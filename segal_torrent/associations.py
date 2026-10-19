from __future__ import annotations

import ctypes
import logging
import os
import sys
from ctypes import wintypes
from pathlib import Path

log = logging.getLogger("segal_torrent")

APP_KEY = "SEGAL-TORRENT"
TORRENT_ID = "SEGAL-TORRENT.torrent"
MAGNET_ID = "SEGAL-TORRENT.magnet"
_UI_CLSID = "{1968106d-f3b5-44cf-890e-116fcb9ecef1}"
_UI_IID = "{1f76a169-f994-40ac-8fc8-0959e8874710}"


class _GUID(ctypes.Structure):
    _fields_ = (
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    )


def app_path() -> str:
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve())
    built = Path(__file__).resolve().parents[1] / "dist" / "SEGAL-TORRENT.exe"
    if built.is_file():
        return str(built)
    return str(Path(sys.executable).resolve())


def _command() -> str:
    return f'"{app_path()}" "%1"'


def _write(root, path: str, values: dict[str, str]) -> None:
    import winreg

    with winreg.CreateKey(root, path) as key:
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def register() -> None:
    import winreg

    command = _command()
    icon = f"{app_path()},0"
    hive = winreg.HKEY_CURRENT_USER
    classes = "Software\\Classes"
    _write(hive, f"{classes}\\{TORRENT_ID}", {"": "Torrent"})
    _write(hive, f"{classes}\\{TORRENT_ID}\\DefaultIcon", {"": icon})
    _write(hive, f"{classes}\\{TORRENT_ID}\\shell\\open\\command", {"": command})
    _write(hive, f"{classes}\\.torrent\\OpenWithProgids", {TORRENT_ID: ""})
    _write(hive, f"{classes}\\{MAGNET_ID}", {"": "URL:Magnet link", "URL Protocol": ""})
    _write(hive, f"{classes}\\{MAGNET_ID}\\DefaultIcon", {"": icon})
    _write(hive, f"{classes}\\{MAGNET_ID}\\shell\\open\\command", {"": command})
    _write(hive, f"{classes}\\magnet\\OpenWithProgids", {MAGNET_ID: ""})
    _write(
        hive,
        "Software\\SEGAL-TORRENT\\Capabilities",
        {"ApplicationName": APP_KEY, "ApplicationDescription": "SEGAL-TORRENT"},
    )
    _write(
        hive,
        "Software\\SEGAL-TORRENT\\Capabilities\\FileAssociations",
        {".torrent": TORRENT_ID},
    )
    _write(
        hive,
        "Software\\SEGAL-TORRENT\\Capabilities\\UrlAssociations",
        {"magnet": MAGNET_ID},
    )
    _write(hive, "Software\\RegisteredApplications", {APP_KEY: r"Software\SEGAL-TORRENT\Capabilities"})
    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
    except Exception:
        log.debug("association notify", exc_info=True)


def is_torrent_default() -> bool:
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.torrent\UserChoice",
        ) as key:
            progid, _kind = winreg.QueryValueEx(key, "ProgId")
            return str(progid) == TORRENT_ID
    except OSError:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.torrent") as key:
            progid, _kind = winreg.QueryValueEx(key, "")
            return str(progid) == TORRENT_ID
    except OSError:
        return False


def _guid(text: str) -> _GUID:
    value = _GUID()
    if ctypes.windll.ole32.CLSIDFromString(text, ctypes.byref(value)) != 0:
        raise OSError(text)
    return value


def _launch_association_ui() -> bool:
    ole32 = ctypes.windll.ole32
    ole32.CoInitialize(None)
    clsid = _guid(_UI_CLSID)
    iid = _guid(_UI_IID)
    unknown = ctypes.c_void_p()
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(_GUID),
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(_GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = ctypes.HRESULT
    result = ole32.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(unknown))
    if result != 0 or not unknown.value:
        return False
    table = ctypes.cast(unknown, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))
    launch = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.c_wchar_p)(table[0][3])
    opened = launch(unknown, APP_KEY) == 0
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(table[0][2])
    release(unknown)
    return opened


def open_default_ui() -> None:
    try:
        if _launch_association_ui():
            return
    except Exception:
        log.exception("association ui")
    os.startfile("ms-settings:defaultapps?registeredAppUser=SEGAL-TORRENT")
