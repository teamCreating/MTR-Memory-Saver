"""Exercise real Windows replacement semantics without launching a client."""
import os
import ctypes
from ctypes import wintypes
import pathlib
import tempfile
import unittest

from windows_snapshot_io import open_snapshot, read_snapshot_bytes


@unittest.skipUnless(os.name == "nt", "Windows file sharing semantics")
class WindowsSnapshotSharingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="memory-snapshot-sharing-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = pathlib.Path(self.temporary.name)
        self.destination = self.directory / "snapshot.json"
        self.replacement = self.directory / "replacement.json"
        self.original = b'{"epoch":1}'
        self.updated = b'{"epoch":2}'
        self.destination.write_bytes(self.original)
        self.replacement.write_bytes(self.updated)

    def test_ordinary_python_reader_reproduces_denied_atomic_replacement(self):
        with self.destination.open("rb") as reader:
            with self.assertRaises(PermissionError) as failure:
                os.replace(self.replacement, self.destination)
            self.assertEqual(failure.exception.winerror, 5)
            self.assertEqual(reader.read(), self.original)
        self.assertEqual(self.destination.read_bytes(), self.original)
        self.assertEqual(self.replacement.read_bytes(), self.updated)

    def test_shared_reader_still_exposes_movefileex_overwrite_limitation(self):
        with open_snapshot(self.destination) as reader:
            with self.assertRaises(PermissionError) as failure:
                os.replace(self.replacement, self.destination)
            self.assertEqual(failure.exception.winerror, 5)
            self.assertEqual(reader.read(), self.original)

    def test_shared_reader_allows_replacefile_and_preserves_one_file_version(self):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        replace = kernel.ReplaceFileW
        replace.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                            wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID]
        replace.restype = wintypes.BOOL
        with open_snapshot(self.destination) as reader:
            if not replace(str(self.destination), str(self.replacement), None, 0, None, None):
                raise ctypes.WinError(ctypes.get_last_error())
            self.assertEqual(reader.read(), self.original)
            self.assertEqual(read_snapshot_bytes(self.destination), self.updated)
        self.assertEqual(read_snapshot_bytes(self.destination), self.updated)

    def test_missing_snapshot_preserves_the_real_filesystem_error(self):
        with self.assertRaises(FileNotFoundError):
            read_snapshot_bytes(self.directory / "missing.json")


if __name__ == "__main__":
    unittest.main()
