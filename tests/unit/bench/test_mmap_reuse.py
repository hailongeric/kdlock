"""Offline compatibility failures, using isolated source and build fixtures."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'bench/mmap_lock'))
import paired
import prepare
import reuse


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value) if not isinstance(value,str) else value)
    return path


class Reuse(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.root=self.base/'current';self.prior=self.base/'prior';self.build=self.base/'build'
        self.rules_path=self.root/'bench/mmap_lock/reuse_native_v1.json'
        names=reuse.CHANGED | {'bench/mmap_writer/control.h','bench/mmap_writer/timed_client.c',
                             'workload_modules/mmap_writer/mmap_writer_uapi.h'}
        self.rules=dict(sources={},control_sources={},target_sources={})
        for name in names:
            old=write(self.prior/name,'original '+name)
            self.rules['sources'][name]=paired.rt.digest(old)
            self.rules['control_sources'][name]=paired.rt.digest(old)
            current=write(self.root/name,('new ' if name in reuse.CHANGED else 'original ')+name)
            if name in reuse.CHANGED:self.rules['target_sources'][name]=paired.rt.digest(current)
        for name in reuse.ADDED:
            self.rules['target_sources'][name]=paired.rt.digest(write(self.root/name,'new '+name))
        write(self.rules_path,self.rules)
        for module,key,value in ((reuse,'RULES',self.rules_path),(paired,'ROOT',self.root),(prepare,'ROOT',self.root)):
            guard=patch.object(module,key,value);guard.start();self.addCleanup(guard.stop)
        guard=patch.object(paired,'control_files',side_effect=self.control_files)
        guard.start();self.addCleanup(guard.stop)
        guard=patch.object(paired.rt,'command',side_effect=AssertionError('live action forbidden'))
        guard.start();self.addCleanup(guard.stop)

    def control_files(self):
        return {str(p):paired.rt.digest(p) for p in self.root.rglob('*') if p.is_file()}

    def make_build(self):
        files={str(reuse.ORIGIN/name):h for name,h in self.rules['sources'].items()}
        binaries={}
        for name in ('payload','timed','fixed'):
            p=write(self.base/'old-build'/name,'old '+name)
            files[str(p)]=paired.rt.digest(p);binaries[name]=str(p)
        old=dict(passed=True,built_only=True,modules_loaded=False,profile=paired.PROFILE,files=files,binaries=binaries)
        old_path=write(self.base/'old-build/result.json',old)
        self.rules['prepared_sha256']=paired.rt.digest(old_path)
        write(self.root/'bench/mmap_lock/kdmm31.json',paired.PROFILE)
        manifest=write(self.base/'manifest.json',dict(files={name:paired.rt.digest(self.root/name)
                       for name in self.rules['sources']}))
        self.build.mkdir()
        a=argparse.Namespace(reuse_payload=old_path,source_manifest=manifest,fixed_client_only=True,prior_source=self.prior)
        def compiler(argv,output,**kwargs):
            self.assertEqual(argv[0],'gcc')
            write(Path(argv[-1]),'fixture new fixed binary')
        with patch.object(prepare.rt,'command',side_effect=compiler), \
             patch.object(prepare,'__file__',str(self.root/'bench/mmap_lock/prepare.py')):
            target=prepare.rebuild_client(a,self.build)
        target_path=write(self.build/'result.json',target)
        return paired.bind(old_path),target_path

    def test_source_maps_require_reviewed_old_and_new_bytes(self):
        old,target=reuse.source_maps(self.rules,self.prior)
        self.assertEqual(len(old),len(self.rules['sources']))
        self.assertEqual(target['bench/mmap_writer/client.c'],self.rules['target_sources']['bench/mmap_writer/client.c'])
        for path in (self.root/'bench/mmap_writer/client.c', self.prior/'bench/mmap_writer/client.c',
                     self.root/'bench/mmap_writer/timed_client.c'):
            original=path.read_bytes();path.write_bytes(original+b' changed')
            with self.assertRaises(paired.rt.Failure):reuse.source_maps(self.rules,self.prior)
            path.write_bytes(original)

    def test_source_maps_reject_extra_or_unreviewed_files(self):
        write(self.root/'bench/mmap_lock/unreviewed.py','extra')
        with self.assertRaises(paired.rt.Failure):reuse.source_maps(self.rules,self.prior)

    def test_fixed_only_preparation_keeps_original_sources_and_other_binaries(self):
        old_ref,target_path=self.make_build()
        target=reuse.preparation(old_ref,target_path,self.rules,self.prior)
        old=paired.load_bound(old_ref)
        for name in ('timed','payload'):
            self.assertEqual(target['binaries'][name],old['binaries'][name])
        self.assertTrue(all(not Path(n).is_relative_to(reuse.ORIGIN) for n in target['files']))
        self.assertEqual(target['fixed_eligibility_policy'],paired.eligibility.FUNCTIONAL)

    def test_preparation_rejects_changed_binary_or_unbound_metadata(self):
        old_ref,target_path=self.make_build()
        original=paired.common.load(target_path)
        edits=[lambda r:r['binaries'].__setitem__('timed',r['binaries']['fixed']),
               lambda r:r.__setitem__('fixed_eligibility_policy','unknown'),
               lambda r:r.__setitem__('driver_sha256','0'*64),
               lambda r:r.__setitem__('source_manifest_sha256','0'*64),
               lambda r:r['reused_from'].__setitem__('sha256','0'*64),
               lambda r:r['files'].pop(str(self.prior/'bench/mmap_writer/client.c'))]
        for edit in edits:
            bad=copy.deepcopy(original);edit(bad);write(target_path,bad)
            with self.subTest(edit=edit),self.assertRaises((paired.rt.Failure,KeyError)):
                reuse.preparation(old_ref,target_path,self.rules,self.prior)
        write(target_path,original)
        Path(original['binaries']['payload']).write_text('changed payload')
        with self.assertRaises(paired.rt.Failure):reuse.preparation(old_ref,target_path,self.rules,self.prior)

    def test_import_rejects_arbitrary_failed_receipt_before_replay(self):
        self.rules['validation_sha256']='0'*64;write(self.rules_path,self.rules)
        prior=write(self.base/'failed.json',dict(passed=False))
        with patch.object(paired,'validation_receipt') as replay:
            with self.assertRaises(paired.rt.Failure):reuse.create(prior,self.base/'target.json',self.prior)
            replay.assert_not_called()

    def test_compatibility_replay_recomputes_and_compares_every_field(self):
        original=write(self.base/'original.json',{})
        target=write(self.base/'prepared.json',{})
        importer=write(self.base/'importer.py',Path(reuse.__file__).read_text())
        row=dict(prepared=paired.bind(target),compatibility=dict(original=paired.bind(original),
            rules=paired.bind(self.rules_path),importer=paired.bind(importer),prior_source=str(self.prior)),
            writer_observation='observed')
        path=write(self.base/'compatibility.json',row)
        current=copy.deepcopy(row)
        current['compatibility']['importer']=paired.bind(Path(reuse.__file__))
        with patch.object(reuse,'create',side_effect=lambda *args:copy.deepcopy(current)):
            self.assertEqual(reuse.replay(path,'native',paired.bind(target),paired.SCALING_PLAN),row)
            bad=copy.deepcopy(row);bad['writer_observation']='inconclusive';write(path,bad)
            with self.assertRaises(paired.rt.Failure):reuse.replay(path,'native',paired.bind(target),paired.SCALING_PLAN)
            write(path,row)
            with self.assertRaises(paired.rt.Failure):reuse.replay(path,'kd',paired.bind(target),paired.SCALING_PLAN)
            original.write_text('{"modified":true}')
            with self.assertRaises(paired.rt.Failure):reuse.replay(path,'native',paired.bind(target),paired.SCALING_PLAN)

    def test_new_boot_readiness_preserves_environment_topology_and_policies(self):
        original=dict(boot_id='old',environment=dict(boot_id='old',cmdline='old native',packages={'fixture':'1'}),
            topology={'fixture':[0,1]},window_roles={'fixture':'roles'},prior_api=['native','kd'])
        path=write(self.base/'ready.json',original)
        row=dict(prepared={'fixture':'prepared'},compatibility={'original_ready':paired.bind(path)})
        for mode in ('native','kd'):
            ready=dict(original,passed=True,boot_id='new',mode=mode,plan=paired.SCALING_PLAN,
                prepared=row['prepared'],eligibility_policy=paired.eligibility.FUNCTIONAL,
                measurement_policy=paired.window.POLICY,admission_policy=paired.window.WORKER_ADMISSION,
                kernel_identity=dict(running_build_id=paired.PROFILE['build_id']),
                environment=dict(original['environment'],boot_id='new',cmdline=' '.join(paired.PROFILE['cmdline_common']+
                                 ['kd_mmap='+paired.PROFILE['modes'][mode]])))
            reuse.match_ready(row,ready)
            edits=[lambda r:r.__setitem__('boot_id','old'),lambda r:r.__setitem__('topology',{}),
                   lambda r:r['environment']['packages'].__setitem__('fixture','2'),
                   lambda r:r['environment'].__setitem__('cmdline','unbound command line'),
                   lambda r:r.__setitem__('eligibility_policy',paired.eligibility.STRICT),
                   lambda r:r.__setitem__('window_roles',{}),lambda r:r.__setitem__('prior_api',[])]
            for edit in edits:
                bad=copy.deepcopy(ready);edit(bad)
                with self.assertRaises(paired.rt.Failure):reuse.match_ready(row,bad)


if __name__=='__main__':unittest.main()
