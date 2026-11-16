# Runtime contract — 0.4.7

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

The required compatibility plugin reports an incompatible dependency through
Mixin's standard `MixinInitialisationError`, preserving the fingerprint cause.
A plain Exception during configuration selection is logged and skipped by the
actual Mixin runtime, so it cannot implement the required startup rejection.

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
Blockbench inputs use the native Gson parser directly: malformed/truncated or
non-object JSON fails rather than inheriting the utility's empty-object fallback.
Valid model data still uses the native Blockbench schema and baking algorithm.
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
cannot beat compact String storage. It claims a conservative five payload bytes
per code unit without waiting, or retains the raw entry when workspace is busy.
Exact UTF-16 is preserved, including null
characters and unpaired surrogates. The first reader keeps its String identity;
followers restore from a temporary/compressed entry under the same read admission.
Failed readers resolve their single-flight futures and remove pending entries.
Generation retirement prevents older readers from filling the replacement cache.

`SegmentedResourceText` checks decoded size before storing another segment. It
preserves the native charset/replacement policy and native stream ownership.
The size guard fails explicitly; it never truncates an oversized resource.
The official provider's existing-resource reader propagates open, read, close,
size and cancellation failures to the cache rather than inheriting the native
helper's logged empty-String fallback. Valid empty resources and the native
missing-resource Optional fallback remain distinct successful empty values.
Repairing a missing resource still requires a resource reload to retire that cache.

Temporary decoded payloads share a weighted workspace. A reader first claims a
fair share; input that grows beyond it is saved as exact UTF-16 code units in an
owned temporary file. The reader drops its segments and releases its entire share
before waiting to claim the known complete size. Two large unknown readers cannot
hold partial reservations while waiting for each other. Smaller inputs keep the
segmented in-memory path. Restoration and cache unpacking claim four conservative
payload bytes per code unit before allocation. Claims inherit generation
cancellation and release on actual materialization exit. A snapshot atomically
creates one channel with CREATE_NEW, READ, WRITE and DELETE_ON_CLOSE and retains
that channel across writing, budget waiting, rewind and restoration. Bounded
channel I/O handles partial transfers and checks retirement during zero progress.
Closing the owner releases the file on success, failure and cancellation; Windows
also removes it when abrupt process exit releases the handle. Unsupported ownership
options and real disk failures propagate. The reader never reopens the path or
scavenges files from earlier processes. These tests do not establish power-loss or
real disk-full behavior.

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
| `mtr.memory.maxTextCodeUnits` | max heap / 16, capped below Java array limit | Strict per-text decoded UTF-16 limit |
| `mtr.memory.textWorkspaceBytes` | max(heap / 4, four times configured text limit) | Shared transient text payload budget; must fit the configured limit |
| `mtr.memory.textCacheBytes` | 100,663,296 | Conservative admitted cache-weight limit |

At a 3 GiB heap the default text limit is 201,326,592 code units and the shared
workspace is 805,306,368 payload bytes. The actual 102,035,449-code-unit authored
OBJ fits this shared budget; it exceeds the initial two-reader fair share and
therefore uses an immutable snapshot. This policy is independent of file paths,
character repertoire and CompactStrings. Explicitly raising the text limit also
raises the inferred workspace unless its separate property is set; inconsistent
limits fail initialization.
Four payload bytes per code unit cover segmented decoding plus final text; this
is a payload sizing allowance rather than an accounting proof of all live objects.
Workspace is released when the materialization returns, whereas read/parse scopes
remain held until their owner exits. Caller-held results, fixed I/O buffers, object
headers, unreachable objects
awaiting GC, native JSON/model structures, native foreign
parsers, GPU allocations and resource-pack internals are outside the LRU budget.
The module does not advertise a whole-load/process RAM ceiling or guaranteed frame
latency. More workers can improve throughput while increasing peak live memory.

## Verification boundary

Headless tests cover exact text, LRU admission/bypass, failure/retry, concurrent
single-flight, provider keys, queue backpressure, cancellation, timeout, stale
publication and 1,000-generation churn. They also assert actual ticket/permit
cleanup. They cannot establish Mixin application, GL ownership or rendered output;
those require the separate [acceptance procedure](ACCEPTANCE.md).
