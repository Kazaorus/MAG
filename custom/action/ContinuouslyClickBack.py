from maa.context import Context
from maa.custom_action import CustomAction
import time


class ContinuouslyClickBack(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        roi_center = [int(argv.box.x+argv.box.w/2), int(argv.box.y+argv.box.h/2)]
        while True:
            context.tasker.controller.post_click(*roi_center).wait()
            time.sleep(1)
            image = context.tasker.controller.post_screencap().wait().get()
            back = context.run_recognition("连续返回主菜单", image)
            if back is None or back.best_result is None:
                break

        return CustomAction.RunResult(True)

