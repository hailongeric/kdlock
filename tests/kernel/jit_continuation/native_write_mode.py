"""Exact Native rwsem writer ownership, sleeping acquisition and final return."""
import fcntl
from pathlib import Path
import struct
import time

import bench_runtime as rt
from killable_mode import DEVICE, RELEASE, control, snapshot, trace_events
from helper_mode import native_events, primitive_events, validate_transaction

SNAPSHOT = 0x83B84510
HEADER = ('version', 'errors', 'count', 'body_after', 'lock_a', 'lock_b', 'stack_low', 'stack_high',
          'attempts', 'grants', 'holder_active', 'native_waiters', 'progress', 'progress_pid', 'progress_cpu')
FIELDS = ('operation', 'object', 'pid', 'cpu', 'stack_address', 'preempt_before', 'preempt_after',
          'rcu_before', 'rcu_after', 'irqs_before', 'irqs_after', 'switches_before', 'switches_after')


def decode_snapshot(data):
    rt.require(len(data) == 952, 'Native writer observation length differs', 'DATA_ERROR')
    words = struct.unpack('=119Q', data)
    state = dict(zip(HEADER, words[:15]))
    rt.require(state['version'] == 1 and state['count'] <= 8, 'Native writer observation ABI differs', 'DATA_ERROR')
    state['events'] = [dict(zip(FIELDS, words[15 + i * 13:28 + i * 13])) for i in range(state['count'])]
    rt.require(not any(words[15 + state['count'] * 13:]), 'unused Native writer observation is nonzero', 'DATA_ERROR')
    return state


def native_write_snapshot():
    packet = bytearray(952)
    with open(DEVICE, 'rb', buffering=0) as device:
        fcntl.ioctl(device, SNAPSHOT, packet, True)
    return decode_snapshot(packet)


def process_observation(pid):
    base = Path('/proc') / str(pid)
    words = (base / 'stat').read_text().rsplit(')', 1)[1].split()
    values = dict(line.split(':', 1) for line in (base / 'status').read_text().splitlines() if ':' in line)
    return dict(pid=pid, start_ticks=int(words[19]), state=words[0], cpu=int(words[36]),
                switches=sum(int(values[name]) for name in ('voluntary_ctxt_switches', 'nonvoluntary_ctxt_switches')))


def observe(session, label, predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        session.faults()
        state, native = snapshot(), native_write_snapshot()
        rt.require(state['errors'] == native['errors'] == 0, 'Native writer fixture error', 'DATA_ERROR')
        if predicate(state, native):
            value = dict(state=state, native=native)
            rt.write_json(session.path / (label + '.json'), value)
            return value
        time.sleep(.005)
    rt.write_json(session.path / (label + '.timeout.json'), dict(state=state, native=native))
    raise rt.Failure('UNDRAINED', 'Native writer observation expired: ' + label, unsafe=True)


def wait_root_enter(session, label, pid, expected_object, expected_entry, timeout=10):
    """A blocked snapshot does not advance this session's log reader."""
    deadline = time.monotonic() + timeout
    roots, reads = [], 0
    while time.monotonic() < deadline:
        session.faults()
        reads += 1
        roots = [event for event in trace_events(session.messages[session.trace_start:])
                 if event['event'] == 'enter' and event['origin'] == pid and event['depth'] == 0]
        if roots:
            valid = (len(roots) == 1 and roots[0]['executor'] > 0 and roots[0]['executor'] != pid and
                roots[0]['object'] == expected_object and roots[0]['entry'] == expected_entry and
                roots[0]['identity'] > 0 and roots[0]['generation'] > 0 and roots[0]['may_delegate'])
            rt.write_json(session.path / (label + '.json'), dict(roots=roots, capture_reads=reads))
            if not valid:
                raise rt.Failure('UNDRAINED', 'blocked writer root identity differs or is duplicated', unsafe=True)
            return roots[0]
        time.sleep(.005)
    rt.write_json(session.path / (label + '.timeout.json'), dict(roots=roots, capture_reads=reads))
    raise rt.Failure('UNDRAINED', 'blocked writer root-enter record not collected before deadline', unsafe=True)


def plan(state, early=False):
    return [(1, state['lock_a'], 'grant', 1), (2, state['lock_a'], 'release', 1)] if early else [
        (1, state['lock_a'], 'grant', 1), (1, state['lock_b'], 'grant', 2),
        (2, state['lock_a'], 'release', 1), (2, state['lock_b'], 'release', 2)]


def validate(messages, root, pid, cpu, descriptors, image_generation, state, early=False):
    expected = plan(state, early)
    acquisitions = 1 if early else 2
    rt.require(state['errors'] == 0 and state['count'] == len(expected) and len(state['events']) == len(expected) and
               state['attempts'] == state['grants'] == acquisitions and state['body_after'] == 1 and
               state['lock_a'] > 0 and state['lock_b'] > 0 and state['lock_a'] != state['lock_b'] and
               0 < state['stack_low'] < state['stack_high'] and not state['holder_active'] and not state['native_waiters'],
               'Native writer body, objects, acquisition or final drain differs', 'DATA_ERROR')
    rt.require((state['progress'] == 0) if early else
               (state['progress'] == 1 and state['progress_pid'] > 0), 'Native writer scheduling control differs', 'DATA_ERROR')
    calls = [event for event in primitive_events(messages) if event['origin'] == pid]
    owners = [event for event in native_events(messages) if event['origin'] == pid]
    rt.require(len(calls) == len(expected) * 4 and len(owners) == len(expected),
               'Native writer transaction/owner trace incomplete', 'DATA_ERROR')
    transactions = []
    symbols = {1: 'jit_test_native_write_lock', 2: 'jit_test_native_write_unlock'}
    for sequence, (expected_event, event, owner) in enumerate(zip(expected, state['events'], owners), 1):
        operation, obj, stage, acquisition = expected_event
        rt.require(event['operation'] == operation and event['object'] == obj and event['pid'] == pid and
                   event['cpu'] == cpu and state['stack_low'] <= event['stack_address'] < state['stack_high'] and
                   all(event[name] == 0 for name in ('preempt_before', 'preempt_after', 'rcu_before', 'rcu_after',
                                                    'irqs_before', 'irqs_after')) and
                   event['switches_after'] >= event['switches_before'], 'Native writer actual task/stack/CPU state differs', 'DATA_ERROR')
        transactions.append(validate_transaction(calls, root, pid, descriptors[symbols[operation]]['target'],
            image_generation, None, sequence, final=early and sequence == len(expected)))
        rt.require(owner['stage'] == stage and owner['origin'] == owner['task'] == pid and
                   owner['executor'] == root['executor'] and owner['identity'] == root['identity'] and
                   owner['generation'] == root['generation'] and owner['sequence'] == sequence and
                   owner['acquisition_seq'] == acquisition and owner['kind'] == 4 and owner['object'] == obj and
                   owner['preempt'] == owner['rcu'] == 0, 'Native writer exact owner/acquisition record differs', 'DATA_ERROR')
    if not early:
        rt.require(state['events'][0]['switches_after'] > state['events'][0]['switches_before'],
                   'Native writer acquisition did not actually schedule O', 'DATA_ERROR')
    return dict(observation=state, transactions=transactions, owners=owners,
                actual_native_owner_kind=4, final_native_complete=early)


def run_native_write_checks(session):
    for early, flags in ((False, 4096), (True, 8192)):
        result = session.phase_begin('native-write-final-release' if early else 'native-write-blocked-nonlifo')
        holder = None
        if not early:
            holder = session.start(result['name'] + '-holder', 4, 0)
            observe(session, result['name'] + '-holder-ready', lambda state, native: native['holder_active'] == 1)
        client = session.start(result['name'] + '-root', 0, 1, flags)
        pid, cpu = client[2]['pid'], client[2]['cpu']
        if not early:
            blocked = observe(session, result['name'] + '-origin-blocked', lambda state, native:
                native['holder_active'] == native['native_waiters'] == native['attempts'] == 1 and native['grants'] == 0 and
                state['phase'] == -1 and state['slots'][1]['prefix'] == 1 and not state['slots'][1]['returned'] and
                process_observation(pid)['state'] == 'D')
            root = wait_root_enter(session, result['name'] + '-root-enter', pid,
                                   blocked['state']['lock_address'], blocked['state']['entry'])
            before = process_observation(root['executor'])
            progress = session.start(result['name'] + '-executor-cpu-progress', 5, 2, cpu=before['cpu'])
            session.join(progress)
            def executor_scheduled(state, native):
                after = process_observation(root['executor'])
                return (after['start_ticks'] == before['start_ticks'] and after['switches'] > before['switches'] and
                    native['holder_active'] == native['native_waiters'] == native['attempts'] == native['progress'] == 1 and
                    native['grants'] == 0 and native['progress_pid'] == progress[2]['pid'] and
                    native['progress_cpu'] == before['cpu'] and process_observation(pid)['state'] == 'D')
            waiting = observe(session, result['name'] + '-executor-scheduled-origin-still-blocked', executor_scheduled)
            result['blocked_schedule'] = dict(blocked=blocked, before=before,
                after=process_observation(root['executor']), progress_worker=progress[2], before_release=waiting,
                root_enter=root)
            control(RELEASE, 32)
            session.join(holder)
        observe(session, result['name'] + '-returned', lambda state, native:
                state['slots'][1]['returned'] == 1 and native['body_after'] == 1)
        session.join(client)
        session.faults()
        messages = session.messages[session.trace_start:]
        roots = [event for event in trace_events(messages) if event['event'] == 'enter' and event['origin'] == pid]
        rt.require(len(roots) == 1, 'Native writer root record missing/duplicated', 'NO_JIT')
        result['native_write'] = validate(messages, roots[0], pid, cpu, session.helper_descriptors,
            session.record['image_registry'][0]['generation'], native_write_snapshot(), early)
        session.phase_end(result, successful=[pid])
        result['execution'] = 'NATIVE_ORIGIN_WRITERS_SAME_EXECUTOR_IMAGE_FINAL_RELEASE' if early else \
                              'NATIVE_ORIGIN_WRITERS_BLOCKED_ACQUIRE_EXECUTOR_SCHEDULE_NONLIFO'
        session.save()
