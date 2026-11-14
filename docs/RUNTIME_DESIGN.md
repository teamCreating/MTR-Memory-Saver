# Runtime contract — 0.4.3

`GenerationWorkCache` is a Java-only scheduling core. Resource/provider identity,
normalized model path, texture and flip flag form the fast key. A hit returns its
future before reading, decompressing or hashing source text. An admitted worker
reads/digests a miss and uses a content key to share identical alias-path inputs.
Aliases attach to the owner future and release their worker instead of waiting
while holding a read permit. No queued preparation supplier captures raw text.

The default scheduler has two workers and 64 extra outstanding slots. Admission
applies backpressure before registering another descriptor. Queue admission and
submitted work both have a 300-second timeout. Failures remove the path/content
entry so later requests can retry. Reload retires the whole generation under one
lock, replaces it, cancels pending futures and removes queued tasks. Registration
completion releases successful source keys, including results that finish later.

Each model, text and vehicle-JSON call captures its resource generation before
waiting for admission. Retirement cancels waiting callers before they read or
enter the replacement generation, including callers waiting behind native work
that ignores interruption. Text hits and single-flight followers recheck their
generation after restoring data. Cancellation does not release a still-running
owner's permit or ticket. Configuration rejects malformed and out-of-range
integer properties rather than silently substituting defaults.

Every module task contributes one native `parseStarted`/`parseFinished` ticket so
MTR's `awaitParsing` observes module-queued work. `BlockbenchParseExecutorMixin`
runs the original native parser Runnable inline only when its caller owns the
thread-local module parse scope. Foreign MTR tasks retain their original executor.
The native parser still owns its separate native ticket. Publication is accepted
only after that Runnable returns and `setModelLoaded` was observed for the same
source. A caught native error without publication becomes a terminal shared error.
The official/v6 facades record publication failures and remain unloaded on failure.
v6 serializes late publication with native consumer close; shared source staging
and each consumer's built GPU models retain their existing separate ownership.

Canceling/timing out a future cannot force native code to stop. A running task
keeps its admission permit and native ticket until its actual exit, even if it
ignores interruption. The pending-future count can therefore be zero while the
outstanding-task count is positive. This distinction is visible in diagnostics and
tested explicitly. Daemon threads do not provide a process-isolation boundary.

`BoundedTextCache` has one synchronized LRU with eviction before insertion. It
checks conservative uncompressed entry weight before attempting compression;
oversized entries bypass compression and caching. Compression stops once output
cannot beat compact String storage. Exact UTF-16 is preserved, including null
characters and unpaired surrogates. The first reader keeps its String identity;
followers restore from a temporary/compressed entry under the same read admission.
Failed readers resolve their single-flight futures and remove pending entries.
Generation retirement prevents older readers from filling the replacement cache.

`SegmentedResourceText` checks decoded size before storing another segment. It
preserves the native charset/replacement policy and native stream ownership.
The size guard fails explicitly; it never truncates an oversized resource.

## Limits and configuration

All values are JVM system properties, read once when their subsystem initializes.
Malformed, nonpositive and out-of-range limits fail initialization instead of
silently disabling checks or substituting defaults.

| Property | Default | Meaning |
| --- | --- | --- |
| `mtr.memory.readers` | 2 | Concurrent read/unpack/module-parse scopes, with same-thread nesting |
| `mtr.memory.parsers` | 2 | Module worker count |
| `mtr.memory.parseQueue` | 64 | Extra outstanding descriptor capacity beyond workers |
| `mtr.memory.parseTimeoutSeconds` | 300 | Queue-admission and submitted-work timeout |
| `mtr.memory.maxTextCodeUnits` | max heap / 32, capped below Java array limit | Per-text decoded UTF-16 limit |
| `mtr.memory.textCacheBytes` | 100,663,296 | Conservative admitted cache-weight limit |

At a 3 GiB heap the text limit is 100,663,296 code units. The historical largest
65,255,687-byte model is below that decoded limit. Four payload bytes per code unit
is a sizing allowance for segmented decoding plus final text, not an accounting
proof of all live Java objects. Compression capacity rounding, unreachable objects
awaiting GC, caller-held Strings, native JSON/model structures, native foreign
parsers, GPU allocations and resource-pack internals are outside the LRU budget.
The module does not advertise a whole-load/process RAM ceiling or guaranteed frame
latency. More workers can improve throughput while increasing peak live memory.

## Verification boundary

Headless tests cover exact text, LRU admission/bypass, failure/retry, concurrent
single-flight, provider keys, queue backpressure, cancellation, timeout, stale
publication and 1,000-generation churn. They also assert actual ticket/permit
cleanup. They cannot establish Mixin application, GL ownership or rendered output;
those require the separate [acceptance procedure](ACCEPTANCE.md).
