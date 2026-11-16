"""Read the owned JVM's complete rolled log; no game input or runtime writes."""
import datetime as dt
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUTPUT = HERE / (sys.argv[1] if len(sys.argv) > 1 else "actual-read-01")
OUTPUT.mkdir(parents=True, exist_ok=False)
sys.path.insert(0, str(ROOT / "tools"))
import native_log_stream as logs
import observe_packaged_client as observer
import windows_snapshot_io

instance = ROOT / ".cache/acceptance/official-nf248-owned-049c"
plan = json.loads((instance / "packaged-client-plan.json").read_bytes())
launch = json.loads((instance / "packaged-client-launch.json").read_bytes())
source_names = ["tools/native_log_stream.py", "config/native-log-reader.json", "tools/observe_packaged_client.py",
                "tools/reload_before_recorder.py", "tools/client_experiment.py", "tools/windows_process_identity.py"]
before = {}
for name in source_names:
    raw = (ROOT / name).read_bytes()
    path = OUTPUT / "sources" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    before[name] = logs.sha(raw)
started = logs.now()
process = observer.WindowsProcess(plan, launch)
try:
    assert process.sample()["running"]
    identity = {**process.identity, "created": process.created}
    (OUTPUT / "actual-process.json").write_text(json.dumps(identity, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    witness = ROOT / "evidence/engineering-050/neutral103-startup/capture-01/observation/native-log-at-completion.log"
    reader = logs.NativeLogStream.from_launch(instance, plan, launch, OUTPUT / "native-log", identity, prefix_witness=witness)
    captured = reader.read()
    rebuilt = b"".join(gzip.decompress((reader.output / part["blob"]).read_bytes()) if part["name"].endswith(".gz")
                       else (reader.output / part["blob"]).read_bytes() for part in captured.receipt["segments"])
    assert rebuilt == captured.data == logs.verify_capture(reader.output, captured.receipt_path)
    assert captured.data.startswith(witness.read_bytes())
    (OUTPUT / "logical-native.log").write_bytes(captured.data)
    native_inputs = {}
    for name in ("native-observer.json", "native-resource-epochs.jsonl", "native-invalid-model.jsonl"):
        raw = windows_snapshot_io.read_snapshot_bytes(instance / "game-probe" / name)
        native_inputs[name] = raw
        (OUTPUT / name).write_bytes(raw)
    native = json.loads(native_inputs["native-observer.json"])
    old = ROOT / "evidence/engineering-050/neutral103-startup/capture-01/observation"
    review = json.loads((old / "native-diagnostic-review.json").read_bytes())
    modules = {}
    for name in ("client_experiment_analysis", "native_diagnostic_review"):
        spec = importlib.util.spec_from_file_location("sealed_"+name, old / (name+".py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules[name] = module
    text = captured.data.decode("utf-8")
    replay = modules["native_diagnostic_review"].review_diagnostics(modules["client_experiment_analysis"].native_diagnostics(text), text,
        [json.loads(row) for row in native_inputs["native-invalid-model.jsonl"].splitlines()],
        [json.loads(row) for row in native_inputs["native-resource-epochs.jsonl"].splitlines()], identity, native["target"], review,
        {"start": plan["timestamp"], "end": logs.now()}, native)
    original = json.loads((old / "summary.json").read_bytes())["native_diagnostics"]
    assert replay == original and replay["native_attribution"]["passed"]
    assert native["pid"] == identity["pid"] and native["observation_errors"] == 0
    result = {"started_at": started, "completed_at": logs.now(), "passed": True, "process": identity,
              "logical_bytes": len(captured.data), "logical_sha256": logs.sha(captured.data),
              "reference": reader.reference(), "segments": captured.receipt["segments"],
              "independent_gzip_reconstruction_equal": True, "earlier_startup_prefix_preserved": True,
              "diagnostic_replay_equal_to_original_startup": True, "native_diagnostics": replay,
              "source_sha256_before": before,
              "source_sha256_after": {name: logs.sha((ROOT / name).read_bytes()) for name in source_names},
              "scope": "Read-only logging/identity validation. No game input, restart, reload, route or performance acceptance."}
    assert result["source_sha256_before"] == result["source_sha256_after"]
    (OUTPUT / "assessment.json").write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps({"passed": True, "logical_bytes": len(captured.data), "segments": [s["name"] for s in captured.receipt["segments"]], "diagnostic_replay_equal": True}))
finally:
    process.close()
