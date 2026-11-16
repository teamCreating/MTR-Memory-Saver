"""Read-only-to-game Windows filesystem reproduction; changes only a temp fixture."""
import ctypes
from ctypes import wintypes
import json
import pathlib
import tempfile
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "tools"))
from windows_snapshot_io import open_snapshot

k = ctypes.WinDLL("kernel32", use_last_error=True)
k.MoveFileExW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
k.MoveFileExW.restype = wintypes.BOOL
k.ReplaceFileW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID]
k.ReplaceFileW.restype = wintypes.BOOL
k.DeleteFileW.argtypes = [wintypes.LPCWSTR]
k.DeleteFileW.restype = wintypes.BOOL

results = []
for operation in ("move_replace", "move_away", "replace_file", "delete"):
    with tempfile.TemporaryDirectory(prefix="memory-native-sharing-") as raw:
        root = pathlib.Path(raw)
        before, after, away = root / "snapshot", root / "replacement", root / "away"
        before.write_bytes(b"original")
        after.write_bytes(b"updated")
        with open_snapshot(before) as reader:
            if operation == "move_replace":
                success = k.MoveFileExW(str(after), str(before), 1)
            elif operation == "move_away":
                success = k.MoveFileExW(str(before), str(away), 0)
            elif operation == "replace_file":
                success = k.ReplaceFileW(str(before), str(after), None, 0, None, None)
            else:
                success = k.DeleteFileW(str(before))
            error = ctypes.get_last_error() if not success else 0
            results.append({"operation": operation, "success": bool(success), "winerror": error,
                            "held_reader": reader.read().decode(),
                            "destination_exists": before.exists(),
                            "destination": before.read_bytes().decode() if before.exists() else None})
print(json.dumps(results, indent=2))
