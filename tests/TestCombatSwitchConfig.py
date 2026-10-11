import time
import unittest
from config import config
from ok.test.TaskTestCase import TaskTestCase
from src.char.BaseChar import BaseChar, CharType
from src.task.AutoCombatTask import AutoCombatTask

config['debug'] = True


class FreezeTask:
    """最小 fake task, 满足 BaseChar 构造与选人计时需求 (与 TestChar 相同模式)。"""

    def time_elapsed_accounting_for_freeze(self, start, intro_motion_freeze=False):
        if start < 0:
            return 10000
        return time.time() - start


class SwitchTask(FreezeTask):
    """switch_other_char 所需的 fake task。"""

    def __init__(self, chars, current_index, blocked=(), dead=()):
        self.chars = chars
        self.current_index = current_index
        self.blocked = set(blocked)
        self.dead = set(dead)
        self.sent_keys = []
        self.sleeps = []

    def can_switch_to_index(self, index):
        if index is None:
            return False
        if index in self.dead:
            return False
        return index not in self.blocked

    def can_switch_to(self, char):
        if char is None:
            return False
        return self.can_switch_to_index(char.index)

    def in_team(self):
        if self.sent_keys:
            return True, int(self.sent_keys[-1]) - 1, len(self.chars)
        return True, self.current_index, len(self.chars)

    def send_key(self, key, **kwargs):
        self.sent_keys.append(key)

    def sleep(self, timeout, check_combat=True):
        self.sleeps.append(timeout)


class ReviveDialogHarness:
    """handle_revive_dialog 的探测/点击 mock。"""

    def __init__(self, medicine=True, dialog_visible=True, confirm_box='confirm_box',
                 confirm_missing_template=False, dialog_closes=True):
        self.medicine = medicine
        self.dialog_visible = dialog_visible
        self.confirm_box = confirm_box
        self.confirm_missing_template = confirm_missing_template
        self.dialog_closes = dialog_closes
        self.clicked = []
        self.closed_popup = []
        self.info = []

    # --- BaseCombatTask.handle_revive_dialog 依赖的实例属性 ---

    def wait_feature(self, feature, threshold=0, time_out=3, **kwargs):
        return self.dialog_visible

    def find_one(self, feature, threshold=0, **kwargs):
        if self.confirm_missing_template:
            raise ValueError(f'feature {feature} not found in config')
        return self.confirm_box

    def find_feature(self, feature, threshold=0, **kwargs):
        return None if self.dialog_closes else self.confirm_box

    def click(self, box, after_sleep=0, **kwargs):
        self.clicked.append(box)

    def wait_until(self, condition, time_out=10, raise_if_not_found=True, **kwargs):
        return self.dialog_closes

    def close_revive_popup(self):
        self.closed_popup.append(True)

    def info_set(self, key, value):
        self.info.append((key, value))


def make_combat(config_dict):
    combat = AutoCombatTask.__new__(AutoCombatTask)
    combat.config = config_dict
    combat.reset_combat_exclusions()
    return combat


class TestCombatSwitchConfig(TaskTestCase):
    task_class = AutoCombatTask
    config = config

    # --- blocked_switch_indices / can_switch_to_index ---

    def test_blocked_switch_indices_default_empty(self):
        combat = make_combat({})
        self.assertEqual(combat.blocked_switch_indices(), set())

    def test_blocked_switch_indices_slots_map_to_index(self):
        combat = make_combat({'Block Switch Slot 1': True})
        self.assertEqual(combat.blocked_switch_indices(), {0})

        combat.config = {'Block Switch Slot 2': True, 'Block Switch Slot 3': True}
        self.assertEqual(combat.blocked_switch_indices(), {1, 2})

    def test_blocked_switch_indices_all_three_downgrades_and_warns_once(self):
        combat = make_combat({
            'Block Switch Slot 1': True,
            'Block Switch Slot 2': True,
            'Block Switch Slot 3': True,
        })
        self.assertEqual(combat.blocked_switch_indices(), set())
        self.assertTrue(combat._blocked_slots_warned)
        # 再次调用仍为空集, 且不重复告警
        self.assertEqual(combat.blocked_switch_indices(), set())
        self.assertTrue(combat._blocked_slots_warned)

    def test_can_switch_to_index_blocks_dead_and_blocked(self):
        combat = make_combat({'Block Switch Slot 1': True})
        self.assertFalse(combat.can_switch_to_index(None))
        self.assertFalse(combat.can_switch_to_index(0))
        self.assertTrue(combat.can_switch_to_index(1))
        self.assertTrue(combat.can_switch_to_index(2))

        combat.combat_dead_indices.add(1)
        self.assertFalse(combat.can_switch_to_index(1))

    def test_reset_combat_exclusions_clears_state(self):
        combat = make_combat({})
        combat.combat_dead_indices.add(2)
        combat._blocked_slots_warned = True
        combat.reset_combat_exclusions()
        self.assertEqual(combat.combat_dead_indices, set())
        self.assertFalse(combat._blocked_slots_warned)

    # --- _choose_switch_target 集成屏蔽/死亡过滤 ---

    def test_choose_switch_target_respects_block_config(self):
        task = FreezeTask()
        combat = make_combat({})
        current = BaseChar(task, 0, char_type=CharType.MAIN_DPS)
        healer = BaseChar(task, 1, char_type=CharType.HEALER)
        sub_dps = BaseChar(task, 2, char_type=CharType.SUB_DPS)
        combat.chars = [current, healer, sub_dps]

        # 回归: 默认不屏蔽时保持原有选人优先级 (治疗位优先)
        self.assertEqual(combat._choose_switch_target(current, False), healer)

        # 屏蔽二号位 -> 不再切治疗位, 顺延到三号位
        combat.config = {'Block Switch Slot 2': True}
        self.assertEqual(combat._choose_switch_target(current, False), sub_dps)

        # 屏蔽二号位 + 三号位 -> 无可用候选, 返回 current 原地继续输出
        combat.config = {'Block Switch Slot 2': True, 'Block Switch Slot 3': True}
        self.assertEqual(combat._choose_switch_target(current, False), current)

    def test_choose_switch_target_excludes_dead_teammate(self):
        task = FreezeTask()
        combat = make_combat({})
        current = BaseChar(task, 0, char_type=CharType.MAIN_DPS)
        healer = BaseChar(task, 1, char_type=CharType.HEALER)
        sub_dps = BaseChar(task, 2, char_type=CharType.SUB_DPS)
        combat.chars = [current, healer, sub_dps]

        combat.combat_dead_indices.add(1)
        self.assertEqual(combat._choose_switch_target(current, False), sub_dps)

    # --- BaseChar.switch_other_char 过滤 ---

    def test_switch_other_char_prefers_allowed_healer(self):
        task = SwitchTask(chars=None, current_index=0)
        current = BaseChar(task, 0, char_type=CharType.MAIN_DPS)
        healer = BaseChar(task, 1, char_type=CharType.HEALER)
        sub_dps = BaseChar(task, 2, char_type=CharType.SUB_DPS)
        task.chars = [current, healer, sub_dps]

        current.switch_other_char()
        self.assertEqual(task.sent_keys, ['2'])
        self.assertTrue(healer.is_current_char)
        self.assertFalse(current.is_current_char)

    def test_switch_other_char_skips_blocked_healer_and_blocked_fallback(self):
        task = SwitchTask(chars=None, current_index=0, blocked={1, 2})
        current = BaseChar(task, 0, char_type=CharType.MAIN_DPS)
        healer = BaseChar(task, 1, char_type=CharType.HEALER)
        sub_dps = BaseChar(task, 2, char_type=CharType.SUB_DPS)
        task.chars = [current, healer, sub_dps]

        current.switch_other_char()
        self.assertEqual(task.sent_keys, [])

    def test_switch_other_char_falls_back_when_no_healer(self):
        task = SwitchTask(chars=None, current_index=0)
        current = BaseChar(task, 0, char_type=CharType.MAIN_DPS)
        sub_dps = BaseChar(task, 1, char_type=CharType.SUB_DPS)
        task.chars = [current, sub_dps]

        current.switch_other_char()
        self.assertEqual(task.sent_keys, ['2'])

    def test_switch_other_char_no_target_when_teammate_dead(self):
        task = SwitchTask(chars=None, current_index=0, dead={1})
        current = BaseChar(task, 0, char_type=CharType.MAIN_DPS)
        healer = BaseChar(task, 1, char_type=CharType.HEALER)
        task.chars = [current, healer]

        current.switch_other_char()
        self.assertEqual(task.sent_keys, [])

    # --- handle_revive_dialog 三分支 ---

    def test_handle_revive_dialog_none_when_no_dialog(self):
        harness = ReviveDialogHarness(dialog_visible=False)
        combat = make_combat({'Revive Teammate with Medicine': True})
        for attr in ('wait_feature', 'find_one', 'find_feature', 'click', 'wait_until',
                     'close_revive_popup', 'info_set'):
            setattr(combat, attr, getattr(harness, attr))

        self.assertEqual(combat.handle_revive_dialog(), 'none')
        self.assertEqual(harness.clicked, [])
        self.assertEqual(harness.closed_popup, [])

    def test_handle_revive_dialog_revived_with_medicine(self):
        harness = ReviveDialogHarness(medicine=True, confirm_box='confirm_box', dialog_closes=True)
        combat = make_combat({'Revive Teammate with Medicine': True})
        for attr in ('wait_feature', 'find_one', 'find_feature', 'click', 'wait_until',
                     'close_revive_popup', 'info_set'):
            setattr(combat, attr, getattr(harness, attr))

        self.assertEqual(combat.handle_revive_dialog(), 'revived')
        self.assertEqual(harness.clicked, ['confirm_box'])
        self.assertIn(('Revive', 'Success'), harness.info)
        self.assertEqual(harness.closed_popup, [])

    def test_handle_revive_dialog_closed_when_confirm_template_missing(self):
        harness = ReviveDialogHarness(medicine=True, confirm_missing_template=True)
        combat = make_combat({'Revive Teammate with Medicine': True})
        for attr in ('wait_feature', 'find_one', 'find_feature', 'click', 'wait_until',
                     'close_revive_popup', 'info_set'):
            setattr(combat, attr, getattr(harness, attr))

        self.assertEqual(combat.handle_revive_dialog(), 'closed')
        self.assertEqual(harness.clicked, [])
        self.assertEqual(harness.closed_popup, [True])

    def test_handle_revive_dialog_closed_when_medicine_disabled(self):
        harness = ReviveDialogHarness(medicine=False)
        combat = make_combat({'Revive Teammate with Medicine': False})
        for attr in ('wait_feature', 'find_one', 'find_feature', 'click', 'wait_until',
                     'close_revive_popup', 'info_set'):
            setattr(combat, attr, getattr(harness, attr))

        self.assertEqual(combat.handle_revive_dialog(), 'closed')
        self.assertEqual(harness.clicked, [])
        self.assertEqual(harness.closed_popup, [True])


if __name__ == '__main__':
    unittest.main()
