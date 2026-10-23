#!/usr/bin/env python3
"""Freeze a tiny observer update and reuse existing, verified MM transitions."""
import argparse
import json
from pathlib import Path
import runpy
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
C = runpy.run_path(str(HERE.parent / 'serial-continuation-20261022/campaign.py'))
PRIOR = '/root/kdlock-evidence/10.176.26.71/tests/mm-mixed-partial-20261023'
C['boot'].__globals__['PRIOR'] = PRIOR + '/control-2'
BASE = '/mnt/kdlock-builds/mm-mixed-matrix-20261023'
RAW = ROOT / 'bench/results/10.176.26.71/raw/tests/mm-mixed-matrix-20261023'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('prepare', 'kd', 'recovery', 'collect'))
    p.add_argument('--attempt', type=int, default=1)
    a = p.parse_args(); assert a.attempt > 0
    local = RAW / f'{a.action}-{a.attempt}'; local.mkdir(parents=True)
    if a.action == 'prepare':
        assert a.attempt == 1, 'frozen inputs never overwritten'
        host = C['capture'](local / 'host.json'); assert host['pins_verified'] and host['snapshot_listed']
        script = f'''import os,sys,runpy,json,shutil
from pathlib import Path
root=Path('/root/host_fs/kdlock');sys.path.insert(0,str(root/'bench/spin_cacheline'));import bench_runtime as rt
runpy.run_path(str(root/'bench/archive_run.py'))['idle'](Path('/root'),rt.idle)
assert os.uname().release=='6.1.159-kdclobber2'
assert shutil.disk_usage('/').free>8_000_000 and shutil.disk_usage('/mnt/kdlock-builds').free>5_000_000
base=Path({BASE!r});base.mkdir()
(base/'control-1').mkdir();(base/'probes-1/mixed_partial').mkdir(parents=True)
print(json.dumps(dict(idle=True,release=os.uname().release,root_free=shutil.disk_usage('/').free,data_free=shutil.disk_usage('/mnt/kdlock-builds').free)))
'''
        C['guest'](C['PY'] + " - <<'PYG'\n" + script + '\nPYG', local / 'idle.json', 60)
        sources = {f'control-1/{name}': HERE / name for name in ('prepare.py', 'focus.py', 'workflow.py')}
        sources.update({f'probes-1/mixed_partial/{name}': ROOT / 'tests/kernel/mmap_lock/mixed_partial' / name
                        for name in ('client.c', 'receipts.py', 'controls.py')})
        inputs = dict(commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                      files={name: C['sha'](path) for name, path in sources.items()})
        C['save'](local / 'inputs.json', inputs)
        C['copy_in']([HERE / n for n in ('prepare.py', 'focus.py', 'workflow.py')] + [local / 'inputs.json'],
                     BASE + '/control-1/', local / 'copy-control.log')
        C['copy_in']([sources['probes-1/mixed_partial/' + n] for n in ('client.c', 'receipts.py', 'controls.py')],
                     BASE + '/probes-1/mixed_partial/', local / 'copy-client.log')
        C['guest'](C['remote']([BASE + '/control-1/prepare.py']), local / 'build.log', 240)
        C['fetch'](BASE + '/build-1/result.json', local / 'result.json')
    elif a.action in ('kd', 'recovery'):
        block = BASE + f'/{a.action}-{a.attempt}'
        C['guest']('mkdir -- ' + shlex.quote(block), local / 'mkdir.log', 30)
        transition = C['boot'](a.action, block, local)
        if a.action == 'kd':
            C['guest'](C['remote']([BASE + '/control-1/focus.py', '--run', f'focused-{a.attempt}']), local / 'focused.log', 1200)
            C['fetch'](BASE + f'/focused-{a.attempt}/result.json', local / 'result.json')
        else: C['save'](local / 'result.json', transition)
    else:
        script = f'''import tarfile,sys
from pathlib import Path
base=Path({BASE!r})
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as tar:
 for path in sorted(base.rglob('*')):
  if path.is_file() and not path.is_symlink() and path.suffix in ('.json','.log','.c','.py'):
   tar.add(path,arcname=str(path.relative_to(base)),recursive=False)
'''
        C['guest'](C['PY'] + " - <<'PYG'\n" + script + '\nPYG', local / 'essential.tar.gz', 120)
        C['save'](local / 'receipt.json', dict(file='essential.tar.gz', bytes=(local / 'essential.tar.gz').stat().st_size,
                                             sha256=C['sha'](local / 'essential.tar.gz')))
    print(json.dumps(dict(action=a.action, passed=True)), flush=True)


if __name__ == '__main__': main()
