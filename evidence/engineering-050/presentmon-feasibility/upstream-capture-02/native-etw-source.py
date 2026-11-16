"""Read-only identity and exact named-session counters; no ETW control writes."""
import ctypes
from ctypes import wintypes as w
from datetime import datetime, timedelta, timezone


def child_identity(child):
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.GetProcessTimes.argtypes = [w.HANDLE] + [ctypes.POINTER(w.FILETIME)] * 4
    api.GetProcessTimes.restype = w.BOOL
    api.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
    api.QueryFullProcessImageNameW.restype = w.BOOL
    handle = w.HANDLE(int(child._handle))
    stamps = [w.FILETIME() for _ in range(4)]
    if not api.GetProcessTimes(handle, *[ctypes.byref(stamp) for stamp in stamps]):
        raise ctypes.WinError(ctypes.get_last_error())
    image = ctypes.create_unicode_buffer(32768)
    length = w.DWORD(len(image))
    if not api.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length)):
        raise ctypes.WinError(ctypes.get_last_error())
    values = [(stamp.dwHighDateTime << 32) | stamp.dwLowDateTime for stamp in stamps]
    epoch = datetime(1601, 1, 1, tzinfo=timezone.utc)
    return {"pid": child.pid, "executable": image.value,
            "created": (epoch + timedelta(microseconds=values[0] // 10)).isoformat(),
            "exit_time": (epoch + timedelta(microseconds=values[1] // 10)).isoformat() if child.poll() is not None else None,
            "kernel_100ns": values[2], "user_100ns": values[3], "source": "actual_owned_Popen_handle"}


class Wnode(ctypes.Structure):
    _fields_ = [("BufferSize", w.ULONG), ("ProviderId", w.ULONG), ("HistoricalContext", ctypes.c_ulonglong),
                ("TimeStamp", ctypes.c_longlong), ("Guid", ctypes.c_byte * 16), ("ClientContext", w.ULONG), ("Flags", w.ULONG)]


class Properties(ctypes.Structure):
    _fields_ = [("Wnode", Wnode)] + [(name, w.ULONG) for name in (
        "BufferSize", "MinimumBuffers", "MaximumBuffers", "MaximumFileSize", "LogFileMode", "FlushTimer", "EnableFlags",
        "AgeLimit", "NumberOfBuffers", "FreeBuffers", "EventsLost", "BuffersWritten", "LogBuffersLost", "RealTimeBuffersLost"
    )] + [("LoggerThreadId", w.HANDLE), ("LogFileNameOffset", w.ULONG), ("LoggerNameOffset", w.ULONG)]


def query_session(session):
    api = ctypes.WinDLL("advapi32", use_last_error=True)
    api.ControlTraceW.argtypes = [ctypes.c_ulonglong, w.LPCWSTR, ctypes.POINTER(Properties), w.ULONG]
    api.ControlTraceW.restype = w.ULONG
    buffer = ctypes.create_string_buffer(ctypes.sizeof(Properties) + 8192)
    props = ctypes.cast(buffer, ctypes.POINTER(Properties)).contents
    props.Wnode.BufferSize = ctypes.sizeof(buffer)
    props.LoggerNameOffset = ctypes.sizeof(Properties)
    props.LogFileNameOffset = ctypes.sizeof(Properties) + 4096
    status = api.ControlTraceW(0, session, ctypes.byref(props), 0)  # EVENT_TRACE_CONTROL_QUERY only
    return {"observed_at": datetime.now(timezone.utc).isoformat(), "session_name": session,
            "operation": "ControlTraceW_EVENT_TRACE_CONTROL_QUERY", "status": status,
            "properties_size": ctypes.sizeof(Properties), "wnode_size": ctypes.sizeof(Wnode),
            "counters": {name: getattr(props, name) for name in ("EventsLost", "LogBuffersLost", "RealTimeBuffersLost",
                         "NumberOfBuffers", "FreeBuffers", "BuffersWritten")} if status == 0 else None}
