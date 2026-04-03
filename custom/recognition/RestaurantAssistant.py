from typing import Dict, List, Optional, Tuple, Set, Any
from maa.context import Context
from maa.custom_action import CustomAction
from maa.custom_recognition import CustomRecognition
from maa.define import OCRResult, Rect, RecognitionDetail
from dataclasses import dataclass
import json
import os


from pathlib import Path
import sys
current_file = Path(__file__).resolve()
sys.path.append(str(current_file.parent.parent.parent))
from custom.action.RestaurantDecider.RestaurantDecider import PurchaseStrategy

# ── 基本参数 ──────────────────────────────────────────────
WAREHOUSE_ROI: List[int] = [303, 138, 391, 495]
WAREHOUSE_SWIPE_BEGIN: List[int] = [473, 625]
WAREHOUSE_SWIPE_END: List[int] = [473, 160]

SHOP_ROI: List[int] = [284, 93, 958, 606]
SHOP_SWIPE_BEGIN: List[int] = [759, 605]
SHOP_SWIPE_END: List[int] = [759, 93]

OCR_SCORE_THRESHOLD: float = 0.8
MAX_FAILED_NUM: int = 5
SHOP_MAX_PAGES: int = 3  # 商店最多翻页次数（含首页）


@dataclass
class OcrItem:
    """封装OCR初步分类后的结果，用于进一步匹配"""
    identifier: int | str
    position: Rect

    def corner(self, sign: int) -> Tuple[int, int]:
        """
        获取矩形角点坐标。
        sign: 0=左上, 1=右上, 2=左下, 3=右下
        """
        x, y, w, h = self.position.x, self.position.y, self.position.w, self.position.h
        corners = {
            0: (x, y),
            1: (x + w, y),
            2: (x, y + h),
            3: (x + w, y + h),
        }
        if sign not in corners:
            raise ValueError("sign的值只能为0,1,2,3")
        return corners[sign]


# ── 工具函数 ──────────────────────────────────────────────
def to_rect(box: Any) -> Rect:
    """将所有可能用于表示ROI的类型统一为Rect"""
    if isinstance(box, Rect):
        return box
    if isinstance(box, (list, tuple)) and len(box) == 4:
        return Rect(*box)
    raise ValueError(f"to_rect: 需要长度为4的列表/元组或Rect实例，收到 {type(box)}")


def to_roi_list(box: Any) -> Optional[List[int]]:
    """将各种box格式安全地转为 [x, y, w, h] 列表"""
    if isinstance(box, Rect):
        return [*box]
    if isinstance(box, (list, tuple)) and len(box) == 4:
        return list(box)
    return None


def manhattan_distance(p1: Tuple[int, int], p2: Tuple[int, int]) -> int:
    """计算两点间的曼哈顿距离"""
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


def parse_number(text: str) -> int:
    """将带有K/M/B后缀的简写数字解析为整数，无法解析时抛出ValueError"""
    text = text.strip().upper()
    if not text:
        raise ValueError("空字符串")
    suffixes = {'K': 10 ** 3, 'M': 10 ** 6, 'B': 10 ** 9}
    if text[-1] in suffixes:
        return int(float(text[:-1]) * suffixes[text[-1]])
    return int(float(text))


def define_swipe_task(context: Context, task_name: str,
                      begin: List[int], end: List[int],
                      duration: int = 2000, post_delay: int = 500,
                      end_hold: int = 0):
    """定义通用的滑动任务"""
    action_param = {
        "begin": begin,
        "end": end,
        "duration": duration,
    }
    if end_hold > 0:
        action_param["end_hold"] = end_hold

    task_config = {
        task_name: {
            "action": {
                "type": "Swipe",
                "param": action_param
            },
            "post_delay": post_delay,
        }
    }
    context.override_pipeline(task_config)


def load_merchandise_limits() -> Dict[str, int]:
    """加载食材限购数据"""
    path = os.path.join(
        os.getcwd(),
        "custom_task_config", "restaurant", "ingredients.json",
    )
    with open(path, "r", encoding="UTF-8") as f:
        data = json.load(f)
    return {
        name: int(param["shop_daily_limit"])
        for name, param in data.items()
    }


def push_message(context: Context, message: str):
    context.run_task("推送消息", {
        "推送消息": {
            "focus": {
                "Node.Action.Starting": message
            }
        }
    })


# ── 仓库扫描 ──────────────────────────────────────────────
class WarehouseScan(CustomRecognition):
    """
    扫描仓库中的食材储量。
    在 AnalyzeResult.detail 中返回 {食材名: 数量}。
    传入的 argv.image 不会使用。
    """

    def __init__(self):
        super().__init__()
        self.context = None

    def analyze(
            self, context: Context, argv: CustomRecognition.AnalyzeArg
    ) -> CustomRecognition.AnalyzeResult:
        self._define_tasks(context)
        context.run_task("进入餐厅仓库")
        merchandise_limits = load_merchandise_limits()
        self.context = context

        warehouse_stock: Dict[str, int] = {}
        consecutive_failures = 0
        while True:
            # 截图识别；处理可能的失败
            ocr_detail = context.run_recognition(
                "gain_warehouse_category",
                context.tasker.controller.post_screencap().wait().get()
            )
            if not ocr_detail or not ocr_detail.filtered_results:
                consecutive_failures += 1
                if consecutive_failures >= MAX_FAILED_NUM:
                    break
                continue
            consecutive_failures = 0

            # 筛选高置信度结果
            confident_results = [
                result for result in ocr_detail.filtered_results
                if result.score >= OCR_SCORE_THRESHOLD
            ]
            if not confident_results:
                consecutive_failures += 1
                if consecutive_failures >= MAX_FAILED_NUM:
                    break
                continue
            # 分类、匹配；若出现重复以首次匹配到的为准
            page_data = self._match_items_to_quantities(
                merchandise_limits,
                *self._classify_ocr_results(confident_results),
            )

            is_last_page = False
            for name, count in page_data.items():
                if name in warehouse_stock:
                    is_last_page = True
                else:
                    warehouse_stock[name] = count

            if is_last_page:
                break

            context.run_task("warehouse_page_turning")

        context.run_task("点击下方空白")
        return CustomRecognition.AnalyzeResult(argv.roi, warehouse_stock)

    @staticmethod
    def _match_items_to_quantities(
            merchandise_limits: Dict[str, int],
            items: List[OcrItem],
            quantities: List[OcrItem]
    ) -> Dict[str, int]:
        """
        将物品名与最近的数量配对。
        使用名称右上角与数字左下角的曼哈顿距离进行匹配。
        """
        matched: Dict[str, int] = {}
        remaining_quantities = quantities.copy()  # 不修改原列表
        filtered_items: List[OcrItem] = [
            item for item in items
            if item.identifier in merchandise_limits
        ]

        for item in filtered_items:
            if not remaining_quantities:
                break

            best_match: Optional[OcrItem] = None
            best_distance = float('inf')

            for qty in remaining_quantities:
                dist = manhattan_distance(item.corner(1), qty.corner(2))
                if dist < best_distance and dist < 150:
                    best_distance = dist
                    best_match = qty

            if best_match is not None:
                matched[item.identifier] = best_match.identifier
                remaining_quantities.remove(best_match)
            else:  # 1经常无法被OCR识别到，因此作为默认结果
                matched[item.identifier] = 1

        return matched

    @staticmethod
    def _classify_ocr_results(
            ocr_results: List[OCRResult],
    ) -> Tuple[List[OcrItem], List[OcrItem]]:
        """
        将OCR结果分为文本项（食材名）和数值项（数量）。
        返回 (items, quantities)
        """
        items: List[OcrItem] = []
        quantities: List[OcrItem] = []
        for result in ocr_results:
            try:
                num = parse_number(result.text)
                quantities.append(OcrItem(num, to_rect(result.box)))
            except (ValueError, IndexError):
                items.append(OcrItem(result.text, to_rect(result.box)))

        return items, quantities

    @staticmethod
    def _define_tasks(context: Context):
        context.override_pipeline({
            "gain_warehouse_category": {
                "recognition": {
                    "param": {
                        "roi": WAREHOUSE_ROI
                    }
                },
                "on_error": ["空白任务"]
            }
        })
        define_swipe_task(
            context, "warehouse_page_turning",
            WAREHOUSE_SWIPE_BEGIN, WAREHOUSE_SWIPE_END,
            duration=2000, post_delay=500, end_hold=1000,
        )


# ── 商店扫描 ──────────────────────────────────────────────
class ShopScan(CustomRecognition):
    """
    扫描商店中可购买的食材。
    在 AnalyzeResult.detail 中返回 {食材名: 限购数}。
    传入的 argv.image 不会使用。
    """
    def analyze(
            self, context: Context, argv: CustomRecognition.AnalyzeArg
    ) -> CustomRecognition.AnalyzeResult:
        self._define_tasks(context)
        merchandise_limits = load_merchandise_limits()
        context.run_task("进入餐厅商店")

        shop_stock: Dict[str, int] = {}
        sold_outs: Set[str] = set()  # 已售罄食材
        consecutive_failures = 0
        page_num = 1
        while page_num <= SHOP_MAX_PAGES:
            # 截图识别；处理可能的失败
            ocr_detail = context.run_recognition(
                "gain_shop_category",
                context.tasker.controller.post_screencap().wait().get()
            )
            if not ocr_detail or not ocr_detail.filtered_results:
                consecutive_failures += 1
                if consecutive_failures >= MAX_FAILED_NUM:
                    break
                continue
            consecutive_failures = 0

            is_last_page = False
            ingredients, sold_out = self._filter_available(ocr_detail)
            sold_outs.update(sold_out)
            for ingredient in ingredients:
                if ingredient in shop_stock:
                    is_last_page = True
                elif ingredient not in sold_outs:
                    # 上一页识别到的售罄食材在下一页可能因为未识别到标志等原因异常加入，因此需要另外排除
                    shop_stock[ingredient] = merchandise_limits[ingredient]

            if is_last_page:
                break

            page_num += 1
            context.run_action("shop_page_turning")

        context.run_task("点击下方空白")
        context.run_task("返回上级菜单")
        return CustomRecognition.AnalyzeResult(argv.roi, shop_stock)

    @staticmethod
    def _filter_available(recognition_detail: RecognitionDetail) -> Tuple[List[str], Set[str]]:
        """
        从OCR结果中筛选可购买的食材名称。
        排除"限购"、"本日售罄"文本，并移除已售罄标记下方最近的食材。
        返回可用食材列表、售罄食材集合
        """
        items: List[OcrItem] = []
        sold_out_signs: List[OcrItem] = []
        sold_out_ingredients: Set[str] = set()

        for result in recognition_detail.filtered_results:
            if result.score <= OCR_SCORE_THRESHOLD:
                continue
            text = result.text
            if "售罄" in text:
                sold_out_signs.append(OcrItem(text, to_rect(result.box)))
            elif "限购" not in text:
                items.append(OcrItem(text, to_rect(result.box)))

        # 移除售罄标记正下方最近的食材
        filtered_items: List[OcrItem] = [
            item for item in items
            if item.identifier in load_merchandise_limits()
        ]
        for sign in sold_out_signs:
            nearest: Optional[OcrItem] = None
            nearest_dist = float("inf")

            for item in filtered_items:
                # 食材必须在售罄标记下方
                if item.position.y <= sign.position.y:
                    continue
                dist = manhattan_distance(sign.corner(0), item.corner(0))
                if dist < nearest_dist:
                    nearest_dist = dist
                    nearest = item

            if nearest is not None:
                filtered_items.remove(nearest)
                sold_out_ingredients.add(nearest.identifier)

        return [item.identifier for item in filtered_items], sold_out_ingredients

    @staticmethod
    def _define_tasks(context: Context):
        context.override_pipeline({
            "gain_shop_category": {
                "recognition": {
                    "type": "OCR",
                    "param": {
                        "roi": SHOP_ROI
                    }
                },
                "on_error": ["空白任务"]
            }
        })
        define_swipe_task(
            context, "shop_page_turning",
            SHOP_SWIPE_BEGIN, SHOP_SWIPE_END,
            duration=2000, post_delay=500
        )

# ── 商店购买 ──────────────────────────────────────────────
class ShopPurchase(CustomAction):
    """
    在商店购买食材。
    需要在 argv.custom_action_param 中传入 JSON:
    {
        "demands": {食材名: 需求数量, ...},
        "option": PurchaseStrategy.value
    }
    """

    def run(
            self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult | bool:
        params = json.loads(argv.custom_action_param)
        demands_dict: Dict[str, int] = params["demands"]
        option: int = params["option"]

        if option == PurchaseStrategy.BUY_ALL.value:  # 根据模式确定购买列表
            pending: List[str] = list(demands_dict.keys())
        else:
            pending: List[str] = [
                name for name, num in demands_dict.items() if num > 0
            ]

        if not pending:
            return CustomAction.RunResult(success=True)

        context = context.clone()
        self._define_tasks(context)
        context.run_task("进入餐厅商店")
        purchased: Set[str] = set()
        page_num = 1
        while pending and page_num <= SHOP_MAX_PAGES:
            # 在当前页面识别待购买的食材
            recognition_detail: RecognitionDetail = context.run_recognition(
                "gain_shop_category",
                context.tasker.controller.post_screencap().wait().get(),
                {
                    "gain_shop_category": {
                        "recognition": {
                            "type": "OCR",
                            "param": {
                                "roi": SHOP_ROI,
                                "expected": pending
                            },
                        },
                        "timeout": 5000,
                        "on_error": ["空白任务"]
                    }
                }
            )
            if not recognition_detail or not recognition_detail.filtered_results:
                page_num += 1
                context.run_task("shop_page_turning")
                continue

            # 筛选高置信度且确实在待购列表中的结果
            found_duplicate = False
            current_matches = [
                r for r in recognition_detail.filtered_results
                if r.score > OCR_SCORE_THRESHOLD and r.text in pending
            ]
            for match in current_matches:
                if match.text in purchased:
                    # 出现已购买项，说明已翻到重复页
                    found_duplicate = True
                    continue

                roi = to_roi_list(match.box)
                if roi is None:
                    continue

                # 点击食材 → 点击最大 → 点击购买
                context.run_task("click_item", {
                    "click_item": {
                        "action": {
                            "type": "Click",
                            "param": {"target": roi},
                        },
                        "post_wait_freeze": 1000,
                    },
                })
                context.run_task("餐厅商店_点击最大")
                context.run_task("餐厅商店_点击购买")
                purchased.add(match.text)
                pending.remove(match.text)

            if found_duplicate or not pending:
                break

            page_num += 1
            if page_num <= SHOP_MAX_PAGES:
                context.run_action("shop_page_turning")

        context.run_task("返回上级菜单")
        return CustomAction.RunResult(success=True)

    @staticmethod
    def _define_tasks(context: Context):
        define_swipe_task(
            context, "shop_page_turning",
            SHOP_SWIPE_BEGIN, SHOP_SWIPE_END,
            duration=2000, post_delay=500,
        )
