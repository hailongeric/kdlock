"""Returning primitives and Native pairs using the continuation lifecycle."""
import errno
import fcntl
import os
import re
import signal
import struct

import bench_runtime as rt
from killable_mode import DEVICE, PARAMETERS, RELEASE, control, snapshot, trace_events, session_class as killable_session

SNAPSHOT, UNREGISTER = 0x85D8450C, 0x450D
FIELDS = ('origin_stack', 'calls', 'pid', 'stack_address', 'stack_low', 'stack_high',
          'preempt_before', 'irqs_before', 'arguments', 'result', 'body_result', 'body_after',
          'sleep_calls', 'jiffies_delta', 'switches_delta', 'child_acquired', 'child_released', 'signal_seen')
ARGUMENTS = (0x1122334455667788, 0x89ABCDEF01234567, 0x1020304050607080,
             0x55AA00FF88776611, 0xDEADBEEF2468ACE0)
DECLARATIONS = {
    'jit_test_call_scalar': (6, 1, 1), 'jit_test_call_wait': (6, 1, 1),
    'jit_test_native_spin_lock': (1, 2, 4), 'jit_test_native_spin_try': (1, 1, 5),
    'jit_test_native_spin_unlock': (1, 2, 6), 'jit_test_native_rcu_lock': (0, 2, 7),
    'jit_test_native_rcu_unlock': (0, 2, 8),
    'jit_test_memory_observe': (1, 2, 2),
}
SYMBOLS = tuple(DECLARATIONS)
NATIVE_SNAPSHOT = 0x87B8450E
NATIVE_FIELDS = ('operation', 'pid', 'stack_address', 'preempt_before', 'preempt_after',
                 'rcu_before', 'rcu_after', 'irqs_before', 'irqs_after', 'result')


def expected_result(index):
    a1, a2, a3, a4, a5 = ARGUMENTS
    return (0x7EDCBA9876543210 ^ index ^ (a1 + 3 * a2 + 5 * a3 + 7 * a4 + 11 * a5)) & ((1 << 64) - 1)


def helper_snapshot():
    buffer = bytearray(1496)
    with open(DEVICE, 'rb', buffering=0) as device:
        fcntl.ioctl(device, SNAPSHOT, buffer, True)
    return decode_helper_snapshot(buffer)


def decode_helper_snapshot(buffer):
    rt.require(len(buffer) == 1496, 'returning primitive observation size differs', 'DATA_ERROR')
    words = struct.unpack('=187Q', buffer)
    state = dict(zip(('version', 'registered', 'errors'), words[:3]))
    rt.require(state['version'] == 1, 'returning primitive observation ABI differs', 'DATA_ERROR')
    state['slots'] = []
    for index in range(8):
        row = words[3 + index * 23:26 + index * 23]
        state['slots'].append(dict(zip(FIELDS, (*row[:8], list(row[8:14]), *row[14:]))))
    return state


def native_snapshot():
    buffer = bytearray(1976)
    with open(DEVICE, 'rb', buffering=0) as device:
        fcntl.ioctl(device, NATIVE_SNAPSHOT, buffer, True)
    return decode_native_snapshot(buffer)


def decode_native_snapshot(buffer):
    rt.require(len(buffer) == 1976, 'Native observation size differs', 'DATA_ERROR')
    words = struct.unpack('=247Q', buffer)
    state = dict(zip(('version', 'count', 'errors', 'lock_address', 'body_after', 'stack_low', 'stack_high'), words[:7]))
    rt.require(state['version'] == 1 and state['count'] <= 24,
               'Native observation version/count differs', 'DATA_ERROR')
    state['events'] = [dict(zip(NATIVE_FIELDS, words[7 + index * 10:17 + index * 10]))
                       for index in range(state['count'])]
    return state


def descriptor_rows(text):
    rows = []
    for line in text.splitlines():
        fields = line.split()
        rt.require(len(fields) == 6, 'primitive descriptor discovery row differs', 'DATA_ERROR')
        cookie, target, nargs, result, context, symbol = fields
        rows.append(dict(cookie=int(cookie, 16), target=int(target, 16), nargs=int(nargs),
                         result=int(result), context=int(context), symbol=symbol))
    return rows


def call_table(text):
    rows = descriptor_rows(text)
    selected = {name: [row for row in rows if row['symbol'] == name] for name in SYMBOLS}
    rt.require(all(len(selected[name]) == 1 for name in SYMBOLS),
               'primitive fixture descriptor missing or duplicated', 'DATA_ERROR')
    selected = {name: selected[name][0] for name in SYMBOLS}
    rt.require(all(row['cookie'] > 0 and row['target'] > 0 and
                   (row['nargs'], row['result'], row['context']) == DECLARATIONS[name]
                   for name, row in selected.items()) and
               len({row['target'] for row in selected.values()}) == len(SYMBOLS),
               'primitive declaration target/arity/result/context differs', 'DATA_ERROR')
    return selected, rows


def primitive_events(messages):
    rows = []
    for line in messages.splitlines():
        if 'kd_service primitive:' not in line:
            continue
        fields = dict(re.findall(r'(\w+)=([^\s]+)', line))
        required = {'stage', 'origin', 'executor', 'identity', 'generation', 'sequence',
                    'target', 'return', 'task', 'image_generation', 'ax', 'flags'}
        rt.require(required <= fields.keys(), 'primitive transaction trace incomplete', 'DATA_ERROR')
        row = dict(stage=fields['stage'])
        for key in required - {'stage'}:
            row[key] = int(fields[key], 16 if key in ('identity', 'target', 'return', 'ax', 'flags') else 10)
        rows.append(row)
    return rows


def validate_transaction(events, root, pid, target, image_generation, result, sequence=None, final=False):
    rows = [row for row in events if row['origin'] == pid and
            (sequence is None or row['sequence'] == sequence)]
    rt.require([row['stage'] for row in rows] == ['request', 'enter', 'done', 'complete' if final else 'resume'],
               'primitive transaction missing, repeated or out of order', 'DATA_ERROR')
    rt.require(rows[0]['sequence'] > 0 and rows[0]['return'] > 0 and all(
        row['identity'] == root['identity'] and row['generation'] == root['generation'] and
        row['executor'] == root['executor'] and row['origin'] == pid and row['target'] == target and
        row['sequence'] == rows[0]['sequence'] and row['return'] == rows[0]['return'] and
        row['image_generation'] == image_generation for row in rows),
        'primitive transaction changed root, executor, target, sequence or image', 'DATA_ERROR')
    rt.require(root['executor'] != pid and
               [row['task'] for row in rows] == [root['executor'], pid, pid, root['executor']] and
               rows[2]['ax'] == rows[3]['ax'] and (result is None or rows[2]['ax'] == result) and
               rows[2]['flags'] == rows[3]['flags'],
               'primitive actual task or full AX return differs', 'DATA_ERROR')
    return rows


def native_plan(early=False):
    # Each tuple is (operation, preempt before/after, RCU before/after,
    # actual trylock result, owner stage, acquisition sequence).
    plan = [(1, 0, 1, 0, 0, 0, 'grant', 1)]
    if early:
        return plan + [(3, 1, 0, 0, 0, 0, 'release', 1)]
    plan.append((2, 1, 1, 0, 0, 0, 'not_granted', 2))
    plan.extend((4, 1, 1, depth, depth + 1, 0, 'grant', depth + 3) for depth in range(9))
    plan.extend((5, 1, 1, depth, depth - 1, 0, 'release', depth + 2) for depth in range(9, 0, -1))
    plan.extend(((3, 1, 0, 0, 0, 0, 'release', 1),
                 (2, 0, 1, 0, 0, 1, 'grant', 22), (3, 1, 0, 0, 0, 0, 'release', 22)))
    return plan


def validate_native_observation(state, pid, early=False):
    plan = native_plan(early)
    rt.require(not state['errors'] and state['count'] == len(plan) and state['body_after'] == 1 and
               state['lock_address'] > 0 and 0 < state['stack_low'] < state['stack_high'] and
               len(state['events']) == len(plan), 'Native body/count/retirement observation differs', 'DATA_ERROR')
    for event, expected in zip(state['events'], plan):
        operation, before, after, rcu_before, rcu_after, result, _, _ = expected
        rt.require(event['operation'] == operation and event['pid'] == pid and
                   state['stack_low'] <= event['stack_address'] < state['stack_high'] and
                   (event['preempt_before'], event['preempt_after'], event['rcu_before'], event['rcu_after'],
                    event['result']) == (before, after, rcu_before, rcu_after, result) and
                   event['irqs_before'] == event['irqs_after'] == 0,
                   'Native API task/stack, grant result or context delta differs', 'DATA_ERROR')
    return plan


def native_events(messages):
    rows = []
    for line in messages.splitlines():
        if 'kd_service native:' not in line:
            continue
        fields = dict(re.findall(r'(\w+)=([^\s]+)', line))
        required = {'stage', 'origin', 'executor', 'task', 'identity', 'generation',
                    'sequence', 'acquisition_seq', 'kind', 'object', 'preempt', 'rcu'}
        rt.require(required <= fields.keys(), 'Native owner trace incomplete', 'DATA_ERROR')
        row = dict(stage=fields['stage'])
        row.update((key, int(fields[key], 16 if key in ('identity', 'object') else 10))
                   for key in required - {'stage'})
        rows.append(row)
    return rows


def validate_native_trace(messages, root, pid, descriptors, image_generation, observation, early=False):
    plan = validate_native_observation(observation, pid, early)
    transactions = primitive_events(messages)
    rt.require(len([row for row in transactions if row['origin'] == pid]) == len(plan) * 4,
               'Native primitive transaction count differs', 'DATA_ERROR')
    owners = [row for row in native_events(messages) if row['origin'] == pid]
    rt.require(len(owners) == len(plan), 'Native owner grant/release count differs', 'DATA_ERROR')
    symbols = {1: 'jit_test_native_spin_lock', 2: 'jit_test_native_spin_try',
               3: 'jit_test_native_spin_unlock', 4: 'jit_test_native_rcu_lock', 5: 'jit_test_native_rcu_unlock'}
    checked = []
    for sequence, (expected, owner) in enumerate(zip(plan, owners), 1):
        operation, _, after, _, rcu_after, value, stage, acquired = expected
        checked.append(validate_transaction(transactions, root, pid, descriptors[symbols[operation]]['target'],
            image_generation, value if operation == 2 else None, sequence, early and sequence == len(plan)))
        rt.require(owner['stage'] == stage and owner['identity'] == root['identity'] and
                   owner['generation'] == root['generation'] and owner['executor'] == root['executor'] and
                   owner['task'] == owner['origin'] == pid and owner['sequence'] == sequence and
                   owner['acquisition_seq'] == acquired and owner['kind'] == (1 if operation <= 3 else 2) and
                   owner['object'] == (observation['lock_address'] if operation <= 3 else 0) and
                   owner['preempt'] == after and owner['rcu'] == rcu_after,
                   'Native owner identity, acquisition pairing or actual context differs', 'DATA_ERROR')
    return dict(transactions=checked, owners=owners, observation=observation)


def session_class(base):
    class HelperSession(killable_session(base)):
        def counts(self, label):
            result = super().counts(label)
            if label == 'initial':
                caps = self.record['capabilities']
                rt.require(caps['version'] == 16 and
                           caps['features'] & ((1 << 14) | (1 << 15) | (1 << 16)) ==
                           ((1 << 14) | (1 << 15) | (1 << 16)),
                           'returning primitive/GS instruction service unavailable', 'ENVIRONMENT')
                state = helper_snapshot()
                rt.require(state['registered'] == 1 and not state['errors'],
                           'primitive fixture registration failed', 'DATA_ERROR')
                self.helper_descriptors, self.helper_table_before = call_table(
                    (PARAMETERS / 'service_call_table').read_text())
                try:
                    control(UNREGISTER)
                except OSError as error:
                    rt.require(error.errno == errno.EBUSY, 'open-source unregister result differs', 'DATA_ERROR')
                else:
                    raise rt.Failure('DATA_ERROR', 'registered primitives removed before source closure')
                rt.require(helper_snapshot()['registered'] == 1,
                           'failed unregister dropped registration pin', 'DATA_ERROR')
                self.record.update(helper_descriptors=self.helper_descriptors,
                                   open_source_unregister='EBUSY; registration retained')
                self.save()
            return result

        def observe_helper(self, label, predicate):
            return self.observe_pair(label, predicate)

        def observe_pair(self, label, predicate):
            # Reuse the existing bounded controller's wait/drain behavior.
            observed = {}
            def check(state):
                helper = helper_snapshot()
                rt.require(not helper['errors'], 'primitive fixture reported an error', 'DATA_ERROR')
                observed.update(state=state, helper=helper)
                return predicate(state, helper)
            self.observe(label, check)
            rt.write_json(self.path / (label + '.helper.json'), observed)
            return observed

        def measure(self):
            self.clients = []
            self.initial = snapshot()
            self.record['execution_status'] = 'MEASURING'
            trace = PARAMETERS / 'service_trace'
            trace.write_text('1\n')
            rt.require(trace.read_text().strip() == 'Y', 'service trace readback differs')
            self.record['service_trace_during_checks'] = True
            for sleeping, symbol, flags in ((False, SYMBOLS[0], 64), (True, SYMBOLS[1], 128)):
                result = self.phase_begin('primitive-sleeping-child' if sleeping else 'primitive-six-word-scalar')
                client = self.start(result['name'] + '-root', 0, 1, flags)
                pid = client[2]['pid']
                if sleeping:
                    self.observe_helper('primitive-child-held-before-signal', lambda state, helper:
                        state['phase'] == -1 and state['slots'][1]['prefix'] == 1 and
                        not state['slots'][1]['returned'] and helper['slots'][1]['calls'] == 1 and
                        helper['slots'][1]['child_acquired'] == 1 and
                        helper['slots'][1]['child_released'] == 0 and helper['slots'][1]['sleep_calls'] > 0)
                    os.kill(pid, signal.SIGKILL)
                    result['signal_sent_after_parent_commit'] = True
                    control(RELEASE, 16)
                self.observe_helper(result['name'] + '-returned', lambda state, helper:
                    state['slots'][1]['returned'] == 1 and helper['slots'][1]['body_after'] == 1)
                self.join(client, killed=sleeping)
                self.faults()
                state = helper_snapshot()
                row = state['slots'][1]
                value = expected_result(1)
                rt.require(row['calls'] == row['body_after'] == 1 and row['pid'] == pid and
                           row['origin_stack'] == row['stack_low'] > 0 and
                           row['stack_low'] <= row['stack_address'] < row['stack_high'] and
                           row['preempt_before'] == row['irqs_before'] == 0 and
                           row['arguments'] == [1, *ARGUMENTS] and row['result'] == row['body_result'] == value,
                           'primitive original task/stack, six arguments, AX or body replay differs', 'DATA_ERROR')
                rt.require((row['sleep_calls'] > 0 and row['jiffies_delta'] > 0 and row['switches_delta'] > 0 and
                            row['child_acquired'] == row['child_released'] == row['signal_seen'] == 1) if sleeping else
                           all(row[key] == 0 for key in ('sleep_calls', 'child_acquired', 'child_released', 'signal_seen')),
                           'primitive sleeping child/context or post-grant signal result differs', 'DATA_ERROR')
                roots = [row for row in trace_events(self.messages[self.trace_start:]) if row['event'] == 'enter' and row['origin'] == pid]
                rt.require(len(roots) == 1, 'primitive root actual executor record missing', 'NO_JIT')
                root = roots[0]
                transactions = validate_transaction(primitive_events(self.messages[self.trace_start:]), root, pid,
                    self.helper_descriptors[symbol]['target'], self.record['image_registry'][0]['generation'], value)
                result.update(helper_observation=state, primitive_transaction=transactions,
                              execution='ORIGINAL_TASK_PRIMITIVE_SAME_EXECUTOR_IMAGE_RETURN')
                self.phase_end(result, successful=[pid])
                result['execution'] = 'ORIGINAL_TASK_PRIMITIVE_SAME_EXECUTOR_IMAGE_RETURN'
                self.save()
            for early, flags in ((False, 256), (True, 512)):
                result = self.phase_begin('native-early-outer-release' if early else 'native-spin-try-rcu-depth9')
                client = self.start(result['name'] + '-root', 0, 1, flags)
                pid = client[2]['pid']
                self.observe(result['name'] + '-returned', lambda state: state['slots'][1]['returned'] == 1)
                self.join(client)
                self.faults()
                messages = self.messages[self.trace_start:]
                roots = [row for row in trace_events(messages) if row['event'] == 'enter' and row['origin'] == pid]
                rt.require(len(roots) == 1, 'Native root actual executor record missing', 'NO_JIT')
                result['native_pairs'] = validate_native_trace(messages, roots[0], pid, self.helper_descriptors,
                    self.record['image_registry'][0]['generation'], native_snapshot(), early)
                self.phase_end(result, successful=[pid])
                result['execution'] = 'NATIVE_ORIGIN_PAIRS_SAME_EXECUTOR_IMAGE'
                self.save()
            from memory_mode import run_memory_checks
            run_memory_checks(self)
            trace.write_text('0\n')
            rt.require(trace.read_text().strip() == 'N', 'service trace final readback differs')
            self.record.update(accepted=True, jit_status='RETURNING_ORIGINAL_TASK_PRIMITIVES',
                               escape_events=[], origin_service=False, service_trace_final=False)
            self.save()

        def after_source_retire(self):
            control(UNREGISTER)
            state = helper_snapshot()
            rt.require(state['registered'] == 0 and not state['errors'],
                       'primitive registration did not retire after source closure', 'UNDRAINED')
            lines = (PARAMETERS / 'service_call_table').read_text().splitlines()
            rt.require(not any(line.split()[-1] in SYMBOLS for line in lines if line.split()),
                       'primitive declarations remain after unregister', 'UNDRAINED')
            expected = [row for row in self.helper_table_before if row['symbol'] not in SYMBOLS]
            rt.require(descriptor_rows('\n'.join(lines)) == expected,
                       'unregister changed another descriptor owner', 'UNDRAINED')
            rt.write_json(self.path / 'primitive-unregistered.json', state)
            self.record['helper_registration_retired'] = True
            self.save()
    return HelperSession
