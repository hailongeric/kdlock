"""Focused shared-MM plan, mode and prerequisite guards; VM execution only."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import linux70
import shared_platform

fixtures = linux70.common.module('shared_mm_receipt_fixtures',
                                 linux70.ROOT/'tests/unit/bench/test_mmap_aggregate.py')


class SharedLinux70(unittest.TestCase):
    def test_exact_single_round_42_point_union(self):
        identities = set()
        for mode in ('native','kd'):
            rows = linux70.plan(mode)
            self.assertEqual(len(rows),21)
            for row in rows:
                self.assertEqual(row['repeat'],0)
                self.assertEqual(row['observation'],'plain')
                self.assertEqual(row['cpus'],list(range(row['threads'])))
                self.assertEqual(row['collector_cpu'],63)
                identities.add((row['backend'],row['threads']))
        self.assertEqual(len(identities),42)
        with self.assertRaises(linux70.rt.Failure):
            linux70.plan('tclock')

    def test_exact_mode_requires_enabled_verified_identity(self):
        identity = dict(ok=True,schema=2,running_build_id='id',runtime_policy_verified=True,
                        runtime_policy=dict(mmap_mode='off',cmdline='nokaslr nopvspin kd_mmap=off',preempt='lazy'))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'.config').write_text('CONFIG_KDLOCK_MMAP=y\n')
            manifest=dict(variant='kdmm1-native',source_files={'x':'hash'},build_files={'y':'hash'})
            (root/'manifest.json').write_text(json.dumps(manifest))
            self.assertEqual(shared_platform.binding(identity,root,root,'native')['kernel_mmap_backend'],'native')
            for mode in ('kd','invalid'):
                with self.assertRaises(linux70.rt.Failure):
                    shared_platform.binding(identity,root,root,mode)
            for change in (dict(schema=1),dict(runtime_policy_verified=False),dict(running_build_id='')):
                with self.assertRaises(linux70.rt.Failure):
                    shared_platform.binding(dict(identity,**change),root,root,'native')
            (root/'.config').write_text('# CONFIG_KDLOCK_MMAP is not set\n')
            with self.assertRaises(linux70.rt.Failure):
                shared_platform.binding(identity,root,root,'native')

    def test_exact_completion_is_retained_when_peak_unavailable(self):
        for peak in (True,False):
            rows,spec=fixtures.fixture(peak)
            spec.update(backend='kd',peak_policy='optional-positive-window')
            result=linux70.validate(rows,spec)
            self.assertEqual(result['completed'],2048)
            self.assertEqual(result['execution'],'KD_LOCAL_MMAP_LOCK')
            self.assertFalse(result['delegated'])
            self.assertEqual(result['peak'] is not None,peak)

    def test_bad_identity_callback_or_timing_never_becomes_optional_peak(self):
        mutations=[lambda rows:rows[1]['workers'][0]['identity'].update(mm=999),
                   lambda rows:rows[1]['after'].update(closes=0),
                   lambda rows:rows[1].update(joined=1),
                   lambda rows:rows[1]['workers'][0].update(latency_ns=[1]),
                   lambda rows:rows[1]['samples'][1].update(completed=[999999,0])]
        for mutate in mutations:
            rows,spec=fixtures.fixture(False)
            spec.update(backend='native',peak_policy='optional-positive-window')
            mutate(rows)
            with self.assertRaises((ValueError,linux70.rt.Failure)):
                linux70.validate(rows,spec)
        rows,spec=fixtures.fixture(False);spec.update(backend='kd',peak_policy='optional-positive-window')
        for error in (ValueError('malformed progress'),TypeError('no positive full-cohort peak window')):
            with patch.object(linux70.writer,'validate',side_effect=error),self.assertRaises(type(error)):
                linux70.validate(rows,spec)

    def test_missing_or_wrong_kernel_prerequisite_cannot_be_reused(self):
        with self.assertRaises(linux70.rt.Failure):
            linux70.prerequisite_files({}, {}, 'boot')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'result.json'
            binding=dict(kernel_mmap_backend='native',build_id='current')
            base=dict(passed=True,drained=True,boot_id='boot',mode='native',kernel_binding=binding)
            variants=[dict(passed=False),dict(drained=False),dict(boot_id='another'),dict(mode='kd'),
                      dict(kernel_binding=dict(binding,build_id='old'))]
            for changes in variants:
                path.write_text(json.dumps(dict(base,**changes)))
                with self.assertRaises(linux70.rt.Failure):
                    linux70.prerequisite_files(dict.fromkeys(linux70.PREREQUISITES,path),binding,'boot')


if __name__=='__main__':
    unittest.main()
