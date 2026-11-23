"""Adapt the existing literal twenty-reload closure to this NF265 session.

Run only after all producers and the owned JVM have stopped. The historical
operators remain unchanged and the derived operator is retained with the proof.
"""
from pathlib import Path
import hashlib, json, sys

repo = Path.cwd().resolve()
root = repo / '.cache/acceptance/release048-nf265'
old = repo / 'evidence/engineering-052/revised048-reload20'
def read(p): return json.loads(p.read_bytes())
def sha(raw): return hashlib.sha256(raw).hexdigest()

def prepare():
    owned = read(root/'endurance-owned-exit.json')
    assert owned['exit_code'] == 0
    client = root/'endurance'
    # The closure's execution inventory is derived from the actual owned wait
    # receipt; it does not claim an independent collector was running.
    files = [client/'packaged-client-plan.json', client/'packaged-client-launch.json']
    files += list((client/'game-probe').glob('*')) + list((client/'logs').glob('*'))
    files = [p for p in files if p.is_file()]
    inventory = {p.relative_to(client).as_posix():sha(p.read_bytes()) for p in files}
    (root/'closed-execution.json').write_text(json.dumps({
        'status':'exited','exit_code':owned['exit_code'],'pid':owned['pid'],
        'ended':next(owned[k] for k in ('ended','ended_at','completed_at','finished_at') if k in owned),
        'receipt':'endurance-owned-exit.json','files':inventory,
        'scope':'Derived closed-file inventory with actual parent-owned process wait; no collector claim.'
    },indent=2)+'\n',encoding='utf-8')

    s=(old/'operators/seal.py').read_text(encoding='utf-8')
    s=s.replace("rec=cache/'obj048-full04-reload-recorder';obs=cache/'obj048-full04-reload-observation';settled=cache/'obj048-full04-post20-settled';collector=cache/'streamed-obj048-client-validation/full-nf248-04'",
        "run=cache/'release048-nf265';rec=run/'recorder03';obs=run/'consumer03';settled=run/'post20';collector=run/'endurance'")
    s=s.replace("execution=read(collector/'execution.json')", "execution=read(run/'closed-execution.json')")
    s=s.replace("post['baseline_completed_epoch_sequence']==21", "post['baseline_completed_epoch_sequence']==22")
    s=s.replace("source=cache/f'obj048-full04-wait-{number:03d}'", "source=run/f'ready-{number+2:03d}'")
    s=s.replace("tree(cache/'obj048-full04-ui',Path('ui'))", "\nfor number in range(3,23):copy(run/f'input-{number:03d}.json',Path('ui')/f'reload-{number-2:03d}.json')")
    s=s.replace("flat(collector,Path('collector-final'),exclude=('native-snapshots.jsonl',))", "\nfor name in ['packaged-client-plan.json','packaged-client-launch.json']:copy(collector/name,Path('collector-final')/name)\ncopy(run/'closed-execution.json',Path('collector-final/execution.json'))\ncopy(run/'endurance-owned-exit.json',Path('collector-final/endurance-owned-exit.json'))")
    s=s.replace("tree(cache/'obj048-full04-final-jfr',Path('jfr-readability'))", "tree(run/'jfr-readability',Path('jfr-readability'))\ncopy(run/'installed-fingerprints.json',Path('installed-fingerprints.json'))\ncopy(run/'candidate.jar',Path('candidate.jar'))")
    s=s.replace("'evidence/engineering-051/streamed-obj-input/runs/02-final-nf248/mtr-memory-saver-official-nf248-0.4.8.jar'", "'candidate.jar'")
    s=s.replace('943b3d455fa3ce9d3ede74bc1a2071ece7bf70b09d9b7f829027347b53a9b588','920c1f833b6f173c7443ff5956493b779acfeceb293fa640817a459985db3f5b')
    (root/'seal.py').write_text(s,encoding='utf-8')

    v=(old/'verify_sealed.py').read_text(encoding='utf-8')
    v=v.replace("'official-nf248'","'official-nf265'")
    start=v.index("   ui=read(HERE/'ui'")
    finish=v.index("  raw=(obs/'samples.jsonl')",start)
    v=v[:start]+"""   ui_path=HERE/'ui'/f'reload-{n:03d}.json';ui=read(ui_path)
   check(sha(ui_path.read_bytes())==e['external_receipt_sha256'],'UI receipt differs')
   check(ui['succeeded'] is True and ui['method']=='native_f3_t' and ui==e['input'],'UI method/receipt differs')
"""+v[finish:]
    v=v.replace("==1,'Fresh startup baseline differs'", "==2,'Recorded post-calibration baseline differs'")
    v=v.replace('list(range(2,22))','list(range(3,23))').replace('list(range(1,22))','list(range(1,23))')
    v=v.replace("x['sequence']==n+1", "x['sequence']==n+2").replace('local,n+1,','local,n+2,')
    v=v.replace("['baseline_completed_epoch_sequence']==21", "['baseline_completed_epoch_sequence']==22")
    v=v.replace("pdata,21,", "pdata,22,").replace("x['sequence']==21", "x['sequence']==22")
    v=v.replace("jar=REPO/binding['candidate_reference']", "jar=HERE/binding['candidate_reference']")
    v=v.replace('Collector JVM did not exit normally','Owned JVM did not exit normally').replace('Closed collector payload differs','Closed process payload differs').replace('Late collector diagnostic failure','Late process diagnostic failure').replace('NF248 full16pack','NF265 full16pack')
    v=v.replace("for name,expected in collector['files'].items():", "owned=read(HERE/'collector-final/endurance-owned-exit.json');check(owned['exit_code']==0 and owned['pid']==p.launch['pid'],'Owned wait receipt differs')\n  for name,expected in collector['files'].items():")
    (root/'verify_sealed.py').write_text(v,encoding='utf-8')
    print(json.dumps({'prepared':True,'owned':owned,'scope':'Operators only; seal and replay still required'}))

if __name__=='__main__':prepare()
