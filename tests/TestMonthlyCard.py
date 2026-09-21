import unittest

from src.task.BaseWWTask import BaseWWTask, MAIL_UI_MARKERS


class TextBox:
    def __init__(self, name):
        self.name = name


class FakeMonthlyTask:
    """Drives BaseWWTask.handle_monthly_card with scripted state.

    monthly_card_hit: find_monthly_card() result (None or truthy)
    ocr_frames: lists of TextBox returned by successive ocr() calls
    world_sequence: in_team_and_world() results popped per call
    """

    def __init__(self, monthly_card_hit=None, ocr_frames=None, world_sequence=None):
        self.monthly_card_hit = monthly_card_hit
        self.ocr_frames = list(ocr_frames or [])
        self.world_sequence = list(world_sequence or [])
        self.relative_clicks = []
        self.slept = []
        self.set_check_calls = []
        self.post_actions = 0

    def find_monthly_card(self):
        return self.monthly_card_hit

    def is_mail_ui_open(self):
        return BaseWWTask.is_mail_ui_open(self)

    def ocr(self):
        return self.ocr_frames.pop(0) if self.ocr_frames else []

    def find_boxes(self, texts, boundary=None, match=None):
        if not texts or not match:
            return None
        hits = [box for box in texts if any(pattern.search(box.name) for pattern in match)]
        return hits or None

    def click_relative(self, x, y, after_sleep=0):
        self.relative_clicks.append((x, y, after_sleep))

    def sleep(self, timeout):
        self.slept.append(timeout)

    def in_team_and_world(self):
        return self.world_sequence.pop(0) if self.world_sequence else False

    def wait_until(self, condition, time_out=0, post_action=None, settle_time=-1,
                   raise_if_not_found=False):
        result = condition()
        if result:
            return result
        if post_action is not None:
            post_action()
            self.post_actions += 1
        return None

    def set_check_monthly_card(self, next_day=False):
        self.set_check_calls.append(next_day)

    def log_info(self, *args, **kwargs):
        pass

    def log_error(self, *args, **kwargs):
        pass

    def log_debug(self, *args, **kwargs):
        pass


class FakeIsMainTask:
    """Minimal harness for BaseWWTask.is_main flow-control tests."""

    def __init__(self, handle_result=False, wait_login_result=None):
        self.logged_in = True
        self.handle_result = handle_result
        self.wait_login_result = wait_login_result
        self.back_calls = []

    def in_team_and_world(self):
        return False

    def wait_login(self):
        return self.wait_login_result

    def handle_monthly_card(self):
        return self.handle_result

    def back(self, after_sleep=0):
        self.back_calls.append(after_sleep)

    def log_debug(self, *args, **kwargs):
        pass


class TestHandleMonthlyCard(unittest.TestCase):

    def test_no_template_match_returns_false(self):
        task = FakeMonthlyTask(monthly_card_hit=None)

        result = BaseWWTask.handle_monthly_card(task)

        self.assertFalse(result)
        self.assertEqual(task.relative_clicks, [])
        self.assertEqual(task.set_check_calls, [])

    def test_mailbox_false_positive_is_skipped(self):
        # 真机故障场景：monthly_card 模板在信箱页误命中，但信箱文案可见，
        # 不得点击、不得推进检查窗口，让 is_main 继续走 ESC 关闭信箱
        task = FakeMonthlyTask(
            monthly_card_hit=object(),
            ocr_frames=[[TextBox('全部邮件 12/200'), TextBox('全部领取'), TextBox('删除已读')]],
        )

        result = BaseWWTask.handle_monthly_card(task)

        self.assertFalse(result)
        self.assertEqual(task.relative_clicks, [])
        self.assertEqual(task.set_check_calls, [])

    def test_mailbox_marker_english_and_traditional(self):
        for marker_text in ('Claim All', 'Delete Read', 'All Mail', '全部領取', '刪除已讀', '全部郵件'):
            task = FakeMonthlyTask(
                monthly_card_hit=object(),
                ocr_frames=[[TextBox(marker_text)]],
            )

            result = BaseWWTask.handle_monthly_card(task)

            self.assertFalse(result, f'marker {marker_text} should be recognized as mailbox UI')
            self.assertEqual(task.relative_clicks, [])

    def test_genuine_popup_is_clicked_and_scheduled(self):
        # 真月卡弹窗：OCR 无信箱文案，点击后回到大世界，推进次日检查窗口
        task = FakeMonthlyTask(
            monthly_card_hit=object(),
            ocr_frames=[[TextBox('月相观测卡')]],
            world_sequence=[True],
        )

        result = BaseWWTask.handle_monthly_card(task)

        self.assertTrue(result)
        self.assertEqual(task.relative_clicks.count((0.5, 0.89, 0)), 2)
        self.assertEqual(task.slept, [2, 2])
        self.assertEqual(task.set_check_calls, [True])

    def test_failed_click_keeps_check_time(self):
        # 点击后仍未回到大世界：不推进检查窗口，避免真正弹窗被漏判到第二天
        task = FakeMonthlyTask(
            monthly_card_hit=object(),
            ocr_frames=[[TextBox('月相观测卡')]],
            world_sequence=[False],
        )

        result = BaseWWTask.handle_monthly_card(task)

        self.assertTrue(result)
        self.assertEqual(task.set_check_calls, [])
        self.assertEqual(task.post_actions, 1)


class TestIsMainMailboxEscape(unittest.TestCase):

    def test_mailbox_false_positive_path_still_sends_esc(self):
        # handle_monthly_card 被信箱守卫挡回 False 后，is_main 必须发送 ESC，
        # 这是修复前信箱永远关不掉的死结
        task = FakeIsMainTask(handle_result=False)

        result = BaseWWTask.is_main(task, esc=True)

        self.assertFalse(result)
        self.assertEqual(task.back_calls, [2])

    def test_genuine_monthly_card_handling_skips_esc(self):
        # 真正处理月卡时不需要 ESC（点击即关闭弹窗），保持原有控制流
        task = FakeIsMainTask(handle_result=True)

        result = BaseWWTask.is_main(task, esc=True)

        self.assertFalse(result)
        self.assertEqual(task.back_calls, [])


if __name__ == "__main__":
    unittest.main()
