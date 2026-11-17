from pathlib import Path
import json, hashlib, shutil, datetime
source = Path('.cache/acceptance/streaming048-validation')
destination = Path('evidence/engineering-051/streamed-blockbench-input')
destination.mkdir(parents=True, exist_ok=False)
mapping = {'01-targeted-nf248':'01', '02-final-nf248':'02', '03-string-negative-control':'03', '04-frozen-nf248':'04', '06-corrected-final-nf248':'06', '07-corrected-final-nf265':'07'}
archive_map = {}
for original, identifier in mapping.items():
    for path in sorted((source/original).rglob('*')):
        if not path.is_file(): continue
        relative = Path('runs')/identifier/path.relative_to(source/original)
        copy = destination/relative
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, copy)
        if path.read_bytes() != copy.read_bytes(): raise AssertionError('Archive copy mismatch: '+str(path))
    archive_map[identifier] = str((source/original).resolve())
for name in ['run-final-builds.py', 'run-final-builds-after-test-correction.py', 'seal-evidence.py']:
    shutil.copyfile(source/name, destination/name)
(destination/'archive-map.json').write_bytes((json.dumps(archive_map, indent=2)+'\n').encode('utf8'))
final_runs = {}
for identifier in ['06', '07']:
    run = destination/'runs'/identifier
    command = json.loads((run/'command.json').read_text(encoding='utf8'))
    tests = json.loads((run/'test-summary.json').read_text(encoding='utf8'))
    totals = {key:sum(int(t[key]) for t in tests) for key in ['tests','failures','errors','skipped']}
    if command['exit_code'] != 0 or totals != {'tests':99,'failures':0,'errors':0,'skipped':0}: raise AssertionError('Final validation failed')
    manifest = json.loads((run/'source-sha256.json').read_text(encoding='utf8'))
    if any(hashlib.sha256(Path(name).read_bytes()).hexdigest()!=sha for name,sha in manifest.items()): raise AssertionError('Frozen source changed')
    artifacts = json.loads((run/'artifact-sha256.json').read_text(encoding='utf8'))
    for name, detail in artifacts.items():
        artifact = run/name
        if artifact.stat().st_size!=detail['size'] or hashlib.sha256(artifact.read_bytes()).hexdigest()!=detail['sha256']: raise AssertionError('Artifact hash mismatch')
        if name.endswith('.build.json'):
            identity = json.loads(artifact.read_text(encoding='utf8'))
            if hashlib.sha256((run/identity['artifact']).read_bytes()).hexdigest()!=identity['sha256']: raise AssertionError('Manifest artifact mismatch')
            if 'companionSha256' in identity and hashlib.sha256((run/identity['companionArtifact']).read_bytes()).hexdigest()!=identity['companionSha256']: raise AssertionError('Probe companion mismatch')
    final_runs[identifier] = {'target':command['argv'][2].split('=',1)[1], 'exit_code':command['exit_code'], 'tests':totals, 'source_changed':[], 'artifacts':artifacts}
now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds')
assessment = {'schema_version':1, 'sealed_at':now, 'version':'0.4.8', 'status':'engineering_checks_passed_runtime_not_accepted', 'final_runs':final_runs,
 'native_provider_contract':{'mtr_sha256':'ff2b753d03f2bcc000d053a9014e4250c8ba720daa9b69b6899fe7dc26be1efa', 'default_provider_sites':5, 'asm_contract_passed_both_official_targets':True, 'actual_mixin_weaving_claimed':False},
 'retained_failures':[{'run':'03','exit_code':1,'type':'OutOfMemoryError at complete String.join','scope':'64MiB fixture, explicit decoded length/workspace limits; not a client acceptance'}, {'run':'04','exit_code':1,'tests':99,'failures':1,'type':'test used current pending > 0 after beginReload installed a new empty epoch','production_change_for_correction':False,'old_manifest_matches_new_jar':False}],
 'allocation_control':{'heap_bytes':67108864,'decoded_units':41943042,'digest':'5b0390cb3134dc6f7b26634b704c8d62833d07a887ae0fd0b446cf384ef03053','snapshot_exit_code':0,'complete_string_exit_code':1,'limits':'explicit fixture overrides, not production defaults','native_schema_equal':True,'settled':True},
 'runtime_acceptance':{'accepted':False,'scope':'Runtime checks and performance are separate evidence; these engineering results do not award game acceptance.','release_work_remaining_elsewhere':['NF248/NF265 actual 24 lifecycle + 18 strict resource checks and wrong-binary rejection','fresh all-16-pack 20 reloads','A/B, A/A and observer-overhead controls','CI and release documentation'], 'outside_release_scope':['interaction coverage','two-hour route']},
 'limitations':['Streaming removes the module-owned complete Blockbench input String, not the native Gson DOM/model heap.','Unknown providers retain get/String fallback; native DEBUG retains its local-file path.','Capability counters cover explicit wrappers, not arbitrary unknown providers; in-progress AtomicLong snapshots are not instantaneous conservation equations.','Early runs 01/02 predate the final late-error handling/counters; run02 source snapshot records one changed test file that was not copied.','Run04 built a JAR before test failure but did not execute buildManifest/verifyRelease; copied stale manifest is explicitly ineligible.','Standalone allocation audit stderr retains a Log4j missing-provider diagnostic; it is not a game run.']}
(destination/'assessment.json').write_bytes((json.dumps(assessment,indent=2)+'\n').encode('utf8'))
readme = f"""# Streamed Blockbench input candidate 0.4.8

Sealed at {now}. These are engineering results; no packaged-client or full-pack acceptance is awarded here.

The old 0.4.7 fourth-reload failure is preserved in `../../engineering-050/owned049d-reload-attempt03-oom/`. Both OOM stacks fail at the module's complete `String.join` input materialization. That stack locates an allocation; it does not prove a generation leak.

The candidate adds an explicit snapshot capability only at five audited native default `ResourceProvider` arguments. The exact MTR SHA is `ff2b753d03f2bcc000d053a9014e4250c8ba720daa9b69b6899fe7dc26be1efa`; ASM tests check their method-reference producer and downstream call descriptors. Unknown providers still call their actual `get`; native DEBUG still uses its original String/local-file path. Snapshot capture decodes with strict length/cancellation checks into one `CREATE_NEW/READ/WRITE/DELETE_ON_CLOSE` UTF-16 channel, hashes equivalent UTF-8 bytes, and feeds the existing shaded Gson/Blockbench parser through a bounded Reader. No full module-owned input String is created on that capability path. This does not bound the native Gson DOM or model heap.

`Prepared` owns the snapshot through parsing. Success and content aliases close it before publication/subscription. Cancellation, retirement, timeout, parse and close errors retain the original outcome and independent suppressed failures without cause cycles. Source-close failures cannot transfer a snapshot. Failed facades include the dynamic resource ID. Capability counters bind to the wrapper's creation epoch so late old work cannot inflate a new epoch's stream count; the log explicitly scopes these counts to native snapshot capability attempts.

## Final checked artifacts

| Target | Product SHA-256 | Product manifest | Probe SHA-256 | Probe manifest |
|---|---|---|---|---|
| NF248 | `34c0b27780f7a3d4d5f29845f98a655f22cae0b1eeca1a4a95ab86b60921b0c1` | `runs/06/mtr-memory-saver-official-nf248-0.4.8.build.json` | `ad5e9cccf272559c62dcf35f9fbe237e2bd1c6f896cb06bfb692e604d5e4c79a` | `runs/06/mtr-memory-saver-official-nf248-0.4.8-acceptance-probe.build.json` |
| NF265 | `89720d30c76b4f5dfc6a71a398bb67c3138cf4f8f4e0afd0dbb062753552e735` | `runs/07/mtr-memory-saver-official-nf265-0.4.8.build.json` | `ad5e9cccf272559c62dcf35f9fbe237e2bd1c6f896cb06bfb692e604d5e4c79a` | `runs/07/mtr-memory-saver-official-nf265-0.4.8-acceptance-probe.build.json` |

Runs 06 and 07 each execute `test verifyRelease probeJar probeManifest streamingBlockbenchInputAudit`: exit 0, **99 tests / 0 failures / 0 errors / 0 skipped**. Their original command receipts, raw stdout/stderr, JUnit XML, byte-exact source snapshots, source fingerprints, product/probe JARs and identity manifests are retained. Source hashes still match at sealing. The runner executes the targets sequentially and stops on failure. Only official NF248/NF265 were validated; v6 validation stays paused.

## Preserved controls and failure

- Run 01: early targeted 59/59; it is not the final source validation.
- Run 02: intermediate 92/92 and successful stream fixture, before late-failure handling/counters. Its `source-snapshot-status.json` names the subsequently changed test source that was not copied; no replacement is presented as the earlier file.
- Run 03: one actual exit-1 complete-String control. The same generated 40 MiB whitespace plus `{{}}` input under a 64 MiB heap fails at `SegmentedResourceText.read:47 / String.join`. The snapshot path succeeds with the same digest and native serialized schema, and settles all ownership. Explicit fixture size/workspace limits differ from production defaults. This isolates input copying; it is not a 3 GiB game claim.
- Run 04: 99 tests / 1 failure, preserved unchanged. The new race test incorrectly asserted `current.pending > 0` after `beginReload` had replaced the current epoch with an empty one. The correction only asserts current pending 0 and retirement still blocked, retaining the not-yet-canceled old future, both closed owners, released permits/tickets and original Cancellation/suppressed-error checks. Product logic did not change for this correction. `artifact-eligibility.json` documents that this failed build's copied old manifest does not match its newer JAR; neither is accepted as a final pair.
- Runs 06/07: final corrected source, both 99/99 plus successful snapshot fixture. The retained Log4j missing-provider stderr line belongs to the standalone audit, not a Minecraft run.

`archive-map.json` maps compact run directories to the original ignored paths. `SHA256SUMS.json` covers every payload except itself. The actual final-build and sealing scripts are included. Later runtime smoke, wrong-binary, twenty-reload and performance evidence must remain separate. Interaction coverage and a two-hour route are outside the revised 0.4.8 release scope.
"""
(destination/'README.md').write_bytes(readme.encode('utf8'))
files = {p.relative_to(destination).as_posix():{'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(destination.rglob('*')) if p.is_file()}
(destination/'SHA256SUMS.json').write_bytes((json.dumps(files,indent=2)+'\n').encode('utf8'))
print(json.dumps({'destination':str(destination),'sealed_at':now,'payload_files':len(files),'payload_bytes':sum(v['size'] for v in files.values())},indent=2))
