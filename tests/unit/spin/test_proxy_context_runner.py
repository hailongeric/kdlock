"""Guest-only rejection checks for the live context probe's witness policy."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('proxy_context_live_checks',
                                             ROOT/'tests/kernel/spin/proxy_context/run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ContextWitness(unittest.TestCase):
    def row(self, bodies, completed=None, guards=0):
        return dict(bench_jit_bodies=bodies, bench_jit_completions=bodies if completed is None else completed,
                    address_guard_count=guards)

    def test_explicit_positive_and_local_matrix(self):
        self.assertEqual([(mode,expected) for _,mode,expected in runner.PHASES],
                         [(0,'delegated'),(1,'delegated'),(2,'local'),(3,'local'),
                          (4,'local'),(5,'local'),(6,'stress'),(0,'delegated')])
        self.assertEqual(runner.phase_result(self.row(7),'delegated')['returned_delegated_bodies'],7)
        self.assertEqual(runner.phase_result(self.row(0),'local')['returned_delegated_bodies'],0)

    def test_no_jit_partial_completion_native_escape_and_bad_counts_reject(self):
        for row,mode in ((self.row(0),'delegated'),(self.row(1),'local'),
                         (self.row(3,2),'delegated'),(self.row(2,3),'delegated'),
                         (self.row(1,guards=1),'delegated'),(self.row(-1),'stress')):
            with self.subTest(row=row,mode=mode),self.assertRaises(runner.probe.rt.Failure):
                runner.phase_result(row,mode)

    def test_mixed_stress_never_claims_mismatch_refusal(self):
        for bodies in (0,3):
            result=runner.phase_result(self.row(bodies),'stress')
            self.assertFalse(result['mismatch_refusal_proved'])
            self.assertEqual(result['expected'],'stress')


if __name__=='__main__':unittest.main()
