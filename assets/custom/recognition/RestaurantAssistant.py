from typing import Dict, List, Optional, Tuple
from maa.context import Context
from maa.custom_action import CustomAction
from maa.custom_recognition import CustomRecognition
from maa.define import OCRResult, Rect, RecognitionDetail
import json
import os


# 定义基本参数
warehouse_roi: List[int] = [303, 138, 391, 495]
warehouse_page_turning_path: List[List[int]] = [[473, 625, 0, 0], [473, 167, 0, 0]]
shop_roi: List[int] = [284, 93, 958, 606]
shop_page_turning_path: List[List[int]] = [[759, 605, 0, 0], [759, 93, 0, 0]]
ocr_score_threshold: float = 0.8
max_failed_num: int = 5


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
            if unprocessed_category and unprocessed_category.filterd_results:
                category: List[OCRResult] = [
                    result for result in unprocessed_category.filterd_results if result.score > ocr_score_threshold
                ]
            else:
                if failed_num >= max_failed_num:
                    context.run_task("点击下方空白")
                    return CustomRecognition.AnalyzeResult(argv.roi, json.dumps(warehouse_stock))
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
        return CustomRecognition.AnalyzeResult(argv.roi, json.dumps(warehouse_stock))

    @staticmethod
    def match_items_and_quantities(ocr_results: List[OCRResult]) -> Dict[str, int]:
        def calculate_distance(p1: Tuple[int, int], p2: Tuple[int, int]) -> int:
            return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])

        def get_box(result: OCRResult) -> Rect:
            if (isinstance(result.box, list) or isinstance(result.box, tuple)) and len(result.box) == 4:
                return Rect(*result.box)
            elif isinstance(result.box, Rect):
                return result.box
            else:
                raise ValueError("仓库扫描：get_box需要传入长度为4的列表/元组或Rect实例")

        items: List[OCRResult] = []
        quantities: List[OCRResult] = []
        matched: Dict[str, int] = {}
        for result in ocr_results:
            # 区分物品名和数量
            try:
                int(result.text)
                quantities.append(result)
            except ValueError:
                items.append(result)

        for item in items:
            item_box = get_box(item)
            item_point = (item_box.x + item_box.w, item_box.y)  # 取roi右上角作为识别点
            min_distance = float('inf')
            best_match_quantity: Optional[OCRResult] = None
            if not quantities:
                break

            for quantity in quantities:
                quantity_box = get_box(quantity)
                quantity_point = (quantity_box.x, quantity_box.y + quantity_box.h)  # 取roi左下角作为识别点
                current_distance = calculate_distance(item_point, quantity_point)
                if current_distance < min_distance:
                    min_distance = current_distance
                    best_match_quantity = quantity

            if best_match_quantity:
                matched[item.text] = int(best_match_quantity.text)
                quantities.remove(best_match_quantity)

        return matched

    @staticmethod
    def define_basic_tasks(context: Context):
        # 匹配食材名称和数量
        context.override_pipeline({
            "gain_warehouse_category": {
                "recognition": {
                    "type": "OCR",
                    "param": {
                        "roi": warehouse_roi,
                        "expected": "^([\\u4e00-\\u9fa5]+|[1-9]\\d*)$"
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
            recorded_items = shop_stock.keys()
            screenshot = context.tasker.controller.post_screencap().wait().get()

            # 记录食材
            unprocessed_category = context.run_recognition("gain_shop_category", screenshot)
            if unprocessed_category and unprocessed_category.filterd_results:
                category: List[OCRResult] = self.filter_eligible_ingredients(unprocessed_category)
            else:
                if failed_num >= max_failed_num:  # 超过最大失败次数，返回当前结果
                    context.run_task("返回上级菜单")
                    return CustomRecognition.AnalyzeResult(argv.roi, json.dumps(shop_stock))
                else:
                    failed_num += 1
                    continue

            for ingredient in category:
                if ingredient.text in recorded_items:
                    is_last_page = True
                    continue
                if ingredient.text in merchandises.keys():
                    shop_stock[ingredient.text] = merchandises[ingredient.text]

            if is_last_page:
                break
            else:
                context.run_action("shop_page_turning")

        context.run_task("返回上级菜单")
        return CustomRecognition.AnalyzeResult(argv.roi, json.dumps(shop_stock))

    @staticmethod
    def load_total_merchandise_dic() -> Dict[str, int]:
        # 由于每种食材的限购数固定，直接读取记录即可，无需独立扫描
        with open(
                os.path.join(os.getcwd(), "custom_task_config\\restaurant\\ingredients.json"),
                "r", encoding="UTF-8"
        ) as merchandises_dic:
            return {name: int(param["shop_daily_limit"]) for name, param in json.load(merchandises_dic).items()}

    @staticmethod
    def filter_eligible_ingredients(recognition_results: RecognitionDetail) -> List[OCRResult]:
        def calculate_distance(p1: Tuple[int, int], p2: Tuple[int, int]) -> int:
            return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])

        category: List[OCRResult] = []
        sold_out_signs: List[OCRResult] = []
        for result in recognition_results.filterd_results:
            if result.score > ocr_score_threshold:
                if "限购" not in result.text and "本日售罄" not in result.text:
                    category.append(result)
                elif "本日售罄" in result.text:
                    sold_out_signs.append(result)

        # 删除category中位于售罄标志下方最近的食材
        for sign in sold_out_signs:
            sign_point = (sign.box[0], sign.box[1])  # 取左上角作为判定点
            min_distance = float("inf")
            nearest_ingredient: Optional[OCRResult] = None
            for ingredient in category:
                if ingredient.box[1] <= sign.box[1]:
                    continue  # 食材位于售罄标志上方
                current_distance = calculate_distance(sign_point, (ingredient.box[0], ingredient.box[1]))
                if current_distance < min_distance:
                    nearest_ingredient = ingredient
                    min_distance = current_distance

            if nearest_ingredient:
                category.remove(nearest_ingredient)

        return category


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
    需要在argv.custom_action_param中传入购买列表 [食材名]
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult | bool:
        demands: List[str] = json.loads(argv.custom_action_param)
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
            if recognition_detail is None or not recognition_detail.filterd_results:  # 无结果，翻页后继续
                context.run_task("shop_page_turning")
                page_num += 1
                continue

            current_demands = [
                filtered_result for filtered_result in recognition_detail.filterd_results
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
        # 如果 box 是 Rect 对象，返回 roi 属性
        elif isinstance(box, Rect):
            return box.roi

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