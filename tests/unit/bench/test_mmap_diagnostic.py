"""Only virtual time, in-memory proc/sys fixtures and mocked transport/processes.

Run in the recovery VM. Neither main() nor a live observer/SSH command is run.
"""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'bench/mmap_lock'))
import diagnostic_observer as ob
import diagnostic_controller as ctl


def stat(tid, start=11, comm='worker'):
    fields = ['S'] + ['0'] * 37
    fields[19], fields[36] = str(start), '63'
    return (str(tid) + ' (' + comm + ') ' + ' '.join(fields)).encode()


class FakeClock:
    def __init__(self):
        self.ns = 0
        self.on_sleep = None

    def now(self):
        return self.ns

    def cpu(self):
        return self.ns // 100

    def stamp(self):
        return dict(monotonic_before_ns=self.ns, monotonic_after_ns=self.ns,
                    boottime_ns=self.ns + 20 * ob.NS, process_cpu_ns=self.cpu())

    def sleep(self, seconds):
        self.ns += round(seconds * ob.NS)
        if self.on_sleep:
            self.on_sleep()


class FakeFS:
    def __init__(self):
        command = b'qemu-system-x86_64\0retained-VM-arguments\0'
        self.expected = dict(pid=42, start_ticks=11, boot_id='fixture-boot',
                             command_sha256=hashlib.sha256(command).hexdigest(),
                             task_count=67, snapshot='fixture-snapshot')
        self.files = {'/tmp/kdlock-qemu.pid': b'42\n',
                      '/proc/sys/kernel/random/boot_id': b'fixture-boot\n',
                      '/proc/42/stat': stat(42, comm='qemu-system-x86'),
                      '/proc/42/cmdline': command,
                      '/proc/42/numa_maps': b'fixture NUMA maps\n'}
        self.dirs = {'/proc/42/task': [], '/sys/devices/system/cpu/cpufreq': ['policy0'],
                     '/sys/devices/system/node': ['node0', 'node1']}
        self.exe = dict(path='/usr/bin/qemu-system-x86_64', device=1, inode=2,
                        size=3, mtime_ns=4, ctime_ns=5)
        self.affinities = {0: [63]}
        self.reads = []
        self.before_read = None
        for tid in (42, 43, 44):
            self.add(tid)
        for cpu in range(64):
            self.add(100 + cpu, comm='CPU ' + str(cpu) + '/KVM', affinity=[cpu])
        for field in ob.POLICY_FIELDS:
            self.files['/sys/devices/system/cpu/cpufreq/policy0/' + field] = b'fixture\n'
        for node in range(2):
            self.files['/sys/devices/system/node/node' + str(node) + '/cpulist'] = b'0-31\n'

    def add(self, tid, start=11, comm='worker', affinity=None):
        self.dirs['/proc/42/task'].append(str(tid))
        prefix = '/proc/42/task/' + str(tid)
        self.files.update({prefix + '/stat': stat(tid, start, comm),
                           prefix + '/schedstat': b'100 20 3\n', prefix + '/io': b'write_bytes: 0\n',
                           prefix + '/wchan': b'futex_wait_queue\n'})
        self.affinities[tid] = affinity or [63]

    def read(self, path, limit=65536):
        self.reads.append(path)
        if self.before_read:
            self.before_read(path)
        data = self.files[path]
        if isinstance(data, BaseException):
            raise data
        if len(data) > limit:
            raise ValueError('fixture output bound: ' + path)
        return data

    def names(self, path, limit=1024):
        names = sorted(self.dirs[path])
        if len(names) > limit:
            raise ValueError('fixture inventory bound')
        return names

    def executable(self, path):
        return self.exe.copy()

    def affinity(self, tid):
        return self.affinities[tid]

    def processor(self):
        return 63


class FakeWire:
    def __init__(self, clock):
        self.clock, self.rows, self.inbox = clock, [], []
        self.auto_ack = True
        self.on_emit = None

    def emit(self, row):
        self.rows.append(copy.deepcopy(row))
        if self.on_emit:
            self.on_emit(row)
        if row['kind'] == 'launch_request' and self.auto_ack:
            r = row['request']
            stdout = (b'' if r['name'] == 'guest_true' else
                      (ob.IMAGE_SHA + '  /boot/vmlinuz-6.1.159-kdmm31\n').encode())
            self.inbox.extend([dict(kind='launched', id=r['id']),
                dict(kind='completed', id=r['id'], local_exit_observed=True, returncode=0,
                     stdout_base64=base64.b64encode(stdout).decode(), stderr_base64='',
                     completion_unconfirmed=False)])

    def receive(self):
        rows, self.inbox = self.inbox, []
        return rows


class FakeMonitor:
    def __init__(self, clock):
        self.clock, self.steps = clock, 0
        self.complete = self.closed = False
        self.error = None
        self.parts = {'response': b'fixture-snapshot\n(qemu) '}

    def step(self):
        self.steps += 1
        self.complete = self.steps == 5

    def close(self):
        self.closed = True

    def receipt(self):
        return dict(complete=self.complete, error=self.error, output_base64={'response': 'Zml4dHVyZQ=='})


class NoLive(unittest.TestCase):
    def setUp(self):
        # Fail immediately if an injected fixture leaks into an external action.
        for target in ('subprocess.Popen', 'socket.socket', 'os.kill', 'os.killpg', 'os.sched_getaffinity'):
            p = patch(target, side_effect=AssertionError('live operation forbidden: ' + target))
            p.start()
            self.addCleanup(p.stop)
        # Production adapters are exercised only in the explicit mocked transport
        # cases below. All observer runs receive FakeFS/FakeClock/FakeWire.
        for cls, names in ((ob.Proc, ('read', 'names', 'executable', 'affinity', 'processor')),
                           (ob.Clock, ('now', 'cpu', 'stamp', 'sleep'))):
            for name in names:
                p = patch.object(cls, name, side_effect=AssertionError('real adapter forbidden: ' + name))
                p.start()
                self.addCleanup(p.stop)
        for name in ('read', 'write', 'set_blocking'):
            p = patch.object(ctl.os, name, side_effect=AssertionError('real pipe I/O forbidden: ' + name))
            p.start()
            self.addCleanup(p.stop)


class Observations(NoLive):
    def setUp(self):
        super().setUp()
        self.fs, self.clock = FakeFS(), FakeClock()

    def capture(self):
        return ob.sample(self.fs, self.clock, self.fs.expected, self.fs.exe)

    def test_full_inventory_has_brackets_stat_pairs_io_and_affinity(self):
        row = self.capture()
        self.assertTrue(row['complete'])
        self.assertEqual(len(row['tasks']), 67)
        self.assertIn('io', row['tasks'][0])
        self.assertNotIn('io', next(t for t in row['tasks'] if t['tid'] == 100))
        self.assertEqual(row['observer_processor'], 63)
        self.assertEqual(row['tasks'][0]['stat_before']['start_ticks'], 11)
        self.assertIn('boottime_ns', row['tasks'][0]['end'])

    def test_retained_process_identity_components_fail_closed(self):
        for path, value in (('/tmp/kdlock-qemu.pid', b'99'),
                            ('/proc/sys/kernel/random/boot_id', b'newboot'),
                            ('/proc/42/stat', stat(42, 12)),
                            ('/proc/42/cmdline', b'changed')):
            with self.subTest(path=path):
                self.fs = FakeFS()
                self.fs.files[path] = value
                self.assertFalse(self.capture()['complete'])

    def test_executable_replacement_rejected(self):
        self.fs.exe['inode'] += 1
        old = dict(self.fs.exe, inode=2)
        self.assertFalse(ob.sample(self.fs, self.clock, self.fs.expected, old)['complete'])

    def test_task_exit_read_error_preserves_partial_fields(self):
        self.fs.files['/proc/42/task/42/wchan'] = PermissionError('denied')
        row = self.capture()
        self.assertFalse(row['complete'])
        self.assertIn('io', row['tasks'][0])
        self.assertIn('runtime_ns', row['tasks'][0])

    def test_tid_reuse_during_scan_is_incomplete(self):
        reads = 0
        def change(path):
            nonlocal reads
            if path == '/proc/42/task/42/stat':
                reads += 1
                if reads == 2:
                    self.fs.files[path] = stat(42, 99)
        self.fs.before_read = change
        self.assertFalse(self.capture()['complete'])

    def test_membership_change_and_bad_pin_are_incomplete(self):
        self.fs.affinities[42] = [62]
        self.assertFalse(self.capture()['complete'])
        self.fs = FakeFS()
        def change(path):
            if path == '/proc/42/task/163/stat' and '999' not in self.fs.dirs['/proc/42/task']:
                self.fs.add(999)
        self.fs.before_read = change
        self.assertFalse(self.capture()['complete'])

    def test_watchdog_preserves_partial_and_stops_further_proc_reads(self):
        self.fs.files['/proc/42/task/42/io'] = ob.ObserverAbort('deadline')
        row = self.capture()
        self.assertFalse(row['complete'])
        self.assertEqual(self.fs.reads[-1], '/proc/42/task/42/io')
        self.assertIn('runtime_ns', row['tasks'][0])
        self.assertNotIn('identity_after', row)

    def test_metadata_is_one_bundle_without_serial_reads(self):
        paths = list(ob.metadata_paths(self.fs, 42))
        self.assertEqual(len(paths), 8)
        self.assertEqual(len(set(paths)), len(paths))
        self.assertNotIn('/tmp/qemu-serial.log', paths)
        self.fs.dirs['/sys/devices/system/cpu/cpufreq'] = []
        with self.assertRaises(ValueError):
            list(ob.metadata_paths(self.fs, 42))


class Phases(NoLive):
    def setUp(self):
        super().setUp()
        self.fs, self.clock = FakeFS(), FakeClock()
        self.wire = FakeWire(self.clock)
        self.monitors = []
        def make(clock):
            monitor = FakeMonitor(clock)
            self.monitors.append(monitor)
            return monitor
        self.runner = ob.Observer(self.fs.expected, self.fs, self.clock, self.wire, make)

    def rows(self, kind):
        return [row for row in self.wire.rows if row['kind'] == kind]

    def test_success_exact_order_one_stimulus_each_and_no_qualification(self):
        self.assertTrue(self.runner.run())
        self.assertEqual([row['phase'] for row in self.rows('phase')],
                         [name for _, name in ob.PHASES[1:]])
        self.assertEqual([row['command'] for row in self.rows('launch_request')],
                         list(ob.GUEST_COMMANDS.values()))
        self.assertEqual(len(self.monitors), 1)
        self.assertEqual(len(self.rows('metadata_read')), 8)
        self.assertTrue(any(row['immediate_post_monitor'] for row in self.rows('sample')))
        self.assertGreater(len(self.rows('sample')), 100)
        self.assertLess(len(self.rows('sample')), 125)
        final = self.rows('final')[0]
        self.assertFalse(final['accepted'])
        self.assertFalse(final['cause_established'])
        self.assertLessEqual(final['elapsed_ns'], 60 * ob.NS)
        self.assertLessEqual(final['maximum_gap_ns'], ob.MAX_GAP)

    def test_existing_extra_worker_is_inventory_never_admission(self):
        self.fs.add(999)
        self.assertTrue(self.runner.run())
        inventory = self.rows('inventory_bound')[0]
        self.assertEqual(len(inventory['identities']), 68)
        self.assertEqual(inventory['original_admission_task_count'], 67)
        self.assertFalse(inventory['accepted'])

    def test_new_task_stops_with_five_second_tail_and_no_stimuli(self):
        def change():
            if self.clock.now() >= 7 * ob.NS and '999' not in self.fs.dirs['/proc/42/task']:
                self.fs.add(999)
        self.clock.on_sleep = change
        self.assertFalse(self.runner.run())
        self.assertEqual(self.rows('stop')[0]['reason'], 'first new QEMU task')
        self.assertFalse(self.monitors)
        self.assertFalse(self.rows('launch_request'))
        self.assertLessEqual(self.clock.now(), 12 * ob.NS)

    def test_boot_change_stops_prior_to_metadata(self):
        self.clock.on_sleep = lambda: self.fs.files.update(
            {'/proc/sys/kernel/random/boot_id': b'newboot'}) if self.clock.now() >= 7 * ob.NS else None
        self.assertFalse(self.runner.run())
        self.assertFalse(self.rows('metadata_read'))

    def test_failed_binding_never_enters_idle(self):
        self.fs.files['/tmp/kdlock-qemu.pid'] = b'99'
        self.assertFalse(self.runner.run())
        self.assertFalse(self.rows('phase'))
        self.assertFalse(self.rows('launch_request'))

    def test_observation_loss_stops_no_catch_up_launches(self):
        def skip():
            if 6 * ob.NS <= self.clock.now() < 7 * ob.NS:
                self.clock.ns += 40 * ob.NS
        self.clock.on_sleep = skip
        self.assertFalse(self.runner.run())
        self.assertIn('observation loss', self.rows('stop')[0]['reason'])
        self.assertFalse(self.rows('launch_request'))

    def test_nonzero_scan_time_and_ordinary_jitter_are_retained_not_rejected(self):
        def cost(path):
            if path.endswith('/schedstat'):
                self.clock.ns += 1_000_000
        self.fs.before_read = cost
        self.runner.executable = self.fs.exe.copy()
        self.runner.scan()
        self.assertEqual(self.rows('sample')[0]['duration_ns'], 67_000_000)
        self.clock.ns = 500_000_000
        self.runner.scan()
        self.assertIsNone(self.runner.stop_reason)
        # The uncovered gap is only 450 ms, but the scan-start gap is 517 ms.
        self.clock.ns += 450_000_000
        self.runner.scan()
        self.assertEqual(self.rows('sample')[-1]['unobserved_gap_ns'], 450_000_000)
        self.assertEqual(self.rows('sample')[-1]['gap_ns'], 517_000_000)
        self.assertIsNone(self.runner.stop_reason)

    def test_full_phases_with_scan_cost_and_oversleep_keep_nominal_cadence(self):
        # Deterministic 6.7 ms scans plus variable sleep/dispatch jitter. A
        # perfect virtual clock previously hid the zero-margin 500 ms policy.
        def cost(path):
            if path.endswith('/schedstat'):
                self.clock.ns += 100_000
        delays = iter([0, 1_000_000, 3_000_000, 7_000_000] * 2000)
        self.fs.before_read = cost
        self.clock.on_sleep = lambda: setattr(self.clock, 'ns', self.clock.ns + next(delays))
        self.assertTrue(self.runner.run())
        samples = self.rows('sample')
        self.assertTrue(all(row['duration_ns'] == 6_700_000 for row in samples))
        self.assertGreater(max(row['gap_ns'] or 0 for row in samples), 500_000_000)
        self.assertLess(max(row['gap_ns'] or 0 for row in samples), 550_000_000)
        self.assertGreater(len(samples), 110)
        self.assertLess(len(samples), 125)
        self.assertEqual(self.rows('start')[0]['sample_period_ns'], 500_000_000)
        self.assertEqual(self.rows('start')[0]['maximum_sample_start_gap_ns'], 5 * ob.NS)
        self.assertEqual(self.rows('final')[0]['completed_phases'],
                         ['metadata', 'monitor', 'guest_true', 'guest_hash'])
        self.assertEqual(len(self.monitors), 1)
        self.assertEqual(len(self.rows('launch_request')), 2)
        self.assertFalse(self.rows('final')[0]['accepted'])

    def test_phase_window_loss_boundary_is_separate_from_nominal_period(self):
        self.runner.executable = self.fs.exe.copy()
        self.runner.scan()
        self.clock.ns = 5 * ob.NS
        self.runner.scan()
        self.assertIsNone(self.runner.stop_reason)
        self.clock.ns += 5 * ob.NS + 1
        self.runner.scan()
        self.assertIn('observation loss', self.runner.stop_reason)
        self.assertEqual(self.rows('sample')[-1]['gap_ns'], 5 * ob.NS + 1)
        self.assertFalse(self.rows('launch_request'))

    def test_slow_scan_stops_even_without_prior_gap(self):
        def cost(path):
            if path.endswith('/schedstat'):
                self.clock.ns += 80_000_000
        self.fs.before_read = cost
        self.runner.executable = self.fs.exe.copy()
        self.runner.scan()
        self.assertEqual(self.rows('sample')[0]['duration_ns'], 5_360_000_000)
        self.assertIsNone(self.rows('sample')[0]['gap_ns'])
        self.assertIn('observation loss', self.runner.stop_reason)

    def test_end_stall_without_a_following_scan_cannot_complete(self):
        def skip():
            if self.runner.phase == 'tail':
                self.clock.ns += 6 * ob.NS
        self.clock.on_sleep = skip
        self.assertFalse(self.runner.run())
        final = self.rows('final')[0]
        self.assertEqual(final['completed_phases'], ['metadata', 'monitor', 'guest_true', 'guest_hash'])
        self.assertGreater(final['final_sample_start_gap_ns'], 5 * ob.NS)
        self.assertIn('observation loss at observer end', final['stop_reason'])
        self.assertFalse(final['observation_complete'])

    def test_successful_stimuli_cannot_replace_missing_phase_observations(self):
        # Less than the loss bound, but enough to leave the short final phase
        # unobserved before the normal 50 ms finish margin. Stimuli all succeed.
        # Complete the mock monitor in one step, keeping its required extra
        # scan on the nominal grid so the last pre-tail scan starts at 55 s.
        def immediate_monitor(clock):
            monitor = FakeMonitor(clock)
            monitor.steps = 4
            self.monitors.append(monitor)
            return monitor
        self.runner.monitor_factory = immediate_monitor
        def skip():
            if self.runner.phase == 'tail':
                self.clock.ns += 4_950_000_000
        self.clock.on_sleep = skip
        self.assertFalse(self.runner.run())
        final = self.rows('final')[0]
        self.assertEqual(final['completed_phases'], ['metadata', 'monitor', 'guest_true', 'guest_hash'])
        self.assertLessEqual(final['final_sample_start_gap_ns'], 5 * ob.NS)
        self.assertEqual(final['missing_observation_phases'], ['tail'])
        self.assertIn('missing task observations', final['stop_reason'])
        self.assertFalse(final['observation_complete'])

    def test_metadata_read_failure_preserves_earlier_bundle_rows(self):
        self.fs.files['/sys/devices/system/cpu/cpufreq/policy0/scaling_governor'] = PermissionError('denied')
        self.assertFalse(self.runner.run())
        self.assertEqual(len(self.rows('metadata_read')), 2)
        self.assertFalse(self.monitors)

    def test_monitor_timeout_has_partial_receipt_and_no_guest_launch(self):
        def make(clock):
            monitor = FakeMonitor(clock)
            monitor.step = lambda: None
            self.monitors.append(monitor)
            return monitor
        self.runner.monitor_factory = make
        self.assertFalse(self.runner.run())
        self.assertFalse(self.rows('launch_request'))
        self.assertEqual(len(self.rows('monitor_result')), 1)
        self.assertTrue(self.monitors[0].closed)
        self.assertIn('output_base64', self.rows('monitor_result')[0])

    def test_new_task_while_monitor_pending_stops_future_stimuli(self):
        def make(clock):
            monitor = FakeMonitor(clock)
            def pending():
                if '999' not in self.fs.dirs['/proc/42/task']:
                    self.fs.add(999)
            monitor.step = pending
            return monitor
        self.runner.monitor_factory = make
        self.assertFalse(self.runner.run())
        self.assertFalse(self.rows('launch_request'))
        self.assertEqual(self.rows('stop')[0]['reason'], 'first new QEMU task')

    def test_missing_guest_ack_does_not_launch_hash(self):
        self.wire.auto_ack = False
        self.assertFalse(self.runner.run())
        self.assertEqual(len(self.rows('launch_request')), 1)
        self.assertTrue(self.rows('final')[0]['remote_completion_unconfirmed'])
        self.assertGreaterEqual(len([r for r in self.rows('sample') if r['phase'] == 'guest_true']), 15)

    def test_invalid_guest_completion_or_wrong_ack_order_stops(self):
        for change in ('output', 'order', 'unknown', 'id'):
            with self.subTest(change=change):
                self.setUp()
                self.wire.auto_ack = False
                def ack(row):
                    if row['kind'] != 'launch_request':
                        return
                    self.wire.inbox = [dict(kind='launched', id=1), dict(kind='completed', id=1,
                        local_exit_observed=True, returncode=0, stdout_base64='', stderr_base64='',
                        completion_unconfirmed=False)]
                    if change == 'output':
                        self.wire.inbox[-1]['stdout_base64'] = 'eA=='
                    elif change == 'order':
                        self.wire.inbox.reverse()
                    elif change == 'unknown':
                        self.wire.inbox[-1]['completion_unconfirmed'] = True
                    else:
                        self.wire.inbox[0]['id'] = 99
                self.wire.on_emit = ack
                self.assertFalse(self.runner.run())
                self.assertEqual(len(self.rows('launch_request')), 1)

    def test_monitor_immediate_post_scan_sees_new_task(self):
        def change(row):
            if row['kind'] == 'monitor_result':
                self.fs.add(999)
        self.wire.on_emit = change
        self.assertFalse(self.runner.run())
        post = [r for r in self.rows('sample') if r['immediate_post_monitor']]
        self.assertEqual(post[0]['new_identities'], [(999, 11)])
        self.assertFalse(self.rows('launch_request'))

    def test_broken_receipt_channel_closes_monitor_and_stops_without_final_delivery(self):
        original = self.wire.emit
        def emit(row):
            if row['phase'] == 'monitor' and row['kind'] == 'sample':
                raise BrokenPipeError('sink disappeared')
            original(row)
        self.wire.emit = emit
        def make(clock):
            monitor = FakeMonitor(clock)
            monitor.step = lambda: None
            self.monitors.append(monitor)
            return monitor
        self.runner.monitor_factory = make
        self.assertFalse(self.runner.run())
        self.assertTrue(self.monitors[0].closed)
        self.assertFalse(self.rows('launch_request'))
        self.assertFalse(self.rows('final'))
        self.assertFalse(self.runner.final['observation_complete'])
        self.assertIn('BrokenPipeError', self.runner.final['output_error'])

    def test_stop_record_output_overflow_does_not_skip_socket_cleanup(self):
        original = self.wire.emit
        def emit(row):
            if row['kind'] == 'stop':
                raise ValueError('output cap')
            original(row)
        self.wire.emit = emit
        def make(clock):
            monitor = FakeMonitor(clock)
            def pending():
                if '999' not in self.fs.dirs['/proc/42/task']:
                    self.fs.add(999)
            monitor.step = pending
            self.monitors.append(monitor)
            return monitor
        self.runner.monitor_factory = make
        self.assertFalse(self.runner.run())
        self.assertTrue(self.monitors[0].closed)
        self.assertFalse(self.rows('launch_request'))
        self.assertTrue(self.runner.output_error)

    def test_final_receipt_failure_is_not_a_complete_observation(self):
        original = self.wire.emit
        def emit(row):
            if row['kind'] == 'final':
                raise BrokenPipeError('final lost')
            original(row)
        self.wire.emit = emit
        self.assertFalse(self.runner.run())
        self.assertFalse(self.runner.final['observation_complete'])


class MonitorChecks(NoLive):
    def setUp(self):
        super().setUp()
        self.clock, self.sock = FakeClock(), MagicMock()
        self.sock.connect_ex.return_value = 0
        self.sock.send.side_effect = lambda data: len(data)
        self.factory = MagicMock(return_value=self.sock)
        self.monitor = ob.Monitor(self.clock, self.factory)

    def test_one_socket_one_exact_query_and_partial_reads(self):
        self.sock.recv.side_effect = [b'ban', b'ner(qemu) ', b'snap', b'shots(qemu) ']
        for _ in range(5):
            self.monitor.step()
        self.assertTrue(self.monitor.complete)
        self.factory.assert_called_once()
        self.sock.connect_ex.assert_called_once_with('/tmp/qemu-monitor.sock')
        self.sock.send.assert_called_once_with(b'info snapshots\n')
        self.sock.close.assert_called_once()

    def test_timeout_preserves_bytes_without_retry(self):
        self.sock.recv.return_value = b'partial banner'
        self.monitor.step()
        self.clock.ns = 8 * ob.NS
        with self.assertRaises(TimeoutError):
            self.monitor.step()
        receipt = self.monitor.receipt()
        self.assertEqual(base64.b64decode(receipt['output_base64']['banner']), b'partial banner')
        self.sock.send.assert_not_called()
        self.factory.assert_called_once()

    def test_output_bound_counts_banner_and_response_together(self):
        self.monitor.parts['banner'].extend(b'x' * (ob.MONITOR_LIMIT - 8))
        self.monitor.state = 'response'
        self.sock.recv.return_value = b'overflow preserved'
        with self.assertRaises(ValueError):
            self.monitor.step()
        self.assertEqual(self.monitor.parts['response'], b'overflow preserved')

    def test_eof_and_access_failure_do_not_send_query(self):
        self.sock.recv.return_value = b''
        with self.assertRaises(EOFError):
            self.monitor.step()
        self.sock.send.assert_not_called()
        self.sock.connect_ex.return_value = 13
        with self.assertRaises(OSError):
            ob.Monitor(self.clock, self.factory)
        self.sock.close.assert_called_once()


class FakeChildChannel:
    def __init__(self):
        self.child = MagicMock(pid=987)
        self.code, self.done = None, False
        self.uncertain = True
        self.deadline_failed = False
        self.stdout = b''

    def poll(self):
        if self.done and not self.deadline_failed:
            self.uncertain = False
        return {}, self.done

    def receipt(self):
        return dict(pid=987, returncode=self.code, local_exit_observed=self.done,
                    completion_unconfirmed=self.uncertain,
                    stdout_base64=base64.b64encode(self.stdout).decode(), stderr_base64='')


class ControllerChecks(NoLive):
    def setUp(self):
        super().setUp()
        self.clock, self.sent, self.children = FakeClock(), [], []
        def launch(name, command):
            channel = FakeChildChannel()
            self.children.append((name, command, channel))
            return channel
        self.coordinator = ctl.Coordinator(launch, self.sent.append, self.clock.now)

    def request(self, name='guest_true', ident=1):
        return dict(kind='launch_request', command=ob.GUEST_COMMANDS[name],
                    request=dict(name=name, id=ident))

    def feed(self, *rows):
        self.coordinator.feed(b''.join((json.dumps(r) + '\n').encode() for r in rows))

    def test_exact_order_launch_and_completion_acknowledgements(self):
        self.feed(self.request())
        channel = self.children[0][2]
        channel.code, channel.done = 0, True
        self.coordinator.poll()
        self.feed(self.request('guest_hash', 2))
        self.assertEqual([r['kind'] for r in self.sent], ['launched', 'completed', 'launched'])
        self.assertEqual([c[1] for c in self.children], list(ob.GUEST_COMMANDS.values()))

    def test_stop_in_same_transport_batch_wins_over_launch(self):
        with self.assertRaises(ValueError):
            self.feed(self.request(), dict(kind='stop', reason='new task'))
        self.assertFalse(self.children)

    def test_stop_prevents_all_subsequent_requests(self):
        self.feed(dict(kind='stop', reason='new task'))
        with self.assertRaises(ValueError):
            self.feed(self.request())
        self.assertFalse(self.children)

    def test_pending_wrong_order_duplicate_and_arbitrary_command_refused(self):
        for request in (self.request('guest_hash', 2), dict(self.request(), command='uname -a')):
            with self.assertRaises(ValueError):
                self.feed(request)
        self.feed(self.request())
        with self.assertRaises(ValueError):
            self.feed(self.request('guest_hash', 2))
        self.assertEqual(len(self.children), 1)

    def test_timeout_unknown_sticky_even_after_later_local_exit(self):
        self.feed(self.request())
        self.clock.ns = 8 * ob.NS
        self.coordinator.poll()
        channel = self.children[0][2]
        channel.code, channel.done = 0, True
        self.coordinator.poll()
        self.assertTrue(self.coordinator.stopped)
        self.assertTrue(self.coordinator.receipts[0]['completion_unconfirmed'])
        self.assertEqual([r['kind'] for r in self.sent], ['launched', 'controller_stop'])
        channel.child.kill.assert_not_called()
        channel.child.terminate.assert_not_called()
        with self.assertRaises(ValueError):
            self.feed(self.request('guest_hash', 2))

    def test_nonzero_ssh_exit_is_not_remote_completion_proof(self):
        self.feed(self.request())
        channel = self.children[0][2]
        channel.done, channel.code = True, 255
        self.coordinator.poll()
        self.assertTrue(self.coordinator.receipts[0]['completion_unconfirmed'])
        self.assertTrue(self.coordinator.stopped)

    def test_partial_protocol_and_oversized_line(self):
        raw = (json.dumps(self.request()) + '\n').encode()
        self.coordinator.feed(raw[:7])
        self.assertFalse(self.children)
        self.coordinator.feed(raw[7:])
        self.assertEqual(len(self.children), 1)
        with self.assertRaises(ValueError):
            self.coordinator.feed(b'x' * (ob.MAX_LINE + 1))

    def test_consumed_child_partial_output_survives_limit_and_nonzero(self):
        child = MagicMock(pid=987)
        child.poll.return_value = 255
        logs = {'stdout': io.BytesIO(), 'stderr': io.BytesIO()}
        with patch.object(ctl.os, 'set_blocking'), patch.object(ctl.os, 'read', return_value=b'partial\xff'):
            channel = ctl.Channel(['fixture'], 4, logs, MagicMock(return_value=child))
            with self.assertRaises(ValueError):
                channel.poll()
        self.assertEqual(logs['stdout'].getvalue(), b'partial\xff')
        self.assertTrue(channel.receipt()['completion_unconfirmed'])
        self.assertEqual(base64.b64decode(channel.receipt()['stdout_base64']), b'partial\xff')
        child.kill.assert_not_called()
        child.terminate.assert_not_called()
        child.wait.assert_not_called()

    def test_child_timeout_has_no_kill_or_wait_path(self):
        child = MagicMock(pid=987)
        child.poll.return_value = None
        with patch.object(ctl.os, 'set_blocking'), patch.object(ctl.os, 'read', side_effect=BlockingIOError):
            channel = ctl.Channel(['fixture'], 100, {'stdout': io.BytesIO(), 'stderr': io.BytesIO()},
                                  MagicMock(return_value=child))
            channel.deadline_failed = True
            self.assertFalse(channel.poll()[1])
        self.assertTrue(channel.receipt()['completion_unconfirmed'])
        child.kill.assert_not_called()
        child.terminate.assert_not_called()
        child.wait.assert_not_called()

    def test_broken_stdin_preserves_both_available_outputs_and_prevents_later_launch(self):
        child = MagicMock(pid=987)
        child.poll.return_value = 255
        logs = {'stdout': io.BytesIO(), 'stderr': io.BytesIO()}
        with patch.object(ctl.os, 'set_blocking'), \
             patch.object(ctl.os, 'read', side_effect=[b'partial stdout', b'partial stderr']), \
             patch.object(ctl.os, 'write', side_effect=BrokenPipeError('stdin closed')) as write:
            channel = ctl.Channel(['fixture'], 1000, logs, MagicMock(return_value=child))
            channel.send(b'queued acknowledgement\n')
            self.coordinator.start_guest = lambda name, command: channel
            self.feed(self.request())
            self.coordinator.poll()
        self.assertEqual(logs['stdout'].getvalue(), b'partial stdout')
        self.assertEqual(logs['stderr'].getvalue(), b'partial stderr')
        self.assertTrue(channel.receipt()['completion_unconfirmed'])
        self.assertTrue(self.coordinator.stopped)
        self.assertEqual(write.call_count, 1)
        self.assertEqual([r['kind'] for r in self.sent], ['launched', 'controller_stop'])
        with self.assertRaises(ValueError):
            self.feed(self.request('guest_hash', 2))
        child.kill.assert_not_called()
        child.terminate.assert_not_called()
        child.wait.assert_not_called()


class WireChecks(NoLive):
    def wire(self):
        with patch.object(ob.os, 'set_blocking'):
            return ob.Wire(40, 41)

    def test_partial_writes_and_backpressure_preserve_exact_queued_bytes(self):
        wire = self.wire()
        written = bytearray()
        calls = 0
        def write(fd, data):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise BlockingIOError()
            size = 3 if calls == 1 else len(data)
            written.extend(data[:size])
            return size
        with patch.object(ob.os, 'write', side_effect=write), \
             patch.object(ob.os, 'read', side_effect=BlockingIOError):
            wire.emit(dict(kind='fixture', text='partial'))
            retained = bytes(wire.output)
            self.assertTrue(retained)
            self.assertEqual(wire.receive(), [])
            self.assertEqual(bytes(wire.output), retained)
            wire.flush()
        self.assertFalse(wire.output)
        self.assertEqual(json.loads(written), dict(kind='fixture', text='partial'))

    def test_output_cap_keeps_existing_prefix(self):
        wire = self.wire()
        with patch.object(ob.os, 'write', side_effect=BlockingIOError), patch.object(ob, 'MAX_LINE', 128):
            wire.emit(dict(kind='first', text='a' * 60))
            previous = bytes(wire.output)
            with self.assertRaises(ValueError):
                wire.emit(dict(kind='second', text='b' * 60))
        self.assertEqual(bytes(wire.output), previous)

    def test_partial_ack_lines_are_retained_until_complete(self):
        wire = self.wire()
        with patch.object(ob.os, 'read', side_effect=[b'{"kind":"laun', b'ched","id":1}\n']):
            self.assertEqual(wire.receive(), [])
            self.assertEqual(wire.receive(), [dict(kind='launched', id=1)])

    def test_final_flush_failure_keeps_unwritten_receipt(self):
        wire = self.wire()
        with patch.object(ob.os, 'write', side_effect=[BlockingIOError(), BrokenPipeError('closed')]):
            wire.emit(dict(kind='final', observation_complete=False))
            before = bytes(wire.output)
            with self.assertRaises(BrokenPipeError):
                wire.flush()
        self.assertEqual(bytes(wire.output), before)


class MemoryPath:
    def __init__(self, name='', store=None):
        self.name = name
        self.store = {} if store is None else store

    def __truediv__(self, name):
        return MemoryPath(self.name + '/' + name, self.store)

    def mkdir(self, **kwargs):
        if self.name in self.store:
            raise FileExistsError(self.name)
        self.store[self.name] = 'directory'

    def write_text(self, data):
        self.store[self.name] = data

    def open(self, mode):
        stream = io.BytesIO()
        original_close = stream.close
        def close():
            self.store[self.name] = stream.getvalue()
            original_close()
        stream.close = close
        return stream


class ExecutionReceipts(NoLive):
    def test_interruption_preserves_completed_guest_ack_and_partial_host_output(self):
        clock, output = FakeClock(), MemoryPath('fixture-output')
        host = FakeChildChannel()
        host.code = None
        host.send = MagicMock()
        guest = FakeChildChannel()
        guest.code, guest.done = 0, True
        launches = []
        request = dict(kind='launch_request', command='/bin/true', request=dict(name='guest_true', id=1))
        raw = (json.dumps(request) + '\n').encode()
        def factory(command, limit, logs):
            launches.append(command)
            if len(launches) == 1:
                steps = 0
                def poll():
                    nonlocal steps
                    steps += 1
                    if steps == 1:
                        logs['stdout'].write(raw)
                        return {'stdout': raw}, False
                    logs['stderr'].write(b'partial before interruption')
                    raise ob.ObserverAbort('fixture interrupt')
                host.poll = poll
                return host
            return guest
        with patch.object(ctl, 'payload', return_value=(b'fixture source', {'fixture': 'sha'})), \
             patch.object(ctl.Path, 'read_bytes', return_value=b'fixture controller'), \
             patch.object(ctl.time, 'process_time_ns', return_value=1):
            record = ctl.execute(output, factory, clock.now, clock.sleep)
        self.assertEqual(len(launches), 2)
        self.assertEqual(launches[1][-1], '/bin/true')
        self.assertEqual(record['guest_receipts'][0]['name'], 'guest_true')
        self.assertFalse(record['guest_receipts'][0]['completion_unconfirmed'])
        self.assertTrue(record['host_completion_unconfirmed'])
        self.assertFalse(record['observation_complete'])
        self.assertEqual(output.store['fixture-output/host.stdout'], raw)
        self.assertEqual(output.store['fixture-output/host.stderr'], b'partial before interruption')
        self.assertEqual(record['signals_sent'], 0)
        self.assertEqual(record['retries'], 0)
        host.child.kill.assert_not_called()
        guest.child.kill.assert_not_called()
        host.child.wait.assert_not_called()
        guest.child.wait.assert_not_called()


if __name__ == '__main__':
    unittest.main()
