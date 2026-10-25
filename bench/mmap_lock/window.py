#!/usr/bin/env python3
"""Prepared mmap window: bounded control and replay, with no implicit drain."""
import hashlib
import json
import os
import re
from pathlib import Path
import selectors
import select
import socket
import subprocess
import time

POLICY = 'mmap-window-v2'
LEGACY = 'mmap-transport-v1'
ABI = 'MW1'
MAX_OUTPUT = 1024 * 1024
MAX_ERROR = 64 * 1024
MAX_FRAME = 4096
PERIOD_NS = 500_000_000
MAX_GAP_NS = 1_000_000_000
GUARD_NS = 2_000_000_000
GUARD_SCANS = 5
GUARD_TIMEOUT_NS = 10_000_000_000
WINDOW_TIMEOUT_NS = 30_000_000_000
COUNTERS = ('runtime_ns', 'runqueue_wait_ns', 'timeslices')
IO_KEYS = ('rchar', 'wchar', 'syscr', 'syscw', 'read_bytes', 'write_bytes',
           'cancelled_write_bytes')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def policy(row):
    value = row.get('measurement_policy', LEGACY)
    require(value in (LEGACY, POLICY), 'unknown measurement policy')
    return value


def binding():
    return dict(measurement_policy=POLICY, control_abi=ABI,
                window_sha256=globals().get('_STREAM_SHA256') or
                hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


class Protocol:
    """Strict, single-use ordering shared by live transport and offline replay."""
    ORDER = ('prepared', 'go', 'started', 'finished', 'endpoint', 'export', 'exited')

    def __init__(self, nonce):
        require(isinstance(nonce, str) and len(nonce) == 32 and
                all(c in '0123456789abcdef' for c in nonce), 'invalid case nonce')
        self.nonce, self.events = nonce, []

    def add(self, event, **fields):
        require(len(self.events) < len(self.ORDER) and event == self.ORDER[len(self.events)],
                'duplicate or out-of-order control: ' + event)
        row = dict(event=event, nonce=self.nonce, **fields)
        self.events.append(row)
        return row

    def receive(self, row, expected):
        require(row.get('nonce') == self.nonce and row.get('event') == expected and
                row.get('measurement_policy') == POLICY and row.get('control_abi') == ABI,
                'control identity/type differs')
        return self.add(expected, **{k: row[k] for k in ('endpoint_sha256', 'completion_token') if k in row})


def frame(event, nonce, **fields):
    data = (json.dumps(dict(event=event, nonce=nonce, **binding(), **fields),
                       separators=(',', ':')) + '\n').encode()
    require(len(data) <= MAX_FRAME, 'control frame exceeds bound')
    return data


def control_replay(record):
    require(all(record.get(k) == v for k, v in binding().items()), 'control source/policy differs')
    p = Protocol(record['nonce'])
    for row in record['events']:
        require(row.get('nonce') == p.nonce, 'control nonce changed')
        p.add(row['event'])
    require(len(p.events) == len(p.ORDER) and record['returncode'] == 0 and
            record['completion_confirmed'] and record['publication_after_endpoint'] and 'error' not in record,
            'incomplete control/publication evidence')
    events = {r['event']: r for r in record['events']}
    token, digest = record['completion_token'], record['endpoint_sha256']
    require(re.fullmatch('[0-9a-f]{16}', token) and re.fullmatch('[0-9a-f]{64}', digest) and
            events['finished']['completion_token'] == events['export']['completion_token'] == token and
            events['endpoint']['endpoint_sha256'] == events['export']['endpoint_sha256'] == digest,
            'completion token or endpoint event binding differs')
    return True


def write_all(fd, data, deadline):
    """Absolute deadline, including partial writes, EINTR and backpressure."""
    os.set_blocking(fd, False)
    done = 0
    while done < len(data):
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError('control write deadline')
        try:
            _, ready, _ = select.select([], [fd], [], left)
            if not ready or time.monotonic() >= deadline:
                raise TimeoutError('control write deadline')
            n = os.write(fd, data[done:])
            require(n > 0, 'closed control output')
            done += n
        except (BlockingIOError, InterruptedError):
            continue
    require(time.monotonic() < deadline, 'control write completed after deadline')


def require_unpublished(data):
    # The sole allowed pre-export stdout is one complete ready line. A partial
    # second line is already publication, even without its terminating newline.
    require(data.count(b'\n') == 1 and data.endswith(b'\n') and
            json.loads(data)['event'] == 'ready', 'measurement published before endpoint/export')


def read_frame(fd, limit, deadline):
    os.set_blocking(fd, False)
    data = bytearray()
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError('control read deadline')
        try:
            ready, _, _ = select.select([fd], [], [], left)
            if not ready or time.monotonic() >= deadline:
                raise TimeoutError('control read deadline')
            block = os.read(fd, min(65536, limit + 1 - len(data)))
            require(block, 'control input closed before complete frame')
            data.extend(block)
            require(len(data) <= limit, 'control input exceeds bound')
            if b'\n' in data:
                require(data.count(b'\n') == 1 and data.endswith(b'\n'), 'pipelined control input')
                return json.loads(data)
        except (BlockingIOError, InterruptedError):
            continue


def bridge(argv, nonce, command_input, event_output, *, popen=subprocess.Popen):
    """Guest-only bridge. Retain client output in RAM until explicit EXPORT.

    The caller writes receipts only after this returns. Failure returns partial
    bytes and an explicit completion flag; it cannot authorize module unload.
    No subprocess.run timeout or context manager can kill the client here.
    """
    p = Protocol(nonce)
    record = dict(**binding(), nonce=nonce, events=p.events, returncode=None,
                  completion_confirmed=False, publication_after_endpoint=False)
    buffers = {name: bytearray() for name in ('stdout', 'stderr', 'control', 'input')}
    parent, child_socket = socket.socketpair()
    parent.settimeout(1)
    child = None
    start = time.monotonic()
    prepared_seen = False
    stage_deadline = start + 30
    try:
        child = popen([*argv, '--control-fd', str(child_socket.fileno())],
                      pass_fds=(child_socket.fileno(),), stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE, start_new_session=True)
        record['client_pid'] = child.pid
        child_socket.close()
        os.set_blocking(child.stdout.fileno(), False)
        with selectors.DefaultSelector() as selector:
            for stream, name in ((child.stdout, 'stdout'), (child.stderr, 'stderr'),
                                 (parent, 'control'), (command_input, 'input')):
                selector.register(stream, selectors.EVENT_READ, name)
            while True:
                remaining = stage_deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('control phase deadline; completion not implied')
                for key, _ in selector.select(min(remaining, 0.1)):
                    try:
                        block = os.read(key.fd, 65536)
                    except BlockingIOError:
                        continue
                    name = key.data
                    if not block:
                        selector.unregister(key.fileobj)
                        if name == 'input' and len(p.events) < 6:
                            raise EOFError('controller disappeared before export')
                        continue
                    buffers[name].extend(block)
                    cap = MAX_OUTPUT if name == 'stdout' else MAX_ERROR if name == 'stderr' else MAX_FRAME
                    require(len(buffers[name]) <= cap, name + ' exceeds bounded memory')
                    if name == 'control':
                        while b'\n' in buffers[name]:
                            raw, _, rest = buffers[name].partition(b'\n')
                            buffers[name] = bytearray(rest)
                            message = raw.decode()
                            if message == 'MW1 PREPARED':
                                require(not prepared_seen, 'duplicate PREPARED')
                                prepared_seen = True
                            elif message == 'MW1 STARTED' or message.startswith('MW1 FINISHED '):
                                event = message.split()[1].lower()
                                extra = {}
                                if event == 'finished':
                                    token = message.split()[2]
                                    require(re.fullmatch('[0-9a-f]{16}', token), 'invalid completion token')
                                    extra['completion_token'] = token
                                    record['completion_token'] = token
                                p.add(event, **extra)
                                write_all(event_output.fileno(), frame(event, nonce, **extra), stage_deadline)
                                stage_deadline = time.monotonic() + 30
                            else:
                                raise ValueError('client aborted or invalid control: ' + message)
                    elif name == 'input':
                        while b'\n' in buffers[name]:
                            raw, _, rest = buffers[name].partition(b'\n')
                            buffers[name] = bytearray(rest)
                            command = json.loads(raw)
                            event = command.get('event')
                            if event == 'export':
                                # stdout and the controller command can be ready
                                # in either selector order. Drain/check stdout
                                # before forwarding EXPORT; ambiguous bytes fail.
                                while True:
                                    try:
                                        pending = os.read(child.stdout.fileno(), 65536)
                                    except BlockingIOError:
                                        break
                                    if not pending:
                                        break
                                    buffers['stdout'].extend(pending)
                                    require(len(buffers['stdout']) <= MAX_OUTPUT, 'stdout exceeds bounded memory')
                                require_unpublished(bytes(buffers['stdout']))
                                # The source controller supplies the bound endpoint
                                # before releasing publication on this same channel.
                                require(isinstance(command.get('endpoint_sha256'), str) and
                                        len(command['endpoint_sha256']) == 64, 'missing endpoint binding')
                                p.add('endpoint', endpoint_sha256=command['endpoint_sha256'])
                                record['endpoint_sha256'] = command['endpoint_sha256']
                                require(command.get('completion_token') == record.get('completion_token') and
                                        'completion_token' in record, 'completion token differs')
                                p.receive(command, 'export')
                                record['publication_after_endpoint'] = True
                                write_all(parent.fileno(), ('MW1 EXPORT ' + record['completion_token'] + '\n').encode(), stage_deadline)
                            else:
                                p.receive(command, 'go')
                                write_all(parent.fileno(), b'MW1 GO\n', stage_deadline)
                            stage_deadline = time.monotonic() + 30
                if prepared_seen and not p.events and b'\n' in buffers['stdout']:
                    ready = json.loads(bytes(buffers['stdout']).splitlines()[0])
                    require(ready['event'] == 'ready' and len(buffers['stdout'].splitlines()) == 1,
                            'output before prepared hold')
                    p.add('prepared')
                    write_all(event_output.fileno(), frame('prepared', nonce), stage_deadline)
                if len(p.events) < 6:
                    if b'\n' in buffers['stdout']:
                        require_unpublished(bytes(buffers['stdout']))
                code = child.poll()
                # EOF must be consumed as well as waitpid: pipe bytes can remain.
                streams = {key.data for key in selector.get_map().values()}
                if code is not None and not streams.intersection(('stdout', 'stderr', 'control')):
                    record.update(returncode=code, completion_confirmed=True)
                    require(code == 0 and not buffers['stderr'], 'client failed')
                    p.add('exited')
                    control_replay(record)
                    break
    except BaseException as error:
        record['error'] = repr(error)
        # Closing only our socket cooperatively cancels a not-yet-started client;
        # after GO the client runs to its own deadline and joins. Never signal it.
        parent.close()
        if child is not None:
            code = child.poll()
            record.update(returncode=code, completion_confirmed=code is not None)
    finally:
        parent.close(); child_socket.close()
    record['elapsed_seconds'] = time.monotonic() - start
    return record, bytes(buffers['stdout']), bytes(buffers['stderr'])


def task_key(task):
    return task['tid'], task['start_ticks']


def core_inventory(original, current):
    """Original 67 roles stay exact; additional roles are checked separately."""
    old = original['qemu'][0]['tasks']
    require(len(old) == 67, 'original core inventory differs')
    tasks = {t['tid']: t for t in current['qemu'][0]['tasks']}
    core = []
    for prior in old:
        task = tasks[prior['tid']]
        require(all(task[k] == prior[k] for k in ('tid', 'comm', 'affinity')),
                'original core task or placement changed')
        require(type(task['start_ticks']) is int and task['start_ticks'] > 0, 'missing core lifetime')
        core.append(task)
    return core


def same_environment(original_host, host, original_env, env, original_topology, topology):
    """Mmap-specific comparison; never pretend the legacy all-task check passed."""
    for key in ('cpufreq', 'numa', 'recovery_snapshot'):
        require(host[key] == original_host[key], 'host configuration differs: ' + key)
    require(len(original_host['qemu']) == len(host['qemu']) == 1, 'same single QEMU required')
    old, new = original_host['qemu'][0], host['qemu'][0]
    for key in ('pid', 'args'):
        require(old[key] == new[key], 'QEMU configuration differs: ' + key)
    core = core_inventory(original_host, host)

    def memory(qemu):
        rows = []
        for line in qemu['numa_maps'].splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[1].startswith('bind:'):
                values = dict(f.split('=', 1) for f in fields[2:] if '=' in f)
                rows.append(dict(address=fields[0], policy=fields[1], page_kb=int(values['kernelpagesize_kB']),
                                 resident_pages={k: int(v) for k, v in values.items() if re.fullmatch(r'N[0-9]+', k)}))
        require(rows, 'missing host memory bindings')
        return rows
    before, after = memory(old), memory(new)
    configuration = lambda rows: [(r['address'], r['policy'], r['page_kb']) for r in rows]
    require(configuration(before) == configuration(after), 'host memory binding differs')
    for key in ('boot_id', 'cmdline', 'preemption', 'packages', 'python', 'snapshot_tag', 'collector_topology'):
        require(original_env[key] == env[key], 'guest environment differs: ' + key)
    require(original_topology == topology, 'guest topology differs')
    return dict(configuration_matches=True, measurement_policy=POLICY, core=core,
                original_memory=before, replay_memory=after,
                scope='Exact original core roles/configuration; auxiliary identities and activity need window replay.')


def counters(task):
    require(task['complete'], 'partial task observation')
    values = {k: task[k] for k in COUNTERS}
    values.update({k: task['io'][k] for k in IO_KEYS})
    require(all(type(v) is int and v >= 0 for v in values.values()), 'invalid/missing task counter')
    return values


def resolve_roles(tasks, core, definitions):
    """Resolve reviewed role selectors once, after setup and before the guard."""
    keys = {task_key(t) for t in core}
    result = []
    for task in tasks:
        if task_key(task) in keys:
            continue
        matches = [r for r in definitions if r['comm'] == task['comm'] and
                   r['affinity'] == task['affinity'] == [63]]
        require(len(matches) == 1, 'unclassified or ambiguously classified auxiliary')
        result.append(dict(matches[0], tid=task['tid'], start_ticks=task['start_ticks']))
    return result


def check_samples(samples, core, roles, *, complete=True):
    """Validate one frozen inventory; no quiet-interval restart or count budget.

    core: original vCPU/service identities and affinities. roles: explicit extra
    identity -> classification/evidence. Expected service activity is recorded,
    not subjected to the inactive-auxiliary zero-delta rule.
    """
    require(samples, 'missing window observations')
    expected = {task_key(t): t for t in core}
    require(len(expected) == 67 and len(core) == 67, 'exact original core inventory required')
    classified = {}
    for r in roles:
        key = task_key(r)
        require(key not in expected and key not in classified and r['affinity'] == [63] and
                r['class'] in ('inactive_auxiliary', 'expected_service') and
                isinstance(r.get('evidence'), str) and len(r['evidence']) == 64 and
                isinstance(r.get('reason'), str) and r['reason'].strip(), 'unclassified auxiliary')
        classified[key] = r
    expected.update(classified)
    baseline, previous, first = None, None, samples[0]
    deltas = []
    for sample in samples:
        require(sample['complete'] and not sample['errors'] and sample['equal_observed_tid_lists'] and
                sample['identity_before'] == sample['identity_after'] == first['identity_before'],
                'incomplete observation or QEMU identity drift')
        require(type(sample['begin_ns']) is int and type(sample['end_ns']) is int and
                0 <= sample['begin_ns'] <= sample['end_ns'] and
                sample['end_ns'] - sample['begin_ns'] <= MAX_GAP_NS, 'invalid or slow observation')
        if previous:
            require(previous['end_ns'] <= sample['begin_ns'] and
                    sample['begin_ns'] - previous['begin_ns'] <= MAX_GAP_NS,
                    'observation gap or order differs')
        tasks = {task_key(t): t for t in sample['tasks']}
        require(len(tasks) == len(sample['tasks']) and tasks.keys() == expected.keys() and
                sample['initial_tids'] == sample['final_tids'] == sorted(t['tid'] for t in tasks.values()),
                'task addition/removal/replacement')
        current = {}
        for key, task in tasks.items():
            require(task['affinity'] == expected[key]['affinity'] and task['comm'] == expected[key]['comm'],
                    'task placement/comm drift')
            current[key] = counters(task)
            if baseline is not None:
                delta = {k: current[key][k] - baseline[key][k] for k in current[key]}
                require(all(current[key][k] >= prior_counts[key][k] for k in current[key]),
                        'counter regression')
                if key in classified and classified[key]['class'] == 'inactive_auxiliary':
                    require(task['state'] == 'S' and not any(delta.values()),
                            'inactive auxiliary ran, queued or performed I/O')
                deltas.append(dict(tid=key[0], start_ticks=key[1], **delta))
            if key in classified and classified[key]['class'] == 'inactive_auxiliary':
                require(task['state'] == 'S', 'inactive auxiliary not sleeping')
        if baseline is None:
            baseline = current
        prior_counts, previous = current, sample
    if complete:
        require(len(samples) >= GUARD_SCANS and samples[-1]['end_ns'] - first['begin_ns'] >= GUARD_NS,
                'incomplete guard coverage')
    return deltas
