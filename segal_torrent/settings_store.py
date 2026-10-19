from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path

from segal_torrent.paths import data_dir


def detect_language() -> str:
    try:
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        if (lang_id & 0x3FF) == 0x19:
            return "ru"
    except Exception:
        pass
    for key in ("LANG", "LANGUAGE"):
        value = os.environ.get(key, "")
        if value.lower().startswith("ru"):
            return "ru"
    return "en"


def detect_theme() -> str:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if int(value) == 1 else "dark"
    except Exception:
        return "dark"


def default_download_dir() -> str:
    downloads = Path.home() / "Downloads"
    if downloads.is_dir():
        return str(downloads)
    return str(Path.home())


class Settings:
    def __init__(self, folder: Path | None = None) -> None:
        self.folder = folder or data_dir()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / "settings.json"
        self.language = detect_language()
        self.theme = detect_theme()
        self.download_dir = default_download_dir()
        self.listen_port = 45682
        self.listen_host = "0.0.0.0"
        self.max_download_kb = 0
        self.max_upload_kb = 0
        self.active_downloads = 8
        self.start_immediately = True
        self.details_visible = True
        self.geometry = ""
        self.enable_dht = True
        self.enable_lsd = True
        self.enable_upnp = True
        self.enable_natpmp = True
        self.asked_default = False
        self.torrents: list[dict] = []
        self.load()

    def load(self) -> None:
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self.language = data.get("language", self.language)
        self.theme = data.get("theme", self.theme)
        self.download_dir = data.get("download_dir", self.download_dir)
        self.listen_port = int(data.get("listen_port", self.listen_port))
        self.listen_host = data.get("listen_host", self.listen_host)
        self.max_download_kb = int(data.get("max_download_kb", self.max_download_kb))
        self.max_upload_kb = int(data.get("max_upload_kb", self.max_upload_kb))
        self.active_downloads = int(data.get("active_downloads", self.active_downloads))
        self.start_immediately = bool(data.get("start_immediately", self.start_immediately))
        self.details_visible = bool(data.get("details_visible", self.details_visible))
        self.geometry = data.get("geometry", self.geometry) or ""
        self.enable_dht = bool(data.get("enable_dht", self.enable_dht))
        self.enable_lsd = bool(data.get("enable_lsd", self.enable_lsd))
        self.enable_upnp = bool(data.get("enable_upnp", self.enable_upnp))
        self.enable_natpmp = bool(data.get("enable_natpmp", self.enable_natpmp))
        self.asked_default = bool(data.get("asked_default", self.asked_default))
        torrents = data.get("torrents", [])
        self.torrents = torrents if isinstance(torrents, list) else []

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "theme": self.theme,
            "download_dir": self.download_dir,
            "listen_port": self.listen_port,
            "listen_host": self.listen_host,
            "max_download_kb": self.max_download_kb,
            "max_upload_kb": self.max_upload_kb,
            "active_downloads": self.active_downloads,
            "start_immediately": self.start_immediately,
            "details_visible": self.details_visible,
            "geometry": self.geometry,
            "enable_dht": self.enable_dht,
            "enable_lsd": self.enable_lsd,
            "enable_upnp": self.enable_upnp,
            "enable_natpmp": self.enable_natpmp,
            "asked_default": self.asked_default,
            "torrents": self.torrents,
        }

    def save(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        self.path.write_text(payload, encoding="utf-8")
