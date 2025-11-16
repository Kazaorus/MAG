from typing import Dict
from maa.custom_action import CustomAction
from typing import Set, Optional
from maa.context import Context
import os
import json


class MarkSuitChoice(CustomAction):
    """
    需要在MaaCustomActionCallback.custom_action_param中传入一个字典，类似：
    {
        "aim": "得胜者的凯歌"
    }
    """

    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        # 准备基本参数
        param: Dict = json.loads(argv.custom_action_param)
        aim: str = param["aim"]
        mark_path: str = os.path.join(os.getcwd(), "resource\\base\\image\\刻印图标")
        self._define_basic_tasks(context)
        mark_names: Set[str] = self._load_mark_names(mark_path)

        if aim not in mark_names:
            return CustomAction.RunResult(success=False)
        context.run_task("choice_mark")

        # 滑动至最上层
        recorded_mark: Optional[str] = None
        while True:
            context.run_task("slide_to_top")
            context.run_task("click_first_mark")
            screenshot = context.tasker.controller.post_screencap().wait().get()
            current_mark = context.run_recognition("recognize_mark_name", screenshot)
            if current_mark is not None and current_mark.best_result is not None:
                if current_mark.best_result.text == recorded_mark:
                    break  # 滑动后左上刻印与滑动前相同，表明已滑动至顶端
                else:
                    recorded_mark = current_mark.best_result.text

        # 逐次向下滑动并对每一页进行匹配
        recorded_mark: Optional[str] = None
        is_last_page = False
        while True:
            context.run_task("click_first_mark")
            screenshot = context.tasker.controller.post_screencap().wait().get()
            chose_mark = context.run_recognition("recognize_mark_name", screenshot)

            if chose_mark is not None and chose_mark.best_result is not None:
                if self._compare_mark_name(chose_mark.best_result.text, aim):  # 已选中
                    context.run_task("ensure_mark")
                    context.run_task("点击下方空白")
                    break
                if chose_mark.best_result.text == recorded_mark:
                    is_last_page = True  # 已划到尾页
                else:
                    recorded_mark = chose_mark.best_result.text

            marched_mark = context.run_recognition("recognize_mark_template", screenshot, {
                "recognize_mark_template": {
                    "recognition": {
                        "type": "TemplateMatch",
                        "param": {
                            "roi": [204, 214, 495, 279],
                            "template": f"刻印图标/{aim}.png"
                        }
                    }
                }
            })
            if marched_mark is not None and marched_mark.best_result is not None:  # 模板匹配成功
                context.run_task("click_first_mark", {
                    "click_first_mark": {
                        "action": {
                            "type": "Click",
                            "param": {
                                "target": marched_mark.box.roi
                            }
                        }
                    }
                })
                context.run_task("ensure_mark")
                context.run_task("点击下方空白")
                break

            # 匹配未成功
            if is_last_page:
                context.run_task("push_message", {
                    "push_message": {
                        "focus": {
                            "start": f"[size:15][color:tomato]刻印匹配失败，即将退出[/color][/size]"
                        }
                    }
                })
                context.run_task("ensure_mark")
                context.run_task("点击下方空白")
                context.override_next("选择刻印", ["直接返回主菜单"])
                break
            else:
                context.run_task("slide_to_bottom")

        return CustomAction.RunResult(success=True)

    @staticmethod
    def _define_basic_tasks(context: Context):
        context.override_pipeline({
            "slide_to_top": {
                "action": {
                    "type": "Swipe",
                    "param": {
                        "begin": [453, 226, 0, 0],
                        "end": [453, 514, 0, 0],
                        "duration": 2000,
                        "end_hold": 1000
                    }
                }
            },
            "slide_to_bottom": {
                "action": {
                    "type": "Swipe",
                    "param": {
                        "begin": [453, 461, 0, 0],
                        "end": [453, 165, 0, 0],
                        "duration": 2000,
                        "end_hold": 1000
                    }
                }
            },
            "click_first_mark": {
                "action": {
                    "type": "Click",
                    "param": {
                        "target": [272, 268, 1, 1]
                    }
                }
            },
            "recognize_mark_name": {
                "recognition": {
                    "type": "OCR",
                    "param": {
                        "roi": [712, 202, 164, 37],
                        "expected": "[\\u4e00-\\u9fa5]+"
                    }
                }
            },
            "recognize_mark_template": {
                "recognition": {
                    "type": "TemplateMatch",
                    "param": {
                        "roi": [204, 214, 495, 279],
                        "template": "刻印图标/得胜者的凯歌.png"
                    }
                }
            },
            "ensure_mark": {
                "timeout": 3000,
                "on_error": ["空白任务"],
                "recognition": {
                    "type": "OCR",
                    "param": {
                        "roi": [785, 482, 219, 59],
                        "expected": ["确定", "当前", "选择"]
                    }
                },
                "action": "Click",
                "post_wait_freeze": 1000
            },
            "choice_mark": {
                "recognition": {
                    "type": "TemplateMatch",
                    "param": {
                        "roi": [185, 537, 120, 180],
                        "template": "战斗任务/选择刻印.png",
                        "threshold": 0.6
                    }
                },
                "action": "Click"
            }
        })

    @staticmethod
    def _compare_mark_name(primal: Optional[str], comparison: str) -> bool:
        if primal is None:
            return False

        seperator = None
        if "的" in comparison:
            seperator = "的"
        elif "之" in comparison:
            seperator = "之"

        if seperator:  # 装备名里有“之”或“的”，拆分后分别匹配，有一部分成功即视为匹配成功
            try:
                primal_left, primal_right = primal.split(seperator, 1)
                comparison_left, comparison_right = comparison.split(seperator, 1)
            except ValueError:
                return False
            if primal_left and primal_right:
                if primal_left == comparison_left or primal_right == comparison_right:
                    return True
        else:  # 不含“之”或“的”，有连续两个字匹配则视为成功
            if len(primal) >= 2:
                for idx in range(len(primal) - 1):
                    if primal[idx:idx + 1] in comparison:
                        return True
        return False

    @staticmethod
    def _load_mark_names(path: str) -> Set[str]:
        """获取刻印名"""
        names = set()
        for name in os.listdir(path):
            if os.path.isfile(os.path.join(path, name)):
                pure_name = os.path.splitext(name)[0]
                names.add(pure_name)
        return names
