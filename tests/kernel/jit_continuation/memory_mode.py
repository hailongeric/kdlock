"""Exact GS instruction observations; no performance scores or MM-body helper."""
import fcntl
import re
import struct

import bench_runtime as rt
from killable_mode import DEVICE, trace_events

SNAPSHOT = 0x8138450F
HEADER = ('version', 'errors', 'count', 'origin_stack', 'origin_stack_high',
          'body_after', 'cf_checks', 'reg_checks', 'sp_checks', 'read_value', 'read_checks')
FIELDS = ('stage', 'pid', 'cpu', 'stack_address', 'preempt', 'irqs', 'counter')


def memory_snapshot():
    buffer = bytearray(312)
    with open(DEVICE, 'rb', buffering=0) as device:
        fcntl.ioctl(device, SNAPSHOT, buffer, True)
    return decode_memory_snapshot(buffer)


def decode_memory_snapshot(buffer):
    rt.require(len(buffer) == 312, 'GS observation size differs', 'DATA_ERROR')
    words = struct.unpack('=39Q', buffer)
    state = dict(zip(HEADER, words[:11]))
    rt.require(state['version'] == 1 and state['count'] <= 4,
               'GS observation version/count differs', 'DATA_ERROR')
    state['events'] = [dict(zip(FIELDS, words[11 + index * 7:18 + index * 7]))
                       for index in range(state['count'])]
    return state


def memory_events(messages):
    rows = []
    hexadecimal = {'identity', 'ip', 'next', 'sp', 'offset', 'input_flags', 'output_flags',
                   'preempt_object', 'value'}
    required = {'stage', 'origin', 'executor', 'task', 'identity', 'generation', 'sequence',
                'image_generation', 'ip', 'next', 'sp', 'offset', 'width', 'operation',
                'preempt_operand', 'preempt_seq', 'preempt_object', 'input_flags', 'output_flags',
                'read', 'destination', 'value'}
    for line in messages.splitlines():
        if 'kd_service memory:' not in line:
            continue
        fields = dict(re.findall(r'(\w+)=([^\s]+)', line))
        rt.require(required <= fields.keys(), 'GS instruction trace incomplete', 'DATA_ERROR')
        row = dict(stage=fields['stage'])
        row.update((key, int(fields[key], 16 if key in hexadecimal else 10))
                   for key in required - {'stage'})
        for key in ('family_generation', 'artifact_sequence'):
            if key in fields:
                row[key] = int(fields[key])
        if 'source_value' in fields:
            row['source_value'] = int(fields['source_value'], 16)
        rows.append(row)
    return rows


def memory_plan(early=False):
    # Operation INC1/DEC2/MOV3, width and exact preempt-count classification.
    return [(1, 32, 1), (3, 32, 1), (2, 32, 1)] if early else [
        (1, 64, 0), (1, 32, 1), (3, 32, 1), (2, 32, 1), (2, 64, 0)]


def validate_memory_observation(state, pid, cpu, early=False):
    expected = [(0, 0), (1, 0), (0, 0)] if early else [(0, 0), (0, 1), (1, 1), (0, 0)]
    checks = len(memory_plan(early))
    rt.require(not state['errors'] and state['count'] == len(expected) and
               state['body_after'] == 1 and state['cf_checks'] == state['reg_checks'] ==
               state['sp_checks'] == checks and state['read_checks'] == 1 and
               0 <= state['read_value'] <= 0xffffffff and state['read_value'] & 0x7fffffff == 1 and
               0 < state['origin_stack'] < state['origin_stack_high'],
               'GS body/CF/GPR/SP/retirement observation differs', 'DATA_ERROR')
    for stage, (event, (preempt, counter)) in enumerate(zip(state['events'], expected)):
        rt.require(event['stage'] == stage and event['pid'] == pid and event['cpu'] == cpu and
                   state['origin_stack'] <= event['stack_address'] < state['origin_stack_high'] and
                   event['preempt'] == preempt and event['counter'] == counter and not event['irqs'],
                   'GS original task/CPU/stack, Native pin or local counter differs', 'DATA_ERROR')


def validate_memory_trace(messages, root, pid, image_generation, observation, cpu, early=False):
    from helper_mode import validate_execution_identity
    validate_memory_observation(observation, pid, cpu, early)
    rows = [row for row in memory_events(messages) if row['origin'] == pid]
    plan = memory_plan(early)
    rt.require(len(rows) == len(plan) * 4, 'GS transaction count differs', 'DATA_ERROR')
    checked = []
    preempt_object = None
    for sequence, (operation, width, preempt_operand) in enumerate(plan, 1):
        group = rows[(sequence - 1) * 4:sequence * 4]
        final = early and sequence == len(plan)
        rt.require([row['stage'] for row in group] ==
                   ['request', 'enter', 'done', 'complete' if final else 'resume'],
                   'GS transaction missing, repeated or out of order', 'DATA_ERROR')
        first = group[0]
        validate_execution_identity(group, root, image_generation)
        acquired = 1 if early else 2
        reading = operation == 3
        if preempt_operand and not reading:
            preempt_object = preempt_object or first['preempt_object']
        rt.require((first['preempt_seq'] == acquired and first['preempt_object'] == preempt_object > 0)
                   if preempt_operand and not reading else first['preempt_seq'] == first['preempt_object'] == 0,
                   'GS preempt ticket acquisition/object pairing differs', 'DATA_ERROR')
        rt.require(root['executor'] != pid and first['ip'] > 0 and first['next'] > first['ip'] and
                   observation['origin_stack'] <= first['sp'] < observation['origin_stack_high'] and
                   all(row['identity'] == root['identity'] and row['generation'] == root['generation'] and
                       row['executor'] == root['executor'] and row['sequence'] == sequence and
                       row['operation'] == operation and
                       row['width'] == width and row['preempt_operand'] == preempt_operand and
                       row['read'] == int(reading) and
                       (row['ip'], row['next'], row['sp'], row['offset'], row['input_flags'],
                        row['preempt_seq'], row['preempt_object'], row['destination']) ==
                       (first['ip'], first['next'], first['sp'], first['offset'], first['input_flags'],
                        first['preempt_seq'], first['preempt_object'], first['destination'])
                       for row in group),
                   'GS transaction changed root, image, instruction, operand or SP', 'DATA_ERROR')
        rt.require([row['task'] for row in group] == [root['executor'], pid, pid, root['executor']] and
                   first['input_flags'] & 1 and group[2]['output_flags'] & 1 and
                   group[2]['output_flags'] == group[3]['output_flags'],
                   'GS apply task or preserved CF/output flags differs', 'DATA_ERROR')
        if reading:
            rt.require(first['destination'] in (0, 1, 2, 3, 5, 6, 7, 8, 9, 12, 13, 14, 15) and
                       first['value'] == group[1]['value'] == 0 and
                       group[2]['value'] == group[3]['value'] == observation['read_value'] and
                       not ((first['input_flags'] ^ group[2]['output_flags']) & 0x8d5),
                       'GS normalized MOV result, zero extension, destination or flags differs', 'DATA_ERROR')
        else:
            rt.require(first['destination'] == 17 and all(row['value'] == 0 for row in group),
                       'GS mutation unexpectedly exported a GPR result', 'DATA_ERROR')
        if width == 64:
            rt.require(bool(group[2]['output_flags'] & 0x40) == (operation == 2),
                       'GS counter zero-result flags differ', 'DATA_ERROR')
        checked.append(group)
    return dict(transactions=checked, observation=observation)


def run_memory_checks(session):
    from helper_mode import primitive_events, validate_transaction

    for early, flags in ((False, 1024), (True, 2048)):
        result = session.phase_begin('gs-final-inline-preempt' if early else 'gs-counter-inline-preempt')
        client = session.start(result['name'] + '-root', 0, 1, flags)
        pid, cpu = client[2]['pid'], client[2]['cpu']
        session.observe(result['name'] + '-returned', lambda state: state['slots'][1]['returned'] == 1)
        session.join(client)
        session.faults()
        messages = session.messages[session.trace_start:]
        roots = [row for row in trace_events(messages) if row['event'] == 'enter' and row['origin'] == pid]
        rt.require(len(roots) == 1, 'GS root actual executor record missing', 'NO_JIT')
        image = session.service_generation()
        result['memory'] = validate_memory_trace(messages, roots[0], pid, image,
                                                memory_snapshot(), cpu, early)
        primitives = primitive_events(messages)
        calls = 2 if early else 4
        rt.require(len([row for row in primitives if row['origin'] == pid]) == calls * 4,
                   'GS observation primitive count differs', 'DATA_ERROR')
        result['observation_calls'] = [validate_transaction(primitives, roots[0], pid,
            session.helper_descriptors['jit_test_memory_observe']['target'], image, None, sequence)
            for sequence in range(1, calls + 1)]
        session.phase_end(result, successful=[pid])
        result['execution'] = 'ORIGINAL_TASK_GS_SAME_EXECUTOR_IMAGE_FINAL_IP_SP'
        session.save()
