#!/usr/bin/env python3
"""Source-host orchestration for separately observed collection and preservation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path('/home/eric/vm/vm-shared/kdlock')
RAW = ROOT/'bench/results/10.176.26.71/raw/bench/qemu-workers-20261021'
REPORT = ROOT/'bench/results/10.176.26.71/bench/qemu-workers-20261021'
BASE = '/root/kdlock-evidence/10.176.26.71/bench/qemu-workers-20261021'
NAMES = ['host-1', 'guest-1', 'setup-1', 'sync-1', 'basic-1', 'basic-2', 'sync-2', 'sync-3', 'sync-4', 'phase-1', 'phase-2']


def main():
    spec = importlib.util.spec_from_file_location('worker_controls', ROOT/'bench/mutex_api_compare/qemu_controls.py')
    c = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(c)
    out = RAW/'collection-1'
    out.mkdir(exist_ok=False)
    receipt = dict(mode='collection', accepted=False, complete=False, streams=[], requests=[], commands=[],
        source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        sources={}, started=c.stamp())
    for src in (Path(__file__), c.TRACE, REPORT/'capture-health.py', Path(c.__file__)):
        data = src.read_bytes()
        (out/src.name).write_bytes(data)
        receipt['sources'][str(src)] = hashlib.sha256(data).hexdigest()

    def save():
        (out/'supervisor.json').write_text(json.dumps(receipt, indent=2)+'\n')

    save()
    argv = c.SSH+['eric@10.176.26.71', shlex.join(['sudo', '-n', 'python3', '-u', '-c', c.TRACE.read_text(),
        '--pid', '257489', '--cmdline-sha256', '08a7ad4ddad7da7d6437c5ebcc2987894c2e69b1cd8abd31db0bd491f30ce917',
        '--duration', '600', '--interval', '0.5'])]
    observer = c.Stream(out, 'observer', argv, receipt, save)
    mark = lambda name: observer.request('marker', name, 'marker')

    def command(label, argv, limit=120):
        mark(label+'-before')
        row = dict(label=label, argv=argv, started=c.stamp(), timeout_seconds=limit)
        receipt['commands'].append(row)
        save()
        with (out/(label+'.stdout')).open('xb') as stdout, (out/(label+'.stderr')).open('xb') as stderr:
            proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
            row['pid'] = proc.pid
            save()
            code = proc.wait(timeout=limit)
        row.update(exit_code=code, finished=c.stamp())
        mark(label+'-after')
        assert code == 0, row

    def guest(code):
        return c.SSH+['-p', '2222', 'root@10.176.26.71', shlex.join([
            'env', 'PYTHONDONTWRITEBYTECODE=1', 'LC_ALL=C',
            'PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
            '/root/kdlock-translation-venv-20261019/bin/python3', '-c', code])]

    try:
        observer.until('ready')
        sample = observer.until('sample')['remote']
        receipt['initial_task_count'] = len(sample['tasks'])
        mark('await-original-67-gate')
        deadline = time.monotonic()+180
        while len(sample['tasks']) != 67 and time.monotonic() < deadline:
            sample = observer.until('sample', limit=5)['remote']
        receipt.update(gate_task_count=len(sample['tasks']), gate_sample_sequence=sample['sequence'])
        save()
        assert len(sample['tasks']) == 67
        mark('host-only-idle')
        time.sleep(5)
        command('read-sync-manifests', c.SSH+['eric@10.176.26.71', shlex.join(['python3', '-c',
            "import json;from pathlib import Path;p=Path('/home/eric/vm/qemu-scripts');print(json.dumps({n:json.loads((p/n).read_text()) for n in ('source-state.json','source-sha256.json')}))"])])
        prepare = f'''import sys,runpy
from pathlib import Path
sys.path.insert(0,'/root/host_fs/kdlock/bench/spin_cacheline')
import bench_runtime as r
base=Path({BASE!r})
runpy.run_path('/root/host_fs/kdlock/bench/archive_run.py')['idle'](base,r.idle)
assert (base/'phase-2/result.json').is_file()
assert not (base/'capture-health.py').exists() and not (base/'final-health.json').exists()
(base/'host-controls').mkdir()
'''
        command('prepare-collection', guest(prepare))
        for name in NAMES:
            state = json.loads((RAW/name/'supervisor.json').read_text())
            assert state['complete'] or (state['commands'] == [] and 'error' in state)
        scp = ['scp', '-r', '-p', '-q', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-P', '2222']
        command('copy-controls', scp+[str(RAW/name) for name in NAMES]+[str(RAW/'ownership-0.json'),
            str(out/'read-sync-manifests.stdout'), 'root@10.176.26.71:'+BASE+'/host-controls/'])
        command('copy-health-source', scp+[str(REPORT/'capture-health.py'), 'root@10.176.26.71:'+BASE+'/capture-health.py'])
        command('health-and-frozen-input-check', guest(f"import subprocess,sys;subprocess.run([sys.executable,{BASE+'/capture-health.py'!r},'--run','phase-2'],check=True)"), 180)
        archive_args = ['/root/host_fs/kdlock/bench/archive_run.py', '--base', BASE, '--output', BASE+'-archives-1',
            '--health', BASE+'/final-health.json', '--group', 'phase=phase-2', '--group', 'controls=host-controls', '--timeout-seconds', '180']
        command('archive', guest(f'import subprocess,sys;subprocess.run([sys.executable]+{archive_args!r},check=True)'), 240)
        command('download-archives', scp+['root@10.176.26.71:'+BASE+'-archives-1', str(out/'archives-1')])
        mark('collection-tail')
        time.sleep(5)
        mark('stop')
        observer.finish()
        receipt.update(complete=True, finished=c.stamp())
        save()
    except BaseException as error:
        receipt.update(error=repr(error), finished=c.stamp(), scope='Retain failure; no timeout proves drain and no child is killed.')
        save()
        if not observer.proc.stdin.closed:
            observer.proc.stdin.close()
        raise
    print(json.dumps(dict(output=str(out), complete=True, accepted=False)))


if __name__ == '__main__':
    main()
