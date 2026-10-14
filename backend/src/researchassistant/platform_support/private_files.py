"""Helpers for private, application-created files and directories.

POSIX paths use owner-only mode bits and ownership checks. Windows paths use a
protected DACL granting full access to the object owner (``OW``) and SYSTEM
(``SY``); directories propagate those owner/SYSTEM ACEs to descendants.
"""

from __future__ import annotations

import ctypes
import os
import stat
import sys
from pathlib import Path
from typing import Any

_POSIX = os.name == "posix"


class PrivateFileSecurityError(PermissionError):
    """Raised when private file permissions cannot be established safely."""


def _windows_security_functions() -> tuple[Any, Any, Any]:
    """Load configured Win32 security functions only on Windows."""
    if sys.platform != "win32":
        raise PrivateFileSecurityError("Windows ACL operations are unavailable on this platform")
    try:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (AttributeError, OSError) as exc:
        raise PrivateFileSecurityError("Could not load Windows security APIs") from exc

    convert = advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    convert.restype = ctypes.c_int
    set_security = advapi32.SetFileSecurityW
    set_security.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_void_p]
    set_security.restype = ctypes.c_int
    local_free = kernel32.LocalFree
    local_free.argtypes = [ctypes.c_void_p]
    local_free.restype = ctypes.c_void_p
    return convert, set_security, local_free


def _set_windows_private_acl(path: Path, *, directory: bool) -> None:
    """Apply an owner/SYSTEM-only protected DACL and free its descriptor."""
    convert, set_security, local_free = _windows_security_functions()
    inheritance = "OICI" if directory else ""
    sddl = f"D:P(A;{inheritance};FA;;;OW)(A;{inheritance};FA;;;SY)"
    descriptor = ctypes.c_void_p()
    if not convert(sddl, 1, ctypes.byref(descriptor), None):
        code = _windows_last_error()
        raise PrivateFileSecurityError(f"Could not create Windows private ACL (error {code})")
    try:
        # DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION
        if not set_security(str(path), 0x00000004 | 0x80000000, descriptor):
            code = _windows_last_error()
            raise PrivateFileSecurityError(f"Could not apply Windows private ACL (error {code})")
    finally:
        if descriptor.value:
            result = local_free(descriptor)
            if result:
                raise PrivateFileSecurityError("Could not release Windows ACL descriptor")


def _windows_last_error() -> int:
    """Return the native error when available, including in platform-mocked tests."""
    get_last_error = getattr(ctypes, "get_last_error", None)
    return int(get_last_error()) if get_last_error is not None else 0


def private_directory(path: Path) -> Path:
    """Create or secure an explicitly application-owned private directory.

    Callers must only pass application-owned paths. Caller-selected folders must
    not be passed here because existing directory permissions are user policy.
    """
    path = Path(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise PrivateFileSecurityError(f"Private directory is not a real directory: {path}")
    if _POSIX:
        if info.st_uid != os.geteuid():
            raise PrivateFileSecurityError(f"Private directory is not owned by this user: {path}")
        os.chmod(path, 0o700, follow_symlinks=False)
        secured = path.lstat()
        if (
            not stat.S_ISDIR(secured.st_mode)
            or secured.st_uid != os.geteuid()
            or (info.st_dev, info.st_ino) != (secured.st_dev, secured.st_ino)
        ):
            raise PrivateFileSecurityError(f"Private directory changed during setup: {path}")
        if stat.S_IMODE(secured.st_mode) != 0o700:
            raise PrivateFileSecurityError(f"Could not secure private directory: {path}")
    else:
        if path.is_symlink():
            raise PrivateFileSecurityError(f"Private directory must not be a symlink: {path}")
        _set_windows_private_acl(path, directory=True)
    return path


def secure_private_path(path: Path) -> Path:
    """Set and verify owner-only access on an owned, regular file."""
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise PrivateFileSecurityError(f"Private file is not a regular file: {path}")
    if path.is_symlink():
        raise PrivateFileSecurityError(f"Private file must not be a symlink: {path}")
    if _POSIX:
        if info.st_uid != os.geteuid():
            raise PrivateFileSecurityError(f"Private file is not owned by this user: {path}")
        os.chmod(path, 0o600, follow_symlinks=False)
        secured = path.lstat()
        if (
            not stat.S_ISREG(secured.st_mode)
            or secured.st_uid != os.geteuid()
            or stat.S_IMODE(secured.st_mode) != 0o600
            or (info.st_dev, info.st_ino) != (secured.st_dev, secured.st_ino)
        ):
            raise PrivateFileSecurityError(f"Could not secure private file: {path}")
    else:
        _set_windows_private_acl(path, directory=False)
    return path


def create_private_file(path: Path) -> int:
    """Exclusively create a private file and return its open file descriptor.

    If permission setup fails, only the inode created by this call is removed.
    """
    path = Path(path)
    flags = os.O_CREAT | os.O_EXCL | os.O_RDWR
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    fd = os.open(path, flags, 0o600)
    created_info: os.stat_result | None = None
    try:
        created_info = os.fstat(fd)
        if not stat.S_ISREG(created_info.st_mode) or (
            _POSIX and created_info.st_uid != os.geteuid()
        ):
            raise PrivateFileSecurityError(
                f"Created private path is not a regular owned file: {path}"
            )
        if _POSIX:
            os.fchmod(fd, 0o600)
            secured = os.fstat(fd)
            if stat.S_IMODE(secured.st_mode) != 0o600:
                raise PrivateFileSecurityError(f"Could not secure private file: {path}")
        else:
            path_info = path.lstat()
            if not stat.S_ISREG(path_info.st_mode) or (path_info.st_dev, path_info.st_ino) != (
                created_info.st_dev,
                created_info.st_ino,
            ):
                raise PrivateFileSecurityError(
                    f"Created private path changed before ACL setup: {path}"
                )
            _set_windows_private_acl(path, directory=False)
        return fd
    except BaseException:
        os.close(fd)
        try:
            current = path.lstat()
        except FileNotFoundError:
            pass
        else:
            if created_info is not None and (current.st_dev, current.st_ino) == (
                created_info.st_dev,
                created_info.st_ino,
            ):
                path.unlink()
        raise
