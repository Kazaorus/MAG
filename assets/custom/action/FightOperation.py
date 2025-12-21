from maa.custom_action import CustomAction
from maa.context import Context
import json


class FightOperation(CustomAction):
    """
    需要在 MMaaCustomActionCallback.custom_recognition_param 中传入战斗次数："消耗全部体力"或任意大于0小于等于10的的数字
    """
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult | bool:
        fight_param: str = json.loads(argv.custom_action_param)
        context.run_task("调至最小扫荡次数", {
            "调至最小扫荡次数": {
                "timeout": 2000,
                "on_error": ["空白任务"],
                "next": []
            }
        })
        if fight_param == "消耗全部体力":
            # 直接运行直至自然结束
            context.run_task("调至最大扫荡次数")
            return CustomAction.RunResult(True)

        try:
            num_fight = int(fight_param)
            if num_fight < 1 or num_fight > 10:
                context.run_task("push_message", {
                    "push_message": {
                        "focus": {
                            "start": f"[size:15][color:tomato]扫荡次数非法，即将返回主菜单[/color][/size]"
                        }
                    }
                })
                return CustomAction.RunResult(False)

            context.override_pipeline({
                "已达到目标扫荡次数": {
                    "recognition": {
                        "param": {
                            "expected": [f"^.?{num_fight}$"]
                        }
                    }
                },
                "扫荡完成": {
                    "next": ["直接返回主菜单"]
                }
            })
            while True:
                screenshot = context.tasker.controller.post_screencap().wait().get()
                largest_reco_detail = context.run_recognition("已达到最大扫荡次数", screenshot)
                aim_num_reco_detail = context.run_recognition("已达到目标扫荡次数", screenshot)
                if largest_reco_detail and largest_reco_detail.best_result is None:
                    break
                if aim_num_reco_detail and aim_num_reco_detail.best_result:
                    break

                context.run_task("调至指定扫荡次数")

            context.run_task("开始扫荡")
            return CustomAction.RunResult(True)
        except ValueError:
            context.run_task("push_message", {
                "push_message": {
                    "focus": {
                        "start": f"[size:15][color:tomato]扫荡次数非法，即将返回主菜单[/color][/size]"
                    }
                }
            })
            return CustomAction.RunResult(False)
    