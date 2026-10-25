#!/usr/bin/env python3
"""Prepare/review offline; --execute requires separate approval for this exact cycle.

Owns one host SSH and at most the two fixed guest SSH controls, without retries,
signals, context-manager waits or timeout kills. An unknown completion stays
unknown even if a later local SSH exit is observed. Never qualifies a benchmark.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import time

import diagnostic_observer as observer

HERE = Path(__file__).resolve().parent
SSH = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=3',
       '-o', 'StrictHostKeyChecking=yes', '-o', 'ControlMaster=no',
       '-o', 'ControlPath=none', '-o', 'ClearAllForwardings=yes']
OWNED = []  # Keep ownership explicit; never use Popen as a context manager.
GUEST_LIMIT = 16384
BOOTSTRAP = """import os
size = bytearray()
while not size.endswith(b'\\n'):
    part = os.read(0, 1)
    if not part or len(size) > 12: raise ValueError('missing/bad source size')
    size.extend(part)
count = int(size)
if not 0 < count <= 1048576: raise ValueError('source bound')
source = bytearray()
while len(source) < count:
    part = os.read(0, count - len(source))
    if not part: raise EOFError('incomplete reviewed source')
    source.extend(part)
exec(compile(source, '<reviewed diagnostic>', 'exec'), {'__name__':'__main__'})
"""


def payload():
    files = {name: (HERE / name).read_bytes() for name in
             ('host_capture_control.py', 'diagnostic_observer.py', 'kdmm31.json')}
    expected = json.loads(files['kdmm31.json'])['host']
    code = ('import sys,types\nm=types.ModuleType("host_capture_control")\n' +
            'exec(compile(' + repr(files['host_capture_control.py']) +
            ', "host_capture_control.py", "exec"),m.__dict__)\n' +
            'sys.modules[m.__name__]=m\nn=types.ModuleType("diagnostic_observer")\n' +
            'exec(compile(' + repr(files['diagnostic_observer.py']) +
            ', "diagnostic_observer.py", "exec"),n.__dict__)\n' +
            'raise SystemExit(n.main(' + repr(expected) + '))\n').encode()
    return code, {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}


class Channel:
    """Nonblocking child pipes with durable raw bytes and sticky uncertainty."""
    def __init__(self, command, limit, logs, popen=None):
        self.child = (popen or subprocess.Popen)(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, start_new_session=True)
        OWNED.append(self.child)
        self.command, self.limit, self.logs = command, limit, logs
        self.data = {'stdout': bytearray(), 'stderr': bytearray()}
        self.eof = set()
        self.input = bytearray()
        self.uncertain = True
        self.deadline_failed = False
        self.output_failed = False
        self.io_error = None
        self.code = None
        for pipe in (self.child.stdin, self.child.stdout, self.child.stderr):
            os.set_blocking(pipe.fileno(), False)

    def send(self, data):
        if len(self.input) + len(data) > 1024 * 1024:
            raise ValueError('child input bound')
        self.input.extend(data)

    def poll(self):
        fresh = {}
        errors = []
        already_over_limit = self.output_failed
        # Drain one bounded chunk from BOTH streams before any stdin write.
        # Even a failed acknowledgement write must preserve available evidence.
        for name in ('stdout', 'stderr'):
            if name in self.eof or already_over_limit:
                continue
            try:
                data = os.read(getattr(self.child, name).fileno(), 65536)
            except BlockingIOError:
                continue
            except OSError as error:
                errors.append(error)
                continue
            if not data:
                self.eof.add(name)
            else:
                # Preserve the consumed overflow chunk too; do not erase partial
                # stdout because a child failed, timed out or exceeded a limit.
                self.logs[name].write(data)
                self.logs[name].flush()
                self.data[name].extend(data)
                fresh[name] = data
                if sum(map(len, self.data.values())) > self.limit:
                    self.output_failed = True
                    errors.append(ValueError('child output bound; completion unconfirmed'))
        if self.input and not self.io_error and not errors:
            try:
                size = os.write(self.child.stdin.fileno(), self.input)
                del self.input[:size]
            except BlockingIOError:
                pass
            except OSError as error:
                errors.append(error)
        self.code = self.child.poll()
        if errors:
            self.io_error = repr(errors[0])
            self.uncertain = True
            raise errors[0]
        done = self.code is not None and len(self.eof) == 2
        if done and not self.deadline_failed and not self.output_failed and not self.io_error:
            self.uncertain = False
        return fresh, done

    def receipt(self):
        return dict(pid=self.child.pid, command=self.command, returncode=self.code,
                    local_exit_observed=self.code is not None, eof=sorted(self.eof),
                    completion_unconfirmed=self.uncertain, deadline_failed=self.deadline_failed,
                    output_failed=self.output_failed,
                    io_error=self.io_error,
                    stdout_base64=base64.b64encode(self.data['stdout']).decode(),
                    stderr_base64=base64.b64encode(self.data['stderr']).decode())


class Coordinator:
    """Host events govern launch order. No cross-host clock arithmetic."""
    def __init__(self, start_guest, send, now=time.monotonic_ns):
        self.start_guest, self.send, self.now = start_guest, send, now
        self.stopped = False
        self.reason = None
        self.active = None
        self.next_phase = 0
        self.events = []
        self.receipts = []
        self.final = None
        self.input = bytearray()

    def stop(self, reason):
        if not self.stopped:
            self.stopped, self.reason = True, reason
            self.send(dict(kind='controller_stop', reason=reason, source_monotonic_ns=self.now()))

    def feed(self, data):
        self.input.extend(data)
        if len(self.input) > observer.MAX_LINE:
            raise ValueError('host event line exceeds bound')
        rows = []
        while b'\n' in self.input:
            line, _, rest = self.input.partition(b'\n')
            self.input = bytearray(rest)
            rows.append(json.loads(line))
        # A stop already delivered in the same read wins over any queued request.
        if any(row.get('kind') in ('stop', 'final') for row in rows):
            self.stopped = True
        for row in rows:
            kind = row.get('kind')
            if kind == 'stop':
                self.reason = row.get('reason')
            if kind == 'final':
                if self.final is not None:
                    raise ValueError('duplicate host final')
                self.final = row
            if kind != 'launch_request':
                continue
            self.events.append(dict(source_received_ns=self.now(), request=row))
            phases = list(observer.GUEST_COMMANDS)
            request = row['request']
            if (self.stopped or self.active or self.next_phase >= len(phases) or
                    request['name'] != phases[self.next_phase] or
                    request['id'] != self.next_phase + 1 or
                    row['command'] != observer.GUEST_COMMANDS[request['name']]):
                raise ValueError('guest request after stop, pending work or wrong phase/order')
            name = request['name']
            begin = self.now()
            channel = self.start_guest(name, observer.GUEST_COMMANDS[name])
            self.active = dict(id=request['id'], name=name, channel=channel,
                               deadline=begin + 8 * observer.NS, reported=False)
            self.next_phase += 1
            self.send(dict(kind='launched', id=request['id'], pid=channel.child.pid,
                           source_launch_before_ns=begin, source_launch_after_ns=self.now()))

    def poll(self):
        if not self.active:
            return
        active = self.active
        channel = active['channel']
        try:
            _, done = channel.poll()
        except (OSError, ValueError) as error:
            channel.deadline_failed = True
            self.stop(repr(error))
            return
        if self.now() >= active['deadline'] and not active['reported']:
            channel.deadline_failed = channel.uncertain = True
            active['reported'] = True
            self.receipts.append(dict(name=active['name'], **channel.receipt()))
            self.stop('guest eight-second observation deadline; remote completion unknown')
        if done and not active['reported']:
            active['reported'] = True
            receipt = dict(name=active['name'], **channel.receipt())
            # Nonzero SSH exit cannot prove whether a remote command completed.
            if channel.code != 0:
                channel.uncertain = True
                receipt['completion_unconfirmed'] = True
            self.receipts.append(receipt)
            self.send(dict(kind='completed', id=active['id'], source_observed_ns=self.now(), **receipt))
            if receipt['completion_unconfirmed']:
                self.stop('SSH completion is unconfirmed')
            self.active = None


def execute(output, channel_factory=Channel, now=time.monotonic_ns, sleep=time.sleep):
    output.mkdir(parents=True, exist_ok=False)
    code, hashes = payload()
    record = dict(accepted=False, observation_complete=False, live_approval_external=True,
                  source_hashes=hashes, payload_sha256=hashlib.sha256(code).hexdigest(),
                  controller_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  host_completion_unconfirmed=True, guest_completion_unconfirmed=True)
    files = []
    host = coordinator = None
    start = now()
    owned_start = len(OWNED)
    cpu_start = time.process_time_ns()
    def save():
        (output / 'controller.json').write_text(json.dumps(record, indent=2) + '\n')
    def logs(stem):
        result = {name: (output / (stem + '.' + name)).open('xb') for name in ('stdout', 'stderr')}
        files.extend(result.values())
        return result
    try:
        save()
        command = shlex.join(['sudo', '-n', '/usr/bin/python3', '-c', BOOTSTRAP])
        host = channel_factory([*SSH, 'eric@10.176.26.71', command], observer.MAX_OUTPUT,
                               logs('host'))
        record['host_ssh_pid'] = host.child.pid
        save()
        host.send(str(len(code)).encode() + b'\n' + code)
        def send(row):
            host.send((json.dumps(row) + '\n').encode())
        def guest(name, command):
            return channel_factory([*SSH, '-p', '2222', 'root@10.176.26.71', command],
                                   GUEST_LIMIT, logs(name))
        coordinator = Coordinator(guest, send, now)
        host_done = False
        while now() - start < 75 * observer.NS:
            try:
                data, host_done = host.poll()
                coordinator.feed(data.get('stdout', b''))
                coordinator.poll()
            except (OSError, ValueError, EOFError) as error:
                coordinator.stop(repr(error))
                record.setdefault('errors', []).append(repr(error))
                # One terminal transport/format failure; no retry or drain claim.
                break
            if host_done:
                if coordinator.input or coordinator.final is None:
                    coordinator.stop('host EOF without a complete final receipt')
                break
            sleep(0.01)
        else:
            host.deadline_failed = host.uncertain = True
            coordinator.stop('source 75-second observation deadline; host completion unknown')
        final = coordinator.final or {}
        record.update(host_returncode=host.code, host_completion_unconfirmed=host.uncertain,
                      guest_completion_unconfirmed=bool(coordinator.active) or any(
                          row['completion_unconfirmed'] for row in coordinator.receipts),
                      host_final=coordinator.final, guest_receipts=coordinator.receipts,
                      launch_events=coordinator.events, stop_reason=coordinator.reason)
        if coordinator.active:
            record['pending_guest'] = dict(name=coordinator.active['name'],
                                           **coordinator.active['channel'].receipt())
        record['observation_complete'] = (not host.uncertain and host.code == 0 and
            not record['guest_completion_unconfirmed'] and final.get('observation_complete') is True
            and len(coordinator.receipts) == 2 and not record.get('errors'))
    except BaseException as error:
        record.setdefault('errors', []).append(repr(error))
        if host:
            record.update(host_ssh_pid=host.child.pid, host_completion_unconfirmed=True)
        if coordinator and coordinator.active:
            record['pending_guest'] = dict(name=coordinator.active['name'],
                                           **coordinator.active['channel'].receipt())
    finally:
        # An interruption must not erase acknowledgements already accumulated.
        if coordinator:
            record.update(guest_receipts=coordinator.receipts, launch_events=coordinator.events,
                          host_final=coordinator.final, stop_reason=coordinator.reason,
                          guest_completion_unconfirmed=bool(coordinator.active) or any(
                              row['completion_unconfirmed'] for row in coordinator.receipts))
            if coordinator.active:
                record['pending_guest'] = dict(name=coordinator.active['name'],
                                               **coordinator.active['channel'].receipt())
        record['owned_local_ssh_pids'] = [child.pid for child in OWNED[owned_start:]]
        record['source_elapsed_ns'] = now() - start
        record['source_cpu_ns'] = time.process_time_ns() - cpu_start
        record['signals_sent'] = record['retries'] = 0
        record['drain_proven'] = False
        record['limitations'] = ('An issued guest launch may be in flight when the host detects a stop. '
            'A local SSH exit does not resolve an earlier unknown completion. '
            'No result qualifies performance or identifies a worker creation cause.')
        save()
        # These are our local receipt files, not child pipes or remote resources.
        for file in files:
            file.close()
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--execute', action='store_true',
                        help='requires external approval for this exact live diagnostic')
    args = parser.parse_args()
    if not args.execute:
        code, hashes = payload()
        print(json.dumps(dict(executed=False, source_hashes=hashes,
                              payload_sha256=hashlib.sha256(code).hexdigest()), indent=2))
        return 0
    if args.output is None:
        parser.error('--execute requires a new --output directory')
    def interrupted(signum, frame):
        raise observer.ObserverAbort('controller interrupted: ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    result = execute(args.output)
    print(json.dumps(result, indent=2))
    return int(not result['observation_complete'])


if __name__ == '__main__':
    raise SystemExit(main())
