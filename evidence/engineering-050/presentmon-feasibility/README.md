# External OpenGL present-source feasibility

Neither requested capture produced a CSV or target present records. This exact
attempted OpenGL/display path therefore has **no demonstrated external frame
data source**. The records do not establish calibration, a performance comparison,
gameplay correctness, or general driver/API incompatibility. No third capture was
attempted.

The target was the already-owned diagnostic client PID 18796, creation
`2026-11-16T15:31:22.677672Z`, official NF248 / Memory Saver 0.4.7. Before and later
after observations bind the same PID, creation time, executable and complete game
command. Neither helper launches Minecraft or sends game input. Other builds,
collectors and ordinary user activity were present; this was not a quiet benchmark.

## Retained attempts

| Attempt | Actual observation | Limit |
| --- | --- | --- |
| Installed NVIDIA FrameView PresentMon `1.8.12407.0`, `capture-01/` | Owned helper PID 73196 returned 1 naturally; stdout/stderr empty; no CSV. Its unique session was absent at the sampled during/after queries. Target identities match before/after. | No present data or explanation of the return code. The global sessions-before query also failed with HRESULT 2147946600; that failed raw diagnostic remains retained. |
| Official upstream PresentMon `2.6.0`, `upstream-capture-02/` | Requested `--timed 25`; actual owned helper PID 57868 and its creation/executable/command are independently retained. Console reports recording started/stopped; the unique session was observed live by logman and a read-only native query. No CSV. | Post-wait image lookup failed with WinError 31 before the original helper return code was written; that code remains null. |

The upstream query at `2026-11-17T00:18:50.033495+08:00` returned zero
`EventsLost`, `LogBuffersLost` and `RealTimeBuffersLost`. These are **one query
point**, not final counters or proof of complete window/frame coverage.
`upstream-recovery-01/` then records the original helper absent, the unique session
absent (`ControlTraceW` status 4201), and unchanged target identity at the actual
later read. No session-stop command, service operation, privilege change or game
input was issued. Other session sets are not asserted to have remained static.

## Binary provenance and actual CLI

The installed FrameView executable has an observed valid NVIDIA signature and
SHA-256
`25fcc45da599b13c434d022c57214972b9fd64608e4820c399f41d01fb1961ba`.
It was not overwritten. The current token is non-administrator and belongs to
Performance Log Users; successful tracing was not inferred from membership.

The second executable was downloaded separately into the repository's ignored
cache from the [official v2.6.0 release](https://github.com/GameTechDev/PresentMon/releases/tag/v2.6.0).
`upstream-download-01/` retains the exact GitHub release API bytes, HTTPS request
receipts and downloaded license. The API asset ID/size and official SHA-256 digest
match the actual executable:
`b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af`.
Its observed signature is valid Intel Corporation. PE version-resource fields are
unavailable; the actual help output identifies PresentMon 2.6.0. It was not
installed and no service was started.

Both actual `--help` invocations return 1 while emitting complete usage; those
raw statuses and the first wrapper's rejected exit-zero assumption remain
unchanged in `help-01/` and `upstream-help-01/`. The upstream stdout is only a
UTF-16 BOM, while its version/usage is in stderr. `upstream-capture-01/` preserves
the strict UTF-8 preflight rejection before any capture helper was launched.
The subsequent reader honors BOMs strictly without replacing bytes or choosing
a UI language. Actual help confirms every used option. The capture retains
display tracing while explicitly disabling input and GPU-work tracing.

QPC/UTC witnesses contain the actual frequency and UTC bracketed by two QPC
reads. They establish a possible time mapping; without CSV there are no frame
timestamps to map or frame distributions to certify. Native render-loop frame,
CPU utilization, OS memory, heap and GC measurements were not supplied by these
captures. Present timing would remain a distinct measurement even if obtained;
it cannot replace `mtrtest.ClientFrame`.

## Wrapper repair and independent audit

The failed upstream wrapper called `QueryFullProcessImageNameW` after process
exit. `owned-child-control-01/` uses one separate ordinary Python child, PID
73488, expected/actual exit 7: the original post-exit call really reproduces
WinError 31, the already-written wait receipt retains its original SHA, and the
repaired post-exit timing query succeeds while leaving unavailable image data
unavailable. The pilot now saves `capture-exit.json` immediately after wait and
before optional metadata. This repair was **not** followed by another PresentMon
capture. The ordinary-child result cannot reconstruct the missing original
PresentMon exit code.

`assessment-01.json` retains an assessor failure that looked for the version
only in stdout; its exact source is preserved. `assessment-02.json` independently
verifies actual retained streams, their SHA chains, helper/target identities,
unique-session/QPC witnesses, official asset digest, absence of CSV, missing exit
receipt and the separate owned-child control. `audit_passed=true` means this
integrity audit passes; `capture_data_source_available=false`,
`calibration_accepted=false` and `performance_accepted=false` remain explicit.

The frozen sources in each attempt are execution records. Re-running them is
not a replay of this historical client state. To recheck only retained evidence,
use a fresh assessment output:

```powershell
.venv/Scripts/python.exe -X utf8 evidence/engineering-050/presentmon-feasibility/assess_pilot.py assessment-03.json
```

The outer SHA index binds all payloads except itself. The original world, packs,
MTR/JDK/runtime bytes and running client inputs are not changed or freshly
qualified. The full-client calibration gate and its strict native/scene/diagnostic
requirements remain pending.
