"""Focused generic killable continuation controller; no performance scores.

Reuse the continuation session's frozen source, publication, daemon and drain.
Callable holders are released only after cancellation evidence is captured.
"""
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import struct
import subprocess
import sys
import time

import bench_runtime as rt

DEVICE = '/dev/kd_jit_continuation_test'
PARAMETERS = Path('/sys/module/kdlock_km/parameters')
RUN, SNAPSHOT, RELEASE, RESET = 0xC0204508, 0x83684509, 0x4008450A, 0x450B
HEADER = ('version', 'lock_address', 'inner_address', 'entry', 'active',
          'holder_mask', 'release_mask', 'phase', 'readers', 'queue_count',
          'inner_queue_count', 'errors', 'idle')
SLOT = ('pid', 'prefix', 'child_prefix', 'child_result', 'returned', 'result',
        'tail_ready', 'tail_done')


def signed(value):
    return value - (1 << 64) if value & (1 << 63) else value


def snapshot():
    buffer = bytearray(872)
    with open(DEVICE, 'rb', buffering=0) as device:
        fcntl.ioctl(device, SNAPSHOT, buffer, True)
    words = struct.unpack('=109Q', buffer)
    row = dict(zip(HEADER, words[:13]))
    row['phase'] = signed(row['phase'])
    for index, key in enumerate(('queue_pid', 'queue_state', 'inner_queue_pid', 'inner_queue_state')):
        row[key] = list(words[13 + index * 8:21 + index * 8])
    row['slots'] = []
    for index in range(8):
        item = dict(zip(SLOT, words[45 + index * 8:53 + index * 8]))
        for key in ('result', 'child_result'):
            item[key] = signed(item[key])
        row['slots'].append(item)
    rt.require(row['version'] == 1 and row['queue_count'] <= 8 and row['inner_queue_count'] <= 8,
               'killable observation ABI/queue bound differs', 'DATA_ERROR')
    return row


def control(command, value=None):
    with open(DEVICE, 'rb', buffering=0) as device:
        if value is None:
            fcntl.ioctl(device, command)
        else:
            fcntl.ioctl(device, command, struct.pack('=Q', value))


def worker(arguments, configure_worker):
    cpu, operation, slot, flags = map(int, arguments)
    configure_worker(cpu)
    buffer = bytearray(struct.pack('=4IqQ', operation, slot, flags, 0, 0, 0))
    with open(DEVICE, 'rb', buffering=0) as device:
        fcntl.ioctl(device, RUN, buffer, True)
    words = struct.unpack('=4IqQ', buffer)
    print(json.dumps(dict(operation=words[0], slot=words[1], flags=words[2],
                          reserved=words[3], result=words[4], returned=words[5])))


def trace_events(messages):
    pattern = re.compile(
        r'kd_service event=(\w+) origin=(\d+) executor=(\d+) identity=(?:0x)?([0-9a-fA-F]+) '
        r'generation=(\d+) object=(?:0x)?([0-9a-fA-F]+) depth=(\d+) entry=([0-9a-fA-F]+) may_delegate=([01])')
    rows = []
    for line in messages.splitlines():
        m = pattern.search(line)
        if m is None:
            continue
        row = dict(event=m[1], origin=int(m[2]), executor=int(m[3]), identity=int(m[4], 16),
                   generation=int(m[5]), object=int(m[6], 16), depth=int(m[7]), entry=int(m[8], 16),
                   may_delegate=bool(int(m[9])))
        family = re.search(r'\bfamily_generation=(\d+)', line)
        if family is not None:
            row['family_generation'] = int(family[1])
        for field in ('ip', 'sp', 'image_generation'):
            value = re.search(r'\b' + field + r'=([0-9a-fA-F]+)', line)
            if value is not None:
                row[field] = int(value[1], 10 if field == 'image_generation' else 16)
        rows.append(row)
    return rows


def session_class(base):
    class KillableSession(base):
        def counts(self, label):
            state = snapshot()
            rt.write_json(self.path / (label + '.killable.json'), state)
            rt.require(state['errors'] == 0, 'killable payload reported an error', 'DATA_ERROR')
            rt.require(state['active'] == 0 and state['idle'] == 1,
                       'killable callers or lock state remain active', 'UNDRAINED')
            entered = sum(row['prefix'] for row in state['slots'])
            returned = sum(row['prefix'] for row in state['slots'] if row['returned'])
            return dict(prefix=entered, suffix=returned, hot_taken=0, hot=0,
                        lock_address=state['lock_address'], entry=state['entry'],
                        marker=state['entry'], active=state['active'], idle=state['idle'], failures=0)

        def observe(self, label, predicate, timeout=10):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                self.faults()
                state = snapshot()
                rt.require(not state['errors'], 'killable payload reported an error', 'DATA_ERROR')
                if predicate(state):
                    rt.write_json(self.path / (label + '.json'), state)
                    return state
                time.sleep(.005)
            rt.write_json(self.path / (label + '.timeout.json'), state)
            raise rt.Failure('UNDRAINED', 'killable control predicate expired: ' + label, unsafe=True)

        def start(self, label, operation, slot, flags=0, *, cpu=None):
            log = (self.path / (label + '.worker.json')).open('w')
            cpu = self.record['cpus'][slot % len(self.record['cpus'])] if cpu is None else cpu
            rt.require(type(cpu) is int and 0 <= cpu < os.cpu_count(), 'explicit fixture CPU is unavailable')
            argv = [sys.executable, self.translation_source / 'tests/kernel/jit_continuation/run.py',
                    '--killable-worker', str(cpu), str(operation), str(slot), str(flags)]
            process = subprocess.Popen(list(map(str, argv)), stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            item = dict(label=label, pid=process.pid, operation=operation, slot=slot, flags=flags,
                        cpu=cpu, argv=list(map(str, argv)), joined=False)
            self.record.setdefault('callers', []).append(item)
            self.clients.append((process, log, item))
            self.save()
            return process, log, item

        def join(self, client, killed=False):
            process, log, item = client
            try:
                status = process.wait(timeout=10)
            except subprocess.TimeoutExpired as error:
                raise rt.Failure('UNDRAINED', 'killable caller did not exit', unsafe=True) from error
            log.close()
            item.update(joined=True, returncode=status, expected_signal=signal.SIGKILL if killed else None)
            self.save()
            rt.require(status == (-signal.SIGKILL if killed else 0),
                       'killable caller exit differs: ' + str(item), 'DATA_ERROR')

        def phase_begin(self, name):
            self.verify()
            self.faults()
            self.observe(name + '-idle-before', lambda row: row['idle'] == 1)
            control(RESET)
            self.trace_start = len(self.messages)
            result = dict(name=name, complete=False)
            self.record.setdefault('phases', []).append(result)
            self.save()
            return result

        def phase_end(self, result, successful=(), canceled=(), nested=None, downgraded=None, policy=None):
            final = self.observe(result['name'] + '-idle-after', lambda row: row['idle'] == 1)
            self.faults()
            events = trace_events(self.messages[self.trace_start:])
            layout = self.record['layout']
            roots = {}
            for pid in successful:
                entered = [row for row in events if row['event'] == 'enter' and row['origin'] == pid]
                returned = [row for row in events if row['event'] == 'returned' and row['origin'] == pid]
                rt.require(len(entered) == len(returned) == 1,
                           'exact root enter/returned pair missing', 'NO_JIT')
                start, end = entered[0], returned[0]
                rt.require(start['identity'] and start['generation'] and start['executor'] != pid and
                           all(start[key] == end[key] for key in ('origin', 'executor', 'identity', 'generation', 'object', 'entry')) and
                           start['object'] == layout['lock_address'] and start['entry'] == layout['entry'],
                           'root actual executor or exact request pair differs', 'DATA_ERROR')
                bodies = [row for row in final['slots'] if row['pid'] == pid]
                rt.require(len(bodies) == 1 and bodies[0]['prefix'] == 1 and bodies[0]['returned'] == 1 and
                           bodies[0]['result'] == 0, 'root body effect/return differs', 'DATA_ERROR')
                roots[pid] = start
            for pid in canceled:
                rows = [row for row in events if row['event'] == 'cancel' and row['origin'] == pid]
                rt.require(len(rows) == 1 and rows[0]['identity'] and rows[0]['generation'] and
                           rows[0]['object'] == layout['lock_address'] and
                           not any(row['event'] == 'enter' and row['origin'] == pid for row in events),
                           'canceled root has missing cancellation or entered body', 'DATA_ERROR')
                bodies = [row for row in final['slots'] if row['pid'] == pid]
                rt.require(len(bodies) == 1 and bodies[0]['prefix'] == bodies[0]['child_prefix'] == 0 and
                           bodies[0]['returned'] == 1 and bodies[0]['result'] == -4,
                           'canceled root ran a prefix or lost its API return', 'DATA_ERROR')
            if nested is not None:
                rows = [row for row in events if row['event'] == 'child_cancel' and row['origin'] == nested]
                root = roots[nested]
                rt.require(len(rows) == 1 and rows[0]['executor'] == root['executor'] and
                           rows[0]['identity'] and rows[0]['generation'] and
                           (rows[0]['identity'], rows[0]['generation']) != (root['identity'], root['generation']) and
                           rows[0]['depth'] == root['depth'] + 1 and
                           not rows[0]['may_delegate'] and
                           rows[0]['object'] == self.initial['inner_address'],
                           'nested logical-origin cancellation or parent/executor identity differs', 'DATA_ERROR')
            if downgraded is not None:
                root = roots[downgraded]
                for event in ('downgrade', 'read_release'):
                    rows = [row for row in events if row['event'] == event and row['origin'] == downgraded]
                    rt.require(len(rows) == 1 and all(rows[0][key] == root[key] for key in
                               ('origin', 'executor', 'identity', 'generation', 'object', 'entry')),
                               'downgraded tail actual executor/request proof differs', 'DATA_ERROR')
            if policy is not None:
                pid, kind = policy
                root = roots[pid]
                grants = [row for row in events if row['event'] == 'child_grant' and row['origin'] == pid]
                count = 8 if kind in ('depth9', 'early') else 128 if kind == 'reuse' else 1
                rt.require(len(grants) == count and len({(row['identity'], row['generation']) for row in grants}) == count,
                           'child grants missing or exact invocation identity reused', 'DATA_ERROR')
                rt.require(all(row['identity'] and row['generation'] and row['executor'] == root['executor'] and
                               row['entry'] == root['entry'] for row in grants),
                           'child actual executor/request identity differs', 'DATA_ERROR')
                if kind in ('depth9', 'early'):
                    rt.require([row['depth'] for row in grants] == list(range(root['depth'] + 1, root['depth'] + 9)) and
                               len({row['object'] for row in grants}) == 8 and
                               all(not row['may_delegate'] for row in grants),
                               'mixed distinct-object depth9 grant chain differs', 'DATA_ERROR')
                else:
                    expected = [bool(i & 1) for i in range(128)] if kind == 'reuse' else [True]
                    rt.require([row['may_delegate'] for row in grants] == expected and
                               all(row['depth'] == root['depth'] + 1 for row in grants) and
                               len({row['object'] for row in grants}) == 1,
                               'repeated true/false child entry policy or depth differs', 'DATA_ERROR')
                released = []
                for row in grants:
                    matches = [event for event in events if event['event'] == 'release' and all(
                        event[key] == row[key] for key in ('origin', 'executor', 'identity', 'generation', 'object', 'depth'))]
                    rt.require(len(matches) == 1, 'child physical release/record completion differs', 'DATA_ERROR')
                    released.append(matches[0])
                outer = [row for row in events if row['event'] == 'release' and
                         (row['identity'], row['generation']) == (root['identity'], root['generation'])]
                rt.require(len(outer) == 1, 'outer exact release missing', 'DATA_ERROR')
                if kind in ('depth9', 'early'):
                    ordered_releases = sorted(released, key=events.index)
                    rt.require([row['depth'] - root['depth'] for row in ordered_releases] == [1, 3, 5, 7, 2, 4, 6, 8],
                               'out-of-order child release sequence differs', 'DATA_ERROR')
                    if kind == 'early':
                        rt.require(max(map(events.index, grants)) < events.index(outer[0]) < min(map(events.index, released)),
                                   'outer did not release while all eight children remained held', 'DATA_ERROR')
                    else:
                        rt.require(max(map(events.index, released)) < events.index(outer[0]),
                                   'ordinary deep outer release preceded child completion', 'DATA_ERROR')
                elif kind == 'reuse':
                    rt.require(all(events.index(released[i]) < events.index(grants[i + 1]) for i in range(count - 1)),
                               'child reuse began before exact prior release', 'DATA_ERROR')
                body = next(row for row in final['slots'] if row['pid'] == pid)
                rt.require(body['child_prefix'] == count and body['child_result'] == 0,
                           'child bodies did not finish exactly once', 'DATA_ERROR')
            rt.require(self.registry(result['name'] + '-after', 0) == self.record['image_registry'] and
                       self.publication() == self.record['publication'],
                       'killable phase changed the immutable root image or left frames active', 'UNDRAINED')
            result.update(complete=True, final=final, service_events=events,
                          execution='EXACT_OTHER_TASK_ENTER_AND_RETURN' if successful else 'CANCELED_BEFORE_BODY')
            self.save()

        def measure(self):
            self.clients = []
            self.initial = snapshot()
            self.record['execution_status'] = 'MEASURING'
            trace = PARAMETERS / 'service_trace'
            rt.require(trace.is_file(), 'generic service trace unavailable', 'ENVIRONMENT')
            trace.write_text('1\n')
            rt.require(trace.read_text().strip() == 'Y', 'service trace readback differs')
            self.record['service_trace_during_checks'] = True
            self.save()
            result = self.phase_begin('killable-success')
            client = self.start('success-root', 0, 0)
            self.observe('success-returned', lambda row: row['slots'][0]['returned'] and
                         row['slots'][0]['prefix'] == 1 and row['slots'][0]['result'] == 0)
            self.join(client)
            self.phase_end(result, successful=[client[2]['pid']])
            for position in range(3):
                result = self.phase_begin(f'queued-cancel-{position}')
                holder = self.start(f'holder-{position}', 1, 0)
                self.observe(f'holder-{position}-acquired', lambda row: row['holder_mask'] == 1)
                clients = []
                for index in range(3):
                    clients.append(self.start(f'queued-{position}-{index}', 0, index + 1))
                    pids = [item[2]['pid'] for item in clients]
                    self.observe(f'queued-{position}-{index}-published',
                        lambda row, pids=pids: row['queue_pid'][:row['queue_count']] == pids)
                victim = clients[position]
                remaining = [item for index, item in enumerate(clients) if index != position]
                os.kill(victim[2]['pid'], signal.SIGKILL)
                state = self.observe(f'queued-{position}-cancel-before-release',
                    lambda row: row['slots'][position + 1]['returned'] == 1 and
                    row['queue_pid'][:row['queue_count']] == [item[2]['pid'] for item in remaining])
                rt.require(state['holder_mask'] == 1 and state['release_mask'] == 0 and
                           state['slots'][position + 1]['result'] == -4 and
                           all(row['prefix'] == 0 for row in state['slots']) and
                           state['queue_pid'][:state['queue_count']] == [item[2]['pid'] for item in remaining],
                           'queued cancellation did not unlink/return while holder remained acquired', 'DATA_ERROR')
                self.join(victim, killed=True)
                control(RELEASE, 1)
                self.join(holder)
                for item in remaining:
                    self.join(item)
                self.phase_end(result, successful=[item[2]['pid'] for item in remaining],
                               canceled=[victim[2]['pid']])
            result = self.phase_begin('selected-reader-drain-cancel')
            holder = self.start('reader-holder', 2, 0)
            self.observe('reader-holder-acquired', lambda row: row['holder_mask'] == 2 and row['readers'] == 1)
            client = self.start('draining-root', 0, 1)
            self.observe('reader-drain-selected', lambda row: row['phase'] == -1 and row['readers'] == 1 and
                         row['queue_pid'][:row['queue_count']] == [client[2]['pid']] and row['queue_state'][0] == 2)
            os.kill(client[2]['pid'], signal.SIGKILL)
            state = self.observe('reader-drain-cancel-before-release', lambda row:
                                 row['slots'][1]['returned'] == 1 and row['phase'] == 0 and row['queue_count'] == 0)
            rt.require(state['holder_mask'] == 2 and state['release_mask'] == 0 and state['readers'] == 1 and
                       state['phase'] == 0 and state['queue_count'] == 0 and
                       state['slots'][1]['result'] == -4 and state['slots'][1]['prefix'] == 0,
                       'selected cancellation lost reader/phase/ACK semantics', 'DATA_ERROR')
            self.join(client, killed=True)
            control(RELEASE, 2)
            self.join(holder)
            self.phase_end(result, canceled=[client[2]['pid']])
            result = self.phase_begin('nested-origin-cancel')
            holder = self.start('inner-holder', 3, 0)
            self.observe('inner-holder-acquired', lambda row: row['holder_mask'] == 4)
            client = self.start('nested-root', 0, 1, 1)
            self.observe('nested-child-published', lambda row: row['slots'][1]['prefix'] == 1 and
                         row['inner_queue_pid'][:row['inner_queue_count']] == [client[2]['pid']])
            os.kill(client[2]['pid'], signal.SIGKILL)
            state = self.observe('nested-return-before-inner-release', lambda row:
                                 row['slots'][1]['returned'] == 1 and row['phase'] == 0 and row['inner_queue_count'] == 0)
            row = state['slots'][1]
            rt.require(state['holder_mask'] == 4 and state['release_mask'] == 0 and
                       row['prefix'] == 1 and row['child_prefix'] == 0 and row['child_result'] == -4 and
                       row['result'] == 0 and state['phase'] == 0 and state['inner_queue_count'] == 0,
                       'nested cancellation lost parent effects or waited for inner holder release', 'DATA_ERROR')
            self.join(client, killed=True)
            control(RELEASE, 4)
            self.join(holder)
            self.phase_end(result, successful=[client[2]['pid']], nested=client[2]['pid'])
            result = self.phase_begin('executor-downgrade-and-fresh-writer')
            tail = self.start('downgraded-root', 0, 0, 2)
            self.observe('executor-read-tail-live', lambda row: row['slots'][0]['tail_ready'] == 1 and
                         row['slots'][0]['tail_done'] == 0 and row['readers'] == 1 and row['phase'] == 0)
            next_writer = self.start('fresh-writer-after-downgrade', 0, 1)
            state = self.observe('fresh-writer-draining-tail', lambda row: row['phase'] == -1 and row['readers'] == 1 and
                                 row['queue_pid'][:row['queue_count']] == [next_writer[2]['pid']])
            rt.require(not state['slots'][0]['returned'] and state['slots'][0]['tail_done'] == 0 and
                       not state['slots'][1]['prefix'],
                       'fresh writer bypassed executor read tail', 'DATA_ERROR')
            control(RELEASE, 8)
            self.join(tail)
            self.join(next_writer)
            final = self.observe('downgraded-tail-completed', lambda row: row['idle'] == 1)
            rt.require(final['slots'][0]['tail_done'] == 0x1234 and
                       all(final['slots'][i]['prefix'] == 1 and final['slots'][i]['result'] == 0 for i in (0, 1)),
                       'executor read tail or following writer did not complete exactly', 'DATA_ERROR')
            self.phase_end(result, successful=[tail[2]['pid'], next_writer[2]['pid']], downgraded=tail[2]['pid'])
            for name, flags, kind in (('mixed-depth9', 4, 'depth9'),
                                      ('early-outer-depth9', 12, 'early'),
                                      ('repeated-child-128', 16, 'reuse'),
                                      ('nested-true-control', 32, 'true')):
                result = self.phase_begin(name)
                client = self.start(name + '-root', 0, 0, flags)
                self.observe(name + '-returned', lambda row: row['slots'][0]['returned'] == 1)
                self.join(client)
                self.phase_end(result, successful=[client[2]['pid']], policy=(client[2]['pid'], kind))
            trace.write_text('0\n')
            rt.require(trace.read_text().strip() == 'N', 'service trace final readback differs')
            rt.require(all(item['joined'] for _, _, item in self.clients), 'unjoined killable caller', 'UNDRAINED')
            self.record.update(accepted=True, jit_status='KILLABLE_PROXY_AND_EXACT_CANCELLATION',
                               escape_events=[], origin_service=False, service_trace_final=False)
            self.save()
    return KillableSession
