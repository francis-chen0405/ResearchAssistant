from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace

import pytest

import researchassistant.platform_support.private_files as private_files_module
import researchassistant.storage.history_import as history_import_module
from researchassistant.platform_support.private_files import (
    PrivateFileSecurityError,
    create_private_file,
    private_directory,
    secure_private_path,
)
from tests.test_database_import_failures import _source_database


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode checks")
def test_private_directory_enforces_owner_only_and_rejects_symlink(tmp_path: Path) -> None:
    folder = tmp_path / "app-owned" / "imports"
    folder.mkdir(parents=True, mode=0o777)
    folder.chmod(0o755)

    assert private_directory(folder) == folder
    assert folder.stat().st_mode & 0o777 == 0o700

    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "linked-imports"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(PrivateFileSecurityError, match="real directory"):
        private_directory(link)
    assert target.stat().st_mode & 0o777 == 0o755


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode checks")
def test_create_private_file_uses_exclusive_mode_and_secure_helper(tmp_path: Path) -> None:
    path = tmp_path / "private.sqlite3"
    fd = create_private_file(path)
    try:
        assert os.fstat(fd).st_mode & 0o777 == 0o600
    finally:
        os.close(fd)

    path.chmod(0o644)
    assert secure_private_path(path) == path
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        create_private_file(path)


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode checks")
def test_failed_permission_setup_removes_only_created_inode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "created.sqlite3"

    def deny_fchmod(fd: int, mode: int) -> None:
        raise OSError("permission setup failed")

    monkeypatch.setattr("researchassistant.platform_support.private_files.os.fchmod", deny_fchmod)
    with pytest.raises(OSError, match="permission setup failed"):
        create_private_file(path)
    assert not path.exists()

    collision = tmp_path / "occupied.sqlite3"
    collision.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        create_private_file(collision)
    assert collision.read_bytes() == b"keep"


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode checks")
def test_import_copy_is_private_without_changing_selected_directory(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    _source_database(source)
    destination_dir = tmp_path / "selected-imports"
    destination_dir.mkdir(mode=0o755)
    destination_dir.chmod(0o755)

    result = history_import_module.import_history(source, destination_dir=destination_dir)

    imported = Path(result.db_path)
    assert imported.stat().st_mode & 0o777 == 0o600
    assert destination_dir.stat().st_mode & 0o777 == 0o755


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode checks")
def test_default_import_directory_is_restricted_even_if_it_already_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.sqlite3"
    _source_database(source)
    app_data = tmp_path / "app-data"
    imports = app_data / "imports"
    imports.mkdir(parents=True, mode=0o777)
    imports.chmod(0o755)
    monkeypatch.setenv("RESEARCHASSISTANT_DATA_DIR", str(app_data))

    result = history_import_module.import_history(source)

    imported = Path(result.db_path)
    assert imports.stat().st_mode & 0o777 == 0o700
    assert imported.stat().st_mode & 0o777 == 0o600


def _mock_windows_acl_functions(
    monkeypatch: pytest.MonkeyPatch,
    *,
    apply_success: bool = True,
) -> tuple[list[str], list[tuple[str, int]], list[bool]]:
    sddl_values: list[str] = []
    applied: list[tuple[str, int]] = []
    freed: list[bool] = []

    def convert(sddl: str, revision: int, output: ctypes.c_void_p, size: None) -> int:
        sddl_values.append(sddl)
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.c_void_p(1234)
        return 1

    def set_security(path: str, flags: int, descriptor: ctypes.c_void_p) -> int:
        assert descriptor.value == 1234
        applied.append((path, flags))
        return int(apply_success)

    def local_free(descriptor: ctypes.c_void_p) -> ctypes.c_void_p:
        assert descriptor.value == 1234
        freed.append(True)
        return ctypes.c_void_p()

    monkeypatch.setattr(
        private_files_module,
        "_windows_security_functions",
        lambda: (convert, set_security, local_free),
    )
    monkeypatch.setattr(private_files_module, "_POSIX", False)
    monkeypatch.setattr(private_files_module.sys, "platform", "win32")
    return sddl_values, applied, freed


def test_windows_acl_helpers_apply_owner_system_dacl_and_free_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sddl_values, applied, freed = _mock_windows_acl_functions(monkeypatch)
    folder = tmp_path / "imports"
    file_path = tmp_path / "history.sqlite3"

    assert private_directory(folder) == folder
    fd = create_private_file(file_path)
    os.close(fd)
    assert secure_private_path(file_path) == file_path

    assert "D:P(A;OICI;FA;;;OW)(A;OICI;FA;;;SY)" in sddl_values
    assert sddl_values.count("D:P(A;;FA;;;OW)(A;;FA;;;SY)") == 2
    assert len(applied) == 3
    assert all(flags == 0x80000004 for _, flags in applied)
    assert len(freed) == 3


def test_windows_acl_failure_frees_descriptor_and_removes_created_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, freed = _mock_windows_acl_functions(monkeypatch, apply_success=False)
    path = tmp_path / "history.sqlite3"

    with pytest.raises(PrivateFileSecurityError, match="apply Windows private ACL"):
        create_private_file(path)

    assert freed == [True]
    assert not path.exists()


def test_windows_api_setup_uses_ctypes_compatible_signatures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    convert = ctypes.CFUNCTYPE(ctypes.c_int)(lambda: 1)
    set_security = ctypes.CFUNCTYPE(ctypes.c_int)(lambda: 1)
    local_free = ctypes.CFUNCTYPE(ctypes.c_void_p)(lambda: None)
    advapi32 = SimpleNamespace(
        ConvertStringSecurityDescriptorToSecurityDescriptorW=convert,
        SetFileSecurityW=set_security,
    )
    kernel32 = SimpleNamespace(LocalFree=local_free)

    def load_library(name: str, *, use_last_error: bool) -> SimpleNamespace:
        assert use_last_error
        return advapi32 if name == "advapi32" else kernel32

    monkeypatch.setattr(private_files_module.sys, "platform", "win32")
    monkeypatch.setattr(private_files_module.ctypes, "WinDLL", load_library, raising=False)

    configured_convert, configured_set, configured_free = (
        private_files_module._windows_security_functions()
    )

    assert configured_convert.argtypes[3] is ctypes.POINTER(ctypes.c_uint32)
    assert configured_convert.argtypes[3] is not None
    assert configured_set.argtypes == [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_void_p]
    assert configured_free.argtypes == [ctypes.c_void_p]


def test_windows_acl_setup_refuses_replaced_created_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "history.sqlite3"
    original_fstat = os.fstat
    replaced = False

    def replace_after_open(fd: int) -> os.stat_result:
        nonlocal replaced
        info = original_fstat(fd)
        if not replaced:
            path.unlink()
            path.write_bytes(b"replacement")
            replaced = True
        return info

    monkeypatch.setattr(private_files_module, "_POSIX", False)
    monkeypatch.setattr(private_files_module.os, "fstat", replace_after_open)

    def fail_acl(path: Path, *, directory: bool) -> None:
        pytest.fail("ACL must not target a replacement path")

    monkeypatch.setattr(
        private_files_module,
        "_set_windows_private_acl",
        fail_acl,
    )

    with pytest.raises(PrivateFileSecurityError, match="changed before ACL setup"):
        create_private_file(path)

    assert path.read_bytes() == b"replacement"


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows ACL verification")
def test_native_windows_acl_is_protected_and_contains_owner_and_system(
    tmp_path: Path,
) -> None:
    path = tmp_path / "native-private.sqlite3"
    fd = create_private_file(path)
    os.close(fd)

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_security = advapi32.GetFileSecurityW
    get_security.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    get_security.restype = wintypes.BOOL
    to_sddl = advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW
    to_sddl.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(wintypes.DWORD),
    ]
    to_sddl.restype = wintypes.BOOL
    local_free = kernel32.LocalFree
    local_free.argtypes = [ctypes.c_void_p]
    local_free.restype = ctypes.c_void_p
    security_information = 0x00000004
    descriptor_size = ctypes.c_uint32()
    result = get_security(str(path), security_information, None, 0, ctypes.byref(descriptor_size))
    assert not result
    descriptor = ctypes.create_string_buffer(descriptor_size.value)
    assert get_security(
        str(path),
        security_information,
        descriptor,
        descriptor_size,
        ctypes.byref(descriptor_size),
    )

    sddl = ctypes.c_wchar_p()
    assert to_sddl(descriptor, 1, security_information, ctypes.byref(sddl), None)
    try:
        rendered = sddl.value or ""
        assert "D:P" in rendered
        assert ";;;OW)" in rendered
        assert ";;;SY)" in rendered
        assert "OICI" not in rendered
    finally:
        local_free(sddl)
