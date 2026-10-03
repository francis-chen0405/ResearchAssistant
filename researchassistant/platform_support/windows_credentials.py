"""Direct Windows Credential Manager access; no selectable fallback backend."""

from __future__ import annotations

import ctypes
from ctypes import wintypes


class Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def _vault() -> ctypes.CDLL:
    vault = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    vault.CredReadW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(Credential)),
    )
    vault.CredReadW.restype = wintypes.BOOL
    vault.CredWriteW.argtypes = (ctypes.POINTER(Credential), wintypes.DWORD)
    vault.CredWriteW.restype = wintypes.BOOL
    vault.CredDeleteW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD)
    vault.CredDeleteW.restype = wintypes.BOOL
    vault.CredFree.argtypes = (ctypes.c_void_p,)
    vault.CredFree.restype = None
    return vault


def read(target: str) -> str | None:
    vault = _vault()
    pointer = ctypes.POINTER(Credential)()
    if not vault.CredReadW(target, 1, 0, ctypes.byref(pointer)):
        error = ctypes.get_last_error()
        if error == 1168:
            return None
        raise OSError(error, "Windows credential vault read failed")
    try:
        entry = pointer.contents
        return ctypes.string_at(entry.CredentialBlob, entry.CredentialBlobSize).decode("utf-16-le")
    finally:
        vault.CredFree(pointer)


def write(target: str, secret: str) -> None:
    payload = secret.encode("utf-16-le")
    if len(payload) > 2560:
        raise ValueError("Credential exceeds the Windows vault size limit")
    buffer = (ctypes.c_ubyte * len(payload)).from_buffer_copy(payload)
    entry = Credential(
        Type=1,
        TargetName=target,
        CredentialBlobSize=len(payload),
        CredentialBlob=buffer,
        Persist=2,
        UserName="ResearchAssistant",
    )
    try:
        if not _vault().CredWriteW(ctypes.byref(entry), 0):
            raise OSError(ctypes.get_last_error(), "Windows credential vault save failed")
    finally:
        ctypes.memset(buffer, 0, len(payload))


def delete(target: str) -> None:
    if not _vault().CredDeleteW(target, 1, 0):
        error = ctypes.get_last_error()
        if error != 1168:
            raise OSError(error, "Windows credential vault removal failed")
