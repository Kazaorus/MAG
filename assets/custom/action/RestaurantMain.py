from maa.context import Context
from maa.custom_action import CustomAction
from maa.define import Rect
from typing import Dict, Any, Optional
import numpy as np
import time
import json
import os

# 由于MFW前端的缺陷，在导入自定义模块时需要使用sys将MFW.exe所在目录加入sys.path，并从该路径导入模块
# 以下导入路径仅适用打包后的代码，若IDE报错请无视，经实际测试可以正常运行
from pathlib import Path
import sys
current_file = Path(__file__).resolve()
sys.path.append(str(current_file.parent.parent.parent))
from custom.action.RestaurantDecider.RestaurantDecider import RestaurantOptimizer, DecisionResult, PurchaseStrategy


# ── 常量 ──────────────────────────────────────────────────
EMPTY_IMAGE: np.ndarray = np.zeros((1, 1, 3), dtype=np.uint8)

# 界面坐标常量
COOKWARE_ROI: list = [110, 143, 184, 381]
DISH_LIST_ROI: list = [303, 136, 384, 511]
ADD_BUTTON_OFFSET: Rect = Rect(190, 20, 0, 0)  # 从菜品名到"添加"按钮的偏移
BAR_START_X: int = 681
BAR_END_X: int = 865
BAR_Y: int = 522
MENU_SWIPE_BEGIN: list = [480, 623, 0, 0]
MENU_SWIPE_END: list = [480, 136, 0, 0]
ADD_DISH_ROI: list = [718, 574, 152, 68]

MAX_DISH_SEARCH_ATTEMPTS: int = 3
DEFAULT_SELLING_TIME: float = 32.0

# 前端参数名到内部枚举的映射
STRATEGY_MAPPING: Dict[str, PurchaseStrategy] = {
    "BuyAllDemand": PurchaseStrategy.BUY_ALL,
    "OnlyBuyDemand": PurchaseStrategy.BUY_MISSING,
    "DoNotBuy": PurchaseStrategy.NO_PURCHASE,
}


class RestaurantMainProcess(CustomAction):
    """
    餐厅经营自动化主流程。
    传入参数（通过 custom_action_param JSON）：
    - estimated_selling_time: float, 预计售卖时间（小时）
    - ingredients_purchase_option: "BuyAllDemand" | "OnlyBuyDemand" | "DoNotBuy"
    """
    def run(
            self, context: Context, argv: CustomAction.RunArg
    ) -> CustomAction.RunResult | bool:
        '''初始化'''
        params = json.loads(argv.custom_action_param)
        config_path = os.path.join(
            Path(__file__).resolve().parent.parent.parent,
            "custom_task_config", "restaurant"
        )
        self._define_tasks(context)

        '''扫描仓库与商店'''
        warehouse_storage = self._scan_storage(context, "warehouse_scan")
        if params.get("ingredients_purchase_option", "OnlyBuyDemand") != "DoNotBuy":
            shop_storage = self._scan_storage(context, "shop_scan")
        else:
            shop_storage = {}

        '''优化求解'''
        optimizer = RestaurantOptimizer(
            json_dish=self._load_str_dishes(config_path),
            json_player_status=self._load_str_player_status(config_path),
            warehouse_storage=warehouse_storage,
            shop_storage=shop_storage,
            time_limit=float(params.get("estimated_selling_time", DEFAULT_SELLING_TIME)),
            strategy=params.get("ingredients_purchase_option", "OnlyBuyDemand"),
            purchase_threshold=int(params.get("purchase_threshold", 0)),
        )
        result = optimizer.find_best_solution()
        self._push_message(context, str(result))

        if not result.solutions:
            self._push_message(context, "未得出上架计划，跳过任务")
            context.run_task("直接返回主菜单")
            return CustomAction.RunResult(success=True)

        '''执行操作'''
        self._execute_purchase(context, result)
        self._execute_serving(context, result)

        '''返回主页'''
        context.run_task("直接返回主菜单")
        return CustomAction.RunResult(success=True)

    @staticmethod
    def _scan_storage(context: Context, task_name: str) -> Dict[str, int]:
        """执行仓库或商店扫描，返回 {名称: 数量} 字典"""
        detail = context.run_recognition(task_name, EMPTY_IMAGE)
        if detail is None or detail.best_result is None:
            return {}
        result = detail.best_result.detail
        if isinstance(result, str):
            return json.loads(result)
        if isinstance(result, dict):
            return result
        return {}

    @staticmethod
    def _execute_purchase(
            context: Context,
            result: DecisionResult
    ):
        """菜品购买流程"""
        if result.strategy == PurchaseStrategy.NO_PURCHASE:
            return
        if not result.purchase_plan:
            return

        # BUY_ALL: 购买计划中所有食材都要买
        # BUY_MISSING: 购买计划中只包含确实缺少的食材
        if result.strategy == PurchaseStrategy.BUY_ALL:
            option: int = PurchaseStrategy.BUY_ALL.value
        else:
            option: int = PurchaseStrategy.BUY_MISSING.value

        context.run_task("shop_purchase", {
            "shop_purchase": {
                "action": {
                    "type": "Custom",
                    "param": {
                        "custom_action": "ShopPurchase",
                        "custom_action_param": {
                            "demands": result.purchase_plan,
                            "option": option
                        },
                    },
                },
                "on_error": ["返回上级菜单"]
            }
        })

    def _execute_serving(self, context: Context, result: DecisionResult):
        """执行菜品上架流程"""
        context.run_task("进入今日菜单")
        context.run_task("下架菜品任务")

        for solution in result.solutions:
            if solution.count <= 0:
                continue

            # 选择对应厨具
            context.run_task("choose_cooker", {
                "choose_cooker": {
                    "recognition": {
                        "type": "OCR",
                        "param": {
                            "roi": COOKWARE_ROI,
                            "expected": [solution.dish.cookware]
                        },
                    },
                    "action": "Click"
                }
            })

            # 查找并上架菜品
            if not self._find_and_serve_dish(context, solution):
                self._push_message(
                    context, f"菜品 {solution.dish.name} 未找到"
                )

        context.run_action("点击下方空白")

    def _find_and_serve_dish(self, context: Context, solution) -> bool:
        """
        在菜品列表中查找目标菜品并上架。
        返回是否成功找到并上架。
        """
        for attempt in range(MAX_DISH_SEARCH_ATTEMPTS):
            screenshot = context.tasker.controller.post_screencap().wait().get()
            target = context.run_recognition(
                "reco_planned_dish", screenshot,
                {
                    "reco_planned_dish": {
                        "recognition": {
                            "type": "OCR",
                            "param": {
                                "roi": DISH_LIST_ROI,
                                "expected": [solution.dish.name]
                            },
                        },
                        "timeout": 3000,
                        "on_error": ["空白任务"]
                    }
                }
            )

            if target is None or target.best_result is None:
                # 未找到，翻页后重试
                context.run_task("menu_page_turning")
                continue

            # 点击菜品旁的添加按钮
            dish_box = Rect(*target.best_result.box) if not isinstance(
                target.best_result.box, Rect
            ) else target.best_result.box
            add_button_target = [
                dish_box.x + ADD_BUTTON_OFFSET.x,
                dish_box.y + ADD_BUTTON_OFFSET.y,
                ADD_BUTTON_OFFSET.w,
                ADD_BUTTON_OFFSET.h,
            ]

            context.run_task("add_planned_dish", {
                "add_planned_dish": {
                    "action": {
                        "type": "Click",
                        "param": {"target": add_button_target}
                    },
                    "post_wait_freeze": 1000
                }
            })

            # 拖动进度条
            self._swipe_bar(context, solution.bar_ratio)

            # 点击上架
            context.run_task("add_dish")
            time.sleep(3)
            return True

        return False

    @staticmethod
    def _swipe_bar(context: Context, ratio: float):
        """根据比例拖动进度条"""
        if ratio <= 0:
            return

        bar_target_x = round(BAR_START_X + (BAR_END_X - BAR_START_X) * ratio + 0.5)
        bar_target_x = min(bar_target_x, BAR_END_X)  # 防止超出终点
        context.run_task("swipe_menu_bar", {
            "swipe_menu_bar": {
                "action": {
                    "type": "Swipe",
                    "param": {
                        "begin": [BAR_START_X, BAR_Y, 1, 1],
                        "end": [bar_target_x, BAR_Y, 1, 1],
                        "duration": 1000
                    }
                }
            }
        })

    @staticmethod
    def _parse_selling_time(raw_value) -> Optional[float]:
        """安全解析售卖时间，失败返回 None（使用优化器默认值）"""
        if raw_value is None:
            return None
        try:
            value = float(raw_value)
            return value if value > 0 else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _push_message(context: Context, message: Any):
        context.run_task("push_message", {
            "push_message": {
                "focus": {
                    "Node.Action.Starting": str(message),
                },
            },
        })

    @staticmethod
    def _define_tasks(context: Context):
        context.override_pipeline({
            "shop_scan": {
                "recognition": {
                    "type": "Custom",
                    "param": {"custom_recognition": "ShopScan"}
                }
            },
            "warehouse_scan": {
                "recognition": {
                    "type": "Custom",
                    "param": {"custom_recognition": "WarehouseScan"}
                }
            },
            "menu_page_turning": {
                "action": {
                    "type": "Swipe",
                    "param": {
                        "begin": MENU_SWIPE_BEGIN,
                        "end": MENU_SWIPE_END,
                        "duration": 2000,
                        "end_hold": 1000
                    },
                }
            },
            "add_dish": {
                "recognition": {
                    "type": "OCR",
                    "param": {
                        "roi": ADD_DISH_ROI,
                        "expected": ["上架"]
                    },
                },
                "action": "Click",
                "post_wait_freeze": 2000
            }
        })

    @staticmethod
    def _load_str_dishes(config_path: str) -> str:
        with open(
                os.path.join(
                    config_path,
                    "dishes.json"
                ),"r", encoding="utf-8"
        ) as f:
            return f.read()

    @staticmethod
    def _load_str_player_status(config_path: str) -> str:
        with open(
                os.path.join(
                    config_path,
                    "player_status.json"
                ),"r", encoding="utf-8"
        ) as f:
            return f.read()
