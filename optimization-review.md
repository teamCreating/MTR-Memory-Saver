# Further optimization review for v0.3.0

Date: 2026-11-05 (UTC+08:00). Scope: read the delivered sources, pinned NeoForge
release bytecode, existing experiment results and both preserved 3 GiB runs.
No mod implementation, artifact, game configuration or world was changed.

The subsequent [cache, Full GC and scheduler analysis](cache-gc-scheduler-analysis.md)
examines the exact miss/hit paths, observed GC intervals, the installed JDK's global
carrier limits and the comparisons needed to separate their performance effects.

There is further opportunity, especially in transient allocations and reload
pressure. The current evidence supports successful operation at 3 GiB in the
fixture, but does not establish a lower safe heap or a quantified saving for the
proposals below. Prioritize less Full GC and fewer large temporary objects before
trying a lower heap limit.

## Corrected measurement interpretation

[Reanalysis and input fingerprints](evidence/neoforge-v030-optimization-review.json)
come directly from the existing raw observations. The first startup sampler began
after registration: native completion was 14:26:42.785 +08:00, process sampling
started at 14:27:03.508805 +08:00 and jstat at 14:27:05.254621 +08:00. Its 2.812 GiB
heap and 3.863 GiB working-set values describe the sampled post-registration
interval, not parsing peaks. The repeat startup and both reload jstat samplers do
cover parsing. This corrects the previous blanket statement that both startup
samplers covered blocked parsing; the two successful 3 GiB runs remain valid.

The preserved Windows `peak_working_set_since_process_start` counters reach
**5.239 GiB / 5.363 GiB** by the two reload observations. These are OS process-lifetime
working-set high-water marks, not phase-only measurements. The earlier
**4.767 GiB / 4.541 GiB** figures are maxima of sampled current working sets and miss
shorter peaks. The initial final response's 4.77 GiB figure was only a sampled
maximum; it is not an upper bound on process memory. Neither measure is the
3 GiB Java heap limit.

| Observation window | Young GC count increase | Full GC count increase | Full GC time increase | Total GC counter time increase |
| --- | ---: | ---: | ---: | ---: |
| Repeat startup | 234 | 1 | 0.949 s | 7.109 s |
| First reload | 274 | 5 | 4.534 s | 10.281 s |
| Repeat reload | 268 | 6 | 5.063 s | 10.799 s |

These are first-to-last jstat sample deltas. They include some pre-reload and
post-completion stability time and do not measure all wall-clock loading cost.
The first startup's short post-registration sampling cannot establish its startup
GC workload. No diagnostic GC was requested in any of these acceptance runs.
The observations identify remaining memory pressure; they do not identify the
objects or native allocator responsible.

## Ranked opportunities

| Priority | Change to investigate | Source evidence and expected benefit | Limits and validation |
| --- | --- | --- | --- |
| 1 | Reuse parsed-source results before reconstructing text and rehashing it | `SharedBlockbenchCache.get` obtains the full resource String and hashes it before checking the shared source cache. Each epoch reports 4,608 requests but only 651 unique parses. Avoiding repeated text restoration/digests can reduce allocation and CPU work even when the parsed mesh is already shared. | The 3,957 excess requests are not a measured cache-hit or byte-saving count. A fast lookup needs reload epoch, resource-provider/resolved-resource identity, texture and orientation semantics; a global path-only cache is unsafe. Keep cross-path content sharing and test pack overrides and reload invalidation. |
| 2 | Bound bytes retained by queued parse jobs | `SharedBlockbenchCache` captures `raw` in a Supplier. The actual release's `BlockbenchModelLoader.loadModel(Supplier)` submits it to an executor, which invokes the Supplier later. The 96 MiB text-cache limit does not constrain those job-owned Strings or concurrently parsed JSON trees. | Two carrier threads are not a byte limit or a guarantee that only two jobs retain data. Measure queued jobs and source bytes, then apply admission before reading large inputs. Avoid blocking under cache locks or on the completion executor; preserve interruption and failure completion. |
| 3 | Remove full packed-output copies and improve cache admission | `Text.pack` grows a `ByteArrayOutputStream` and calls `toByteArray`, retaining a temporary full copy at publication. Admission happens after compression, even for an input that cannot be retained. Native compression state is created for each miss. | Consider chunked immutable compressed storage, measured admission by size/reuse, and a bounded reusable codec pool if profiling supports it. Preserve exact UTF-16, first-read identity and concurrent reload ownership. Full final Strings are still required by unchanged String-consuming APIs. |
| 4 | Investigate native allocation and resource disposal | OS working-set high-water marks exceed the Java heap cap substantially, and first-run private committed sampling reached 5.619 GiB. Possible contributors include committed heap residency, codec state/allocator behavior, direct buffers, textures, driver allocations and other JVM memory. | Existing data cannot attribute the difference. Use JFR allocation/GC data plus NMT and Windows process-memory observations on a separate diagnostic run. NMT does not account for every third-party native or GPU allocation; do not subtract independent peaks and label the difference a native leak. |
| 5 | Compact/share immutable bounds and metadata after measuring ownership | The older v0.2.2 post-GC histogram records 2,536,178 AABBs (about 154.8 MiB shallow), large object arrays and property/JSON structures. Some such data may be shareable without changing coordinates. | This is historical shallow-size evidence, not a v0.3.0 retained-size profile. Find current retaining owners first; share only immutable values, keep mutable per-vehicle containers independent, and preserve vertex/bounds multiplicity and exact floor/doorway data. |

Current cache statistics expose 3,010 evictions per epoch but no read/decode/hit
counts or byte/time cost per path. Evictions alone do not prove re-reading or
thrashing. A small set of observational counters and a JFR capture would make the
first three decisions much more reliable.

## Lower-priority approaches

- Reducing the cache from 96 to 64 or 32 MiB reduces its configured admitted-weight
  ceiling by only 32 or 64 MiB. That is not a guaranteed reduction in peak heap:
  additional reads/decompression can offset it. Even eliminating retained text
  cannot remove parser-owned Strings or parsed models.
- Immutable transformed mesh views were already tried in v0.2.3. Although they
  shared source bytes correctly, the historical full-client post-GC shallow total
  increased by about 1.3 MiB and the startup process peak barely changed. This may
  still be a CPU optimization, but it is not an established memory improvement.
- v0.2.4 block interning and v0.2.5 early display selection did not establish a
  useful lower heap in their historical runtime tests. Those older tests were
  dominated by the earlier text path, so they do not prove the ideas are useless
  on v0.3.0; they do rule out presenting the offline byte savings as proven runtime
  benefits. Require current allocation evidence before revisiting them.
- Higher compression levels trade loading CPU for compressed size and do not
  address the complete String/JSON allocations. Texture downscaling and geometry
  reduction would change quality; they are unnecessary for these proposals.

## Recommended next experiment

Keep the delivered 3 GiB baseline. First record a complete startup/reload JFR plus
cache read/decode/digest counters and queued-source bytes. Implement the resource
identity fast lookup as an isolated candidate, then compare against v0.3.0 at the
same heap and pack/mod hashes. Add byte-based parse admission if queued inputs
prove material. Compare GC counts/time, allocations, loading time and OS memory;
retain the complete text, native cache, rendering and repeated F3+T checks. Only
after those results should 2.5 GiB become a lower-heap experiment. There is no
current basis to promise stable 2 GiB operation or a 3 GiB total-process limit.
