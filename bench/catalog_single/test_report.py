"""Publication checks; execute in the designated VM."""
import json
from pathlib import Path
import tempfile
import unittest

from report import receipt_rows


class PublicationTests(unittest.TestCase):
    def test_partial_unknown_and_explicitly_ineligible_records_have_no_rate(self):
        cases = [
            ('native', {}, True),
            ('tclock', {}, True),
            ('kdlock', dict(jit_bodies=2, jit_completions=2), True),
            ('kdlock', dict(jit_bodies=0, jit_completions=0), True),
            ('kdlock', dict(jit_bodies=2, jit_completions=0), False),
            ('kdlock', {}, False),
            ('native', dict(score_eligible=False), False),
            ('kdlock', dict(jit_bodies=2, jit_completions=2, score_eligible=False), False),
            ('kdlock', dict(jit_bodies=2, jit_completions=2, drained=False), False),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan, records = [], []
            for index, (arm, extra, _) in enumerate(cases):
                name = str(index)
                plan.append(dict(name=name, threads=index + 1, arm=arm))
                record = dict(name=name, execution_status='OK', drained=True,
                              measurement=dict(complete=True, data_ok=True, completed=2000,
                                               wall_ns=2000000000,
                                               peak=dict(throughput_ops_s=2000)))
                record.update(extra)
                records.append(record)
            (root / 'plan.json').write_text(json.dumps(plan))
            (root / 'records.json').write_text(json.dumps(records))
            rows = receipt_rows(root, False)
            for row, (_, _, eligible) in zip(rows, cases):
                self.assertEqual(row['whole_mops_s'], .001 if eligible else None)
                if not eligible:
                    self.assertIsNone(row['peak_mops_s'])
            self.assertEqual(rows[4]['jit_status'], 'PARTIAL_JIT')
            self.assertEqual(rows[5]['jit_status'], 'UNMEASURED')
            self.assertEqual(rows[3]['jit_status'], 'NO_JIT')


if __name__ == '__main__':
    unittest.main()
