$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create the build environment.' }
}
& .\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Failed to install build dependencies.' }
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean EasyTS-zh-CN.spec
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
Write-Host 'Build complete: dist\EasyTS-zh-CN.exe'
