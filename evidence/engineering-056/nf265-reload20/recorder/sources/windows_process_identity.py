"""Read a Windows process identity from one owned caller-supplied handle.

The class-60 ABI is qualified only on Windows 10 build 19045, native AMD64
Python and target processes. Unsupported platforms and query failures fail
closed. This module never derives an observed command line from a launch plan.
"""
import ctypes
from ctypes import wintypes
import datetime as dt
import os


PROCESS_COMMAND_LINE_INFORMATION = 60
STATUS_INFO_LENGTH_MISMATCH = 0xC0000004
MAX_COMMAND_BYTES = 1024 * 1024
MAX_QUERY_ATTEMPTS = 3
IMAGE_FILE_MACHINE_AMD64 = 0x8664


class NativeIdentityError(OSError):
    pass


class UnicodeString(ctypes.Structure):
    _fields_ = [("length", wintypes.USHORT), ("maximum_length", wintypes.USHORT),
                ("buffer", ctypes.c_void_p)]


class OSVersion(ctypes.Structure):
    _fields_ = [("size", wintypes.ULONG), ("major", wintypes.ULONG),
                ("minor", wintypes.ULONG), ("build", wintypes.ULONG),
                ("platform", wintypes.ULONG), ("service_pack", wintypes.WCHAR * 128)]


def nt_failure(operation, status):
    return NativeIdentityError(f"{operation} failed with NTSTATUS 0x{status & 0xffffffff:08x}")


def decode_command_buffer(memory, returned):
    header = ctypes.sizeof(UnicodeString)
    if not header <= returned <= len(memory):
        raise NativeIdentityError("Command-line query returned a truncated or excessive buffer length.")
    value = UnicodeString.from_buffer(memory)
    begin, end = ctypes.addressof(memory), ctypes.addressof(memory)+returned
    length, maximum, pointer = value.length, value.maximum_length, value.buffer
    if (not length or length % 2 or maximum % 2 or length > maximum or pointer is None
            or pointer % 2 or pointer < begin+header or pointer > end or maximum > end-pointer):
        raise NativeIdentityError("Command-line query returned an invalid inline UNICODE_STRING.")
    command = ctypes.string_at(pointer, length).decode("utf-16-le", errors="surrogatepass")
    if "\0" in command:
        raise NativeIdentityError("Command-line query contains an embedded null character.")
    return command


def command_line(handle, query):
    needed = wintypes.ULONG()
    status = query(handle, PROCESS_COMMAND_LINE_INFORMATION, None, 0, ctypes.byref(needed)) & 0xffffffff
    if status != STATUS_INFO_LENGTH_MISMATCH:
        raise nt_failure("NtQueryInformationProcess(command-line size)", status)
    size = needed.value
    for _ in range(MAX_QUERY_ATTEMPTS):
        if not ctypes.sizeof(UnicodeString) <= size <= MAX_COMMAND_BYTES:
            raise NativeIdentityError("Command-line query requested an invalid buffer size.")
        memory = ctypes.create_string_buffer(size)
        returned = wintypes.ULONG()
        status = query(handle, PROCESS_COMMAND_LINE_INFORMATION, memory, size, ctypes.byref(returned)) & 0xffffffff
        if status == STATUS_INFO_LENGTH_MISMATCH:
            if returned.value <= size:
                raise NativeIdentityError("Command-line buffer growth made no progress.")
            size = returned.value
            continue
        if status:
            raise nt_failure("NtQueryInformationProcess(command line)", status)
        return decode_command_buffer(memory, returned.value)
    raise NativeIdentityError("Command-line buffer did not stabilize within the bounded size queries.")


def supported_platform(version, pointer_bytes, caller_architecture, target_architecture):
    native_amd64 = (0, IMAGE_FILE_MACHINE_AMD64)
    if (version != (10, 0, 19045) or pointer_bytes != 8
            or caller_architecture != native_amd64 or target_architecture != native_amd64):
        raise NativeIdentityError("Native identity queries are qualified only on Windows 10 build 19045, native AMD64 caller and target.")


class NativeApi:
    def __init__(self, kernel=None, ntdll=None):
        if os.name != "nt":
            raise NativeIdentityError("Native process identity requires Windows.")
        self.kernel = kernel if kernel is not None else ctypes.WinDLL("kernel32", use_last_error=True)
        self.ntdll = ntdll if ntdll is not None else ctypes.WinDLL("ntdll")
        signatures = {
            "GetProcessId": ((wintypes.HANDLE,), wintypes.DWORD),
            "GetCurrentProcess": ((), wintypes.HANDLE),
            "GetExitCodeProcess": ((wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)), wintypes.BOOL),
            "GetProcessTimes": ((wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4, wintypes.BOOL),
            "QueryFullProcessImageNameW": ((wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)), wintypes.BOOL),
            "IsWow64Process2": ((wintypes.HANDLE, ctypes.POINTER(wintypes.USHORT), ctypes.POINTER(wintypes.USHORT)), wintypes.BOOL),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = arguments, result
        self.query = self.ntdll.NtQueryInformationProcess
        self.query.argtypes = (wintypes.HANDLE, wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG, ctypes.POINTER(wintypes.ULONG))
        self.query.restype = ctypes.c_long
        self.version_query = self.ntdll.RtlGetVersion
        self.version_query.argtypes, self.version_query.restype = (ctypes.POINTER(OSVersion),), ctypes.c_long

    def architecture(self, handle):
        process, native = wintypes.USHORT(), wintypes.USHORT()
        if not self.kernel.IsWow64Process2(handle, ctypes.byref(process), ctypes.byref(native)):
            raise ctypes.WinError(ctypes.get_last_error())
        return process.value, native.value

    def platform(self, handle):
        version = OSVersion()
        version.size = ctypes.sizeof(version)
        status = self.version_query(ctypes.byref(version)) & 0xffffffff
        if status:
            raise nt_failure("RtlGetVersion", status)
        actual = (version.major, version.minor, version.build)
        caller = self.architecture(self.kernel.GetCurrentProcess())
        target = self.architecture(handle)
        supported_platform(actual, ctypes.sizeof(ctypes.c_void_p), caller, target)
        return {"windows": list(actual), "caller_architecture": list(caller),
                "target_architecture": list(target), "command_line_information_class": PROCESS_COMMAND_LINE_INFORMATION}

    def live(self, handle):
        code = wintypes.DWORD()
        if not self.kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        if code.value != 259:
            raise NativeIdentityError(f"The queried process exited with code {code.value}.")

    def pid(self, handle):
        result = self.kernel.GetProcessId(handle)
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())
        return result

    def creation_filetime(self, handle):
        created, exited, kernel, user = [wintypes.FILETIME() for _ in range(4)]
        if not self.kernel.GetProcessTimes(handle, *[ctypes.byref(value) for value in (created, exited, kernel, user)]):
            raise ctypes.WinError(ctypes.get_last_error())
        # An exit code of STILL_ACTIVE is also a possible actual exit code.
        if exited.dwHighDateTime or exited.dwLowDateTime:
            raise NativeIdentityError("The queried process has a recorded exit time.")
        return (created.dwHighDateTime << 32) | created.dwLowDateTime

    def image(self, handle):
        capacity = 256
        while capacity <= 32768:
            memory = ctypes.create_unicode_buffer(capacity)
            size = wintypes.DWORD(capacity)
            if self.kernel.QueryFullProcessImageNameW(handle, 0, memory, ctypes.byref(size)):
                if not 0 < size.value < capacity:
                    raise NativeIdentityError("Executable query returned an invalid character count.")
                return memory[:size.value]
            error = ctypes.get_last_error()
            if error != 122:
                raise ctypes.WinError(error)
            capacity *= 2
        raise NativeIdentityError("Executable path exceeds the bounded image-query buffer.")

    def command(self, handle):
        return command_line(handle, self.query)


def query_identity(handle, api=None):
    api = NativeApi() if api is None else api
    context = api.platform(handle)
    api.live(handle)
    created = api.creation_filetime(handle)
    pid, executable, command = api.pid(handle), api.image(handle), api.command(handle)
    api.live(handle)
    if api.creation_filetime(handle) != created:
        raise NativeIdentityError("Process creation identity changed during the native query.")
    stamp = dt.datetime(1601, 1, 1, tzinfo=dt.timezone.utc)+dt.timedelta(microseconds=created // 10)
    return {"pid": pid, "executable": executable, "command": command,
            "created": stamp.isoformat(), "identity_query": context}
