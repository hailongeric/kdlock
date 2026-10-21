#!/usr/bin/env python3
"""Negative checks for the explicit boot-transition comparison boundary."""
import copy
import unittest
import recovery_replay as followup
import run


class RecoveryComparison(unittest.TestCase):
    def setUp(self):
        self.host = dict(cpufreq={'policy': 'fixed'}, numa={'node0': '0-31'},
            recovery_snapshot='snapshot', qemu=[dict(pid=257489, args=['qemu'],
                tasks=[dict(tid=i, comm=str(i), affinity=[i % 64]) for i in range(67)],
                numa_maps='1000 bind:0 anon=100 N0=100 kernelpagesize_kB=4')])
        self.old = {k: 'same' for k in ('cmdline', 'preemption', 'packages',
                                       'python', 'snapshot_tag', 'collector_topology')}
        self.old['boot_id'] = followup.ORIGINAL_BOOT
        self.new = dict(self.old, boot_id='new-recorded-boot')
        self.transition = dict(passed=True, original_boot_id=followup.ORIGINAL_BOOT,
            new_boot_id=self.new['boot_id'], kernel_release='6.1.159-kdclobber2',
            kernel_build_id=followup.BUILD_ID, recovery_preserved=True)

    def compare(self, host=None, env=None, transition=None):
        return followup.compare_environment(run.same_environment,
            self.transition if transition is None else transition, self.host,
            self.host if host is None else host, self.old,
            self.new if env is None else env, {'cpus': 64}, {'cpus': 64})

    def test_recorded_transition_keeps_actual_receipts(self):
        before = copy.deepcopy((self.old, self.new))
        result = self.compare()
        self.assertFalse(result['same_boot'])
        self.assertTrue(result['configuration_matches'])
        self.assertEqual((self.old, self.new), before)

    def test_every_other_guest_field_remains_exact(self):
        for key in self.new.keys() - {'boot_id'}:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'guest environment'):
                self.compare(env=dict(self.new, **{key: 'changed'}))

    def test_transition_cannot_admit_another_boot_or_kernel(self):
        for key, value in [('passed', False), ('original_boot_id', 'wrong'),
                           ('new_boot_id', 'wrong'), ('kernel_release', 'other'),
                           ('kernel_build_id', 'other'), ('recovery_preserved', False)]:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'transition'):
                self.compare(transition=dict(self.transition, **{key: value}))

    def test_extra_or_replaced_host_threads_are_rejected(self):
        for replacement in (True, False):
            host = copy.deepcopy(self.host)
            if replacement:
                host['qemu'][0]['tasks'][0]['tid'] = 999
            else:
                host['qemu'][0]['tasks'].append(dict(tid=999, comm='worker', affinity=[63]))
            with self.assertRaisesRegex(ValueError, 'thread identities'):
                self.compare(host=host)

    def test_host_configuration_and_numa_policy_remain_exact(self):
        for key in ('cpufreq', 'numa', 'recovery_snapshot'):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'host configuration'):
                self.compare(host=dict(self.host, **{key: 'changed'}))
        host = copy.deepcopy(self.host)
        host['qemu'][0]['numa_maps'] = host['qemu'][0]['numa_maps'].replace('bind:0', 'bind:1')
        with self.assertRaisesRegex(ValueError, 'memory binding'):
            self.compare(host=host)

    def test_selected_order_retains_rotations_and_three_repeats(self):
        original = run.execution_order()
        selected = [r for r in original if r[:2] in followup.POINTS]
        self.assertEqual(len(selected), 84)
        self.assertEqual(len(set(selected)), 84)
        self.assertTrue(all(r[:2] in run.REPLAY_POINTS for r in selected))


if __name__ == '__main__':
    unittest.main()
