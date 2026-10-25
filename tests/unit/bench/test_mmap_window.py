"""Offline control/receipt fixtures. No SSH, host observer or kernel workload."""
import copy
import json
import selectors
import shlex
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'bench/mmap_lock'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import window
import window_controller
import report
import test_mmap_scaling as scaling

NONCE = '0123456789abcdef0123456789abcdef'


def core():
    return [dict(tid=100+i, start_ticks=50+i, comm=f'CPU {i}/KVM' if i < 64 else f'service-{i}',
                 affinity=[i] if i < 64 else [63]) for i in range(67)]


def auxiliary(kind='inactive_auxiliary'):
    return dict(tid=300, start_ticks=60, comm='worker', affinity=[63], **{'class': kind},
                evidence='a'*64, reason='Fixture explicitly classifies this QEMU role.')


def samples(extra=None):
    tasks = core() + ([extra] if extra else [])
    rows = []
    for i in range(7):
        observed = [dict(t, state='S', complete=True, runtime_ns=100, runqueue_wait_ns=100,
                         timeslices=1, io={k: 0 for k in window.IO_KEYS}) for t in tasks]
        rows.append(dict(begin_ns=i*506_000_000, end_ns=i*506_000_000+6_000_000,
            complete=True, errors=[], equal_observed_tid_lists=True,
            identity_before=dict(pid=1, start_ticks=1), identity_after=dict(pid=1, start_ticks=1),
            initial_tids=sorted(t['tid'] for t in tasks), final_tids=sorted(t['tid'] for t in tasks), tasks=observed))
    return rows


class Ordering(unittest.TestCase):
    def test_shell_program_keeps_cd_and_quoted_arguments_with_nonce(self):
        with tempfile.TemporaryDirectory(prefix="mmap control ' ") as directory:
            script = 'import json,os,sys; print(json.dumps([os.getcwd(),os.environ["KDLOCK_WINDOW_NONCE"],sys.argv[1]]))'
            argument = 'spaces, quotes " and \' and $literal'
            command = 'cd ' + shlex.quote(directory) + ' && ' + shlex.join([sys.executable, '-c', script, argument])
            result = subprocess.run(['sh', '-c', window_controller.guest_command(command, NONCE)],
                                    capture_output=True, text=True, timeout=5, check=True)
            self.assertEqual(json.loads(result.stdout), [directory, NONCE, argument])

    def test_order_is_single_use(self):
        p = window.Protocol(NONCE)
        for name in p.ORDER:
            p.add(name)
        with self.assertRaises(ValueError):
            p.add('exited')

    def test_duplicate_out_of_order_and_early_export(self):
        for sequence in (['go'], ['prepared', 'prepared'], ['prepared', 'go', 'export'],
                         ['prepared', 'go', 'started', 'endpoint']):
            with self.subTest(sequence=sequence), self.assertRaises(ValueError):
                p = window.Protocol(NONCE)
                for name in sequence:
                    p.add(name)

    def test_wrong_nonce_or_policy(self):
        for change in ({'nonce': 'f'*32}, {'measurement_policy': window.LEGACY}, {'control_abi': 'MW0'}):
            row = dict(json.loads(window.frame('prepared', NONCE)), **change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                window.Protocol(NONCE).receive(row, 'prepared')

    def test_legacy_missing_policy_never_becomes_window(self):
        self.assertEqual(window.policy({}), window.LEGACY)
        with self.assertRaises(ValueError):
            window.policy({'measurement_policy': 'unknown'})

    def test_lost_ack_or_uncertain_completion_cannot_replay(self):
        p = window.Protocol(NONCE)
        for event in p.ORDER:
            p.add(event)
        row = dict(**window.binding(), nonce=NONCE, events=p.events, returncode=0,
                   completion_confirmed=True, publication_after_endpoint=True)
        for change in ({'events': p.events[:-1]}, {'completion_confirmed': False},
                       {'publication_after_endpoint': False}, {'returncode': 3}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                window.control_replay(dict(row, **change))

    def test_actual_token_hash_and_error_bindings_are_required(self):
        p = window.Protocol(NONCE)
        for event in p.ORDER:
            fields = {}
            if event in ('finished', 'export'):
                fields['completion_token'] = '0'*16
            if event in ('endpoint', 'export'):
                fields['endpoint_sha256'] = 'a'*64
            p.add(event, **fields)
        row = dict(**window.binding(), nonce=NONCE, events=p.events, returncode=0,
                   completion_confirmed=True, publication_after_endpoint=True,
                   completion_token='0'*16, endpoint_sha256='a'*64)
        self.assertTrue(window.control_replay(row))
        for change in ({'error': 'failed before exit'}, {'completion_token': '1'*16},
                       {'endpoint_sha256': 'b'*64}):
            with self.assertRaises(ValueError):
                window.control_replay(dict(row, **change))
        for index, key in ((3, 'completion_token'), (4, 'endpoint_sha256'), (5, 'completion_token')):
            bad = copy.deepcopy(row)
            del bad['events'][index][key]
            with self.assertRaises((KeyError, ValueError)):
                window.control_replay(bad)

    def test_partial_writes_and_backpressure_have_absolute_deadlines(self):
        with patch.object(window.os, 'set_blocking'), patch.object(window.select, 'select', return_value=([], [9], [])), \
             patch.object(window.time, 'monotonic', return_value=0), \
             patch.object(window.os, 'write', side_effect=[InterruptedError(), BlockingIOError(), 1, 2]) as write:
            window.write_all(9, b'abc', 1)
            self.assertEqual(write.call_count, 4)
        for observation in ([0, 1], [0, 0, 2]):
            with patch.object(window.os, 'set_blocking'), patch.object(window.select, 'select', return_value=([], [9], [])), \
                 patch.object(window.os, 'write', return_value=3), \
                 patch.object(window.time, 'monotonic', side_effect=observation), \
                 self.assertRaises((TimeoutError, ValueError)):
                window.write_all(9, b'abc', 1)

    def test_fragmented_input_unterminated_input_and_deadline(self):
        with patch.object(window.os, 'set_blocking'), patch.object(window.select, 'select', return_value=([9], [], [])), \
             patch.object(window.time, 'monotonic', return_value=0), \
             patch.object(window.os, 'read', side_effect=[b'{"x":', b'1}\n']):
            self.assertEqual(window.read_frame(9, 100, 1), {'x': 1})
        with patch.object(window.os, 'set_blocking'), patch.object(window.select, 'select', return_value=([9], [], [])), \
             patch.object(window.time, 'monotonic', side_effect=[0, 0, 2]), \
             patch.object(window.os, 'read', return_value=b'{"unterminated":'), self.assertRaises(TimeoutError):
            window.read_frame(9, 100, 1)
        with patch.object(window.os, 'set_blocking'), patch.object(window.select, 'select', return_value=([9], [], [])), \
             patch.object(window.time, 'monotonic', side_effect=[0, 2]), \
             patch.object(window.os, 'read') as read, self.assertRaises(TimeoutError):
            window.read_frame(9, 100, 1)
        read.assert_not_called()


class Observations(unittest.TestCase):
    def test_jitter_and_expected_core_activity_are_retained(self):
        rows = samples()
        for i, row in enumerate(rows):
            row['tasks'][0]['runtime_ns'] += i*1000
        delta = window.check_samples(rows, core(), [])
        self.assertEqual(delta[-67]['runtime_ns'], 6000)

    def test_supported_inactive_auxiliary_can_be_stable_after_setup(self):
        aux = auxiliary()
        rows = samples(aux)
        # Cumulative setup I/O is present at the first guard scan and remains.
        for row in rows:
            row['tasks'][-1]['io']['write_bytes'] = 20480
        window.check_samples(rows, core(), [aux])

    def test_sleeping_auxiliary_cpu_queue_schedule_or_io_activity_rejects(self):
        aux = auxiliary()
        for field in (*window.COUNTERS, *window.IO_KEYS):
            rows = samples(aux)
            for row in rows[1:]:
                target = row['tasks'][-1] if field in window.COUNTERS else row['tasks'][-1]['io']
                target[field] += 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                window.check_samples(rows, core(), [aux])

    def test_expected_service_activity_is_not_universal_zero(self):
        aux = auxiliary('expected_service')
        rows = samples(aux)
        for i, row in enumerate(rows):
            row['tasks'][-1]['state'] = 'R'
            row['tasks'][-1]['runtime_ns'] += i*1000
            row['tasks'][-1]['io']['write_bytes'] = i*4096
        delta = window.check_samples(rows, core(), [aux])
        self.assertEqual(delta[-1]['write_bytes'], 6*4096)

    def test_unknown_inactive_worker_has_no_implicit_allowance(self):
        rows = samples(auxiliary())
        with self.assertRaises(ValueError):
            window.resolve_roles(rows[0]['tasks'], core(), [])
        with self.assertRaises(ValueError):
            window.check_samples(rows, core(), [])

    def test_role_resolved_once_at_prepared_guard(self):
        aux = auxiliary()
        definition = {k: v for k, v in aux.items() if k not in ('tid', 'start_ticks')}
        self.assertEqual(window.resolve_roles(samples(aux)[0]['tasks'], core(), [definition]), [aux])
        with self.assertRaises(ValueError):
            window.resolve_roles(samples(aux)[0]['tasks'], core(), [definition, definition])

    def test_new_task_removed_task_and_same_count_replacement(self):
        for mutation in ('new', 'removed', 'replacement'):
            rows = samples()
            if mutation == 'new':
                rows[-1]['tasks'].append(dict(rows[-1]['tasks'][0], tid=500))
            elif mutation == 'removed':
                rows[-1]['tasks'].pop()
            else:
                rows[-1]['tasks'][0]['start_ticks'] += 1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                window.check_samples(rows, core(), [])

    def test_affinity_and_comm_drift(self):
        for change in ({'affinity': [63]}, {'comm': 'replacement'}):
            rows = samples()
            rows[-1]['tasks'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                window.check_samples(rows, core(), [])

    def test_missing_partial_regressing_and_invalid_counters(self):
        for change in ({'complete': False}, {'runtime_ns': 99}, {'runtime_ns': True},
                       {'runtime_ns': -1}, {'io': {}}):
            rows = samples()
            rows[-1]['tasks'][0].update(change)
            with self.subTest(change=change), self.assertRaises((ValueError, KeyError)):
                window.check_samples(rows, core(), [])

    def test_missing_guard_and_final_observation_gap(self):
        for rows in (samples()[:4], samples()):
            if len(rows) == 7:
                rows[-1]['begin_ns'] += 2_000_000_000
                rows[-1]['end_ns'] += 2_000_000_000
            with self.assertRaises(ValueError):
                window.check_samples(rows, core(), [])

    def test_runnable_or_blocked_inactive_auxiliary(self):
        for state in ('R', 'D'):
            aux = auxiliary()
            rows = samples(aux)
            rows[0]['tasks'][-1]['state'] = state
            with self.assertRaises(ValueError):
                window.check_samples(rows, core(), [aux])

    def test_host_identity_or_partial_inventory_rejects(self):
        for change in ({'complete': False}, {'identity_after': {}}, {'equal_observed_tid_lists': False}):
            rows = samples()
            rows[-1].update(change)
            with self.assertRaises(ValueError):
                window.check_samples(rows, core(), [])


class Bridge(unittest.TestCase):
    def exchange(self, mode='valid', host_mode='valid', reverse=False):
        wire, peer = socket.socketpair()
        children, errors = [], []
        def launch(args, **kwargs):
            child = subprocess.Popen(args, **kwargs)
            children.append(child)
            return child
        def controller():
            try:
                peer.settimeout(3)
                source = peer.makefile('rb', buffering=0)
                prepared = json.loads(source.readline())
                self.assertEqual(prepared['event'], 'prepared')
                if host_mode == 'lost_go':
                    return
                peer.sendall(window.frame('export' if host_mode == 'early_export' else 'go', NONCE))
                if host_mode == 'early_export':
                    return
                self.assertEqual(json.loads(source.readline())['event'], 'started')
                if host_mode == 'duplicate_go':
                    peer.sendall(window.frame('go', NONCE));return
                finished = json.loads(source.readline())
                if host_mode == 'lost_export':
                    return
                token = 'f'*16 if host_mode == 'wrong_token' else finished['completion_token']
                peer.sendall(window.frame('export', NONCE, endpoint_sha256='a'*64, completion_token=token))
            except (OSError, ValueError) as error:
                errors.append(repr(error))
            finally:
                peer.close()
        thread = threading.Thread(target=controller)
        thread.start()
        actual_selector = selectors.DefaultSelector
        class OrderedSelector(actual_selector):
            def select(self, timeout=None):
                return sorted(super().select(timeout), key=lambda event: event[0].data, reverse=reverse)
        with wire.makefile('rb', buffering=0) as commands, wire.makefile('wb', buffering=0) as events:
            with patch.object(window.selectors, 'DefaultSelector', OrderedSelector):
                result, stdout, stderr = window.bridge([sys.executable, str(Path(__file__).with_name('mmap_control_child.py')), mode],
                                                       NONCE, commands, events, popen=launch)
        wire.close();thread.join(timeout=4)
        self.assertFalse(thread.is_alive())
        for child in children:
            # A test-owned fixture, not a workload. No kill or implied drain.
            child.wait(timeout=4)
            child.stdout.close();child.stderr.close()
        return result, stdout, stderr

    def test_valid_sequence_exports_after_endpoint(self):
        record, stdout, stderr = self.exchange()
        self.assertNotIn('error', record)
        self.assertTrue(window.control_replay(record))
        self.assertEqual(len(stdout.splitlines()), 2)
        self.assertFalse(stderr)

    def test_lost_ack_duplicate_wrong_token_and_early_export(self):
        for mode in ('lost_go', 'lost_export', 'duplicate_go', 'wrong_token', 'early_export'):
            with self.subTest(mode=mode):
                result, stdout, _ = self.exchange(host_mode=mode)
                self.assertIn('error', result)
                self.assertNotEqual([r['event'] for r in result['events']], list(window.Protocol.ORDER))
                self.assertEqual(len(stdout.splitlines()), 1)

    def test_premature_client_publication_is_not_accepted(self):
        result, _, _ = self.exchange(mode='premature')
        self.assertIn('error', result)
        self.assertFalse(result['publication_after_endpoint'])

    def test_pending_stdout_and_export_reject_in_both_descriptor_orders(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                result, _, _ = self.exchange(mode='ambiguous', reverse=reverse)
                self.assertIn('error', result)
                self.assertFalse(result['publication_after_endpoint'])

    def test_result_memory_is_bounded(self):
        result, _, _ = self.exchange(mode='large')
        self.assertIn('error', result)
        self.assertIn('bound', result['error'])


class ReplayIsolation(unittest.TestCase):
    def test_grid_stays_exact_and_rejects_policy_mixing(self):
        rows = scaling.rows()
        self.assertEqual(len(rows), 126)
        report.summarize(rows, scaling.bindings())
        for policy in (window.POLICY, 'unknown'):
            bad = copy.deepcopy(rows)
            bad[0]['measurement_policy'] = policy
            with self.assertRaises(ValueError):
                report.summarize(bad, scaling.bindings())

    def test_screen_cannot_be_promoted_to_full_grid(self):
        rows = scaling.rows()
        rows[0]['screen'] = True
        with self.assertRaises(ValueError):
            report.summarize(rows, scaling.bindings())


if __name__ == '__main__':
    unittest.main()
