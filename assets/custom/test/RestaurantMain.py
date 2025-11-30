from maa.context import Context
from maa.custom_action import CustomAction
from maa.define import Rect, RecognitionDetail
from RestaurantOptimization import RestaurantOptimizer
from typing import Dict
import numpy as np
import json
import os


class RestaurantMainProcess(CustomAction):
    """传入决策过程需要最大化收益的时间: float"""
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult | bool:
        absolute_config_path: str = os.path.join(os.getcwd(), "custom_task_config\\restaurant")
        empty_pix: np.ndarray[tuple[int, int, int], np.uint8] = np.zeros((1,1,3), dtype=np.uint8)
        warehouse_storage = self.decode_scanning_results(context.run_recognition("warehouse_scan", empty_pix))
        shop_storage = self.decode_scanning_results(context.run_recognition("shop_scan", empty_pix))

        try:
            decision_time = float(json.loads(argv.custom_action_param))
            optimizer = RestaurantOptimizer(absolute_config_path, warehouse_storage, shop_storage, decision_time)
        except (json.decoder.JSONDecodeError, ValueError):
            optimizer = RestaurantOptimizer(absolute_config_path, warehouse_storage, shop_storage)

        self.define_basic_tasks(context)

        '''上架流程'''
        while True:
            context.run_task("shop_scan")
            optimizer.shop_info_wrought = True
            solutions, demands = optimizer.find_best_solution()

            if not solutions:
                self.push_message(context, "未得出上架计划，跳过任务")
                break
            if demands:
                context.run_task("shop_purchase", {
                    "shop_purchase": {
                        "action": {
                            "type": "Custom",
                            "param": {
                                "custom_action": "ShopPurchase",
                                "custom_action_param": list(demands)
                            }
                        },
                        "on_error": ["返回上级菜单"]
                    }
                })
            context.run_task("进入今日菜单")
            context.run_task("下架菜品任务")

            # 上架菜品
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
                        break
                else:  # 菜品未找到，发送信息至操作界面
                    self.push_message(context, f"菜品 {solution.dish.name} 未找到")

            # 上架菜品流程结束，退出菜谱界面和外层while循环
            context.run_action("点击下方空白")
            break

        '''仓库扫描流程'''
        context.run_task("warehouse_scan")

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
    def push_message(context: Context, message: str, text_size: int = 20, text_color: str="red"):
        context.run_task("push_message", {
            "push_message": {
                "focus": {
                    "start": f"[size:{text_size}][color:{text_color}]{message}[/color][/size]"
                }
            }
        })

    @staticmethod
    def define_basic_tasks(context: Context):
        # 定义餐厅自定义任务
        context.override_pipeline({
            "shop_scan": {
                "action": {
                    "type": "Custom",
                    "param": {
                        "custom_action": "ShopScan"
                    }
                }
            },
            "warehouse_scan": {
                "action": {
                    "type": "Custom",
                    "param": {
                        "custom_action": "WarehouseScan"
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
                "post_wait_freeze": 1000
            }
        })