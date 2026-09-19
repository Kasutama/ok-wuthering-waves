import gc
import unittest

from src.task.AutoCombatTask import CombatToggleHotkey


class FakeHandler:
    """立即执行 post 的回调，模拟任务 Handler 线程的串行投递。"""

    def __init__(self, task):
        self.task = task
        self.posted = 0

    def post(self, fn, *args, **kwargs):
        self.posted += 1
        fn()
        return True


class FakeTask:
    def __init__(self, enabled=False, fail_enable=False):
        self._enabled = enabled
        self.fail_enable = fail_enable
        self.handler = FakeHandler(self)
        self.enable_calls = 0
        self.disable_calls = 0
        self.notifications = []

    @property
    def enabled(self):
        return self._enabled

    def enable(self):
        self.enable_calls += 1
        if self.fail_enable:
            raise RuntimeError('enable boom')
        self._enabled = True

    def disable(self):
        self.disable_calls += 1
        self._enabled = False

    def notification(self, message, title=None, tray=False):
        self.notifications.append((message, title, tray))


class FakeListener:
    def __init__(self, callback):
        self.callback = callback
        self.started = False
        self.daemon = False

    def start(self):
        self.started = True


class TestCombatToggleHotkey(unittest.TestCase):
    def setUp(self):
        self.created_listeners = []

        def factory(callback):
            listener = FakeListener(callback)
            self.created_listeners.append(listener)
            return listener

        self.hk = CombatToggleHotkey(listener_factory=factory)
        self.factory = factory

    def test_register_starts_single_listener_for_all_tasks(self):
        t1 = FakeTask()
        t2 = FakeTask()
        self.hk.register(t1)
        self.hk.register(t2)
        self.assertEqual(len(self.created_listeners), 1)
        self.assertTrue(self.created_listeners[0].started)
        self.assertTrue(self.created_listeners[0].daemon)

    def test_first_press_enables_and_notifies(self):
        task = FakeTask(enabled=False)
        self.hk.register(task)
        self.created_listeners[0].callback()
        self.assertTrue(task.enabled)
        self.assertEqual(task.enable_calls, 1)
        self.assertEqual(task.disable_calls, 0)
        message, title, tray = task.notifications[0]
        self.assertIn('自动战斗', message)
        self.assertTrue(tray)

    def test_second_press_disables(self):
        task = FakeTask(enabled=True)
        self.hk.register(task)
        self.created_listeners[0].callback()
        self.assertFalse(task.enabled)
        self.assertEqual(task.disable_calls, 1)
        self.assertIn('手动战斗', task.notifications[0][0])

    def test_debounce_ignores_rapid_repeat(self):
        task = FakeTask(enabled=False)
        self.hk.register(task)
        cb = self.created_listeners[0].callback
        cb()
        cb()
        cb()
        self.assertEqual(task.handler.posted, 1)
        self.assertTrue(task.enabled)

    def test_toggle_failure_does_not_raise_from_hotkey(self):
        task = FakeTask(enabled=False, fail_enable=True)
        self.hk.register(task)
        # 不应抛异常
        self.created_listeners[0].callback()
        self.assertEqual(task.enable_calls, 1)
        self.assertEqual(task.notifications, [])

    def test_listener_start_failure_does_not_break_registration(self):
        hk = CombatToggleHotkey(listener_factory=lambda cb: (_ for _ in ()).throw(RuntimeError('occupied')))
        task = FakeTask()
        hk.register(task)  # 不抛异常
        # 直接调用切换逻辑仍可用
        hk.toggle(task)
        self.assertTrue(task.enabled)

    def test_garbage_collected_task_is_not_toggled(self):
        task = FakeTask()
        self.hk.register(task)
        del task
        gc.collect()
        # 弱引用集合已空，触发不报错
        self.created_listeners[0].callback()

    def test_hotkey_is_f5(self):
        self.assertEqual(CombatToggleHotkey.HOTKEY, '<f5>')


if __name__ == '__main__':
    unittest.main()
