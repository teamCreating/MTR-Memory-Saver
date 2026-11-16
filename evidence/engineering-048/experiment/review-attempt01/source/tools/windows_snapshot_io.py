"""Read an immutable snapshot while allowing its publisher to replace the path."""
import ctypes
from ctypes import wintypes
import os

if os.name == "nt":
    import msvcrt

    _kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    _create_file = _kernel.CreateFileW
    _create_file.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                            wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    _create_file.restype = wintypes.HANDLE
    _close_handle = _kernel.CloseHandle
    _close_handle.argtypes = [wintypes.HANDLE]
    _close_handle.restype = wintypes.BOOL


def open_snapshot(path):
    """Return an owned binary reader; Windows permits read/write/delete sharing.

    The handle still refers to one file if the path is replaced during the read.
    Genuine access or publication errors are not retried or suppressed.
    """
    if os.name != "nt":
        return open(path, "rb")
    name = os.fsdecode(os.fspath(path))
    if "\0" in name:
        raise ValueError("Snapshot path contains a null character.")
    # GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
    # OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL.
    handle = _create_file(name, 0x80000000, 0x1 | 0x2 | 0x4, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        _close_handle(handle)
        raise
    try:
        return os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise


def read_snapshot_bytes(path):
    with open_snapshot(path) as reader:
        return reader.read()
