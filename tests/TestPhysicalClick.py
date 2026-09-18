import unittest

import src.task.BaseWWTask as base_module
from src.task.BaseWWTask import BaseWWTask


class FakePynputBackend:
    created = []

    def __init__(self, capture, hwnd_window):
        self.capture = capture
        self.hwnd_window = hwnd_window
        self.click_calls = []
        self.click_error = None
        FakePynputBackend.created.append(self)

    def click(self, x, y, move_back=False, down_time=0.01, key="left"):
        if self.click_error:
            raise self.click_error
        self.click_calls.append({
            'x': x, 'y': y, 'move_back': move_back,
            'down_time': down_time, 'key': key,
        })


class FakeHwndWindow:
    def __init__(self, foreground=True):
        self._foreground = foreground

    def is_foreground(self):
        return self._foreground


class FakePostInteraction:
    pass


class FakePyDirectInteraction:
    pass


_UNSET = object()


class FakeTask:
    # bind the real unbound functions so self._get_physical_backend() resolves
    _get_physical_backend = BaseWWTask._get_physical_backend
    physical_click = BaseWWTask.physical_click
    physical_click_box = BaseWWTask.physical_click_box
    physical_click_relative = BaseWWTask.physical_click_relative

    def __init__(self, interaction=None, hwnd_window=_UNSET, capture_method=_UNSET,
                 foreground=True):
        if hwnd_window is _UNSET:
            hwnd_window = FakeHwndWindow(foreground)
        if capture_method is _UNSET:
            capture_method = object()
        self.executor = type('Executor', (), {})()
        self.executor.interaction = interaction if interaction is not None else FakePostInteraction()
        self.executor.device_manager = type('DM', (), {})()
        self.executor.device_manager.hwnd_window = hwnd_window
        self.executor.device_manager.capture_method = capture_method
        self.executor.reset_scene = self._reset_scene
        self.normal_clicks = []
        self.ensured_front = 0
        self.slept = []
        self.reset_scenes = 0
        self.errors = []
        self.width = 1920
        self.height = 1080

    def _reset_scene(self):
        self.reset_scenes += 1

    def click(self, x, y, after_sleep=1, name=None):
        self.normal_clicks.append((x, y, after_sleep, name))

    def ensure_in_front(self):
        self.ensured_front += 1

    def sleep(self, seconds):
        self.slept.append(seconds)

    def log_info(self, *args, **kwargs):
        pass

    def log_error(self, message):
        self.errors.append(message)

    def out_of_ratio(self):
        return False


class FakeBox:
    def __init__(self, name, x=100, y=200):
        self.name = name

    def relative_with_variance(self, rel_x, rel_y):
        return 111, 222


class TestGetPhysicalBackend(unittest.TestCase):

    def setUp(self):
        FakePynputBackend.created.clear()
        self._orig_pynput = base_module.PynputInteraction
        self._orig_pydirect = base_module.PyDirectInteraction
        base_module.PynputInteraction = FakePynputBackend
        base_module.PyDirectInteraction = FakePyDirectInteraction

    def tearDown(self):
        base_module.PynputInteraction = self._orig_pynput
        base_module.PyDirectInteraction = self._orig_pydirect

    def test_returns_none_when_global_interaction_is_already_physical(self):
        # with the module classes patched, a real Pynput backend instance is
        # an instance of the patched FakePynputBackend class
        for physical in (FakePynputBackend(None, None), FakePyDirectInteraction()):
            task = FakeTask(interaction=physical)
            self.assertIsNone(BaseWWTask._get_physical_backend(task))

    def test_builds_independent_pynput_backend_for_postmessage_global(self):
        task = FakeTask(interaction=FakePostInteraction())

        backend = BaseWWTask._get_physical_backend(task)

        self.assertIsInstance(backend, FakePynputBackend)
        self.assertIs(backend.capture, task.executor.device_manager.capture_method)
        self.assertIs(backend.hwnd_window, task.executor.device_manager.hwnd_window)
        # global interaction is untouched
        self.assertIsInstance(task.executor.interaction, FakePostInteraction)

    def test_backend_is_cached_and_reused(self):
        task = FakeTask()

        first = BaseWWTask._get_physical_backend(task)
        second = BaseWWTask._get_physical_backend(task)

        self.assertIs(first, second)
        self.assertEqual(len(FakePynputBackend.created), 1)

    def test_backend_refreshed_when_capture_is_rebuilt(self):
        task = FakeTask()
        first = BaseWWTask._get_physical_backend(task)

        task.executor.device_manager.capture_method = object()
        second = BaseWWTask._get_physical_backend(task)

        self.assertIsNot(first, second)
        self.assertEqual(len(FakePynputBackend.created), 2)

    def test_returns_none_without_hwnd_window_or_capture(self):
        task = FakeTask(hwnd_window=None, capture_method=object())
        self.assertIsNone(BaseWWTask._get_physical_backend(task))

        task = FakeTask(hwnd_window=FakeHwndWindow(), capture_method=None)
        self.assertIsNone(BaseWWTask._get_physical_backend(task))


class TestPhysicalClick(unittest.TestCase):

    def setUp(self):
        FakePynputBackend.created.clear()
        self._orig_pynput = base_module.PynputInteraction
        self._orig_pydirect = base_module.PyDirectInteraction
        base_module.PynputInteraction = FakePynputBackend
        base_module.PyDirectInteraction = FakePyDirectInteraction

    def tearDown(self):
        base_module.PynputInteraction = self._orig_pynput
        base_module.PyDirectInteraction = self._orig_pydirect

    def test_physical_global_interaction_falls_through_to_normal_click(self):
        task = FakeTask(interaction=FakePynputBackend(None, None))
        # constructing the interaction above records creation; only backend
        # creation inside the code under test must stay empty
        FakePynputBackend.created.clear()

        BaseWWTask.physical_click(task, 10, 20, after_sleep=0, name='login')

        self.assertEqual(task.normal_clicks, [(10, 20, 0, 'login')])
        self.assertEqual(FakePynputBackend.created, [])

    def test_postmessage_global_uses_lazy_backend_with_move_back(self):
        task = FakeTask(interaction=FakePostInteraction(), foreground=True)

        ok = BaseWWTask.physical_click(task, 100, 200, after_sleep=2, name='account')

        self.assertTrue(ok)
        backend = FakePynputBackend.created[0]
        self.assertEqual(backend.click_calls, [{
            'x': 100, 'y': 200, 'move_back': True,
            'down_time': 0.05, 'key': 'left',
        }])
        self.assertEqual(task.slept, [2])
        self.assertEqual(task.reset_scenes, 1)
        self.assertEqual(task.ensured_front, 0)

    def test_brings_window_to_front_when_not_foreground(self):
        task = FakeTask(interaction=FakePostInteraction(), foreground=False)

        BaseWWTask.physical_click(task, 1, 2, after_sleep=0)

        self.assertEqual(task.ensured_front, 1)
        self.assertIn(0.5, task.slept)
        self.assertEqual(len(FakePynputBackend.created[0].click_calls), 1)

    def test_backend_exception_falls_back_to_normal_click(self):
        task = FakeTask(interaction=FakePostInteraction(), foreground=True)
        # prime the cached backend then inject a failure
        BaseWWTask._get_physical_backend(task).click_error = RuntimeError('pynput boom')

        BaseWWTask.physical_click(task, 5, 6, after_sleep=1, name='dropdown')

        self.assertEqual(task.normal_clicks, [(5, 6, 1, 'dropdown')])
        self.assertTrue(any('pynput boom' in message for message in task.errors))

    def test_physical_click_box_unwraps_list_and_uses_box_center(self):
        task = FakeTask(interaction=FakePostInteraction())

        BaseWWTask.physical_click_box(task, [FakeBox('acc')], after_sleep=0)

        self.assertEqual(FakePynputBackend.created[0].click_calls[0]['x'], 111)
        self.assertEqual(FakePynputBackend.created[0].click_calls[0]['y'], 222)

    def test_physical_click_box_empty_list_is_noop(self):
        task = FakeTask(interaction=FakePostInteraction())

        self.assertFalse(BaseWWTask.physical_click_box(task, [], after_sleep=0))
        self.assertEqual(FakePynputBackend.created, [])

    def test_physical_click_relative_maps_frame_ratio_coordinates(self):
        task = FakeTask(interaction=FakePostInteraction())

        BaseWWTask.physical_click_relative(task, 0.5, 0.5, after_sleep=0)

        call = FakePynputBackend.created[0].click_calls[0]
        self.assertEqual((call['x'], call['y']), (960, 540))


if __name__ == "__main__":
    unittest.main()
