from typing import Dict, List, Optional, Tuple, Literal, Any
from maa.context import Context
from maa.custom_action import CustomAction
from maa.custom_recognition import CustomRecognition
from maa.define import OCRResult, Rect, RecognitionDetail
from dataclasses import dataclass
import json
import os


# 定义基本参数
warehouse_roi: List[int] = [303, 138, 391, 495]
warehouse_page_turning_path: List[List[int]] = [[473, 625, 0, 0], [473, 160, 0, 0]]
shop_roi: List[int] = [284, 93, 958, 606]
shop_page_turning_path: List[List[int]] = [[759, 605, 0, 0], [759, 93, 0, 0]]
ocr_score_threshold: float = 0.8
max_failed_num: int = 5


@dataclass
class ResultMatchPrecursor:
    """封装OCR初步分类后的结果，用于进一步匹配"""
    identifier: int | str
    position: Rect

    def corner(self, sign: int) -> Tuple[int, int]:
        """sign为0,1,2,3时分别表示左上、右上、左下、右下角"""
        match sign:  # 无需在意“此代码不可到达”，纯粹是因为PyCharm抽风
            case 0: return self.position.x, self.position.y
            case 1: return self.position.x+self.position.w, self.position.y
            case 2: return self.position.x, self.position.y+self.position.h
            case 3: return self.position.x+self.position.w, self.position.y+self.position.h
            case _: raise ValueError("sign的值只能为0,1,2,3")


def box_rectify(box: Any) -> Rect:
    """将所有可能用于表示ROI的类型统一为Rect"""
    if (isinstance(box, list) or isinstance(box, tuple)) and len(box) == 4:
        return Rect(*box)
    elif isinstance(box, Rect):
        return box
    else:
        raise ValueError("仓库扫描：box_rectify需要传入长度为4的列表/元组或Rect实例")

def calculate_distance(p1: Tuple[int, int], p2: Tuple[int, int]) -> int:
    """计算两点间的曼哈顿距离"""
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


class WarehouseScan(CustomRecognition):
    """
    扫描仓库；
    在AnalyzeResult.detail中返回json字符串{食材名: 数量}；
    传入的argv.image不会使用，建议传入np.zeros((1,1,3), dtype=np.uint8)；
    继承CustomRecognition是为了能够返回识别结果
    """
    def analyze(self,
                context: Context,
                argv: CustomRecognition.AnalyzeArg
                ) -> CustomRecognition.AnalyzeResult:
        self.define_basic_tasks(context)
        context.run_task("进入餐厅仓库")

        warehouse_stock: Dict[str, int] = {}
        failed_num = 0
        while True:
            is_last_page = False
            recorded_items = warehouse_stock.keys()
            screenshot = context.tasker.controller.post_screencap().wait().get()

            # 记录食材名和数量的识别结果
            unprocessed_category = context.run_recognition("gain_warehouse_category", screenshot)
            if unprocessed_category and unprocessed_category.filtered_results:
                category: List[OCRResult] = [
                    result for result in unprocessed_category.filtered_results if result.score > ocr_score_threshold
                ]
            else:
                if failed_num >= max_failed_num:
                    context.run_task("点击下方空白")
                    return CustomRecognition.AnalyzeResult(argv.roi, warehouse_stock)
                else:
                    failed_num += 1
                    continue

            # 排序后打包
            for item, num in self.match_items_and_quantities(category).items():
                if item in recorded_items:  # 本页有食材已经被记录过，说明本页是最后一页
                    is_last_page = True
                    continue
                warehouse_stock[item] = num

            if is_last_page:
                break
            else:
                context.run_task("warehouse_page_turning")

        context.run_task("点击下方空白")
        return CustomRecognition.AnalyzeResult(argv.roi, warehouse_stock)

    def match_items_and_quantities(self, ocr_results: List[OCRResult]) -> Dict[str, int]:
        """匹配OCR结果中的物品名及其对应的数量"""
        items: List[ResultMatchPrecursor] = []
        quantities: List[ResultMatchPrecursor] = []
        matched: Dict[str, int] = {}
        for result in ocr_results:  # 区分物品名和数量
            try:
                quantities.append(ResultMatchPrecursor(self.parse_number(result.text), box_rectify(result.box)))
            except ValueError:
                items.append(ResultMatchPrecursor(result.text, box_rectify(result.box)))

        for item in items:
            min_distance = float('inf')
            best_match_quantity: Optional[ResultMatchPrecursor] = None
            if not quantities: break

            for quantity in quantities:
                # 取名称右上角、数字左下角作为识别点
                current_distance = calculate_distance(item.corner(1), quantity.corner(2))
                if current_distance < min_distance:
                    min_distance = current_distance
                    best_match_quantity = quantity

            if best_match_quantity:
                matched[item.identifier] = best_match_quantity.identifier
                quantities.remove(best_match_quantity)

        return matched

    @staticmethod
    def define_basic_tasks(context: Context):
        # 匹配食材名称和数量（汉字 | 纯数字 | 结尾带K,M,B的简写数字）
        context.override_pipeline({
            "gain_warehouse_category": {
                "recognition": {
                    "type": "OCR",
                    "param": {
                        "roi": warehouse_roi,
                        "expected": "^([\\u4e00-\\u9fa5]+)|((?:\\d+\\.\\d*|\\d+)[kKmMbB]?)$"
                    }
                },
                "on_error": ["空白任务"]
            }
        })
        # 仓库翻页
        context.override_pipeline({
            "warehouse_page_turning": {
                "action": {
                    "type": "Swipe",
                    "param": {
                        "begin": warehouse_page_turning_path[0],
                        "end": warehouse_page_turning_path[1],
                        "duration": 2000,
                        "end_hold": 1000
                    }
                },
                "post_delay": 500
            }
        })

    @staticmethod
    def parse_number(unparsed: str) -> int:
        """将带有K,M,B的简写数字解析为整数"""
        unparsed = unparsed.strip().upper()
        suffixes = {'K': 10 ** 3, 'M': 10 ** 6, 'B': 10 ** 9}
        if unparsed[-1] in suffixes:
            return int(float(unparsed[:-1]) * suffixes[unparsed[-1]])
        return int(float(unparsed))


class ShopScan(CustomRecognition):
    """
    扫描商店；
    在AnalyzeResult.detail中返回json字符串{食材名: 限购数}；
    传入的argv.image不会使用，建议传入np.zeros((1,1,3), dtype=np.uint8)
    继承CustomRecognition是为了能够返回识别结果
    """
    def analyze(self,
                context: Context,
                argv: CustomRecognition.AnalyzeArg
                ) -> CustomRecognition.AnalyzeResult:
        self.define_basic_tasks(context)
        merchandises = self.load_total_merchandise_dic()

        context.run_task("进入餐厅商店")
        shop_stock: Dict[str, int] = {}
        failed_num = 0
        while True:
            is_last_page = False
            screenshot = context.tasker.controller.post_screencap().wait().get()

            # 记录食材
            unprocessed_category = context.run_recognition("gain_shop_category", screenshot)
            if unprocessed_category and unprocessed_category.filtered_results:
                category: List[str] = self.filter_eligible_ingredients(unprocessed_category)
            else:
                if failed_num >= max_failed_num:  # 超过最大失败次数，返回当前结果
                    context.run_task("返回上级菜单")
                    return CustomRecognition.AnalyzeResult(argv.roi, shop_stock)
                else:
                    failed_num += 1
                    continue

            for ingredient in category:
                if ingredient in shop_stock.keys():  # 食材已记录，表明本页是最后一页
                    is_last_page = True
                    continue
                if ingredient in merchandises.keys():
                    shop_stock[ingredient] = merchandises[ingredient]

            if is_last_page:
                break
            else:
                context.run_action("shop_page_turning")

        context.run_task("点击下方空白")
        context.run_task("返回上级菜单")
        return CustomRecognition.AnalyzeResult(argv.roi, shop_stock)

    @staticmethod
    def load_total_merchandise_dic() -> Dict[str, int]:
        # 由于每种食材的限购数固定，直接读取记录即可，无需独立扫描
        with open(
                os.path.join(os.getcwd(), "custom_task_config\\restaurant\\ingredients.json"),
                "r", encoding="UTF-8"
        ) as merchandises_dic:
            return {name: int(param["shop_daily_limit"]) for name, param in json.load(merchandises_dic).items()}

    @staticmethod
    def filter_eligible_ingredients(recognition_results: RecognitionDetail) -> List[str]:
        category: List[ResultMatchPrecursor] = []
        sold_out_signs: List[ResultMatchPrecursor] = []
        for result in recognition_results.filtered_results:
            if result.score > ocr_score_threshold:
                if "限购" not in result.text and "本日售罄" not in result.text:  # 食材名
                    category.append(ResultMatchPrecursor(result.text, box_rectify(result.box)))
                elif "本日售罄" in result.text:  # 售罄标志
                    sold_out_signs.append(ResultMatchPrecursor(result.text, box_rectify(result.box)))

        # 删除category中位于售罄标志下方最近的食材
        for sign in sold_out_signs:
            min_distance = float("inf")
            nearest_ingredient: Optional[ResultMatchPrecursor] = None
            for ingredient in category:
                if ingredient.position.y <= sign.position.y:
                    continue  # 食材位于售罄标志上方
                current_distance = calculate_distance(sign.corner(0), ingredient.corner(0))  # 均取左上角作为判定点
                if current_distance < min_distance:
                    nearest_ingredient = ingredient
                    min_distance = current_distance

            if nearest_ingredient:
                category.remove(nearest_ingredient)

        return [filtered.identifier for filtered in category]


    @staticmethod
    def define_basic_tasks(context: Context):
        # 识别物品名、限购数
        context.override_pipeline({
            "gain_shop_category": {
                "recognition": {
                    "type": "OCR",
                    "param": {
                        "roi": shop_roi,
                        "expected": "^[\\u4e00-\\u9fa5]+$",
                        "replace": ["售馨", "售罄"]
                    }
                },
                "on_error": ["空白任务"]
            },
            "shop_page_turning": {
                "action": {
                    "type": "Swipe",
                    "param": {
                        "begin": shop_page_turning_path[0],
                        "end": shop_page_turning_path[1],
                        "duration": 2000
                    }
                },
                "post_delay": 500
            }
        })


class ShopPurchase(CustomAction):
    """
    购买食材；
    需要在argv.custom_action_param中传入购买字典 {食材名: 需求数量}
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult | bool:
        unprocessed_demands: Dict[str, int] = json.loads(argv.custom_action_param)["demands"]
        option: Literal['BuyAllDemand', 'OnlyBuyDemand'] = json.loads(argv.custom_action_param)["option"]
        if option == 'BuyAllDemand':  # 购买全部
            demands: List[str] = list(unprocessed_demands.keys())
        else:  # 仅购买需求
            demands: List[str] = list(
                {name: num for name, num in unprocessed_demands.items() if num > 0}.keys()
            )

        self.define_basic_tasks(context)

        context.run_task("进入餐厅商店")
        context = context.clone()
        purchased_items: List[str] = []
        page_num = 1
        while True:
            screenshot = context.tasker.controller.post_screencap().wait().get()
            # 在当前页面筛选购买列表中的目标
            recognition_detail = context.run_recognition("gain_shop_category", screenshot, {
                "gain_shop_category": {
                    "recognition": {
                        "type": "OCR",
                        "param": {
                            "roi": shop_roi,
                            "expected": demands
                        }
                    },
                    "timeout": 5000,
                    "on_error": ["空白任务"]
                }
            })
            if recognition_detail is None or not recognition_detail.filtered_results:  # 无结果，翻页后继续
                context.run_task("shop_page_turning")
                page_num += 1
                continue

            current_demands = [
                filtered_result for filtered_result in recognition_detail.filtered_results
                if filtered_result.score > ocr_score_threshold and filtered_result.text in demands
            ]
            for current_demand in current_demands:
                if current_demand.text in purchased_items:
                    page_num = 3  # 出现重复匹配项，已经到达尾页
                    continue
                target_roi = self.safe_get_roi(current_demand)
                if target_roi is None:
                    continue  # 跳过无法获取 roi 的项目

                context.run_task("click_item", {
                    "click_item": {
                        "action": {
                            "type": "Click",
                            "param": {
                                "target": target_roi,
                            }
                        },
                        "post_wait_freeze": 1000
                    }
                })
                context.run_task("餐厅商店_点击最大")
                context.run_task("餐厅商店_点击购买")
                purchased_items.append(current_demand.text)
                demands.remove(current_demand.text)

            if page_num >= 3:  # 最多下滑两次
                break
            else:
                page_num += 1
                context.run_action("shop_page_turning")

        context.run_task("返回上级菜单")
        return CustomAction.RunResult(success=True)

    @staticmethod
    def safe_get_roi(result: OCRResult) -> Optional[List[int]]:
        """安全地获取 OCRResult 的 box roi，支持列表和 Rect 两种格式"""
        box = getattr(result, 'box', None)

        # 如果 box 已经是列表格式 [x, y, w, h]，直接返回
        if isinstance(box, list) and len(box) == 4:
            return box
        # 如果 box 是元组格式 (x, y, w, h)，转换为列表
        elif isinstance(box, tuple) and len(box) == 4:
            return list(box)
        # 如果 box 是 Rect 对象，将其转为列表
        elif isinstance(box, Rect):
            return list(box)

        return None

    @staticmethod
    def box_center(box: Rect) -> Tuple[int, int]:
        return box.x + box.w // 2, box.y + box.h // 2

    @staticmethod
    def define_basic_tasks(context: Context):
        context.override_pipeline({
            "shop_page_turning": {
                "action": {
                    "type": "Swipe",
                    "param": {
                        "begin": shop_page_turning_path[0],
                        "end": shop_page_turning_path[1],
                        "duration": 2000
                    }
                },
                "post_delay": 500
            }
        })