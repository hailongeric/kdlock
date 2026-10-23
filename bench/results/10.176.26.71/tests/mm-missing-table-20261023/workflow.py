#!/usr/bin/env python3
"""Source-host transport and serial transitions; no tests execute on this host."""
import argparse
import io
import json
from pathlib import Path
import runpy
import shlex
import subprocess
import tarfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
RAW=ROOT/'bench/results/10.176.26.71/raw/tests/mm-missing-table-20261023'
BASE='/root/kdlock-evidence/10.176.26.71/tests/mm-missing-table-20261023'
C=runpy.run_path(str(HERE.parent/'serial-continuation-20261022/campaign.py'))
SYNC=runpy.run_path(str(ROOT/'tools/vm/sync_source.py'))
C['boot'].__globals__['PRIOR']=BASE+'/control'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('prepare','build','probe','kd','run','recovery','collect'))
    p.add_argument('--attempt',type=int,default=1)
    a=p.parse_args()
    local=RAW/(a.action+'-'+str(a.attempt));local.mkdir(parents=True)
    if a.action=='prepare':
        assert a.attempt==1
        C['capture'](local/'availability-host.json')
        names={'kernel_integration/mmap_lock/guest-kernel.patch','kernel_integration/mmap_lock/install.py',
               'bench/results/10.176.26.71/tests/mm-resident-partial-20261023/incremental.patch'}
        names.update('kernel_integration/mmap_lock/overlay/'+n for n in ('mm/kd_mmap_unmap.inc','include/linux/kd_mmap_lock.h','include/linux/kd_mmap_lock_types.h','kernel/locking/kd_mmap/unmap.c'))
        for folder in [HERE,*[ROOT/'tests/kernel/mmap_lock'/s for s in ('missing_table','absent_target','zero_target','resident_partial','unmap_body')]]:
            names.update(str(path.relative_to(ROOT)) for path in folder.rglob('*')
                         if path.is_file() and (path.suffix in ('.py','.c','.h','.inc','.patch') or path.name=='Makefile'))
        files={n:C['sha'](ROOT/n) for n in sorted(names)}
        inputs=dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),files=files)
        C['save'](local/'inputs.json',inputs)
        ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-p','2222','root@10.176.26.71',
             'env PYTHONDONTWRITEBYTECODE=1 python3 -c '+shlex.quote(SYNC['REMOTE_CODE'])]
        C['command'](ssh,local/'sync-before.json',120,(json.dumps(dict(operation='inspect',manifest=files))+'\n').encode())
        before=json.loads((local/'sync-before.json').read_text());assert before['idle'] and before['fstype']=='ext4'
        changed=[n for n in files if before['hashes'][n]!=files[n]]
        archive=io.BytesIO()
        with tarfile.open(fileobj=archive,mode='w') as tar:
            for n in changed:tar.add(ROOT/n,arcname=n,recursive=False)
        header=dict(operation='copy',manifest=files,changed=changed,previous={n:before['hashes'][n] for n in changed})
        C['command'](ssh,local/'sync-after.json',180,(json.dumps(header)+'\n').encode()+archive.getvalue())
        after=json.loads((local/'sync-after.json').read_text());assert after['idle'] and after['hashes']==files
        C['guest']('mkdir -p -- '+BASE+'/control',local/'mkdir.log',30)
        C['copy_in']([local/'inputs.json',HERE/'build.py',HERE/'focus.py',HERE/'transition.py',HERE/'hydrate.py'],BASE+'/control/',local/'copy.log')
        host=C['capture'](local/'host.json');assert host['pins_verified'] and host['snapshot_listed']
        C['copy_in']([local/'host.json'],BASE+'/control/',local/'copy-host.log')
    elif a.action=='build':
        C['guest']('unshare --mount --propagation private '+C['remote']([BASE+'/control/build.py','--attempt',str(a.attempt)]),local/'build.log',2400)
        C['fetch'](BASE+'/build-'+str(a.attempt)+'/result.json',local/'result.json')
    elif a.action=='probe':
        assert a.attempt==2
        host=C['capture'](local/'host.json');assert host['pins_verified'] and host['snapshot_listed']
        script="""import os,runpy,sys
from pathlib import Path
sys.path.insert(0,'/root/host_fs/kdlock/bench/spin_cacheline')
import bench_runtime as rt
runpy.run_path('/root/host_fs/kdlock/bench/archive_run.py')['idle'](Path('/root'),rt.idle)
assert os.uname().release=='6.1.159-kdmm14'
base=Path(BASE)
for name in ('control-2','probes-2'):(base/name).mkdir()
for name in ('zero_target','missing_table'):(base/'probes-2'/name).mkdir()
""".replace('BASE',repr(BASE))
        C['guest'](C['PY']+" - <<'PYG'\n"+script+'\nPYG',local/'idle-prepare.log',60)
        files={}
        for family in ('zero_target','missing_table'):
            sources=[ROOT/'tests/kernel/mmap_lock'/family/name for name in ('client.c','receipts.py','controls.py')]
            files.update({'probes-2/'+family+'/'+path.name:C['sha'](path) for path in sources})
            C['copy_in'](sources,BASE+'/probes-2/'+family+'/',local/('copy-'+family+'.log'))
        sources=[HERE/'focus.py',HERE/'probe_revision.py']
        files.update({'control-2/'+path.name:C['sha'](path) for path in sources})
        C['save'](local/'inputs.json',dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),files=files))
        C['copy_in']([*sources,local/'inputs.json'],BASE+'/control-2/',local/'copy-control.log')
        C['guest'](C['remote']([BASE+'/control-2/probe_revision.py']),local/'probe.log',180)
        C['fetch'](BASE+'/probe-revision-2/result.json',local/'result.json')
    elif a.action=='run':
        host=C['capture'](local/'host.json');assert host['pins_verified'] and host['snapshot_listed']
        C['guest'](C['remote']([BASE+'/control-2/focus.py','--run','focused-'+str(a.attempt),'--probe-revision',BASE+'/probe-revision-2/result.json']),local/'focused.log',1200)
        C['fetch'](BASE+'/focused-'+str(a.attempt)+'/result.json',local/'result.json')
    elif a.action in ('kd','recovery'):
        guest=BASE+'/'+a.action+'-'+str(a.attempt)
        C['guest']('mkdir -- '+guest,local/'mkdir.log',30)
        transition=C['boot'](a.action,guest,local)
        if a.action=='kd':
            C['guest'](C['remote']([BASE+'/control-2/focus.py','--build-attempt','1','--run','focused-'+str(a.attempt),'--probe-revision',BASE+'/probe-revision-2/result.json']),local/'focused.log',1200)
            C['fetch'](BASE+'/focused-'+str(a.attempt)+'/result.json',local/'result.json')
        else:C['save'](local/'result.json',transition)
    else:
        # One small transport of new logs/receipts/sources, never old archives
        # or duplicate kernel ELFs. The guest retains original probe binaries.
        script="""import json,tarfile,sys
from pathlib import Path
base=Path(BASE)
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as tar:
 for p in sorted(base.rglob('*')):
  if p.is_file() and not p.is_symlink() and (p.suffix in ('.json','.log','.c','.h','.py','.inc') or p.name=='Makefile'):
   tar.add(p,arcname=str(p.relative_to(base)),recursive=False)
""".replace('BASE',repr(BASE))
        C['guest'](C['PY']+" - <<'PYG'\n"+script+'\nPYG',local/'essential.tar.gz',180)
        C['save'](local/'receipt.json',dict(file='essential.tar.gz',bytes=(local/'essential.tar.gz').stat().st_size,sha256=C['sha'](local/'essential.tar.gz')))
    print(json.dumps(dict(action=a.action,passed=True)),flush=True)


if __name__=='__main__':main()
