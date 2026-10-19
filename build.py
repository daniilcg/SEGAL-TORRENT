"""Build SEGAL-TORRENT.exe."""

from __future__ import annotations

import os
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent


def main() -> None:
    PyInstaller.__main__.run(
        [
            str(ROOT / "main.py"),
            "--noconfirm",
            "--clean",
            "--windowed",
            "--onefile",
            "--name",
            "SEGAL-TORRENT",
            "--icon",
            str(ROOT / "assets" / "icon.ico"),
            "--version-file",
            str(ROOT / "version_info.txt"),
            "--add-data",
            f"{ROOT / 'assets'}{os.pathsep}assets",
            "--hidden-import",
            "libtorrent",
            "--collect-binaries",
            "libtorrent",
            "--exclude-module",
            "PySide6.QtWebEngine",
            "--exclude-module",
            "PySide6.QtWebEngineCore",
            "--exclude-module",
            "PySide6.QtWebEngineWidgets",
            "--exclude-module",
            "PySide6.QtPdf",
            "--exclude-module",
            "PySide6.QtPdfWidgets",
            "--exclude-module",
            "PySide6.Qt3DCore",
            "--exclude-module",
            "PySide6.Qt3DRender",
            "--exclude-module",
            "PySide6.QtQuick",
            "--exclude-module",
            "PySide6.QtQml",
            "--exclude-module",
            "PySide6.QtMultimedia",
            "--exclude-module",
            "PySide6.QtCharts",
            "--exclude-module",
            "PySide6.QtBluetooth",
        ]
    )


if __name__ == "__main__":
    main()
