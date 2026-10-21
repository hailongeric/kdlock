"""VM-only checks for serial campaign ordering and unchanged endpoint gates."""
import copy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import serial


class SerialTests(unittest.TestCase):
    def test_post_load_fault_prevents_client(self):
        trace=[]
        def command(args,*unused,**kw):
            trace.append(args[0]);return 'BUG: fault' if trace==['dmesg','insmod','dmesg'] else ''
        with tempfile.TemporaryDirectory() as directory, patch.object(serial.plain.rt,'command',side_effect=command):
            with self.assertRaises(serial.plain.rt.Failure):
                serial.load_and_run(Path(directory),dict(binaries=dict(writer_payload='payload',writer_plain='client')),
                    dict(task='mmap',threads=1,module='payload'))
        self.assertEqual(trace,['dmesg','insmod','dmesg'])

    def test_client_timeout_retains_loaded_state(self):
        trace=[]
        def command(args,*unused,**kw):
            trace.append(args[0])
            if args[0]=='client':raise serial.plain.rt.Failure('TIMEOUT','retained',unsafe=True)
            return ''
        with tempfile.TemporaryDirectory() as directory, patch.object(serial.plain.rt,'command',side_effect=command), \
                patch.object(serial,'health',return_value=serial.expected_health('mmap',0)):
            with self.assertRaises(serial.plain.rt.Failure) as failure:
                serial.load_and_run(Path(directory),dict(binaries=dict(writer_payload='payload',writer_plain='client')),
                    dict(task='mmap',threads=1,module='payload'))
            self.assertTrue(failure.exception.unsafe)
        self.assertEqual(trace,['dmesg','insmod','dmesg','client'])

    def test_pre_unload_failure_never_removes_payload(self):
        for fault,health in ((True,serial.expected_health('mmap',1)),(False,'files=1')):
            trace=[]
            def command(args,*unused,**kw):trace.append(args[0]);return 'WARNING: fault' if fault else ''
            with tempfile.TemporaryDirectory() as directory, patch.object(serial.plain.rt,'command',side_effect=command), \
                    patch.object(serial,'health',return_value=health),patch.object(serial.plain,'validate_plain',return_value={}):
                out=Path(directory);(out/'client.log').write_text('{}\n')
                with self.assertRaises(serial.plain.rt.Failure):
                    serial.validate_and_unload(out,dict(task='mmap',module='payload',spec={}))
            self.assertEqual(trace,['dmesg'])

    def test_normal_cleanup_preserves_fault_check_order(self):
        trace=[]
        def command(args,*unused,**kw):trace.append(args[0]);return ''
        with tempfile.TemporaryDirectory() as directory, patch.object(serial.plain.rt,'command',side_effect=command), \
                patch.object(serial,'health',return_value=serial.expected_health('mmap',1)), \
                patch.object(serial.plain,'validate_plain',return_value=dict(valid=True)):
            out=Path(directory);(out/'client.log').write_text('{}\n')
            measured,_=serial.validate_and_unload(out,dict(task='mmap',module='payload',spec={}))
            self.assertTrue(measured['valid'])
        self.assertEqual(trace,['dmesg','rmmod','dmesg'])

    def test_distinct_ordered_boots(self):
        self.assertEqual(serial.block_binding(0,0,'native','a',None,'h'),[])
        previous=dict(passed=True,drained=True,final_idle=True,block=0,sessions=[{}]*4,
                      inputs_sha256='h',boot_ids=['a'])
        self.assertEqual(serial.block_binding(1,0,'kd','b',previous,'h'),['a'])
        for args in ((1,0,'native','b',previous,'h'),(1,0,'kd','a',previous,'h'),
                     (1,0,'kd','b',None,'h'),(1,0,'kd','b',dict(previous,drained=False),'h'),
                     (1,0,'kd','b',previous,'other')):
            with self.assertRaises(serial.plain.rt.Failure):serial.block_binding(*args)

    def test_cases_require_exact_predecessor(self):
        ready=dict(repeat=0,boot_id='a',inputs_sha256='h')
        serial.case_binding(0,'mmap',1,0,ready,None)
        previous=dict(passed=True,drained=True,final_idle=True,case=0,boot_id='a',inputs_sha256='h')
        serial.case_binding(1,'mmap',16,0,ready,previous)
        for args in ((1,'fault',16,0,ready,previous),(1,'mmap',16,1,ready,previous),
                     (1,'mmap',16,0,ready,None),(2,'fault',1,0,ready,previous),
                     (1,'mmap',16,0,ready,dict(previous,drained=False))):
            with self.assertRaises(serial.plain.rt.Failure):serial.case_binding(*args)

    def test_full_host_gate_rejects_identity_and_policy_changes(self):
        base=serial.plain.common.ORIGINAL
        host=serial.plain.common.load(base/'host-state.json')
        env=serial.plain.common.load(base/'environment.json')
        topology=serial.plain.common.load(base/'topology.json')
        serial.endpoint_check(host,env,topology)
        def changed_tid(h):h['qemu'][0]['tasks'][0]['tid']+=1
        def changed_args(h):h['qemu'][0]['args'].append('different')
        def changed_policy(h):next(iter(h['cpufreq'].values()))['scaling_governor']='different'
        for mutate in (changed_tid,changed_args,changed_policy,
                       lambda h:h.update(pins_verified=False),lambda h:h.update(snapshot_listed=False)):
            bad=copy.deepcopy(host);mutate(bad)
            with self.assertRaises((serial.plain.rt.Failure,ValueError)):serial.endpoint_check(bad,env,topology)

    def test_bound_receipt_substitution(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'receipt.json';path.write_text('{"passed":true}')
            binding=serial.binding(path);self.assertTrue(serial.verify_binding(binding)['passed'])
            path.write_text('{"passed":false}')
            with self.assertRaises(serial.plain.rt.Failure):serial.verify_binding(binding)

    def test_kernel_fault_stops_before_following_action(self):
        with patch.object(serial.plain.rt,'command',return_value='WARNING: probe fault'):
            with self.assertRaises(serial.plain.rt.Failure):serial.fault_check(Path('/unused'),'before-unload')

    def test_finish_cannot_replace_existing_result(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);path=out/'result.json';path.write_text('retained')
            with self.assertRaises(serial.plain.rt.Failure):serial.finish(SimpleNamespace(output=out))
            self.assertEqual(path.read_text(),'retained')


if __name__=='__main__':unittest.main(verbosity=2)
