from maa.context import Context
from maa.custom_action import CustomAction
from maa.define import Rect, RecognitionDetail
from typing import Dict, Any, Literal
import numpy as np
import time
import json
import os

# 由于MFW的缺陷，在导入自定义模块时需要使用sys将MFW.exe所在目录加入sys.path，并从该路径导入模块
# 以下导入路径仅适用打包后的代码，如果在这里显示错误那纯粹是IDE抽风，实际上可以正常运行
from pathlib import Path
import sys
current_file = Path(__file__).resolve()
sys.path.append(str(current_file.parent.parent.parent))
from custom.action.RestaurantOptimization import RestaurantOptimizer


class RestaurantMainProcess(CustomAction):
    """传入决策过程需要最大化收益的时间: float"""
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult | bool:
        # 加载基本参数
        absolute_config_path: str = os.path.join(os.getcwd(), "custom_task_config\\restaurant")
        empty_pix: np.ndarray[tuple[int, int, int], np.uint8] = np.zeros((1,1,3), dtype=np.uint8)
        self.define_basic_tasks(context)
        estimated_selling_time: str = json.loads(argv.custom_action_param)["estimated_selling_time"]
        ingredients_purchase_option: Literal['BuyAllDemand', 'OnlyBuyDemand', 'DoNotBuy'] = json.loads(
            argv.custom_action_param
        )["ingredients_purchase_option"]

        warehouse_storage = self.decode_scanning_results(context.run_recognition("warehouse_scan", empty_pix))
        shop_storage = self.decode_scanning_results(context.run_recognition("shop_scan", empty_pix)) \
            if ingredients_purchase_option != "DoNotBuy" else {}  # 购买选项为DoNotBuy时不扫描商店，也不视其中食材为可用

        try:
            decision_time = float(estimated_selling_time)
            optimizer = RestaurantOptimizer(absolute_config_path, warehouse_storage, shop_storage, decision_time)
        except (json.decoder.JSONDecodeError, ValueError):
            optimizer = RestaurantOptimizer(absolute_config_path, warehouse_storage, shop_storage)

        '''上架流程'''
        while True:
            solutions, demands = optimizer.find_best_solution()
            if not solutions:
                self.push_message(context, "未得出上架计划，跳过任务")
                break
                
            # 购买任务触发条件：demands不为空 且 (购买选项为BuyAllDemand 或 (购买选项为OnlyBuyDemand 且 demands的值至少有一个大于0))
            if demands and (ingredients_purchase_option == "BuyAllDemand" or
                            (ingredients_purchase_option == "OnlyBuyDemand" and max(demands.values()) >0)):
                context.run_task("shop_purchase", {
                    "shop_purchase": {
                        "action": {
                            "type": "Custom",
                            "param": {
                                "custom_action": "ShopPurchase",
                                "custom_action_param": {
                                    "demands" : demands,
                                    "option": ingredients_purchase_option
                                }
                            }
                        },
                        "on_error": ["返回上级菜单"]
                    }
                })

            # 上架菜品
            context.run_task("进入今日菜单")
            context.run_task("下架菜品任务")
            for solution in solutions:
                context.run_task("choose_cooker", {
                    "choose_cooker": {
                        "recognition": {
                            "type": "OCR",
                            "param": {
                                "roi": [110, 143, 184, 381],
                                "expected": [solution.dish.cookware]
                            }
                        },
                        "action": "Click"
                    }
                })  # 进入对应厨具的界面
                for _ in range(3):  # 尝试寻找菜品并上架
                    target_dish = context.run_recognition("reco_planned_dish",
                                                          context.tasker.controller.post_screencap().wait().get(),
                                                          {
                                                              "reco_planned_dish": {
                                                                  "recognition": {
                                                                      "type": "OCR",
                                                                      "param": {
                                                                          "roi": [303, 136, 384, 511],
                                                                          "expected": [solution.dish.name]
                                                                      }
                                                                  },
                                                                  "timeout": 3000,
                                                                  "on_error": ["空白任务"]
                                                              }
                                                          })
                    if target_dish is None or target_dish.best_result is None:  # 未找到对应菜品，下滑并再次寻找
                        context.run_task("menu_page_turning")
                        continue
                    else:
                        context.run_task("add_planned_dish", {
                            "add_planned_dish": {
                                "action": {
                                    "type": "Click",
                                    "param": {
                                        "target": list(Rect(*target_dish.box)+Rect(190, 20, 0, 0))
                                    }
                                },
                                "post_wait_freeze": 1000
                            }
                        })
                        bar_end_x = round(681 + (865 - 681) * solution.bar_ratio + 0.5)  # 向上取整
                        context.run_task("swipe_menu_bar", {
                            "swipe_menu_bar": {
                                "action": {
                                    "type": "Swipe",
                                    "param": {
                                        "begin": [681, 522, 1, 1],
                                        "end": [bar_end_x, 522, 1, 1],
                                        "duration": 1000
                                    }
                                }
                            }
                        })
                        context.run_task("add_dish")
                        time.sleep(3)
                        break
                else:  # 菜品未找到，发送信息至操作界面
                    self.push_message(context, f"菜品 {solution.dish.name} 未找到")

            # 上架菜品流程结束，退出菜谱界面和外层while循环
            context.run_action("点击下方空白")
            break

        '''餐厅任务完成，退出至主页'''
        context.run_task("直接返回主菜单")
        return CustomAction.RunResult(success=True)

    @staticmethod
    def decode_scanning_results(scanning_results: RecognitionDetail) -> Dict[str, int]:
        # 由于WarehouseScan和ShopScan的设计，best_result中必定有结果，无需判断是否为None
        encoded = scanning_results.best_result.detail
        if isinstance(encoded, str):
            return json.loads(encoded)
        if isinstance(encoded, dict):
            return encoded
        return {}

    @staticmethod
    def push_message(context: Context, message: Any):
        context.run_task("push_message", {
            "push_message": {
                "focus": {
                    "Node.Action.Starting": f"{message}"
                }
            }
        })

    @staticmethod
    def define_basic_tasks(context: Context):
        # 定义餐厅自定义任务
        context.override_pipeline({
            "shop_scan": {
                "recognition": {
                    "type": "Custom",
                    "param": {
                        "custom_recognition": "ShopScan"
                    }
                }
            },
            "warehouse_scan": {
                "recognition": {
                    "type": "Custom",
                    "param": {
                        "custom_recognition": "WarehouseScan"
                    }
                }
            },
            "menu_page_turning": {
                "action": {
                    "type": "Swipe",
                    "param": {
                        "begin": [480, 623, 0, 0],
                        "end": [480, 136, 0, 0],
                        "duration": 2000,
                        "end_hold": 1000
                    }
                }
            },
            "add_dish": {
                "recognition": {
                    "type": "OCR",
                    "param": {
                        "roi": [718, 574, 152, 68],
                        "expected": ["上架"]
                    }
                },
                "action": "Click",
                "post_wait_freeze": 2000
            }
        })