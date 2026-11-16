# VEX
# Copyright (c) 2026 ahhmilo. All rights reserved.
#
# This software is proprietary. The source code is publicly viewable for
# transparency, but copying, modification, redistribution, reuploading,
# repackaging, or publishing modified versions is not allowed without
# explicit permission from the author.
#
# See LICENSE for full license terms.

import webview
import os
import sys
import re
import json
import time
import math
import base64
import ctypes
import winreg
import threading
import subprocess
import tempfile
import textwrap
import webbrowser
import urllib.request
import tkinter as tk
from tkinter import messagebox
from ctypes import wintypes
from typing import Optional, Tuple
from nvidia_modes import NvidiaError, create_custom_resolution

CURRENT_VERSION = "v4.2.0"
GITHUB_URL      = "https://github.com/ahhmilo/EasyTS"
APP_NAME = "VEX"
APP_VERSION = "1.1.0"

WEBVIEW2_DOWNLOAD_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
WEBVIEW2_REGISTRY_KEYS = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
    (winreg.HKEY_CURRENT_USER,  r"Software\Microsoft\EdgeUpdate\ClientState\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
]

CREATE_NO_WINDOW      = 0x08000000
ENUM_CURRENT_SETTINGS = 0xFFFFFFFF
DM_PELSWIDTH          = 0x00080000
DM_PELSHEIGHT         = 0x00100000
SEE_MASK_NOCLOSEPROCESS = 0x00000040
SW_HIDE               = 0
ERROR_CANCELLED       = 1223
MAX_ELEVATED_PARAMS   = 1900
MODE_CONFIRM_SECONDS = 20

DISPLAY_CHANGE_MESSAGES = {
    1:  "Windows 需要重启后才能应用 {w}x{h}。",
    -1: "显卡驱动无法切换到 {w}x{h}。",
    -2: "Windows 拒绝应用 {w}x{h}。驱动未接受该显示模式，请查看日志中的分辨率检测或创建结果。",
    -3: "Windows 无法保存 {w}x{h} 的显示设置。",
    -4: "Windows 拒绝了切换到 {w}x{h} 的请求。",
    -5: "Windows 拒绝了切换到 {w}x{h} 的请求。",
    -6: "在当前多显示器配置下，Windows 无法应用 {w}x{h}。",
}

VALORANT_PROCESS        = "valorant-win64-shipping.exe"
WATCH_INTERVAL          = 4
WATCH_MISSES_REQUIRED   = 2
MIN_DIMENSION           = 200
MAX_DIMENSION           = 16384

RESOLUTION_PATTERN = re.compile(r"^\s*(\d{3,5})\s*[x\u00d7,\s]\s*(\d{3,5})\s*$", re.IGNORECASE)

DEFAULT_SETTINGS = {"auto_restore": True, "hotkey_enabled": True}
DEFAULT_HOTKEY = {"key": "S", "modifiers": 3}
HOTKEY_KEYS = {chr(k): k for k in range(65, 91)}
HOTKEY_KEYS.update({str(k): 48 + k for k in range(10)})
HOTKEY_KEYS.update({f"F{k}": 111 + k for k in range(1, 12)})


def validate_hotkey(value):
    if not isinstance(value, dict):
        raise ValueError("请选择一个按键，可搭配 Ctrl、Alt 或 Shift。")
    key, modifiers = value.get("key"), value.get("modifiers")
    if not isinstance(key, str) or key not in HOTKEY_KEYS or type(modifiers) is not int or not 0 <= modifiers <= 7:
        raise ValueError("支持 A–Z、0–9、F1–F11，可搭配 Ctrl、Alt 或 Shift。")
    if (key == "F4" and modifiers & 1) or (key == "F10" and modifiers == 4):
        raise ValueError("此快捷键用于窗口控制，请选择其他按键。")
    return {"key": key, "modifiers": modifiers}


def hotkey_label(value):
    return " + ".join([name for bit, name in [(2, "Ctrl"), (1, "Alt"), (4, "Shift")] if value["modifiers"] & bit] + [value["key"]])

DRIVER_STATUS_SCRIPT = (
    "Get-PnpDevice -Class Monitor -PresentOnly -ErrorAction Stop | "
    "Select-Object InstanceId,FriendlyName,Status,Problem | ConvertTo-Json -Compress"
)

BLACK_BARS_SCRIPT = (
    r"$b='HKLM:\SYSTEM\ControlSet001\Control\GraphicsDrivers\Configuration';$c=0;$f=0;"
    r"try{$k=Get-ChildItem $b -ErrorAction Stop}catch{exit 2};"
    r"foreach($i in $k){$p=Join-Path $i.PSPath '00\00';"
    r"if($null -ne (Get-ItemProperty $p -Name Scaling -ErrorAction SilentlyContinue)){"
    r"try{Set-ItemProperty $p -Name Scaling -Value 3 -Type DWord -ErrorAction Stop;$c++}catch{$f++}}};"
    r"if($f -gt 0){exit 2};if($c -eq 0){exit 3};exit 0"
)


class DisplayError(Exception):
    pass


class ElevationDenied(Exception):
    pass


class DEVMODE(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName",         ctypes.c_uint16 * 32),
        ("dmSpecVersion",        ctypes.c_uint16),
        ("dmDriverVersion",      ctypes.c_uint16),
        ("dmSize",               ctypes.c_uint16),
        ("dmDriverExtra",        ctypes.c_uint16),
        ("dmFields",             ctypes.c_uint32),
        ("dmPositionX",          ctypes.c_int32),
        ("dmPositionY",          ctypes.c_int32),
        ("dmDisplayOrientation", ctypes.c_uint32),
        ("dmDisplayFixedOutput", ctypes.c_uint32),
        ("dmColor",              ctypes.c_int16),
        ("dmDuplex",             ctypes.c_int16),
        ("dmYResolution",        ctypes.c_int16),
        ("dmTTOption",           ctypes.c_int16),
        ("dmCollate",            ctypes.c_int16),
        ("dmFormName",           ctypes.c_uint16 * 32),
        ("dmLogPixels",          ctypes.c_uint16),
        ("dmBitsPerPel",         ctypes.c_uint32),
        ("dmPelsWidth",          ctypes.c_uint32),
        ("dmPelsHeight",         ctypes.c_uint32),
        ("dmDisplayFlags",       ctypes.c_uint32),
        ("dmDisplayFrequency",   ctypes.c_uint32),
        ("dmICMMethod",          ctypes.c_uint32),
        ("dmICMIntent",          ctypes.c_uint32),
        ("dmMediaType",          ctypes.c_uint32),
        ("dmDitherType",         ctypes.c_uint32),
        ("dmReserved1",          ctypes.c_uint32),
        ("dmReserved2",          ctypes.c_uint32),
        ("dmPanningWidth",       ctypes.c_uint32),
        ("dmPanningHeight",      ctypes.c_uint32),
    ]


class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize",         ctypes.c_uint32),
        ("fMask",          ctypes.c_uint32),
        ("hwnd",           ctypes.c_void_p),
        ("lpVerb",         ctypes.c_wchar_p),
        ("lpFile",         ctypes.c_wchar_p),
        ("lpParameters",   ctypes.c_wchar_p),
        ("lpDirectory",    ctypes.c_wchar_p),
        ("nShow",          ctypes.c_int),
        ("hInstApp",       ctypes.c_void_p),
        ("lpIDList",       ctypes.c_void_p),
        ("lpClass",        ctypes.c_wchar_p),
        ("hkeyClass",      ctypes.c_void_p),
        ("dwHotKey",       ctypes.c_uint32),
        ("hIconOrMonitor", ctypes.c_void_p),
        ("hProcess",       ctypes.c_void_p),
    ]


_user32_cache = None

def _user32():
    global _user32_cache
    if _user32_cache is None:
        lib = ctypes.WinDLL("user32", use_last_error=True)
        lib.EnumDisplaySettingsW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.POINTER(DEVMODE)]
        lib.EnumDisplaySettingsW.restype  = ctypes.c_int
        lib.ChangeDisplaySettingsW.argtypes = [ctypes.POINTER(DEVMODE), ctypes.c_uint32]
        lib.ChangeDisplaySettingsW.restype  = ctypes.c_int32
        _user32_cache = lib
    return _user32_cache

def get_display_resolution() -> Tuple[int, int]:
    dm = DEVMODE()
    dm.dmSize = ctypes.sizeof(DEVMODE)
    if not _user32().EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, ctypes.byref(dm)):
        raise DisplayError("无法读取当前分辨率。")
    return int(dm.dmPelsWidth), int(dm.dmPelsHeight)

def change_display_resolution(width: int, height: int) -> None:
    dm = DEVMODE()
    dm.dmSize = ctypes.sizeof(DEVMODE)
    _user32().EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, ctypes.byref(dm))
    dm.dmPelsWidth  = width
    dm.dmPelsHeight = height
    dm.dmFields     = DM_PELSWIDTH | DM_PELSHEIGHT
    code = _user32().ChangeDisplaySettingsW(ctypes.byref(dm), 0)
    if code != 0:
        template = DISPLAY_CHANGE_MESSAGES.get(code, "Windows 无法应用 {w}x{h}（错误码 {c}）。")
        raise DisplayError(template.format(w=width, h=height, c=code))


class DisplayDevice(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('DeviceName', wintypes.WCHAR * 32),
                ('DeviceString', wintypes.WCHAR * 128), ('StateFlags', wintypes.DWORD),
                ('DeviceID', wintypes.WCHAR * 128), ('DeviceKey', wintypes.WCHAR * 128)]


def primary_display_name() -> str:
    user32 = _user32()
    user32.EnumDisplayDevicesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DisplayDevice), wintypes.DWORD]
    user32.EnumDisplayDevicesW.restype = wintypes.BOOL
    for index in range(64):
        device = DisplayDevice()
        device.cb = ctypes.sizeof(device)
        if not user32.EnumDisplayDevicesW(None, index, ctypes.byref(device), 0):
            break
        if device.StateFlags & 4:
            return device.DeviceName
    raise DisplayError('无法识别 Windows 主显示器。')


def current_refresh_rate() -> int:
    mode = DEVMODE()
    mode.dmSize = ctypes.sizeof(mode)
    if not _user32().EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, ctypes.byref(mode)):
        raise DisplayError('无法读取主显示器刷新率。')
    if not 20 <= mode.dmDisplayFrequency <= 1000:
        raise DisplayError('主显示器未报告有效刷新率，已停止创建自定义分辨率。')
    return int(mode.dmDisplayFrequency)


def resolution_available(width: int, height: int, refresh: int) -> bool:
    for index in range(4096):
        mode = DEVMODE()
        mode.dmSize = ctypes.sizeof(mode)
        if not _user32().EnumDisplaySettingsW(None, index, ctypes.byref(mode)):
            return False
        if (mode.dmPelsWidth, mode.dmPelsHeight, mode.dmDisplayFrequency) == (width, height, refresh):
            return True
    raise DisplayError('显示模式列表过长，无法确认目标分辨率。')


def ensure_resolution_available(width: int, height: int) -> bool:
    """Create only a missing mode, on the NVIDIA-connected primary display."""
    refresh = current_refresh_rate()
    if resolution_available(width, height, refresh):
        return False
    original = get_display_resolution()
    try:
        create_custom_resolution(primary_display_name(), width, height, refresh)
    except NvidiaError as exc:
        if exc.code != -175:
            raise DisplayError(str(exc)) from exc
        if get_display_resolution() != original:
            change_display_resolution(*original)
        args = ['--create-nvidia-mode', str(width), str(height)]
        if not getattr(sys, 'frozen', False):
            args.insert(0, os.path.abspath(__file__))
        code = run_elevated_program(sys.executable, subprocess.list2cmdline(args))
        if code != 0:
            raise DisplayError(f'管理员创建自定义分辨率未完成（结果 {code}）。未继续禁用监视器。')
    if get_display_resolution() != original:
        raise DisplayError('自定义分辨率测试后未能确认原桌面已恢复，已停止后续操作。')
    for attempt in range(10):
        if resolution_available(width, height, refresh):
            return True
        if attempt < 9:
            time.sleep(0.2)
    raise DisplayError('NVIDIA 返回已保存，但 Windows 尚未报告目标分辨率，已停止后续操作。')

def parse_resolution(text) -> Tuple[int, int]:
    match = RESOLUTION_PATTERN.match(str(text))
    if not match:
        raise ValueError("格式不正确，请输入“宽度x高度”，例如 1440x1080。")
    width, height = int(match.group(1)), int(match.group(2))
    if not (MIN_DIMENSION <= width <= MAX_DIMENSION and MIN_DIMENSION <= height <= MAX_DIMENSION):
        raise ValueError("此分辨率超出了支持范围（宽、高均须为 200–16384）。")
    return width, height


def log_to_ui(window, message: str, msg_type: str = "info"):
    window.evaluate_js(f"window.appendLog({json.dumps(message)}, {json.dumps(msg_type)});")


def get_easysts_dir() -> str:
    path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "EasyTS")
    os.makedirs(path, exist_ok=True)
    return path

def read_json_file(name: str, fallback):
    path = os.path.join(get_easysts_dir(), name)
    if not os.path.isfile(path):
        return fallback
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback

def write_json_file(name: str, data) -> None:
    with open(os.path.join(get_easysts_dir(), name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_settings() -> dict:
    data = read_json_file("settings.json", {})
    settings = DEFAULT_SETTINGS.copy()
    if isinstance(data, dict):
        for key in DEFAULT_SETTINGS:
            if key in data:
                settings[key] = bool(data[key])
    try:
        settings["hotkey"] = validate_hotkey(data.get("hotkey", DEFAULT_HOTKEY))
    except (ValueError, AttributeError):
        settings["hotkey"] = DEFAULT_HOTKEY.copy()
    return settings

def save_settings(settings: dict) -> None:
    write_json_file("settings.json", settings)

def load_presets() -> list:
    data = read_json_file("presets.json", [])
    if not isinstance(data, list):
        return []
    return [p for p in data if isinstance(p, dict) and "name" in p and "resolution" in p]

def save_presets(presets: list) -> None:
    write_json_file("presets.json", presets)

def load_display_state() -> dict:
    data = read_json_file("display_state.json", {})
    if not isinstance(data, dict):
        return {}
    original = data.get("original")
    if not (isinstance(original, list) and len(original) == 2 and all(isinstance(v, int) for v in original)):
        return {}
    return data

def save_display_state(state: dict) -> None:
    write_json_file("display_state.json", state)

def clear_display_state() -> None:
    path = os.path.join(get_easysts_dir(), "display_state.json")
    if os.path.isfile(path):
        os.remove(path)


def load_game_session() -> dict:
    path = os.path.join(get_easysts_dir(), "game_session.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
        original = data["original"]
        if (data.get("version") != 1 or not isinstance(original, list) or len(original) != 2
                or not all(type(v) is int and MIN_DIMENSION <= v <= MAX_DIMENSION for v in original)
                or not isinstance(data["restore_monitors"], list)
                or not all(isinstance(v, str) and v for v in data["restore_monitors"])):
            raise ValueError()
        return data
    except Exception as exc:
        raise ValueError("一键模式的恢复记录无法读取。请保留数据目录中的 game_session.json，以便检查。") from exc


def save_game_session(state: dict) -> None:
    path = os.path.join(get_easysts_dir(), "game_session.json")
    # Commit the recovery record before changing any device or display setting.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=get_easysts_dir(), delete=False) as file:
        temporary = file.name
        json.dump(state, file, indent=2, ensure_ascii=False)
        file.flush()
        os.fsync(file.fileno())
    try:
        os.replace(temporary, path)
    finally:
        if os.path.isfile(temporary):
            os.remove(temporary)


def clear_game_session() -> None:
    path = os.path.join(get_easysts_dir(), "game_session.json")
    if os.path.isfile(path):
        os.remove(path)


def powershell_executable() -> str:
    return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")


def is_valorant_running() -> bool:
    try:
        result = subprocess.run(
            ["tasklist", "/NH", "/FO", "CSV"],
            capture_output=True, text=True, errors="replace",
            creationflags=CREATE_NO_WINDOW
        )
        return VALORANT_PROCESS in result.stdout.lower()
    except Exception:
        return False


def run_powershell(script: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        [powershell_executable(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-Command", "[Console]::OutputEncoding=[Text.Encoding]::UTF8;" + script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, creationflags=CREATE_NO_WINDOW
    )

def build_elevated_params(script: str) -> str:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    params = f"-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -EncodedCommand {encoded}"
    if len(params) > MAX_ELEVATED_PARAMS:
        raise ValueError("管理员操作脚本过长，无法执行。")
    return params

def run_elevated_powershell(script: str, timeout_ms: int = 120000) -> int:
    params = build_elevated_params(script)
    return run_elevated_program(powershell_executable(), params, timeout_ms)


def run_elevated_program(executable: str, params: str, timeout_ms: int = 120000) -> int:

    shell32  = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
    shell32.ShellExecuteExW.restype  = ctypes.c_int
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.WaitForSingleObject.restype  = ctypes.c_uint32
    kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    kernel32.GetExitCodeProcess.restype  = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype  = ctypes.c_int
    kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.TerminateProcess.restype = ctypes.c_int

    info = SHELLEXECUTEINFOW()
    info.cbSize       = ctypes.sizeof(SHELLEXECUTEINFOW)
    info.fMask        = SEE_MASK_NOCLOSEPROCESS
    info.lpVerb       = "runas"
    info.lpFile       = executable
    info.lpParameters = params
    info.nShow        = SW_HIDE

    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        if ctypes.get_last_error() == ERROR_CANCELLED:
            raise ElevationDenied()
        raise OSError("无法启动管理员操作。")
    if not info.hProcess:
        raise OSError("管理员操作未返回有效的进程句柄。")

    try:
        if kernel32.WaitForSingleObject(info.hProcess, timeout_ms) != 0:
            kernel32.TerminateProcess(info.hProcess, 1)
            raise TimeoutError("等待管理员操作完成超时。")
        code = ctypes.c_uint32()
        kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
        return int(code.value)
    finally:
        kernel32.CloseHandle(info.hProcess)


def list_monitor_devices() -> list:
    try:
        result = run_powershell(DRIVER_STATUS_SCRIPT)
        if result.returncode != 0:
            raise OSError("监视器查询失败。")
        raw = result.stdout.strip()
        if not raw:
            return []
        data = json.loads(raw)
    except Exception as exc:
        raise OSError("无法检测监视器状态，请重新检测后再试。") from exc
    if isinstance(data, dict):
        data = [data]
    devices = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict) and item.get("InstanceId"):
            devices.append({
                "instance_id": item["InstanceId"],
                "name":        item.get("FriendlyName") or "监视器",
                "status":      str(item.get("Status") or ""),
                "problem":     item.get("Problem"),
            })
    return devices

def get_driver_status() -> str:
    try:
        devices = list_monitor_devices()
    except Exception:
        return "error"
    if not devices:
        return "not_found"
    if any(monitor_enabled(d) for d in devices):
        return "enabled"
    return "disabled" if all(monitor_disabled(d) for d in devices) else "error"


def monitor_enabled(device: dict) -> bool:
    return device.get("status", "").upper() == "OK" and device.get("problem") in (None, 0)


def monitor_disabled(device: dict) -> bool:
    return device.get("problem") == 22

def build_driver_script(enable: bool, device_ids=None) -> str:
    cmdlet = "Enable-PnpDevice" if enable else "Disable-PnpDevice"
    select = ""
    if device_ids is not None:
        literals = ",".join("'" + v.replace("'", "''") + "'" for v in device_ids)
        select = f"$i=@({literals});$d=@($d|Where-Object {{$_.InstanceId -in $i}});if($d.Count -ne $i.Count){{exit 3}};"
    return (
        "$d=@(Get-PnpDevice -Class Monitor -PresentOnly -ErrorAction Stop);"
        + select +
        "if($d.Count -eq 0){exit 3};$f=0;"
        f"foreach($m in $d){{try{{{cmdlet} -InstanceId $m.InstanceId -Confirm:$false -ErrorAction Stop}}catch{{$f++}}}};"
        "if($f -gt 0){exit 2};exit 0"
    )


def change_monitor_devices(device_ids: list, enable: bool) -> None:
    if not device_ids:
        return
    check = monitor_enabled if enable else monitor_disabled
    devices = {d["instance_id"]: d for d in list_monitor_devices()}
    if all(v in devices and check(devices[v]) for v in device_ids):
        return
    code = run_elevated_powershell(build_driver_script(enable, device_ids))
    for attempt in range(5):
        devices = {d["instance_id"]: d for d in list_monitor_devices()}
        if code == 0 and all(v in devices and check(devices[v]) for v in device_ids):
            return
        if attempt < 4:
            time.sleep(0.3)
    label = "启用" if enable else "禁用"
    raise OSError(f"未能确认所有目标监视器已{label}（系统结果 {code}）。恢复记录已保留，请重试。")



def is_webview2_installed() -> bool:
    for hive, key_path in WEBVIEW2_REGISTRY_KEYS:
        try:
            with winreg.OpenKey(hive, key_path):
                return True
        except OSError:
            continue
    return False

def download_webview2_bootstrapper() -> str:
    tmp = tempfile.mktemp(suffix=".exe", prefix="MicrosoftEdgeWebview2Setup_")
    urllib.request.urlretrieve(WEBVIEW2_DOWNLOAD_URL, tmp)
    return tmp

def run_webview2_installer(bootstrapper_path: str) -> None:
    bat = tempfile.mktemp(suffix=".bat", prefix="VEX_webview2_")
    script = textwrap.dedent(f"""
        @echo off
        chcp 65001 >nul
        echo ============================================================
        echo  VEX - WebView2 安装
        echo ============================================================
        echo.
        echo  即将安装 Microsoft WebView2 运行时。
        echo  完成后将继续启动 VEX。
        echo.
        echo  安装期间请勿关闭此窗口。
        echo ============================================================
        echo.
        "{bootstrapper_path}" /install
        echo.
        echo ============================================================
        echo  安装程序已结束；请按任意键继续启动 VEX。
        echo  如果安装未成功，请重新安装 WebView2。
        echo ============================================================
        echo.
        pause >nul
    """).strip()
    with open(bat, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(script)
    subprocess.Popen(["cmd.exe", "/c", bat], creationflags=subprocess.CREATE_NEW_CONSOLE).wait()
    try:
        os.remove(bat)
    except Exception:
        pass

def prompt_webview2() -> None:
    root = tk.Tk()
    root.withdraw()

    dialog = tk.Toplevel(root)
    dialog.title("VEX — 需要 WebView2 运行时")
    dialog.resizable(False, False)
    dialog.configure(bg="#111111")
    dialog.attributes("-topmost", True)
    dialog.update_idletasks()
    w, h = 420, 210
    dialog.geometry(f"{w}x{h}+{(dialog.winfo_screenwidth()-w)//2}+{(dialog.winfo_screenheight()-h)//2}")

    choice = {"value": None}

    tk.Label(dialog, text="未检测到 WebView2 运行时",
             bg="#111111", fg="#ff4655", font=("Microsoft YaHei UI", 13, "bold")).pack(pady=(22, 6))
    tk.Label(dialog,
             text="VEX 需要 Microsoft WebView2 运行时。\n当前电脑尚未安装，请选择安装方式。",
             bg="#111111", fg="#cccccc", font=("Microsoft YaHei UI", 9), justify="center").pack(pady=(0, 18))

    btn_frame = tk.Frame(dialog, bg="#111111")
    btn_frame.pack()

    btn_style = {"font": ("Microsoft YaHei UI", 9, "bold"), "relief": "flat", "cursor": "hand2", "padx": 14, "pady": 7, "bd": 0}

    def on_auto():   choice["value"] = "auto";   dialog.destroy()
    def on_manual(): choice["value"] = "manual"; dialog.destroy()
    def on_cancel(): choice["value"] = "cancel"; dialog.destroy()

    def make_btn(text, bg, fg, bg_h, fg_h, cmd, col):
        b = tk.Button(btn_frame, text=text, bg=bg, fg=fg,
                      activebackground=bg_h, activeforeground=fg_h, command=cmd, **btn_style)
        b.grid(row=0, column=col, padx=6)
        b.bind("<Enter>", lambda e: b.config(bg=bg_h, fg=fg_h))
        b.bind("<Leave>", lambda e: b.config(bg=bg,   fg=fg))

    make_btn("自动安装",   "#ff4655", "#ffffff", "#cc2233", "#ffffff", on_auto,   0)
    make_btn("手动安装", "#2a2a2a", "#cccccc", "#3d3d3d", "#ffffff", on_manual, 1)
    make_btn("取消",         "#1a1a1a", "#777777", "#2a2a2a", "#aaaaaa", on_cancel, 2)

    dialog.protocol("WM_DELETE_WINDOW", on_cancel)
    dialog.wait_window()
    root.destroy()

    if choice["value"] in ("cancel", None):
        raise SystemExit(0)

    if choice["value"] == "manual":
        webbrowser.open(WEBVIEW2_DOWNLOAD_URL)
        raise SystemExit(0)

    if choice["value"] == "auto":
        root2 = tk.Tk()
        root2.withdraw()
        info = tk.Toplevel(root2)
        info.title("VEX — 正在下载 WebView2")
        info.resizable(False, False)
        info.configure(bg="#111111")
        info.attributes("-topmost", True)
        iw, ih = 340, 90
        info.geometry(f"{iw}x{ih}+{(info.winfo_screenwidth()-iw)//2}+{(info.winfo_screenheight()-ih)//2}")
        tk.Label(info, text="正在下载 WebView2 安装程序…",
                 bg="#111111", fg="#cccccc", font=("Microsoft YaHei UI", 10)).pack(expand=True)
        info.update()
        try:
            bootstrapper = download_webview2_bootstrapper()
        finally:
            info.destroy()
            root2.destroy()
        run_webview2_installer(bootstrapper)
        try:
            os.remove(bootstrapper)
        except Exception:
            pass

def ensure_webview2() -> None:
    if not is_webview2_installed():
        prompt_webview2()



def black_bars_needed() -> bool:
    try:
        base_key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\ControlSet001\Control\GraphicsDrivers\Configuration"
        )
        found_any = False
        needs_fix = False
        i = 0
        while True:
            try:
                config_name = winreg.EnumKey(base_key, i)
                try:
                    sub_key = winreg.OpenKey(base_key, config_name + r"\00\00")
                    try:
                        val, _ = winreg.QueryValueEx(sub_key, "Scaling")
                        found_any = True
                        if val != 3:
                            needs_fix = True
                    except FileNotFoundError:
                        pass
                    winreg.CloseKey(sub_key)
                except OSError:
                    pass
                i += 1
            except OSError:
                break
        winreg.CloseKey(base_key)
        return found_any and needs_fix
    except Exception:
        return False


def load_local_html() -> str:
    """Keep the authorized Chinese interface bundled with this build."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "index.html"), encoding="utf-8") as source:
        content = source.read()
    if not content.strip():
        raise ValueError("内置中文界面为空，请重新解压完整程序。")
    return content


def error_message(exc: Exception) -> str:
    text = str(exc).strip()
    if any("\u4e00" <= char <= "\u9fff" for char in text):
        return text
    return f"操作未完成。系统详细信息：{text or type(exc).__name__}"


def show_fatal_error(message: str) -> None:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    messagebox.showerror("VEX", message, parent=root)
    root.destroy()


class ResolutionHotkey:
    def __init__(self, callback, binding=None):
        self.callback = callback
        self.binding = validate_hotkey(DEFAULT_HOTKEY if binding is None else binding)
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.active = False
        self.error = ""
        self.thread = None
        self.busy = threading.Lock()

    def start(self):
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        self.ready.wait(2)

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(2)

    def _invoke(self):
        try:
            if not self.stop.is_set():
                self.callback()
        finally:
            self.busy.release()

    def _loop(self):
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.UnregisterHotKey.restype = wintypes.BOOL
        user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
        user32.PeekMessageW.restype = wintypes.BOOL
        try:
            self.active = bool(user32.RegisterHotKey(None, 1, 0x4000 | self.binding["modifiers"], HOTKEY_KEYS[self.binding["key"]]))
            if not self.active:
                self.error = f"快捷键 {hotkey_label(self.binding)} 不可用，可能已被其他程序或 Windows 占用。请选择其他快捷键，或关闭冲突程序。"
            self.ready.set()
            msg = wintypes.MSG()
            while self.active and not self.stop.wait(0.04):
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    if msg.message == 0x0312 and msg.wParam == 1 and self.busy.acquire(blocking=False):
                        threading.Thread(target=self._invoke, daemon=True).start()
        except Exception as exc:
            self.error = f"无法注册快捷键 {hotkey_label(self.binding)}。详细信息：{exc}"
        finally:
            self.ready.set()
            if self.active:
                user32.UnregisterHotKey(None, 1)
            self.active = False


class Api:
    def __init__(self):
        self._window  = None
        self._lock    = threading.RLock()
        self._stop    = threading.Event()
        self._watcher = None
        self._seen    = False
        self._hotkey = None
        self._hotkey_lock = threading.Lock()
        self._closing = False
        self._confirmation_timer = None

    def start_hotkey(self):
        with self._hotkey_lock:
            if not self._closing and self._hotkey is None and load_settings()["hotkey_enabled"]:
                self._hotkey = ResolutionHotkey(self.toggle_resolution, load_settings()["hotkey"])
                self._hotkey.start()

    def shutdown(self):
        self._closing = True
        self._cancel_mode_confirmation()
        self._stop_watcher()
        with self._hotkey_lock:
            if self._hotkey:
                self._hotkey.close()
                self._hotkey = None

    def get_hotkey_status(self):
        hotkey = self._hotkey
        settings = load_settings()
        return {
            "enabled": settings["hotkey_enabled"],
            "binding": settings["hotkey"],
            "label": hotkey_label(settings["hotkey"]),
            "active": bool(hotkey and hotkey.active),
            "message": hotkey.error if hotkey else "",
        }

    def set_hotkey_enabled(self, enabled):
        return self._configure_hotkey(enabled=bool(enabled))

    def set_hotkey(self, binding):
        try:
            return self._configure_hotkey(binding=validate_hotkey(binding))
        except ValueError as exc:
            return {"success": False, "message": error_message(exc)}

    def _configure_hotkey(self, binding=None, enabled=None):
        with self._hotkey_lock:
            candidate = None
            try:
                with self._lock:
                    if self._closing:
                        raise ValueError("VEX 正在关闭。")
                    settings = load_settings()
                    if binding is not None:
                        settings["hotkey"] = binding
                    if enabled is not None:
                        settings["hotkey_enabled"] = enabled
                    old = self._hotkey
                    reuse = bool(old and old.active and old.binding == settings["hotkey"])
                    if settings["hotkey_enabled"] and not reuse:
                        candidate = ResolutionHotkey(self.toggle_resolution, settings["hotkey"])
                        candidate.start()
                        if not candidate.active:
                            raise ValueError(candidate.error or "无法注册此快捷键。")
                    save_settings(settings)
                    if not settings["hotkey_enabled"] or not reuse:
                        self._hotkey = candidate
                        if old:
                            old.close()
                return {"success": True, **self.get_hotkey_status()}
            except Exception as exc:
                if candidate:
                    candidate.close()
                return {"success": False, "message": error_message(exc)}

    def toggle_resolution(self):
        with self._lock:
            if self._closing:
                return {"success": False}
            try:
                current = get_display_resolution()
                original = load_display_state().get("original")
                if original and tuple(original) != current:
                    return self.restore_display()
                target = read_json_file("last_resolution.json", None)
                if not isinstance(target, str):
                    raise ValueError("使用快捷键之前，请先在 VEX 中应用一次拉伸分辨率。")
                parse_resolution(target)
                if original:
                    clear_display_state()
                    if not load_game_session():
                        self._stop_watcher()
                return self.apply_resolution(target)
            except Exception as exc:
                self._log(error_message(exc), "error")
                return {"success": False, "message": error_message(exc)}

    def _log(self, message: str, msg_type: str = "info") -> None:
        if self._window:
            try:
                log_to_ui(self._window, message, msg_type)
            except Exception:
                pass

    def _notify(self) -> None:
        if self._window:
            try:
                self._window.evaluate_js("void (window.refreshDisplay && window.refreshDisplay()); void (window.refreshGameMode && window.refreshGameMode());")
            except Exception:
                pass

    def _watching(self) -> bool:
        return self._watcher is not None and self._watcher.is_alive() and not self._stop.is_set()

    def _start_watcher(self) -> None:
        if self._watching():
            return
        stop = threading.Event()
        self._stop    = stop
        self._seen    = False
        self._watcher = threading.Thread(target=self._watch_loop, args=(stop,), daemon=True)
        self._watcher.start()

    def _stop_watcher(self) -> None:
        self._stop.set()
        self._watcher = None

    def _watch_loop(self, stop: threading.Event) -> None:
        misses = 0
        while not stop.wait(WATCH_INTERVAL):
            if is_valorant_running():
                self._seen = True
                misses = 0
                continue
            if not self._seen:
                continue
            misses += 1
            if misses < WATCH_MISSES_REQUIRED:
                continue
            if stop.is_set():
                return
            with self._lock:
                if stop.is_set():
                    return
                self._log("《无畏契约》已退出，正在恢复桌面…", "info")
                if load_game_session():
                    self.restore_game_mode()
                else:
                    self.restore_display()
                self._stop_watcher()
            return

    def _snapshot(self) -> dict:
        current = get_display_resolution()
        state   = load_display_state()
        session = load_game_session()
        original = session.get("original") or state.get("original")
        if original and tuple(original) == current and not session:
            clear_display_state()
            self._stop_watcher()
            original = None
        return {
            "current":       list(current),
            "original":      original,
            "watching":      self._watching(),
            "valorant_seen": self._seen,
            "auto_restore":  load_settings()["auto_restore"],
        }

    def close(self):
        if not self._window:
            return
        with self._lock:
            try:
                if load_game_session() and not self.restore_game_mode()["success"]:
                    self._log("桌面尚未完全恢复，窗口已保留。请点击“一键恢复桌面”重试。", "error")
                    return
            except Exception as exc:
                self._log(error_message(exc), "error")
                return
        try:
            snap = self._snapshot()
        except Exception:
            snap = {}
        if snap.get("original") and snap.get("watching"):
            cw, ch = snap["current"]
            ow, oh = snap["original"]
            message = (
                f"当前分辨率仍为 {cw}x{ch}。VEX 保持运行时，退出《无畏契约》后会自动恢复为 {ow}x{oh}。"
                "\n\n仍要关闭 VEX 吗？关闭后，你需要自行恢复分辨率。"
            )
            if not self._window.create_confirmation_dialog("VEX", message):
                return
        self.shutdown()
        self._window.destroy()

    def on_window_closing(self):
        with self._lock:
            try:
                if load_game_session():
                    return self.restore_game_mode()["success"]
            except Exception as exc:
                self._log(error_message(exc), "error")
                return False
        return True

    def minimize(self):
        if self._window:
            self._window.minimize()

    def open_url(self, url: str) -> None:
        webbrowser.open(url)

    def get_version(self) -> str:
        return CURRENT_VERSION

    def get_app_info(self) -> dict:
        return {"name": APP_NAME, "version": APP_VERSION, "upstream_version": CURRENT_VERSION}

    def open_data_folder(self) -> None:
        subprocess.Popen(["explorer", get_easysts_dir()])

    def get_display_state(self) -> dict:
        try:
            with self._lock:
                return self._snapshot()
        except Exception as e:
            return {"error": error_message(e)}

    def get_game_mode_state(self) -> dict:
        with self._lock:
            try:
                state = load_game_session()
                return {"active": bool(state), "phase": state.get("phase"),
                        "target": state.get("target"), "original": state.get("original"),
                        "monitor_count": len(state.get("restore_monitors", [])),
                        "confirmation_remaining": max(0, math.ceil(state.get("confirmation_deadline", 0) - time.time())),
                        "preferred": read_json_file("last_resolution.json", "1566x1080")}
            except Exception as exc:
                return {"active": True, "phase": "restore_needed", "error": error_message(exc)}

    def resume_game_mode(self) -> dict:
        with self._lock:
            state = self.get_game_mode_state()
            if state.get("active") and not state.get("error"):
                self._log("发现上次一键模式的恢复记录，可点击“一键恢复桌面”。", "info")
                pending = load_game_session().get('confirmation_deadline')
                if pending:
                    self._arm_mode_confirmation(pending)
                if load_settings()["auto_restore"] and is_valorant_running():
                    self._start_watcher()
                    self._seen = True
            return state

    def start_game_mode(self, resolution_str: str) -> dict:
        with self._lock:
            saved = False
            try:
                if self._closing:
                    raise ValueError("VEX 正在关闭。")
                width, height = parse_resolution(resolution_str)
                if load_game_session():
                    raise ValueError("一键模式已经开启或仍有待恢复的记录。请先点击“一键恢复桌面”。")
                current = get_display_resolution()
                devices = list_monitor_devices()
                if not devices:
                    raise ValueError("未检测到监视器，已停止一键操作。请重新检测设备。")
                if any(not monitor_enabled(d) and not monitor_disabled(d) for d in devices):
                    raise ValueError("有监视器状态异常，已停止一键操作。请先检查设备状态。")
                owned = [d["instance_id"] for d in devices if monitor_enabled(d)]
                if owned and is_valorant_running():
                    raise ValueError("请先退出《无畏契约》，再点击“一键开启拉伸”，完成后重新启动游戏。")
                original = load_display_state().get("original") or list(current)
                state = {"version": 1, "phase": "preparing", "original": original,
                         "target": [width, height], "restore_monitors": owned}
                save_game_session(state)
                saved = True
                self._log(f'正在检测 {width}x{height}；缺少时将自动创建 NVIDIA 自定义分辨率…', 'info')
                try:
                    created = ensure_resolution_available(width, height)
                except ElevationDenied:
                    raise DisplayError('未获得管理员权限，自定义分辨率创建已取消。')
                if created:
                    self._log('NVIDIA 自定义分辨率已创建并通过驱动测试。', 'success')
                self._log("正在禁用监视器；如出现 Windows 权限提示，请选择“是”…", "info")
                try:
                    change_monitor_devices(owned, False)
                except ElevationDenied:
                    clear_game_session()
                    saved = False
                    raise ValueError("管理员操作已取消，未切换分辨率。")
                self._log(f"监视器已准备好，正在应用 {width}x{height}…", "info")
                if get_display_resolution() != (width, height):
                    change_display_resolution(width, height)
                if get_display_resolution() != (width, height):
                    raise DisplayError("尚未确认目标分辨率已应用。")
                save_display_state({"original": original, "applied": [width, height]})
                write_json_file("last_resolution.json", f"{width}x{height}")
                state["phase"] = "active"
                if created:
                    state['confirmation_deadline'] = time.time() + MODE_CONFIRM_SECONDS
                save_game_session(state)
                if created:
                    self._arm_mode_confirmation(state['confirmation_deadline'])
                if load_settings()["auto_restore"]:
                    self._start_watcher()
                    self._seen = is_valorant_running()
                self._log(f"一键开启完成：监视器已禁用，分辨率为 {width}x{height}。" + ('请在 20 秒内确认画面正常，否则自动恢复。' if created else '现在可以启动游戏。'), "success")
                self._notify()
                return {"success": True, "created_mode": created}
            except Exception as exc:
                message = error_message(exc)
                self._log(message, "error")
                if saved:
                    self._log("开启未完成，正在撤回本次操作…", "info")
                    restored = self.restore_game_mode()
                    if not restored["success"]:
                        message += " 桌面尚未完全恢复，请点击“一键恢复桌面”重试。"
                self._notify()
                return {"success": False, "message": message}

    def restore_game_mode(self) -> dict:
        with self._lock:
            self._cancel_mode_confirmation()
            try:
                state = load_game_session()
                if not state:
                    return self.restore_display()
                state["phase"] = "restore_needed"
                save_game_session(state)
                self._stop_watcher()
                errors = []
                try:
                    self._log("正在重新启用本次禁用的监视器，请允许 Windows 管理员操作…", "info")
                    change_monitor_devices(state["restore_monitors"], True)
                except ElevationDenied:
                    errors.append("未获得管理员权限，监视器尚未恢复。")
                except Exception as exc:
                    errors.append(error_message(exc))
                # Enabling a monitor can reset its mode, so restore the resolution last.
                try:
                    original = tuple(state["original"])
                    if get_display_resolution() != original:
                        change_display_resolution(*original)
                    if get_display_resolution() != original:
                        raise DisplayError("尚未确认原分辨率已恢复。")
                except Exception as exc:
                    errors.append(error_message(exc))
                if errors:
                    raise ValueError(" ".join(errors) + " 恢复记录已保留，可点击“一键恢复桌面”重试。")
                clear_display_state()
                clear_game_session()
                self._log("桌面已恢复：原分辨率已还原，本次禁用的监视器已重新启用。", "success")
                self._notify()
                return {"success": True}
            except Exception as exc:
                message = error_message(exc)
                self._log(message, "error")
                self._notify()
                return {"success": False, "message": message}

    def _cancel_mode_confirmation(self):
        if self._confirmation_timer:
            self._confirmation_timer.cancel()
            self._confirmation_timer = None

    def _arm_mode_confirmation(self, deadline):
        self._cancel_mode_confirmation()
        self._confirmation_timer = threading.Timer(max(0, deadline - time.time()), self._mode_confirmation_timeout, args=(deadline,))
        self._confirmation_timer.daemon = True
        self._confirmation_timer.start()

    def _mode_confirmation_timeout(self, deadline):
        with self._lock:
            state = load_game_session()
            if state.get('confirmation_deadline') != deadline:
                return
            self._log('未确认新分辨率，正在自动恢复桌面…', 'info')
            # Recover a visible desktop before any administrator prompt for devices.
            try:
                change_display_resolution(*state['original'])
            except Exception as exc:
                self._log(error_message(exc), 'error')
            self.restore_game_mode()

    def confirm_game_mode(self):
        with self._lock:
            state = load_game_session()
            deadline = state.get('confirmation_deadline')
            if not deadline:
                return {'success': False, 'message': '没有等待确认的新分辨率。'}
            if time.time() >= deadline:
                self._mode_confirmation_timeout(deadline)
                return {'success': False, 'message': '确认已超时，正在恢复桌面。'}
            del state['confirmation_deadline']
            save_game_session(state)
            self._cancel_mode_confirmation()
            self._log('已确认画面正常，可以启动游戏。', 'success')
            self._notify()
            return {'success': True}

    def apply_resolution(self, resolution_str: str) -> dict:
        try:
            width, height = parse_resolution(resolution_str)
        except ValueError as e:
            self._log(error_message(e), "error")
            return {"success": False, "message": error_message(e)}

        with self._lock:
            try:
                current = get_display_resolution()
                if current == (width, height):
                    self._log(f"当前已是 {width}x{height}，无需切换。", "muted")
                    self._notify()
                    return {"success": True, "changed": False}

                state = load_display_state()
                session = load_game_session()
                if session:
                    state["original"] = session["original"]
                if state.get("original") and tuple(state["original"]) == current and not session:
                    state = {}
                previous_state = dict(state)
                newly_saved = not state.get("original")
                if newly_saved:
                    state = {"original": list(current)}
                state["applied"] = [width, height]
                state["at"]      = time.strftime("%Y-%m-%d %H:%M")
                save_display_state(state)

                try:
                    change_display_resolution(width, height)
                except DisplayError:
                    if newly_saved:
                        clear_display_state()
                    else:
                        save_display_state(previous_state)
                    raise

                ow, oh = state["original"]
                if (ow, oh) == (width, height):
                    clear_display_state()
                    if not session:
                        self._stop_watcher()
                    self._log(f"已恢复为 {width}x{height}。", "success")
                else:
                    try:
                        write_json_file("last_resolution.json", f"{width}x{height}")
                    except Exception as exc:
                        self._log(f"分辨率已应用，但无法保存快捷键的切换目标。详细信息：{exc}", "error")
                    self._log(f"已切换到 {width}x{height}，原分辨率 {ow}x{oh} 已保存。", "success")
                    if load_settings()["auto_restore"]:
                        self._start_watcher()
                        self._log("自动恢复已开启。请保持 VEX 运行，退出《无畏契约》后会恢复原分辨率。", "info")
            except DisplayError as e:
                self._log(error_message(e), "error")
                return {"success": False, "message": error_message(e)}
            except Exception as e:
                self._log(f"操作失败。详细信息：{e}", "error")
                return {"success": False, "message": error_message(e)}

        self._notify()
        return {"success": True, "changed": True}

    def restore_display(self) -> dict:
        with self._lock:
            try:
                original = load_display_state().get("original")
                if not original:
                    if not load_game_session():
                        self._stop_watcher()
                    self._log("没有已保存的原分辨率可供恢复。", "muted")
                    self._notify()
                    return {"success": True, "changed": False}

                ow, oh = original
                if get_display_resolution() != (ow, oh):
                    change_display_resolution(ow, oh)
                    self._log(f"已恢复为 {ow}x{oh}。", "success")
                else:
                    self._log("当前已是原分辨率。", "muted")
                clear_display_state()
                if not load_game_session():
                    self._stop_watcher()
            except DisplayError as e:
                self._log(error_message(e), "error")
                self._notify()
                return {"success": False, "message": error_message(e)}
            except Exception as e:
                self._log(f"操作失败。详细信息：{e}", "error")
                self._notify()
                return {"success": False, "message": error_message(e)}

        self._notify()
        return {"success": True, "changed": True}

    def dismiss_saved_display(self) -> dict:
        with self._lock:
            if load_game_session():
                return {"success": False, "message": "一键模式中不能清除恢复记录，请使用“一键恢复桌面”。"}
            clear_display_state()
            self._stop_watcher()
        self._log("已清除保存的原分辨率，当前分辨率保持不变。", "muted")
        self._notify()
        return {"success": True}

    def get_driver_status(self) -> str:
        return get_driver_status()

    def set_driver_enabled(self, enabled: bool) -> dict:
        with self._lock:
            if load_game_session():
                return {"success": False, "message": "请使用“一键恢复桌面”结束当前一键模式。", "status": get_driver_status()}
            return self._set_driver_enabled(enabled)

    def _set_driver_enabled(self, enabled: bool) -> dict:
        enable = bool(enabled)
        label  = "启用" if enable else "禁用"
        self._log(f"正在{label}监视器驱动，请在 Windows 权限提示中选择“是”…", "info")
        try:
            code = run_elevated_powershell(build_driver_script(enable))
        except ElevationDenied:
            self._log("未获得管理员权限，监视器驱动操作已取消。", "error")
            return {"success": False, "denied": True, "status": get_driver_status()}
        except Exception as e:
            self._log(f"操作失败。详细信息：{e}", "error")
            return {"success": False, "status": get_driver_status()}

        status = get_driver_status()
        if status == "not_found":
            self._log("未检测到监视器设备，无法确认操作结果。", "error")
            return {"success": False, "status": status}

        expected = "enabled" if enable else "disabled"
        if status != expected and code == 0:
            time.sleep(1.5)
            status = get_driver_status()

        if status == expected and code == 0:
            if enable:
                self._log("监视器驱动已重新启用。", "success")
            else:
                self._log("监视器驱动已禁用，现在可以启动《无畏契约》。", "success")
            return {"success": True, "status": status}

        self._log(f"无法{label}监视器驱动。", "error")
        return {"success": False, "status": status}

    def get_settings(self) -> dict:
        return load_settings()

    def set_auto_restore(self, enabled: bool) -> dict:
        enable   = bool(enabled)
        try:
            with self._lock:
                settings = load_settings()
                settings["auto_restore"] = enable
                save_settings(settings)
        except Exception as e:
            return {"success": False, "message": error_message(e)}

        with self._lock:
            if not enable:
                self._stop_watcher()
            elif load_display_state().get("original") or load_game_session():
                self._start_watcher()
        self._notify()
        return {"success": True, "enabled": enable}

    def get_presets(self) -> list:
        return load_presets()

    def save_preset(self, name: str, resolution: str) -> dict:
        try:
            width, height = parse_resolution(resolution)
        except ValueError as e:
            return {"success": False, "message": error_message(e)}
        value   = f"{width}x{height}"
        presets = load_presets()
        for p in presets:
            if p["name"] == value:
                p["resolution"] = value
                save_presets(presets)
                return {"success": True}
        presets.append({"name": value, "resolution": value})
        save_presets(presets)
        return {"success": True}

    def delete_preset(self, name: str) -> dict:
        save_presets([p for p in load_presets() if p["name"] != name])
        return {"success": True}

    def check_black_bars_needed(self) -> bool:
        return black_bars_needed()

    def fix_black_bars(self) -> dict:
        self._log("正在应用黑边修复，请在 Windows 权限提示中选择“是”…", "info")
        try:
            code = run_elevated_powershell(BLACK_BARS_SCRIPT)
        except ElevationDenied:
            self._log("未获得管理员权限，黑边修复已取消。", "error")
            return {"success": False, "denied": True}
        except Exception as e:
            self._log(f"操作失败。详细信息：{e}", "error")
            return {"success": False}

        if code == 0:
            self._log("黑边修复已应用，重启电脑后生效。", "success")
            return {"success": True}
        if code == 3:
            self._log("未找到显示缩放配置，此电脑不适用该修复。", "muted")
            return {"success": True}
        self._log("未能对所有显示配置应用黑边修复。", "error")
        return {"success": False}


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--create-nvidia-mode':
        try:
            if len(sys.argv) != 4:
                raise ValueError('无效的自定义分辨率参数。')
            width, height = parse_resolution(sys.argv[2] + 'x' + sys.argv[3])
            create_custom_resolution(primary_display_name(), width, height, current_refresh_rate())
            return 0
        except NvidiaError as exc:
            return abs(exc.code or 1)
        except Exception:
            return 1
    try:
        ensure_webview2()
    except Exception as exc:
        show_fatal_error("WebView2 运行时准备失败，请尝试手动安装。\n\n" + error_message(exc))
        return

    try:
        html_content = load_local_html()
    except Exception as exc:
        show_fatal_error(
            "VEX 无法读取内置中文界面，请重新解压或重新构建程序。\n\n"
            + error_message(exc)
        )
        return

    webview.settings['DRAG_REGION_DIRECT_TARGET_ONLY'] = True
    api    = Api()
    window = webview.create_window(
        title     = APP_NAME,
        html      = html_content,
        js_api    = api,
        width     = 800,
        height    = 620,
        resizable = False,
        frameless = True,
        easy_drag = False,
        text_select = True,
    )
    api._window = window
    window.events.closing += api.on_window_closing
    window.events.closed += api.shutdown
    api.start_hotkey()
    try:
        webview.start(localization={
            "global.ok": "确定", "global.cancel": "取消", "global.quit": "退出",
            "global.quitConfirmation": "确定要退出 VEX 吗？",
            "global.saveFile": "保存文件", "windows.fileFilter.allFiles": "所有文件",
            "windows.fileFilter.otherFiles": "其他文件类型",
        })
    except Exception as exc:
        show_fatal_error("VEX 启动失败。\n\n" + error_message(exc))
    finally:
        api.shutdown()


if __name__ == "__main__":
    sys.exit(main())
