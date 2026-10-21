#!/usr/bin/env python3
"""Source-host supervisor for bounded read-only host and serial guest controls.

The observer timestamps phase acknowledgements on the host clock. Source-host
send/receive brackets also bound clock offsets; no synchronized-clock assumption.
No workload rates from these intrusive diagnostics qualify for acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import queue
import shlex
import subprocess
import threading
import time

ROOT = Path('/home/eric/vm/vm-shared/kdlock')
CAPTURE = ROOT/'bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/capture-host.py'
TRACE = ROOT/'bench/mutex_api_compare/qemu_trace.py'
GUEST = ROOT/'bench/mutex_api_compare/qemu_guest_control.py'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
       '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3']


def stamp():
    return dict(real_ns=time.time_ns(), mono_ns=time.monotonic_ns())


class Stream:
    def __init__(self, out, label, argv, receipt, save, mixed_output=False):
        self.receipt, self.save = receipt, save
        self.mixed_output = mixed_output
        self.record = dict(label=label, argv=argv, started=stamp())
        receipt['streams'].append(self.record)
        self.error = (out/(label+'.stderr')).open('xb')
        self.output = (out/(label+'.jsonl')).open('x')
        self.items = queue.Queue()
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self.error, text=True, bufsize=1)
        self.record['pid'] = self.proc.pid
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()
        save()

    def read(self):
        try:
            for line in self.proc.stdout:
                received = stamp()
                if self.mixed_output:
                    data = json.loads(line.removeprefix('KD_PHASE ')) if line.startswith('KD_PHASE ') else dict(event='stdout', text=line)
                else:
                    data = json.loads(line)
                row = dict(received=received, remote=data)
                self.output.write(json.dumps(row)+'\n')
                self.output.flush()
                self.items.put(row)
        except Exception as error:
            self.items.put(dict(reader_error=repr(error)))
        finally:
            self.items.put(None)

    def until(self, event, key=None, value=None, limit=20):
        deadline = time.monotonic()+limit
        while True:
            row = self.items.get(timeout=max(.001, deadline-time.monotonic()))
            assert row is not None and 'reader_error' not in row, row
            data = row['remote']
            if data['event'] == event and (key is None or data.get(key) == value):
                return row
            assert time.monotonic() < deadline, 'stream acknowledgement timed out'

    def request(self, key, value, event, limit=20):
        sent = stamp()
        self.proc.stdin.write(json.dumps({key: value})+'\n')
        self.proc.stdin.flush()
        row = self.until(event, key, value, limit)
        result = dict(stream=self.record['label'], key=key, value=value,
                      sent=sent, ack=row)
        self.receipt['requests'].append(result)
        self.save()
        return result

    def finish(self):
        self.proc.stdin.close()
        code = self.proc.wait(timeout=20)
        self.reader.join(timeout=5)
        assert not self.reader.is_alive()
        self.output.close()
        self.error.close()
        self.record.update(exit_code=code, finished=stamp())
        self.save()
        assert code == 0, self.record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=('host', 'guest', 'guest-setup', 'sync', 'basic', 'workload'), required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    receipt = dict(mode=a.mode, accepted=False, complete=False, streams=[], requests=[], commands=[],
                   source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                   sources={}, started=stamp())
    for src in (Path(__file__), TRACE, GUEST, CAPTURE, ROOT/'bench/mutex_api_compare/unlock_run.py'):
        data = src.read_bytes()
        (out/src.name).write_bytes(data)
        receipt['sources'][str(src)] = hashlib.sha256(data).hexdigest()

    def save():
        (out/'supervisor.json').write_text(json.dumps(receipt, indent=2)+'\n')

    save()
    observer_command = shlex.join(['sudo', '-n', 'python3', '-u', '-c', TRACE.read_text(),
        '--pid', '257489', '--cmdline-sha256',
        '08a7ad4ddad7da7d6437c5ebcc2987894c2e69b1cd8abd31db0bd491f30ce917',
        '--duration', '600' if a.mode == 'workload' else ('120' if a.mode == 'sync' else '110'),
        '--interval', '0.5'])
    observer = Stream(out, 'observer', SSH+['eric@10.176.26.71', observer_command], receipt, save)
    try:
        observer.until('ready')
        initial = observer.until('sample')['remote']
        receipt['initial_task_count'] = len(initial['tasks'])
        save()
        assert receipt['initial_task_count'] == 67, 'control postponed: wait for original idle 67 tasks'
        mark = lambda value: observer.request('marker', value, 'marker')
        mark('host-only-idle')
        time.sleep(8)
        if a.mode in ('sync', 'basic'):
            if a.mode == 'sync':
                commands = [('sync-dry-run', ['python3', str(ROOT/'tools/vm/sync_to_vm.py'), '--dry-run']),
                            ('sync-write', ['python3', str(ROOT/'tools/vm/sync_to_vm.py')])]
            else:
                code = '''import hashlib,json,os,sys,subprocess
from pathlib import Path
assert os.uname().release == '6.1.159-kdclobber2'
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == '88449cfc-cea9-4647-a294-bc601e372146'
sys.path.insert(0,'/root/host_fs/kdlock/bench/spin_cacheline')
import bench_runtime as r
r.idle()
root=Path('/root/host_fs/kdlock')
sources=[root/'tests/unit/Makefile', *sorted((root/'tests/unit/basic').glob('*.c')), root/'daemon/daemon.c', *sorted((root/'daemon').glob('*.inc')), *sorted((root/'include').glob('*.h'))]
before={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
print(json.dumps(dict(unit_input_sha256=before)),flush=True)
subprocess.run(['make','-B','-C','/root/host_fs/kdlock/tests/unit','run'],check=True)
assert before == {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
print(json.dumps(dict(unit_sources_unchanged=True)),flush=True)
r.idle()
'''
                command = shlex.join(['env', 'PYTHONDONTWRITEBYTECODE=1', 'LC_ALL=C',
                    'PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                    '/root/kdlock-translation-venv-20261019/bin/python3', '-c', code])
                commands = [('basic-build-test', SSH+['-p', '2222', 'root@10.176.26.71', command])]
            for label, argv in commands:
                mark(label+'-before')
                record = dict(label=label, argv=argv, started=stamp())
                receipt['commands'].append(record)
                save()
                with (out/(label+'.stdout')).open('xb') as stream, (out/(label+'.stderr')).open('xb') as error:
                    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=stream, stderr=error, cwd=ROOT)
                    record['pid'] = proc.pid
                    code = proc.wait(timeout=45 if a.mode == 'sync' else 60)
                record.update(exit_code=code, finished=stamp())
                mark(label+'-after')
                assert code == 0
                time.sleep(3)
            time.sleep(5)
        elif a.mode in ('host', 'workload'):
            mark('snapshot-query-before')
            argv = SSH+['eric@10.176.26.71', 'sudo -n python3 -']
            record = dict(label='existing-capture-host', argv=argv, started=stamp())
            receipt['commands'].append(record)
            save()
            with (out/'host-snapshot.json').open('xb') as stream, (out/'host-snapshot.stderr').open('xb') as error:
                proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=stream, stderr=error)
                record['pid'] = proc.pid
                proc.stdin.write(CAPTURE.read_bytes())
                proc.stdin.close()
                code = proc.wait(timeout=45)
            record.update(exit_code=code, finished=stamp())
            mark('snapshot-query-after')
            assert code == 0
            if a.mode == 'host':
                time.sleep(10)
            else:
                host = json.loads((out/'host-snapshot.json').read_text())
                assert len(host['qemu'][0]['tasks']) == 67 and host['pins_verified'] and host['snapshot_listed']
                mark('guest-workload-setup-before')
                launch = '''import json,os,shutil,subprocess,sys
from pathlib import Path
root=Path('/root/host_fs/kdlock')
base=Path('/root/kdlock-evidence/10.176.26.71/bench/qemu-workers-20261021')
base.mkdir(exist_ok=True)
name=NAME
host=base/(name+'-host.json')
with host.open('x') as stream: json.dump(HOST,stream)
runner=base/(name+'-runner.py')
with runner.open('xb') as stream: stream.write((root/'bench/mutex_api_compare/unlock_run.py').read_bytes())
old=base.parent/'pipecap-unlock-20261021'
args=[sys.executable,str(runner),'--mode','timing','--phase-single-outer','--inputs',str(old/'inputs-1/inputs.json'),'--inputs-sha256','daf7f77beda2704d9cc56291f9864489f733c844f6188cd6c8198480539badae','--output',str(base/name),'--host-state',str(host),'--unit-checks',str(old/'checks-1/result.json'),'--task-check',str(old/'task-2/result.json'),'--elf-checks',str(old/'elf-checks-2.json'),'--correctness',str(old/'correctness-1/result.json'),'--source-commit',COMMIT]
sys.exit(subprocess.call(args))
'''.replace('NAME', repr(out.name)).replace('HOST', repr(host)).replace('COMMIT', repr(receipt['source_commit']))
                (out/'guest-launch.py').write_text(launch)
                command = shlex.join(['env', 'PYTHONDONTWRITEBYTECODE=1', 'LC_ALL=C',
                    'PATH=/root/kdlock-translation-venv-20261019/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                    'KDLOCK_RECOVERY_CONFIRMED=1', 'KDLOCK_SNAPSHOT_TAG=before-mutex-kdonly-20261017T140354Z',
                    '/root/kdlock-translation-venv-20261019/bin/python3', '-u', '-c', launch])
                guest = Stream(out, 'workload', SSH+['-p', '2222', 'root@10.176.26.71', command], receipt, save, mixed_output=True)
                receipt['phases'] = []
                while True:
                    event = guest.items.get(timeout=240)
                    if event is None:
                        break
                    assert 'reader_error' not in event, event
                    row = event['remote']
                    if row['event'] != 'phase':
                        continue
                    ack = mark(f"phase{row['sequence']}-{row['label']}-{row['edge']}")
                    sent = stamp()
                    guest.proc.stdin.write(json.dumps(dict(phase_ack=row['sequence']))+'\n')
                    guest.proc.stdin.flush()
                    receipt['phases'].append(dict(guest_event=event, host_ack=ack, guest_ack_sent=sent))
                    save()
                guest.finish()
                mark('guest-workload-exit-after')
                time.sleep(5)
        else:
            mark('guest-ssh-setup-before')
            command = shlex.join(['/root/kdlock-translation-venv-20261019/bin/python3', '-u', '-c',
                                  GUEST.read_text(), '--run', out.name])
            guest = Stream(out, 'guest', SSH+['-p', '2222', 'root@10.176.26.71', command], receipt, save)
            guest.until('ready')
            mark('guest-ssh-setup-after')
            actions = (('clock', 'noop', 'clock', 'noop', 'clock', 'noop', 'clock') if a.mode == 'guest-setup' else
                       ('clock', 'noop', 'tmpfs-write', 'tmpfs-read', 'disk-write', 'disk-read', 'cleanup', 'clock'))
            for index, action in enumerate(actions):
                mark(str(index)+'-'+action+'-before')
                guest.request('action', action, 'end')
                mark(str(index)+'-'+action+'-after')
                time.sleep(3)
            mark('guest-exit-before')
            guest.request('action', 'stop', 'end')
            guest.finish()
            mark('guest-exit-after')
            time.sleep(5)
        mark('stop')
        observer.finish()
        receipt.update(complete=True, finished=stamp())
        save()
    except BaseException as error:
        receipt.update(error=repr(error), finished=stamp(),
                       scope='Failure retained; no unknown process killed and no drain inferred.')
        save()
        # stdin closure ends only our observer/controls. Remote command timeouts
        # are retained; they never prove that other guest work drained.
        for stream in (locals().get('guest'), observer):
            if stream is not None and not stream.proc.stdin.closed:
                stream.proc.stdin.close()
        raise
    print(json.dumps(dict(output=str(out), complete=receipt['complete'], accepted=False)))


if __name__ == '__main__':
    main()
