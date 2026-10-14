"""Private verified SQLite recovery copies with no-overwrite publication."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from researchassistant.platform_support.private_files import create_private_file, private_directory
from researchassistant.storage.database_lock import database_lock
from researchassistant.storage.sqlite_policy import connect_database
from researchassistant.storage.store_schema import (
    CURRENT_SCHEMA_VERSION,
    validate_recorded_database,
)

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackupPolicy:
    count: int = 3
    directory: Path | None = None

    def __post_init__(self) -> None:
        if type(self.count) is not int or self.count < 1:
            raise ValueError("Backup retention count must be at least one")


@dataclass(frozen=True)
class BackupRecord:
    path: Path
    schema_version: int
    created_at: str


def _policy(policy: BackupPolicy | None) -> BackupPolicy:
    if policy is not None:
        return policy
    return BackupPolicy(count=int(os.environ.get("RESEARCHASSISTANT_BACKUP_COUNT", "3")))


def _source_id(path: Path) -> str:
    return hashlib.sha256(os.fsencode(path.resolve())).hexdigest()


def _folder(path: Path, policy: BackupPolicy) -> Path:
    if policy.directory is not None:
        folder = policy.directory.expanduser().resolve()
        folder.mkdir(parents=True, exist_ok=True)
        return folder
    folder = path.with_name(f"{path.name}.backups")
    private_directory(folder)
    return folder


@contextmanager
def _read_only(path: Path) -> Iterator[sqlite3.Connection]:
    uri = f"file:{quote(path.as_posix(), safe='/')}?mode=ro"
    with closing(connect_database(uri, uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        yield conn


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _content_digest(conn: sqlite3.Connection) -> str:
    """Compare all SQLite schema and row contents inside a consistent snapshot."""
    digest = hashlib.sha256()
    for statement in conn.iterdump():
        encoded = statement.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def _verify(conn: sqlite3.Connection, version: int) -> None:
    if [row[0] for row in conn.execute("PRAGMA integrity_check")] != ["ok"]:
        raise sqlite3.DatabaseError("Recovery copy integrity verification failed")
    if validate_recorded_database(conn) != version:
        raise sqlite3.DatabaseError("Recovery copy schema version verification failed")


def _flush_file(path: Path) -> None:
    # Windows FlushFileBuffers requires a handle opened for writing.
    with path.open("rb+") as handle:
        os.fsync(handle.fileno())
        if sys.platform == "darwin":
            import fcntl

            fcntl.fcntl(handle.fileno(), fcntl.F_FULLFSYNC)


def _flush_directory(path: Path) -> None:
    # Windows fsync flushes the file via FlushFileBuffers; there is no portable
    # directory fsync. Native NTFS power-loss durability remains a release check.
    if sys.platform == "win32":
        return
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _publish(temporary: Path, destination: Path) -> None:
    """Hard-link publication is atomic and fails if any destination already exists."""
    os.link(temporary, destination)
    _flush_directory(destination.parent)
    temporary.unlink()
    _flush_directory(destination.parent)


def _remove_owned(path: Path, identity: tuple[int, int]) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if (info.st_dev, info.st_ino) == identity:
        path.unlink()


def _metadata_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.verified.json")


def create_upgrade_backup(
    source_path: Path,
    connection: sqlite3.Connection,
    version: int,
    *,
    policy: BackupPolicy | None = None,
) -> BackupRecord:
    """Called with the source process lock and a read transaction retained."""
    folder = _folder(source_path, _policy(policy))
    _flush_directory(folder.parent)
    created_at = datetime.now(UTC).isoformat()
    name = f"{source_path.name}.pre-v{version}-{uuid4()}.sqlite3"
    destination = folder / name
    temporary = folder / f".pending-{uuid4()}.sqlite3"
    metadata_temporary = folder / f".pending-{uuid4()}.json"
    owned: list[tuple[Path, tuple[int, int]]] = []
    try:
        fd = create_private_file(temporary)
        info = os.fstat(fd)
        owned.append((temporary, (info.st_dev, info.st_ino)))
        os.close(fd)
        before = _content_digest(connection)
        with closing(sqlite3.connect(temporary)) as target:
            connection.backup(target)
        with _read_only(temporary) as copied:
            _verify(copied, version)
            if _content_digest(copied) != before:
                raise sqlite3.DatabaseError("Recovery copy differs from the source snapshot")
        _flush_file(temporary)
        identity = source_path.stat()
        metadata = {
            "format": 1,
            "source_id": _source_id(source_path),
            "source_device": identity.st_dev,
            "source_inode": identity.st_ino,
            "schema_version": version,
            "target_schema_version": CURRENT_SCHEMA_VERSION,
            "created_at": created_at,
            "file_sha256": _file_digest(temporary),
            "content_sha256": before,
            "restore": "restore-backup into a new, non-existing database path",
        }
        fd = create_private_file(metadata_temporary)
        info = os.fstat(fd)
        owned.append((metadata_temporary, (info.st_dev, info.st_ino)))
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(metadata, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        _flush_file(metadata_temporary)
        _publish(temporary, destination)
        # The marker is published last; discovery never accepts unfinished copies.
        _publish(metadata_temporary, _metadata_path(destination))
        return BackupRecord(destination, version, created_at)
    finally:
        for path, identity in owned:
            _remove_owned(path, identity)


def _verified_record(path: Path) -> tuple[BackupRecord, dict[str, object]]:
    if path.is_symlink() or _metadata_path(path).is_symlink():
        raise ValueError("Recovery paths must be regular files")
    metadata = json.loads(_metadata_path(path).read_text(encoding="utf-8"))
    if metadata.get("format") != 1 or _file_digest(path) != metadata.get("file_sha256"):
        raise ValueError("Recovery copy does not match its verification record")
    version = metadata["schema_version"]
    if not isinstance(version, int) or not isinstance(metadata["created_at"], str):
        raise ValueError("Recovery metadata is invalid")
    with _read_only(path) as conn:
        _verify(conn, version)
        if _content_digest(conn) != metadata.get("content_sha256"):
            raise ValueError("Recovery contents do not match their verification record")
    return BackupRecord(path, version, metadata["created_at"]), metadata


def list_backups(db_path: str | Path, *, policy: BackupPolicy | None = None) -> list[BackupRecord]:
    path = Path(db_path).expanduser().resolve()
    selected = _policy(policy)
    folder = (
        selected.directory.expanduser().resolve()
        if selected.directory is not None
        else path.with_name(f"{path.name}.backups")
    )
    records: list[BackupRecord] = []
    for marker in folder.glob("*.sqlite3.verified.json"):
        backup = marker.with_name(marker.name.removesuffix(".verified.json"))
        try:
            record, metadata = _verified_record(backup)
            if metadata.get("source_id") == _source_id(path):
                records.append(record)
        except (OSError, ValueError, sqlite3.Error, KeyError, TypeError, AttributeError):
            continue  # An orphan or unverified copy is never a recovery point.
    return sorted(records, key=lambda record: (record.created_at, record.path.name), reverse=True)


def prune_backups(db_path: str | Path, *, policy: BackupPolicy | None = None) -> None:
    """Only call after a successful upgrade; never remove the final verified copy."""
    selected = _policy(policy)
    for record in list_backups(db_path, policy=selected)[selected.count :]:
        try:
            # Restore holds this same lock through publication. Never wait here:
            # an active restore may be acquiring another database's lock.
            with database_lock(record.path):
                # Remove the marker first so partial cleanup cannot advertise a copy.
                _metadata_path(record.path).unlink()
                record.path.unlink()
                _flush_directory(record.path.parent)
        except RuntimeError:
            _LOG.info("Recovery retention deferred while a backup is in use")
        except OSError:
            _LOG.warning("Recovery retention cleanup failed; successful upgrade retained")


def restore_backup(backup_path: str | Path, destination: str | Path) -> Path:
    backup = Path(backup_path).expanduser().resolve(strict=True)
    target = Path(destination).expanduser().absolute()
    if os.path.lexists(target) or target.resolve() == backup:
        raise FileExistsError("Restore requires a new, non-existing database path")
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".restore-{uuid4()}.sqlite3")
    created_identity: tuple[int, int] | None = None
    try:
        with database_lock(backup), database_lock(target):
            record, metadata = _verified_record(backup)
            fd = create_private_file(temporary)
            info = os.fstat(fd)
            created_identity = (info.st_dev, info.st_ino)
            os.close(fd)
            with _read_only(backup) as original, closing(sqlite3.connect(temporary)) as copied:
                original.backup(copied)
            with _read_only(temporary) as copied:
                _verify(copied, record.schema_version)
                if _content_digest(copied) != metadata["content_sha256"]:
                    raise ValueError("Restored database differs from the recovery copy")
            _flush_file(temporary)
            _publish(temporary, target)
        return target
    finally:
        if created_identity is not None:
            _remove_owned(temporary, created_identity)
