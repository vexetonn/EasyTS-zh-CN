# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)
package_data = [
    (str(root / 'index.html'), '.'),
    (str(root / 'LICENSE'), 'licenses/EasyTS'),
    (str(root / 'README.zh-CN.md'), 'help'),
    (str(root / 'THIRD_PARTY_LICENSES'), 'licenses/third-party'),
]
a = Analysis(
    [str(root / 'main.pyw')],
    pathex=[str(root)],
    binaries=[],
    datas=package_data,
    hiddenimports=['webview.platforms.winforms', 'webview.platforms.edgechromium'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'cefpython3'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='EasyTS-zh-CN',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(root / 'assets' / 'EasyTS.ico'),
    version=str(root / 'version_info.txt'),
    uac_admin=False,
)
