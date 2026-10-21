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
    def __init__(self, out, label, argv, receipt, save):
        self.receipt, self.save = receipt, save
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
                row = dict(received=stamp(), remote=json.loads(line))
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
    p.add_argument('--mode', choices=('host', 'guest'), required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    receipt = dict(mode=a.mode, accepted=False, complete=False, streams=[], requests=[], commands=[],
                   source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                   sources={}, started=stamp())
    for src in (Path(__file__), TRACE, GUEST, CAPTURE):
        data = src.read_bytes()
        (out/src.name).write_bytes(data)
        receipt['sources'][str(src)] = hashlib.sha256(data).hexdigest()

    def save():
        (out/'supervisor.json').write_text(json.dumps(receipt, indent=2)+'\n')

    save()
    observer_command = shlex.join(['sudo', '-n', 'python3', '-u', '-c', TRACE.read_text(),
        '--pid', '257489', '--cmdline-sha256',
        '08a7ad4ddad7da7d6437c5ebcc2987894c2e69b1cd8abd31db0bd491f30ce917',
        '--duration', '110', '--interval', '0.5'])
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
        if a.mode == 'host':
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
            time.sleep(10)
        else:
            mark('guest-ssh-setup-before')
            command = shlex.join(['/root/kdlock-translation-venv-20261019/bin/python3', '-u', '-c',
                                  GUEST.read_text(), '--run', out.name])
            guest = Stream(out, 'guest', SSH+['-p', '2222', 'root@10.176.26.71', command], receipt, save)
            guest.until('ready')
            mark('guest-ssh-setup-after')
            for index, action in enumerate(('clock', 'noop', 'tmpfs-write', 'tmpfs-read', 'disk-write', 'disk-read', 'cleanup', 'clock')):
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
