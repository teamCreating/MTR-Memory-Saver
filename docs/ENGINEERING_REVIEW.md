# Engineering review — 2026-11-13 (UTC+08:00)

The 0.3.x project is a credible, carefully observed optimization experiment. It is
not yet a maintainable general-purpose release. Its evidence establishes bounded
**admitted text-cache weight** and successful particular fixtures. It does not
establish a bound on the loader's total live memory, acceptable reload latency,
arbitrary compatibility, or reliable failed-load recovery.

## Correctness and ownership precede further heap reductions

The most serious gap is not documentation. `SharedBlockbenchCache` stores futures
in an identity pending map and normally completes them only when native
`setModelLoaded` runs. The inspected official `BlockbenchModelLoader` catches a
parse exception, logs it and decrements its native pending counter without calling
`setModelLoaded`. A failed shared parse can therefore leave an unresolved future
and pending identity entry. The old reload path clears one concurrent map and
increments a separate epoch counter; it is not an atomic generation swap.
Cancellation/timeout, failed construction and reload races need terminal outcomes
and idempotent cleanup. Publishing an empty successful model to conceal an error
would make this worse.

The v6 close guard is valuable, but protects consumer publication only. It does not
by itself cancel queued work or clean the source-future graph. Source groups,
property-dependent destination groups and GPU owners must remain separate.
Their ownership cannot be inferred from the number of cache entries alone.

## The cache budget is a local contract

The old reader constructs a complete String, compresses it, then performs LRU
admission. Temporary output, concurrent misses, restored Strings, native JSON/model
objects and queued parse suppliers are outside the advertised cache budget. A
source-cache hit still retrieves and hashes that complete String. This reduces
retained memory but can repeatedly allocate and scan large inputs.

The current sixteen-pack fixture includes a 65,255,687-byte Blockbench input.
An input-size guard and a bounded executor must be checked against such real inputs,
not selected so generously that they cease to constrain anything or so narrowly
that normal authored models are silently rejected. Controlled text bytes and active
parses are measurable limits; they still are not a whole-process RAM cap. Native
model/GPU memory remains workload-dependent.

## Build and release identity are part of correctness

The old default selects 0.1.1. The recommended 0.3.x implementation is assembled by
feature booleans and same-name source replacement. A maintainer can change an
inactive copy or produce an untested combination. Independent Git did not remove
the instance marker, launcher-private Python API and patched-client prerequisites.

Stable common code must have one active location. Official and v6 have genuinely
different Color and GPU lifecycle ABIs, so explicit target source directories are
appropriate; arbitrary feature permutations are not release presets. The target
matrix must determine source directories, binary fingerprint, loader version,
metadata, tests and artifact name together. Default development builds should
resolve their own dependencies without reading a game-test marker.

Checking SHA-256 only at build time does not identify the JAR later loaded by the
user. Exact runtime fingerprints and closed loader ranges prevent a same-version
replacement or future NeoForge build from inheriting acceptance automatically.

## Evidence needs a repeatable decision procedure

The historical v6 measurements include ten/eleven reload Full GCs and about
13.5 seconds of cumulative GC pauses. That is a real cost, not a footnote to a
successful 3 GiB startup. The heap cap, sixteen exact packs, target JAR, scheduler,
world/camera, observation windows and instrumentation must be identical when
comparing implementations. Allocation, load/reload elapsed time, pause distributions,
frame intervals and post-reload retained state are distinct outcomes.

Class-file equivalence is excellent refactor evidence but cannot establish Mixin
application, GL ownership or gameplay. Conversely, a screenshot of a rendered train
cannot establish failed-load cleanup. Both headless adversarial tests and an explicit
runtime acceptance protocol are necessary. Historical raw evidence stays immutable;
new candidates get their own report and never inherit an older “pass”.

## Engineering sequence and limits

1. **0.4.0:** deterministic stable presets, Gradle dependency bootstrap, canonical
   source locations, closed target matrix, runtime fingerprint guard, release
   identity, license and concise entry documents.
2. **0.4.1:** bounded resource-read/parse admission, path/provider fast lookup,
   atomic generation retirement, explicit terminal failure/cancellation and
   independently checked cleanup. Keep native parser/model algorithms intact.
3. **Acceptance:** bring core source/text/mesh audits into this repository, run
   repeatable headless failure/churn/reload tests and paired real-input benchmarks,
   and supply a separate runtime probe/protocol for Mixin, native caches and GPU
   ownership. Publish runtime support only for artifacts actually observed.

These changes can make development and verification reproducible. They do not
convert a short benchmark into a long-session GPU leak proof or promise universal
MTR compatibility. Public release hosting also remains a separate action until a
remote/release destination is configured.

## Engineering changes completed — 2026-11-14 (UTC+08:00)

The active line has advanced through **0.4.0**, **0.4.1** and **0.4.2**. These are
development candidates, with a single version authority and four closed presets.

| Original gap | Implemented change | Evidence boundary |
| --- | --- | --- |
| Instance-bound builds and source substitution | Gradle bootstrap, canonical common/target sources, deterministic bundles | Four builds; 0.4.0 historical-class equivalence and clean rebuild hash equality |
| Unbounded raw queued work and hanging failed loads | Descriptor admission, provider/path fast hits, native inline parse scope, failure/timeout/retirement cleanup | Adversarial lifecycle tests and 1,000-generation churn |
| Cache budget applied after compression | Pre-compression oversized bypass, pre-insertion LRU eviction, bounded compression and decoded-size checks | Exact UTF-16, admission and failure tests |
| Audits outside the independent repository | Native mesh/display/JSON audits, explicit real-model runner, standalone JFR analyzer and optional client probe JAR | Native-reference tests, three actual model parses, NF248 official/v6 client Mixin smoke and 100 v6 GPU ownership cycles |
| Memory-only performance claims | Three alternating paired real-input source-lookup runs with hashes, equal 3 GiB heap, JFR and GC logs | Microbenchmark only; a digest substitutes for native parsed meshes |
| Compatibility/download ambiguity | Exact MTR runtime guard, exact loader ranges, support matrix, license, local release bundles and CI | Public release hosting and full-client support certification remain unrecorded |

The paired source benchmark lowered digest calls from 24 to 8 and allocation from
about 1.59 GB to 458 MB for four exact inputs over two generations and three
queries. Baseline elapsed time ranged from 17.36 to 44.23 seconds; candidate ranged
from 4.16 to 5.42 seconds. The unusually slow first baseline is preserved. This is
evidence for reducing repeated source work, not a whole-game loading/GC/frame
improvement. Reports and raw data are under `evidence/engineering-042/`.

Real client checks also found an incorrect v6 metadata version in the initial
0.4.0/0.4.1 presets. Those builds compiled but their strict dependency rejected the
custom version at startup. 0.4.2 corrects the exact version and verifies metadata
against the audited binary during every build. The original failed run is retained.
The official/v6 client smoke passes and v6's 100 synthetic GPU cycles establish
specific client injection/ownership behavior, using current development classes;
they do not certify a complete packaged release or a long gameplay session.

The next release gate is a controlled full-pack comparison, followed by repeated
reload and a long route session.
The historical Full-GC pause cost remains unresolved at that level. Provider-held
data, native/foreign parsing, JSON/model expansion and GPU lifetime still prevent a
whole-load memory ceiling. Engineering made these limits explicit and testable;
it did not eliminate them by lowering the minimum startup heap.
