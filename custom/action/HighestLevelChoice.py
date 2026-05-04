from maa.custom_action import CustomAction
from maa.context import Context
from maa.define import OCRResult, RecognitionDetail, Rect
from typing import List, Tuple
import numpy as np


class HighestLevelChoice(CustomAction):
    def __init__(self):
        super().__init__()
        self.context = None

    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult | bool:
        self.context = context

        # 划到最右侧界面
        levels = self._get_levels()
        while True:
            self.context.run_action("寻找资源关卡")  # 借用该节点向右滑动（无识别及后续）
            is_last, levels = self._is_last_page(levels, True)
            if is_last:
                break

        # 判断最高级关卡能否扫荡
        self._click(levels[0].box)
        if self._can_mopping():
            return CustomAction.RunResult(True)

        # 不可扫荡：记录当前关卡名，随后逐级向下尝试
        current_level = levels[0].text
        while True:
            levels = self._get_levels()
            if not levels:
                return CustomAction.RunResult(False)

            levels_can_mopping = self._get_low_levels(levels, current_level)
            if not levels_can_mopping:  # 无可扫荡关卡
                return CustomAction.RunResult(False)

            self._click(levels_can_mopping[0].box)
            if self._can_mopping():  # 找到可扫荡关卡，返回
                return CustomAction.RunResult(True)

            current_level = levels_can_mopping[0].text

    # 获取当前页面的所有关卡
    def _get_levels(self) -> List[OCRResult]:
        levels_detail: RecognitionDetail = self.context.run_recognition("level_reco", self._screencap)
        if not levels_detail.hit:
            return []

        return levels_detail.filtered_results[::-1]  # 将最高级关卡放最前面

    def _is_last_page(self, previous_levels: List[OCRResult], judge_right_side: bool) -> Tuple[bool, List[OCRResult]]:
        current_levels = self._get_levels()
        if not current_levels or not previous_levels:
            return False, []
        if judge_right_side:
            # 右侧页面，判断两次检测到的最高级关卡是否相等
            return current_levels[0].text == previous_levels[0].text, current_levels
        else:
            # 左侧页面，判断两次检测到的最低级关卡是否相等
            return current_levels[-1].text == previous_levels[-1].text, current_levels

    def _can_mopping(self) -> bool:
        mopping_detail: RecognitionDetail = self.context.run_recognition("可扫荡检测", self._screencap,
                                                       {"可扫荡检测": {
                                                           "inverse": False,
                                                           "next": ["空白任务"],
                                                           "on_error": ["空白任务"]
                                                       }})
        # 不可扫荡
        if mopping_detail.hit:
            self.context.run_task("点击下方空白")
            return False
        return True

    # 获取低于指定关卡等级的所有关卡（要求输入从高到低排序）
    @staticmethod
    def _get_low_levels(levels: List[OCRResult], current_level_name: str) -> List[OCRResult]:
        level_names: List[str] = [level.text for level in levels]
        try:
            current_level_idx = level_names.index(current_level_name)
            return levels[current_level_idx+1:]
        except ValueError:
            return levels

    def _click(self, box: Rect):
        self.context.run_task("click_target", {
                "click_target": {
                    "action": {
                        "type": "Click",
                        "param": {"target": list(box)}
                    }
                }
            })

    @property
    def _screencap(self) -> np.ndarray:
        return self.context.tasker.controller.post_screencap().wait().get()
