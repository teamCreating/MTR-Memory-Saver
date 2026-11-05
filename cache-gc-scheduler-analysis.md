# Cache, Full GC and virtual-thread scheduler tradeoffs

Date: 2026-11-05 (UTC+08:00). Target: delivered v0.3.0, official NeoForge
MTR 4.1.0-beta.2, Temurin 21.0.11+10. This analysis reads the current implementation,
the installed JDK source, the actual MTR release bytecode and existing runtime
observations. It does not change the mod, JVM arguments or test world.

[Evidence and scheduler source excerpt](evidence/neoforge-v030-cache-gc-scheduler-analysis.json)
preserve the original input fingerprints. No new Minecraft speed comparison was run.

## 1. Cache eviction can add work, but its net loading cost is not measured

The exact paths in `CompressedResourceTextCache.get` are:

| Request state | Work performed by this text-cache layer |
| --- | --- |
| Missing or previously evicted | Read/decode the resource, attempt compression, decide retention, return the original String directly |
| Compressed entry present | Inflate the entry and reconstruct its exact String |
| Uncompressed entry present | Return the retained String |
| Null or failed native read | Preserve null/failure handling; no successful text entry is retained |

A miss does **not** compress and then immediately decompress the same String.
The previous wording describes work across repeated accesses, not an obligatory
three-step pipeline for every miss. A resource ZIP may itself require decompression
when read; that is separate from inflating this mod's compressed text entry.
Windows file caching may avoid a physical disk read, so a cache miss is not proof
of disk I/O. Archive extraction, decoding, allocation and digest CPU work can
remain even with a warm OS file cache.

Potential added costs are repeated misses after eviction, compression of entries
that will not be reused, compressed-output copies, and LRU bookkeeping. An
oversized entry is compressed before the admission code can reject it. Conversely,
the smaller cache can reduce retained-heap pressure and GC work enough to offset
some extra CPU work. The current 3,010-eviction count does not reveal how many
evicted entries were requested again, the hit ratio or the number of bytes reread.

The independent parsed-model cache already avoids most repeated parsing: 4,608
requests produce 651 unique sources. However, its lookup currently reads/restores
the complete text and computes its digest before looking up that shared result.
Text-cache eviction therefore need not cause a second model parse, but repeated
text restoration and hashing still cost work. A source-identity fast lookup,
scoped to the provider/resource generation, texture and orientation, can eliminate
some of this work without enlarging the text cache or reducing model quality.

Conclusion: additional work on specific request paths is established by the code;
slower overall loading, the size of a slowdown, and a net performance regression
against v0.2.9 are **not** established. v0.2.9's failed 3 GiB load is not a valid
completed-load timing control.

## 2. Full GC is real; ownership and causes remain unmeasured

| Preserved reload window | Full GC count increase | Full GC cumulative time increase |
| --- | ---: | ---: |
| First run | 5 | 4.534 s |
| Repeat | 6 | 5.063 s |

The intervals with increasing counters occur during the reload/registration
period. The repeat's last interval straddles the native registration-completion
timestamp, so its exact event boundary cannot be placed from five-second samples.
The GC burden is not merely an inference from the maximum heap value.

The same installed JVM with the recorded heap/scheduler flags selects G1 in an
independent `PrintCommandLineFlags -version` check. G1 Full GC includes a
stop-the-world collection, which can delay the render and integrated-server
threads along with application workers. The evidence does not supply per-event
pause quantiles, exact safepoint duration or frames lost. Cumulative Full GC time
must not be described as one continuous 4.5-5.1-second freeze. JFR/GC and safepoint
logs are required for those claims. Ordinary-play GC frequency was not measured.

Several mechanisms can contribute:

- The fixed 3 GiB heap has less allocation headroom than larger configurations.
- MTR parsing builds complete source Strings, JSON objects and model structures;
  pending jobs retain source inputs outside the text cache's budget.
- Reload involves old and new resources, vanilla assets and native/GPU work;
  reclaimable data and not-yet-reclaimable live data have different effects.
- Compression, decompression and copies add allocations; eviction can either
  reduce live data or increase repeat work. Their net GC effect needs comparison.
- Concurrent parsing changes allocation rate and overlapping live data. Humongous
  allocations, evacuation failure, an explicit collection request or another
  trigger cannot be distinguished from these jstat counters alone.

No diagnostic GC was requested by the acceptance harness. That fact does not rule
out every library's explicit request or identify the trigger. Full GC is a
JVM-wide event; neither all five/six events nor all cumulative pause time can be
assigned to Memory Mod using the existing evidence. Passing 3 GiB loading remains
different from demonstrating comfortable frame-time or tick-time headroom.

## 3. The two JVM properties have distinct global effects

Inspection of this exact JDK's `VirtualThread.createDefaultScheduler` confirms:

| Setting | Meaning | Effect of the tested value |
| --- | --- | --- |
| `jdk.virtualThreadScheduler.parallelism=2` | Target parallelism of the default virtual-thread carrier scheduler; default follows available processors | Limits target execution parallelism of virtual threads using this scheduler to two carriers |
| `jdk.virtualThreadScheduler.maxPoolSize=2` | Carrier pool ceiling, including expansion for certain blocking operations; unset default is at least 256 in this JDK | Removes expansion headroom beyond those two carriers |

These properties do not limit the process to two threads, the machine to two CPU
cores, or the number of submitted virtual threads/tasks to two. Waiting virtual
threads may remain alive with their inputs. The properties are read when the
default scheduler is created and are not a per-mod or reload-only throttle.

The actual released `WorkerThread` constructor uses
`Executors.newVirtualThreadPerTaskExecutor()`, so MTR does use the affected
scheduler. Other mods using the same default virtual-thread scheduler share the
limit even when they create a separate virtual-thread-per-task executor. MTR's
background worker also handles work such as culling and dynamic textures, so the
possible impact extends beyond initial model parsing. Actual frame-time effects
have not been measured.

Conventional platform-thread pools, the ordinary common ForkJoinPool, render and
server threads, Netty pools, and GC worker counts are not directly capped by these
two properties. They can still be indirectly delayed while waiting for virtual
tasks or by shared CPU/heap/GC pressure. More than two GC/refinement threads are
allowed; this is not an `ActiveProcessorCount=2` configuration.

When virtual threads can unmount during waiting, two carriers can serve many
I/O-waiting tasks. CPU-heavy parsing and compression still occupy carriers. Some
blocking operations use scheduler compensation, and the pool ceiling matters for
them. Java 21 also has pinned-thread cases involving monitor/native boundaries;
increasing the carrier maximum does not automatically fix pinning. No pinned
event was measured in these acceptance runs. Do not infer pinning from the mere
presence of `synchronized`, or claim that pinning caused the observed pauses.

The tested 2/2 combination is a broad concurrency control with real tradeoffs.
It may reduce overlapping allocations, but can reduce throughput and delay other
virtual-thread workloads. It does not provide an MTR source-byte budget or prove
the same 3 GiB acceptance without those flags.

## Separating the effects experimentally

Keep Java, resource/mod hashes, fixture, graphics settings, observer and endpoints
fixed. Separate startup and F3+T, use fresh processes, repeat runs, and alternate
test order. Record filesystem-cache conditions instead of treating every restart
as cold storage. End loading measurements at complete native registration/parsing
and rendering readiness; record the subsequent stability period separately.

| Comparison | Hold fixed | Change | Question answered |
| --- | --- | --- | --- |
| v0.2.9 versus v0.3.0 | A heap at which both finish, initially 4 GiB; 2/2 scheduler | Only the memory companion | Does bounded retention improve or worsen completed-load CPU, wall time, GC and memory? |
| v0.3.0 at 3 versus 4 GiB | Same companion, 2/2 scheduler | Heap cap | How much of the GC pressure tracks heap headroom? |
| v0.3.0 2/2 versus 2/unset maximum | Same companion and heap | Carrier expansion ceiling | Does restricting compensation materially affect load/tail latency? |
| v0.3.0 2/unset versus 4/unset or both properties unset | Same companion and heap | Target parallelism | How do throughput, peak live memory and other virtual workloads trade off? |

An OOM is a failed feasibility result, not a fast/slow completed-load measurement.
Collect JFR/GC/safepoint data, text hit/miss/decode/rehit bytes and timings, queued
input bytes, and representative frame/tick latencies. Instrumentation should avoid
logging or sampling every hot-path operation excessively. Testing larger global
limits is an experiment, not a replacement recommendation for the verified 3 GiB
settings.

The preferred implementation direction is to remove redundant text work and put
admission control on MTR model loads before large inputs are read. Budget both
concurrent parse jobs and queued source bytes, preserve completion/failure
ownership, and avoid holding cache locks while awaiting work. A semaphore placed
inside tasks after capturing all their Strings does not bound queued memory.
Once that local control is verified, retest with the global JVM restrictions
removed. This targets the expensive work while avoiding a permanent scheduling
limit for unrelated virtual-thread users.
