from __future__ import annotations

import logging
import shutil
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import libtorrent as lt

from segal_torrent.settings_store import Settings

log = logging.getLogger("segal_torrent")

# Peer id and user agent stay the libtorrent defaults. A custom id is rejected
# by a lot of uTorrent peers, which leaves the swarm stuck on "connecting".

# Added only to public torrents that already list a tracker. Dead announce
# URLs (for example openbittorrent) otherwise leave the swarm at zero peers.
PUBLIC_TRACKERS = (
    "https://tracker.opentrackr.org:443/announce",
    "https://opentracker.i2p.rocks:443/announce",
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://exodus.desync.com:6969/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://open.demonii.com:1337/announce",
)

_TRACKER_ERROR_KEYS = {
    "timed out": "tracker_timed_out",
    "connection timed out": "tracker_timed_out",
    "host unreachable": "tracker_unreachable",
    "network unreachable": "tracker_unreachable",
    "no such device or address": "tracker_unreachable",
    "connection refused": "tracker_refused",
}


@dataclass
class FileInfo:
    index: int
    path: str
    size: int
    progress: float = 0.0
    priority: int = 4


@dataclass
class TorrentPreview:
    name: str
    size: int
    comment: str
    creator: str
    info_hash: str
    files: list[FileInfo]


@dataclass
class TorrentRow:
    id: str
    name: str
    size: int
    progress: float
    status_key: str
    error: str
    down_rate: int
    up_rate: int
    eta: int
    peers: int
    seeds: int
    paused: bool
    sequential: bool


@dataclass
class TrackerInfo:
    url: str
    status_key: str
    seeds: int
    peers: int
    message: str


@dataclass
class PeerInfo:
    address: str
    client: str
    progress: float
    down_rate: int
    up_rate: int


@dataclass
class TorrentDetails:
    id: str
    name: str
    size: int
    selected: int
    progress: float
    status_key: str
    error: str
    save_path: str
    info_hash: str
    info_hash_v2: str
    pieces_have: int
    pieces_total: int
    piece_size: int
    downloaded: int
    uploaded: int
    ratio: float
    availability: float
    comment: str
    creator: str
    has_metadata: bool
    files: list[FileInfo] = field(default_factory=list)
    trackers: list[TrackerInfo] = field(default_factory=list)
    peers: list[PeerInfo] = field(default_factory=list)


@dataclass
class SessionStats:
    down_rate: int
    up_rate: int
    dht_nodes: int
    port: int
    listening: bool


def info_id(info_hashes) -> str:
    if not info_hashes.v1.is_all_zeros():
        return str(info_hashes.v1).lower()
    return str(info_hashes.v2).lower()


def _display_path(path: str) -> str:
    return str(path).replace("\\", "/")


def _file_storage(ti):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return ti.files()


def _is_pad(storage, index: int) -> bool:
    try:
        flags = int(storage.file_flags(index))
    except Exception:
        return False
    return bool(flags & int(lt.file_storage.flag_pad_file))


def _coerce_bytes(raw) -> bytes:
    if isinstance(raw, bytes):
        return raw
    if isinstance(raw, bytearray):
        return bytes(raw)
    if isinstance(raw, str):
        return raw.encode("latin-1")
    return bytes(bytearray(int(part) & 0xFF for part in raw))


class Engine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = None
        self.handles: dict[str, object] = {}
        self.records: dict[str, dict] = {}
        self.errors: dict[str, str] = {}
        self.notices: list[tuple[str, str]] = []
        self._saved: set[str] = set()
        self._last_resume = 0.0
        self._last_discover = 0.0
        self._next_announce: dict[str, float] = {}
        self.torrent_dir = settings.folder / "torrents"
        self.resume_dir = settings.folder / "resume"
        self.torrent_dir.mkdir(parents=True, exist_ok=True)
        self.resume_dir.mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        pack = dict(lt.default_settings())
        pack.update(self._network_settings())
        nodes = pack.get("dht_bootstrap_nodes") or ""
        extra = (
            "dht.libtorrent.org:25401,"
            "dht.transmissionbt.com:6881,"
            "router.utorrent.com:6881,"
            "router.bittorrent.com:6881,"
            "dht.aelitis.com:6881"
        )
        pack["dht_bootstrap_nodes"] = ",".join(part for part in (nodes, extra) if part)
        self.session = lt.session(pack)
        self._restore()

    def _network_settings(self) -> dict:
        port = int(self.settings.listen_port)
        host = self.settings.listen_host or "0.0.0.0"
        if host == "0.0.0.0":
            listen = f"0.0.0.0:{port},[::]:{port}"
        else:
            listen = f"{host}:{port}"
        mask = (
            lt.alert_category.status
            | lt.alert_category.error
            | lt.alert_category.storage
            | lt.alert_category.tracker
            | lt.alert_category.port_mapping
        )
        active = max(1, int(self.settings.active_downloads))
        return {
            "listen_interfaces": listen,
            "enable_dht": bool(self.settings.enable_dht),
            "enable_lsd": bool(self.settings.enable_lsd),
            "enable_upnp": bool(self.settings.enable_upnp),
            "enable_natpmp": bool(self.settings.enable_natpmp),
            "announce_to_all_tiers": True,
            "announce_to_all_trackers": True,
            "tracker_receive_timeout": 20,
            "dht_announce_interval": 90,
            "mixed_mode_algorithm": 0,
            "out_enc_policy": int(lt.enc_policy.pe_enabled),
            "in_enc_policy": int(lt.enc_policy.pe_enabled),
            "allowed_enc_level": int(lt.enc_level.pe_both),
            "prefer_rc4": True,
            "enable_outgoing_tcp": True,
            "enable_incoming_tcp": True,
            "enable_outgoing_utp": True,
            "enable_incoming_utp": True,
            "min_reconnect_time": 5,
            "max_failcount": 10,
            "peer_connect_timeout": 8,
            "connection_speed": 100,
            "torrent_connect_boost": 100,
            "listen_system_port_fallback": True,
            "connections_limit": 800,
            "active_downloads": active,
            "active_seeds": max(4, active),
            "active_limit": active + max(4, active),
            "download_rate_limit": max(0, int(self.settings.max_download_kb)) * 1024,
            "upload_rate_limit": max(0, int(self.settings.max_upload_kb)) * 1024,
            "alert_mask": int(mask),
            "unchoke_interval": 10,
        }

    def apply_runtime(self) -> None:
        if self.session is None:
            return
        settings = self._network_settings()
        self.session.apply_settings(settings)
        try:
            self.session.reopen_network_sockets()
        except Exception:
            log.exception("reopen sockets")

    def shutdown(self) -> None:
        if self.session is None:
            return
        try:
            self.session.pause()
        except Exception:
            log.exception("pause session")
        pending: list[str] = []
        for tid, handle in list(self.handles.items()):
            if not _valid(handle):
                continue
            try:
                handle.save_resume_data(lt.torrent_handle.save_info_dict)
                pending.append(tid)
            except Exception:
                log.exception("save resume %s", tid)
        self._saved.clear()
        deadline = time.time() + 5
        while pending and time.time() < deadline:
            self._drain_alerts()
            pending = [tid for tid in pending if tid not in self._saved]
            if pending:
                time.sleep(0.05)
        self._persist()
        self.handles.clear()
        self.session = None

    def pump(self) -> None:
        if self.session is None:
            return
        self._drain_alerts()
        now = time.time()
        if now - self._last_discover >= 8:
            self._last_discover = now
            self._discover_peers(now)
        if now - self._last_resume < 15:
            return
        self._last_resume = now
        for handle in self.handles.values():
            if not _valid(handle):
                continue
            try:
                if handle.need_save_resume_data():
                    handle.save_resume_data(lt.torrent_handle.save_info_dict)
            except Exception:
                log.exception("periodic resume")

    def pop_notices(self) -> list[tuple[str, str]]:
        items = self.notices
        self.notices = []
        return items

    def preview(self, path: str) -> tuple[TorrentPreview | None, str]:
        try:
            ti = lt.torrent_info(path)
        except Exception:
            log.info("invalid torrent preview: %s", path)
            return None, "invalid_torrent"
        storage = _file_storage(ti)
        files: list[FileInfo] = []
        for index in range(ti.num_files()):
            if _is_pad(storage, index):
                continue
            files.append(
                FileInfo(
                    index=index,
                    path=_display_path(storage.file_path(index)),
                    size=int(storage.file_size(index)),
                )
            )
        preview = TorrentPreview(
            name=ti.name() or Path(path).stem,
            size=int(ti.total_size()),
            comment=ti.comment() or "",
            creator=ti.creator() or "",
            info_hash=info_id(ti.info_hashes()),
            files=files,
        )
        return preview, ""

    def add_file(
        self,
        path: str,
        save_path: str,
        selected: set[int] | None,
        start: bool,
        sequential: bool,
    ) -> tuple[bool, str, str]:
        try:
            ti = lt.torrent_info(path)
        except Exception:
            log.info("invalid torrent file: %s", path)
            return False, "invalid_torrent", ""
        tid = info_id(ti.info_hashes())
        if tid in self.handles:
            return False, "duplicate", tid
        try:
            Path(save_path).mkdir(parents=True, exist_ok=True)
        except OSError:
            log.exception("mkdir %s", save_path)
            return False, "folder_missing", ""
        storage = _file_storage(ti)
        priorities = _priority_vector(storage, ti.num_files(), selected)
        if not any(priority > 0 for priority in priorities):
            return False, "no_files", ""
        dest = self.torrent_dir / f"{tid}.torrent"
        try:
            shutil.copyfile(path, dest)
        except OSError:
            dest.write_bytes(Path(path).read_bytes())
        record = {
            "id": tid,
            "name": ti.name() or Path(path).stem,
            "save_path": save_path,
            "paused": not start,
            "sequential": sequential,
            "magnet": "",
            "added": int(time.time()),
        }
        ok, err = self._add_handle(record, ti=ti, priorities=priorities)
        if not ok:
            dest.unlink(missing_ok=True)
            return False, err, ""
        return True, "", tid

    def add_magnet(self, uri: str, save_path: str, start: bool) -> tuple[bool, str, str]:
        uri = uri.strip()
        try:
            parsed = lt.parse_magnet_uri(uri)
            if parsed.info_hashes.v1.is_all_zeros() and parsed.info_hashes.v2.is_all_zeros():
                raise ValueError("missing hash")
        except Exception:
            log.info("invalid magnet")
            return False, "invalid_magnet", ""
        tid = info_id(parsed.info_hashes)
        if tid in self.handles:
            return False, "duplicate", tid
        try:
            Path(save_path).mkdir(parents=True, exist_ok=True)
        except OSError:
            return False, "folder_missing", ""
        record = {
            "id": tid,
            "name": parsed.name or tid[:12],
            "save_path": save_path,
            "paused": not start,
            "sequential": False,
            "magnet": uri,
            "added": int(time.time()),
        }
        ok, err = self._add_handle(record, magnet=parsed)
        if not ok:
            return False, err, ""
        return True, "", tid

    def pause(self, ids: list[str]) -> None:
        for tid in ids:
            handle = self.handles.get(tid)
            record = self.records.get(tid)
            if not handle or not record or not _valid(handle):
                continue
            try:
                handle.unset_flags(lt.torrent_flags.auto_managed)
                handle.pause()
            except Exception:
                log.exception("pause %s", tid)
            record["paused"] = True
        self._persist()

    def resume(self, ids: list[str]) -> None:
        for tid in ids:
            handle = self.handles.get(tid)
            record = self.records.get(tid)
            if not handle or not record or not _valid(handle):
                continue
            try:
                handle.clear_error()
                handle.set_flags(lt.torrent_flags.auto_managed)
                handle.resume()
            except Exception:
                log.exception("resume %s", tid)
            record["paused"] = False
            self.errors.pop(tid, None)
        self._persist()

    def set_sequential(self, tid: str, enabled: bool) -> None:
        handle = self.handles.get(tid)
        record = self.records.get(tid)
        if not handle or not record or not _valid(handle):
            return
        try:
            if enabled:
                handle.set_flags(lt.torrent_flags.sequential_download)
            else:
                handle.unset_flags(lt.torrent_flags.sequential_download)
        except Exception:
            log.exception("sequential %s", tid)
        record["sequential"] = enabled
        self._persist()

    def set_file_priority(self, tid: str, index: int, priority: int) -> None:
        self.set_priorities(tid, {index: priority})

    def set_priorities(self, tid: str, updates: dict[int, int]) -> None:
        handle = self.handles.get(tid)
        if not handle or not _valid(handle) or not handle.has_metadata():
            return
        try:
            current = [int(item) for item in handle.get_file_priorities()]
            for index, priority in updates.items():
                if 0 <= index < len(current):
                    current[index] = int(priority)
            handle.prioritize_files(current)
            handle.save_resume_data(lt.torrent_handle.save_info_dict)
        except Exception:
            log.exception("priorities %s", tid)

    def force_recheck(self, tid: str) -> None:
        handle = self.handles.get(tid)
        if handle and _valid(handle):
            handle.force_recheck()

    def force_reannounce(self, tid: str) -> None:
        handle = self.handles.get(tid)
        if handle and _valid(handle):
            try:
                handle.force_reannounce()
            except Exception:
                log.exception("reannounce %s", tid)

    def connect_peer(self, tid: str, host: str, port: int) -> None:
        handle = self.handles.get(tid)
        if handle and _valid(handle):
            handle.connect_peer((host, int(port)))

    def magnet_uri(self, tid: str) -> str:
        handle = self.handles.get(tid)
        record = self.records.get(tid)
        if handle and _valid(handle):
            try:
                if handle.has_metadata() or handle.status().has_metadata:
                    return lt.make_magnet_uri(handle)
            except Exception:
                log.exception("magnet uri %s", tid)
        if record:
            return record.get("magnet") or ""
        return ""

    def info_hash(self, tid: str) -> str:
        handle = self.handles.get(tid)
        if handle and _valid(handle):
            return info_id(handle.info_hashes())
        return tid

    def location(self, tid: str) -> Path | None:
        record = self.records.get(tid)
        if not record:
            return None
        save = Path(record["save_path"])
        handle = self.handles.get(tid)
        if not handle or not _valid(handle) or not handle.has_metadata():
            return save
        try:
            ti = handle.torrent_file()
            storage = _file_storage(ti)
            real = [index for index in range(ti.num_files()) if not _is_pad(storage, index)]
            if len(real) == 1:
                return save / storage.file_path(real[0])
            root = save / ti.name()
            return root if root.exists() else save
        except Exception:
            log.exception("location %s", tid)
            return save

    def remove(self, ids: list[str], delete_files: bool) -> None:
        for tid in ids:
            handle = self.handles.pop(tid, None)
            record = self.records.pop(tid, None)
            name = (record or {}).get("name") or tid
            if handle and _valid(handle) and self.session is not None:
                try:
                    option = lt.session.delete_files if delete_files else 0
                    self.session.remove_torrent(handle, option)
                except Exception:
                    log.exception("remove %s", tid)
                    self.notices.append(("delete_failed", name))
            resume = self.resume_dir / f"{tid}.fastresume"
            torrent = self.torrent_dir / f"{tid}.torrent"
            resume.unlink(missing_ok=True)
            torrent.unlink(missing_ok=True)
            self.errors.pop(tid, None)
            self._next_announce.pop(tid, None)
        self._persist()

    def rows(self) -> list[TorrentRow]:
        items: list[TorrentRow] = []
        for tid, record in self.records.items():
            handle = self.handles.get(tid)
            items.append(self._row(tid, record, handle))
        return items

    def details(self, tid: str) -> TorrentDetails | None:
        record = self.records.get(tid)
        if not record:
            return None
        handle = self.handles.get(tid)
        row = self._row(tid, record, handle)
        info_hash_v2 = ""
        pieces_total = 0
        piece_size = 0
        comment = ""
        creator = ""
        files: list[FileInfo] = []
        trackers: list[TrackerInfo] = []
        peers: list[PeerInfo] = []
        selected = row.size
        downloaded = 0
        uploaded = 0
        availability = -1.0
        has_metadata = False
        if handle and _valid(handle):
            status = _status(handle)
            downloaded = int(status.all_time_download)
            uploaded = int(status.all_time_upload)
            try:
                availability = float(status.distributed_copies)
            except Exception:
                availability = -1.0
            has_metadata = bool(status.has_metadata)
            selected = int(status.total_wanted) if has_metadata else 0
            hashes = handle.info_hashes()
            if not hashes.v2.is_all_zeros():
                info_hash_v2 = str(hashes.v2).lower()
            if has_metadata:
                try:
                    ti = handle.torrent_file()
                    storage = _file_storage(ti)
                    pieces_total = int(ti.num_pieces())
                    piece_size = int(ti.piece_length())
                    comment = ti.comment() or ""
                    creator = ti.creator() or ""
                    progress = list(handle.file_progress(lt.torrent_handle.piece_granularity))
                    priorities = [int(item) for item in handle.get_file_priorities()]
                    for index in range(ti.num_files()):
                        if _is_pad(storage, index):
                            continue
                        done = progress[index] if index < len(progress) else 0
                        size = int(storage.file_size(index))
                        ratio = (done / size) if size else 1.0
                        priority = priorities[index] if index < len(priorities) else 4
                        files.append(
                            FileInfo(
                                index=index,
                                path=_display_path(storage.file_path(index)),
                                size=size,
                                progress=max(0.0, min(1.0, ratio)),
                                priority=priority,
                            )
                        )
                except Exception:
                    log.exception("files %s", tid)
            try:
                trackers = _tracker_rows(handle.trackers())
            except Exception:
                log.exception("trackers %s", tid)
            try:
                peers = _peer_rows(handle.get_peer_info())
            except Exception:
                log.exception("peers %s", tid)
        ratio = (uploaded / downloaded) if downloaded else 0.0
        return TorrentDetails(
            id=tid,
            name=row.name,
            size=row.size,
            selected=selected,
            progress=row.progress,
            status_key=row.status_key,
            error=row.error,
            save_path=record.get("save_path", ""),
            info_hash=row.id,
            info_hash_v2=info_hash_v2,
            pieces_have=int(_status(handle).num_pieces) if handle and _valid(handle) else 0,
            pieces_total=pieces_total,
            piece_size=piece_size,
            downloaded=downloaded,
            uploaded=uploaded,
            ratio=ratio,
            availability=availability,
            comment=comment,
            creator=creator,
            has_metadata=has_metadata,
            files=files,
            trackers=trackers,
            peers=peers,
        )

    def stats(self) -> SessionStats:
        if self.session is None:
            return SessionStats(0, 0, 0, 0, False)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            status = self.session.status()
        return SessionStats(
            down_rate=int(status.payload_download_rate),
            up_rate=int(status.payload_upload_rate),
            dht_nodes=int(status.dht_nodes),
            port=int(self.session.listen_port()),
            listening=bool(self.session.is_listening()),
        )

    def _row(self, tid: str, record: dict, handle) -> TorrentRow:
        name = record.get("name") or tid[:12]
        if not handle or not _valid(handle):
            return TorrentRow(
                id=tid,
                name=name,
                size=0,
                progress=0.0,
                status_key="paused" if record.get("paused") else "error",
                error="",
                down_rate=0,
                up_rate=0,
                eta=-1,
                peers=0,
                seeds=0,
                paused=bool(record.get("paused")),
                sequential=bool(record.get("sequential")),
            )
        status = _status(handle)
        if status.name:
            name = status.name
        key, error = self._status_key(tid, record, status)
        size = int(status.total_wanted) if status.has_metadata else 0
        progress = float(status.progress or 0.0)
        if progress < 0:
            progress = 0.0
        if progress > 1:
            progress = 1.0
        down = int(status.download_payload_rate)
        up = int(status.upload_payload_rate)
        remaining = max(0, int(status.total_wanted) - int(status.total_wanted_done))
        if key in ("paused", "queued", "seeding", "finished", "error", "no_seeds"):
            eta = -1
        elif down > 0 and remaining > 0:
            eta = int(remaining / down)
        elif key in ("downloading", "checking", "metadata", "searching", "connecting"):
            eta = -2
        else:
            eta = -1
        return TorrentRow(
            id=tid,
            name=name,
            size=size,
            progress=progress,
            status_key=key,
            error=error,
            down_rate=down,
            up_rate=up,
            eta=eta,
            peers=int(status.num_peers),
            seeds=int(status.num_seeds),
            paused=bool(record.get("paused")),
            sequential=bool(status.sequential_download),
        )

    def _status_key(self, tid: str, record: dict, status) -> tuple[str, str]:
        errc = status.errc
        message = ""
        if int(errc.value()) != 0:
            message = errc.message()
        elif tid in self.errors and status.paused and not record.get("paused"):
            message = self.errors[tid]
        state = status.state
        if record.get("paused"):
            key = "paused"
        elif message and int(errc.value()) != 0:
            key = "error"
        elif state in (lt.torrent_status.checking_files, lt.torrent_status.checking_resume_data):
            key = "checking"
        elif (not status.has_metadata) or state == lt.torrent_status.downloading_metadata:
            key = "metadata"
        elif state == lt.torrent_status.downloading and status.paused:
            key = "queued"
        elif state == lt.torrent_status.downloading and int(status.num_peers) == 0 and int(status.list_peers) == 0:
            key = "searching"
        elif (
            state == lt.torrent_status.downloading
            and int(status.num_peers) == 0
            and int(status.list_seeds) == 0
            and int(status.num_complete) == 0
        ):
            key = "no_seeds"
        elif state == lt.torrent_status.downloading and int(status.num_peers) == 0:
            key = "connecting"
        elif state == lt.torrent_status.downloading:
            key = "downloading"
        elif state == lt.torrent_status.finished:
            key = "finished"
        elif state == lt.torrent_status.seeding or status.is_seeding:
            key = "seeding"
        elif message:
            key = "error"
        else:
            key = "downloading"
        if key != "error":
            message = ""
        return key, message

    def _add_handle(self, record: dict, ti=None, magnet=None, priorities: list[int] | None = None) -> tuple[bool, str]:
        if self.session is None:
            return False, "add_failed"
        tid = record["id"]
        atp = lt.add_torrent_params()
        if ti is not None:
            atp.ti = ti
        elif magnet is not None:
            atp.info_hashes = magnet.info_hashes
            atp.name = magnet.name or record["name"]
            try:
                atp.trackers = magnet.trackers
            except Exception:
                log.exception("copy magnet trackers")
        atp.save_path = record["save_path"]
        flags = lt.torrent_flags.default_flags | lt.torrent_flags.duplicate_is_error
        if record.get("paused"):
            flags &= ~lt.torrent_flags.auto_managed
        if record.get("sequential"):
            flags |= lt.torrent_flags.sequential_download
        atp.flags = flags
        if priorities is not None:
            atp.file_priorities = priorities
        try:
            handle = self.session.add_torrent(atp)
        except Exception:
            log.exception("add torrent %s", tid)
            return False, "add_failed"
        if not _valid(handle):
            return False, "add_failed"
        actual = info_id(handle.info_hashes())
        if actual != tid:
            record["id"] = actual
            tid = actual
        self.handles[tid] = handle
        self.records[tid] = record
        self._persist()
        self._kick(handle)
        return True, ""

    def _restore(self) -> None:
        for record in list(self.settings.torrents):
            if not isinstance(record, dict) or not record.get("id"):
                continue
            try:
                self._load_record(record, use_resume=True)
            except Exception:
                log.exception("restore %s", record.get("id"))
                try:
                    self._load_record(record, use_resume=False)
                except Exception:
                    log.exception("restore fallback %s", record.get("id"))

    def _load_record(self, record: dict, use_resume: bool) -> None:
        tid = str(record["id"])
        if tid in self.handles:
            return
        atp = None
        resume_path = self.resume_dir / f"{tid}.fastresume"
        if use_resume and resume_path.is_file():
            try:
                atp = lt.read_resume_data(resume_path.read_bytes())
            except Exception:
                log.exception("resume %s", tid)
                atp = None
        if atp is None:
            atp = lt.add_torrent_params()
        torrent_path = self.torrent_dir / f"{tid}.torrent"
        if torrent_path.is_file():
            try:
                atp.ti = lt.torrent_info(str(torrent_path))
            except Exception:
                log.exception("torrent file %s", tid)
        if atp.ti is None and record.get("magnet"):
            parsed = lt.parse_magnet_uri(record["magnet"])
            atp.info_hashes = parsed.info_hashes
            if not atp.name:
                atp.name = parsed.name or record.get("name") or tid[:12]
            try:
                if not list(atp.trackers or []):
                    atp.trackers = parsed.trackers
            except Exception:
                log.exception("restore trackers %s", tid)
        atp.save_path = record.get("save_path") or self.settings.download_dir
        flags = lt.torrent_flags.default_flags
        if record.get("paused"):
            flags &= ~lt.torrent_flags.auto_managed
        if record.get("sequential"):
            flags |= lt.torrent_flags.sequential_download
        atp.flags = flags
        handle = self.session.add_torrent(atp)
        actual = info_id(handle.info_hashes()) if _valid(handle) else tid
        stored = dict(record)
        stored["id"] = actual
        self.handles[actual] = handle
        self.records[actual] = stored
        self._kick(handle)

    def _persist(self) -> None:
        self.settings.torrents = list(self.records.values())
        self.settings.save()

    def _drain_alerts(self) -> None:
        if self.session is None:
            return
        try:
            alerts = self.session.pop_alerts()
        except Exception:
            log.exception("pop alerts")
            return
        for alert in alerts:
            self._on_alert(alert)

    def _on_alert(self, alert) -> None:
        if isinstance(alert, lt.save_resume_data_alert):
            self._write_resume(alert)
            return
        if isinstance(alert, lt.save_resume_data_failed_alert):
            log.warning("resume failed: %s", alert.message())
            return
        if isinstance(alert, lt.metadata_received_alert):
            self._on_metadata(alert.handle)
            return
        if isinstance(alert, lt.torrent_finished_alert):
            self._save_one(alert.handle)
            return
        if isinstance(alert, lt.tracker_error_alert):
            log.info("tracker: %s", alert.message())
            return
        if isinstance(alert, (lt.file_error_alert, lt.torrent_error_alert)):
            handle = getattr(alert, "handle", None)
            if handle and _valid(handle):
                tid = info_id(handle.info_hashes())
                self.errors[tid] = alert.message()
            return
        if isinstance(alert, lt.torrent_delete_failed_alert):
            name = ""
            handle = getattr(alert, "handle", None)
            if handle and _valid(handle):
                name = handle.name()
            self.notices.append(("delete_failed", name or alert.message()))

    def _discover_peers(self, now: float) -> None:
        dht_ready = False
        if self.settings.enable_dht and self.session is not None:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    dht_ready = int(self.session.status().dht_nodes) >= 4
            except Exception:
                dht_ready = False
        for tid, handle in list(self.handles.items()):
            if not _valid(handle):
                continue
            record = self.records.get(tid) or {}
            if record.get("paused"):
                continue
            try:
                status = _status(handle)
            except Exception:
                continue
            if status.paused or status.is_seeding:
                continue
            if int(status.num_peers) > 0:
                continue
            private = _is_private(handle)
            if not private and dht_ready:
                try:
                    handle.force_dht_announce()
                except Exception:
                    log.debug("dht announce %s", tid, exc_info=True)
            if now < self._next_announce.get(tid, 0):
                continue
            self._next_announce[tid] = now + 45
            if not private:
                _ensure_public_trackers(handle)
            try:
                handle.force_reannounce(0, -1, int(lt.torrent_handle.ignore_min_interval))
            except Exception:
                log.debug("reannounce %s", tid, exc_info=True)

    def _kick(self, handle) -> None:
        if not _valid(handle):
            return
        try:
            tid = info_id(handle.info_hashes())
        except Exception:
            tid = ""
        private = _is_private(handle)
        if not private:
            _ensure_public_trackers(handle)
            if self.settings.enable_dht:
                try:
                    handle.force_dht_announce()
                except Exception:
                    log.debug("dht announce %s", tid, exc_info=True)
        try:
            handle.force_reannounce(0, -1, int(lt.torrent_handle.ignore_min_interval))
        except Exception:
            log.debug("reannounce %s", tid, exc_info=True)
        if tid:
            self._next_announce[tid] = time.time() + 45

    def _on_metadata(self, handle) -> None:
        if not _valid(handle):
            return
        tid = info_id(handle.info_hashes())
        record = self.records.get(tid)
        if record is not None:
            try:
                record["name"] = handle.name() or record.get("name")
            except Exception:
                pass
            self._persist()
        self._write_metadata_torrent(handle, tid)
        self._save_one(handle)
        self._kick(handle)

    def _save_one(self, handle) -> None:
        if _valid(handle):
            try:
                handle.save_resume_data(lt.torrent_handle.save_info_dict)
            except Exception:
                log.exception("save one")

    def _write_resume(self, alert) -> None:
        handle = alert.handle
        if not _valid(handle):
            return
        tid = info_id(handle.info_hashes())
        try:
            data = _coerce_bytes(lt.write_resume_data_buf(alert.params))
            (self.resume_dir / f"{tid}.fastresume").write_bytes(data)
            self._saved.add(tid)
        except Exception:
            log.exception("write resume %s", tid)

    def _write_metadata_torrent(self, handle, tid: str) -> None:
        dest = self.torrent_dir / f"{tid}.torrent"
        if dest.is_file() and dest.stat().st_size > 0:
            return
        try:
            atp = lt.add_torrent_params()
            atp.ti = handle.torrent_file()
            dest.write_bytes(_coerce_bytes(lt.write_torrent_file_buf(atp)))
        except Exception:
            log.exception("write torrent %s", tid)


def _is_private(handle) -> bool:
    try:
        info = handle.torrent_file()
    except Exception:
        return False
    if info is None:
        return False
    try:
        return bool(info.priv())
    except Exception:
        return False


def _tracker_urls(handle) -> set[str]:
    found: set[str] = set()
    try:
        listed = handle.trackers() or []
    except Exception:
        return found
    for tracker in listed:
        url = tracker.get("url") if isinstance(tracker, dict) else getattr(tracker, "url", "")
        if url:
            found.add(str(url).strip().lower())
    return found


def _ensure_public_trackers(handle) -> None:
    if not _valid(handle):
        return
    try:
        info = handle.torrent_file()
    except Exception:
        return
    if info is None:
        return
    try:
        if info.priv():
            return
    except Exception:
        return
    existing = _tracker_urls(handle)
    if not existing:
        return
    for url in PUBLIC_TRACKERS:
        if url.lower() in existing:
            continue
        try:
            handle.add_tracker({"url": url, "tier": 1})
            existing.add(url.lower())
        except Exception:
            log.debug("add tracker %s", url, exc_info=True)


def _decode_error(last_error) -> str:
    if not isinstance(last_error, dict):
        return ""
    value = int(last_error.get("value") or 0)
    if value == 0:
        return ""
    category = str(last_error.get("category") or "")
    try:
        if category == "libtorrent":
            cat = lt.libtorrent_category()
        elif category == "generic":
            cat = lt.generic_category()
        else:
            cat = lt.system_category()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            text = str(lt.error_code(value, cat).message() or "")
    except Exception:
        text = ""
    return text


def _tracker_error_text(last_error) -> str:
    text = _decode_error(last_error)
    if not text:
        return ""
    return _TRACKER_ERROR_KEYS.get(text.strip().lower(), text)


def _valid(handle) -> bool:
    try:
        return bool(handle and handle.is_valid())
    except Exception:
        return False


def _status(handle):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return handle.status()


def _priority_vector(storage, count: int, selected: set[int] | None) -> list[int]:
    priorities: list[int] = []
    for index in range(count):
        if _is_pad(storage, index):
            priorities.append(0)
        elif selected is None or index in selected:
            priorities.append(4)
        else:
            priorities.append(0)
    return priorities


def _tracker_rows(trackers) -> list[TrackerInfo]:
    rows: list[TrackerInfo] = []
    for tracker in trackers or []:
        if not isinstance(tracker, dict):
            url = getattr(tracker, "url", "")
            tracker = {"url": url}
        url = str(tracker.get("url", ""))
        fails = int(tracker.get("fails") or 0)
        updating = bool(tracker.get("updating"))
        verified = bool(tracker.get("verified"))
        last_error = tracker.get("last_error") or {}
        err_value = int(last_error.get("value") or 0) if isinstance(last_error, dict) else 0
        message = str(tracker.get("message") or "")
        if updating:
            key = "updating"
        elif verified or (err_value == 0 and tracker.get("start_sent")):
            key = "working"
        elif fails > 0 or err_value not in (0,):
            key = "error"
        else:
            key = "waiting"
        if key == "error" and not message:
            message = _tracker_error_text(last_error)
            if not message:
                for endpoint in tracker.get("endpoints") or []:
                    if not isinstance(endpoint, dict):
                        continue
                    if endpoint.get("message"):
                        message = str(endpoint["message"])
                        break
                    message = _tracker_error_text(endpoint.get("last_error"))
                    if message:
                        break
        seeds = int(tracker.get("scrape_complete") if tracker.get("scrape_complete") is not None else -1)
        peers = int(tracker.get("scrape_incomplete") if tracker.get("scrape_incomplete") is not None else -1)
        rows.append(TrackerInfo(url=url, status_key=key, seeds=seeds, peers=peers, message=message))
    return rows


def _peer_rows(peers) -> list[PeerInfo]:
    rows: list[PeerInfo] = []
    for peer in peers or []:
        try:
            ip, port = peer.ip
            address = f"{ip}:{port}"
        except Exception:
            address = "?"
        client = peer.client
        if isinstance(client, bytes):
            client = client.decode("utf-8", "replace")
        client = str(client).strip("\x00 ")
        rows.append(
            PeerInfo(
                address=address,
                client=client,
                progress=float(peer.progress or 0.0),
                down_rate=int(peer.payload_down_speed),
                up_rate=int(peer.payload_up_speed),
            )
        )
    return rows
