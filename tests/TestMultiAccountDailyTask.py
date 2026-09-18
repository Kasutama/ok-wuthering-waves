import unittest

from src.task.BaseWWTask import LOGIN_TEXTS
from src.task.MultiAccountDailyTask import (
    MultiAccountDailyTask,
    ENTER_GAME_TEXTS,
    account_pattern,
    normalize_account_name,
)


class TestMultiAccountDailyTask(unittest.TestCase):

    def test_account_dropdown_accepts_multiple_login_text_matches(self):
        account_box = object()

        class FakeTask:
            def ocr(self):
                return []

            def find_boxes(self, texts, match):
                if match == account_pattern:
                    return [account_box]
                if match == LOGIN_TEXTS:
                    return [object(), object()]
                return []

        self.assertIs(MultiAccountDailyTask.do_find_account_drop_down(FakeTask()), account_box)

    def test_account_name_normalization_groups_common_ocr_variants(self):
        self.assertEqual(
            normalize_account_name("cc****33@demo.com.hk"),
            normalize_account_name("cc****33@dem0.com.hk"),
        )
        self.assertEqual(
            normalize_account_name("bb****02@example.com"),
            normalize_account_name("bb****02@example.con"),
        )

    def test_click_account_list_selects_visible_third_account_after_first_two_are_done(self):
        class AccountBox:
            def __init__(self, name):
                self.name = name

        class FakeTask:
            def __init__(self):
                self.done_set = {
                    normalize_account_name("aa****01@example.com"),
                    normalize_account_name("bb****02@example.com"),
                }
                self.all_accounts = set()
                self.clicked = []

            _is_done = MultiAccountDailyTask._is_done

            def ocr(self, match=None):
                return [
                    AccountBox("aa****01@example.com"),
                    AccountBox("aa****01@example.com"),
                    AccountBox("bb****02@example.com"),
                    AccountBox("cc****03@example.com.hk"),
                ]

            def info_set(self, *args):
                pass

            # multifix13: account list clicks go through the physical channel
            # (CEF launcher popup ignores PostMessage synthetic clicks)
            def physical_click_box(self, account, after_sleep=0):
                self.clicked.append(account.name)

            def log_info(self, *args):
                pass

            def tr(self, message):
                return message

        task = FakeTask()

        selected = MultiAccountDailyTask._click_account_in_list(task)

        self.assertEqual(selected, "cc****03@example.com.hk")
        self.assertEqual(task.clicked, ["cc****03@example.com.hk"])


class FakeLoginClickTask:
    """Drives _click_login_until_entered with scripted OCR frames."""

    def __init__(self, frames, in_world_frames=None):
        self.frames = list(frames)
        self.in_world_frames = list(in_world_frames or [])
        self.logged_in = False
        self.box_clicks = []
        self.relative_clicks = []
        self.front_ensured = 0

    def in_team_and_world(self):
        return self.in_world_frames.pop(0) if self.in_world_frames else False

    def ensure_in_front(self):
        self.front_ensured += 1

    def box_of_screen(self, *args, **kwargs):
        return args

    def ocr(self):
        return self.frames.pop(0) if self.frames else []

    def find_boxes(self, texts, boundary=None, match=None):
        if match is None:
            match = boundary
        if match == LOGIN_TEXTS:
            hits = [b for b in texts if getattr(b, 'kind', '') == 'login']
            return hits or None
        if match == ENTER_GAME_TEXTS:
            hits = [b for b in texts if getattr(b, 'kind', '') == 'enter']
            return hits or None
        if match == account_pattern:
            return [b for b in texts if getattr(b, 'kind', '') == 'account']
        return None

    def physical_click_box(self, box, after_sleep=0):
        if isinstance(box, list):
            box = box[0]
        self.box_clicks.append(box.name)

    def physical_click_relative(self, rel_x, rel_y, hcenter=False, vcenter=False, after_sleep=0):
        self.relative_clicks.append((rel_x, rel_y))

    def sleep(self, *args):
        pass

    def log_info(self, *args, **kwargs):
        pass


class OCRBox:
    def __init__(self, name, kind, x=0, y=0, width=10, height=10):
        self.name = name
        self.kind = kind
        self.x, self.y, self.width, self.height = x, y, width, height


class TestClickLoginUntilEntered(unittest.TestCase):

    def test_ocr_login_button_goes_through_physical_channel(self):
        task = FakeLoginClickTask(
            frames=[[OCRBox('登录', 'login')], []],
            # not in world for round 1, already in world at round 2
            in_world_frames=[False, True],
        )

        ok = MultiAccountDailyTask._click_login_until_entered(task, max_rounds=2)

        self.assertTrue(ok)
        self.assertTrue(task.logged_in)
        self.assertEqual(task.box_clicks, ['登录'])
        self.assertEqual(task.relative_clicks, [])
        # foreground ensured on the clicking round; round 2 returns before it
        self.assertEqual(task.front_ensured, 1)

    def test_enter_game_button_variant_is_clicked(self):
        task = FakeLoginClickTask(
            frames=[[OCRBox('开始游戏', 'enter')]],
            in_world_frames=[False, False],
        )

        MultiAccountDailyTask._click_login_until_entered(task, max_rounds=1)

        self.assertEqual(task.box_clicks, ['开始游戏'])

    def test_missing_button_with_account_text_uses_center_fallback(self):
        task = FakeLoginClickTask(
            frames=[[OCRBox('aa****01@x.com', 'account')]],
            in_world_frames=[False, False],
        )

        MultiAccountDailyTask._click_login_until_entered(task, max_rounds=1)

        self.assertEqual(task.box_clicks, [])
        self.assertEqual(task.relative_clicks, [(0.5, 0.568)])

    def test_no_button_and_no_account_evidence_clicks_nothing(self):
        task = FakeLoginClickTask(
            frames=[[]],
            in_world_frames=[False, False],
        )

        MultiAccountDailyTask._click_login_until_entered(task, max_rounds=1)

        self.assertEqual(task.box_clicks, [])
        self.assertEqual(task.relative_clicks, [])
        # still brought to front even when nothing is clicked
        self.assertEqual(task.front_ensured, 1)


if __name__ == "__main__":
    unittest.main()
