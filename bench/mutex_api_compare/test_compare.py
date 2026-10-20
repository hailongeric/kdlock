"""Guest-only tests for immutable input selection and matched comparison gates."""
from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import run
import report


class ComparisonTests(unittest.TestCase):
    def test_retained_program_copy_can_restore_execute_bit_without_changing_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source, binary = folder/'program.c', folder/'program'
            source.write_text('int main(void) { return 0; }\n')
            subprocess.run(['gcc', str(source), '-o', str(binary)], check=True,
                           capture_output=True)
            digest = run.sha(binary)
            binary.chmod(0o644)
            result = run.executable_copy(binary)
            self.assertEqual(result['mode_before'], '0o644')
            self.assertEqual(result['mode_after'], '0o744')
            self.assertEqual(run.sha(binary), digest)
            module = folder/'object.o'
            subprocess.run(['gcc', '-c', str(source), '-o', str(module)], check=True,
                           capture_output=True)
            with self.assertRaisesRegex(ValueError, 'executable'):
                run.executable_copy(module)

    def test_full_grid_has_three_matched_rotated_rounds_without_duplicates(self):
        plan = run.execution_order()
        self.assertEqual(len(plan), 7 * 21 * 3 * 4)
        self.assertEqual(len(set(plan)), len(plan))
        self.assertEqual(set(n for _, n, _, _ in plan), set(run.THREADS))
        counts = Counter((w, n, arm) for w, n, _, arm in plan)
        self.assertEqual(set(counts.values()), {3})
        for index in range(0, len(plan), 4):
            self.assertEqual({r[3] for r in plan[index:index+4]}, set(run.ARMS))
        self.assertNotEqual(plan[0][3], plan[4][3])

    def test_focused_replay_preserves_all_original_matched_rounds(self):
        points = {('c08', 2), ('c08', 3), ('c08', 4), ('c08', 5), ('rcuht', 2),
                  ('pipebytes', 3), ('pipebytes', 4), ('pipebytes', 5),
                  ('pipecap', 4), ('pipecap', 5)}
        plan = run.replay_order()
        self.assertEqual(len(plan), 120)
        self.assertEqual(len(set(plan)), 120)
        self.assertEqual({row[:2] for row in plan}, points)
        self.assertEqual(plan, [row for row in run.execution_order() if row[:2] in points])
        for index in range(0, len(plan), 4):
            matched = plan[index:index + 4]
            self.assertEqual(len({row[:3] for row in matched}), 1)
            self.assertEqual({row[3] for row in matched}, set(run.ARMS))
        self.assertEqual(set(Counter((w, n, a) for w, n, _, a in plan).values()), {3})

    def test_replay_uses_retained_collector_and_refuses_changed_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            prepared = Path(temporary)
            original = '/root/host_fs/kdlock/bench/spin_cacheline/bench_runtime.py'
            retained = prepared/'harness/bench/spin_cacheline/bench_runtime.py'
            retained.parent.mkdir(parents=True)
            retained.write_text('retained collector\n')
            digest = run.sha(retained)
            run.save(prepared/'harness-inputs.json', {original: digest})
            with patch.object(run, 'REPLAY_HARNESS_SHA256', run.sha(prepared/'harness-inputs.json')):
                self.assertEqual(run.retained_harness(prepared), {str(retained): digest})
                retained.write_text('later collector\n')
                with self.assertRaisesRegex(ValueError, 'frozen input changed'):
                    run.retained_harness(prepared)
                run.save(prepared/'harness-inputs.json', {original: run.sha(retained)})
                with self.assertRaisesRegex(ValueError, 'harness manifest differs'):
                    run.retained_harness(prepared)
            run.save(prepared/'harness-inputs.json', {
                '/root/host_fs/kdlock/../other.py': digest})
            with patch.object(run, 'REPLAY_HARNESS_SHA256', run.sha(prepared/'harness-inputs.json')), \
                    self.assertRaisesRegex(ValueError, 'unexpected original collector'):
                run.retained_harness(prepared)

    def test_replay_rejects_current_or_unbound_collector_imports(self):
        with tempfile.TemporaryDirectory() as temporary:
            retained = Path(temporary).resolve()
            current = run.ROOT/'bench/spin_cacheline/bench_runtime.py'
            bound = retained/'bench/spin_cacheline/bench_runtime.py'
            for path, manifest, error in (
                    (current, {}, 'current collector'),
                    (bound, {}, 'unbound retained')):
                with patch.object(run.sys, 'modules', {'collector': SimpleNamespace(__file__=str(path))}):
                    with self.assertRaisesRegex(ValueError, error):
                        run.verify_collector_modules(retained, manifest)
            with patch.object(run.sys, 'modules', {'collector': SimpleNamespace(__file__=str(bound))}):
                run.verify_collector_modules(retained, {str(bound): 'verified separately'})
            with patch.object(run.sys, 'modules', {
                    'bench_runtime': SimpleNamespace(__file__='/external/bench_runtime.py')}), \
                    self.assertRaisesRegex(ValueError, 'unexpected origin'):
                run.verify_collector_modules(retained, {str(bound): 'verified separately'})
            with patch.object(run.sys, 'modules', {}), \
                    self.assertRaisesRegex(ValueError, 'explicit collector'):
                run.verify_collector_modules(retained, {str(bound): 'verified separately'},
                    [(SimpleNamespace(__file__='/external/run.py'), 'bench/real_api/run.py')])

    def test_replay_rejects_copied_metadata_and_output_overlap(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prepared, copy = root/'original', root/'copied-metadata'
            prepared.mkdir()
            copy.mkdir()
            frozen = {v+'/'+g: dict(bundle=str(prepared/v/g), files={
                str(prepared/v/g/'source/input.c'): 'hash'})
                for v in ('baseline', 'current') for g in run.GROUPS}
            for folder in (prepared, copy):
                run.save(folder/'frozen-inputs.json', frozen)
            with patch.object(run, 'REPLAY_INPUTS_SHA256', run.sha(prepared/'frozen-inputs.json')):
                self.assertEqual(run.replay_inputs(prepared, root/'new'), frozen)
                with self.assertRaisesRegex(ValueError, 'independent'):
                    run.replay_inputs(prepared, prepared/'new')
                with self.assertRaisesRegex(ValueError, 'outside selected prepared root'):
                    run.replay_inputs(copy, prepared/'current/c08/new')
                frozen['current/c08']['files'] = {str(root/'outside.c'): 'hash'}
                run.save(prepared/'frozen-inputs.json', frozen)
                with patch.object(run, 'REPLAY_INPUTS_SHA256', run.sha(prepared/'frozen-inputs.json')), \
                        self.assertRaisesRegex(ValueError, 'escapes'):
                    run.replay_inputs(prepared, root/'new')

    def test_replay_requires_original_environment_and_records_page_placement(self):
        host = dict(cpufreq={'policy0': {'scaling_governor': 'ondemand'}},
            numa={'node0': '0-31', 'node1': '32-63'}, recovery_snapshot='recovery',
            qemu=[dict(pid=123, args=['qemu', '-m', '24G'],
                       tasks=[dict(comm='CPU 0/KVM', affinity=[0])],
                       numa_maps='1000 bind:0 anon=100 N0=90 N1=10 kernelpagesize_kB=4')])
        env = {k: 'same' for k in ('boot_id', 'cmdline', 'preemption', 'packages',
                                    'python', 'snapshot_tag', 'collector_topology')}
        topology = {'role_nodes': [0, 1]}
        current = json.loads(json.dumps(host))
        current['qemu'][0]['numa_maps'] = host['qemu'][0]['numa_maps'].replace('N0=90', 'N0=89')
        receipt = run.same_environment(host, current, env, env, topology, topology)
        self.assertTrue(receipt['configuration_matches'])
        self.assertNotEqual(receipt['original_memory'], receipt['replay_memory'])
        for key in ('cpufreq', 'numa'):
            bad = dict(current, **{key: {}})
            with self.assertRaisesRegex(ValueError, 'host configuration differs'):
                run.same_environment(host, bad, env, env, topology, topology)
        for key in ('boot_id', 'collector_topology'):
            with self.assertRaisesRegex(ValueError, 'guest environment differs'):
                run.same_environment(host, current, env, dict(env, **{key: 'changed'}),
                                     topology, topology)
        current['qemu'][0]['numa_maps'] = current['qemu'][0]['numa_maps'].replace('bind:0', 'bind:1')
        with self.assertRaisesRegex(ValueError, 'memory binding differs'):
            run.same_environment(host, current, env, env, topology, topology)

    def test_frozen_variants_preserve_directories_and_ignore_overwritten_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            run.save(bundle/'binary-sha256.json', {
                '/root/host_fs/kdlock/daemon/daemon': 'daemon-hash',
                '/old/c01/variants/native/mutex_cacheline.ko': 'native-hash',
                '/old/c01/variants/kdlock/mutex_cacheline.ko': 'kd-hash'})
            paths = run.binary_paths(bundle, True)
            self.assertEqual(paths[str(bundle/'binaries/daemon')], 'daemon-hash')
            self.assertEqual(paths[str(bundle/'variants/native/mutex_cacheline.ko')], 'native-hash')
            self.assertEqual(paths[str(bundle/'variants/kdlock/mutex_cacheline.ko')], 'kd-hash')
            run.save(bundle/'binaries.json', {
                'tclock-mutex/provider.ko': dict(path='/old/build/tclock-mutex/provider.ko', sha256='nested'),
                'provider.ko': dict(path='/old/build/provider.ko', sha256='top')})
            self.assertEqual(set(run.binary_paths(bundle, False).values()), {'nested', 'top'})
            run.save(bundle/'binaries.json', {
                '../escape': dict(path='/old/build/../escape', sha256='bad')})
            with self.assertRaises(ValueError):
                run.binary_paths(bundle, False)

    @staticmethod
    def record(arm, repeat, entries=1, rate=100):
        return dict(comparison_workload='c01', threads=1, comparison_arm=arm,
            arm='kdlock' if arm.endswith('-kd') else arm, repeat=repeat, cpus=[0],
            source_identity=arm, caller_shell=arm, cookie_storage=arm,
            execution_status='OK', drained=True, jit_bodies=entries,
            measurement=dict(complete=True, data_ok=True, completed=rate, wall_ns=1000000000,
                workers=[dict(cpu=0, observed_cpu=0, error=0, completed=rate)],
                peak=dict(throughput_ops_s=rate)))

    def test_mixed_jit_classes_and_missing_repeats_cannot_pass_gate(self):
        rows = [self.record(arm, repeat, entries=int(repeat != 1))
                for arm in run.ARMS for repeat in range(3)]
        summary = report.summarize(rows)
        comparisons = report.comparisons(summary)
        self.assertTrue(comparisons)
        self.assertTrue(all(row['throughput_gate'] == 'INCOMPLETE' for row in comparisons))
        self.assertTrue(all(row['p95_latency_gate'] == 'UNMEASURED' for row in comparisons))

    def test_losses_and_unknown_latency_stay_visible(self):
        rows = [self.record(arm, repeat, rate=80 if arm == 'public-kd' else 100)
                for arm in run.ARMS for repeat in range(3)]
        comparisons = report.comparisons(report.summarize(rows))
        self.assertEqual(len(comparisons), 3)
        self.assertTrue(all(row['whole_median_ratio'] == .8 for row in comparisons))
        self.assertTrue(all(row['loss_exceeds_observed_range'] for row in comparisons))
        self.assertTrue(all(row['overall_acceptance'] == 'OPEN' for row in comparisons))

    def test_undrained_or_zero_progress_records_are_excluded(self):
        row = self.record('public-kd', 0)
        self.assertTrue(report.accepted(row))
        self.assertFalse(report.accepted(dict(row, drained=False)))
        row['measurement']['workers'][0]['completed'] = 0
        self.assertFalse(report.accepted(row))

    def test_unmeasured_counters_and_mismatched_geometry_are_not_inferred(self):
        row = self.record('public-kd', 0)
        del row['jit_bodies']
        self.assertEqual(report.execution_class(row), 'UNMEASURED')
        with self.assertRaisesRegex(ValueError, 'geometry'):
            report.summarize([self.record('public-kd', 0),
                              dict(self.record('native', 0), duration_ms=1000)])


if __name__ == '__main__':
    unittest.main()
