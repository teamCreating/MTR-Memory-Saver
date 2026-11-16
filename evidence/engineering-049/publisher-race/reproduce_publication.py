"""Reproduce Windows snapshot namespace semantics; no JVM or game access."""
import argparse
import ctypes
from ctypes import wintypes
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time


class RenameInfo(ctypes.Structure):
    _fields_ = [("Flags", wintypes.DWORD), ("RootDirectory", wintypes.HANDLE),
                ("FileNameLength", wintypes.DWORD), ("FileName", wintypes.WCHAR * 1)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", choices=("replacefile", "posix-rename"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--publications", type=int, default=1500)
    parser.add_argument("--reader-source", type=Path, default=Path(__file__).parent / "old-sources/tools/windows_snapshot_io.py")
    args = parser.parse_args()
    if args.publications <= 0:
        parser.error("Require a positive number of separately recorded publication attempts.")
    args.output.mkdir(parents=True, exist_ok=False)
    reader_bytes = args.reader_source.read_bytes()
    (args.output / "reader-source.py").write_bytes(reader_bytes)
    (args.output / "reproducer-source.py").write_bytes(Path(__file__).read_bytes())
    spec = importlib.util.spec_from_file_location("publication_fixture_reader", args.reader_source)
    reader_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader_module)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes, close.restype = [wintypes.HANDLE], wintypes.BOOL
    rename = kernel.SetFileInformationByHandle
    rename.argtypes, rename.restype = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD], wintypes.BOOL
    replace = kernel.ReplaceFileW
    replace.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID]
    replace.restype = wintypes.BOOL

    def publish(source, destination):
        if args.api == "replacefile":
            if not replace(str(destination), str(source), None, 0, None, None):
                raise ctypes.WinError(ctypes.get_last_error())
            return
        handle = create(str(source), 0x10000, 7, None, 3, 0x80, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            name = str(destination.resolve()).encode("utf-16-le")
            size = RenameInfo.FileName.offset + len(name) + 2
            data = ctypes.create_string_buffer(size)
            information = ctypes.cast(data, ctypes.POINTER(RenameInfo)).contents
            information.Flags, information.RootDirectory, information.FileNameLength = 3, None, len(name)
            ctypes.memmove(ctypes.addressof(data) + RenameInfo.FileName.offset, name, len(name))
            if not rename(handle, 22, data, size):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            if not close(handle):
                raise ctypes.WinError(ctypes.get_last_error())

    stop, ready = threading.Event(), threading.Barrier(5)
    readers, publications = [], []
    with tempfile.TemporaryDirectory(prefix="memory-namespace-publish-") as temporary:
        folder = Path(temporary)
        destination, source = folder / "列车-🚆.json", folder / "snapshot.tmp"
        destination.write_bytes(b'{"epoch":0,"complete":true}\n')
        def observe(index):
            attempts, successes, failures = 0, 0, []
            ready.wait()
            while not stop.is_set():
                attempts += 1
                try:
                    value = json.loads(reader_module.read_snapshot_bytes(destination))
                    if value.get("complete") is not True:
                        raise ValueError("Read an incomplete snapshot payload.")
                    successes += 1
                except BaseException as error:
                    failures.append({"reader": index, "attempt": attempts, "time_ns": time.perf_counter_ns(),
                                     "exception": repr(error), "winerror": getattr(error, "winerror", None),
                                     "path_exists_immediately_after": destination.exists()})
            readers.append({"reader": index, "attempts": attempts, "successes": successes, "failures": failures})
        threads = [threading.Thread(target=observe, args=(index,)) for index in range(4)]
        for thread in threads:
            thread.start()
        ready.wait()
        started = time.monotonic()
        try:
            for epoch in range(1, args.publications + 1):
                source.write_bytes((json.dumps({"epoch": epoch, "complete": True}) + "\n").encode())
                before = time.perf_counter_ns()
                try:
                    publish(source, destination)
                    error = None
                except OSError as failure:
                    error = repr(failure)
                publications.append({"epoch": epoch, "start_ns": before, "end_ns": time.perf_counter_ns(), "error": error})
                if error is not None:
                    break
        finally:
            stop.set()
            for thread in threads:
                thread.join()
        failures = [failure for reader in readers for failure in reader["failures"]]
        for name, rows in (("publications.jsonl", publications), ("reader-failures.jsonl", failures)):
            (args.output / name).write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        report = {"timestamp": dt.datetime.now(dt.timezone.utc).isoformat(), "api": args.api,
                  "reader_source_sha256": hashlib.sha256(reader_bytes).hexdigest(), "elapsed_seconds": time.monotonic() - started,
                  "publications": len(publications), "publisher_failures": sum(row["error"] is not None for row in publications),
                  "reader_successes": sum(reader["successes"] for reader in readers), "reader_failures": len(failures),
                  "struct_offsets": {field: getattr(RenameInfo, field).offset for field in ("Flags", "RootDirectory", "FileNameLength", "FileName")},
                  "limits": "Independent Win32 fixture only. Every failed reader attempt is retained; no retry within an attempt. No game or JVM access."}
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report))


if __name__ == "__main__":
    main()
