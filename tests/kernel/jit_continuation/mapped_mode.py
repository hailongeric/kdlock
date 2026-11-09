"""Differing-arity Native mapping and one bounded production allocation."""
import fcntl
import struct

import bench_runtime as rt
from killable_mode import DEVICE, trace_events
from helper_mode import primitive_events, validate_transaction

SNAPSHOT, REGISTER = 0x80F04511, 0x4512
WORD = 0x1122334455667788
RESULT = WORD ^ 0x6AE35D09C4B27180 ^ 1
HEADER = ('version', 'errors', 'registered', 'source_target', 'execution_target', 'logical_calls', 'calls', 'pid',
          'stack_address', 'stack_low', 'stack_high', 'preempt', 'irqs')
TAIL = ('result', 'body_result', 'body_after', 'body_flags', 'source_return',
        'allocation_size', 'allocation_flags', 'allocation_pointer', 'allocation_zero_bytes',
        'allocation_written_bytes', 'allocation_freed', 'allocation_body_after')


def decode_snapshot(data):
    rt.require(len(data) == 240, 'mapped observation length differs', 'DATA_ERROR')
    words = struct.unpack('=30Q', data)
    state = dict(zip(HEADER, words[:13]))
    state['arguments'] = list(words[13:18])
    state.update(zip(TAIL, words[18:]))
    rt.require(state['version'] == 1 and state['registered'] == 1 and not state['errors'],
               'mapped observation ABI, registration or errors differ', 'DATA_ERROR')
    return state


def snapshot():
    data = bytearray(240)
    with open(DEVICE, 'rb', buffering=0) as device:
        fcntl.ioctl(device, SNAPSHOT, data, True)
    return decode_snapshot(data)


def validate_mapped(state, transactions, pid):
    rt.require(state['logical_calls'] == 0 and state['calls'] == state['body_after'] == 1 and
               state['pid'] == pid and 0 < state['stack_low'] <= state['stack_address'] < state['stack_high'] and
               state['preempt'] == state['irqs'] == 0 and state['source_return'] > 0 and
               state['arguments'] == [1, 0, WORD, (1 << 64) - 1, state['source_return']] and
               state['result'] == state['body_result'] == RESULT and
               state['source_target'] > 0 and state['execution_target'] > 0 and
               state['source_target'] != state['execution_target'] and
               all(row['return'] == state['source_return'] and row['target'] == state['source_target'] and
                   row.get('execution_target') == state['execution_target'] for row in transactions) and
               (state['body_flags'] & 0x8C5) == (transactions[-1]['flags'] & 0x8C5),
               'mapped arguments, source CALL word, original task/stack, AX/flags or replay differ', 'DATA_ERROR')
    rt.require(all(state[key] == 0 for key in TAIL[5:]),
               'mapped scalar phase unexpectedly allocated', 'DATA_ERROR')


def validate_allocation(state):
    rt.require(state['allocation_size'] == state['allocation_zero_bytes'] ==
               state['allocation_written_bytes'] == 53 and state['allocation_pointer'] > 4096 and
               state['allocation_flags'] > 0 and state['allocation_freed'] == state['allocation_body_after'] == 1,
               'bounded production allocation, contents or exact release differs', 'DATA_ERROR')
    rt.require(all(state[key] == 0 for key in
                   ('logical_calls', 'calls', 'body_after', 'result', 'body_result', 'source_return')),
               'allocation phase unexpectedly ran the scalar fixture', 'DATA_ERROR')


def run_mapped_checks(session):
    for name, flag, allocation in (('primitive-mapped-two-to-five', 32768, False),
                                   ('primitive-mapped-allocation', 65536, True)):
        result = session.phase_begin(name)
        client = session.start(result['name'] + '-root', 0, 1, flag)
        pid = client[2]['pid']
        session.observe(result['name'] + '-returned', lambda state: state['slots'][1]['returned'] == 1)
        session.join(client)
        session.faults()
        messages = session.messages[session.trace_start:]
        roots = [row for row in trace_events(messages) if row['event'] == 'enter' and row['origin'] == pid]
        rt.require(len(roots) == 1, 'mapped root executor record missing', 'NO_JIT')
        root, state = roots[0], snapshot()
        events = primitive_events(messages)
        events = [row for row in events if row['origin'] == pid]
        generation = session.service_generation()
        if allocation:
            validate_allocation(state)
            rt.require(len(events) == 8, 'allocation/release transaction count differs', 'DATA_ERROR')
            calls = [validate_transaction(events, root, pid, session.allocation_descriptors[symbol]['target'],
                     generation, value, sequence=sequence) for sequence, symbol, value in (
                         (1, '__kmalloc_noprof', state['allocation_pointer']), (2, 'kfree', None))]
            native_target = calls[0][0].get('execution_target')
            rt.require(native_target and native_target != session.allocation_descriptors['__kmalloc_noprof']['target'] and
                       all(row.get('execution_target') == native_target for row in calls[0]) and
                       all(row.get('execution_target') == session.allocation_descriptors['kfree']['target'] for row in calls[1]),
                       'production mapped allocation or identity release execution target differs', 'DATA_ERROR')
            policy = 'ONE_PRODUCTION_MAPPED_ALLOCATION_EXACT_RELEASE'
        else:
            calls = validate_transaction(events, root, pid,
                session.helper_descriptors['jit_test_call_mapped']['target'], generation, RESULT)
            validate_mapped(state, calls, pid)
            policy = 'MAPPED_NATIVE_TWO_TO_FIVE_SAME_EXECUTOR_IMAGE_RETURN'
        result.update(mapped_observation=state, primitive_transactions=calls, execution=policy)
        session.phase_end(result, successful=[pid])
        result['execution'] = policy
        session.save()
