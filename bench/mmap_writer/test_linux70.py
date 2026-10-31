"""Focused shared-MM plan, mode and prerequisite guards; VM execution only."""
import argparse
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
        for variant, selected in shared_platform.PROFILES.items():
            mode = selected['mode']
            identity = dict(ok=True, schema=2, running_build_id='id', runtime_policy_verified=True,
                            variant=variant, runtime_policy=dict(mmap_mode=shared_platform.MODES[mode],
                            cmdline='nokaslr nopvspin kd_mmap='+shared_platform.MODES[mode], preempt='lazy'))
            config = 'CONFIG_KDLOCK_MMAP=y\n'
            if selected['api_enabled']:
                config += 'CONFIG_KD_API_LOCKS=y\n# CONFIG_DEBUG_SPINLOCK is not set\n'
            manifest = dict(variant=variant, source_files={'x':'hash'}, build_files={'y':'hash'})
            def read(path):
                if path == selected['build']/'.config': return config
                if path == selected['bundle']/'manifest.json': return json.dumps(manifest)
                self.fail('unexpected file: '+str(path))
            with patch.object(Path,'read_text',autospec=True,side_effect=read), \
                 patch.object(shared_platform.rt,'digest',return_value='hash'):
                def bind(receipt=identity, **changes):
                    values = dict(build=selected['build'], bundle=selected['bundle'], mode=mode, variant=variant)
                    values.update(changes)
                    return shared_platform.binding(receipt, **values)
                result = bind()
                self.assertEqual(result['kernel_mmap_backend'], mode)
                self.assertEqual(result['release'], selected['release'])
                self.assertEqual(result['variant'], variant)
                self.assertFalse(result['private_backing_locks'])
                for change in (dict(schema=1), dict(runtime_policy_verified=False), dict(running_build_id=''),
                               dict(variant='other'), dict(runtime_policy=dict(mmap_mode='on' if mode=='native' else 'off',
                                    cmdline=identity['runtime_policy']['cmdline']))):
                    with self.subTest(variant=variant,change=change),self.assertRaises(linux70.rt.Failure):
                        bind(dict(identity, **change))
                for change in (dict(build=Path('/tmp/unreviewed/build')),dict(bundle=Path('/tmp/manifest-selected')),
                               dict(mode='kd' if mode=='native' else 'native'),dict(variant='future-'+mode)):
                    with self.assertRaises(linux70.rt.Failure): bind(**change)
                manifest['variant'] = 'kdmm1-'+mode if selected['api_enabled'] else 'kdscope1-'+mode
                with self.assertRaises(linux70.rt.Failure): bind()
                manifest['variant'] = variant
                valid = config
                config = valid.replace('CONFIG_KDLOCK_MMAP=y','# CONFIG_KDLOCK_MMAP is not set')
                with self.assertRaises(linux70.rt.Failure): bind()
                config = valid.replace('CONFIG_KD_API_LOCKS=y','') if selected['api_enabled'] else valid+'CONFIG_KD_API_LOCKS=y\n'
                with self.assertRaises(linux70.rt.Failure): bind()
                if selected['api_enabled']:
                    config = valid.replace('# CONFIG_DEBUG_SPINLOCK is not set','CONFIG_DEBUG_SPINLOCK=y')
                    with self.assertRaises(linux70.rt.Failure): bind()

    def test_explicit_profiles_and_legacy_defaults_select_only_canonical_paths(self):
        self.assertEqual(shared_platform.profile('native')['build'],shared_platform.BUILD)
        self.assertEqual(shared_platform.profile('native','kdscope1-native')['build'],
                         Path('/mnt/kdlock-builds/linux-7.0.0-38-kdscope1/build'))
        self.assertEqual(shared_platform.profile('native','kdscope3-native')['build'],
                         Path('/mnt/kdlock-builds2/linux-7.0.0-38-kdscope3/build'))
        parser=argparse.ArgumentParser()
        shared_platform.arguments(parser,required=False)
        for variant in (None,*shared_platform.PROFILES):
            mode='native' if variant is None else shared_platform.PROFILES[variant]['mode']
            args=parser.parse_args([] if variant is None else ['--kernel-variant',variant])
            args.mode,args.boot_id=mode,'boot'
            with patch.object(shared_platform.common.mm_platform,'guest') as gate, \
                 patch.object(Path,'read_text',return_value='nokaslr nopvspin kd_mmap='+shared_platform.MODES[mode]):
                shared_platform.guest(args)
                expected_variant=variant or 'kdmm1-native'
                family=expected_variant.rsplit('-',1)[0]
                disk,date={'kdmm1':('kdlock-builds','20261027'),
                           'kdscope1':('kdlock-builds','20261030'),
                           'kdscope3':('kdlock-builds2','20261031')}[family]
                self.assertEqual(args.kernel_source,Path('/mnt/'+disk+'/linux-7.0.0-38-'+family+'/build'))
                self.assertEqual(args.kernel_baseline,Path('/root/kdlock-kernel-baselines/linux70-'+expected_variant+'-'+date))
                self.assertEqual(args.kernel_variant,expected_variant)
                gate.assert_called_once_with('boot',release='7.0.0-38-'+family)
                args.kernel_source=Path('/tmp/alias/build')
                with self.assertRaises(linux70.rt.Failure): shared_platform.guest(args)
        args=argparse.Namespace(mode='native',boot_id='boot',kernel_variant='kdscope1-kd',
                                kernel_source=None,kernel_baseline=None)
        with patch.object(shared_platform.common.mm_platform,'guest') as gate:
            with self.assertRaises(linux70.rt.Failure): shared_platform.guest(args)
            gate.assert_not_called()
        args.kernel_variant='kdscope1-native'
        with patch.object(shared_platform.common.mm_platform,'guest'), \
             patch.object(Path,'read_text',return_value='kd_mmap=off kd_mmap=on'):
            with self.assertRaises(linux70.rt.Failure): shared_platform.guest(args)

    def test_writer_receipt_uses_shared_adapter_for_all_enabled_families(self):
        sites=linux70.common.module('shared_mm_site_tests',linux70.ROOT/'bench/mmap_writer/sites.py')
        for variant in ('kdlock1',*shared_platform.PROFILES):
            binding=dict(variant=variant)
            receipt=dict(schema=1,kernel_binding=binding,vmlinux_sha256='a'*64,callers={'site':1})
            with patch.object(sites.rt,'digest',return_value='a'*64), \
                 patch.object(sites.common,'load',return_value=receipt), \
                 patch.object(sites,'derive',return_value={'callers':{'site':1}}) as native, \
                 patch.object(sites,'derive_shared',return_value={'callers':{'site':1}}) as shared:
                sites.checked_receipt(Path('/receipt'),'a'*64,binding,Path('/vmlinux'),Path('/out'),None)
                self.assertEqual(native.call_count,int(variant=='kdlock1'))
                self.assertEqual(shared.call_count,int(variant!='kdlock1'))

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
