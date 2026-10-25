#!/usr/bin/env python3
"""Proposed 60-second QEMU diagnostic; never an admission/qualification receipt.

No work runs on import. The source controller streams these reviewed bytes only
after separate live approval. Filesystem, clock, wire and monitor are injectable
so the focused tests do not inspect /proc, create a socket or start SSH.
"""
import base64
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import time

from host_capture_control import stat_fields

NS = 1_000_000_000
PERIOD = NS // 2
MAX_GAP = NS // 2
MAX_LINE = 2 * 1024 * 1024
MAX_OUTPUT = 32 * 1024 * 1024
MONITOR_LIMIT = 1024 * 1024
PHASES = ((0, 'binding'), (5, 'idle'), (15, 'metadata'), (25, 'monitor'),
          (35, 'guest_true'), (45, 'guest_hash'), (55, 'tail'))
GUEST_COMMANDS = {'guest_true': '/bin/true',
                  'guest_hash': '/usr/bin/sha256sum -- /boot/vmlinuz-6.1.159-kdmm31'}
IMAGE_SHA = '17f1fa00971f0084bf1b130c7a09f88cb9aae0544adcded61bcfce20484c7040'
POLICY_FIELDS = ('scaling_driver', 'scaling_governor', 'scaling_min_freq',
                 'scaling_max_freq', 'affected_cpus')


class ObserverAbort(BaseException):
    """Do not swallow a watchdog/interrupt as a recoverable per-task read error."""


class ReceiptFailure(Exception):
    """Output failure has already closed admission and our monitor client."""


class Clock:
    def now(self):
        return time.monotonic_ns()

    def cpu(self):
        return time.process_time_ns()

    def stamp(self):
        before = self.now()
        boot = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
        return dict(monotonic_before_ns=before, boottime_ns=boot,
                    monotonic_after_ns=self.now(), process_cpu_ns=self.cpu())

    def sleep(self, seconds):
        time.sleep(seconds)


class Proc:
    """Bound each read and inventory; a stalled kernel read is not safe drain."""
    def read(self, path, limit=65536):
        with open(path, 'rb', buffering=0) as source:
            data = source.read(limit + 1)
        if len(data) > limit:
            raise ValueError('read exceeds bound: ' + path)
        return data

    def names(self, path, limit=1024):
        names = []
        with os.scandir(path) as entries:
            for entry in entries:
                names.append(entry.name)
                if len(names) > limit:
                    raise ValueError('inventory exceeds bound: ' + path)
        return sorted(names)

    def executable(self, path):
        resolved = str(Path(path).resolve(strict=True))
        st = os.stat(path)
        return dict(path=resolved, device=st.st_dev, inode=st.st_ino,
                    size=st.st_size, mtime_ns=st.st_mtime_ns, ctime_ns=st.st_ctime_ns)

    def affinity(self, tid):
        return sorted(os.sched_getaffinity(tid))

    def processor(self):
        return stat_fields(self.read('/proc/self/stat').decode())['processor']


def identity(fs, expected, executable=None):
    pid = int(fs.read('/tmp/kdlock-qemu.pid', 32).strip())
    if pid != expected['pid']:
        raise ValueError('resolved QEMU PID differs from retained VM')
    root = '/proc/' + str(pid)
    first = stat_fields(fs.read(root + '/stat').decode())
    boot = fs.read('/proc/sys/kernel/random/boot_id', 128).decode().strip()
    command = fs.read(root + '/cmdline')
    exe = fs.executable(root + '/exe')
    last = stat_fields(fs.read(root + '/stat').decode())
    if (first['tid'] != pid or last['tid'] != pid or
            first['start_ticks'] != last['start_ticks'] or
            last['start_ticks'] != expected['start_ticks'] or
            boot != expected['boot_id'] or
            hashlib.sha256(command).hexdigest() != expected['command_sha256'] or
            Path(exe['path']).name != 'qemu-system-x86_64' or
            (executable is not None and exe != executable)):
        raise ValueError('QEMU boot/start/command/executable identity differs')
    return dict(pid=pid, boot_id=boot, start_ticks=last['start_ticks'],
                command_sha256=hashlib.sha256(command).hexdigest(), executable=exe)


def sample(fs, clock, expected, executable):
    out = dict(begin=clock.stamp(), tasks=[], errors=[], complete=False)
    root = '/proc/' + str(expected['pid'])
    aborted = False
    try:
        out['identity_before'] = identity(fs, expected, executable)
        out['initial_tids'] = sorted(map(int, fs.names(root + '/task', 256)))
        for tid in out['initial_tids']:
            row = dict(tid=tid, begin=clock.stamp(), complete=False)
            out['tasks'].append(row)
            try:
                path = root + '/task/' + str(tid)
                row['stat_before'] = stat_fields(fs.read(path + '/stat').decode())
                row['runtime_ns'], row['runqueue_wait_ns'], row['timeslices'] = map(
                    int, fs.read(path + '/schedstat', 4096).split())
                row['affinity'] = fs.affinity(tid)
                vcpu = re.fullmatch(r'CPU (\d+)/KVM', row['stat_before']['comm'])
                if not vcpu:
                    row['io'] = fs.read(path + '/io', 8192).decode()
                    row['wchan'] = fs.read(path + '/wchan', 4096).decode().strip()
                row['stat_after'] = stat_fields(fs.read(path + '/stat').decode())
                first, last = row['stat_before'], row['stat_after']
                if first['tid'] != tid or last['tid'] != tid or first['start_ticks'] != last['start_ticks']:
                    raise ValueError('task identity changed within observation')
                if first['comm'] != last['comm']:
                    raise ValueError('task role changed within observation')
                if row['affinity'] != ([int(vcpu[1])] if vcpu else [63]):
                    raise ValueError('task affinity differs from retained placement')
                row.update(start_ticks=last['start_ticks'], complete=True)
            except (OSError, ValueError) as error:
                row['error'] = repr(error)
                out['errors'].append(dict(tid=tid, error=repr(error)))
            row['end'] = clock.stamp()
        out['final_tids'] = sorted(map(int, fs.names(root + '/task', 256)))
        if out['initial_tids'] != out['final_tids']:
            raise ValueError('membership changed within observation')
        vcpus = sorted(int(m[1]) for row in out['tasks']
                       if (m := re.fullmatch(r'CPU (\d+)/KVM', row.get('stat_after', {}).get('comm', ''))))
        if vcpus != list(range(64)):
            raise ValueError('retained 64-vCPU identity differs')
    except (OSError, ValueError) as error:
        out['errors'].append(dict(error=repr(error)))
    except BaseException as error:
        aborted = True
        out['errors'].append(dict(aborted=True, error=repr(error)))
    finally:
        if not aborted:
            try:
                out['identity_after'] = identity(fs, expected, executable)
                out['observer_processor'] = fs.processor()
            except (OSError, ValueError) as error:
                out['errors'].append(dict(phase='identity_after', error=repr(error)))
        out['end'] = clock.stamp()
    out['complete'] = not out['errors']
    return out


def metadata_paths(fs, pid):
    yield '/proc/' + str(pid) + '/numa_maps'
    root = '/sys/devices/system/cpu/cpufreq'
    policies = [name for name in fs.names(root) if re.fullmatch(r'policy\d+', name)]
    if not policies:
        raise ValueError('missing cpufreq policies')
    for policy in policies:
        for field in POLICY_FIELDS:
            yield root + '/' + policy + '/' + field
    root = '/sys/devices/system/node'
    nodes = [name for name in fs.names(root) if re.fullmatch(r'node\d+', name)]
    if not nodes:
        raise ValueError('missing NUMA nodes')
    for node in nodes:
        yield root + '/' + node + '/cpulist'


class Monitor:
    """Nonblocking single connection, one query; retain bytes on every error."""
    def __init__(self, clock, factory=None):
        self.clock = clock
        self.begin = clock.stamp()
        self.deadline = clock.now() + 8 * NS
        self.parts = {'banner': bytearray(), 'response': bytearray()}
        self.state = 'connect'
        self.sent = 0
        self.complete = False
        self.closed = False
        self.error = None
        self.sock = (factory or socket.socket)(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.sock.setblocking(False)
            code = self.sock.connect_ex('/tmp/qemu-monitor.sock')
            if code not in (0, errno.EINPROGRESS, errno.EALREADY, errno.EAGAIN):
                raise OSError(code, 'monitor connect')
            if code == 0:
                self.state = 'banner'
        except BaseException:
            self.close()
            raise

    def step(self):
        if self.clock.now() >= self.deadline:
            raise TimeoutError('monitor total eight-second deadline')
        try:
            if self.state == 'connect':
                code = self.sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                if code:
                    raise OSError(code, 'monitor connect')
                # getpeername distinguishes a pending connection from success.
                try:
                    self.sock.getpeername()
                except OSError as error:
                    if error.errno in (errno.ENOTCONN, errno.EAGAIN):
                        return
                    raise
                self.state = 'banner'
            if self.state == 'send':
                self.sent += self.sock.send(b'info snapshots\n'[self.sent:])
                if self.sent == len(b'info snapshots\n'):
                    self.state = 'response'
                return
            data = self.sock.recv(65536)
            if not data:
                raise EOFError('monitor closed before prompt')
            self.parts[self.state].extend(data)
            if sum(map(len, self.parts.values())) > MONITOR_LIMIT:
                raise ValueError('monitor total output exceeds 1 MiB')
            if self.parts[self.state].endswith(b'(qemu) '):
                if self.state == 'banner':
                    self.state = 'send'
                else:
                    self.complete = True
                    self.close()
        except BlockingIOError:
            return

    def receipt(self):
        return dict(begin=self.begin, end=self.clock.stamp(), complete=self.complete,
                    state=self.state, query_bytes_sent=self.sent, error=self.error,
                    output_base64={key: base64.b64encode(value).decode()
                                   for key, value in self.parts.items()})

    def close(self):
        if not self.closed:
            self.sock.close()  # Only our monitor client, never quit/kill/reset.
            self.closed = True


class Wire:
    """Nonblocking NDJSON channel. A broken channel leaves only partial evidence."""
    def __init__(self, source=0, sink=1):
        self.source, self.sink = source, sink
        os.set_blocking(source, False)
        os.set_blocking(sink, False)
        self.input = bytearray()
        self.output = bytearray()
        self.total = 0

    def emit(self, row):
        data = (json.dumps(row, separators=(',', ':')) + '\n').encode()
        self.total += len(data)
        if len(data) > MAX_LINE or self.total > MAX_OUTPUT or len(self.output) + len(data) > MAX_LINE:
            raise ValueError('observer output/backpressure bound')
        self.output.extend(data)
        self.flush()

    def flush(self):
        if self.output:
            try:
                count = os.write(self.sink, self.output)
                del self.output[:count]
            except BlockingIOError:
                pass

    def receive(self):
        self.flush()
        try:
            data = os.read(self.source, 65536)
            if not data:
                raise EOFError('controller channel closed')
            self.input.extend(data)
        except BlockingIOError:
            pass
        if len(self.input) > 65536:
            raise ValueError('controller input exceeds bound')
        rows = []
        while b'\n' in self.input:
            line, _, rest = self.input.partition(b'\n')
            self.input = bytearray(rest)
            rows.append(json.loads(line))
            if len(rows) > 8:
                raise ValueError('too many controller messages')
        return rows


class Observer:
    def __init__(self, expected, fs, clock, wire, monitor_factory=Monitor):
        self.expected, self.fs, self.clock, self.wire = expected, fs, clock, wire
        self.monitor_factory = monitor_factory
        self.start = clock.now()
        self.cpu_start = clock.cpu()
        self.end = self.start + 60 * NS
        self.stop_reason = None
        self.phase = 'binding'
        self.phase_index = 0
        self.pending = None
        self.baseline = None
        self.executable = None
        self.last_sample_start = None
        self.last_sample_end = None
        self.sample_count = 0
        self.next_sample = self.start
        self.completed = []
        self.max_gap_ns = 0
        self.max_unobserved_gap_ns = 0
        self.next_id = 0
        self.monitor = None
        self.output_error = None
        self.final = None

    def emit(self, kind, **values):
        if self.output_error is not None:
            raise ReceiptFailure(self.output_error)
        try:
            self.wire.emit(dict(kind=kind, phase=self.phase, host=self.clock.stamp(), **values))
        except BaseException as error:
            self.output_error = repr(error)
            # No receipt write is needed to prevent launches or close our socket.
            self.quench('receipt output failed: ' + repr(error))
            self.end = self.clock.now()
            raise ReceiptFailure(self.output_error) from error

    def quench(self, reason):
        if self.stop_reason is None:
            self.stop_reason = reason
            self.end = min(self.end, self.clock.now() + 5 * NS)
        receipt = None
        if self.monitor:
            monitor, self.monitor = self.monitor, None
            monitor.error = reason
            try:
                receipt = monitor.receipt()
            finally:
                monitor.close()
        return receipt

    def stop(self, reason):
        if self.stop_reason is None:
            receipt = self.quench(reason)
            try:
                self.emit('stop', reason=reason, pending=self.pending,
                          further_stimuli_allowed=False, tail_deadline_ns=self.end)
                if receipt:
                    self.emit('monitor_result', **receipt)
            except ReceiptFailure:
                pass  # Partial wire bytes remain evidence; final delivery is not promised.

    def scan(self, immediate=False):
        start = self.clock.now()
        gap = None if self.last_sample_start is None else start - self.last_sample_start
        uncovered = None if self.last_sample_end is None else start - self.last_sample_end
        if gap is not None:
            self.max_gap_ns = max(self.max_gap_ns, gap)
            self.max_unobserved_gap_ns = max(self.max_unobserved_gap_ns, uncovered)
        self.last_sample_start = start
        row = sample(self.fs, self.clock, self.expected, self.executable)
        elapsed = self.clock.now() - start
        self.last_sample_end = self.clock.now()
        keys = {(t['tid'], t['start_ticks']) for t in row['tasks'] if t['complete']}
        added = sorted(keys - self.baseline) if self.baseline is not None else []
        removed = sorted(self.baseline - keys) if self.baseline is not None else []
        self.emit('sample', observation=row, gap_ns=gap, unobserved_gap_ns=uncovered, duration_ns=elapsed,
                  immediate_post_monitor=immediate, new_identities=added, removed_identities=removed)
        self.sample_count += 1
        self.next_sample = start + PERIOD
        if not row['complete']:
            self.stop('incomplete observation or identity/access failure')
        elif added:
            self.stop('first new QEMU task')
        elif elapsed > MAX_GAP or (gap is not None and not 0 <= gap <= MAX_GAP):
            self.stop('task sampling exceeded 500 ms bound')
        elif self.baseline is None:
            self.baseline = keys
            self.emit('inventory_bound', identities=sorted(keys),
                      original_admission_task_count=self.expected['task_count'], accepted=False)

    def acknowledge(self, message):
        if message.get('kind') == 'controller_stop':
            self.stop('controller stopped: ' + str(message.get('reason')))
            return
        if not self.pending or message.get('id') != self.pending.get('id'):
            raise ValueError('unexpected/stale controller acknowledgement')
        kind = message.get('kind')
        if kind == 'launched' and not self.pending.get('launch_ack'):
            self.pending['launch_ack'] = True
            self.emit('launch_ack', request=self.pending.copy(), source_receipt=message,
                      interpretation='launch lies between host request and this acknowledgement')
        elif kind == 'completed' and self.pending.get('launch_ack'):
            self.emit('completion_ack', request=self.pending.copy(), source_receipt=message,
                      interpretation='completion lies after request and before this acknowledgement')
            valid = message.get('local_exit_observed') and message.get('returncode') == 0
            stdout = base64.b64decode(message.get('stdout_base64', ''), validate=True)
            stderr = base64.b64decode(message.get('stderr_base64', ''), validate=True)
            wanted = (b'' if self.pending['name'] == 'guest_true' else
                      (IMAGE_SHA + '  /boot/vmlinuz-6.1.159-kdmm31\n').encode())
            if not valid or stdout != wanted or stderr or message.get('completion_unconfirmed', True):
                raise ValueError('guest completion/output not confirmed')
            if self.clock.now() >= self.pending['deadline_ns']:
                raise TimeoutError('guest acknowledgement missed observation deadline')
            self.completed.append(self.pending['name'])
            self.pending = None
        else:
            raise ValueError('acknowledgement order differs')

    def launch(self, name):
        if self.stop_reason or self.pending:
            raise ValueError('launch after stop or pending phase')
        # No wall-clock projection: both request and acknowledgements carry host
        # monotonic/BOOTTIME brackets. Source times are retained only as source times.
        self.next_id += 1
        self.pending = dict(name=name, id=self.next_id, requested=self.clock.stamp(),
                            deadline_ns=self.clock.now() + 8 * NS, launch_ack=False)
        self.emit('launch_request', request=self.pending.copy(), command=GUEST_COMMANDS[name])

    def run(self):
        metadata = None
        metadata_bytes = 0
        try:
            self.emit('start', accepted=False, workload_started=False, phases=PHASES,
                      sample_period_ns=PERIOD, maximum_sample_start_gap_ns=MAX_GAP,
                      expected=self.expected, observer_affinity=self.fs.affinity(0),
                      observer_processor=self.fs.processor())
            bound = identity(self.fs, self.expected)
            self.executable = bound['executable']
            self.emit('identity_bound', identity=bound)
            self.scan()
            if self.clock.now() >= self.start + 5 * NS:
                self.stop('binding phase deadline')
            while self.clock.now() < self.end - 50_000_000:
                try:
                    for message in self.wire.receive():
                        self.acknowledge(message)
                    if self.clock.now() >= self.next_sample:
                        self.scan()
                    if self.stop_reason:
                        self.clock.sleep(0.01)
                        continue
                    now = self.clock.now()
                    if self.pending and now >= self.pending['deadline_ns']:
                        raise TimeoutError('phase observation deadline; completion unconfirmed')
                    index = max(i for i, (offset, _) in enumerate(PHASES) if now >= self.start + offset * NS)
                    if index != self.phase_index:
                        if index != self.phase_index + 1 or self.pending:
                            raise ValueError('phase order/carryover failure')
                        self.phase_index, self.phase = index, PHASES[index][1]
                        self.emit('phase')
                        if self.phase == 'metadata':
                            metadata = iter(metadata_paths(self.fs, self.expected['pid']))
                            self.pending = dict(name='metadata', deadline_ns=now + 8 * NS)
                        elif self.phase == 'monitor':
                            self.monitor = self.monitor_factory(self.clock)
                            self.pending = dict(name='monitor', deadline_ns=now + 8 * NS)
                        elif self.phase in GUEST_COMMANDS:
                            self.launch(self.phase)
                    if metadata is not None:
                        try:
                            path = next(metadata)
                        except StopIteration:
                            metadata = None
                            self.completed.append('metadata')
                            self.pending = None
                            self.emit('metadata_complete', bytes=metadata_bytes)
                        else:
                            before = self.clock.stamp()
                            data = self.fs.read(path, MONITOR_LIMIT)
                            metadata_bytes += len(data)
                            self.emit('metadata_read', path=path, begin=before,
                                      data_base64=base64.b64encode(data).decode())
                            if metadata_bytes > MONITOR_LIMIT:
                                raise ValueError('metadata bundle exceeds 1 MiB')
                    if self.monitor:
                        self.monitor.step()
                        if self.monitor.complete:
                            monitor, self.monitor = self.monitor, None
                            monitor.close()
                            self.emit('monitor_result', **monitor.receipt())
                            snapshots = monitor.parts['response'].decode(errors='replace')
                            self.pending = None
                            self.completed.append('monitor')
                            # This scan precedes all further external actions.
                            self.scan(immediate=True)
                            if self.expected['snapshot'] not in snapshots:
                                raise ValueError('retained recovery snapshot not listed')
                    self.clock.sleep(0.01)
                except (OSError, ValueError, TimeoutError, EOFError, ReceiptFailure) as error:
                    self.stop(repr(error))
                    metadata = None  # No more metadata stimuli after stop.
            if self.pending and not self.stop_reason:
                self.stop('unfinished operation at observer end')
        except BaseException as error:
            self.stop(repr(error))
        finally:
            if self.monitor:
                self.stop('observer ended with monitor completion unknown')
            complete = (not self.stop_reason and self.completed ==
                        ['metadata', 'monitor', 'guest_true', 'guest_hash'])
            self.final = dict(observation_complete=complete, accepted=False, cause_established=False,
                      stop_reason=self.stop_reason, completed_phases=self.completed,
                      pending=self.pending, remote_completion_unconfirmed=self.pending is not None,
                      sample_count=self.sample_count, maximum_gap_ns=self.max_gap_ns,
                      maximum_unobserved_gap_ns=self.max_unobserved_gap_ns, output_error=self.output_error,
                      observer_cpu_ns=self.clock.cpu() - self.cpu_start,
                      elapsed_ns=self.clock.now() - self.start,
                      limitations='Discrete scans can miss short-lived tasks. Names, phase association '
                      'and a negative result do not establish cause or performance qualification. '
                      'An already-issued guest request can be in flight when a stop is detected.')
            try:
                self.emit('final', **self.final)
            except ReceiptFailure:
                complete = False
                self.final.update(observation_complete=False, output_error=self.output_error,
                                  stop_reason=self.stop_reason)
        return complete


def main(expected):
    # This timer interrupts only this observer's Python work; it never signals a
    # QEMU task, SSH child or guest command. A kernel stall/transport loss can
    # still prevent delivery; the controller then retains unknown completion.
    def deadline(signum, frame):
        raise ObserverAbort('observer 60-second watchdog')
    def interrupted(signum, frame):
        raise ObserverAbort('observer interrupted: ' + str(signum))
    signal.signal(signal.SIGALRM, deadline)
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    signal.setitimer(signal.ITIMER_REAL, 60)
    wire = Wire()
    try:
        complete = Observer(expected, Proc(), Clock(), wire).run()
        wire.flush()
        return int(not complete or bool(wire.output))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
