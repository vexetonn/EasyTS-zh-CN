"""Run generated PowerShell against local stub functions, never real PnP cmdlets."""
import unittest
from test_core import app


class DeviceScriptTests(unittest.TestCase):
    STUB = r'''
function Get-PnpDevice {
    [CmdletBinding()] param($Class,[switch]$PresentOnly)
    [pscustomobject]@{InstanceId="DISPLAY\O'NE"}
    [pscustomobject]@{InstanceId='DISPLAY\TWO'}
}
function Disable-PnpDevice {
    [CmdletBinding()] param($InstanceId,[switch]$Confirm)
    if($InstanceId -eq 'DISPLAY\TWO'){throw 'Simulated failure'}
}
function Enable-PnpDevice {
    [CmdletBinding()] param($InstanceId,[switch]$Confirm)
}
'''

    def run_script(self, enabled, ids):
        script = app.build_driver_script(enabled, ids)
        app.build_elevated_params(script)
        return app.run_powershell(self.STUB + script)

    def test_exact_quoted_id_ignores_unselected_failure(self):
        self.assertEqual(self.run_script(False, ["DISPLAY\\O'NE"]).returncode, 0)

    def test_partial_failure_is_not_success(self):
        self.assertEqual(self.run_script(False, ["DISPLAY\\O'NE", 'DISPLAY\\TWO']).returncode, 2)

    def test_missing_target_cannot_succeed(self):
        self.assertEqual(self.run_script(True, ['DISPLAY\\MISSING']).returncode, 3)

    def test_enable_multiple_targets(self):
        self.assertEqual(self.run_script(True, ["DISPLAY\\O'NE", 'DISPLAY\\TWO']).returncode, 0)
