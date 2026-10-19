from __future__ import annotations

import hashlib
import os
import tempfile
import time
import unittest
import warnings
from pathlib import Path

import libtorrent as lt

from segal_torrent.engine import Engine
from segal_torrent.settings_store import Settings


def _torrent_for(folder: Path, dest: Path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        storage = lt.file_storage()
        lt.add_files(storage, str(folder))
        creator = lt.create_torrent(storage, 0, lt.create_torrent.v1_only)
        lt.set_piece_hashes(creator, str(folder.parent))
        creator.set_creator("SEGAL-TORRENT")
        creator.set_comment("transfer test")
        dest.write_bytes(lt.bencode(creator.generate()))


def _seed_session(save_path: Path, torrent_path: Path):
    settings = dict(lt.default_settings())
    settings.update(
        {
            "user_agent": "SEGAL-TORRENT/1.0.0",
            "listen_interfaces": "127.0.0.1:0",
            "enable_dht": False,
            "enable_lsd": False,
            "enable_upnp": False,
            "enable_natpmp": False,
            "upload_rate_limit": 160 * 1024,
            "unchoke_interval": 1,
            "optimistic_unchoke_interval": 1,
            "alert_mask": int(lt.alert_category.error | lt.alert_category.status),
        }
    )
    session = lt.session(settings)
    atp = lt.add_torrent_params()
    atp.ti = lt.torrent_info(str(torrent_path))
    atp.save_path = str(save_path)
    atp.flags = lt.torrent_flags.default_flags | lt.torrent_flags.seed_mode
    handle = session.add_torrent(atp)
    deadline = time.time() + 10
    while time.time() < deadline and not handle.status().is_seeding:
        session.pop_alerts()
        time.sleep(0.05)
    if not handle.status().is_seeding:
        raise RuntimeError(f"seed did not start: {handle.status().state} {handle.status().errc.message()}")
    return session, handle


class TransferTests(unittest.TestCase):
    def test_download_pause_resume_and_restart(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            payload = root / "Demo"
            payload.mkdir()
            blob = os.urandom(4 * 1024 * 1024)
            (payload / "clip.bin").write_bytes(blob)
            (payload / "readme.txt").write_text("SEGAL-TORRENT", encoding="utf-8")
            torrent_path = root / "demo.torrent"
            _torrent_for(payload, torrent_path)
            seed, _seed_handle = _seed_session(root, torrent_path)
            port = seed.listen_port()

            settings = Settings(root / "appdata")
            settings.listen_host = "127.0.0.1"
            settings.listen_port = 0
            settings.enable_dht = False
            settings.enable_lsd = False
            settings.enable_upnp = False
            settings.enable_natpmp = False
            settings.max_download_kb = 160
            settings.download_dir = str(root / "downloads")
            settings.save()

            engine = Engine(settings)
            engine.start()
            try:
                preview, err = engine.preview(str(torrent_path))
                self.assertEqual(err, "")
                self.assertIsNotNone(preview)
                self.assertEqual(preview.name, "Demo")
                self.assertEqual(len(preview.files), 2)

                ok, code, tid = engine.add_file(
                    str(torrent_path),
                    str(root / "downloads"),
                    {item.index for item in preview.files},
                    True,
                    False,
                )
                self.assertTrue(ok, code)
                again, duplicate, _same = engine.add_file(
                    str(torrent_path),
                    str(root / "downloads"),
                    None,
                    True,
                    False,
                )
                self.assertFalse(again)
                self.assertEqual(duplicate, "duplicate")

                bad, bad_code, _none = engine.add_file(str(root / "readme-missing"), str(root / "downloads"), None, True, False)
                self.assertFalse(bad)
                self.assertEqual(bad_code, "invalid_torrent")

                paused = False
                snapshot = 0.0
                deadline = time.time() + 90
                finished = False
                while time.time() < deadline:
                    seed.pop_alerts()
                    engine.pump()
                    engine.connect_peer(tid, "127.0.0.1", port)
                    row = engine.rows()[0]
                    if not paused and 0.02 < row.progress < 0.85:
                        engine.pause([tid])
                        paused = True
                        snapshot = engine.rows()[0].progress
                        time.sleep(1.0)
                        held = engine.rows()[0].progress
                        self.assertLess(abs(held - snapshot), 0.03)
                        self.assertTrue(engine.rows()[0].paused)
                        engine.resume([tid])
                    if row.progress >= 1 and row.status_key in ("seeding", "finished"):
                        finished = True
                        break
                    time.sleep(0.05)
                self.assertTrue(paused, "download finished before a pause could be observed")
                self.assertTrue(finished, f"download did not finish, last={engine.rows()[0]}")
                clip = root / "downloads" / "Demo" / "clip.bin"
                note = root / "downloads" / "Demo" / "readme.txt"
                expected = hashlib.sha256(blob).digest()
                matched = False
                flush_deadline = time.time() + 8
                while time.time() < flush_deadline:
                    if clip.is_file() and hashlib.sha256(clip.read_bytes()).digest() == expected:
                        matched = True
                        break
                    time.sleep(0.2)
                self.assertTrue(matched, "downloaded file does not match the source")
                self.assertEqual(note.read_text(encoding="utf-8"), "SEGAL-TORRENT")
                engine.shutdown()
                engine = Engine(settings)
                engine.start()
                deadline = time.time() + 20
                restored = False
                while time.time() < deadline:
                    engine.pump()
                    rows = engine.rows()
                    if rows and rows[0].progress >= 1 and rows[0].status_key in ("seeding", "finished"):
                        restored = True
                        break
                    time.sleep(0.1)
                self.assertTrue(restored, "resume data did not restore the finished torrent")
                engine.remove([engine.rows()[0].id], delete_files=True)
                self.assertEqual(engine.rows(), [])
                self.assertFalse((root / "downloads" / "Demo" / "clip.bin").exists())
            finally:
                engine.shutdown()
                seed.pause()


class InterfaceTests(unittest.TestCase):
    def test_window_themes_and_languages(self) -> None:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PySide6.QtWidgets import QApplication

        from segal_torrent.main_window import MainWindow

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            payload = root / "Demo"
            payload.mkdir()
            (payload / "note.txt").write_text("hello", encoding="utf-8")
            torrent_path = root / "demo.torrent"
            _torrent_for(payload, torrent_path)
            settings = Settings(root / "appdata")
            settings.listen_host = "127.0.0.1"
            settings.listen_port = 0
            settings.enable_dht = False
            settings.enable_lsd = False
            settings.enable_upnp = False
            settings.enable_natpmp = False
            settings.language = "en"
            settings.theme = "dark"
            settings.download_dir = str(root / "downloads")
            settings.save()
            app = QApplication.instance() or QApplication([])
            window = MainWindow(settings)
            try:
                window.resize(1120, 740)
                window.show()
                app.processEvents()
                shots = Path(__file__).resolve().parent / "shots"
                shots.mkdir(exist_ok=True)
                self._grab(window, shots / "dark-en.png")
                ok, code, _tid = window.engine.add_file(str(torrent_path), settings.download_dir, None, False, False)
                self.assertTrue(ok, code)
                window.refresh()
                window.view.selectRow(0)
                app.processEvents()
                self._grab(window, shots / "dark-en-list.png")
                window.set_theme("light")
                window.set_language("ru")
                window.refresh()
                app.processEvents()
                self._grab(window, shots / "light-ru.png")
                self.assertEqual(window.i18n.lang, "ru")
                self.assertEqual(window.theme.mode, "light")
                self.assertIn("Добавить", window.act_add.text())
                self.assertEqual(window.model.rowCount(), 1)
                self.assertGreater(window.table.grab().width(), 100)
                from segal_torrent.dialogs import AboutDialog, MagnetDialog, SettingsDialog

                AboutDialog(window.i18n, window)
                SettingsDialog(window.settings, window.i18n, window)
                MagnetDialog(settings.download_dir, True, window.i18n, parent=window)
                self.assertTrue(window.search.isVisible())
            finally:
                window.close()
                app.processEvents()

    def _grab(self, window, path: Path) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.instance().processEvents()
        pixmap = window.grab()
        self.assertFalse(pixmap.isNull())
        self.assertTrue(pixmap.save(str(path)))


if __name__ == "__main__":
    unittest.main()
