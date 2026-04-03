from maa.context import Context
from maa.custom_action import CustomAction
from datetime import datetime, time, timedelta
from typing import Dict, Any, List, Optional
import json
import os


CLAIMING_AREA:  List[int] = [1098, 569, 129, 106]
CLAIMING_POINT:  List[int] = [1168, 645]
RELATIVE_CONFIG_DIR = ("custom_task_config", "exploration_cumulative_rewards", "claimable_time.json")


class TimeDecider:
    def __init__(self, task_param: Dict[str, Any]):
        self._now = datetime.now()
        self._absolute_config_path = os.path.join(
                os.getcwd(),
                *RELATIVE_CONFIG_DIR
            )

        self._designated_datetime = self._get_designated_datetime(task_param)
        self._valid_datetime = self._get_valid_datetime()

    def _get_designated_datetime(self, task_param: Dict[str, Any]):
        claimable_time: time = time.fromisoformat(task_param["claimable_time"])
        days_ahead: int = task_param["claimable_date"] - self._now.weekday()

        return (self._now + timedelta(days=days_ahead)).replace(
            hour=claimable_time.hour,
            minute=claimable_time.minute,
            second=claimable_time.second,
            microsecond=0
        )

    def _get_valid_datetime(self) -> datetime:
        with open(self._absolute_config_path, "r", encoding="UTF-8") as f:
            return datetime.fromisoformat(
                json.load(f)["next_valid_datetime"]
            )

    def update_valid_time(self):
        """获取新的有效时间：下一个周六的5点"""
        # 当前为周末时：日期差 = 5(周六) + 7(往后一周) - 当前的weekday
        # 否则：日期差 = 5(周六) - 当前的weekday
        days_param = 12 if self._now.weekday() > 4 else 5
        updated = self._now.replace(hour=5, minute=0, second=0, microsecond=0) \
                             + timedelta(days = days_param - self._now.weekday())

        with open(self._absolute_config_path, "w", encoding="UTF-8") as f:
            json.dump(
                {"next_valid_datetime": updated.isoformat()},
                fp=f,
                indent=4
            )

    def decide(self) -> bool:
        """判定当前时间是否为可领取时间"""
        if self._valid_datetime <= self._designated_datetime <= self._now:
            return True
        return False


class BountyClaim(CustomAction):
    def __init__(self):
        super().__init__()
        self._context: Optional[Context] = None
        self._time_decider: Optional[TimeDecider] = None

    def run(
            self,
            context: Context,
            argv: CustomAction.RunArg
    ) -> CustomAction.RunResult | bool:
        self._context = context
        self._define_tasks()
        param = json.loads(argv.custom_action_param)
        self._time_decider = TimeDecider(param)

        # 只要奖励累计满，无论设置如何都领取
        if self._is_reward_cumulated():
            self._get_reward()
            return CustomAction.RunResult(True)

        # 奖励未满且设置为仅累积奖励满后领取：直接返回主页并结束任务
        if not param["fixed_reward_collection"]:
            self._return_to_homepage()
            return CustomAction.RunResult(True)

        # 定时领取且奖励未满：继续判定时间条件
        if self._time_decider.decide():
            self._get_reward()
            return CustomAction.RunResult(True)

        # 默认退出
        self._return_to_homepage()
        return CustomAction.RunResult(True)

    def _get_reward(self):
        self._context.run_task("enter_reward_interface")
        self._context.run_task("演算可用判定")
        self._time_decider.update_valid_time()

    def _return_to_homepage(self):
        self._context.run_task("直接返回主菜单")

    def _is_reward_cumulated(self) -> bool:
        detail = self._context.run_recognition(
            "cumulative_reward",
            self._context.tasker.controller.post_screencap().wait().get()
        )
        if detail.hit:
            return True
        return False

    def _define_tasks(self):
        self._context.override_pipeline({
            "cumulative_reward": {
                "recognition": {
                    "type": "OCR",
                    "param": {
                        "roi": CLAIMING_AREA
                    }
                }
            },
            "enter_reward_interface": {
                "action": {
                    "type": "Click",
                    "param": {
                        "target": CLAIMING_POINT
                    }
                }
            }
        })