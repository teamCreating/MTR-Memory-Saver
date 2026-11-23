# Snapshot digest capture optimization

The candidate computes its UTF-8 content digest while decoded characters are
written to the owned UTF-16 snapshot. This removes a complete snapshot read
before parsing. Parsing still consumes the immutable snapshot, and capture
retains bounded buffers, length admission and explicit file ownership.

The writer accepts an offset so the UTF-8 digest encoder can carry a high
surrogate across chunks without writing that carried character twice.
The regression test checks a real snapshot channel with zero reads during
capture, exact restored text and the original String UTF-8 digest.
Read, rewind and cancellation fault controls exercise the consumer reader,
where those operations now occur.

Both official targets passed 106 Java tests and the existing 64 MiB heap
Blockbench and OBJ streaming controls before the user narrowed subsequent
validation to NeoForge 21.1.265. Later runtime validation uses 21.1.265.

The initial diagnostic used a real 65,255,687-byte Blockbench input and six
balanced AB/BA pairs of fresh JVMs. Each JVM performed three warmup captures
followed by three measured capture/readback operations. All twelve results
matched the independent Python SHA-256. No trial was omitted.
The benchmark-thread CPU median changed by -16.88% and elapsed median by
-18.50%. The baseline and candidate for this initial diagnostic carry NF248
metadata. Its raw evidence preserves that identity.

Other workstation tasks continued. The initial packaged client overlapped the
beginning of the diagnostic. Thread CPU excludes JVM helper threads and system
I/O work. This one-input diagnostic has no AA calibration and provides no
whole-client memory or loading acceptance.

The initial NF248 client completed all sixteen packs, 1,092 declarations,
651 unique Blockbench parses, 974 OBJ parses and 69 packaged component checks.
Its native log records stopping. The initial 60-second owned wait expired,
and later observation found its process absent. Its actual exit code was not
retained. Those historical records remain in raw-evidence.zip.

[assessment.json](assessment.json) retains the initial measurements and scope.
[payloads.json](payloads.json) indexes the original selected ZIP payload hashes.
Subsequent NF265 evidence and the final scoped decision are recorded separately.
The product remains an unpublished 0.4.8 candidate.

The subsequent [NF265 runtime](nf265-runtime.json) loads all sixteen packs at a
3 GiB heap, registers 1,092 declarations and completes 651 Blockbench plus 974
OBJ parses. All 24 lifecycle, 18 strict-resource and 27 OBJ checks pass.
The actual owned JVM, PID 21632, stops through the native probe exit path and
returns exit code zero. Its candidate SHA-256 is
920c1f833b6f173c7443ff5956493b779acfeceb293fa640817a459985db3f5b.
nf265-runtime.zip retains the plan, exact artifact metadata, actual exit receipt
and native logs, including the expected fault-injection exceptions.

The user selected NF265 for subsequent validation. The target matrix still
describes existing builds. New runtime and benchmark work in this continuation
uses NF265. Historical NF248 results retain their original identity.

The [NF265 diagnostic comparison](nf265-benchmark.json) repeats six AB/BA pairs
against the preserved NF265 candidate, SHA-256 134770ac…,
using the new 920c1f83… binary. The agent-owned game JVM had exited before
this benchmark began. Every sample is retained. Median benchmark-thread CPU
changes by -19.237%, with all six pairs improving by 16.59–23.01%.
Median elapsed time changes by -19.371%, with all six pairs improving by
16.14–23.11%. These are capture/hash/readback measurements for the same
single model, with three warmup and three measured iterations per JVM.
nf265-benchmark.zip retains the frozen inputs, raw per-process outputs,
driver source, results and runner.

JAR comparison finds three changed class payloads and the new capture-reader
anonymous class. The other member payloads match the preceding NF265 candidate.
No third-party binary or resource artwork is included in the selected archive.
The model input and candidate JARs remain in the local ignored cache, bound by
their recorded hashes. Replaying the benchmark requires those inputs.
