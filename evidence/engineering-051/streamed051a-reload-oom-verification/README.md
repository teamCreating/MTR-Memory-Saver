# 051a seventh-reload failed-session seal verification

This directory retains actual separate subprocess receipts, source snapshots, exact indexes and raw stdout/stderr. A verifier integrity exit0 **does not** make the failed game session accepted.

- replay01: actual exit1 because the new verifier used an informal `head` phase instead of original JSON `start`. Original source/index/error are preserved. Captured data/runtime were never changed.
- replay02: actual exit0 for the283-payload initial closure, reproducing final0 and six historical strict prefixes1–6 with original measured spans.
- replay03-final: actual exit0 after additional source/owned-read checks and documentation,285payload. Independent review found the archived waiter constructor's Path.resolve could query original instance directory metadata. Its receipt scope string was too broad for a completely sealed-only claim, although no original payload/JFR/process API was read. The explicit correction and original receipts remain.
- replay04-sealed-only: final actual exit0,285payload/62,274,121bytes. New audit-only SealedProducer initializer retains every context/source/target/plan/launch/PID pin check but compares recorded Windows paths purely lexically. It preserves/reuses the archived importer and replay methods and does not globally patch pathlib. Final source5811f105febc04f40cab287aa0e2aba88f4282c7321670dc89bfb6752ab119ff; final main indexb19f70f80fc34ddd1ebb1603b842240b88c30deca785fc0e84c8a8282415e32a, unchanged before/after. Final peer static review confirms the boundary fix and retained checks.

Each final historical result matches the original compact reload evidence, closed-capture diagnostic review, owned consumer/journal prefix hashes and measured trailing consumer/native spans. The ledger prefix is explicitly derived from immutable terminal rows, not claimed as an original owned-read receipt; subsequent actual inputs occur only after the corresponding wait completes. This does not reconstruct an unsaved mutable native snapshot body or replace the failed complete-prefix summary.

Existing inventory generation registers30 archive Python files,494→524 with all original494 entries identical. Source snapshots of the new verifier are reference-only evidence. Final existing catalog/sample verify actually exits0(524scripts/2datasets/11files); exact stdout/stderr/exits are retained. The earlier523-item catalog/verify run before the sealed-context fix is separately preserved. No production runtime or unit-test code changed; CI for the new commit must be checked independently.

`sha256-index.json` covers this verification directory except itself. No JFR/collector-native-snapshots binary data appears here.

One pre-commit staged-byte audit command exceeded the Windows command-line length when expanding every long path. The agent-reported note preserves that tool-history boundary; the corrected command uses only the exact scope directories and still compares every staged blob. No commit/push or payload change occurred during that failure.
