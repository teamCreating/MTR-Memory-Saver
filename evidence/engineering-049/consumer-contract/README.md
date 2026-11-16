# Reviewed neutral observer consumer versions

The Python recorder and packaged-client consumer use the actual installed
observer metadata and the reviewed `config/native-observer-consumer.json`
contract. The contract permits diagnostic observer 1.0.2 and repaired publisher
1.0.3; it rejects unreviewed versions, another observer/schema and missing or
non-boolean capabilities. The recorder and consumer preserve this configuration
with their source hashes. A configuration change invalidates the run. Native
snapshot read failures remain visible without retries.

The controls retain native process/count/cache/epoch/diagnostic checks and the
complete immutable input-attempt ledger. They do not invent unavailable companion
workspace/counter fields, remove failed inputs or change the 15-second input-before
criterion. The Windows reader still opens one complete file with read/write/delete
sharing; the actual publisher repair is audited separately in `../publisher-race/`.

`run-01/` preserves the first focused invocation: 100 tests, exit 1, three failures
in existing real-time auxiliary-sampling tests. Their 0.3–0.6-second observation
windows collected fewer samples during the concurrent build/stress work. The
other 97 tests pass, including the new contract and recorder source-change
controls. All eleven recorded source/configuration hashes are unchanged across
that execution. Original stdout/stderr, exact argv/times/exit and runner bytes
remain separate from any later execution.

`run-02-targeted/` reruns only those three unchanged tests after the Gradle test
JVMs exit. Two pass; the shutdown-completion test still returns code 1. Original
test cleanup removes its temporary observation directory, so neither failing
execution retains the detailed summary needed to attribute that failure exactly.
The standard output retains the short windows' sample counts; the route fixture
requires coverage within 25 milliseconds of each 100-millisecond window edge.
These tests use the existing companion observer path (`metadata=None`), outside
the changed neutral version/capability checks.

`run-03-diagnostic/` runs that same shutdown test once with a wrapper that copies
its completed output after the observation returns and before unittest cleanup.
The unchanged test passes. Retained raw records show 16 valid samples over
0.3026212 seconds, all three route windows covered, and exactly one auxiliary
request completed at 0.3361170 seconds with `post_sampling_window=true`. The
worker exits and the sampling end remains 0.3026212 seconds. No test threshold,
test assertion, production scheduling or timing source was changed. This supplies
a retained successful shutdown trace; it does not erase the earlier failures or
prove their exact cause. There is no single all-green full-suite execution in
this checkpoint.

These are engineering checks. Generated native epochs, synthetic input receipts
and version-adjusted fixture snapshots do not establish actual 1.0.3 application,
twenty game reloads, gameplay, endurance or performance acceptance. No game is
launched or controlled by this review.

Run the focused suite in a fresh directory with the project Python environment:

```powershell
./.venv/Scripts/python.exe -X utf8 evidence/engineering-049/consumer-contract/run_review.py <fresh-output-name>
```

Additional arguments select existing unittest names without changing their code.
The execution record preserves each selected name, source fingerprint and result.
