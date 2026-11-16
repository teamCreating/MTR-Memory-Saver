"""Read the reviewed FML native log as one byte-preserving rolling stream.

Archives and the active prefix are evidence inputs, never replacement log files.
Unsupported layouts, foreign launches and lost/changed observed bytes fail closed.
"""
from dataclasses import dataclass
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import time
import xml.etree.ElementTree as ET
import zipfile
import zlib

import windows_snapshot_io

REVIEW_FILE = Path(__file__).resolve().parents[1] / "config/native-log-reader.json"


class LogIntegrityError(RuntimeError):
    pass


class PublicationChanged(Exception):
    pass


class LogNotAvailable(OSError):
    """An owned fresh JVM has not yet published its first logger header."""


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def write_once(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def file_identity(info):
    return [info.st_dev, info.st_ino]


def strict_gzip(raw, limit):
    try:
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        decoded = decoder.decompress(raw, limit+1)
    except zlib.error as error:
        raise LogIntegrityError("Published gzip CRC/deflate validation failed: "+str(error)) from error
    if len(decoded) > limit or decoder.unconsumed_tail:
        raise LogIntegrityError("Native log segment exceeds the frozen decompression limit.")
    if not decoder.eof or decoder.unused_data or len(raw) < 18:
        raise LogIntegrityError("Native log archive is truncated, concatenated or has trailing data.")
    crc, size = struct.unpack("<II", raw[-8:])
    if zlib.crc32(decoded) & 0xffffffff != crc or len(decoded) & 0xffffffff != size:
        raise LogIntegrityError("Native log gzip trailer differs from its exact decoded bytes.")
    return decoded, {"crc32": f"{crc:08x}", "isize": size}


@dataclass(frozen=True)
class Layout:
    active: str
    archive_pattern: str
    index_mode: str
    minimum: int
    maximum: int

    @classmethod
    def from_xml(cls, raw):
        xml = ET.fromstring(raw)
        candidates = [a for a in xml.findall("./Appenders/RollingRandomAccessFile") if a.get("fileName") == "logs/latest.log"]
        if len(candidates) != 1:
            raise LogIntegrityError("The reviewed native file appender is ambiguous or absent.")
        appender = candidates[0]
        policies = appender.find("Policies")
        if (appender.get("filePattern") != "logs/%d{yyyy-MM-dd}-%i.log.gz" or policies is None
                or {p.tag for p in policies} != {"TimeBasedTriggeringPolicy", "OnStartupTriggeringPolicy"}
                or any(p.attrib for p in policies)):
            raise LogIntegrityError("Native log layout/policies have no reviewed rolling contract.")
        strategy = appender.find("DefaultRolloverStrategy")
        if strategy is None or strategy.get("fileIndex") != "min" or strategy.get("max") != "99" or set(strategy.attrib) != {"fileIndex", "max"}:
            raise LogIntegrityError("Native archive index strategy differs from the reviewed min strategy.")
        return cls(appender.get("fileName"), appender.get("filePattern"), "min", 1, 99)


@dataclass(frozen=True)
class Snapshot:
    data: bytes
    receipt: dict
    receipt_path: Path


def argument(command, name):
    locations = [i for i, item in enumerate(command) if item == name]
    if len(locations) != 1 or locations[0]+1 >= len(command):
        raise LogIntegrityError("Actual launch lacks a unique logging-profile argument: "+name)
    return command[locations[0]+1]


def reviewed_layout(instance, plan, launch):
    review_raw = REVIEW_FILE.read_bytes()
    review = json.loads(review_raw)
    command = launch["command"]
    profile = review["profiles"].get(argument(command, "--fml.neoForgeVersion"))
    if (review.get("schema") != 1 or not profile or argument(command, "--launchTarget") != profile["launch_target"]
            or argument(command, "--fml.fmlVersion") != profile["fml_version"]):
        raise LogIntegrityError("This launched loader has no reviewed native logging profile.")
    if Path(plan["instance"]).resolve() != Path(instance).resolve():
        raise LogIntegrityError("Log reader instance differs from the frozen launch plan.")
    classpath = [Path(p) for p in argument(command, "-cp").split(os.pathsep)]
    loader = [p for p in classpath if p.name == "loader-"+profile["fml_version"]+".jar" and "fancymodloader" in p.parts]
    core = [p for p in classpath if p.name.startswith("log4j-core-") and p.suffix == ".jar"]
    if len(loader) != 1 or len(core) != 1:
        raise LogIntegrityError("Actual logging dependency selection is ambiguous.")
    fingerprints = []
    for label, path, expected in (("fml_loader", loader[0], profile["loader_sha256"]), ("log4j_core", core[0], profile["core_sha256"])):
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected:
            raise LogIntegrityError("Actual logging dependency differs from its reviewed release: "+label)
        fingerprints.append({"role": label, "path": str(path), "sha256": actual})
    with zipfile.ZipFile(loader[0]) as jar:
        xml = jar.read(profile["xml_member"])
    if sha(xml) != profile["xml_sha256"]:
        raise LogIntegrityError("Actual FML logging XML differs from the reviewed release.")
    return Layout.from_xml(xml), review, xml, {"review_sha256": sha(review_raw), "dependencies": fingerprints,
                                             "xml_sha256": sha(xml), "profile": profile}


class NativeLogStream:
    def __init__(self, instance, layout, output, context, review, *, prefix_witness=None):
        self.instance, self.layout, self.output = Path(instance), layout, Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        self.review = review
        self.context = {**context, "layout": layout.__dict__, "header": review["header"]}
        self.previous = b""
        self.retired = {}
        self.number = 0
        self.anchor = None
        self.last = None
        self.active_identity = None
        self.active_prefix = b""
        self.header = re.compile(rb"^\[[^\r\n]*\] \[[^\r\n]*\] \["+re.escape(review["header"]["logger"].encode())+rb"\]: "+re.escape(review["header"]["message"].encode()))
        write_once(self.output / "context.json", canonical(self.context))
        self.context_sha256 = sha((self.output / "context.json").read_bytes())
        if prefix_witness is not None:
            source = Path(prefix_witness)
            witness = source.read_bytes()
            self._anchor(witness, {"kind": "external_existing_prefix", "source": str(source), "sha256": sha(witness)})

    @classmethod
    def from_launch(cls, instance, plan, launch, output, process, *, prefix_witness=None):
        instance = Path(instance).resolve()
        plan_raw = (instance / "packaged-client-plan.json").read_bytes()
        launch_raw = (instance / "packaged-client-launch.json").read_bytes()
        if json.loads(plan_raw) != plan or json.loads(launch_raw) != launch:
            raise LogIntegrityError("Native logging inputs differ from their actual frozen files.")
        layout, review, xml, configuration = reviewed_layout(instance, plan, launch)
        context = {"schema": 1, "instance": str(instance), "plan_sha256": sha(plan_raw),
                   "launch_sha256": sha(launch_raw), "process": process,
                   "configuration": configuration, "layout": layout.__dict__, "created_at": now(),
                   "source_sha256": sha(Path(__file__).read_bytes()), "review_sha256": sha(REVIEW_FILE.read_bytes())}
        if context["plan_sha256"] != launch["plan_sha256"] or process["pid"] != launch["pid"]:
            raise LogIntegrityError("Log reader context is not bound to the actual frozen launch.")
        result = cls(instance, layout, output, context, review, prefix_witness=prefix_witness)
        write_once(result.output / "plan.json", plan_raw)
        write_once(result.output / "launch.json", launch_raw)
        write_once(result.output / "log4j2.xml", xml)
        write_once(result.output / "review.json", REVIEW_FILE.read_bytes())
        return result

    def _anchor(self, raw, origin):
        if not raw or not raw.endswith(b"\n"):
            raise LogIntegrityError("A startup prefix witness must contain complete raw lines.")
        lines = raw.splitlines()
        if not self.header.match(lines[0]) or str(self.context["instance"]).encode("utf-8") not in lines[0] or sum(bool(self.header.match(line)) for line in lines) != 1:
            raise LogIntegrityError("Prefix witness lacks a unique startup header for this exact instance.")
        self.anchor = raw
        write_once(self.output / "anchor.bin", raw)
        write_once(self.output / "anchor.json", canonical({"origin": origin, "context_sha256": self.context_sha256,
                                                            "bytes": len(raw), "sha256": sha(raw), "header_sha256": sha(lines[0])}))

    def _namespace(self):
        directory = self.instance / Path(self.layout.active).parent
        result = {}
        try:
            paths = list(directory.iterdir())
        except FileNotFoundError:
            if self.anchor is None and not self.previous:
                raise LogNotAvailable("Fresh native logger directory has not been published.")
            raise
        for path in paths:
            match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})-(\d+)\.log(\.gz)?", path.name)
            if path.name == Path(self.layout.active).name or match:
                info = path.stat()
                if match:
                    try:
                        dt.date.fromisoformat(match[1])
                    except ValueError as error:
                        raise LogIntegrityError("Native archive name contains an invalid date.") from error
                result[path.name] = {"id": file_identity(info), "bytes": info.st_size, "mtime_ns": info.st_mtime_ns,
                                     "date": match[1] if match else None, "index": int(match[2]) if match else None,
                                     "temporary": bool(match and not match[3])}
        return result

    def _blob(self, raw):
        path = self.output / "blobs" / (sha(raw)+".bin")
        if path.exists():
            if path.read_bytes() != raw:
                raise LogIntegrityError("A frozen log blob changed.")
        else:
            write_once(path, raw)
        return path.relative_to(self.output).as_posix()

    def _capture(self):
        before = self._namespace()
        active = Path(self.layout.active).name
        if any(item["temporary"] for item in before.values()):
            raise PublicationChanged("Log4J2 archive compression still owns an uncompressed intermediate.")
        if active not in before:
            if not before and self.anchor is None and not self.previous:
                raise LogNotAvailable("Fresh native logger has not published its active file.")
            raise PublicationChanged("Active native log is temporarily absent.")
        archived = sorted((name for name in before if name != active), key=lambda name: (before[name]["date"], -before[name]["index"]))
        if archived and self.anchor is None:
            raise LogIntegrityError("Attaching after rollover requires an independent same-launch prefix witness.")
        pieces, segments, total = [], [], 0
        for name in [*archived, active]:
            path = self.instance / Path(self.layout.active).parent / name
            with windows_snapshot_io.open_snapshot(path) as stream:
                start = os.fstat(stream.fileno())
                if file_identity(start) != before[name]["id"]:
                    raise PublicationChanged("Log name changed before its owned read.")
                if start.st_size > self.review["limits"]["max_segment_bytes"]:
                    raise LogIntegrityError("Native log input exceeds the frozen segment limit.")
                raw = stream.read(start.st_size)
                finish = os.fstat(stream.fileno())
            if len(raw) != start.st_size or finish.st_size < start.st_size:
                raise PublicationChanged("Native log changed or shrank during its owned prefix read.")
            blob = self._blob(raw)
            extra = {}
            decoded = raw
            if name != active:
                if finish.st_size != start.st_size or finish.st_mtime_ns != start.st_mtime_ns:
                    raise PublicationChanged("Archive changed during its read.")
                decoded, extra = strict_gzip(raw, self.review["limits"]["max_segment_bytes"])
            if decoded and not decoded.endswith(b"\n"):
                raise PublicationChanged("Native log publication ends in an incomplete line.")
            total += len(decoded)
            if total > self.review["limits"]["max_stream_bytes"]:
                raise LogIntegrityError("Native logical stream exceeds its frozen size limit.")
            segments.append({"name": name, "file_id": file_identity(start), "stream_start": total-len(decoded), "stream_end": total,
                             "raw_bytes": len(raw), "raw_sha256": sha(raw),
                             "decoded_bytes": len(decoded), "decoded_sha256": sha(decoded), "blob": blob, **extra})
            pieces.append(decoded)
        after = self._namespace()
        if set(after) != set(before):
            raise PublicationChanged("Native log namespace changed during capture.")
        for name in before:
            if name != active and after[name] != before[name]:
                raise PublicationChanged("Native archive namespace changed during capture.")
        if after[active]["id"] != before[active]["id"] or after[active]["bytes"] < segments[-1]["raw_bytes"]:
            raise PublicationChanged("Active log rolled or shrank before capture completed.")
        for date in {before[name]["date"] for name in archived}:
            indices = sorted(before[name]["index"] for name in archived if before[name]["date"] == date)
            if indices != list(range(self.layout.minimum, max(indices)+1)) or indices[-1] > self.layout.maximum:
                raise LogIntegrityError("Published native archive sequence contains a gap or unsupported index.")
        data = b"".join(pieces)
        try:
            data.decode("utf-8")
        except UnicodeError as error:
            raise LogIntegrityError("Native log does not preserve the reviewed UTF-8 encoding.") from error
        if self.anchor is None:
            if not data:
                raise LogNotAvailable("Fresh native logger has not published a complete startup header.")
            self._anchor(data, {"kind": "first_fresh_active_log", "archives_present": False})
        if not data.startswith(self.anchor) or not data.startswith(self.previous):
            raise LogIntegrityError("Native log lost or changed an anchored/previously observed prefix.")
        if sum(bool(self.header.match(line)) for line in data.splitlines()) != 1:
            raise LogIntegrityError("Native logical log contains a foreign or duplicate startup.")
        retired = {tuple(segment["file_id"]): segment["raw_sha256"] for segment in segments[:-1]}
        if len(retired) != len(segments)-1:
            raise LogIntegrityError("Native archive namespace duplicates one file identity.")
        if any(retired.get(file_id) != digest for file_id, digest in self.retired.items()):
            raise LogIntegrityError("A previously observed retired segment was deleted, replaced or changed.")
        if self.active_identity is not None and segments[-1]["file_id"] != self.active_identity:
            old_start = self.last.receipt["segments"][-1]["stream_start"]
            migrated = any(tuple(segment["file_id"]) not in self.retired and segment["stream_start"] == old_start
                           and pieces[index].startswith(self.active_prefix)
                           for index, segment in enumerate(segments[:-1]))
            if not migrated:
                raise LogIntegrityError("The observed active log was replaced without a matching retired publication.")
        return data, segments, before, after, retired

    def read(self):
        self.number += 1
        attempts, started = [], now()
        for attempt in range(self.review["limits"]["publication_attempts"]):
            try:
                data, segments, before, after, retired = self._capture()
                receipt = {"schema": 1, "started_at": started, "completed_at": now(), "context_sha256": self.context_sha256,
                           "anchor_sha256": sha(self.anchor), "bytes": len(data), "sha256": sha(data), "segments": segments,
                           "namespace_before": before, "namespace_after": after, "publication_transitions": attempts}
                path = self.output / "captures" / f"{self.number:08d}.json"
                write_once(path, canonical(receipt))
                self.previous, self.retired = data, retired
                self.active_identity = segments[-1]["file_id"]
                self.active_prefix = data[segments[-1]["stream_start"]:]
                self.last = Snapshot(data, receipt, path)
                return self.last
            except LogNotAvailable as error:
                write_once(self.output / "captures" / f"{self.number:08d}-unavailable.json", canonical({"started_at": started,
                           "failed_at": now(), "error": repr(error), "publication_transitions": attempts}))
                raise
            except (PublicationChanged, FileNotFoundError) as error:
                attempts.append({"at": now(), "error": str(error)})
                if attempt+1 < self.review["limits"]["publication_attempts"]:
                    time.sleep(self.review["limits"]["publication_wait_seconds"])
            except BaseException as error:
                write_once(self.output / "captures" / f"{self.number:08d}-failed.json", canonical({"started_at": started,
                           "failed_at": now(), "error": repr(error), "publication_transitions": attempts}))
                raise
        write_once(self.output / "captures" / f"{self.number:08d}-failed.json", canonical({"started_at": started,
                   "failed_at": now(), "error": "No complete publication within the bounded capture attempts.", "publication_transitions": attempts}))
        raise LogIntegrityError("Native log did not publish a complete stable stream within its bounded capture attempts.")

    def reference(self):
        if self.last is None:
            raise LogIntegrityError("No complete native log publication has been captured.")
        return {"root": str(self.output), "context_sha256": self.context_sha256,
                "receipt": self.last.receipt_path.relative_to(self.output).as_posix(),
                "receipt_sha256": sha(self.last.receipt_path.read_bytes())}


def verify_capture(output, receipt_path):
    """Rebuild a preserved logical prefix from only its original sealed segments."""
    output, receipt_path = Path(output).resolve(), Path(receipt_path).resolve()
    if not receipt_path.is_relative_to(output):
        raise LogIntegrityError("Native log receipt escapes its evidence directory.")
    receipt = json.loads(receipt_path.read_bytes())
    context_raw, anchor_raw = (output / "context.json").read_bytes(), (output / "anchor.bin").read_bytes()
    context, anchor = json.loads(context_raw), json.loads((output / "anchor.json").read_bytes())
    if (receipt["context_sha256"] != sha(context_raw) or receipt["anchor_sha256"] != sha(anchor_raw)
            or anchor["context_sha256"] != sha(context_raw) or anchor["sha256"] != sha(anchor_raw)
            or anchor["bytes"] != len(anchor_raw)):
        raise LogIntegrityError("Native log context/anchor changed after capture.")
    segments, parts, offset = receipt["segments"], [], 0
    active = Path(context["layout"]["active"]).name
    names = [segment["name"] for segment in segments]
    if not names or names[-1] != active or set(names) != set(receipt["namespace_before"]) or len(names) != len(set(names)):
        raise LogIntegrityError("Native log segment inventory is incomplete or duplicated.")
    ordered = []
    for name in names[:-1]:
        matched = re.fullmatch(r"(\d{4}-\d{2}-\d{2})-(\d+)\.log\.gz", name)
        if not matched:
            raise LogIntegrityError("Native log receipt contains an unreviewed archive name.")
        ordered.append((matched[1], -int(matched[2]), name))
    if [value[2] for value in sorted(ordered)] != names[:-1]:
        raise LogIntegrityError("Native archive receipt order differs from fileIndex=min.")
    for date in {value[0] for value in ordered}:
        indices = sorted(-value[1] for value in ordered if value[0] == date)
        if indices != list(range(context["layout"]["minimum"], max(indices)+1)):
            raise LogIntegrityError("Native archive receipt has an index gap.")
    if set(receipt["namespace_before"]) != set(receipt["namespace_after"]):
        raise LogIntegrityError("Native capture crossed a namespace change.")
    for segment in segments:
        before, after = receipt["namespace_before"][segment["name"]], receipt["namespace_after"][segment["name"]]
        if segment["file_id"] != before["id"] or before["id"] != after["id"]:
            raise LogIntegrityError("Native receipt file identities disagree.")
        if segment["name"] != active and before != after:
            raise LogIntegrityError("A retired native segment changed during its captured read.")
        if not before["bytes"] <= segment["raw_bytes"] <= after["bytes"]:
            raise LogIntegrityError("Native source size frontiers disagree with captured bytes.")
        path = (output / segment["blob"]).resolve()
        if not path.is_relative_to(output):
            raise LogIntegrityError("Native log blob escapes its evidence directory.")
        raw = path.read_bytes()
        if sha(raw) != segment["raw_sha256"] or len(raw) != segment["raw_bytes"]:
            raise LogIntegrityError("Original native log segment bytes changed.")
        decoded = raw
        if segment["name"] != active:
            decoded, trailer = strict_gzip(raw, max(segment["decoded_bytes"], 1))
            if any(segment[key] != value for key, value in trailer.items()):
                raise LogIntegrityError("Native gzip trailer metadata changed.")
        if (sha(decoded) != segment["decoded_sha256"] or len(decoded) != segment["decoded_bytes"]
                or segment["stream_start"] != offset or segment["stream_end"] != offset+len(decoded)):
            raise LogIntegrityError("Native segment offsets/content changed.")
        offset += len(decoded)
        parts.append(decoded)
    data = b"".join(parts)
    if len(data) != receipt["bytes"] or sha(data) != receipt["sha256"] or not data.startswith(anchor_raw):
        raise LogIntegrityError("Reconstructed native logical prefix differs from the captured stream.")
    header = re.compile(rb"^\[[^\r\n]*\] \[[^\r\n]*\] \["+re.escape(context["header"]["logger"].encode())+rb"\]: "+re.escape(context["header"]["message"].encode()))
    if (not data or not header.match(data.splitlines()[0]) or sum(bool(header.match(line)) for line in data.splitlines()) != 1
            or str(context["instance"]).encode("utf-8") not in data.splitlines()[0]):
        raise LogIntegrityError("Reconstructed logical prefix lacks its unique same-launch header.")
    return data
