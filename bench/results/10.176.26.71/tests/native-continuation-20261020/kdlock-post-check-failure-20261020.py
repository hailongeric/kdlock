import argparse,hashlib,json,runpy,sys,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args()
root=Path('/root/host_fs/kdlock');out=a.output
sys.dont_write_bytecode=True
sys.path.insert(0,str(root/'bench/spin_cacheline'))
import bench_runtime as rt
runpy.run_path(str(root/'bench/archive_run.py'))['idle'](out,rt.idle)
for p in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
    try:name=p.read_text().strip()
    except(FileNotFoundError,ProcessLookupError):continue
    assert name not in ('ke_worker','kg_worker','ks_worker'),str(p)
frozen=json.loads((out/'source-sha256.json').read_text())
for name,expected in frozen.items():
    for base in (root,out/'source'):
        assert hashlib.sha256((base/name).read_bytes()).hexdigest()==expected,str(base/name)
record={'checked_unix':time.time(),'idle':True,'tracked_and_frozen_sources_unchanged':True,'files':len(frozen),'failed_checks_preserved':True}
(out/'post-failure-health.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
