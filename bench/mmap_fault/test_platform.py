"""Focused Linux 7 MM platform rejection checks; execute only in the VM."""
import copy
import datetime
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mm_platform as platform
import timing


class Platform(unittest.TestCase):
    def setUp(self):
        self.now = datetime.datetime.now(datetime.timezone.utc)
        args = ['qemu-system-x86_64', '-smp', '64,maxcpus=64,sockets=2,cores=32,threads=1',
                '-m', '24G', '-object', 'memory-backend-ram,id=mem0,size=12G,host-nodes=0,policy=bind',
                '-object', 'memory-backend-ram,id=mem1,size=12G,host-nodes=1,policy=bind',
                '-numa', 'node,nodeid=0,cpus=0-31,memdev=mem0',
                '-numa', 'node,nodeid=1,cpus=32-63,memdev=mem1',
                '-monitor', 'unix:/tmp/qemu-monitor.sock,server,nowait']
        tasks = [dict(tid=100+cpu, start_ticks=100, comm=f'CPU {cpu}/KVM', affinity=[cpu])
                 for cpu in range(64)]
        tasks.append(dict(tid=10, start_ticks=90, comm='qemu-system-x86', affinity=[63]))
        self.host = dict(schema=2, capture_kind=platform.host_capture.KIND, host_boot_id='host-boot',
            captured_utc=self.now.isoformat(), pins_verified=True, frequency_verified=True,
            snapshot_listed=True, no_turbo='1', monitor_path='/tmp/qemu-monitor.sock',
            snapshots='ID TAG VM SIZE\n-- snapshot 12 GiB\n(qemu) ', recovery_snapshot='snapshot',
            cpufreq={f'policy{cpu}': dict(scaling_driver='intel_cpufreq',
                scaling_governor='performance', scaling_min_freq='2000000',
                scaling_max_freq='2000000', affected_cpus=str(cpu)) for cpu in range(64)},
            numa={'node0': '0-31', 'node1': '32-63'},
            qemu=[dict(pid=10, start_ticks=90, args=args, tasks=tasks,
                numa_maps='1000 bind:0 anon=100 N0=100 kernelpagesize_kB=4\n'
                          '2000 bind:1 anon=100 N1=100 kernelpagesize_kB=4')])

    def test_matching_preflight_is_not_endpoint_acceptance(self):
        row = platform.compare_host(self.host, self.host, self.now, 'snapshot', True)
        self.assertEqual(row['strict_host_gate'], 'PASS')
        self.assertEqual(row['host_endpoint'], 'PENDING')
        self.assertFalse(row['performance_accepted'])

    def test_only_explicit_exploration_allows_new_pinned_workers(self):
        current = copy.deepcopy(self.host)
        current['qemu'][0]['tasks'].append(dict(tid=2000, start_ticks=200, comm='worker', affinity=[63]))
        with self.assertRaises(ValueError):
            platform.compare_host(self.host, current, self.now, 'snapshot', True)
        row = platform.compare_host(self.host, current, self.now, 'snapshot', False)
        self.assertEqual(row['strict_host_gate'], 'FAILED')
        self.assertTrue(row['exploratory'])
        self.assertFalse(row['performance_accepted'])

    def test_exploration_records_worker_retirement_and_tid_reuse(self):
        reference=copy.deepcopy(self.host)
        original=dict(tid=2000,start_ticks=200,comm='worker',affinity=[63])
        reference['qemu'][0]['tasks'].append(original)
        row=platform.compare_host(reference,self.host,self.now,'snapshot',False)
        self.assertEqual(row['retired_workers'],[original])
        self.assertEqual(row['additional_workers'],[])
        with self.assertRaises(ValueError):
            platform.compare_host(reference,self.host,self.now,'snapshot',True)
        current=copy.deepcopy(reference)
        replacement=dict(original,start_ticks=201)
        current['qemu'][0]['tasks'][-1]=replacement
        row=platform.compare_host(reference,current,self.now,'snapshot',False)
        self.assertEqual(row['retired_workers'],[original])
        self.assertEqual(row['additional_workers'],[replacement])
        same=platform.compare_host(self.host,self.host,self.now,'snapshot',False)
        self.assertTrue(same['task_set_unchanged'])
        self.assertEqual(same['strict_host_gate'],'FAILED')
        self.assertFalse(same['performance_accepted'])

    def test_exploration_cannot_waive_identity_frequency_or_placement(self):
        changes = [lambda h: h.update(host_boot_id='other'),
                   lambda h: h.update(no_turbo='0'),
                   lambda h: h['cpufreq']['policy63'].update(scaling_max_freq='2100000'),
                   lambda h: h['qemu'][0]['tasks'][0].update(start_ticks=101),
                   lambda h: h['qemu'][0]['tasks'][0].update(affinity=[1]),
                   lambda h: h['qemu'][0].update(pid=20),
                   lambda h: h['qemu'][0].update(start_ticks=91),
                   lambda h: h['qemu'][0]['tasks'].append(
                       dict(tid=2000, start_ticks=200, comm='worker', affinity=[62])),
                   lambda h: h['qemu'][0]['tasks'].append(
                       dict(tid=2000, start_ticks=200, comm='unknown', affinity=[63])),
                   lambda h: h['qemu'][0]['tasks'].pop(),
                   lambda h: h['qemu'][0]['tasks'][-1].update(start_ticks=91),
                   lambda h: h.update(snapshot_listed=False),
                   lambda h: h.update(schema=1),
                   lambda h: h.update(captured_utc=(self.now+datetime.timedelta(seconds=1)).isoformat()),
                   lambda h: h.update(captured_utc=(self.now-datetime.timedelta(seconds=301)).isoformat())]
        for mutate in changes:
            current = copy.deepcopy(self.host)
            mutate(current)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                platform.compare_host(self.host, current, self.now, 'snapshot', False)
        with self.assertRaises(ValueError):
            platform.compare_host(self.host, self.host, self.now, 'other-snapshot', False)

    def test_host_reference_hash_cannot_be_omitted_or_relabelled(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'reference.json'
            data = json.dumps(self.host).encode()
            path.write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            self.assertEqual(platform.host_reference(path, digest), (data, self.host))
            for invalid in ('', None, '0'*64):
                with self.assertRaises(ValueError):
                    platform.host_reference(path, invalid)

    def test_private_backing_identity_cannot_accept_legacy_or_enabled_mm(self):
        identity = dict(ok=True, schema=2, running_build_id='build-id', runtime_policy_verified=True,
                        runtime_policy=dict(cmdline='nokaslr nopvspin', preempt='lazy'))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'.config').write_text('# CONFIG_KDLOCK_MMAP is not set\n')
            (root/'manifest.json').write_text('{}\n')
            binding = platform.kernel_binding(identity, root, root)
            self.assertEqual(binding['kernel_mmap_backend'], 'native')
            self.assertTrue(binding['private_backing_locks'])
            for key, value in [('ok', False), ('schema', 1), ('runtime_policy_verified', False),
                               ('running_build_id', '')]:
                with self.assertRaises(ValueError):
                    platform.kernel_binding(dict(identity, **{key: value}), root, root)
            for config in ('CONFIG_KDLOCK_MMAP=y\n', ''):
                (root/'.config').write_text(config)
                with self.assertRaises(ValueError):
                    platform.kernel_binding(identity, root, root)

    def test_prior_correctness_for_another_kernel_is_refused_before_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = dict(passed=True, drained=True, final_idle=True, split=True,
                          basic_programs=2, kernel_binding={'build_id': 'old'})
            (root/'result.json').write_text(json.dumps(result))
            with self.assertRaisesRegex(timing.rt.Failure, 'kernel identity differs'):
                timing.bundle(root, {'build_id': 'current'})

    def test_private_reuse_requires_complete_exact_binary_and_source_manifests(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            binding={'build_id':'current'}
            for backend in ('0,1','2'):
                tc=backend=='2'
                result=dict(passed=True,drained=True,final_idle=True,split=True,
                            basic_programs=2,kernel_binding=binding,backends=backend)
                (root/'result.json').write_text(json.dumps(result))
                source=root/'source/bench/mmap_fault/fixture.c'
                source.parent.mkdir(parents=True,exist_ok=True);source.write_text('source')
                prepared=root/'build/provider/kernel_module/fixture.c'
                prepared.parent.mkdir(parents=True,exist_ok=True);prepared.write_text('prepared')
                provider=('source/tclock_backend/tclock_rwlock_backend_km.ko' if tc else
                          'build/provider/kernel_module/kdlock_km.ko')
                binary_names=(provider,'source/workload_modules/mmap_fault/kd_mmap_fault.ko',
                              'source/bench/tclock_compare/allocator_guard/tc_allocator_guard.ko',
                              'client','split-client')
                for name in binary_names:
                    path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(name)
                manifests={'source-sha256.json':{'bench/mmap_fault/fixture.c':timing.rt.digest(source)},
                           'binary-sha256.json':{name:timing.rt.digest(root/name) for name in binary_names}}
                if not tc:
                    manifests['prepared-source-sha256.json']={'kernel_module/fixture.c':timing.rt.digest(prepared)}
                for name,value in manifests.items():
                    (root/name).write_text(json.dumps(value))
                if tc:(root/'prepared-source-sha256.json').unlink(missing_ok=True)
                bundle=timing.bundle(root,binding)
                self.assertTrue(all(str(root/name) in bundle['files'] for name in binary_names))
                for name,value in manifests.items():
                    path=root/name;original=path.read_text();path.unlink()
                    with self.subTest(backend=backend,missing=name), self.assertRaises(timing.rt.Failure):
                        timing.bundle(root,binding)
                    path.write_text('{}')
                    with self.subTest(backend=backend,empty=name), self.assertRaises(timing.rt.Failure):
                        timing.bundle(root,binding)
                    path.write_text(original)
                for removed in binary_names:
                    incomplete=dict(manifests['binary-sha256.json']);del incomplete[removed]
                    (root/'binary-sha256.json').write_text(json.dumps(incomplete))
                    with self.subTest(backend=backend,omitted=removed), self.assertRaises(timing.rt.Failure):
                        timing.bundle(root,binding)
                (root/'binary-sha256.json').write_text(json.dumps(manifests['binary-sha256.json']))
                (root/provider).write_text('changed executable')
                with self.assertRaisesRegex(timing.rt.Failure,'frozen input changed'):
                    timing.bundle(root,binding)

    def test_late_log_or_close_error_cannot_leave_a_pass_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            for log_error,close_error in ((OSError('kmsg overrun'),None),(None,OSError('close failed'))):
                result=dict(state='COMPLETE',passed=True,drained=True,accepted=False)
                with patch.object(timing.os,'close',side_effect=close_error):
                    with self.assertRaises(OSError):
                        timing.finish_logs(out,result,unittest.mock.Mock(side_effect=log_error),99)
                stored=json.loads((out/'result.json').read_text())
                self.assertEqual(stored['state'],'FAILED')
                self.assertFalse(stored['passed'])
                self.assertTrue(stored['drained'])


if __name__ == '__main__':
    unittest.main()
