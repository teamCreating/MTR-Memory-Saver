import ctypes
from ctypes import wintypes
import datetime as dt
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
from types import SimpleNamespace

import observe_packaged_client as observer
import windows_process_identity as identity


def ulong(pointer, value):
    ctypes.cast(pointer, ctypes.POINTER(wintypes.ULONG))[0] = value


class Query:
    def __init__(self, text="列车🚆 command", mutate=None, growth=0, size_status=None, data_status=0):
        self.payload = text.encode("utf-16-le", errors="surrogatepass")
        self.mutate, self.growth = mutate, growth
        self.size_status, self.data_status = size_status, data_status
        self.calls = []

    def __call__(self, handle, information_class, memory, size, returned):
        self.calls.append((handle, information_class, size))
        needed = ctypes.sizeof(identity.UnicodeString)+len(self.payload)+2
        if memory is None:
            ulong(returned, needed)
            return identity.STATUS_INFO_LENGTH_MISMATCH if self.size_status is None else self.size_status
        if self.growth:
            self.growth -= 1
            ulong(returned, size+2)
            return identity.STATUS_INFO_LENGTH_MISMATCH
        if self.data_status:
            return self.data_status
        value = identity.UnicodeString.from_buffer(memory)
        value.length, value.maximum_length = len(self.payload), len(self.payload)+2
        value.buffer = ctypes.addressof(memory)+ctypes.sizeof(identity.UnicodeString)
        ctypes.memmove(value.buffer, self.payload, len(self.payload))
        ulong(returned, needed)
        if self.mutate:
            self.mutate(value, memory, returned)
        return 0


class CommandBufferTest(unittest.TestCase):
    def test_exact_unicode_and_long_command_and_expected_buffer_growth(self):
        for text, growth in (("列车🚆 \"a b\" \\", 0), ("x"*20000, 1)):
            with self.subTest(growth=growth):
                query = Query(text, growth=growth)
                self.assertEqual(identity.command_line(123, query), text)
                self.assertTrue(all(handle == 123 and kind == 60 for handle, kind, _ in query.calls))

    def test_truncated_odd_null_and_out_of_bounds_unicode_are_rejected_before_dereference(self):
        cases = {
            "truncated_header": lambda value, memory, returned: ulong(returned, ctypes.sizeof(identity.UnicodeString)-1),
            "excessive_return": lambda value, memory, returned: ulong(returned, len(memory)+1),
            "odd_length": lambda value, memory, returned: setattr(value, "length", 3),
            "odd_maximum": lambda value, memory, returned: setattr(value, "maximum_length", 3),
            "length_exceeds_maximum": lambda value, memory, returned: setattr(value, "maximum_length", 2),
            "null_pointer": lambda value, memory, returned: setattr(value, "buffer", None),
            "points_into_header": lambda value, memory, returned: setattr(value, "buffer", ctypes.addressof(memory)),
            "beyond_buffer": lambda value, memory, returned: setattr(value, "buffer", ctypes.addressof(memory)+len(memory)+2),
            "unaligned_pointer": lambda value, memory, returned: setattr(value, "buffer", value.buffer+1),
            "range_exceeds_returned_bytes": lambda value, memory, returned: setattr(value, "buffer", value.buffer+2),
        }
        for name, mutate in cases.items():
            with self.subTest(case=name), self.assertRaises(identity.NativeIdentityError):
                identity.command_line(123, Query(mutate=mutate))
        for text in ("", "before\0after"):
            with self.subTest(text=text), self.assertRaises(identity.NativeIdentityError):
                identity.command_line(123, Query(text))

    def test_native_statuses_sizes_and_unstable_growth_fail_closed(self):
        for query in (Query(size_status=0xC0000022), Query(size_status=0), Query(data_status=0xC000010A), Query(data_status=0xC0000003),
                      Query(growth=identity.MAX_QUERY_ATTEMPTS)):
            with self.subTest(query=query), self.assertRaises(identity.NativeIdentityError):
                identity.command_line(123, query)
        for required in (0, ctypes.sizeof(identity.UnicodeString)-1, identity.MAX_COMMAND_BYTES+1):
            def invalid_size(handle, kind, memory, size, returned):
                ulong(returned, required)
                return identity.STATUS_INFO_LENGTH_MISMATCH
            with self.subTest(required=required), self.assertRaises(identity.NativeIdentityError):
                identity.command_line(123, invalid_size)
        def no_progress(handle, kind, memory, size, returned):
            ulong(returned, size if memory is not None else 64)
            return identity.STATUS_INFO_LENGTH_MISMATCH
        with self.assertRaisesRegex(identity.NativeIdentityError, "no progress"):
            identity.command_line(123, no_progress)
        with self.assertRaisesRegex(OSError, "actual API failure"):
            identity.command_line(123, mock.Mock(side_effect=OSError("actual API failure")))

    def test_only_qualified_os_and_same_native_amd64_bitness_are_accepted(self):
        native = (0, 0x8664)
        identity.supported_platform((10, 0, 19045), 8, native, native)
        for version, width, caller, target in (((10, 0, 22631), 8, native, native),
                ((10, 0, 19044), 8, native, native), ((10, 0, 19045), 4, native, native),
                ((10, 0, 19045), 8, (0x14C, 0x8664), native),
                ((10, 0, 19045), 8, native, (0x14C, 0x8664)),
                ((10, 0, 19045), 8, (0, 0xAA64), (0, 0xAA64))):
            with self.subTest(version=version, width=width, caller=caller, target=target), self.assertRaises(identity.NativeIdentityError):
                identity.supported_platform(version, width, caller, target)


class FakeApi:
    def __init__(self, fail=None, creation_change=False):
        self.fail, self.creation_change, self.calls = fail, creation_change, []
        self.created_count = self.live_count = 0
    def call(self, name, handle):
        self.calls.append((name, handle))
        if name == self.fail:
            raise identity.NativeIdentityError("Failed "+name)
    def platform(self, handle): self.call("platform", handle); return {"qualified": True}
    def live(self, handle):
        self.live_count += 1
        self.call("live_after" if self.live_count > 1 else "live_before", handle)
    def creation_filetime(self, handle):
        self.created_count += 1
        self.call("created_after" if self.created_count > 1 else "created_before", handle)
        return 133000000000000000 + int(self.creation_change and self.created_count > 1)
    def pid(self, handle): self.call("pid", handle); return 321
    def image(self, handle): self.call("image", handle); return "C:\\java.exe"
    def command(self, handle): self.call("command", handle); return '"C:\\java.exe" -Xmx3g'


class IdentitySequenceTest(unittest.TestCase):
    def test_all_queries_share_one_handle_and_creation_and_liveness_bracket_the_capture(self):
        api = FakeApi()
        result = identity.query_identity(123, api)
        self.assertEqual(result["pid"], 321)
        self.assertEqual(result["command"], '"C:\\java.exe" -Xmx3g')
        self.assertEqual([name for name, _ in api.calls],
                         ["platform", "live_before", "created_before", "pid", "image", "command", "live_after", "created_after"])
        self.assertEqual({handle for _, handle in api.calls}, {123})
        for name, _ in api.calls:
            with self.subTest(failure=name), self.assertRaisesRegex(identity.NativeIdentityError, "Failed"):
                identity.query_identity(123, FakeApi(fail=name))
        with self.assertRaisesRegex(identity.NativeIdentityError, "creation identity changed"):
            identity.query_identity(123, FakeApi(creation_change=True))

    @unittest.skipUnless(os.name == "nt", "Win32 failure binding")
    def test_real_win32_error_results_and_recorded_exit_time_are_not_accepted(self):
        api = identity.NativeApi.__new__(identity.NativeApi)
        api.kernel = SimpleNamespace(GetExitCodeProcess=mock.Mock(return_value=0), GetProcessId=mock.Mock(return_value=0),
            GetProcessTimes=mock.Mock(return_value=0), QueryFullProcessImageNameW=mock.Mock(return_value=0),
            IsWow64Process2=mock.Mock(return_value=0))
        with mock.patch.object(ctypes, "get_last_error", return_value=5):
            for method in (api.live, api.pid, api.creation_filetime, api.image, api.architecture):
                with self.subTest(method=method.__name__), self.assertRaises(OSError): method(123)
        def exited(handle, created, exit_time, kernel, user):
            ctypes.cast(exit_time, ctypes.POINTER(wintypes.FILETIME))[0].dwLowDateTime = 1
            return 1
        api.kernel.GetProcessTimes = exited
        with self.assertRaisesRegex(identity.NativeIdentityError, "recorded exit time"):
            api.creation_filetime(123)
        observed = observer.WindowsProcess.__new__(observer.WindowsProcess)
        observed.kernel, observed.handle = api.kernel, 123
        observed.kernel.GetExitCodeProcess = lambda handle, code: (ulong(code, 259) or 1)
        with self.assertRaisesRegex(identity.NativeIdentityError, "recorded exit time"):
            observed.sample()

    @unittest.skipUnless(os.name == "nt", "Win32 image buffer binding")
    def test_image_buffer_growth_is_bounded_and_preserves_the_exact_path(self):
        api = identity.NativeApi.__new__(identity.NativeApi)
        calls, path = [], "C:\\"+"列"*400+"\\java.exe"
        def image(handle, flags, memory, size):
            calls.append(len(memory))
            if len(memory) <= len(path): return 0
            memory.value = path
            ulong(size, len(path))
            return 1
        api.kernel = SimpleNamespace(QueryFullProcessImageNameW=image)
        with mock.patch.object(ctypes, "get_last_error", return_value=122):
            self.assertEqual(api.image(123), path)
        self.assertEqual(calls, [256, 512])
        api.kernel.QueryFullProcessImageNameW = lambda *unused: 0
        with mock.patch.object(ctypes, "get_last_error", return_value=122), self.assertRaises(identity.NativeIdentityError):
            api.image(123)


@unittest.skipUnless(os.name == "nt", "Windows process ownership")
class ProcessOwnershipTest(unittest.TestCase):
    def test_constructor_closes_its_handle_on_every_identity_failure(self):
        created = identity.query_identity(123, FakeApi())["created"]
        good = {"pid": 321, "created": created, "executable": "C:\\java.exe", "command": '"C:\\java.exe" -Xmx3g'}
        plan = {"java": "C:\\java.exe"}
        launch = {"pid": 321, "timestamp": created, "command": ["C:\\java.exe", "-Xmx3g"]}
        for failure in ("api_load", "missing_export", "native_query", "pid", "created", "executable", "argv", "parse", "times"):
            kernel = SimpleNamespace(**{name: mock.Mock(return_value=1) for name in
                ("GetExitCodeProcess", "GetProcessTimes", "CloseHandle")})
            kernel.OpenProcess = mock.Mock(return_value=123)
            psapi = SimpleNamespace(GetProcessMemoryInfo=mock.Mock(return_value=1))
            observed = dict(good)
            if failure == "pid": observed["pid"] += 1
            if failure == "created": observed["created"] = "2000-01-01T00:00:00Z"
            if failure == "executable": observed["executable"] = "C:\\wrong.exe"
            with self.subTest(failure=failure), \
                 mock.patch.object(observer.ctypes, "WinDLL", side_effect=lambda name, **kwargs: kernel if name == "kernel32" else psapi), \
                 mock.patch.object(identity, "NativeApi", side_effect=(OSError("api load") if failure == "api_load" else
                     AttributeError("missing API export") if failure == "missing_export" else None)), \
                 mock.patch.object(identity, "query_identity", side_effect=OSError("native query") if failure == "native_query" else None, return_value=observed), \
                 mock.patch.object(observer, "windows_arguments", side_effect=OSError("parse") if failure == "parse" else None,
                                   return_value=launch["command"][:-1] if failure == "argv" else launch["command"]), \
                 mock.patch.object(observer.WindowsProcess, "creation_time", side_effect=OSError("times") if failure == "times" else None, return_value=created):
                with self.assertRaises((OSError, ValueError, AttributeError)):
                    observer.WindowsProcess(plan, launch)
            kernel.CloseHandle.assert_called_once_with(123)

    def test_every_dependent_tool_freezes_the_native_identity_source(self):
        import reload_before_recorder as recorder
        import client_experiment as experiment
        source = Path(identity.__file__)
        self.assertIn(source, recorder.source_files())
        self.assertIn(source, experiment.SOURCES)


@unittest.skipUnless(os.name == "nt", "Actual qualified Windows child")
class OwnedChildTest(unittest.TestCase):
    def setUp(self):
        # Hosted Windows Server runners are not the qualified live-reader OS.
        # Query failures still fail; only the provider's explicit platform
        # rejection skips these actual-child cases. ABI/unit tests run normally.
        api = identity.NativeApi()
        version = identity.OSVersion()
        version.size = ctypes.sizeof(version)
        self.assertEqual(api.version_query(ctypes.byref(version)) & 0xffffffff, 0)
        architecture = api.architecture(api.kernel.GetCurrentProcess())
        try:
            identity.supported_platform((version.major, version.minor, version.build),
                                        ctypes.sizeof(ctypes.c_void_p), architecture, architecture)
        except identity.NativeIdentityError as error:
            self.skipTest(str(error))

    def start_child(self, name):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        evidence = os.environ.get("MTR_IDENTITY_TEST_EVIDENCE")
        output = Path(evidence)/name if evidence else Path(temporary.name)
        if evidence: output.mkdir(parents=True, exist_ok=False)
        child = output/"owned-child-列车-🚆.py"
        child.write_text("import json,os,sys\nprint(json.dumps({'pid':os.getpid(),'argv':sys.argv},ensure_ascii=False),flush=True)\nsys.stdin.buffer.read(1)\n", encoding="utf-8")
        arguments = ["", "space value", "列车🚆", 'quote"value', "ends-with-slash\\", "space then slash\\", 'backslashes\\\\"quote', "x"*20000]
        command = [sys._base_executable, "-X", "utf8", "-u", str(child), *arguments]
        stamp = dt.datetime.now(dt.timezone.utc).isoformat()
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.close_child, process)
        lines = queue.Queue()
        threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
        raw = lines.get(timeout=30)
        observed = json.loads(raw)
        self.assertEqual(observed, {"pid": process.pid, "argv": [str(child), *arguments]})
        if evidence: (output/"child-ready.json").write_bytes(raw)
        return process, {"pid": process.pid, "timestamp": stamp, "command": command}, {"java": command[0]}, output

    @staticmethod
    def close_child(process):
        if process.poll() is None:
            process.stdin.write(b"x"); process.stdin.flush()
        process.wait(timeout=20)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream: stream.close()

    def test_actual_same_handle_identity_matches_full_child_argv_without_a_subprocess_query(self):
        process, launch, plan, output = self.start_child("positive")
        with mock.patch.object(observer.subprocess, "run", side_effect=AssertionError("No shell/CIM identity query permitted")):
            captured = observer.WindowsProcess(plan, launch)
        try:
            self.assertEqual(captured.identity["pid"], process.pid)
            self.assertEqual(observer.windows_arguments(captured.identity["command"]), launch["command"])
            self.assertTrue(captured.sample()["running"])
            if os.environ.get("MTR_IDENTITY_TEST_EVIDENCE"):
                (output/"actual-identity.json").write_text(json.dumps({"launch": launch, "identity": captured.identity,
                    "created": captured.created, "memory": captured.sample()}, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
        finally:
            captured.close()

    def test_actual_child_exit_between_native_size_and_data_queries_is_rejected(self):
        process, launch, plan, output = self.start_child("exit-during-query")
        api = identity.NativeApi()
        actual_query = api.query
        def query_then_exit(handle, kind, memory, size, returned):
            result = actual_query(handle, kind, memory, size, returned)
            if memory is None:
                process.stdin.write(b"x"); process.stdin.flush(); process.wait(timeout=20)
            return result
        api.query = query_then_exit
        with mock.patch.object(identity, "NativeApi", return_value=api):
            with self.assertRaises(identity.NativeIdentityError) as failure:
                observer.WindowsProcess(plan, launch)
        if os.environ.get("MTR_IDENTITY_TEST_EVIDENCE"):
            (output/"rejected-exit.json").write_text(json.dumps({"pid": process.pid, "exit_code": process.returncode,
                "error": str(failure.exception)}, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
