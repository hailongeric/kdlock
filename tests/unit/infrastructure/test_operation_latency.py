"""Guest-only sampler, observation integrity and fixed comparison-plan checks."""
from collections import Counter
from copy import deepcopy
import os
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'bench/mutex_api_compare'))
import latency
import latency_overlay
import latency_run
import latency_inputs
# Avoid collision with the unit driver's __main__ module.
import importlib.util
spec = importlib.util.spec_from_file_location('latency_test_scheduler',
                                             ROOT/'bench/mutex_api_compare/run.py')
scheduler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scheduler)


class LatencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='kd-operation-latency-')
        cls.binary = Path(cls.temporary.name)/'sampler'
        subprocess.run(shlex.split(os.environ.get('CC', 'gcc')) +
                       ['-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                        str(ROOT/'tests/unit/infrastructure/operation_latency_fixture.c'),
                        '-o', str(cls.binary)], check=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def sample(self, worker, done):
        result = subprocess.run([str(self.binary), str(worker), str(done)],
                                capture_output=True, text=True, check=True, timeout=30)
        first, *lines = result.stdout.splitlines()
        header, size, ioctl, selected, dropped = map(int, first.split())
        self.assertEqual((header, size, ioctl), (latency.HEADER.size, latency.SIZE, latency.READ))
        return dict(worker=worker, completed=done, selected=selected, dropped=dropped,
                    enabled=True, samples=[list(map(int, line.split())) for line in lines])

    def test_export_crc_reader_uses_original_section_word(self):
        # ET_REL uses section-relative symbol values, like the original modules.
        target = Path(self.temporary.name)/'exports.o'
        subprocess.run(shlex.split(os.environ.get('CC', 'gcc')) +
                       ['-c', str(ROOT/'tests/unit/infrastructure/operation_latency_fixture.c'),
                        '-o', str(target)], check=True, timeout=30)
        self.assertEqual(latency_inputs.export_crcs(target), {'fixture': 0x12345678})

    def test_c_sampler_matches_independent_schedule_and_clock_extents(self):
        for worker, done in ((0, 0), (0, 1), (1, 255), (2, 256), (5, 257), (62, 100000)):
            with self.subTest(worker=worker, done=done):
                row = self.sample(worker, done)
                self.assertEqual([s[0] for s in row['samples']],
                                 latency.selected_ordinals(worker, done))
                self.assertEqual(latency.validate_worker(row, worker, done, 99, 104+done*4, True),
                                 [2]*row['selected'])

    def test_capacity_overflow_is_retained_and_rejected(self):
        done = (latency.CAPACITY+1)*latency.STRIDE
        row = self.sample(3, done)
        self.assertEqual((row['selected'], row['dropped'], len(row['samples'])),
                         (latency.CAPACITY+1, 1, latency.CAPACITY))
        with self.assertRaises(ValueError):
            latency.validate_worker(row, 3, done, 99, 104+done*4, True)

    def test_rejected_chunk_is_preserved_before_source_cleanup(self):
        device = Path(self.temporary.name)/'fake-device'
        device.touch()
        evidence = Path(self.temporary.name)/'failure.json'
        header = (1, 0, 0, 256, 100, 123, latency.CAPACITY+1, 1, 0, 1, 0)

        def ioctl(fd, request, data, mutable):
            self.assertEqual(request, latency.READ)
            latency.HEADER.pack_into(data, 0, *header)

        with patch.object(latency.fcntl, 'ioctl', side_effect=ioctl):
            with self.assertRaisesRegex(ValueError, 'overflow'):
                latency.read_synthetic(device, dict(started_ns=100, workers=[{}]), True, evidence)
        saved = json.loads(evidence.read_text())
        self.assertEqual(saved['last_header'], list(header))
        self.assertEqual(latency.HEADER.unpack_from(bytes.fromhex(saved['last_chunk_hex'])), header)

    def test_changed_schedule_counts_modes_and_intervals_are_rejected(self):
        good = self.sample(0, 4096)
        mutations = [
            lambda r: r.update(worker=1), lambda r: r.update(completed=4095),
            lambda r: r.update(enabled=False), lambda r: r.update(enabled=1),
            lambda r: r.update(dropped=1), lambda r: r.update(selected=r['selected']+1),
            lambda r: r['samples'].pop(),
            lambda r: r['samples'][0].__setitem__(0, r['samples'][0][0]+1),
            lambda r: r['samples'][0].__setitem__(1, 98),
            lambda r: r['samples'][0].__setitem__(2, 1000000),
            lambda r: r['samples'][1].__setitem__(1, r['samples'][0][2]-1),
            lambda r: r['samples'][0].__setitem__(1, 1.5),
        ]
        for mutate in mutations:
            row = deepcopy(good)
            mutate(row)
            with self.assertRaises(ValueError):
                latency.validate_worker(row, 0, 4096, 99, 104+4096*4, True)

    def test_disabled_and_small_samples_are_not_sufficient(self):
        row = dict(worker=0, completed=1000, selected=0, dropped=0, enabled=False, samples=[])
        measurement = dict(workers=[dict(cpu=0, completed=1000, active_started_ns=99,
                                          kernel_finished_ns=4104)])
        summary = latency.summarize([row], measurement, False, 'fixture')
        self.assertEqual((summary['samples'], summary['p95_ns'], summary['sufficient']), (0, None, False))
        row = self.sample(0, 1000)
        summary = latency.summarize([row], measurement, True, 'fixture')
        self.assertEqual(summary['p95_ns'], 2)
        self.assertFalse(summary['sufficient'])
        self.assertFalse(summary['calibration_subtracted'])
        with self.assertRaises(ValueError):
            latency.summarize([], dict(workers=[]), True, 'fixture')

    def test_percentile_is_nearest_rank(self):
        self.assertEqual(latency.percentile(list(range(100))), 94)
        self.assertEqual(latency.percentile([10, 1, 3]), 10)
        self.assertIsNone(latency.percentile([]))

    def test_exact_fixed_plan_has_all_controls_and_rotated_modes(self):
        original = scheduler.execution_order()
        plan = latency_run.order(original)
        self.assertEqual(len(plan), 252)
        self.assertEqual(len(set(plan)), 252)
        self.assertEqual({r[:2] for r in plan}, latency_run.POINTS)
        self.assertEqual(set(Counter((g, n, arm, mode) for g, n, r, arm, mode in plan).values()), {3})
        for g, n in latency_run.POINTS:
            for repeat in range(3):
                rows = [r for r in plan if r[:3] == (g, n, repeat)]
                modes = latency_run.MODES[repeat:]+latency_run.MODES[:repeat]
                arms = [r[3] for r in original if r[:3] == (g, n, repeat)]
                self.assertEqual([(r[3], r[4]) for r in rows],
                                 [(arm, mode) for mode in modes for arm in arms])

    def test_overlay_refuses_unknown_source_or_ambiguous_anchors(self):
        for transform in (latency_overlay.synthetic, latency_overlay.api_client):
            with self.assertRaises(ValueError):
                transform(b'not the frozen original')
        for source in ('none', 'anchor anchor'):
            with self.assertRaises(ValueError):
                latency_overlay.replace_once(source, 'anchor', 'replacement')


if __name__ == '__main__':
    unittest.main()
