"""Preserve route-03 failure evidence; never change the source fixture or JFR chunks."""
import datetime as dt
import hashlib
import json
import pathlib
import shutil
import struct
import subprocess
import sys

OUT = pathlib.Path(__file__).resolve().parent
ROOT = OUT.parents[2]
INSTANCE = ROOT / ".cache/acceptance/official-nf248-full-native-046-profile"
REPOSITORY = pathlib.Path("C:/Users/ben_l/AppData/Local/Temp/2026_11_15_04_59_08_34668")
JDK = pathlib.Path("C:/Users/ben_l/Saved Games/Yuuniverse 1.20.1 Shenyang/porting-output/work/tools/jdk21/jdk-21.0.11+10")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def command(name, args):
    start = dt.datetime.now(dt.timezone.utc).isoformat()
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    (OUT / (name + ".stdout.log")).write_bytes(result.stdout)
    (OUT / (name + ".stderr.log")).write_bytes(result.stderr)
    return {"command": args, "started": start, "ended": dt.datetime.now(dt.timezone.utc).isoformat(),
            "exit_code": result.returncode}


if (OUT / "capture.json").exists():
    raise SystemExit("Use a fresh evidence directory; capture.json already exists.")
report = {"timestamp": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
          "source_sha256": sha(pathlib.Path(__file__)), "instance": str(INSTANCE),
          "source_repository": str(REPOSITORY), "files": [], "chunks": [], "commands": []}
for source in (INSTANCE / "logs/latest.log", INSTANCE / "launch.stdout.log", INSTANCE / "launch.stderr.log",
               INSTANCE / "acceptance-gc.log", INSTANCE / "acceptance.jfr",
               INSTANCE / "game-probe/packaged-observer.json", INSTANCE / "game-probe/live.json"):
    if source.exists():
        destination = OUT / "raw-runtime" / source.relative_to(INSTANCE)
        destination.parent.mkdir(parents=True, exist_ok=True)
        original = sha(source)
        shutil.copy2(source, destination)
        if sha(source) != original or sha(destination) != original:
            raise RuntimeError("Source changed during capture: " + str(source))
        report["files"].append({"source": str(source), "path": destination.relative_to(OUT).as_posix(),
                                "sha256": original, "bytes": destination.stat().st_size})

raw_chunks = OUT / "raw-jfr-chunks"
raw_chunks.mkdir()
complete_dir = ROOT / ".cache/recovery/engineering-048-route03-complete-chunks"
complete_dir.mkdir(parents=True, exist_ok=False)
for source in sorted(REPOSITORY.glob("*.jfr")):
    destination = raw_chunks / source.name
    original = sha(source)
    shutil.copy2(source, destination)
    if sha(source) != original or sha(destination) != original:
        raise RuntimeError("JFR changed during capture: " + str(source))
    with destination.open("rb") as stream:
        header = struct.unpack(">4sHHQQQQQQQI", stream.read(68))
    result = command("summary-" + source.stem, [str(JDK / "bin/jfr.exe"), "summary", str(destination)])
    report["commands"].append(result)
    report["chunks"].append({"source": str(source), "path": destination.relative_to(OUT).as_posix(),
        "sha256": original, "bytes": destination.stat().st_size, "jdk_summary_exit": result["exit_code"],
        "header": {"major": header[1], "minor": header[2], "chunk_size": header[3], "start_nanos": header[6],
                   "duration_nanos": header[7], "flags": header[10]},
        "readable_complete_chunk": result["exit_code"] == 0})
    if result["exit_code"] == 0:
        shutil.copy2(destination, complete_dir / source.name)
assembled = complete_dir.parent / "engineering-048-route03-readable-prefix.jfr"
report["commands"].append(command("assemble-readable-prefix", [str(JDK / "bin/jfr.exe"), "assemble", str(complete_dir), str(assembled)]))
if assembled.exists():
    report["assembled_readable_prefix"] = {"path": str(assembled), "sha256": sha(assembled), "bytes": assembled.stat().st_size}
    report["commands"].append(command("summary-readable-prefix", [str(JDK / "bin/jfr.exe"), "summary", str(assembled)]))
save(OUT / "capture.json", report)
print(json.dumps({"chunks": len(report["chunks"]), "readable_chunks": sum(x["readable_complete_chunk"] for x in report["chunks"]),
                  "assembled": report.get("assembled_readable_prefix")}, indent=2))
