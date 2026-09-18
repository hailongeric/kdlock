"""The four-arm report retains failed/NO_JIT runs and all five alternating repeats."""
import json
from pathlib import Path
import tempfile
import unittest

import clobber_compare as compare
from summarize import write_json


class ClobberComparisonTests(unittest.TestCase):
    def test_plan_contains_each_arm_five_times(self):
        schedule = compare.plan([1, 16], [1, 4, 20], 5, 100000)
        self.assertEqual(len(schedule), 120)
        for index in range(0, len(schedule), 20):
            block = schedule[index:index + 20]
            arms = lambda rows: [(r['caller_abi'], r['arm']) for r in rows]
            self.assertEqual(arms(block[:4]), arms(block[4:8])[::-1])
            self.assertEqual(arms(block[:4]), arms(block[8:12]))
            self.assertEqual(len({r['name'] for r in block}), 20)

    def test_medians_exclude_failures_without_hiding_no_jit(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            schedule = compare.plan([1], [1], 5, 100)
            write_json(out/'plan.json', schedule)
            for spec in schedule:
                folder = out/spec['name']
                folder.mkdir()
                write_json(folder/'session.json', dict(spec, execution_status='OK', drained=True,
                    measurement=dict(complete=True, data_ok=True, completed=100, wall_ns=1000),
                    jit_status='NO_JIT', jit_share=0))
            broken = out/schedule[0]['name']/'session.json'
            record = json.loads(broken.read_text())
            record['drained'] = False
            record['measurement']['wall_ns'] = 1
            write_json(broken, record)
            compare.report(out)
            rows = json.loads((out/'summary.json').read_text())
            self.assertEqual(rows[0]['valid'], 4)
            self.assertEqual(rows[0]['no_jit'], 4)
            self.assertEqual(rows[0]['median_throughput_ops_s'], 100000000)
            self.assertEqual(len(json.loads((out/'records.json').read_text())), 20)


if __name__ == '__main__':
    unittest.main()
