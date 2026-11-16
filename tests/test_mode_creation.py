"""Mode creation, recovery and NVAPI ABI tests. Hardware writes are always mocked."""
import ast
import ctypes
from pathlib import Path
import time
import unittest
from unittest.mock import Mock, patch
import test_core
import nvidia_modes as nv

app = test_core.app


class NvidiaModeTests(unittest.TestCase):
    def test_public_sdk_abi_sizes_and_offsets(self):
        self.assertEqual([ctypes.sizeof(t) for t in (nv.TimingExtra, nv.Timing, nv.TimingFlags, nv.TimingInput, nv.CustomDisplay)], [64,96,12,32,144])
        self.assertEqual(nv.CustomDisplay.timing.offset, 44)
        self.assertEqual(nv.Timing.etc.offset, 32)

    def fake_api(self, failing=None):
        api = Mock()
        api.__enter__ = Mock(return_value=api)
        api.__exit__ = Mock(return_value=False)
        api.display_id.return_value = 123
        timing = nv.Timing()
        timing.etc.rrx1k = 144000
        api.timing.return_value = timing
        api.call.side_effect = lambda operation, *_: (_ for _ in ()).throw(nv.NvidiaError(operation, -175)) if operation == failing else None
        return api

    def test_trial_save_revert_order_and_current_refresh(self):
        api = self.fake_api()
        with patch.object(nv, 'NvidiaApi', return_value=api):
            result = nv.create_custom_resolution(r'\\.\DISPLAY1',1566,1080,144)
        self.assertEqual([c.args[0] for c in api.call.call_args_list], ['try_mode','save_mode','revert'])
        self.assertEqual(result['refresh'],144)
        custom = api.call.call_args_list[0].args[-1]._obj
        self.assertEqual((custom.width,custom.height,custom.srcPartition.w,custom.srcPartition.h),(1566,1080,1,1))
        self.assertEqual(api.timing.call_args.args, (123,1566,1080,144))

    def test_trial_failure_still_reverts_and_never_saves(self):
        api = self.fake_api('try_mode')
        with patch.object(nv,'NvidiaApi',return_value=api), self.assertRaises(nv.NvidiaError):
            nv.create_custom_resolution(r'\\.\DISPLAY1',1566,1080,144)
        self.assertEqual([c.args[0] for c in api.call.call_args_list],['try_mode','revert'])

    def test_save_failure_still_reverts(self):
        api = self.fake_api('save_mode')
        with patch.object(nv,'NvidiaApi',return_value=api), self.assertRaises(nv.NvidiaError) as failure:
            nv.create_custom_resolution(r'\\.\DISPLAY1',1566,1080,144)
        self.assertEqual(failure.exception.code,-175)
        self.assertEqual(api.call.call_args.args[0],'revert')

    def test_revert_failure_is_not_reported_as_success(self):
        api = self.fake_api('revert')
        with patch.object(nv,'NvidiaApi',return_value=api), self.assertRaises(nv.NvidiaError):
            nv.create_custom_resolution(r'\\.\DISPLAY1',1566,1080,144)

    def test_bad_dimensions_or_refresh_never_load_driver(self):
        with patch.object(nv,'NvidiaApi') as api:
            for args in [(100,1080,144),(1566,1080,0),(1566,1080,2000)]:
                with self.assertRaises(ValueError): nv.create_custom_resolution('DISPLAY',*args)
            api.assert_not_called()


class ModePreparationTests(unittest.TestCase):
    def setUp(self):
        for name,value in [('current_refresh_rate',144),('primary_display_name',r'\\.\DISPLAY1'),('get_display_resolution',(1920,1080))]:
            p=patch.object(app,name,return_value=value);p.start();self.addCleanup(p.stop)

    def test_existing_mode_skips_nvidia(self):
        with patch.object(app,'resolution_available',return_value=True), patch.object(app,'create_custom_resolution') as create:
            self.assertFalse(app.ensure_resolution_available(1566,1080))
        create.assert_not_called()

    def test_missing_mode_is_created_and_verified(self):
        with patch.object(app,'resolution_available',side_effect=[False,False,True]), patch.object(app,'create_custom_resolution') as create, patch.object(app.time,'sleep'):
            self.assertTrue(app.ensure_resolution_available(1566,1080))
        create.assert_called_once_with(r'\\.\DISPLAY1',1566,1080,144)

    def test_unsupported_driver_fails_without_elevation(self):
        with patch.object(app,'resolution_available',return_value=False), patch.object(app,'create_custom_resolution',side_effect=nv.NvidiaError('创建',-104)), patch.object(app,'run_elevated_program') as elevate:
            with self.assertRaises(app.DisplayError): app.ensure_resolution_available(1566,1080)
        elevate.assert_not_called()

    def test_access_denied_automatically_uses_restricted_helper(self):
        with patch.object(app,'resolution_available',side_effect=[False,True]), patch.object(app,'create_custom_resolution',side_effect=nv.NvidiaError('保存',-175)), patch.object(app,'run_elevated_program',return_value=0) as elevate:
            self.assertTrue(app.ensure_resolution_available(1566,1080))
        self.assertIn('--create-nvidia-mode 1566 1080',elevate.call_args.args[1])

    def test_uac_cancel_is_not_success(self):
        with patch.object(app,'resolution_available',return_value=False), patch.object(app,'create_custom_resolution',side_effect=nv.NvidiaError('保存',-175)), patch.object(app,'run_elevated_program',side_effect=app.ElevationDenied):
            with self.assertRaises(app.ElevationDenied): app.ensure_resolution_available(1566,1080)

    def test_saved_but_unlisted_mode_is_not_success(self):
        with patch.object(app,'resolution_available',return_value=False), patch.object(app,'create_custom_resolution'), patch.object(app.time,'sleep'):
            with self.assertRaisesRegex(app.DisplayError,'尚未报告'): app.ensure_resolution_available(1566,1080)


class NewModeWorkflowTests(unittest.TestCase):
    def setUp(self):
        test_core.CoreTests.setUp(self)
        self.resolution=(1920,1080)
        self.events=[]
        def change(w,h):
            self.events.append('resolution'); self.resolution=(w,h)
        for name,replacement in [('get_display_resolution',lambda:self.resolution),('change_display_resolution',change),
             ('list_monitor_devices',lambda:[{'instance_id':'DISPLAY\\A','status':'OK','problem':0}]),
             ('change_monitor_devices',lambda *_:self.events.append('device')),('is_valorant_running',lambda:False)]:
            p=patch.object(app,name,side_effect=replacement);p.start();self.addCleanup(p.stop)

    def test_creation_precedes_device_disable_and_arms_confirmation(self):
        def prepare(*_): self.events.append('create'); return True
        with patch.object(app,'ensure_resolution_available',side_effect=prepare):
            result=self.api.start_game_mode('1566x1080')
        self.assertTrue(result['created_mode'])
        self.assertEqual(self.events,['create','device','resolution'])
        self.assertGreater(self.api.get_game_mode_state()['confirmation_remaining'],0)
        self.api._arm_mode_confirmation.assert_called_once()

    def test_creation_failure_never_disables_a_monitor(self):
        with patch.object(app,'ensure_resolution_available',side_effect=app.DisplayError('驱动不支持')):
            self.assertFalse(self.api.start_game_mode('1566x1080')['success'])
        self.assertNotIn('resolution',self.events)
        # The recovery path can verify/enable the originally enabled device, but never disables it.
        self.assertEqual(app.load_game_session(),{})

    def test_confirmation_keeps_mode_and_cancels_deadline(self):
        with patch.object(app,'ensure_resolution_available',return_value=True): self.api.start_game_mode('1566x1080')
        self.assertTrue(self.api.confirm_game_mode()['success'])
        self.assertNotIn('confirmation_deadline',app.load_game_session())
        self.assertEqual(self.resolution,(1566,1080))

    def test_timeout_restores_resolution_before_admin_device_operation(self):
        with patch.object(app,'ensure_resolution_available',return_value=True): self.api.start_game_mode('1566x1080')
        deadline=app.load_game_session()['confirmation_deadline']
        self.events=[]
        self.api._mode_confirmation_timeout(deadline)
        self.assertEqual(self.events[:2],['resolution','device'])
        self.assertEqual(self.resolution,(1920,1080))
        self.assertEqual(app.load_game_session(),{})

    def test_stale_timer_cannot_restore_a_confirmed_session(self):
        with patch.object(app,'ensure_resolution_available',return_value=True): self.api.start_game_mode('1566x1080')
        deadline=app.load_game_session()['confirmation_deadline']
        self.api.confirm_game_mode();self.events=[]
        self.api._mode_confirmation_timeout(deadline)
        self.assertEqual(self.events,[])

    def test_dragging_is_restricted_and_text_selection_enabled(self):
        tree=ast.parse((Path(__file__).resolve().parents[1]/'main.pyw').read_text(encoding='utf-8'))
        create=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='create_window')
        options={k.arg:ast.literal_eval(k.value) for k in create.keywords if k.arg in ('easy_drag','text_select')}
        self.assertEqual(options,{'easy_drag':False,'text_select':True})
