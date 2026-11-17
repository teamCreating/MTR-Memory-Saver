"""Prepare and launch a fresh ordinary NeoForge client using fingerprinted packaged JARs.

Profile recordings retain their complete history until stopped or dumped, with
explicit unlimited size retention instead of JDK 21's implicit 250 MiB cap.
"""
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
import importlib.metadata
from legacy_identity import verify_legacy_identity

ROOT = pathlib.Path(__file__).resolve().parents[1]
INPUT_DIRECTORIES = ("assets", "libraries", "versions", "config", "defaultconfigs")
JAVA_INJECTION_ENV = ("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS", "CLASSPATH")
PERFORMANCE_SCOPE = "packaged_client_performance_preparation"
FROZEN_JVM_PREFIXES = (
    "-xms", "-xmx", "-xx:initialheapsize", "-xx:maxheapsize", "-xx:minheapsize",
    "-xx:ram", "-xx:maxram", "-xx:minram", "-xx:initialram", "-xx:startflightrecording",
    "-xx:flightrecorder", "-xx:+flightrecorder", "-xx:-flightrecorder", "-xx:nativememorytracking",
    "-xlog", "-dmtr.memory.acceptance", "-djdk.virtualthreadscheduler.",
    "-djava.util.concurrent.forkjoinpool.common.", "-xx:flags", "-xx:vmoptionsfile",
)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def timestamp():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()


def verified_artifact(path, matrix, legacy_baseline=None, manifest_path=None):
    if legacy_baseline is not None:
        return verify_legacy_identity(path, matrix, legacy_baseline,
                                      read(ROOT / "config/legacy-baselines.json"), manifest_path)
    identity = read(manifest_path or path.with_suffix(".build.json"))
    if not isinstance(identity.get("target"), str):
        raise ValueError("Historical artifact requires explicit --legacy-baseline selection.")
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
    if (identity["java"] != matrix["java"] or embedded["minecraft"] != matrix["minecraft"]
            or ("java" in embedded and embedded["java"] != matrix["java"])
            or ("minecraft" in identity and identity["minecraft"] != matrix["minecraft"])):
        raise ValueError("Packaged Java/Minecraft target differs from the matrix.")
    if "variant" in embedded and embedded["variant"] != target["variant"]:
        raise ValueError("Packaged variant differs from the official target matrix.")
    return identity


def inventory(directory):
    """A full relative inventory detects changed, added and removed inputs."""
    directory = pathlib.Path(directory)
    if not directory.exists():
        return {"present": False, "directories": [], "files": {}}
    if directory.is_symlink() or (hasattr(directory, "is_junction") and directory.is_junction()) or not directory.is_dir():
        raise ValueError("Frozen input directory must be a real directory.")
    files, directories = {}, []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError("Frozen inputs may not redirect outside their inventory.")
        name = path.relative_to(directory).as_posix()
        if path.is_file():
            files[name] = digest(path)
        elif path.is_dir():
            directories.append(name)
        else:
            raise ValueError("Unsupported frozen filesystem entry.")
    return {"present": True, "directories": directories, "files": files}


def java_environment():
    values = {name: os.environ.get(name) for name in JAVA_INJECTION_ENV}
    if any(value not in (None, "") for value in values.values()):
        raise ValueError("Performance preparation requires empty JVM option injection environment.")
    return values


def java_runtime(java, observed_version):
    java = pathlib.Path(java).resolve()
    root = java.parent.parent
    if not java.is_file() or java.parent.name != "bin" or java.name not in ("java", "java.exe"):
        raise ValueError("Require a concrete Java executable inside the frozen runtime.")
    if not (root / "release").is_file() or not (root / "lib/modules").is_file():
        raise ValueError("Require complete JDK runtime release and modules.")
    native_jvm = ("bin/server/jvm.dll", "lib/server/libjvm.so", "lib/server/libjvm.dylib")
    if not any((root / name).is_file() for name in native_jvm):
        raise ValueError("Require the actual native JVM library.")
    if not all((root / name).is_dir() for name in ("bin", "lib", "conf")):
        raise ValueError("Require complete JDK bin/lib/conf directories.")
    return {"root": str(root), "executable": java.relative_to(root).as_posix(),
            "version": observed_version, "release_sha256": digest(root / "release"),
            "directories": {name: inventory(root / name) for name in ("bin", "lib", "conf")}}


def extra_jvm_arguments(arguments):
    forbidden = FROZEN_JVM_PREFIXES + ("-djava.home", "-djava.library.path", "-djava.security.",
                 "-djava.class.path", "-djdk.module.", "--class-path", "--module-path", "--module",
                 "--source", "--patch-module", "--upgrade-module-path", "-xbootclasspath", "-xrun",
                 "-classpath", "-cp", "-jar", "-javaagent", "-agentlib", "-agentpath")
    for argument in arguments:
        if (not isinstance(argument, str) or not argument.startswith("-") or "\x00" in argument
                or argument.lower().startswith(forbidden)
                or argument in ("-cp", "-classpath", "-jar", "-m", "-p", "--", "-")):
            raise ValueError("Additional JVM argument overrides a frozen control or launcher input.")
    return list(arguments)


def verify_generated_command(command, plan):
    arguments = jvm_arguments(plan)
    if not isinstance(command, list) or command[:len(arguments) + 1] != [plan["java"], *arguments]:
        raise ValueError("Generated launcher command does not preserve frozen JVM arguments.")
    if any(not isinstance(item, str) or item.startswith("@") or item.lower().startswith(FROZEN_JVM_PREFIXES)
           for item in command[len(arguments) + 1:]):
        raise ValueError("Loader command overrides frozen JVM controls or uses a response file.")
    return command


def verified_observer(path, identity, matrix, manifest_path=None):
    with zipfile.ZipFile(path) as archive:
        target = json.loads(archive.read("mtr-native-observer-target.json"))
        capabilities = json.loads(archive.read("capabilities.json"))
    manifest_path = pathlib.Path(manifest_path) if manifest_path else path.with_suffix(".build.json")
    manifest = read(manifest_path)
    expected = {"target": identity["target"], "minecraft": matrix["minecraft"], "java": matrix["java"],
                "neoForge": identity["neoForge"], "mtrSha256": identity["mtrSha256"]}
    if (target.get("schema_version") != 1 or target.get("probe_kind") != "official-native-observer"
            or target.get("variant") != "official" or target.get("mod_id") != "mtr_native_observer"
            or target.get("mtrVersion") != matrix["mtr"]["official"]["version"]
            or any(target.get(key) != value or manifest.get(key) != value for key, value in expected.items())
            or manifest.get("sha256") != digest(path) or manifest.get("artifact") != path.name
            or not isinstance(target.get("observer_version"), str) or not target["observer_version"]
            or manifest.get("observer_version") != target.get("observer_version")
            or manifest.get("schema_version") != 1):
        raise ValueError("Require a fingerprinted independent official observer for this exact target.")
    enabled = ("native_pending", "registration_counts", "native_epochs", "heap", "world", "train_state",
               "cache_state", "frame_jfr", "server_tick_jfr")
    unavailable = ("module_counters", "active_read_permits", "text_workspace")
    required = {**dict.fromkeys(enabled, True), **dict.fromkeys(unavailable, False)}
    if "diagnostics_schema" in target or "diagnostics_path" in target or "native_model_diagnostics" in capabilities.get("capabilities", {}):
        if (type(target.get("diagnostics_schema")) is not int or target["diagnostics_schema"] != 1
                or target.get("diagnostics_path") != "game-probe/native-invalid-model.jsonl"):
            raise ValueError("Independent observer diagnostic metadata differs from its supported live schema.")
        required["native_model_diagnostics"] = True
    if (capabilities.get("schema_version") != 1 or capabilities.get("probe_kind") != target["probe_kind"]
            or capabilities.get("capabilities") != required or manifest.get("capabilities") != required
            or any(type(value) is not bool for value in capabilities.get("capabilities", {}).values())
            or any(type(value) is not bool for value in manifest.get("capabilities", {}).values())
            or target.get("frame_event") != "mtrtest.ClientFrame"
            or target.get("server_tick_event") != "mtrtest.ServerTick"
            or target.get("snapshot_path") != "game-probe/native-observer.json"
            or target.get("epochs_path") != "game-probe/native-resource-epochs.jsonl"):
        raise ValueError("Independent observer capability contract differs from the frozen schema.")
    return {"target": target, "capabilities": required, "sha256": digest(path),
            "manifest_sha256": digest(manifest_path)}


def launcher_settings(plan):
    return {"profile": plan["profile"], "loader": "neoforge-" + plan["artifact"]["neoForge"],
            "customResolution": True, "resolutionWidth": str(plan.get("resolution_width", 1280)),
            "resolutionHeight": str(plan.get("resolution_height", 720)), "disableMultiplayer": True,
            "quickPlaySingleplayer": plan["world"]["name"] if plan["world"] else None, "token": "0"}


def launcher_implementation():
    import minecraft_launcher_lib as launcher
    directory = pathlib.Path(launcher.__file__).parent
    return {"distribution": "minecraft-launcher-lib",
            "version": importlib.metadata.version("minecraft-launcher-lib"),
            "sources": {path.relative_to(directory).as_posix(): digest(path) for path in sorted(directory.rglob("*.py"))}}


def launch_command(instance, plan):
    import minecraft_launcher_lib as launcher
    settings = launcher_settings(plan)
    options = {**settings["profile"], **{key: value for key, value in settings.items()
                                      if key not in ("profile", "loader") and value is not None},
               "executablePath": plan["java"], "gameDirectory": str(instance), "jvmArguments": jvm_arguments(plan)}
    command = launcher.command.get_minecraft_command(settings["loader"], str(instance), options)
    return verify_generated_command(command, plan) if plan.get("schema") == 2 else command


def command_template(command, instance, java):
    return ["{java}" if index == 0 and item == str(java) else item.replace(str(instance), "{instance}")
            for index, item in enumerate(command)]


def _comparison_controls(plan):
    if plan.get("schema") != 2 or plan.get("scope") != PERFORMANCE_SCOPE or plan.get("controls", {}).get("schema") != 1:
        raise ValueError("Performance comparison requires complete schema-2 preparation controls.")
    controls = plan["controls"]
    artifact = plan["artifact"]
    return {"schema": 1, "target": {key: artifact[key] for key in ("target", "java", "minecraft", "mtrSha256", "neoForge")},
            "runtime": {key: value for key, value in controls["runtime"].items() if key != "root"},
            "inputs": controls["inputs"], "jvm": controls["jvm"], "launcher": controls["launcher"],
            "context": {"declarations": controls["context"]["declarations"],
                        "source": {"sha256": controls["context"]["source"]["sha256"]}},
            "options_sha256": plan["options_sha256"],
            "packs": [{key: pack[key] for key in ("filename", "sha256")} for pack in plan["packs"]],
            "world": plan["world"],
            "native_catalogue_sha256": controls["native_catalogue"]["sha256"],
            "mods": [{key: mod[key] for key in ("filename", "sha256", "role")} for mod in plan["mods"]
                     if mod["role"] != "companion"],
            "preparation_sources": {key: value["sha256"] for key, value in controls["sources"].items()}}


def comparison_controls(plan):
    try:
        return _comparison_controls(plan)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("Incomplete schema-2 comparison controls.") from error


def controls_sha256(plan):
    canonical = json.dumps(comparison_controls(plan), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def direct_filename(name):
    if not isinstance(name, str) or pathlib.Path(name).name != name or name in ("", ".", "..") or ":" in name:
        raise ValueError("Prepared file must be a direct-child filename.")
    return name


def verify_prepared_inputs(instance, plan):
    instance = pathlib.Path(instance).resolve()
    for folder, entries in (("mods", plan["mods"]), ("resourcepacks", plan["packs"])):
        expected = {direct_filename(entry["filename"]): entry["sha256"] for entry in entries}
        actual = inventory(instance / folder)
        if len(expected) != len(entries) or actual["files"] != expected or actual["directories"]:
            raise ValueError(f"Prepared {folder} bytes/file set changed before launch.")
    if digest(instance / "options.txt") != plan["options_sha256"]:
        raise ValueError("Prepared settings changed before launch.")
    if plan["world"]:
        world = instance / "saves" / direct_filename(plan["world"]["name"])
        expected_files = {name.replace("\\", "/"): sha for name, sha in plan["world"]["files"].items()}
        if inventory(world)["files"] != expected_files:
            raise ValueError("Prepared world snapshot changed before launch.")


def verify_performance_controls(instance, plan):
    """Recheck preparation only; qualification and executed workload need real evidence."""
    try:
        expected_sha = controls_sha256(plan)
        controls = plan["controls"]
        if expected_sha != plan["controls_sha256"]:
            raise ValueError("Frozen comparison controls digest mismatch.")
        if pathlib.Path(plan["instance"]).resolve() != pathlib.Path(instance).resolve():
            raise ValueError("Frozen prepared instance identity mismatch.")
        if any(plan.get(key) for key in ("smoke", "expected_binary_rejection")):
            raise ValueError("Performance preparation cannot use negative or product-probe controls.")
        verify_prepared_inputs(instance, plan)
        required_jvm = ("initial_heap_mib", "heap_mib", "scheduler_parallelism", "scheduler_max_pool_size",
                        "extra_jvm_arguments", "jfr", "jfr_max_size_bytes", "native_memory_tracking")
        if any(key not in plan for key in required_jvm):
            raise ValueError("Incomplete explicit JVM controls.")
        if any(type(plan.get(key)) is not bool for key in ("jfr", "smoke", "expected_binary_rejection")):
            raise ValueError("Invalid explicit boolean preparation controls.")
        if set(controls["inputs"]) != set(INPUT_DIRECTORIES):
            raise ValueError("Incomplete prepared library/config inventory.")
        for name in INPUT_DIRECTORIES:
            if inventory(pathlib.Path(instance) / name) != controls["inputs"][name]:
                raise ValueError(f"Prepared {name} inventory changed before launch.")
        source_paths = {"packaged_client": pathlib.Path(__file__).resolve(), "legacy_identity": ROOT / "tools/legacy_identity.py",
                        "target_matrix": ROOT / "config/targets.json", "legacy_catalogue": ROOT / "config/legacy-baselines.json"}
        if set(controls["sources"]) != set(source_paths):
            raise ValueError("Incomplete preparation source identity.")
        for name, source in controls["sources"].items():
            if pathlib.Path(source["path"]).resolve() != source_paths[name].resolve():
                raise ValueError("Preparation source identity differs from this verifier.")
            if digest(pathlib.Path(source["path"])) != source["sha256"]:
                raise ValueError("Preparation source bytes changed before launch.")
        matrix = read(ROOT / "config/targets.json")
        companions = [mod for mod in plan["mods"] if mod["role"] == "companion"]
        observers = [mod for mod in plan["mods"] if mod["role"] == "observer"]
        mtr_mods = [mod for mod in plan["mods"] if mod["role"] == "mtr"]
        if len(companions) != 1 or len(observers) != 1 or len(mtr_mods) != 1 or len(plan["mods"]) != 3:
            raise ValueError("Performance controls require one companion and one independent frame provider.")
        if mtr_mods[0]["sha256"] != plan["artifact"]["mtrSha256"]:
            raise ValueError("Frozen official MTR identity mismatch.")
        if companions[0]["sha256"] != plan["artifact"]["sha256"]:
            raise ValueError("Frozen companion treatment mismatch.")
        manifest = pathlib.Path(instance) / ".prepared-controls/companion.build.json"
        actual_identity = verified_artifact(pathlib.Path(instance) / "mods" / companions[0]["filename"], matrix,
                                            plan["artifact"].get("legacy_baseline"), manifest)
        actual_identity = {**actual_identity, "artifact": companions[0]["filename"], "minecraft": matrix["minecraft"]}
        if not plan["artifact"].get("legacy_baseline"):
            actual_identity.update(identity_format="modern_embedded", module_api_capabilities={"status": "unassessed"})
        for key, value in actual_identity.items():
            if plan["artifact"].get(key) != value:
                raise ValueError("Frozen artifact identity mismatch.")
        if digest(manifest) != controls["companion_manifest_sha256"]:
            raise ValueError("Frozen artifact manifest changed before launch.")
        context = controls["context"]
        context_path = pathlib.Path(instance) / ".prepared-controls/context.json"
        if context["source"]["path"] != ".prepared-controls/context.json" or digest(context_path) != context["source"]["sha256"] or read(context_path) != context["declarations"]:
            raise ValueError("Frozen declared workload context changed before launch.")
        if not plan["world"] or not plan["packs"]:
            raise ValueError("Performance preparation requires declared world and catalogue packs.")
        catalogue = controls["native_catalogue"]
        catalogue_path = pathlib.Path(instance) / ".prepared-controls/catalogue.json"
        if catalogue["path"] != ".prepared-controls/catalogue.json" or digest(catalogue_path) != catalogue["sha256"]:
            raise ValueError("Frozen native catalogue source changed before launch.")
        catalogue_data = read(catalogue_path)
        if (catalogue_data["passed"] is not True or catalogue_data["target"]["mtr"] != matrix["mtr"]["official"]["version"]
                or [{"filename": entry["output"], "sha256": entry["output_sha256"]} for entry in catalogue_data["packs"]]
                != [{"filename": pack["filename"], "sha256": pack["sha256"]} for pack in plan["packs"]]):
            raise ValueError("Frozen native catalogue differs from prepared archive order/bytes.")
        observer_path = pathlib.Path(instance) / "mods" / observers[0]["filename"]
        # Observer manifest bytes are frozen outside mods, as loader inputs are JARs.
        observer_manifest = pathlib.Path(instance) / ".prepared-controls/observer.build.json"
        observer = verified_observer(observer_path, plan["artifact"], matrix, manifest_path=observer_manifest)
        if observer != controls["observer"]:
            raise ValueError("Frozen neutral observer identity mismatch.")
        version = subprocess.run([plan["java"], "-version"], capture_output=True, text=True, check=True)
        if java_runtime(plan["java"], version.stderr) != controls["runtime"]:
            raise ValueError("Frozen Java runtime bytes/version changed before launch.")
        if java_environment() != controls["jvm"]["environment"] or jvm_arguments(plan) != controls["jvm"]["arguments"]:
            raise ValueError("Frozen JVM arguments/environment changed before launch.")
        if (launcher_settings(plan) != controls["launcher"]["settings"]
                or launcher_implementation() != controls["launcher"]["implementation"]
                or command_template(launch_command(instance, plan), instance, plan["java"]) != controls["launcher"]["command_template"]):
            raise ValueError("Frozen launcher arguments/implementation changed before launch.")
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("Incomplete schema-2 performance preparation controls.") from error
    return True


def prepare(args):
    source, instance = args.source.resolve(), args.instance.resolve()
    if instance.exists() or instance == source or source in instance.parents:
        raise ValueError("Use a fresh instance outside the source checkout.")
    if any(path.suffix.lower() != ".jar" for path in [args.companion, *args.observer, *([args.probe] if args.probe else [])]):
        raise ValueError("Prepared companion/probe/observer files must be JARs.")
    matrix = read(ROOT / "config/targets.json")
    identity = verified_artifact(args.companion.resolve(), matrix, args.legacy_baseline)
    identity = {**identity, "artifact": args.companion.name, "minecraft": matrix["minecraft"]}
    if not args.legacy_baseline:
        identity.update(identity_format="modern_embedded", module_api_capabilities={"status": "unassessed"})
    if args.legacy_baseline and (args.probe or args.smoke or args.faults or args.expect_binary_rejection):
        raise ValueError("Legacy baselines require independent observation without product API or negative controls.")
    if args.initial_heap_mib <= 0 or args.initial_heap_mib > args.heap_mib:
        raise ValueError("Require a positive initial heap no greater than the maximum heap.")
    if any(value is not None and value <= 0 for value in (args.scheduler_parallelism, args.scheduler_max_pool_size)):
        raise ValueError("Scheduler controls must be positive or absent for JDK defaults.")
    extra_jvm_arguments(args.jvm_arg)
    observer_identity = None
    if args.legacy_baseline and args.observer:
        if len(args.observer) != 1:
            raise ValueError("Legacy baselines allow one independent observer only.")
        observer_identity = verified_observer(args.observer[0], identity, matrix)
    if args.performance:
        if not args.controls or not args.world or not args.catalogue or len(args.observer) != 1 or args.probe or args.smoke or args.faults or args.expect_binary_rejection:
            raise ValueError("Performance preparation requires context, world, catalogue and exactly one independent observer.")
        declarations = read(args.controls)
        if not isinstance(declarations, dict):
            raise ValueError("Declared performance controls must be a JSON object.")
        json.dumps(declarations, allow_nan=False)
        java_environment()
        observer_identity = verified_observer(args.observer[0], identity, matrix)
    elif args.controls:
        raise ValueError("Declared performance controls require --performance.")
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
        world = {"name": args.world, "files": inventory(source / "saves" / args.world)["files"]}
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
                "heap_mib": args.heap_mib, "jfr": args.jfr, "jfr_max_size_bytes": 0 if args.jfr else None,
                "initial_heap_mib": args.initial_heap_mib, "scheduler_parallelism": args.scheduler_parallelism,
                "scheduler_max_pool_size": args.scheduler_max_pool_size, "extra_jvm_arguments": args.jvm_arg,
                "resolution_width": args.resolution_width, "resolution_height": args.resolution_height,
                "native_memory_tracking": args.nmt, "smoke": args.smoke,
                "expected_binary_rejection": args.expect_binary_rejection,
                "mods": [{"filename": path.name, "sha256": digest(path),
                          "role": ("companion" if path.name == args.companion.name else "mtr" if path.name == mtr.name
                                   else "probe" if args.probe and path.name == args.probe.name else "observer")}
                         for path in sorted((instance / "mods").glob("*.jar"))],
                "source_hash": digest(pathlib.Path(__file__))}
    if args.performance:
        metadata = instance / ".prepared-controls"
        metadata.mkdir()
        shutil.copyfile(args.controls, metadata / "context.json")
        shutil.copyfile(args.catalogue, metadata / "catalogue.json")
        shutil.copyfile(args.companion.with_suffix(".build.json"), metadata / "companion.build.json")
        shutil.copyfile(args.observer[0].with_suffix(".build.json"), metadata / "observer.build.json")
        sources = {"packaged_client": pathlib.Path(__file__), "legacy_identity": ROOT / "tools/legacy_identity.py",
                   "target_matrix": ROOT / "config/targets.json", "legacy_catalogue": ROOT / "config/legacy-baselines.json"}
        manifest.update(schema=2, scope=PERFORMANCE_SCOPE)
        manifest["controls"] = {"schema": 1,
            "runtime": java_runtime(java, version.stderr),
            "inputs": {name: inventory(instance / name) for name in INPUT_DIRECTORIES},
            "jvm": {"arguments": jvm_arguments(manifest), "environment": java_environment()},
            "launcher": {"settings": launcher_settings(manifest), "implementation": launcher_implementation(),
                         "command_template": command_template(launch_command(instance, manifest), instance, java)},
            "context": {"declarations": declarations,
                        "source": {"path": ".prepared-controls/context.json", "sha256": digest(metadata / "context.json")}},
            "companion_manifest_sha256": digest(metadata / "companion.build.json"), "observer": observer_identity,
            "native_catalogue": {"path": ".prepared-controls/catalogue.json", "sha256": digest(metadata / "catalogue.json")},
            "sources": {name: {"path": str(path.resolve()), "sha256": digest(path)} for name, path in sources.items()}}
        manifest["controls_sha256"] = controls_sha256(manifest)
        verify_performance_controls(instance, manifest)
    else:
        manifest.update(schema=1, scope="packaged_client_preparation")
    write(instance / "packaged-client-plan.json", manifest)
    write(instance / "vehicle-test-instance.json", {"instance": str(instance), "mod_loader": "neoforge",
          "target": {"minecraft": matrix["minecraft"], "mtr": matrix["mtr"]["official"]["version"]},
          "loader": identity["neoForge"], "java": str(java), "pid": None, "packs": packs,
          "session_kind": "SDK development test profile; local gameplay only"})
    if args.smoke:
        write(instance / "loader-lifecycle-request.json", {"run": str(uuid.uuid4()), "scope": "Actual packaged companion; base resources; no gameplay certification", "faults": args.faults})
    print(json.dumps({"prepared": str(instance), "plan": str(instance / "packaged-client-plan.json")}), flush=True)


def jvm_arguments(plan):
    initial = plan.get("initial_heap_mib", 512)
    if type(initial) is not int or type(plan["heap_mib"]) is not int or not 0 < initial <= plan["heap_mib"]:
        raise ValueError("Invalid frozen initial/maximum heap.")
    arguments = [f"-Xms{initial}M", f"-Xmx{plan['heap_mib']}M", "-Dmtr.memory.acceptance=true"]
    for key, property_name in (("scheduler_parallelism", "parallelism"), ("scheduler_max_pool_size", "maxPoolSize")):
        value = plan.get(key)
        if value is not None:
            if type(value) is not int or value <= 0:
                raise ValueError("Invalid frozen scheduler setting.")
            arguments.append(f"-Djdk.virtualThreadScheduler.{property_name}={value}")
    if plan["smoke"]:
        arguments.append("-Dmtr.memory.acceptance.exit=true")
    if plan.get("native_memory_tracking") is not None:
        tracking = plan["native_memory_tracking"]
        if tracking not in ("summary", "detail"):
            raise ValueError("Unknown frozen native memory tracking mode.")
        arguments.append("-XX:NativeMemoryTracking=" + tracking)
    if plan["jfr"]:
        if type(plan.get("jfr_max_size_bytes")) is not int or plan["jfr_max_size_bytes"] != 0:
            raise ValueError("Freeze explicit full-history JFR retention in a fresh prepared plan.")
        # maxsize=0 disables JDK 21's otherwise implicit 250 MiB history trim.
        # Omit maxage so no age filter is applied to the recording.
        arguments += ["-XX:StartFlightRecording=name=acceptance,settings=profile,disk=true,maxsize=0,dumponexit=true,filename=acceptance.jfr",
                      "-Xlog:gc*,safepoint:file=acceptance-gc.log:time,uptime,level,tags:filecount=0"]
    return arguments + extra_jvm_arguments(plan.get("extra_jvm_arguments", []))


def observe_exit(process, wait_seconds):
    try:
        exit_code = process.wait(timeout=wait_seconds)
    except subprocess.TimeoutExpired:
        exit_code = None
    return {"timestamp": timestamp(), "pid": process.pid, "exited": exit_code is not None,
            "exit_code": exit_code, "wait_limit_seconds": wait_seconds}


def cleanup_failed_launch(process, instance, error):
    """Keep actual child ownership when publishing launch metadata fails."""
    attempts, exit_code = [], None
    try:
        if process.poll() is None:
            process.terminate()
            attempts.append({"action": "terminate_requested"})
        exit_code = process.wait(timeout=15)
        attempts.append({"action": "wait", "exit_code": exit_code})
    except BaseException as failure:
        attempts.append({"action": "terminate_and_wait", "error": repr(failure)})
        try:
            process.kill()
            attempts.append({"action": "kill_requested"})
            exit_code = process.wait(timeout=15)
            attempts.append({"action": "wait_after_kill", "exit_code": exit_code})
        except BaseException as second_failure:
            attempts.append({"action": "kill_and_wait", "error": repr(second_failure)})
    report = {"timestamp": timestamp(), "pid": process.pid, "error": repr(error),
              "cleanup_confirmed": exit_code is not None, "exit_code": exit_code, "attempts": attempts}
    try:
        write(instance / "packaged-client-launch-failure.json", report)
    except BaseException as save_failure:
        error.add_note("Failed to preserve launch cleanup report: " + repr(save_failure))
    error.add_note(f"Launched child PID {process.pid}; cleanup confirmed={report['cleanup_confirmed']}; actual exit={exit_code}.")
    if exit_code is None:
        raise RuntimeError(f"Launch publication failed and child PID {process.pid} cleanup remains unconfirmed.") from error


def launch(args):
    instance = args.instance.resolve()
    plan = read(instance / "packaged-client-plan.json")
    if pathlib.Path(plan["instance"]) != instance or (instance / "packaged-client-launch.json").exists():
        raise ValueError("Require this fresh prepared instance, with no prior launch.")
    verify_prepared_inputs(instance, plan)
    if plan.get("schema") == 2 or plan.get("scope") == PERFORMANCE_SCOPE:
        verify_performance_controls(instance, plan)
    arguments = jvm_arguments(plan)
    command = launch_command(instance, plan)
    if plan.get("schema") == 2:
        verify_generated_command(command, plan)
        if command_template(command, instance, plan["java"]) != plan["controls"]["launcher"]["command_template"]:
            raise ValueError("Generated command changed after performance verification.")
    process = None
    try:
        with (instance / "launch.stdout.log").open("wb") as stdout, (instance / "launch.stderr.log").open("wb") as stderr:
            process = subprocess.Popen(command, cwd=instance, stdout=stdout, stderr=stderr,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        launched = {"timestamp": timestamp(), "pid": process.pid, "plan_sha256": digest(instance / "packaged-client-plan.json"),
                    "jvm_arguments": arguments, "command": command, "launcher_tool_sha256": digest(pathlib.Path(__file__))}
        write(instance / "packaged-client-launch.json", launched)
        marker = read(instance / "vehicle-test-instance.json")
        marker["pid"] = process.pid
        write(instance / "vehicle-test-instance.json", marker)
        print(json.dumps({"pid": process.pid, "instance": str(instance)}), flush=True)
        if args.wait_seconds is not None:
            result = {**observe_exit(process, args.wait_seconds),
                      "launch_sha256": digest(instance / "packaged-client-launch.json")}
            write(instance / "packaged-client-exit.json", result)
            print(json.dumps(result), flush=True)
    except BaseException as error:
        if process is not None:
            cleanup_failed_launch(process, instance, error)
        raise
    return process


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    preparation = commands.add_parser("prepare")
    preparation.add_argument("--source", type=pathlib.Path, required=True)
    preparation.add_argument("--instance", type=pathlib.Path, required=True)
    preparation.add_argument("--companion", type=pathlib.Path, required=True)
    preparation.add_argument("--legacy-baseline", help="Explicit catalogue key for an unchanged historical companion.")
    preparation.add_argument("--probe", type=pathlib.Path)
    preparation.add_argument("--observer", type=pathlib.Path, action="append", default=[])
    preparation.add_argument("--catalogue", type=pathlib.Path)
    preparation.add_argument("--world")
    preparation.add_argument("--username", required=True)
    preparation.add_argument("--heap-mib", type=int, default=3072)
    preparation.add_argument("--initial-heap-mib", type=int, default=512)
    preparation.add_argument("--scheduler-parallelism", type=int)
    preparation.add_argument("--scheduler-max-pool-size", type=int)
    preparation.add_argument("--jvm-arg", action="append", default=[], help="Additional JVM option; use --jvm-arg=VALUE.")
    preparation.add_argument("--resolution-width", type=int, default=1280)
    preparation.add_argument("--resolution-height", type=int, default=720)
    preparation.add_argument("--performance", action="store_true", help="Freeze complete schema-2 preparation controls; this is not executed qualification.")
    preparation.add_argument("--controls", type=pathlib.Path, help="Explicit JSON declarations for workload, scene and machine context.")
    preparation.add_argument("--jfr", action="store_true", help="Freeze full-history profiling; recording disk usage grows until stopped.")
    preparation.add_argument("--nmt", choices=("summary", "detail"), help="Freeze optional JVM native memory tracking before launch.")
    preparation.add_argument("--smoke", action="store_true")
    preparation.add_argument("--faults", action="store_true")
    preparation.add_argument("--expect-binary-rejection", action="store_true")
    launching = commands.add_parser("launch")
    launching.add_argument("--instance", type=pathlib.Path, required=True)
    launching.add_argument("--wait-seconds", type=int, help="Observe actual process exit for 1 to 60 seconds; leave a live process running on timeout.")
    args = parser.parse_args()
    if args.action == "prepare":
        if args.heap_mib < 1024 or min(args.resolution_width, args.resolution_height) <= 0 or (args.smoke and not args.probe) or (args.faults and not args.smoke):
            parser.error("Require a valid heap and a probe for smoke acceptance.")
        prepare(args)
    else:
        if args.wait_seconds is not None and not 1 <= args.wait_seconds <= 60:
            parser.error("Require an exit observation window from 1 to 60 seconds.")
        launch(args)


if __name__ == "__main__":
    main()
