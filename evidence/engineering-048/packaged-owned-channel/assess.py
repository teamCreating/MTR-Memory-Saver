"""Independently verify preserved packaged-client receipts without launching a JVM."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import zipfile


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def require(value, message):
    if not value:
        raise ValueError(message)


def artifact(base, target):
    directory = base / "artifacts" / target
    manifest_path, = directory.glob("*.build.json")
    manifest = read(manifest_path)
    candidate = directory / manifest["artifact"]
    require(sha(candidate) == manifest["sha256"], "Changed candidate artifact")
    require(manifest["sha256"] == read(base / "review-spec.json")["candidate_sha256"][target],
            "Candidate differs from independent owned-channel artifact review")
    require(manifest["target"] == target, "Wrong candidate target")
    with zipfile.ZipFile(candidate) as archive:
        metadata = json.loads(archive.read("mtr-memory-target.json"))
        require(metadata["target"] == target and metadata["version"] == manifest["version"],
                "Candidate metadata differs from manifest")
        require(metadata["mtrSha256"] == manifest["mtrSha256"]
                and metadata["neoForge"] == manifest["neoForge"]
                and metadata["variant"] == "official", "Wrong candidate runtime dependencies")
        require(not any("probe" in name.lower() for name in archive.namelist()),
                "Observation probe leaked into product artifact")
    probe = read(directory / "probe-identity.json")
    require(probe["target"] == target and probe["version"] == manifest["version"]
            and sha(directory / probe["artifact"]) == probe["sha256"], "Changed probe artifact")
    for relative, digest in probe["inputs"].items():
        require(sha(base / "sources" / relative) == digest, "Changed sealed probe source: " + relative)
    return manifest, probe


def verify(base):
    cases = []
    runner_digests = {sha(path) for path in (base / "sources").glob("run_matrix*.py")}
    for target_directory in sorted((base / "artifacts").iterdir()):
        if not target_directory.is_dir():
            continue
        target = target_directory.name
        manifest, probe = artifact(base, target)
        for mode in ("faults", "mismatch"):
            directory = base / "runtime" / (target + "-" + mode)
            execution = read(directory / "execution.json")
            plan_path = directory / "packaged-client-plan.json"
            plan, launched, exited = (read(directory / name) for name in
                ("packaged-client-plan.json", "packaged-client-launch.json", "packaged-client-exit.json"))
            require(execution["target"] == target and execution["mode"] == mode,
                    "Wrong runtime case")
            require(execution["runner_sha256"] in runner_digests, "Unsealed runtime runner")
            require(execution["artifact_sha256"] == manifest["sha256"] == plan["artifact"]["sha256"],
                    "Wrong runtime candidate artifact")
            require(plan_path.read_bytes() == (base / "prepared" / (target + "-" + mode + ".json")).read_bytes(),
                    "Prepared plan changed")
            require(launched["plan_sha256"] == sha(plan_path)
                    and exited["launch_sha256"] == sha(directory / "packaged-client-launch.json"),
                    "Broken launch/exit fingerprint chain")
            require(execution["pid"] == launched["pid"] == exited["pid"], "Wrong process owner")
            require(instant(execution["process_identity"]["created"]) == instant(exited["process_created"]),
                    "Wrong process creation time")
            require(exited["observed_with_owned_handle"] is True and exited["running"] is False,
                    "Exit was not observed with the owned process handle")
            require(instant(execution["started"]) <= instant(launched["timestamp"])
                    <= instant(exited["timestamp"]) <= instant(execution["ended"]), "Invalid runtime timeline")
            require(plan["world"] is None and not plan["packs"] and plan["heap_mib"] == 3072
                    and plan["initial_heap_mib"] == 512, "Runtime scope/control mismatch")
            require(plan["scheduler_parallelism"] is None and plan["scheduler_max_pool_size"] is None,
                    "Unexpected scheduler controls")
            observations = [json.loads(line) for line in
                            (directory / "process-observations.jsonl").read_text(encoding="utf-8").splitlines()]
            require(observations and observations[0]["running"] is True
                    and observations[-1]["running"] is False
                    and observations[-1]["exit_code"] == exited["exit_code"] == execution["exit_code"],
                    "Incomplete actual process observations")
            require(all(instant(a["timestamp"]) < instant(b["timestamp"])
                        for a, b in zip(observations, observations[1:])), "Process observations regressed")
            for relative, expected in execution["source_sha256"].items():
                require(sha(base / "sources" / relative) == expected, "Changed sealed runtime source: " + relative)
            final_inputs = read(directory / "final-input-verification.json")
            require(final_inputs["passed"] is True and final_inputs["pid"] == launched["pid"]
                    and final_inputs["plan_sha256"] == sha(plan_path), "Missing final installed input verification")
            require(final_inputs["mods"] == plan["mods"]
                    and final_inputs["source_sha256"] == execution["source_sha256"],
                    "Final installed mod/source identities changed")
            roles = {item["role"]: item for item in plan["mods"]}
            require(roles["companion"]["sha256"] == manifest["sha256"], "Wrong installed companion")
            log = b"\n".join(path.read_bytes() for path in
                (directory / "logs/latest.log", directory / "launch.stdout.log", directory / "launch.stderr.log")
                if path.exists())
            case = {"target": target, "mode": mode, "pid": launched["pid"],
                    "process_created": exited["process_created"], "exit_code": exited["exit_code"],
                    "artifact_sha256": manifest["sha256"], "plan_sha256": sha(plan_path),
                    "process_observations": len(observations), "source_inputs_verified": len(execution["source_sha256"]),
                    "original_runner_passed": execution["passed"], "passed": True}
            if mode == "faults":
                require(set(roles) == {"companion", "mtr", "probe"}
                        and roles["probe"]["sha256"] == probe["sha256"]
                        and roles["mtr"]["sha256"] == manifest["mtrSha256"], "Wrong fault-client mod set")
                require(plan["smoke"] is True and plan["jfr"] is True
                        and plan["jfr_max_size_bytes"] == 0 and not plan["expected_binary_rejection"],
                        "Wrong fault-client policy")
                result = read(directory / "loader-lifecycle-result.json")
                request = read(directory / "loader-lifecycle-request.json")
                require(result["passed"] is True and result["request"] == request and request["faults"] is True,
                        "Failed or transplanted fault result")
                require(instant(launched["timestamp"]) <= instant(result["timestamp"]) <= instant(exited["timestamp"]),
                        "Fault result is outside actual runtime")
                require(len(result["checks"]) == 24 and len(result["strict_resource_checks"]) == 18
                        and all(value is True for value in [*result["checks"].values(), *result["strict_resource_checks"].values()]),
                        "Missing or failed packaged fault checks")
                detail = result["strict_resource_observations"]
                require(detail["workspace_after"]["used_bytes"] == 0
                        and detail["workspace_after"]["waiting_requests"] == 0, "Leaked text workspace")
                require(detail["oversized"]["failed_read"]["bytes_read"] == detail["decoded_limit"] + 1,
                        "Oversized fixture did not cross the real admission boundary")
                summary = directory / "jfr-summary"
                summary_execution = read(summary / "execution.json")
                require(summary_execution["exit_code"] == 0
                        and sha(directory / "acceptance.jfr") == final_inputs["jfr_sha256"], "JFR summary/identity failed")
                require(b"Version:" in (summary / "stdout.log").read_bytes()
                        and b"jdk.GarbageCollection" in (summary / "stdout.log").read_bytes(),
                        "JFR summary lacks parsed recording events")
                require(exited["exit_code"] == 0, "Fault-client exit failed")
                if execution["passed"] is not True:
                    require(execution.get("error", "").startswith("UnicodeDecodeError("),
                            "Original runner has an unrelated unresolved failure")
                    case["preserved_runner_failure"] = "Post-exit UnicodeDecodeError; independently verified raw receipts and JFR"
                case.update(lifecycle_checks=24, strict_resource_checks=18,
                            jfr_sha256=sha(directory / "acceptance.jfr"), settled_workspace=True)
            else:
                require(set(roles) == {"companion", "mtr"} and plan["expected_binary_rejection"] is True
                        and plan["smoke"] is False and plan["jfr"] is False, "Wrong negative-control policy")
                require(execution["passed"] is True and exited["exit_code"] == 1
                        and not (directory / "loader-lifecycle-result.json").exists(), "Binary rejection did not terminate early")
                require(b"MixinInitialisationError: MTR Memory Saver cannot apply this build to the loaded MTR binary" in log
                        and b"Loaded MTR fingerprint does not match the audited build target" in log
                        and f"mtr_memory_sharing@{manifest['version']}/site.benli06.CompatibilityPlugin.onLoad".encode("ascii") in log
                        and not re.search(rb"\bLoaded \d+ vehicles\b", log), "Missing fatal binary guard evidence")
                control = read(base / "prepare" / (target + "-mismatch") / "mtr-comment-control.json")
                require(control["original_sha256"] == manifest["mtrSha256"]
                        and control["modified_sha256"] == roles["mtr"]["sha256"]
                        and control["comment_only_change"] is True
                        and control["member_and_metadata_bytes_unchanged"] is True, "Invalid same-version binary negative control")
                require(final_inputs["mtr_comment_control"] == control, "Final binary control changed")
                case["rejected_before_registration"] = True
            cases.append(case)
    require(len(cases) == 4 and len({row["pid"] for row in cases}) == 4, "Incomplete/nonindependent case matrix")
    return {"schema_version": 1, "passed": True, "cases": cases,
            "lifecycle_checks": sum(row.get("lifecycle_checks", 0) for row in cases),
            "strict_resource_checks": sum(row.get("strict_resource_checks", 0) for row in cases),
            "binary_rejections": sum(row.get("rejected_before_registration", False) for row in cases),
            "scope": "Exact packaged 0.4.7 official base-resource fault lifecycle and same-version binary rejection. "
                     "No full-pack gameplay, full ResourceManager reload, endurance or performance acceptance."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "Use a fresh independent assessment output")
    result = verify(args.root.resolve())
    result.update(timestamp=datetime.now(timezone.utc).isoformat(), assessor_sha256=sha(Path(__file__)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "cases": len(result["cases"])}))
