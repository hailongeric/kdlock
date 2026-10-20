"""VM-only checks for explicit diagnostic selection without input changes."""
from collections import Counter
import unittest

import run
from profile_replay import profile_order, profile_spec


class ProfilePlanTests(unittest.TestCase):
    def test_every_original_point_retains_all_controls_and_original_rotation(self):
        original = run.replay_order()
        selected = profile_order(original)
        self.assertEqual(selected, [row for row in original if row[2] == 0])
        self.assertEqual(len(selected), 40)
        self.assertEqual(len(set(selected)), 40)
        self.assertEqual({row[:2] for row in selected}, run.REPLAY_POINTS)
        self.assertEqual(set(Counter(row[:2] for row in selected).values()), {4})
        for start in range(0, 40, 4):
            self.assertEqual({row[3] for row in selected[start:start+4]}, set(run.ARMS))

    def test_profiling_preserves_payload_affinity_admission_and_drain_requirements(self):
        original = dict(name='example', source_identity='frozen', threads=4, cpus=[0, 1, 2, 3],
            collector_cpu=63, duration_ms=2000, warmup=48000, warmup_ms=1000,
            require_jit=True, caller_shell='mutex_public_direct', spin_prefetch=2,
            delegation_batch_limit=1024, peak_window_ms=300, sample_ms=10)
        profiled = profile_spec(original, 'perf-hash')
        self.assertEqual({k: profiled[k] for k in original}, original)
        self.assertNotIn('diagnostic', original)
        self.assertTrue(profiled['diagnostic'])
        self.assertTrue(profiled['perf_record'])
        self.assertFalse(profiled['score_eligible'])
        self.assertFalse(profiled['pmu'])
        self.assertEqual(profiled['perf_binary_sha256'], 'perf-hash')


if __name__ == '__main__':
    unittest.main()
