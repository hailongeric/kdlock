"""Archive scoring must not hide a median regression or incomplete control grid."""
import json
from pathlib import Path
import tempfile
import unittest

from owned_origin import gates


class OriginGates(unittest.TestCase):
    def fixture(self, out, counts=(3,), low_median=False,
                arms=('native', 'tclock', 'current-kd', 'numa')):
        for count in counts:
            for arm in arms:
                for repeat in range(3):
                    name = f'{count}-{arm}-{repeat}'
                    path = out/name
                    path.mkdir()
                    whole = 9 if low_median and arm == 'numa' and repeat != 1 else 10
                    row = dict(name=name, threads=count, comparison_arm=arm, repeat=repeat,
                        execution_status='OK', drained=True, measurement=dict(complete=True,
                            data_ok=True, completed=whole, wall_ns=1_000_000_000,
                            peak=dict(throughput_ops_s=10 + (repeat == 1))))
                    (path/'session.json').write_text(json.dumps(row))

    def test_best_peak_session_cannot_hide_median_regression(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            self.fixture(out, low_median=True)
            gates(out)
            result = json.loads((out/'origin-gates.json').read_text())
            comparison = result['comparisons'][0]
            self.assertEqual(comparison['over_current_kd'], dict(peak=1, whole=1, median_whole=.9))
            self.assertFalse(comparison['regression_pass'])
            self.assertFalse(comparison['native_target_pass'])
            self.assertFalse(result['full_grid_complete'])

    def test_full_grid_requires_every_round_and_control(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            self.fixture(out, (*range(1,9), *range(12,65,4)))
            gates(out)
            result = json.loads((out/'origin-gates.json').read_text())
            self.assertTrue(result['full_grid_complete'] and result['regression_pass'])
            path = out/'64-tclock-2/session.json'
            row = json.loads(path.read_text())
            row['repeat'] = 1
            path.write_text(json.dumps(row))
            gates(out)
            self.assertFalse(json.loads((out/'origin-gates.json').read_text())['full_grid_complete'])
            path.unlink()
            gates(out)
            self.assertFalse(json.loads((out/'origin-gates.json').read_text())['regression_pass'])

    def test_unsupported_arm_cannot_expand_the_grid(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            self.fixture(out, (*range(1,9), *range(12,65,4)),
                         arms=('native', 'tclock', 'current-kd', 'numa', 'unsupported'))
            gates(out)
            result = json.loads((out/'origin-gates.json').read_text())
            self.assertFalse(result['full_grid_complete'])
            self.assertFalse(result['regression_pass'])
            self.assertEqual({row['arm'] for row in result['comparisons']}, {'numa'})


if __name__ == '__main__':
    unittest.main()
