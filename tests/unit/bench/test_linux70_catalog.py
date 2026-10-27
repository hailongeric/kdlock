"""Guest-only regression checks for catalog host identity and worker placement."""
import copy
import ast
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('linux70_catalog_checks', ROOT/'bench/catalog_single/linux70.py')
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


class HostIdentity(unittest.TestCase):
    def setUp(self):
        self.reference = dict(host_boot_id='host', cpufreq={'policy0':2000000}, no_turbo='1',
            numa={'node0':'0-31','node1':'32-63'}, recovery_snapshot='current', qemu=[dict(
                pid=10,start_ticks=20,args=['qemu-system-x86_64'],
                numa_maps='1000 bind:0 N0=10 kernelpagesize_kB=4\n2000 bind:1 N1=10 kernelpagesize_kB=4',
                tasks=[dict(tid=11,start_ticks=20,comm='CPU 0/KVM',affinity=[0]),
                       dict(tid=12,start_ticks=30,comm='worker',affinity=[63])])])

    def test_records_auxiliary_worker_lifetime_without_relaxing_placement(self):
        current=copy.deepcopy(self.reference)
        current['qemu'][0]['tasks'][-1]=dict(tid=13,start_ticks=40,comm='worker',affinity=[63])
        self.assertEqual(catalog.compare(self.reference,current),[])
        current['qemu'][0]['tasks'][-1]['affinity']=[0]
        self.assertTrue(catalog.compare(self.reference,current))

    def test_refuses_permanent_identity_policy_and_memory_changes(self):
        mutations=[lambda d:d.update(host_boot_id='new'),
                   lambda d:d.update(no_turbo='0'),
                   lambda d:d.update(cpufreq={}),
                   lambda d:d['qemu'][0].update(start_ticks=21),
                   lambda d:d['qemu'][0]['tasks'][0].update(start_ticks=21),
                   lambda d:d['qemu'][0]['tasks'][0].update(affinity=[1]),
                   lambda d:d['qemu'][0]['tasks'].append(dict(tid=99,start_ticks=20,comm='unknown',affinity=[63])),
                   lambda d:d['qemu'][0].update(numa_maps='1000 bind:1 kernelpagesize_kB=4')]
        for mutate in mutations:
            current=copy.deepcopy(self.reference);mutate(current)
            with self.subTest(current=current):
                self.assertTrue(catalog.compare(self.reference,current))

    def test_source_generations_use_separate_campaign_paths(self):
        original = catalog.CAMPAIGN
        try:
            catalog.select_campaign('catalog-linux70-ordinary-20261027')
            self.assertEqual(catalog.RAW.name, 'catalog-linux70-ordinary-20261027')
            self.assertEqual(catalog.PUBLIC.name, catalog.RAW.name)
            self.assertTrue(catalog.GUEST.endswith('/' + catalog.RAW.name))
            for value in ('../escape', 'catalog-linux70-/nested', 'catalog-linux70-'):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    catalog.select_campaign(value)
        finally:
            catalog.select_campaign(original)

    def test_only_explicit_drained_missing_body_failure_can_continue(self):
        row=dict(arm='kdlock',execution_status='NO_JIT',jit_acceptance='NO_JIT',
                 jit_bodies=0,jit_completions=0,drained=True,
                 measurement=dict(complete=True,data_ok=True))
        self.assertTrue(catalog.completed_record(row))
        for changes in (dict(drained=False),dict(cleanup_error='busy'),dict(jit_bodies=1),
                        dict(arm='native'),dict(execution_status='TIMEOUT'),
                        dict(measurement=dict(complete=True,data_ok=False))):
            self.assertFalse(catalog.completed_record(row|changes))


class FrequencyMonitor(unittest.TestCase):
    """Exercise the real orchestration without SSH, host MSRs or live timers."""
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.markers = self.root/'markers'; self.markers.mkdir()
        self.children, self.stops = [], []
        self.behavior = 'normal'
        self.raw_patch = mock.patch.object(catalog, 'RAW', self.root/'unused')
        self.raw_patch.start(); self.addCleanup(self.raw_patch.stop)
        for patch in (mock.patch.object(catalog, 'CAMPAIGN', 'stale-global-campaign'),
                      mock.patch.object(catalog.subprocess, 'Popen', side_effect=self.spawn),
                      mock.patch.object(catalog, 'remote', side_effect=self.stop_remote),
                      mock.patch.object(catalog.time, 'sleep')):
            patch.start(); self.addCleanup(patch.stop)
        self.addCleanup(self.close_finished_fakes)

    def campaign(self, suffix):
        catalog.RAW = self.root/('catalog-linux70-trusted-'+suffix)
        catalog.RAW.mkdir()

    def close_finished_fakes(self):
        # Test teardown explicitly finishes fake children; production timeouts
        # must leave their streams open until real completion is known.
        for child in self.children:
            child.returncode = 0
            child.output.close(); child.error.close()

    def spawn(self, argv, *, stdin, stdout, stderr):
        owner = self
        token = shlex.split(argv[-1])[-1]
        name = token.removeprefix(catalog.RAW.name+'-')
        receipt = catalog.RAW/(name+'-frequency-command.json')
        initial = json.loads(receipt.read_text())
        self.assertEqual(initial['token'], token)
        self.assertTrue(initial['completion_unconfirmed'])
        self.assertEqual(initial['script_sha256'], hashlib.sha256(
            (catalog.HERE/'frequency_monitor.py').read_bytes()).hexdigest())

        class ScriptPipe(io.BytesIO):
            def close(self):
                if not self.closed:
                    script = self.getvalue()
                    super().close()
                    recorded = json.loads(receipt.read_text())
                    owner.assertEqual(recorded['local_pid'], child.pid)
                    owner.assertEqual(recorded['script_sha256'], hashlib.sha256(script).hexdigest())
                    owner.assertIn(b'assert not STOP.exists()', script)
                    if child.marker.exists():
                        child.returncode = 1
                        child.error.write(b'AssertionError: existing STOP marker\n'); child.error.flush()
                    elif owner.behavior != 'startup_timeout':
                        child.emit(dict(event='start'))

        class Child:
            def __init__(self):
                self.pid = 41000+len(owner.children)
                self.output, self.error = stdout, stderr
                self.marker = owner.markers/('kdlock-linux70-'+token+'-stop')
                self.returncode = None
                self.stdin = ScriptPipe()
                self.stop_timeout = False

            def emit(self, event):
                self.output.write((json.dumps(event)+'\n').encode()); self.output.flush()

            def poll(self):
                return self.returncode

            def wait(self, timeout):
                owner.assertTrue(self.marker.exists())
                if self.stop_timeout:
                    raise subprocess.TimeoutExpired(argv, timeout)
                self.emit(dict(event='sample', policy_ok=True))
                self.emit(dict(event='complete', stop_requested=True))
                self.returncode = 0
                return 0

            def kill(self):
                owner.fail('monitor must never be killed')

            def terminate(self):
                owner.fail('monitor must never be terminated')

        child = Child(); self.children.append(child)
        return child

    def stop_remote(self, label, argv, **kwargs):
        self.assertFalse(kwargs['guest'])
        tree = ast.parse(kwargs['code'])
        touch = tree.body[1].value
        self.assertEqual(touch.func.attr, 'touch')
        self.assertEqual([(item.arg, ast.literal_eval(item.value)) for item in touch.keywords], [('exist_ok', False)])
        actual = ast.literal_eval(touch.func.value.args[0])
        self.stops.append((label, actual))
        (self.markers/Path(actual).name).touch(exist_ok=False)
        return dict(returncode=0, completion_unconfirmed=False)

    def test_old_case_marker_cannot_collide_and_each_campaign_stops_its_own_token(self):
        old = self.markers/'kdlock-linux70-taskname-w00-stop'; old.touch()
        tokens = []
        for suffix in ('20261028', '20261029'):
            self.campaign(suffix)
            state = catalog.monitor_start('taskname-w00')
            record = json.loads(state[3].read_text())
            tokens.append(record['token'])
            self.assertEqual(record['token'], catalog.RAW.name+'-taskname-w00')
            self.assertTrue(record['startup_confirmed'])
            catalog.monitor_stop('taskname-w00', state)
            self.assertEqual(self.stops[-1], ('taskname-w00-frequency-stop', record['stop_path']))
            finished = json.loads(state[3].read_text())
            self.assertEqual(finished['returncode'], 0)
            self.assertFalse(finished['completion_unconfirmed'])
            self.assertTrue(finished['telemetry_complete'])
            self.assertTrue(state[1].closed and state[2].closed)
        self.assertNotEqual(*tokens)
        self.assertTrue(old.exists())
        self.assertTrue(all((self.markers/('kdlock-linux70-'+token+'-stop')).exists() for token in tokens))

    def test_existing_qualified_marker_retains_actual_early_exit_without_removing_it(self):
        self.campaign('20261028')
        marker = self.markers/('kdlock-linux70-'+catalog.RAW.name+'-taskname-w00-stop'); marker.touch()
        with self.assertRaisesRegex(RuntimeError, 'exited before startup'):
            catalog.monitor_start('taskname-w00')
        receipt = json.loads((catalog.RAW/'taskname-w00-frequency-command.json').read_text())
        self.assertEqual(receipt['returncode'], 1)
        self.assertFalse(receipt['completion_unconfirmed'])
        self.assertFalse(receipt['startup_confirmed'])
        self.assertEqual(receipt['local_pid'], self.children[0].pid)
        self.assertTrue(self.children[0].output.closed and self.children[0].error.closed)
        self.assertTrue(marker.exists())
        self.assertEqual(self.stops, [])

    def test_startup_deadline_keeps_completion_unknown_and_live_streams_open(self):
        self.campaign('20261028'); self.behavior = 'startup_timeout'
        with mock.patch.object(catalog.time, 'monotonic', side_effect=(0, 16)):
            with self.assertRaises(TimeoutError) as caught:
                catalog.monitor_start('taskname-w00')
        state = caught.exception.monitor_state
        receipt = json.loads(state[3].read_text())
        self.assertTrue(receipt['completion_unconfirmed'])
        self.assertIsNone(receipt['returncode'])
        self.assertEqual(receipt['state'], 'STARTUP_UNCONFIRMED')
        self.assertFalse(state[1].closed or state[2].closed)
        self.assertEqual(self.stops, [])

    def test_stop_timeout_never_invents_completion_or_closes_live_streams(self):
        self.campaign('20261028')
        state = catalog.monitor_start('taskname-w00'); state[0].stop_timeout = True
        with self.assertRaises(subprocess.TimeoutExpired):
            catalog.monitor_stop('taskname-w00', state)
        receipt = json.loads(state[3].read_text())
        self.assertTrue(receipt['completion_unconfirmed'])
        self.assertIsNone(receipt['returncode'])
        self.assertEqual(receipt['state'], 'STOP_UNCONFIRMED')
        self.assertFalse(state[1].closed or state[2].closed)

    def test_unexpected_exit_before_stop_records_actual_completion_and_closes_streams(self):
        self.campaign('20261028')
        state = catalog.monitor_start('taskname-w00'); state[0].returncode = 7
        with self.assertRaisesRegex(RuntimeError, 'exited unexpectedly'):
            catalog.monitor_stop('taskname-w00', state)
        receipt = json.loads(state[3].read_text())
        self.assertEqual(receipt['returncode'], 7)
        self.assertFalse(receipt['completion_unconfirmed'])
        self.assertTrue(state[1].closed and state[2].closed)
        self.assertEqual(self.stops, [])


if __name__=='__main__':
    unittest.main()
