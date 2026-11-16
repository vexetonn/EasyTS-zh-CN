"""Transaction tests with simulated devices; never change the real desktop."""
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import test_core
app = test_core.app


class GameModeTests(unittest.TestCase):
    def setUp(self):
        test_core.CoreTests.setUp(self)
        self.monitor_helper = app.change_monitor_devices
        self.resolution = (1920, 1080)
        self.devices = [
            {'instance_id': 'DISPLAY\\ON', 'status': 'OK', 'problem': 0},
            {'instance_id': 'DISPLAY\\OFF', 'status': 'Error', 'problem': 22},
        ]
        self.events = []
        for name, replacement in [
            ('get_display_resolution', lambda: self.resolution),
            ('change_display_resolution', self.change_resolution),
            ('list_monitor_devices', lambda: [d.copy() for d in self.devices]),
            ('change_monitor_devices', self.change_monitors),
            ('is_valorant_running', lambda: False),
        ]:
            handle = patch.object(app, name, side_effect=replacement)
            handle.start()
            self.addCleanup(handle.stop)

    def change_resolution(self, width, height):
        self.events.append(('resolution', width, height))
        self.resolution = (width, height)

    def change_monitors(self, ids, enable):
        self.events.append(('monitors', list(ids), enable))
        for d in self.devices:
            if d['instance_id'] in ids:
                d.update(status='OK' if enable else 'Error', problem=0 if enable else 22)

    def test_one_click_orders_operations_and_preserves_pre_disabled_device(self):
        self.assertTrue(self.api.start_game_mode('1566x1080')['success'])
        self.assertEqual(self.events, [('monitors', ['DISPLAY\\ON'], False), ('resolution', 1566, 1080)])
        self.assertEqual(app.load_game_session()['original'], [1920, 1080])
        self.assertEqual(app.load_game_session()['restore_monitors'], ['DISPLAY\\ON'])
        self.assertTrue(self.api.restore_game_mode()['success'])
        self.assertEqual(self.events[-2:], [('monitors', ['DISPLAY\\ON'], True), ('resolution', 1920, 1080)])
        self.assertEqual(self.devices[1]['problem'], 22)
        self.assertEqual(app.load_game_session(), {})
        self.assertEqual(app.load_display_state(), {})

    def test_invalid_input_does_not_touch_devices(self):
        self.assertFalse(self.api.start_game_mode('abc')['success'])
        self.assertEqual(self.events, [])

    def test_uac_cancel_never_changes_resolution(self):
        with patch.object(app, 'change_monitor_devices', side_effect=app.ElevationDenied()):
            self.assertFalse(self.api.start_game_mode('1566x1080')['success'])
        self.assertEqual(self.events, [])
        self.assertEqual(app.load_game_session(), {})

    def test_failed_resolution_rolls_back_monitors(self):
        with patch.object(app, 'change_display_resolution', side_effect=app.DisplayError('分辨率不可用')):
            self.assertFalse(self.api.start_game_mode('1566x1080')['success'])
        self.assertEqual(self.devices[0]['problem'], 0)
        self.assertEqual(app.load_game_session(), {})

    def test_partial_disable_failure_rolls_back(self):
        def partial(ids, enable):
            self.change_monitors(ids, enable)
            if not enable:
                raise OSError('部分设备操作失败')
        with patch.object(app, 'change_monitor_devices', side_effect=partial):
            self.assertFalse(self.api.start_game_mode('1566x1080')['success'])
        self.assertEqual(self.devices[0]['problem'], 0)
        self.assertEqual(app.load_game_session(), {})

    def test_failed_rollback_retains_record_for_retry(self):
        with patch.object(app, 'change_monitor_devices', side_effect=[None, app.ElevationDenied()]), patch.object(app, 'change_display_resolution', side_effect=app.DisplayError('切换失败')):
            self.assertFalse(self.api.start_game_mode('1566x1080')['success'])
        self.assertEqual(app.load_game_session()['phase'], 'restore_needed')
        self.assertTrue(self.api.get_game_mode_state()['active'])
        self.assertTrue(self.api.restore_game_mode()['success'])

    def test_restore_cancel_still_attempts_resolution_and_keeps_record(self):
        self.api.start_game_mode('1566x1080')
        with patch.object(app, 'change_monitor_devices', side_effect=app.ElevationDenied()):
            self.assertFalse(self.api.restore_game_mode()['success'])
        self.assertEqual(self.resolution, (1920, 1080))
        self.assertTrue(app.load_game_session())
        self.assertTrue(self.api.restore_game_mode()['success'])

    def test_resolution_restore_failure_keeps_record(self):
        self.api.start_game_mode('1566x1080')
        with patch.object(app, 'change_display_resolution', side_effect=app.DisplayError('恢复失败')):
            self.assertFalse(self.api.restore_game_mode()['success'])
        self.assertEqual(self.devices[0]['problem'], 0)
        self.assertTrue(app.load_game_session())

    def test_original_saved_before_disable_can_change_mode(self):
        def disable(ids, enable):
            self.assertEqual(app.load_game_session()['original'], [1920, 1080])
            self.change_monitors(ids, enable)
            self.resolution = (1024, 768)
        with patch.object(app, 'change_monitor_devices', side_effect=disable):
            self.assertTrue(self.api.start_game_mode('1566x1080')['success'])
        self.assertEqual(app.load_display_state()['original'], [1920, 1080])

    def test_existing_manual_original_is_preserved(self):
        app.save_display_state({'original': [2560, 1440]})
        self.api.start_game_mode('1566x1080')
        self.assertEqual(app.load_game_session()['original'], [2560, 1440])

    def test_same_resolution_still_disables_and_watches(self):
        self.resolution = (1566, 1080)
        self.assertTrue(self.api.start_game_mode('1566x1080')['success'])
        self.assertEqual(self.devices[0]['problem'], 22)
        self.api._start_watcher.assert_called_once()
        self.assertEqual(app.read_json_file('last_resolution.json', None), '1566x1080')

    def test_game_already_running_requires_restart_before_disable(self):
        with patch.object(app, 'is_valorant_running', return_value=True):
            result = self.api.start_game_mode('1566x1080')
        self.assertFalse(result['success'])
        self.assertIn('退出', result['message'])
        self.assertEqual(self.events, [])

    def test_no_devices_or_abnormal_device_stops_before_change(self):
        for devices in ([], [{'instance_id': 'BAD', 'status': 'Error', 'problem': 10}]):
            self.devices = devices
            self.assertFalse(self.api.start_game_mode('1566x1080')['success'])
        self.assertEqual(self.events, [])

    def test_query_failure_is_not_treated_as_disabled(self):
        with patch.object(app, 'list_monitor_devices', side_effect=OSError('检测失败')):
            self.assertEqual(app.get_driver_status(), 'error')
            self.assertFalse(self.api.start_game_mode('1566x1080')['success'])
        self.assertEqual(self.events, [])

    def test_hotkey_menu_restore_keeps_monitor_recovery(self):
        self.api.start_game_mode('1566x1080')
        self.api._stop_watcher.reset_mock()
        self.api.toggle_resolution()
        self.assertEqual(self.resolution, (1920, 1080))
        self.api.get_display_state()
        self.api._stop_watcher.assert_not_called()
        self.assertTrue(app.load_game_session())
        self.api.toggle_resolution()
        self.assertEqual(self.resolution, (1566, 1080))
        self.assertTrue(app.load_game_session())

    def test_auto_game_exit_restores_both_even_after_menu_restore(self):
        self.api.start_game_mode('1566x1080')
        self.api.restore_display()
        self.api._seen = True
        stop = Mock()
        stop.wait.return_value = False
        stop.is_set.return_value = False
        self.api._watch_loop(stop)
        self.assertEqual(self.resolution, (1920, 1080))
        self.assertEqual(self.devices[0]['problem'], 0)
        self.assertEqual(app.load_game_session(), {})

    def test_restart_can_restore_persistent_session(self):
        self.api.start_game_mode('1566x1080')
        other = app.Api()
        other._window = Mock()
        self.assertTrue(other.resume_game_mode()['active'])
        self.assertTrue(other.restore_game_mode()['success'])
        self.assertEqual(self.resolution, (1920, 1080))

    def test_close_restores_and_failed_close_stays_open(self):
        self.api.start_game_mode('1566x1080')
        with patch.object(app, 'change_monitor_devices', side_effect=app.ElevationDenied()):
            self.api.close()
            self.api._window.destroy.assert_not_called()
            self.assertFalse(self.api.on_window_closing())
        self.api.close()
        self.api._window.destroy.assert_called_once()

    def test_cannot_overwrite_or_dismiss_active_session(self):
        self.api.start_game_mode('1566x1080')
        state = app.load_game_session()
        self.assertFalse(self.api.start_game_mode('1440x1080')['success'])
        self.assertFalse(self.api.dismiss_saved_display()['success'])
        self.assertEqual(app.load_game_session(), state)

    def test_corrupt_recovery_record_is_preserved(self):
        record = Path(app.get_easysts_dir(), 'game_session.json')
        record.write_text('{broken', encoding='utf-8')
        self.assertTrue(self.api.get_game_mode_state()['active'])
        self.assertFalse(self.api.start_game_mode('1566x1080')['success'])
        self.assertFalse(self.api.restore_game_mode()['success'])
        self.assertEqual(record.read_text(encoding='utf-8'), '{broken')

    def test_device_helper_verifies_exact_targets(self):
        def elevated(script):
            self.assertIn("'DISPLAY\\ON'", script)
            self.assertNotIn("'DISPLAY\\OFF'", script)
            self.change_monitors(['DISPLAY\\ON'], False)
            return 0
        with patch.object(app, 'run_elevated_powershell', side_effect=elevated) as run:
            self.monitor_helper(['DISPLAY\\ON'], False)
            self.monitor_helper(['DISPLAY\\ON'], False)
        run.assert_called_once()

    def test_device_helper_rejects_partial_success_and_missing_targets(self):
        with patch.object(app, 'run_elevated_powershell', return_value=0), patch.object(app.time, 'sleep'):
            with self.assertRaisesRegex(OSError, '未能确认'):
                self.monitor_helper(['DISPLAY\\ON'], False)
            with self.assertRaisesRegex(OSError, '未能确认'):
                self.monitor_helper(['MISSING'], True)

    def test_device_script_quotes_identifiers_and_fails_partial_operation(self):
        script = app.build_driver_script(False, ["DISPLAY\\O'NE"])
        self.assertIn("'DISPLAY\\O''NE'", script)
        self.assertIn('if($f -gt 0){exit 2}', script)
        self.assertIn('-Class Monitor', script)
        app.build_elevated_params(script)

    def test_only_problem_22_counts_as_disabled(self):
        self.assertTrue(app.monitor_disabled({'status': 'Error', 'problem': 22}))
        self.assertFalse(app.monitor_disabled({'status': 'Error', 'problem': 10}))
