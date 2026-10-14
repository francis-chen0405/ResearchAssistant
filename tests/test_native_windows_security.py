"""Actual Windows APIs against isolated temp files and unique test-only vault targets."""

from __future__ import annotations

import ctypes
import os
import secrets
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

import pytest

from researchassistant.platform_support import windows_credentials
from researchassistant.platform_support.private_files import create_private_file, private_directory
from researchassistant.storage import database_recovery
from researchassistant.storage.store import init_db
from tests.test_native_storage_durability import _old_database
from tests.test_private_import_files import (
    _assert_native_windows_private_acl,
    _native_windows_acl_sddl,
)

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="requires actual Windows APIs")


def _filesystem(path: Path) -> str:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    volume_path = kernel.GetVolumePathNameW
    volume_path.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD)
    volume_path.restype = wintypes.BOOL
    information = kernel.GetVolumeInformationW
    information.argtypes = (
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPWSTR,
        wintypes.DWORD,
    )
    information.restype = wintypes.BOOL
    root = ctypes.create_unicode_buffer(32768)
    assert volume_path(str(path), root, len(root))
    filesystem = ctypes.create_unicode_buffer(256)
    assert information(root, None, 0, None, None, None, filesystem, len(filesystem))
    return filesystem.value


def test_native_ntfs_private_acl_survives_publication_and_restore(tmp_path: Path) -> None:
    assert _filesystem(tmp_path) == "NTFS"
    folder = private_directory(tmp_path / "privé 研究")
    _assert_native_windows_private_acl(_native_windows_acl_sddl(folder), directory=True)
    path = folder / "history.sqlite3"
    descriptor = create_private_file(path)
    os.close(descriptor)
    _old_database(path)
    init_db(path)
    backup = database_recovery.list_backups(path)[0].path
    restored = folder / "restored.sqlite3"
    database_recovery.restore_backup(backup, restored)
    for target in (path, backup, backup.with_name(backup.name + ".verified.json"), restored):
        _assert_native_windows_private_acl(_native_windows_acl_sddl(target), directory=False)
    _assert_native_windows_private_acl(_native_windows_acl_sddl(backup.parent), directory=True)


def test_native_windows_vault_persists_cross_process_and_cleans_unique_target() -> None:
    target = "ResearchAssistant.Smoke." + secrets.token_hex(12) + ".WindowsCi"
    secret = secrets.token_hex(24) + "-研究"
    assert windows_credentials.read(target) is None
    try:
        windows_credentials.write(target, secret)
        assert windows_credentials.read(target) == secret
        # Never send credentials in argv, output or the environment.
        code = (
            "import sys; from researchassistant.platform_support import windows_credentials as w; "
            "expected=sys.stdin.buffer.read().decode('utf-8'); "
            "assert w.read(sys.argv[1])==expected; print('matched')"
        )
        result = subprocess.run(
            [sys.executable, "-c", code, target],
            input=secret,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        assert result.returncode == 0, "isolated vault child failed (raw output withheld)"
        assert result.stdout.strip() == "matched"
        windows_credentials.write(target, secret + "-replacement")
        assert windows_credentials.read(target) == secret + "-replacement"
    finally:
        windows_credentials.delete(target)
    assert windows_credentials.read(target) is None


def test_native_windows_links_refuse_private_path_and_restore_publication(tmp_path: Path) -> None:
    from researchassistant.platform_support.private_files import (
        PrivateFileSecurityError,
        secure_private_path,
    )

    assert _filesystem(tmp_path) == "NTFS"
    target = tmp_path / "outside-owned-folder"
    target.mkdir()
    before_acl = _native_windows_acl_sddl(target)
    junction = tmp_path / "owned-junction"
    subprocess.run(
        ["cmd", "/d", "/c", "mklink", "/J", str(junction), str(target)],
        capture_output=True,
        check=True,
    )
    try:
        assert junction.is_junction()
        with pytest.raises(PrivateFileSecurityError):
            private_directory(junction)
        assert _native_windows_acl_sddl(target) == before_acl
    finally:
        junction.rmdir()  # Remove the test reparse entry, preserving its target.

    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_bytes(b"unchanged")
    link = tmp_path / "private-file-link"
    link.symlink_to(sentinel)
    with pytest.raises(PrivateFileSecurityError):
        secure_private_path(link)
    with pytest.raises(FileExistsError):
        create_private_file(link)
    pending = tmp_path / "pending"
    descriptor = create_private_file(pending)
    os.close(descriptor)
    with pytest.raises(FileExistsError):
        database_recovery._publish(pending, link)
    assert sentinel.read_bytes() == b"unchanged"
    assert pending.exists()
    source = tmp_path / "source.sqlite3"
    _old_database(source)
    init_db(source)
    backup = database_recovery.list_backups(source)[0].path
    with pytest.raises(FileExistsError):
        database_recovery.restore_backup(backup, link)
    assert sentinel.read_bytes() == b"unchanged"
