import json, os, runpy, subprocess, sys, time
from pathlib import Path

root = Path('/root/host_fs/kdlock')
name = sys.argv[1]
base = Path('/mnt/kdlock-builds/rwsem-opt-20261018')
base.mkdir(exist_ok=True)
out = base / name
env = dict(os.environ, PATH='/root/kdlock-evidence/clobber-20260918/venv/bin:' + os.environ['PATH'],
    LC_ALL='C', PYTHONDONTWRITEBYTECODE='1', KDIR='/root/linux-6.1.159-kdclobber2',
    KDLOCK_RECOVERY_CONFIRMED='1', KDLOCK_SNAPSHOT_TAG='before-mutex-kdonly-20261017T140354Z')
probe = runpy.run_path(str(root / 'tests/kernel/rwsem/run.py'), run_name='preflight')
probe['idle']()
assert not out.exists()
common = ['python3', 'bench/rwlock_compare/run.py', '--collector-cpu', '63', '--output', str(out)]
if name.endswith('-probe'):
    argv = ['python3', 'tests/kernel/rwsem/run.py', '--output', str(out)]
elif name.endswith('-screen'):
    argv = [*common, '--lock-kind', 'rwsem', '--backends', 'native', 'kdlock',
        '--workloads', 'cacheline', '--cachelines', '1', '--write-percent', '1', '20',
        '--threads', '1', '8', '32', '60', '--repeats', '3', '--duration-ms', '2000']
elif name.endswith('-grid'):
    argv = [*common, '--lock-kind', 'rwsem', '--backends', 'native', 'kdlock',
        '--workloads', 'cacheline', 'rcuht', '--cachelines', '1', '8', '--write-percent', '1', '20',
        '--threads', *map(str, [*range(1, 9), *range(12, 61, 4)]),
        '--repeats', '3', '--duration-ms', '2000']
elif name.endswith('-reference'):
    argv = [*common, '--lock-kind', 'rwlock', '--backends', 'native', 'tclock', 'kdlock',
        '--workloads', 'cacheline', 'rcuht', '--cachelines', '1', '8', '--write-percent', '1', '20',
        '--threads', '1', '8', '32', '36', '60', '--repeats', '3', '--duration-ms', '2000']
elif name.endswith('-functional'):
    argv = [*common, '--lock-kind', 'rwsem', '--backends', 'native', 'kdlock',
        '--workloads', 'cacheline', 'rcuht', '--cachelines', '1', '8', '--write-percent', '0', '1', '20',
        '--threads', '1', '8', '--functional', '--repeats', '1', '--iterations', '100000']
elif name.endswith('-local'):
    argv = [*common, '--lock-kind', 'rwsem', '--backends', 'kdlock', '--delegate', 'off',
        '--workloads', 'cacheline', '--cachelines', '8', '--write-percent', '0', '20',
        '--threads', '1', '8', '--functional', '--repeats', '1', '--iterations', '100000']
elif name.endswith('-jit'):
    argv = [*common, '--lock-kind', 'rwsem', '--backends', 'kdlock',
        '--workloads', 'cacheline', 'rcuht', '--cachelines', '8', '--write-percent', '80', '100',
        '--threads', '16', '--functional', '--repeats', '1', '--iterations', '200000', '--require-jit']
else:
    raise ValueError(name)
start = time.monotonic()
print('START', json.dumps(argv), flush=True)
with out.with_suffix('.log').open('xb') as log:
    try:
        rc = subprocess.run(argv, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
                            timeout=7200 if name.endswith('-grid') else 2400).returncode
    except subprocess.TimeoutExpired:
        rc = 'TIMEOUT'
receipt = dict(command=argv, returncode=rc, seconds=time.monotonic()-start)
out.with_suffix('.command.json').write_text(json.dumps(receipt, indent=2)+'\n')
print('END', json.dumps(receipt), flush=True)
print(out.with_suffix('.log').read_text()[-3500:], flush=True)
probe['idle']()
print('IDLE', flush=True)
raise SystemExit(0 if rc == 0 else 1)
