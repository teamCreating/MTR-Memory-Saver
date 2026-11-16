"""Freeze the actual two loader profiles and exact released logging bytecode."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).resolve().parent / "release-proof"
OUTPUT.mkdir(parents=True, exist_ok=False)
profiles = {"official-nf248": ROOT / ".cache/acceptance/official-nf248-owned-049c",
            "official-nf265": ROOT / ".cache/acceptance/official-nf265-faults-048-owned"}
proofs, blobs = {}, {}
for target, instance in profiles.items():
    folder = OUTPUT / target
    folder.mkdir()
    for name in ("vehicle-test-instance.json", "packaged-client-plan.json", "packaged-client-launch.json"):
        (folder / name).write_bytes((instance / name).read_bytes())
    launch = json.loads((folder / "packaged-client-launch.json").read_bytes())
    plan = json.loads((folder / "packaged-client-plan.json").read_bytes())
    command = launch["command"]
    version = command[command.index("--version")+1]
    version_path = instance / "versions" / version / (version+".json")
    (folder / "version-profile.json").write_bytes(version_path.read_bytes())
    cp = [Path(path) for path in command[command.index("-cp")+1].split(";")]
    selected = {"loader": next(p for p in cp if p.name.startswith("loader-") and "fancymodloader" in p.parts),
                "core": next(p for p in cp if p.name.startswith("log4j-core-"))}
    facts = {"instance": str(instance), "version_profile_source": str(version_path), "jvm_logging_properties": [v for v in command if v.startswith("-D") and "log4j" in v.lower()],
             "launch_target": command[command.index("--launchTarget")+1], "neoForge": command[command.index("--fml.neoForgeVersion")+1],
             "fml_version": command[command.index("--fml.fmlVersion")+1], "jars": {}}
    for role, source in selected.items():
        raw = source.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        artifact = OUTPUT / "binaries" / (digest+".jar")
        artifact.parent.mkdir(exist_ok=True)
        if not artifact.exists(): artifact.write_bytes(raw)
        facts["jars"][role] = {"source": str(source), "sha256": digest, "bytes": len(raw), "blob": artifact.relative_to(OUTPUT).as_posix()}
        if digest in blobs: continue
        blobs[digest] = True
        members = []
        with zipfile.ZipFile(artifact) as jar:
            if role == "loader":
                xml = jar.read("log4j2.xml")
                xml_path = OUTPUT / "classes" / role / "log4j2.xml"
                xml_path.parent.mkdir(parents=True, exist_ok=True)
                xml_path.write_bytes(xml)
                facts["xml_sha256"] = hashlib.sha256(xml).hexdigest()
                wanted = {"CommonLaunchHandler.class", "CommonClientLaunchHandler.class", "NeoForgeClientLaunchHandler.class"}
            else:
                wanted = {"DefaultRolloverStrategy.class", "DefaultRolloverStrategy$Builder.class", "AbstractRolloverStrategy.class",
                          "TimeBasedTriggeringPolicy.class", "FileRenameAction.class", "GzCompressAction.class", "RollingFileManager.class"}
            for member in jar.namelist():
                if Path(member).name not in wanted: continue
                value = jar.read(member)
                destination = OUTPUT / "classes" / role / member
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(value)
                java_class = member[:-6].replace("/", ".")
                argv = [str(Path(plan["java"]).with_name("javap.exe")), "-classpath", str(artifact), "-c", "-p", java_class]
                started = dt.datetime.now(dt.timezone.utc).isoformat()
                result = subprocess.run(argv, capture_output=True)
                transcript = destination.with_suffix(".javap.txt")
                transcript.write_bytes(result.stdout)
                transcript.with_suffix(".stderr.txt").write_bytes(result.stderr)
                receipt = {"started_at": started, "ended_at": dt.datetime.now(dt.timezone.utc).isoformat(), "argv": argv, "exit_code": result.returncode,
                           "jar_sha256": digest, "member": member, "class_sha256": hashlib.sha256(value).hexdigest(),
                           "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(), "stderr_sha256": hashlib.sha256(result.stderr).hexdigest()}
                transcript.with_suffix(".execution.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
                assert result.returncode == 0
                members.append(receipt)
        proofs[digest] = members
    with zipfile.ZipFile(selected["loader"]) as jar:
        facts["xml_sha256"] = hashlib.sha256(jar.read("log4j2.xml")).hexdigest()
    (folder / "profile-facts.json").write_text(json.dumps(facts, indent=2)+"\n", encoding="utf-8")
(OUTPUT / "assessment.json").write_text(json.dumps({"profiles": list(profiles), "unique_released_binaries": len(blobs), "bytecode_proofs": proofs,
    "scope": "Read-only exact release/configuration evidence; no game input, launch, restart or runtime mutation."}, indent=2)+"\n", encoding="utf-8")
print(json.dumps({"release_profiles": list(profiles), "unique_binaries": len(blobs)}))
