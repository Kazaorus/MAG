from maa.custom_action import CustomAction
from maa.context import Context


class HighestLevelChoice(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult | bool:
        context = context.clone()
        self.define_basic_tasks(context)

        levels = context.run_recognition("level_reco", context.tasker.controller.post_screencap().wait().get())
        if levels is not None and levels.box is not None:
            context.run_task("click_target", {
                "click_target": {
                    "action": {
                        "type": "Click",
                        "param": {
                            "target": list(levels.box)
                        }
                    }
                }
            })
        else:
            context.run_task("push_message", {
                "push_message": {
                    "focus": {
                        "start": f"[size:15][color:tomato]未获取到关卡[/color][/size]"
                    }
                }
            })
            return CustomAction.RunResult(False)

        sweep_detail = context.run_recognition("可扫荡检测",
                                               context.tasker.controller.post_screencap().wait().get(),
                                               {
                                                   "可扫荡检测": {
                                                       "inverse": False,
                                                       "next": ["空白任务"]
                                                   }
                                               })
        if sweep_detail is not None and sweep_detail.best_result is not None:  # 当前关卡不可扫荡
            context.run_task("点击下方空白")
            level = context.run_recognition("level_reco",
                                            context.tasker.controller.post_screencap().wait().get(),
                                            {
                                                "level_reco": {
                                                    "recognition": {
                                                        "param": {
                                                            "index": -2
                                                        }
                                                    }
                                                }
                                            })
            if level is None or level.box is None:  # 所有关卡不可扫荡
                context.run_task("push_message", {
                    "push_message": {
                        "focus": {
                            "start": f"[size:15][color:tomato]所有关卡不可扫荡[/color][/size]"
                        }
                    }
                })
                return CustomAction.RunResult(False)

            context.run_task("click_target", {
                "click_target": {
                    "action": {
                        "type": "Click",
                        "param": {
                            "target": list(levels.box)
                        }
                    }
                }
            })

        return CustomAction.RunResult(True)

    @staticmethod
    def define_basic_tasks(context: Context):
        context.override_pipeline({
            "cannot_sweep": {
                "timeout": 3000,
                "recognition": {
                    "type": "ColorMatch",
                    "param": {
                        "roi": [905, 645, 179, 53],
                        "lower": [120, 120, 120],
                        "upper": [127, 127, 127],
                        "count": 10
                    }
                },
                "on_error": ["空白任务"]
            },
            "level_reco": {
                "recognition": {
                    "type": "OCR",
                    "param": {
                        "roi": [10, 160, 1257, 479],
                        "index": -1,
                        "expected": ".*\\-\\d"
                    }
                }
            }
        })
