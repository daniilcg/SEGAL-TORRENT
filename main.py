from __future__ import annotations

import ctypes
import logging
import multiprocessing
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from segal_torrent.main_window import MainWindow
from segal_torrent.paths import asset, data_dir

SERVER_NAME = "segal.run.SEGAL-TORRENT"


def _configure_logging() -> None:
    folder = data_dir()
    logging.basicConfig(
        filename=folder / "segal-torrent.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        encoding="utf-8",
    )

    def _hook(exc_type, exc, tb):
        logging.exception("unhandled exception", exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook


def _send_to_running(arguments: list[str]) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if not socket.waitForConnected(300):
        return False
    payload = "\n".join(arguments).encode("utf-8")
    socket.write(payload)
    socket.flush()
    socket.waitForBytesWritten(1000)
    socket.disconnectFromServer()
    return True


def _listen(window: MainWindow) -> QLocalServer:
    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    server.listen(SERVER_NAME)

    def on_connection() -> None:
        sock = server.nextPendingConnection()
        if sock is None:
            return
        sock.waitForReadyRead(800)
        text = bytes(sock.readAll()).decode("utf-8", "replace")
        items = [line.strip() for line in text.splitlines() if line.strip()]
        if items:
            window.open_inputs(items)
        else:
            window.showNormal()
            window.raise_()
            window.activateWindow()
        sock.disconnectFromServer()

    server.newConnection.connect(on_connection)
    return server


def main() -> int:
    multiprocessing.freeze_support()
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("segal.run.SEGAL-TORRENT")
    except Exception:
        pass
    arguments = sys.argv[1:]
    app = QApplication(sys.argv)
    if _send_to_running(arguments):
        return 0
    _configure_logging()
    app.setApplicationName("SEGAL-TORRENT")
    app.setOrganizationName("Dan Segal")
    app.setOrganizationDomain("segal.run")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    icon = asset("icon.png")
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    try:
        window = MainWindow()
    except Exception as exc:
        logging.exception("failed to start")
        QMessageBox.critical(None, "SEGAL-TORRENT", str(exc))
        return 1
    server = _listen(window)
    window._instance_server = server
    if arguments:
        QTimer.singleShot(0, lambda: window.open_inputs(arguments))
    window.show()
    QTimer.singleShot(700, window.offer_default_app)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
