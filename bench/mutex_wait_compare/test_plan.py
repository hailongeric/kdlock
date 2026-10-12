"""Guest-only complete-grid coverage and runner placement checks."""
from pathlib import Path
import unittest

import run


class PlanTests(unittest.TestCase):
    def test_full_grid_preserves_all_payloads_and_rounds(self):
        cpus = [*range(32), *range(33, 65)]
        groups = run.commands(Path('/tmp/unused'), run.FULL_THREADS, 4096, 65, cpus, True)
        self.assertEqual(run.FULL_THREADS, [*range(1, 9), *range(12, 65, 4)])
        self.assertEqual(len(groups), 14)
        self.assertEqual(sum(g['expected'] for g in groups), 8910)
        for group in groups:
            argv = group['argv']
            self.assertEqual(argv[argv.index('--collector-cpu') + 1], '65')
            i = argv.index('--cpus') + 1
            actual = list(map(int, argv[i:i + 64])) if group['family'] == 'rwlock' else list(map(int, argv[i].split(',')))
            self.assertEqual(actual, cpus)
            if group['family'] != 'rwlock':
                self.assertEqual(argv[argv.index('--mutex-wait-mode') + 1], 'both')
        self.assertEqual(sum(g['expected'] for g in groups if g['suite'] == 'micro'), 5280)

    def test_legacy_grid_is_unchanged(self):
        groups = run.commands(Path('/tmp/unused'), [1, 8, 16, 32, 48, 60], 4096, 63)
        self.assertEqual(len(groups), 24)
        self.assertEqual(sum(g['expected'] for g in groups), 2430)


if __name__ == '__main__':
    unittest.main()
