#!/usr/bin/env python3
"""Bounded source-host orchestration; all workload execution stays in the VM."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path('/home/eric/vm/vm-shared/kdlock')
RAW = ROOT/'bench/results/10.176.26.71/raw/bench/pipecap-unlock-followup-20261021'
CAPTURE = ROOT/'bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/capture-host.py'
LIFETIME = ROOT/'bench/mutex_api_compare/qemu_snapshot.py'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observation', type=int, required=True)
    args = parser.parse_args()
    name = 'observation-'+str(args.observation)
    path = RAW/(name+'-supervisor.json')
    assert not path.exists() and not (RAW/(name+'-host.json')).exists()
    previous = RAW/('observation-'+str(args.observation-1)+'-host.json')
    if previous.exists():
        from datetime import datetime, timezone
        age = (datetime.now(timezone.utc)-datetime.fromisoformat(json.loads(previous.read_text())['captured_utc'])).total_seconds()
        assert age >= min(60 * 2**(args.observation-1), 300), 'observation spacing not reached'
    receipt = dict(accepted=False, observation=args.observation, commands=[],
                   supervisor_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())

    def save():
        path.write_text(json.dumps(receipt, indent=2)+'\n')

    def command(label, argv, data=None, limit=60, filename=None):
        row = dict(name=label, argv=argv, started_ns=time.time_ns(), timeout_seconds=limit,
                   stdin_sha256=hashlib.sha256(data).hexdigest() if data else None)
        receipt['commands'].append(row)
        save()
        with (RAW/(filename or label+'.log')).open('xb') as out, (RAW/(label+'.stderr')).open('xb') as err:
            process = subprocess.Popen(argv, stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                                       stdout=out, stderr=err)
            row['pid'] = process.pid
            save()
            if data is not None:
                process.stdin.write(data)
                process.stdin.close()
            try:
                code = process.wait(timeout=limit)
            except subprocess.TimeoutExpired:
                row.update(error='TIMEOUT; process left intact, no drain claimed', finished_ns=time.time_ns())
                save()
                raise
            row.update(exit_code=code, finished_ns=time.time_ns())
        save()
        return code

    assert command(name+'-host', SSH+['eric@10.176.26.71', 'sudo -n python3 -'],
                   CAPTURE.read_bytes(), filename=name+'-host.json') == 0
    host = json.loads((RAW/(name+'-host.json')).read_text())
    count = len(host['qemu'][0]['tasks'])
    receipt.update(captured_utc=host['captured_utc'], host_threads=count)
    save()
    if count != 67:
        receipt['status'] = 'BLOCKED_HOST_THREAD_COUNT'
        assert command(name+'-lifetime', SSH+['eric@10.176.26.71',
            'sudo -n python3 - --pid 257489 --cmdline-sha256 08a7ad4ddad7da7d6437c5ebcc2987894c2e69b1cd8abd31db0bd491f30ce917'],
            LIFETIME.read_bytes(), filename=name+'-lifetime.json') == 0
        save()
        print(json.dumps(receipt))
        return
    assert host['pins_verified'] and host['snapshot_listed']
    assert command(name+'-copy-host', ['scp', '-q', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-P', '2222',
        str(RAW/(name+'-host.json')), 'root@10.176.26.71:/tmp/kdlock-unlock-followup-host.json']) == 0
    guest = b'''import sys,shutil
from pathlib import Path
root=Path('/root/host_fs/kdlock')
sys.path.insert(0,str(root/'bench/spin_cacheline'))
import bench_runtime as r
r.idle()
old=Path('/root/kdlock-evidence/10.176.26.71/bench/pipecap-unlock-20261021')
b=old.parent/'pipecap-unlock-followup-20261021'
b.mkdir(exist_ok=True)
script=Path('/tmp/kdlock-unlock-followup-timing-1.py')
shutil.copyfile(root/'bench/mutex_api_compare/unlock_run.py',script)
args=[sys.executable,script,'--mode','timing','--inputs',old/'inputs-1/inputs.json','--inputs-sha256','daf7f77beda2704d9cc56291f9864489f733c844f6188cd6c8198480539badae','--output',b/'timing-1','--host-state','/tmp/kdlock-unlock-followup-host.json','--unit-checks',old/'checks-1/result.json','--task-check',old/'task-2/result.json','--elf-checks',old/'elf-checks-2.json','--correctness',old/'correctness-1/result.json','--source-commit','2fb3cf06cba373b889728d0edb52ed40869cf7ab']
print(r.command(args,b/'timing-1-command.log',timeout=600),flush=True)
'''
    (RAW/'timing-1-guest-supervisor.py').write_bytes(guest)
    code = command('timing-1-console', SSH+['-p', '2222', 'root@10.176.26.71',
        'env PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin LC_ALL=C PYTHONDONTWRITEBYTECODE=1 KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z /root/kdlock-translation-venv-20261019/bin/python3 -'], guest, 660)
    # No remote log reads or model round trip before the endpoint capture.
    endpoint = command('host-after-timing-1', SSH+['eric@10.176.26.71', 'sudo -n python3 -'],
                       CAPTURE.read_bytes(), filename='host-after-timing-1.json')
    receipt.update(guest_exit_code=code, host_endpoint_exit_code=endpoint,
                   status='RUNNER_COMPLETED' if code == 0 else 'RUNNER_FAILED', finished_ns=time.time_ns())
    save()
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
