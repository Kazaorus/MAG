from typing import Optional, Tuple, Dict
from datetime import datetime, time, timedelta
from maa.context import Context
from maa.custom_recognition import CustomRecognition
from maa.define import RectType
import json
import os


claiming_area:  Tuple[int, int, int, int] = 1098, 569, 129, 106


class ExplorationCumulativeRewardsDetermination(CustomRecognition):
    def analyze(
            self,
            context: Context,
            argv: CustomRecognition.AnalyzeArg
    ) -> CustomRecognition.AnalyzeResult | Optional[RectType]:
        # 加载初始参数
        param = json.loads(argv.custom_recognition_param)
        is_fixed_time: bool = param["fixed_reward_collection"]

        if not is_fixed_time: # 若设置为仅累积奖励满后领取
            if self.is_reward_full(context): # 奖励已满，返回领取区域
                return claiming_area
            else: # 否则视为未识别到
                return None

        # 加载剩余参数
        absolute_config_path: str = os.path.join(os.getcwd(), "custom_task_config\\exploration_cumulative_rewards")
        valid_time: datetime = self.get_valid_datetime(absolute_config_path)
        designated_time: datetime = self.get_designated_datetime(param)
        now: datetime = datetime.now()

        if valid_time <= designated_time <= now:
            # 本周还未领取过(指定时刻晚于或等于有效时刻) 且 当前时刻晚于或等于指定时刻
            self.update_valid_datetime(absolute_config_path)
            return claiming_area
        return None


    @staticmethod
    def get_valid_datetime(directory_path: str) -> datetime:
        with open(os.path.join(directory_path, "claimable_time.json"), "r") as f:
            return datetime.fromisoformat(json.load(f)["next_valid_datetime"])

    @staticmethod
    def update_valid_datetime(directory_path: str):
        # 获取新的有效时间：下周六的5点
        # 日期差 = 5(周六) + 7(往后一周) - 当前的weekday
        now = datetime.now()
        updated_valid_time = now.replace(hour=5, minute=0, second=0, microsecond=0) + timedelta(days=12-now.weekday())
        with open(os.path.join(directory_path, "claimable_time.json"), "w") as f:
            json.dump({"next_valid_datetime": updated_valid_time.isoformat()}, f)

    @staticmethod
    def get_designated_datetime(task_param: Dict) -> datetime:
        now = datetime.now()
        claimable_time: time = time.fromisoformat(task_param["claimable_time"])
        days_ahead: int = task_param["claimable_date"] - now.weekday()

        return (now + timedelta(days=days_ahead)).replace(
            hour=claimable_time.hour,
            minute=claimable_time.minute,
            second=claimable_time.second,
            microsecond=0
        )

    @staticmethod
    def is_reward_full(context: Context) -> bool:
        reward_detail = context.run_task("cumulative_reward", {
            "cumulative_reward": {
                "recognition": {
                    "type": "OCR",
                    "param": {
                        "roi": list(claiming_area),
                        "expected": ["10"]
                    }
                },
                "timeout": 5000,
                "on_error": ["空白任务"]
            }
        })
        if reward_detail is not None and reward_detail.status.succeeded:
            return True
        return False
