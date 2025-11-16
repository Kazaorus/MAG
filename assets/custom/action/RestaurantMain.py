from typing import Dict, List, Optional, Tuple
from pathlib import Path
from maa.context import Context
from maa.custom_action import CustomAction
from maa.define import OCRResult, Rect
import json
import sys
import os
import re

# 由于MFW的缺陷，在导入自定义模块时需要使用sys将MFW.exe所在目录加入sys.path，并从该路径导入模块
# 以下导入路径仅适用打包后的代码
current_file = Path(__file__).resolve()
sys.path.append(str(current_file.parent.parent.parent))
from custom.action.RestaurantOptimizer import DataManager, RestaurantOptimizer

# 定义基本参数
warehouse_roi: List[int] = [303, 138, 391, 495]
warehouse_page_turning_path: List[List[int]] = [[473, 625, 0, 0], [473, 167, 0, 0]]
shop_roi: List[int] = [284, 93, 958, 606]
shop_page_turning_path: List[List[int]] = [[759, 605, 0, 0], [759, 93, 0, 0]]
ocr_score_threshold: float = 0.8


class WarehouseScan(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        # 需要在 custom_action_param 中传入 custom_task_config\restaurant 文件夹的路径
        manager = DataManager(os.path.join(os.getcwd(), json.loads(argv.custom_action_param)))
        self.define_basic_tasks(context)

        context.run_task("进入餐厅仓库")
        warehouse_stock: Dict[str, int] = {}
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
                return CustomAction.RunResult(success=False)

            # 排序后打包
            for item, num in self.match_items_and_quantities(category).items():
                # 若本页有食材已经被记录过，说明本页是最后一页
                if item in recorded_items:
                    is_last_page = True
                    continue
                warehouse_stock[item] = num

            if is_last_page:
                break
            else:
                context.run_task("warehouse_page_turning")

        manager.update_warehouse_stock(warehouse_stock)
        context.run_task("点击下方空白")
        return CustomAction.RunResult(success=True)

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
                return Rect(0, 0, 0, 0)

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


class ShopScan(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        # 需要在 custom_action_param 中传入 custom_task_config/restaurant 文件夹的路径
        self.define_basic_tasks(context)
        manager = DataManager(os.path.join(os.getcwd(), json.loads(argv.custom_action_param)))

        context.run_task("进入餐厅商店")
        shop_stock: Dict[str, Dict[str, int]] = {}
        while True:
            is_last_page = False
            recorded_items = shop_stock.keys()
            screenshot = context.tasker.controller.post_screencap().wait().get()

            # 记录食材
            unprocessed_category = context.run_recognition("gain_shop_category", screenshot)
            if unprocessed_category and unprocessed_category.filterd_results:
                category: List[OCRResult] = [
                    result for result in unprocessed_category.filterd_results
                    if result.score > ocr_score_threshold
                ]
            else:
                return CustomAction.RunResult(success=False)
            # 排序后打包
            matched_items = self.match_items_limits_prices(category, context)
            for item, (limit, price) in matched_items.items():
                # 若本页有食材已经被记录过，说明本页是最后一页
                if item in recorded_items:
                    is_last_page = True
                    continue
                # 初始化字典项（如果不存在）
                if item not in shop_stock:
                    shop_stock[item] = {}
                shop_stock[item]["shop_daily_limit"] = int(limit)
                shop_stock[item]["shop_price"] = int(price)

            if is_last_page:
                break
            else:
                context.run_action("shop_page_turning")

        manager.write_shop_today(shop_stock)
        manager.update_merchandise_data(shop_stock)
        context.run_task("返回上级菜单")
        return CustomAction.RunResult(success=True)

    @staticmethod
    def match_items_limits_prices(ocr_results: List[OCRResult], context: Context) -> Dict[str, Tuple[int, int]]:
        def calculate_distance(p1: Tuple[int, int], p2: Tuple[int, int]) -> int:
            return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])

        def box_center(box: Rect) -> Tuple[int, int]:
            return box.x + box.w // 2, box.y + box.h // 2

        def get_box(result: OCRResult) -> Rect:
            if (isinstance(result.box, list) or isinstance(result.box, tuple)) and len(result.box) == 4:
                return Rect(*result.box)
            elif isinstance(result.box, Rect):
                return result.box
            else:
                return Rect(0, 0, 0, 0)

        items: List[OCRResult] = []
        prices: List[OCRResult] = []
        limits: List[OCRResult] = []
        matched: Dict[str, Tuple[int, int]] = {}

        for result in ocr_results:  # 分类存放识别结果
            try:
                re.search(r"限购\s*(?P<limit>\d+)/\d+", result.text).group("limit")
                limits.append(result)
            except AttributeError:
                try:
                    int(result.text)
                    prices.append(result)
                except ValueError:
                    items.append(result)

        for item in items:
            item_center = box_center(get_box(item))
            best_match_limit: Optional[OCRResult] = None
            min_distance_limit = float('inf')
            for limit in limits:
                limit_center = box_center(get_box(limit))
                current_distance_limit = calculate_distance(item_center, limit_center)
                if current_distance_limit < min_distance_limit and current_distance_limit < 100:
                    min_distance_limit = current_distance_limit
                    best_match_limit = limit
            try:
                limit_value = int(re.search(r"限购\s*(?P<limit>\d+)/\d+", best_match_limit.text).group("limit"))
                limits.remove(best_match_limit)
            except (AttributeError, ValueError):
                continue  # 找不到限购说明已售罄，排除出列表

            # 考虑到OCR经常识别不到单独的1，因此需要限制物品名与价格的距离，并在无结果时将其赋值为1
            best_match_price: Optional[OCRResult] = None
            min_distance_price = float('inf')
            for price in prices:
                price_center = box_center(get_box(price))
                current_distance_price = calculate_distance(item_center, price_center)
                if current_distance_price < min_distance_price and current_distance_price < 100:
                    min_distance_price = current_distance_price
                    best_match_price = price
            if best_match_price:
                price_value = int(best_match_price.text)
                prices.remove(best_match_price)
            else:
                price_value = 1

            matched[item.text] = (limit_value, price_value)

        return matched

    @staticmethod
    def define_basic_tasks(context: Context):
        # 识别物品、限购、价格
        context.override_pipeline({
            "gain_shop_category": {
                "recognition": {
                    "type": "OCR",
                    "param": {
                        "roi": shop_roi,
                        "expected": "^([\\u4e00-\\u9fa5]+|限购\\s*\\d+/\\d+|\\d+)$"
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
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        # 需要在 custom_action_param 中传入购买列表
        demands: List[str] = json.loads(argv.custom_action_param)
        self.define_basic_tasks(context)

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

        context.run_task("进入餐厅商店")
        context = context.clone()
        page_num = 1
        while True:
            purchased_items: List[str] = []
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
                context.run_task("push_message", {
                    "push_message": {
                        "focus": {
                            "start": f"[size:20][color:red]无结果[/color][/size]"
                        }
                    }
                })
                context.run_action("shop_page_turning")
                page_num += 1
                continue
            current_demands = [
                filtered_result for filtered_result in recognition_detail.filterd_results
                if (filtered_result.score > ocr_score_threshold and filtered_result.text in demands)
            ]

            for current_demand in current_demands:
                if current_demand.text in purchased_items:
                    page_num = 3  # 出现重复匹配项，已经到达尾页
                    continue

                target_roi = safe_get_roi(current_demand)
                if target_roi is None:
                    continue  # 跳过无法获取 roi 的项目

                context.run_task("push_message", {
                    "push_message": {
                        "focus": {
                            "start": f"[size:20][color:red]购买{current_demand.text}[/color][/size]"
                        }
                    }
                })
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


class RestaurantMainProcess(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        # 需要在 custom_action_param 中传入 custom_task_config/restaurant 文件夹的路径
        optimizer = RestaurantOptimizer(json.loads(argv.custom_action_param), context)
        self.define_basic_tasks(context, optimizer)

        '''1. 菜品上架流程'''
        while True:
            # 扫描商店并决策今日菜谱
            context.run_task("push_message", {
                "push_message": {
                    "focus": {
                        "start": f"[size:20][color:red]上架开始[/color][/size]"
                    }
                }
            })
            context.run_task("shop_scan")
            optimizer.shop_info_wrought = True
            decision = optimizer.run_optimization()
            plan: Optional[List[Dict[str, str | int | float]]] = decision[0]
            demands: Optional[List[str]] = decision[1]

            if not plan:
                context.run_task("push_message", {
                    "push_message": {
                        "focus": {
                            "start": f"[size:20][color:red]未得出上架计划，跳过任务[/color][/size]"
                        }
                    }
                })
                break

            if demands:  # 购买菜品
                context.run_task("push_message", {
                    "push_message": {
                        "focus": {
                            "start": f"[size:20][color:red]{demands}[/color][/size]"
                        }
                    }
                })
                context.run_task("shop_purchase", {
                    "shop_purchase": {
                        "action": {
                            "type": "Custom",
                            "param": {
                                "custom_action": "ShopPurchase",
                                "custom_action_param": demands
                            }
                        },
                        "on_error": ["返回上级菜单"]
                    }
                })

            context.run_task("进入今日菜单")
            context.run_task("下架菜品任务")
            context.run_task("push_message", {
                "push_message": {
                    "focus": {
                        "start": f"[size:20][color:red]{plan}[/color][/size]"
                    }
                }
            })
            # 上架菜品
            added_num = 0
            for cooker, dishes in optimizer.dishes.items():
                if added_num >= len(plan):
                    break
                # 进入对应厨具的界面
                context.run_task("choose_cooker", {
                    "choose_cooker": {
                        "recognition": {
                            "type": "OCR",
                            "param": {
                                "roi": [110, 143, 184, 381],
                                "expected": [cooker]
                            }
                        },
                        "action": "Click"
                    }
                })
                dishes_names: List[str] = [dish["dish_id"] for dish in dishes]
                for planned_dish in plan:
                    if planned_dish["id"] not in dishes_names:
                        continue
                    # 尝试寻找菜品并上架
                    for _ in range(3):
                        target_dish = context.run_recognition("reco_planned_dish",
                                                              context.tasker.controller.post_screencap().wait().get(),
                                                              {
                                                                  "reco_planned_dish": {
                                                                      "recognition": {
                                                                          "type": "OCR",
                                                                          "param": {
                                                                              "roi": [303, 136, 384, 511],
                                                                              "expected": [planned_dish["id"]]
                                                                          }
                                                                      },
                                                                      "timeout": 3000,
                                                                      "on_error": ["空白任务"]
                                                                  }
                                                              })
                        if target_dish is None or target_dish.best_result is None:  # 未找到对应菜品，下滑并再次寻找
                            context.run_task("menu_page_turning")
                            continue
                        else:  # 找到对应菜品：上架并跳出循环
                            context.run_task("push_message", {
                                "push_message": {
                                    "focus": {
                                        "start": f"[size:20][color:red]识别到{planned_dish["id"]}[/color][/size]"
                                    }
                                }
                            })
                            context.run_task("add_planned_dish", {
                                "add_planned_dish": {
                                    "action": {
                                        "type": "Click",
                                        "param": {
                                            "target": list(target_dish.box+Rect(190, 20, 0, 0))
                                        }
                                    },
                                    "post_wait_freeze": 1000
                                }
                            })
                            context.run_task("push_message", {
                                "push_message": {
                                    "focus": {
                                        "start": f"[size:20][color:red]点击到[/color][/size]"
                                    }
                                }
                            })
                            bar_end_x = round(681 + (865 - 681) * planned_dish["bar_ratio"] + 0.5)  # 向上取整
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
                            added_num += 1
                            break

                    else:
                        # 菜品未找到，发送信息至操作界面
                        added_num += 1
                        context.run_task("push_message", {
                            "push_message": {
                                "focus": {
                                    "start": f"[size:20][color:red]菜品”{planned_dish["id"]}“未找到[/color][/size]"
                                }
                            }
                        })

            # 上架菜品流程结束，退出菜谱界面和外层while循环并清空当日商店数据
            context.run_action("点击下方空白")
            optimizer.clean_shop_today()
            break

        '''2. 仓库扫描流程'''
        context.run_task("warehouse_scan")

        '''3. 餐厅任务完成，退出至主页'''
        context.run_task("直接返回主菜单")
        return CustomAction.RunResult(success=True)

    @staticmethod
    def define_basic_tasks(context: Context, optimizer: RestaurantOptimizer):
        # 定义餐厅自定义任务
        context.override_pipeline({
            "shop_scan": {
                "action": {
                    "type": "Custom",
                    "param": {
                        "custom_action": "ShopScan",
                        "custom_action_param": optimizer.data_path
                    }
                }
            },
            "warehouse_scan": {
                "action": {
                    "type": "Custom",
                    "param": {
                        "custom_action": "WarehouseScan",
                        "custom_action_param": optimizer.data_path
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
