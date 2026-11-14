"""Record this completed engineering stage without claiming runtime completion."""
import datetime as dt
import json
import pathlib
import re

BASE = pathlib.Path(__file__).resolve().parent
ROOT = BASE.parents[1]
execution = json.loads((BASE / "python-tests/attempt-02/execution.json").read_text(encoding="utf-8"))
assert execution["exit_code"] == 0 and not execution["sources_changed_during_execution"]
count = int(re.search(rb"Ran (\d+) tests", (BASE / "python-tests/attempt-02/stderr.log").read_bytes()).group(1))
now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()
path = BASE / "verification-plan.json"
plan = json.loads(path.read_text(encoding="utf-8"))
plan["timestamp"] = now
plan["completed"].update(
    python_tests=count,
    python_suite_scope="Current bounded background observer, interruption/ownership and process-scoped GPU regressions; sources unchanged during execution",
    python_execution="python-tests/attempt-02/execution.json",
    bounded_background_auxiliary_observer={
        "observer_tests": 61,
        "all_python_tests": count,
        "actual_two_hour_validation": "pending",
        "accepted_request_accounting": "Full registry and requested/started/completed sidecar, including terminal reconciliation",
        "bounded_shutdown_seconds": 45,
        "strict_maximum_sampling_gap_seconds": 20,
        "post_window_results": "Explicitly tagged; never extend frozen route sampling elapsed time",
    },
)
plan["in_progress"] = {
    "manual_reload_qualification": {
        "status": "awaiting user",
        "reason": "F2 native export succeeds; three automated F3+T attempts produce no native epoch. No route window is running.",
    },
    "fresh_two_hour_route": {
        "status": "not_started",
        "reason": "Background observer verified; begin after manual reload qualification to avoid reload during the window.",
    },
}
plan["remaining"] = [
    value for value in plan["remaining"]
    if not value.startswith("Complete and verify the bounded background")
    and not value.startswith("Finish final evidence SHA indexing")
]
audits = sorted(
    path.name for path in (BASE / "delivery-audit").glob("*.audit.json")
    if path.name != "links.audit.json"
)
plan["completed"]["current_release_delivery_audit"] = {
    "passed": True,
    "execution": "delivery-audit/execution.json",
    "target_results": ["delivery-audit/" + name for name in audits],
    "scope": "Current development candidate bytes/navigation; remaining runtime gates are not certified",
}
path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
for name in ("docs/COVERAGE_OFFICIAL.md", "docs/ACCEPTANCE.md"):
    path = ROOT / name
    content = path.read_text(encoding="utf-8")
    old = next(line for line in content.splitlines() if line.startswith("Updated:"))
    path.write_text(content.replace(old, "Updated: " + now + " (UTC+08:00)."), encoding="utf-8")

entry = f"""

## {now} (UTC+08:00)

Implemented Memory Saver 0.4.6 only for official MTR 4.1.0-beta.2 on the two explicit NeoForge targets; new v6 verification stays paused. Default decoded-text admission now derives its limit from heap/16 and uses a shared weighted workspace (heap/4, at least four times an explicit text limit). At 3 GiB these defaults are 201326592 UTF-16 code units and 805306368 workspace bytes. Readers exceeding their fair share preserve original UTF-16 units in owned temporary snapshots, release their partial share, then claim the complete restoration budget. Equal-weight waiters retain distinct identities; cancellation, exceptions and normal exit release ownership and delete snapshots. Compression claims are nonblocking and busy workspaces retain exact raw cache entries. Caller/native-retained strings, object overhead, fixed buffers, pending GC and GPU models remain outside this temporary-payload accounting.

Official native resource reads propagate actual open/read/close and decoded-size errors through StrictResourceText, replacing only the identified readResource invocation. IOException causes survive; guard and cancellation failures remain terminal. Native UTF-8 replacement, successful empty files and Optional.empty cache semantics are preserved. A corrected missing resource still needs native cache retirement/reload. Actual-Resource stream fixtures and their Mixin are confined to the separate acceptance probe and excluded from product JARs.

Validation: each official target passes 61 Java tests. The final standalone Python suite passes {count} tests, including 61 observer cases, with unchanged source bytes during execution; intermediate 91-test output and matching observer/test snapshots remain preserved. Both real packaged official clients pass 24 lifecycle plus 18 actual resource checks and exit normally. Their full-history JFR configuration freezes maxsize=0, omits maxage and preserves readable recordings. The actual 102035449-unit authored OBJ passes exact NF248 source/reencoded-byte equality at 3 GiB with CompactStrings enabled and disabled, including eight forced-spill native charset/replacement controls per mode. Workspace peak is 408141796 bytes, with all ownership/files settled. Initial standalone compilation failed during shaded annotation-processor discovery; original failure remains, and the successful second attempt uses the project's explicit -proc:none policy.

The exact NF248 full sixteen-pack client reaches 1092 declarations/1091 unique IDs and settled native/module/workspace counters without the old large-OBJ decode rejection. Its first official native HEAD/RETURN pair is synchronous on the render thread with nesting one. This establishes registration/settlement, not geometry or boarding. Startup observation fails because only two of four GPU samples are available; a later 13-sample settlement window succeeds without replacing that gap. Window screenshot capture previously timed out twice. A real F2 export now shows platform/world/player and confirms single-key input delivery, but no train is visible; no vehicle visual/interaction pass follows. Three API F3+T attempts produce no new native epoch or full ResourceManager log. Successful actual reloads remain zero; a manual qualification is pending.

Preserved two failed route attempts. Attempt 01 has 287 samples over 1432.8089 seconds, 19 unchanged-snapshot failures and one unavailable GPU query out of 23. Attempt 02 has 56 samples over 349.2593 seconds, with all six GPU/NMT requests available but a 20.8425925-second gap beyond the frozen 20-second limit. Both are interrupted, not two-hour passes. Exported and verified partial JFR/NMT before interrupting each observer; the game remains alive. First JFR export supplied an absolute diagnostic filename containing a space: jcmd returned zero with an argument error, but jfr summary failed and prevented any stop. That failure and successful relative-filename export remain. Partial recordings end before final observer samples and are not complete route/performance evidence.

Repaired observation by skipping missed deadlines, querying GPU wildcard instances for the actual PID while preserving counter names/raw errors, and moving bounded auxiliary queries to one owned background worker. Request/start/completion events, actual timestamps/results and the full registry persist separately. Main sampling is nonblocking; 45-second shutdown does not extend the frozen window. Missing/failed/pending observations or unconfirmed worker exit prevent acceptance. Interrupted submission/accounting reconciles by request identity. A real thread-start-then-KeyboardInterrupt regression preserves the worker reference and queued/running ownership until actual exit; no unobserved stop is fabricated. Independent read-only core and observer reviews found no new critical issue. A fresh two-hour run has not started while manual reload qualification is pending.

Both exact 0.4.6 wrong-binary clients have real exit code 1, fatal MixinInitialisationError with the original fingerprint cause and no Loaded vehicles registration. All 12462 MTR entries preserve their bytes; only copied ZIP comments change. NF248's first launcher lacked minecraft_launcher_lib and both 30-second launcher exit windows timed out; those records remain indeterminate, while the fresh retry retained a Windows process handle and measured actual Java exit 1. No source SDK marker/options/MTR or ordinary world/pack was modified.

Rebuilt both release bundles sequentially with -x test because already-tested product sources are unchanged. JAR hashes remain dd47f6ae4daa4139b9ada9196d757db634a79ebdd7fa5f06083719d764285997 (NF248) and fbcb608fd5b2452f650c656bc930934ac4e4880addae4d24846faa5df5d9f63e (NF265). Each bundle's seven files, five navigation links and 44 manifest inputs match current bytes, with probes excluded. Removed a source-only coverage link from bundled navigation. Final evidence SHA indexing and staged Git-blob verification accompany this commit, including negative observations. Remaining gates are actual vehicle geometry/displays/doors/floors/boarding, twenty real complete reloads and their ordering, a qualified two-hour route, NF265 full-pack/world interaction, and controlled full-client comparisons. The 0.3.0 baseline is only a candidate: strict legacy identity, neutral native/frame observation, equal runtime/config/world controls and full A/B/A/A/instrumentation execution still need engineering. Historical source trials remain inconclusive and do not establish whole-client gains. This stage does not complete the active goal. Commit author/committer is A-BenLi06 <ben_li06@outlook.com>.
"""
with (ROOT / "walkthrough.md").open("a", encoding="utf-8", newline="") as stream:
    stream.write(entry)
print(json.dumps({"timestamp": now, "python_tests": count, "delivery_audits": audits}))
