"""Seal the completed probe-only build evidence without modifying any source input."""
import datetime as dt, hashlib, json, pathlib, shutil, subprocess, zipfile
root=pathlib.Path.cwd(); base=root/'evidence/engineering-049/publisher-race/sealed-01'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assessment=json.loads((base/'build-assessment.json').read_text(encoding='utf-8'))
versions=[]
for entry in assessment['targets']:
    target=entry['target']; output=base/target
    manifest=json.loads((output/pathlib.Path(entry['manifest']).name).read_text(encoding='utf-8'))
    for name,digest in manifest['inputs'].items():
        source=root/name
        assert sha(source)==digest,(target,name)
        destination=base/'source'/name;destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.exists():assert destination.read_bytes()==source.read_bytes()
        else:shutil.copyfile(source,destination)
    previous=root/f'evidence/engineering-048/neutral-diagnostics/final-{target}/mtr-native-observer-{target}-1.0.2.jar'
    previous_copy=output/'reference-1.0.2.jar';shutil.copyfile(previous,previous_copy)
    jar=output/pathlib.Path(entry['artifact']).name
    with zipfile.ZipFile(previous) as old,zipfile.ZipFile(jar) as new:
        old_names=set(old.namelist());new_names=set(new.namelist())
        assert old_names==new_names
        changed=[name for name in sorted(old_names) if old.read(name)!=new.read(name)]
        classes=[name for name in new_names if name.endswith('.class')]
        class_changes=[name for name in changed if name.endswith('.class')]
        assert class_changes==['dev/abenli/probeio/AtomicSnapshot$Windows.class','dev/abenli/probeio/AtomicSnapshot$WindowsApi.class','dev/abenli/probeio/AtomicSnapshot.class'],class_changes
        window='dev/abenli/probeio/AtomicSnapshot$Windows.class'
        before,after=old.read(window),new.read(window)
        assert len(before)==len(after)
        debug_byte_changes=[{'offset':i,'before':a,'after':b} for i,(a,b) in enumerate(zip(before,after)) if a!=b]
        assert len(debug_byte_changes)==2,debug_byte_changes
        javap=pathlib.Path(json.loads((output/'execution.json').read_text())['java_home'])/'bin/javap.exe'
        disassemblies=[]
        for label,source_jar in (('reference',previous),('candidate',jar)):
            command=[str(javap),'-classpath',str(source_jar),'-p','-c','dev.abenli.probeio.AtomicSnapshot$Windows']
            run=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE);assert run.returncode==0
            (output/f'windows-helper-{label}-code.javap.txt').write_bytes(run.stdout)
            disassemblies.append(run.stdout)
        assert disassemblies[0]==disassemblies[1]
        assert set(changed)-set(class_changes)=={'META-INF/MANIFEST.MF','META-INF/neoforge.mods.toml','mtr-native-observer-target.json'}
        identity=json.loads(new.read('mtr-native-observer-target.json'))
        assert identity['observer_version']=='1.0.3' and identity['target']==target
        for name in ('capabilities.json','mtr-native-observer.mixins.json'):assert old.read(name)==new.read(name)
    jfr=root/f'build/neutral-probe/{target}/frame-events.jfr'
    shutil.copyfile(jfr,output/'frame-events.jfr')
    java=pathlib.Path(json.loads((output/'execution.json').read_text())['java_home'])/'bin/jfr.exe'
    args=[str(java),'summary',str(output/'frame-events.jfr')]
    start=dt.datetime.now(dt.timezone.utc).isoformat()
    process=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    (output/'jfr-summary.stdout.log').write_bytes(process.stdout);(output/'jfr-summary.stderr.log').write_bytes(process.stderr)
    (output/'jfr-summary.execution.json').write_text(json.dumps({'argv':args,'started_at':start,'finished_at':dt.datetime.now(dt.timezone.utc).isoformat(),'exit_code':process.returncode},indent=2)+'\n',encoding='utf-8')
    assert process.returncode==0
    versions.append({'target':target,'reference_sha256':sha(previous_copy),'candidate_sha256':sha(jar),'all_class_count':len(classes),'unchanged_class_count':len(classes)-len(class_changes),'changed_classes':class_changes,'windows_helper_instruction_disassembly_identical':True,'windows_helper_debug_line_byte_changes':debug_byte_changes,'changed_version_metadata':sorted(set(changed)-set(class_changes)),'declared_input_count':len(manifest['inputs']),'all_declared_inputs_match':True})
# Add tests, build invocation and the documentation sources that the build manifest does not declare.
for name in ('tools/probes/io/test/dev/abenli/probeio/AtomicSnapshotTest.java','tools/probes/neutral/README.md','gradle.properties','gradlew.bat','gradle/wrapper/gradle-wrapper.properties','gradle/wrapper/gradle-wrapper.jar','evidence/engineering-049/publisher-race/build_and_seal.py','evidence/engineering-049/publisher-race/seal_completed.py'):
    source=root/name;destination=base/'source'/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
for folder in ('tools/probes/neutral/test',):
    for source in (root/folder).rglob('*.java'):
        destination=base/'source'/source.relative_to(root);destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
original=json.loads((base.parent/'before.json').read_text(encoding='utf-8'))
assert all(sha(base.parent/'old-sources'/name)==digest for name,digest in original['old_source_sha256'].items())
product_checks={name:sha(root/name)==digest for name,digest in original['product_sha256'].items()}
assert all(product_checks.values()),[name for name,passed in product_checks.items() if not passed]
report={'timestamp':dt.datetime.now(dt.timezone.utc).isoformat(),'targets':versions,'preserved_original_source_count':len(original['old_source_sha256']),'unchanged_recorded_product_input_count':len(product_checks),'unchanged_product_jars':json.loads((base/'product-before.json').read_text()),'limits':'Probe engineering and independent Windows I/O fixtures only; no client start, installed application, reload, gameplay, endurance or performance acceptance. Initial failed restrictive-reader assumption and earlier unstructured build logs remain separate.'}
(base/'artifact-review.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
