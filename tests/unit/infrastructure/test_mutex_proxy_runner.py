"""Guest-only rejection checks for joined-task context receipts; no devices."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    'mutex_proxy_runner', ROOT / 'tests/kernel/mutex/proxy_pin/run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def receipt():
    return ['kd_mutex_proxy_context: role=%d phase=%d cpu=%d preempt=0 migration=0 irq=0 valid=1' %
            (role, phase, 3 if role == 4 else role)
            for role in range(5) for phase in range(3) if (role, phase) != (4, 1)]


class ContextReceipts(unittest.TestCase):
    def test_exact_single_current_epoch_metadata(self):
        good = dict(mutex_spin_budget='65536', mutex_claim_slots='1', mutex_ready_policy='epoch')
        with patch.object(runner.rt, 'command', side_effect=lambda args, log: good[args[2]]):
            self.assertEqual(runner.provider_ready_policy(Path('/provider.ko'), Path('/out')),
                             dict(mutex_spin_budget=65536, mutex_claim_slots=1, mutex_ready_policy='epoch'))
        for field, invalid in (('mutex_spin_budget', '0'), ('mutex_claim_slots', '8'),
                               ('mutex_claim_slots', ''), ('mutex_ready_policy', 'window')):
            values = dict(good, **{field: invalid})
            with self.subTest(field=field), patch.object(runner.rt, 'command',
                    side_effect=lambda args, log: values[args[2]]), self.assertRaises(runner.rt.Failure):
                runner.provider_ready_policy(Path('/provider.ko'), Path('/out'))

    def test_complete_joined_cohort(self):
        rows = runner.contexts('\n'.join(receipt()))
        self.assertEqual(len(rows), 14)
        self.assertEqual({row['role'] for row in rows}, set(range(5)))

    def test_missing_duplicate_and_wrong_identity(self):
        good = receipt()
        for rows in (good[:-1], good + good[:1],
                     good[:-1] + [good[-1].replace('role=4', 'role=5')],
                     good[:-1] + [good[-1].replace('phase=2', 'phase=1')]):
            with self.subTest(rows=rows[-1]), self.assertRaises(runner.rt.Failure):
                runner.contexts('\n'.join(rows))

    def test_unbalanced_or_unobserved_context(self):
        good = receipt()
        for old, new in (('preempt=0', 'preempt=1'), ('migration=0', 'migration=1'),
                         ('irq=0', 'irq=1'), ('valid=1', 'valid=0'), ('cpu=3', 'cpu=2')):
            with self.subTest(field=old), self.assertRaises(runner.rt.Failure):
                runner.contexts('\n'.join(good[:-1] + [good[-1].replace(old, new)]))


if __name__ == '__main__':
    unittest.main()
