"""Standalone local window operator for timed /sparkc profiler commands.

Never imported by practical_client_verification.py or client_experiment.py.
Watches a run directory for sampler-request.json, verifies target JVM process
identity and unpaused in-world state, dispatches /sparkc via Win32 SendInput
with idempotent log recovery, and publishes sampler-continue.json only after
confirmation.
"""
import argparse
import ctypes
from ctypes import wintypes
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import time

from windows_process_identity import NativeApi, NativeIdentityError, query_identity
from windows_snapshot_io import read_snapshot_bytes


CHAT_SCREENS = ("net.minecraft.client.gui.screens.ChatScreen", "net.minecraft.class_408")
SPARK_INITIATED_MARKERS = (
    "Starting a new profiler, please wait...",
    "Profiler is now running!",
    "Starting a new profiler",
)
SPARK_RUNNING_MARKERS = (
    "Profiler is now running!",
    "The results will be automatically returned",
)
KEYS = {"ESC": 0x1B, "ENTER": 0x0D, "T": 0x54}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def instant(text):
    parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp needs an explicit UTC offset.")
    return parsed.astimezone(dt.timezone.utc)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_atomic(path, data):
    path = Path(path)
    content = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8", newline="\n")
    temp.replace(path)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class Win32OperatorBackend:
    """Isolated Win32 window/input backend scoped strictly to a verified JVM PID."""

    def __init__(self):
        if os.name != "nt":
            raise RuntimeError("spark_operator requires Windows.")
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._configure_abi()

    def _configure_abi(self):
        u = self.user32
        k = self.kernel32
        u.SetProcessDPIAware()
        u.GetForegroundWindow.restype = wintypes.HWND
        u.SetForegroundWindow.argtypes = [wintypes.HWND]
        u.SetForegroundWindow.restype = wintypes.BOOL
        u.SetActiveWindow.argtypes = [wintypes.HWND]
        u.SetFocus.argtypes = [wintypes.HWND]
        u.BringWindowToTop.argtypes = [wintypes.HWND]
        u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        u.IsWindowVisible.argtypes = [wintypes.HWND]
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
        u.AttachThreadInput.restype = wintypes.BOOL
        u.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
        u.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
        u.MapVirtualKeyW.restype = wintypes.UINT
        u.LoadKeyboardLayoutW.argtypes = [wintypes.LPCWSTR, wintypes.UINT]
        u.LoadKeyboardLayoutW.restype = wintypes.HKL
        u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        u.PostMessageW.restype = wintypes.BOOL
        k.GetCurrentThreadId.restype = wintypes.DWORD
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.OpenProcess.restype = wintypes.HANDLE
        k.CloseHandle.argtypes = [wintypes.HANDLE]

        class Mouse(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("data", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

        class Keyboard(ctypes.Structure):
            _fields_ = [("vk", wintypes.WORD), ("scan", wintypes.WORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

        class Payload(ctypes.Union):
            _fields_ = [("mouse", Mouse), ("keyboard", Keyboard)]

        class Input(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("payload", Payload)]

        self._input_cls = Input
        self._keyboard_cls = Keyboard
        u.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
        u.SendInput.restype = wintypes.UINT

    def verify_process(self, expected_process):
        pid = expected_process["pid"]
        handle = self.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            raise RuntimeError(f"Target JVM PID {pid} is unavailable (winerr={ctypes.get_last_error()}).")
        try:
            actual = query_identity(handle, NativeApi(kernel=self.kernel32))
        except NativeIdentityError as error:
            raise RuntimeError(f"Target JVM PID {pid} exited or changed identity: {error}") from error
        finally:
            self.kernel32.CloseHandle(handle)
        if actual["pid"] != pid or abs((instant(actual["created"]) - instant(expected_process["created"])).total_seconds()) > 1:
            raise RuntimeError(f"Process creation identity mismatch for PID {pid}.")
        return actual

    def find_window(self, pid):
        found = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def visit(hwnd, _):
            window_pid = wintypes.DWORD()
            self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
            if window_pid.value == pid and self.user32.IsWindowVisible(hwnd):
                class_name = ctypes.create_unicode_buffer(256)
                self.user32.GetClassNameW(hwnd, class_name, len(class_name))
                if class_name.value.startswith("GLFW"):
                    found.append(hwnd)
            return True

        callback = callback_type(visit)
        self.user32.EnumWindows(callback, 0)
        if len(found) != 1:
            raise RuntimeError(f"Expected 1 visible GLFW window for PID {pid}, found {len(found)}.")
        return found[0]

    def apply_us_layout(self, hwnd):
        layout = self.user32.LoadKeyboardLayoutW("00000409", 128)
        if layout:
            self.user32.PostMessageW(hwnd, 0x0050, 0, int(layout))

    def focus_window(self, hwnd):
        u = self.user32
        u.ShowWindow(hwnd, 9)
        u.SetForegroundWindow(hwnd)
        time.sleep(0.15)
        if u.GetForegroundWindow() != hwnd:
            current = self.kernel32.GetCurrentThreadId()
            fg_hwnd = u.GetForegroundWindow()
            foreground = u.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
            target = u.GetWindowThreadProcessId(hwnd, None)
            msg = wintypes.MSG()
            u.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
            attached = []
            try:
                for thread in dict.fromkeys((foreground, target)):
                    if thread and thread != current and u.AttachThreadInput(current, thread, True):
                        attached.append(thread)
                u.BringWindowToTop(hwnd)
                u.SetForegroundWindow(hwnd)
                u.SetActiveWindow(hwnd)
                u.SetFocus(hwnd)
                time.sleep(0.15)
            finally:
                for thread in reversed(attached):
                    u.AttachThreadInput(current, thread, False)
        if u.GetForegroundWindow() != hwnd:
            raise RuntimeError("Target Minecraft window did not acquire foreground focus.")

    def is_foreground(self, hwnd):
        return self.user32.GetForegroundWindow() == hwnd

    def _send(self, event):
        if self.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(self._input_cls)) != 1:
            raise ctypes.WinError(ctypes.get_last_error())

    def press_key(self, name, duration=0.06):
        vk = KEYS[name]
        scan = self.user32.MapVirtualKeyW(vk, 4)
        for released in (False, True):
            flags = 8 | (2 if released else 0) | (1 if scan >> 8 else 0)
            event = self._input_cls(type=1)
            event.payload.keyboard = self._keyboard_cls(0, scan & 0xFF, flags, 0, 0)
            self._send(event)
            if not released:
                time.sleep(duration)

    def type_text(self, value, hwnd=None):
        encoded = value.encode("utf-16-le")
        for index in range(0, len(encoded), 2):
            if hwnd is not None and index % 32 == 0 and not self.is_foreground(hwnd):
                raise RuntimeError("Lost foreground focus while typing command.")
            unit = int.from_bytes(encoded[index:index + 2], "little")
            for flags in (4, 6):
                event = self._input_cls(type=1)
                event.payload.keyboard = self._keyboard_cls(0, unit, flags, 0, 0)
                self._send(event)
            time.sleep(0.004)


def read_snapshot(instance, expected_pid):
    path = Path(instance) / "game-probe/native-observer.json"
    raw = read_snapshot_bytes(path)
    data = json.loads(raw.decode("utf-8-sig"))
    if data.get("pid") != expected_pid:
        raise RuntimeError("Native snapshot PID mismatch.")
    age = (dt.datetime.now(dt.timezone.utc) - instant(data["observed_at"])).total_seconds()
    if not -1 <= age <= 5:
        raise RuntimeError(f"Native snapshot is stale ({age:.2f}s).")
    return data


def spark_log_match(instance, markers=SPARK_RUNNING_MARKERS):
    log_path = Path(instance) / "logs/latest.log"
    if not log_path.is_file():
        return None
    text = log_path.read_text(encoding="utf-8-sig", errors="replace")
    for line in reversed(text.splitlines()):
        if any(marker in line for marker in markers):
            return line
    return None


def wait_for_screen(instance, pid, expected_screens, timeout_seconds=3.0, *, sleep_fn=time.sleep):
    deadline = time.monotonic() + timeout_seconds
    last = None
    while time.monotonic() < deadline:
        try:
            snap = read_snapshot(instance, pid)
            last = snap.get("screen")
            if last in expected_screens and snap.get("in_world") is True and snap.get("paused") is False:
                return snap
        except (OSError, ValueError, RuntimeError):
            pass
        sleep_fn(0.1)
    raise TimeoutError(f"Expected screen {expected_screens}, last observed={last!r}.")


def handle_request(request_path, backend=None, *, sleep_fn=time.sleep):
    request_path = Path(request_path)
    root = request_path.parent
    continue_path = root / "sampler-continue.json"
    failed_path = root / "sampler-operator-failed.json"
    if continue_path.exists() or failed_path.exists():
        return False

    request = read_json(request_path)
    if request.get("schema") != 1 or request.get("kind") != "local_spark_start_coordination":
        raise ValueError("Unsupported sampler request schema.")
    request_sha = digest(request_path)
    process = request["process"]
    instance = Path(request["instance"])
    command = request["command"]
    timeout = float(request["sampler"]["operator_timeout_seconds"])
    created_at = instant(request["created_at"])
    remaining = max(5.0, min(timeout, (created_at + dt.timedelta(seconds=timeout) - dt.datetime.now(dt.timezone.utc)).total_seconds()))
    deadline = time.monotonic() + remaining

    backend = Win32OperatorBackend() if backend is None else backend
    attempts = []

    while time.monotonic() < deadline:
        attempt = {"started_at": now(), "status": "running"}
        try:
            backend.verify_process(process)
            initiated_line = spark_log_match(instance, SPARK_INITIATED_MARKERS)
            if initiated_line is not None:
                # Idempotent recovery: Spark start already reached logs/latest.log.
                snap = read_snapshot(instance, process["pid"])
                if snap.get("screen") in CHAT_SCREENS:
                    hwnd = backend.find_window(process["pid"])
                    backend.focus_window(hwnd)
                    if backend.is_foreground(hwnd):
                        backend.press_key("ESC")
                running_deadline = min(deadline, time.monotonic() + 3.0)
                matched_line = spark_log_match(instance, SPARK_RUNNING_MARKERS)
                while matched_line is None and time.monotonic() < running_deadline:
                    sleep_fn(0.1)
                    matched_line = spark_log_match(instance, SPARK_RUNNING_MARKERS)
                if matched_line is None:
                    matched_line = initiated_line
                wait_for_screen(instance, process["pid"], (None,), timeout_seconds=4.0, sleep_fn=sleep_fn)
                attempt.update(status="recovered_from_log", matched_line=matched_line, finished_at=now())
                attempts.append(attempt)
                write_atomic(root / "sampler-operator-receipt.json", {
                    "schema": 1, "pid": process["pid"], "instance": str(instance),
                    "request_sha256": request_sha, "attempts": attempts,
                    "matched_log_line": matched_line, "confirmed_at": now(),
                })
                write_atomic(continue_path, {
                    "schema": 1, "request_sha256": request_sha, "observed_at": now(),
                })
                return True

            hwnd = backend.find_window(process["pid"])
            backend.apply_us_layout(hwnd)
            backend.focus_window(hwnd)
            snap = read_snapshot(instance, process["pid"])
            if snap.get("in_world") is not True or snap.get("paused") is not False:
                raise RuntimeError(f"Game not ready for command (in_world={snap.get('in_world')}, paused={snap.get('paused')}).")
            if snap.get("screen") in CHAT_SCREENS:
                if not backend.is_foreground(hwnd):
                    raise RuntimeError("Window lost foreground before clearing leftover chat.")
                backend.press_key("ESC")
                wait_for_screen(instance, process["pid"], (None,), timeout_seconds=2.5, sleep_fn=sleep_fn)
            elif snap.get("screen") is not None:
                raise RuntimeError(f"Unexpected blocking screen: {snap.get('screen')}")

            if not backend.is_foreground(hwnd):
                raise RuntimeError("Window lost foreground before opening chat.")
            backend.press_key("T")
            wait_for_screen(instance, process["pid"], CHAT_SCREENS, timeout_seconds=3.0, sleep_fn=sleep_fn)
            if not backend.is_foreground(hwnd):
                raise RuntimeError("Window lost foreground after opening chat.")
            backend.type_text(command, hwnd=hwnd)
            sleep_fn(0.05)
            if not backend.is_foreground(hwnd):
                raise RuntimeError("Window lost foreground before pressing Enter.")
            backend.press_key("ENTER")

            confirm_deadline = min(deadline, time.monotonic() + 5.0)
            matched_line = None
            screen_ok = False
            while time.monotonic() < confirm_deadline:
                matched_line = spark_log_match(instance, SPARK_RUNNING_MARKERS)
                try:
                    snap = read_snapshot(instance, process["pid"])
                    screen_ok = (snap.get("screen") is None and snap.get("in_world") is True and snap.get("paused") is False)
                except (OSError, ValueError, RuntimeError):
                    screen_ok = False
                if matched_line is not None and screen_ok:
                    break
                sleep_fn(0.15)

            if matched_line is not None and screen_ok:
                attempt.update(status="confirmed", hwnd=int(hwnd), matched_line=matched_line, finished_at=now())
                attempts.append(attempt)
                write_atomic(root / "sampler-operator-receipt.json", {
                    "schema": 1, "pid": process["pid"], "hwnd": int(hwnd), "instance": str(instance),
                    "request_sha256": request_sha, "attempts": attempts,
                    "matched_log_line": matched_line, "confirmed_at": now(),
                })
                write_atomic(continue_path, {
                    "schema": 1, "request_sha256": request_sha, "observed_at": now(),
                })
                return True

            # Interrupted or incomplete submission: close chat if still open and retry.
            try:
                snap = read_snapshot(instance, process["pid"])
                if snap.get("screen") in CHAT_SCREENS and backend.is_foreground(hwnd):
                    backend.press_key("ESC")
            except (OSError, ValueError, RuntimeError):
                pass
            raise TimeoutError("Spark start log and unobstructed game screen not confirmed within 5s.")
        except Exception as error:
            attempt.update(status="retry", error=f"{type(error).__name__}: {error}", finished_at=now())
            attempts.append(attempt)
            if "exited" in str(error).lower() or "identity mismatch" in str(error).lower():
                break
            sleep_fn(2.0)

    write_atomic(failed_path, {
        "schema": 1, "pid": process["pid"], "instance": str(instance),
        "request_sha256": request_sha, "attempts": attempts, "failed_at": now(),
    })
    return False


def watch(root, poll_seconds=0.3):
    root = Path(root)
    stop_file = root / "operator-stop"
    print(f"spark_operator watching {root}", flush=True)
    while not stop_file.exists():
        if root.is_dir():
            candidates = [root / "sampler-request.json"] + [
                child / "sampler-request.json"
                for child in sorted(root.iterdir())
                if child.is_dir()
            ]
            for req in candidates:
                if req.is_file() and not (req.parent / "sampler-continue.json").exists() and not (req.parent / "sampler-operator-failed.json").exists():
                    try:
                        handled = handle_request(req)
                        print(f"Handled {req}: {handled}", flush=True)
                    except Exception as error:
                        print(f"Operator error on {req}: {error}", flush=True)
        time.sleep(poll_seconds)
    print(f"spark_operator stopped cleanly via {stop_file}", flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch-root", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=float, default=0.3)
    args = parser.parse_args()
    return watch(args.watch_root, args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
