"""Prepare and launch a fresh ordinary NeoForge client using fingerprinted packaged JARs."""
import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import uuid
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def timestamp():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()


def verified_artifact(path, matrix):
    identity = read(path.with_suffix(".build.json"))
    target = matrix["targets"][identity["target"]]
    if target["variant"] != "official" or identity["sha256"] != digest(path):
        raise ValueError("Require a fingerprinted official-target companion.")
    with zipfile.ZipFile(path) as archive:
        embedded = json.loads(archive.read("mtr-memory-target.json"))
    for key in ("target", "version", "mtrSha256", "neoForge"):
        if embedded[key] != identity[key]:
            raise ValueError(f"Packaged identity mismatch: {key}")
    if identity["mtrSha256"] != matrix["mtr"]["official"]["sha256"] or identity["neoForge"] != target["neoForge"]:
        raise ValueError("Artifact differs from the audited target matrix.")
    if identity["java"] != matrix["java"] or embedded["minecraft"] != matrix["minecraft"]:
        raise ValueError("Packaged Java/Minecraft target differs from the matrix.")
    return identity


def prepare(args):
    source, instance = args.source.resolve(), args.instance.resolve()
    if instance.exists() or instance == source or source in instance.parents:
        raise ValueError("Use a fresh instance outside the source checkout.")
    matrix = read(ROOT / "config/targets.json")
    identity = verified_artifact(args.companion.resolve(), matrix)
    marker = read(source / "vehicle-test-instance.json")
    if pathlib.Path(marker["instance"]).resolve() != source or marker["loader"] != identity["neoForge"]:
        raise ValueError("Source client identity/loader mismatch.")
    if marker.get("pid"):
        active = subprocess.run(["pwsh", "-NoProfile", "-Command",
                                 f"Get-Process -Id {int(marker['pid'])} -ErrorAction SilentlyContinue"], capture_output=True)
        if active.stdout.strip():
            raise ValueError("Source process must be stopped before copying its world.")
    java = pathlib.Path(marker["java"])
    version = subprocess.run([str(java), "-version"], capture_output=True, text=True, check=True)
    if 'version "21.' not in version.stderr:
        raise ValueError("Require the observed Java 21 runtime.")
    loader_version = "neoforge-" + identity["neoForge"]
    if not (source / "versions" / loader_version / (loader_version + ".json")).is_file():
        raise ValueError("Prepared source lacks exact loader metadata.")
    mtr_files = [path for path in (source / "mods").glob("*.jar") if digest(path) == identity["mtrSha256"]]
    if len(mtr_files) != 1:
        raise ValueError("Require exactly one hash-matching official MTR JAR.")
    world = None
    profile = next((entry for entry in read(source / "usercache.json") if entry["name"] == args.username), None)
    if profile is None:
        raise ValueError("Select a profile from the isolated source client's usercache.")
    destinations = [mtr_files[0].name, args.companion.name, *[path.name for path in args.observer]]
    if args.probe:
        destinations.append(args.probe.name)
    if len(set(destinations)) != len(destinations):
        raise ValueError("Supplied mod filenames overlap.")
    for observer in [*args.observer, *([args.probe] if args.probe else [])]:
        if not observer.is_file():
            raise ValueError("A supplied probe/observer is missing.")
    if args.world:
        if pathlib.Path(args.world).name != args.world or not (source / "saves" / args.world / "level.dat").is_file():
            raise ValueError("Select an existing direct-child source world.")
        world = {"name": args.world, "files": {str(path.relative_to(source / "saves" / args.world)): digest(path)
                  for path in sorted((source / "saves" / args.world).rglob("*")) if path.is_file()}}
    packs = []
    if args.catalogue:
        catalogue = read(args.catalogue)
        if catalogue["passed"] is not True or catalogue["target"]["mtr"] != matrix["mtr"]["official"]["version"]:
            raise ValueError("Require the verified official native catalogue.")
        for entry in catalogue["packs"]:
            path = args.catalogue.parent / entry["output"]
            if path.name != entry["output"] or digest(path) != entry["output_sha256"]:
                raise ValueError("Catalogue archive fingerprint mismatch.")
            packs.append({"source": str(path.resolve()), "filename": path.name, "sha256": digest(path)})
    instance.mkdir(parents=True)
    for name in ("assets", "libraries", "versions"):
        print(f"Copying prepared {name}", flush=True)
        shutil.copytree(source / name, instance / name)
    for name in ("config", "defaultconfigs"):
        if (source / name).is_dir():
            shutil.copytree(source / name, instance / name)
    if world:
        shutil.copytree(source / "saves" / args.world, instance / "saves" / args.world)
    (instance / "mods").mkdir()
    (instance / "resourcepacks").mkdir()
    mtr = instance / "mods" / mtr_files[0].name
    shutil.copyfile(mtr_files[0], mtr)
    if args.expect_binary_rejection:
        with zipfile.ZipFile(mtr, "a") as archive:
            archive.comment = b"Memory Saver isolated same-version fingerprint negative control"
    shutil.copyfile(args.companion, instance / "mods" / args.companion.name)
    if args.probe:
        shutil.copyfile(args.probe, instance / "mods" / args.probe.name)
    for observer in args.observer:
        shutil.copyfile(observer, instance / "mods" / observer.name)
    for pack in packs:
        shutil.copyfile(pack["source"], instance / "resourcepacks" / pack["filename"])
    options = (source / "options.txt").read_text(encoding="utf-8-sig").splitlines()
    values = dict(line.split(":", 1) for line in options if ":" in line)
    values["resourcePacks"] = json.dumps(["vanilla", *["file/" + pack["filename"] for pack in packs]], ensure_ascii=False)
    (instance / "options.txt").write_text("\n".join(f"{key}:{value}" for key, value in values.items()) + "\n", encoding="utf-8")
    manifest = {"timestamp": timestamp(), "instance": str(instance), "source": str(source),
                "artifact": identity, "java": str(java), "java_version": version.stderr,
                "world": world, "packs": packs, "options_sha256": digest(instance / "options.txt"),
                "profile": {"username": profile["name"], "uuid": profile["uuid"]},
                "heap_mib": args.heap_mib, "jfr": args.jfr, "smoke": args.smoke,
                "expected_binary_rejection": args.expect_binary_rejection,
                "mods": [{"filename": path.name, "sha256": digest(path)} for path in sorted((instance / "mods").glob("*.jar"))],
                "source_hash": digest(pathlib.Path(__file__))}
    write(instance / "packaged-client-plan.json", manifest)
    write(instance / "vehicle-test-instance.json", {"instance": str(instance), "mod_loader": "neoforge",
          "target": {"minecraft": matrix["minecraft"], "mtr": matrix["mtr"]["official"]["version"]},
          "loader": identity["neoForge"], "java": str(java), "pid": None, "packs": packs,
          "session_kind": "SDK development test profile; local gameplay only"})
    if args.smoke:
        write(instance / "loader-lifecycle-request.json", {"run": str(uuid.uuid4()), "scope": "Actual packaged companion; base resources; no gameplay certification", "faults": args.faults})
    print(json.dumps({"prepared": str(instance), "plan": str(instance / "packaged-client-plan.json")}), flush=True)


def launch(args):
    import minecraft_launcher_lib as launcher
    instance = args.instance.resolve()
    plan = read(instance / "packaged-client-plan.json")
    if pathlib.Path(plan["instance"]) != instance or (instance / "packaged-client-launch.json").exists():
        raise ValueError("Require this fresh prepared instance, with no prior launch.")
    for mod in plan["mods"]:
        if digest(instance / "mods" / mod["filename"]) != mod["sha256"]:
            raise ValueError("Prepared mod bytes changed before launch.")
    for pack in plan["packs"]:
        if digest(instance / "resourcepacks" / pack["filename"]) != pack["sha256"]:
            raise ValueError("Prepared archive bytes changed before launch.")
    if digest(instance / "options.txt") != plan["options_sha256"]:
        raise ValueError("Prepared settings changed before launch.")
    if plan["world"]:
        world = instance / "saves" / plan["world"]["name"]
        actual = {str(path.relative_to(world)): digest(path) for path in sorted(world.rglob("*")) if path.is_file()}
        if actual != plan["world"]["files"]:
            raise ValueError("Prepared world snapshot changed before launch.")
    arguments = ["-Xms512M", f"-Xmx{plan['heap_mib']}M", "-Dmtr.memory.acceptance=true"]
    if plan["smoke"]:
        arguments.append("-Dmtr.memory.acceptance.exit=true")
    if plan["jfr"]:
        arguments += ["-XX:StartFlightRecording=name=acceptance,settings=profile,disk=true,dumponexit=true,filename=acceptance.jfr",
                      "-Xlog:gc*,safepoint:file=acceptance-gc.log:time,uptime,level,tags:filecount=0"]
    options = {**plan["profile"], "token": "0", "executablePath": plan["java"], "gameDirectory": str(instance),
               "jvmArguments": arguments, "customResolution": True, "resolutionWidth": "1280", "resolutionHeight": "720",
               "disableMultiplayer": True}
    if plan["world"]:
        options["quickPlaySingleplayer"] = plan["world"]["name"]
    command = launcher.command.get_minecraft_command("neoforge-" + plan["artifact"]["neoForge"], str(instance), options)
    with (instance / "launch.stdout.log").open("wb") as stdout, (instance / "launch.stderr.log").open("wb") as stderr:
        process = subprocess.Popen(command, cwd=instance, stdout=stdout, stderr=stderr,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    launched = {"timestamp": timestamp(), "pid": process.pid, "plan_sha256": digest(instance / "packaged-client-plan.json"),
                "jvm_arguments": arguments, "command": command}
    write(instance / "packaged-client-launch.json", launched)
    marker = read(instance / "vehicle-test-instance.json")
    marker["pid"] = process.pid
    write(instance / "vehicle-test-instance.json", marker)
    print(json.dumps({"pid": process.pid, "instance": str(instance)}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    preparation = commands.add_parser("prepare")
    preparation.add_argument("--source", type=pathlib.Path, required=True)
    preparation.add_argument("--instance", type=pathlib.Path, required=True)
    preparation.add_argument("--companion", type=pathlib.Path, required=True)
    preparation.add_argument("--probe", type=pathlib.Path)
    preparation.add_argument("--observer", type=pathlib.Path, action="append", default=[])
    preparation.add_argument("--catalogue", type=pathlib.Path)
    preparation.add_argument("--world")
    preparation.add_argument("--username", required=True)
    preparation.add_argument("--heap-mib", type=int, default=3072)
    preparation.add_argument("--jfr", action="store_true")
    preparation.add_argument("--smoke", action="store_true")
    preparation.add_argument("--faults", action="store_true")
    preparation.add_argument("--expect-binary-rejection", action="store_true")
    launching = commands.add_parser("launch")
    launching.add_argument("--instance", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        if args.heap_mib < 1024 or (args.smoke and not args.probe) or (args.faults and not args.smoke):
            parser.error("Require a valid heap and a probe for smoke acceptance.")
        prepare(args)
    else:
        launch(args)


if __name__ == "__main__":
    main()
