"""Regression checks use temporary settings and mocks; never change the display."""
import ast
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('easyts_zh', str(ROOT / 'main.pyw'))
spec = importlib.util.spec_from_loader(loader.name, loader)
app = importlib.util.module_from_spec(spec)
loader.exec_module(app)


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {'LOCALAPPDATA': self.temp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.api = app.Api()
        self.api._window = Mock()
        self.api._start_watcher = Mock()
        self.api._stop_watcher = Mock()

    def test_resolution_formats(self):
        for value in ('1566x1080', '1566×1080', '1566 1080', '1566,1080'):
            self.assertEqual(app.parse_resolution(value), (1566, 1080))

    def test_invalid_resolution_is_chinese(self):
        for value in ('abc', '100x1080', '16385x1080'):
            with self.assertRaisesRegex(ValueError, '[\u4e00-\u9fff]'):
                app.parse_resolution(value)

    def test_hotkey_validation_and_labels(self):
        self.assertEqual(app.validate_hotkey({'key': 'F6', 'modifiers': 0}), {'key': 'F6', 'modifiers': 0})
        self.assertEqual(app.hotkey_label(app.DEFAULT_HOTKEY), 'Ctrl + Alt + S')
        for value in ({'key': 'F4', 'modifiers': 1}, {'key': 'F12', 'modifiers': 0}, None):
            with self.assertRaisesRegex(ValueError, '[\u4e00-\u9fff]'):
                app.validate_hotkey(value)

    def test_legacy_settings_stay_compatible(self):
        app.write_json_file('settings.json', {'auto_restore': False})
        self.assertEqual(app.load_settings(), {'auto_restore': False, 'hotkey_enabled': True, 'hotkey': {'key': 'S', 'modifiers': 3}})

    def test_preset_roundtrip(self):
        self.assertTrue(self.api.save_preset('1566x1080', '1566×1080')['success'])
        self.assertEqual(self.api.get_presets(), [{'name': '1566x1080', 'resolution': '1566x1080'}])
        self.api.delete_preset('1566x1080')
        self.assertEqual(self.api.get_presets(), [])

    def test_successful_apply_saves_original_and_hotkey_target(self):
        with patch.object(app, 'get_display_resolution', return_value=(1920, 1080)), patch.object(app, 'change_display_resolution') as change:
            result = self.api.apply_resolution('1566x1080')
        self.assertTrue(result['success'])
        change.assert_called_once_with(1566, 1080)
        self.assertEqual(app.load_display_state()['original'], [1920, 1080])
        self.assertEqual(app.read_json_file('last_resolution.json', None), '1566x1080')
        self.api._start_watcher.assert_called_once()

    def test_failed_first_apply_leaves_no_restore_state(self):
        with patch.object(app, 'get_display_resolution', return_value=(1920, 1080)), patch.object(app, 'change_display_resolution', side_effect=app.DisplayError('分辨率不可用')):
            result = self.api.apply_resolution('1566x1080')
        self.assertFalse(result['success'])
        self.assertEqual(app.load_display_state(), {})
        self.assertIsNone(app.read_json_file('last_resolution.json', None))

    def test_failed_subsequent_apply_preserves_previous_state(self):
        saved = {'original': [1920, 1080], 'applied': [1566, 1080]}
        app.save_display_state(saved)
        app.write_json_file('last_resolution.json', '1566x1080')
        with patch.object(app, 'get_display_resolution', return_value=(1566, 1080)), patch.object(app, 'change_display_resolution', side_effect=app.DisplayError('分辨率不可用')):
            self.assertFalse(self.api.apply_resolution('1440x1080')['success'])
        self.assertEqual(app.load_display_state(), saved)
        self.assertEqual(app.read_json_file('last_resolution.json', None), '1566x1080')

    def test_apply_same_resolution_is_noop(self):
        with patch.object(app, 'get_display_resolution', return_value=(1566, 1080)), patch.object(app, 'change_display_resolution') as change:
            self.assertFalse(self.api.apply_resolution('1566x1080')['changed'])
        change.assert_not_called()

    def test_restore_preserves_hotkey_target(self):
        app.save_display_state({'original': [1920, 1080]})
        app.write_json_file('last_resolution.json', '1566x1080')
        with patch.object(app, 'get_display_resolution', return_value=(1566, 1080)), patch.object(app, 'change_display_resolution') as change:
            self.assertTrue(self.api.restore_display()['success'])
        change.assert_called_once_with(1920, 1080)
        self.assertEqual(app.load_display_state(), {})
        self.assertEqual(app.read_json_file('last_resolution.json', None), '1566x1080')

    def test_failed_restore_retains_saved_original(self):
        app.save_display_state({'original': [1920, 1080]})
        with patch.object(app, 'get_display_resolution', return_value=(1566, 1080)), patch.object(app, 'change_display_resolution', side_effect=app.DisplayError('恢复失败')):
            self.assertFalse(self.api.restore_display()['success'])
        self.assertEqual(app.load_display_state()['original'], [1920, 1080])

    def test_hotkey_toggles_both_directions(self):
        self.api.apply_resolution = Mock(return_value={'success': True})
        self.api.restore_display = Mock(return_value={'success': True})
        app.write_json_file('last_resolution.json', '1566x1080')
        with patch.object(app, 'get_display_resolution', return_value=(1920, 1080)):
            self.api.toggle_resolution()
        self.api.apply_resolution.assert_called_once_with('1566x1080')
        app.save_display_state({'original': [1920, 1080]})
        with patch.object(app, 'get_display_resolution', return_value=(1566, 1080)):
            self.api.toggle_resolution()
        self.api.restore_display.assert_called_once()

    def test_hotkey_conflict_retains_old_binding(self):
        old = Mock(active=True, binding=app.DEFAULT_HOTKEY.copy())
        self.api._hotkey = old
        candidate = Mock(active=False, error='快捷键被占用')
        with patch.object(app, 'ResolutionHotkey', return_value=candidate):
            result = self.api.set_hotkey({'key': 'F6', 'modifiers': 0})
        self.assertFalse(result['success'])
        self.assertIs(self.api._hotkey, old)
        old.close.assert_not_called()
        self.assertEqual(app.load_settings()['hotkey'], app.DEFAULT_HOTKEY)

    def test_denied_admin_action_preserves_driver_status(self):
        with patch.object(app, 'run_elevated_powershell', side_effect=app.ElevationDenied()), patch.object(app, 'get_driver_status', return_value='enabled'):
            result = self.api.set_driver_enabled(False)
        self.assertEqual(result, {'success': False, 'denied': True, 'status': 'enabled'})

    def test_black_bars_denied_and_success(self):
        with patch.object(app, 'run_elevated_powershell', side_effect=app.ElevationDenied()):
            self.assertTrue(self.api.fix_black_bars()['denied'])
        with patch.object(app, 'run_elevated_powershell', return_value=0):
            self.assertTrue(self.api.fix_black_bars()['success'])

    def test_close_cancel_keeps_app_running(self):
        self.api._snapshot = Mock(return_value={'original': [1920, 1080], 'current': [1566, 1080], 'watching': True})
        self.api._window.create_confirmation_dialog.return_value = False
        self.api.close()
        self.api._window.destroy.assert_not_called()
        message = self.api._window.create_confirmation_dialog.call_args.args[1]
        self.assertIn('需要自行恢复分辨率', message)

    def test_offline_bundled_ui(self):
        with patch.object(app.urllib.request, 'urlopen', side_effect=AssertionError('Network must not load the UI')):
            page = app.load_local_html()
        self.assertIn('lang="zh-CN"', page)
        self.assertIn('data:image/jpeg;base64,', page)
        self.assertNotIn('fonts.googleapis.com', page)

    def test_packaged_path_and_missing_interface(self):
        with patch.object(app.sys, '_MEIPASS', self.temp.name, create=True):
            with self.assertRaises(FileNotFoundError):
                app.load_local_html()
            Path(self.temp.name, 'index.html').write_text('   ', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '内置中文界面为空'):
                app.load_local_html()
            Path(self.temp.name, 'index.html').write_text('中文页面', encoding='utf-8')
            self.assertEqual(app.load_local_html(), '中文页面')

    def test_windows_error_details_keep_a_chinese_explanation(self):
        self.assertEqual(app.error_message(ValueError('中文错误')), '中文错误')
        self.assertIn('系统详细信息：Access denied', app.error_message(OSError('Access denied')))

    def test_display_return_codes_are_chinese(self):
        for code, template in app.DISPLAY_CHANGE_MESSAGES.items():
            self.assertRegex(template.format(w=1566, h=1080, c=code), '[\u4e00-\u9fff]')


if __name__ == '__main__':
    unittest.main(verbosity=2)
