"""Read-only exact ZIP/comment and actual packaged wrong-binary evidence audit."""
import datetime as dt
import hashlib
import json
import pathlib
import re
import struct
import sys
import zipfile

EVIDENCE = pathlib.Path(__file__).resolve().parent
REPOSITORY = EVIDENCE.parents[2]
EXPECTED_ENTRY_COUNT = 12462


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(name, value):
    with (EVIDENCE / name).open("x", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write("\n")


def prefix_sha(path, length):
    answer = hashlib.sha256()
    with path.open("rb") as stream:
        remaining = length
        while remaining:
            block = stream.read(min(1024 * 1024, remaining))
            if not block:
                raise ValueError("Truncated ZIP prefix")
            answer.update(block)
            remaining -= len(block)
    return answer.hexdigest()


def zip_shape(path):
    size = path.stat().st_size
    with path.open("rb") as stream:
        tail_start = max(0, size - 65557)
        stream.seek(tail_start)
        tail = stream.read()
    index = tail.rfind(b"PK\x05\x06")
    if index < 0 or len(tail) - index < 22:
        raise ValueError("ZIP end-of-central-directory record missing")
    comment_length = struct.unpack_from("<H", tail, index + 20)[0]
    offset = tail_start + index
    if size != offset + 22 + comment_length:
        raise ValueError("Unexpected trailing ZIP bytes")
    return {"path": str(path), "bytes": size, "sha256": sha(path),
            "eocd_offset": offset, "unchanged_prefix_length": offset + 20,
            "prefix_sha256": prefix_sha(path, offset + 20),
            "comment_hex": tail[index + 22:].hex(), "comment_bytes": comment_length}


def entries(path):
    output = []
    with zipfile.ZipFile(path) as archive:
        for entry in archive.infolist():
            with archive.open(entry) as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            output.append({"name": entry.filename, "bytes": entry.file_size,
                           "crc32": f"{entry.CRC:08x}", "sha256": digest})
    return output


def main():
    before, after = read(EVIDENCE / "preflight.json"), read(EVIDENCE / "source-final-state.json")
    plan = read(EVIDENCE / "packaged-client-plan.json")
    retry_plan = read(EVIDENCE / "retry01/packaged-client-plan.json")
    expected_mtr = plan["artifact"]["mtrSha256"]
    originals = [path for path in (pathlib.Path(before["source"]) / "mods").glob("*.jar")
                 if sha(path) == expected_mtr]
    if len(originals) != 1:
        raise ValueError("Require exactly one original audited MTR JAR")
    original = originals[0]
    paths = [original]
    for current in (plan, retry_plan):
        candidates = [path for path in (pathlib.Path(current["instance"]) / "mods").glob("*.jar")
                      if path.name == original.name]
        if len(candidates) != 1:
            raise ValueError("Require the copied MTR JAR")
        paths.append(candidates[0])
    shapes = [zip_shape(path) for path in paths]
    original_entries = entries(original)
    comparisons = []
    for path, shape in zip(paths[1:], shapes[1:]):
        copied_entries = entries(path)
        equality = original_entries == copied_entries
        comment_only = (shape["eocd_offset"] == shapes[0]["eocd_offset"]
                        and shape["prefix_sha256"] == shapes[0]["prefix_sha256"]
                        and shape["comment_hex"] != shapes[0]["comment_hex"])
        comparisons.append({"path": str(path), "source_entries": len(original_entries),
                            "copied_entries": len(copied_entries), "ordered_entry_bytes_equal": equality,
                            "only_zip_comment_changed": comment_only,
                            "mismatches": [{"index": index, "source": source, "copied": copied}
                                           for index, (source, copied) in enumerate(zip(original_entries, copied_entries))
                                           if source != copied]})
    save("entry-comparison.json", {"expected_entry_count": EXPECTED_ENTRY_COUNT, "original": shapes[0],
         "copies": shapes[1:], "comparisons": comparisons,
         "ordered_source_entries": original_entries,
         "method": "Every ordered ZIP entry was streamed and compared by uncompressed size, CRC and SHA-256. Whole-file prefixes through the first 20 EOCD bytes are equal; only the ZIP comment length/content differs."})
    invocations = []
    for relative, current in ((".", plan), ("retry01", retry_plan)):
        directory = EVIDENCE / relative
        native = [(directory / name) for name in ("logs/latest.log", "logs/debug.log", "launch.stdout.log", "launch.stderr.log")]
        raw = b"\n".join(path.read_bytes() for path in native if path.is_file())
        stderr = (directory / "launch.stderr.log").read_bytes()
        exit_observation = read(directory / "packaged-client-exit.json")
        invocations.append({"relative_evidence_directory": relative, "pid": exit_observation["pid"],
          "launcher_exit_observation": exit_observation,
          "fatal_mixin_initialisation_error": b"org.spongepowered.asm.launch.MixinInitialisationError" in stderr,
          "preserved_fingerprint_cause": b"Loaded MTR fingerprint does not match the audited build target" in stderr,
          "actual_guard_frame": b"site.benli06.BinaryFingerprint.require" in stderr,
          "vehicle_registration_pattern": r"\bLoaded \d+ vehicles\b",
          "vehicle_registration_matches": [value.decode("ascii") for value in re.findall(rb"\bLoaded \d+ vehicles\b", raw)],
          "scope": {"smoke": current["smoke"], "packs": len(current["packs"]), "world": current["world"],
                    "jfr": current["jfr"], "native_memory_tracking": current.get("native_memory_tracking"),
                    "mod_files": [item["filename"] for item in current["mods"]]}})
    actual_exit = read(EVIDENCE / "retry01-java-exit-observation.json")
    source_unchanged = (before["source_marker_sha256"] == after["source_marker_sha256"]
                        and before["source_options_sha256"] == after["source_options_sha256"]
                        and after["source_process_absent"] and shapes[0]["sha256"] == expected_mtr)
    exact_companion = before["companion_sha256"] == plan["artifact"]["sha256"] == retry_plan["artifact"]["sha256"]
    for current in (plan, retry_plan):
        companion = pathlib.Path(current["instance"]) / "mods" / current["artifact"]["artifact"]
        exact_companion = exact_companion and sha(companion) == current["artifact"]["sha256"]
    tool_unchanged = before["tool_sha256"] == after["tool_sha256"] == sha(EVIDENCE / "packaged-client-tool.py")
    logs_pass = all(value["fatal_mixin_initialisation_error"] and value["preserved_fingerprint_cause"]
                    and value["actual_guard_frame"] and not value["vehicle_registration_matches"]
                    for value in invocations)
    archive_pass = len(original_entries) == EXPECTED_ENTRY_COUNT and all(
        value["source_entries"] == value["copied_entries"] == EXPECTED_ENTRY_COUNT
        and value["ordered_entry_bytes_equal"] and value["only_zip_comment_changed"] for value in comparisons)
    scope_pass = all(value["scope"]["smoke"] is False and value["scope"]["packs"] == 0
                     and value["scope"]["world"] is None and value["scope"]["jfr"] is False
                     and value["scope"]["native_memory_tracking"] is None
                     and len(value["scope"]["mod_files"]) == 2 for value in invocations)
    exit_pass = actual_exit["exited"] is True and actual_exit["exit_code"] == 1 and actual_exit["handle_retained_before_wait"] is True
    assessment = {"timestamp": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
      "target": {"minecraft": "1.21.1", "mtr": "4.1.0-beta.2", "neoforge": "21.1.248", "companion": "0.4.6"},
      "passed": all((logs_pass, archive_pass, scope_pass, exit_pass, source_unchanged, exact_companion, tool_unchanged)),
      "gates": {"fatal_guard_before_native_vehicle_registration": logs_pass, "exact_zip_comment_control": archive_pass,
                "probe_pack_world_jfr_absent": scope_pass, "actual_java_exit_1": exit_pass,
                "source_unchanged": source_unchanged, "exact_companion": exact_companion, "tool_bytes_unchanged": tool_unchanged},
      "companion_sha256": before["companion_sha256"], "audited_mtr_sha256": expected_mtr,
      "tool_source_sha256": before["tool_sha256"], "audit_source_sha256": sha(pathlib.Path(__file__)),
      "source_before": before, "source_after": after, "invocations": invocations, "actual_exit_observation": actual_exit,
      "preserved_failures": [{"evidence": "launch-execution.json", "reason": "PATH Python lacked minecraft_launcher_lib; no Java process was created."},
                             {"evidence": "initial-java-assessment.json", "reason": "First actual Java invocation timed out at the configured 30-second launcher wait; its later exact exit code was not captured."}],
      "limits": ["This is startup rejection for a same-version ZIP-comment fingerprint mismatch, without probe/resources/world/profiling. It does not certify full-pack, route or performance behavior.",
                 "The configured launcher exit observation still reports its genuine timeout where applicable; the fresh retry has an independently retained Windows process handle and actual ExitCode."]}
    save("assessment.json", assessment)
    save("audit-execution.json", {"timestamp": assessment["timestamp"], "python": sys.executable,
         "python_version": sys.version, "command": sys.argv, "cwd": str(pathlib.Path.cwd()),
         "source_sha256": assessment["audit_source_sha256"], "passed": assessment["passed"]})
    index = {str(path.relative_to(EVIDENCE)).replace("\\", "/"): sha(path)
             for path in sorted(EVIDENCE.rglob("*")) if path.is_file() and path.name != "evidence-index.json"}
    save("evidence-index.json", {"sha256": index, "self_excluded": True})
    print(json.dumps({"passed": assessment["passed"], "gates": assessment["gates"],
                      "actual_exit": actual_exit, "source_entry_count": len(original_entries),
                      "indexed_files": len(index)}, ensure_ascii=False))
    return 0 if assessment["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
