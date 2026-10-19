from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home()
    path = root / "SEGAL-TORRENT"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / "assets"
    return Path(__file__).resolve().parent.parent / "assets"


def asset(name: str) -> Path:
    return resource_dir() / name
