"""Focused unchanged-harness, lifetime and actual object receipt checks (VM only)."""
import argparse
import copy
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

bench = module('mmap1_runner_tests', ROOT/'bench/mmap1/run.py')
observer = module('mmap1_observer_tests', ROOT/'tests/kernel/mmap1_identity/run.py')


def output(workers=2):
    samples = ['min:4 max:4 total:'+str(4*workers)]*6
    samples += ['measurement', 'min:5 max:5 total:'+str(5*workers),
                'min:6 max:6 total:'+str(6*workers), 'average:'+str(11*workers//2)]
    return '\n'.join(['testcase:'+bench.DESCRIPTION, 'warmup', *samples])+'\n'


def observed(model='threads'):
    session = dict(passed=True, drained=True, scored=False, instrumentation='identity-kprobe',
                   output=dict(output_valid=True, measured_samples=2), pid=100, model=model, workers=2,
                   workers_observed=[dict(tid=101+i, start_ticks=1000+i, cpus=[i]) for i in range(2)])
    records = [dict(tid=101+i, tgid=100 if model=='threads' else 101+i,
                    start_boottime_ns=(1000+i)*10_000_000+99, mm=0x1000+(0 if model=='threads' else i*0x1000),
                    lock=0x1100+(0 if model=='threads' else i*0x1000),
                    backing=0x1100+(0 if model=='threads' else i*0x1000), use_kd=1, cpu=i,
                    provider=0, route=1)
               for i in range(2)]
    snapshot = dict(abi=2, count=2, overflow=0, errors=0, stopped=1,
                    refs_acquired=2, refs_released=2, repeat_equal=True, records=records)
    return snapshot, session


class KernelProfiles(unittest.TestCase):
    def test_mmap1_selects_explicit_profiles_and_preserves_default(self):
        parser=argparse.ArgumentParser()
        bench.arguments(parser)
        base=['--mode','native','--output','/tmp/out','--host-state','/tmp/host',
              '--boot-id','boot','--host-reference','/tmp/reference','--host-reference-sha256','hash']
        for variant in ('kdlock1',*bench.mm.platform.PROFILES):
            argv=list(base)+['--kernel-variant',variant]
            if variant.endswith('-kd'): argv[1]='kd'
            args=parser.parse_args(argv)
            with patch.object(bench.platform,'guest') as gate, \
                 patch.object(Path,'read_text',return_value='kd_mmap='+('on' if args.mode=='kd' else 'off')):
                bench.guest(args)
                family=variant.rsplit('-',1)[0] if variant!='kdlock1' else variant
                if variant == 'kdscope5-log16-kd':
                    family = 'kdscope5'
                disk,date={'kdlock1':('kdlock-builds','20261027'),
                           'kdmm1':('kdlock-builds','20261027'),
                           'kdscope1':('kdlock-builds','20261030'),
                           'kdscope3':('kdlock-builds2','20261031'),
                           'kdscope4':('kdlock-builds2','20261101'),
                           'kdscope5':('kdlock-builds2','20261103')}[family]
                self.assertEqual(args.kernel_source,Path('/mnt/'+disk+'/linux-7.0.0-38-'+family+'/build'))
                self.assertEqual(args.kernel_baseline,Path('/root/kdlock-kernel-baselines/linux70-'+variant+'-'+date))
                if variant=='kdlock1': gate.assert_called_once_with('boot')
                else: gate.assert_called_once_with('boot',release='7.0.0-38-'+family)
            args.mode='kd' if args.mode=='native' else 'native'
            with patch.object(bench.platform,'guest') as gate:
                with self.assertRaises(bench.rt.Failure): bench.guest(args)
                gate.assert_not_called()
        self.assertEqual(parser.parse_args(base).kernel_variant,'kdlock1')
        args=parser.parse_args(base+['--kernel-variant','kdscope1-native',
                                    '--kernel-source','/mnt/kdlock-builds/linux-7.0.0-38-kdmm1/build'])
        with patch.object(bench.platform,'guest'),self.assertRaises(bench.rt.Failure): bench.guest(args)

    def test_mmap1_binding_forwards_selected_variant(self):
        args=argparse.Namespace(kernel_variant='kdscope1-kd',kernel_source=Path('/scope/build'),
                               kernel_baseline=Path('/scope/bundle'),mode='kd',host_state=Path('/host'),
                               boot_id='boot',host_reference=Path('/reference'),host_reference_sha256='hash')
        captured=dict(schema=2,runtime_policy={'mmap_mode':'on'})
        with patch.object(bench,'guest'),patch.object(bench.common,'host_check',return_value={}), \
             patch.object(bench.identity,'capture',return_value=captured), \
             patch.object(bench.mm.platform,'binding',return_value={'variant':'kdscope1-kd'}) as binding:
            self.assertEqual(bench.admit(args,Path('/out'))['kernel_binding']['variant'],'kdscope1-kd')
            binding.assert_called_once_with(captured,args.kernel_source,args.kernel_baseline,'kd',variant='kdscope1-kd')
            self.assertEqual(args.captured_runtime_policy,{'mmap_mode':'on'})


class Harness(unittest.TestCase):
    def test_exact_single_round_grid_and_original_cli(self):
        work = bench.plan()
        self.assertEqual(len(work), 42)
        for model in bench.MODELS:
            rows = [row for row in work if row['model']==model]
            self.assertEqual([row['workers'] for row in rows], list(range(1,9))+list(range(12,61,4)))
            self.assertTrue(all(row['round']==0 and row['nominal_seconds']==2 for row in rows))
        self.assertEqual(bench.argv('/tmp/mmap1_threads',20), ['/tmp/mmap1_threads','-t','20','-s','2','-m'])
        for count in (0,9,64,True):
            with self.assertRaises(bench.rt.Failure): bench.argv('/tmp/mmap1_threads',count)

    def test_exact_upstream_boundary_and_denominators(self):
        result = bench.parse_output(output(),2)
        self.assertEqual(len(result['warmup']),6)
        self.assertEqual([row['total'] for row in result['measurement']],[10,12])
        self.assertEqual(result['completed_pairs'],22)
        self.assertEqual(result['pairs_per_nominal_second'],11)
        self.assertEqual(result['upstream_average'],11)
        self.assertEqual(result['upstream_average_divisor'],2)
        self.assertFalse(result['elapsed_interval_seconds_observed'])
        self.assertEqual(bench.parse_output(output(1),1)['completed_pairs'],11)
        odd=output().replace('min:6 max:6 total:12','min:5 max:6 total:11').replace('average:11','average:10')
        self.assertEqual(bench.parse_output(odd,2)['pairs_per_nominal_second'],10.5)
        self.assertEqual(bench.parse_output(odd,2)['upstream_average'],10)

    def test_truncated_wrong_divisor_wrong_workload_and_invalid_counts_reject(self):
        text = output()
        mutations = [text.replace('measurement\n',''), text.replace('average:11','average:7'),
                     text.replace(bench.DESCRIPTION,'other test'), text+'average:11\n',
                     text.replace('min:5 max:5 total:10','min:5 max:5 total:9'),
                     text.replace('min:5 max:5 total:10','min:6 max:5 total:10'),
                     text.replace('min:6 max:6 total:12\n','')]
        for bad in mutations:
            with self.subTest(text=bad),self.assertRaises(bench.rt.Failure): bench.parse_output(bad,2)
        # Startup warmup may have a zero minimum, but an absent/stalled worker
        # must not become an apparently successful measured full cohort.
        self.assertEqual(bench.parse_output(text.replace('min:4 max:4 total:8',
                         'min:0 max:8 total:8',1),2)['warmup'][0]['min'],0)
        with self.assertRaises(bench.rt.Failure):
            bench.parse_output(text.replace('min:5 max:5 total:10','min:0 max:10 total:10'),2)

    def test_exact_worker_affinity_and_lifetime(self):
        rows = [dict(tid=101+i,tgid=101+i,start_ticks=12+i,ppid=100,cpus=[i],executable='/tmp/mmap1_processes')
                for i in range(2)]
        with patch.object(bench.os,'sched_getaffinity',return_value={63}):
            bench.validate_placement(rows,100,'processes',2,'/tmp/mmap1_processes')
            changes = [lambda r:r[1].update(tid=101),lambda r:r[1].update(cpus=[0]),
                       lambda r:r[1].update(cpus=[1,2]),lambda r:r[1].update(ppid=99),
                       lambda r:r[1].update(executable='/tmp/replaced'),lambda r:r[1].update(start_ticks=0)]
            for change in changes:
                bad=copy.deepcopy(rows);change(bad)
                with self.assertRaises(bench.rt.Failure):
                    bench.validate_placement(bad,100,'processes',2,'/tmp/mmap1_processes')
        with patch.object(bench.os,'sched_getaffinity',return_value={0,63}),self.assertRaises(bench.rt.Failure):
            bench.validate_placement(rows,100,'processes',2,'/tmp/mmap1_processes')

    def test_dirty_or_wrong_upstream_rejected_before_build(self):
        import argparse
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            args=argparse.Namespace(upstream=base)
            for responses in (['0'*40+'\n',''], [bench.REVISION+'\n',' M main.c\n']):
                with patch.object(bench.rt,'command',side_effect=responses) as command:
                    with self.assertRaises(bench.rt.Failure):bench.prepare(args,base)
                    self.assertEqual(command.call_count,2)
                    self.assertTrue(all(call.args[0][0]=='git' for call in command.call_args_list))


class FrozenInputs(unittest.TestCase):
    def test_binary_source_and_preparation_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);source=base/'upstream';source.mkdir()
            hashes,files,binaries,binary_hashes={},{},{},{}
            for name in bench.PINNED:
                path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture '+name)
                hashes[name]=files[str(path)]=bench.rt.digest(path)
            for model in bench.MODELS:
                path=source/('mmap1_'+model);path.write_text('ELF fixture '+model)
                binaries[model]=str(path);binary_hashes[model]=files[str(path)]=bench.rt.digest(path)
            row=dict(schema=1,upstream_revision=bench.REVISION,source_sha256=hashes,binaries=binaries,
                     binary_sha256=binary_hashes,files=files,executable_modified=False)
            inputs=base/'inputs.json';receipt=base/'result.json'
            def save(value,passed=True):
                inputs.write_text(json.dumps(value))
                receipt.write_text(json.dumps(dict(passed=passed,action='prepare',inputs_sha256=bench.rt.digest(inputs))))
            save(row)
            with patch.object(bench,'PINNED',hashes):
                self.assertEqual(bench.inputs_from(inputs)['binary_sha256'],binary_hashes)
                changed=Path(binaries['threads']);original=changed.read_bytes();changed.write_bytes(original+b' changed')
                with self.assertRaises(bench.rt.Failure):bench.inputs_from(inputs)
                changed.write_bytes(original)
                bad=copy.deepcopy(row);bad['files'].pop(str(source/'main.c'));save(bad)
                with self.assertRaises(bench.rt.Failure):bench.inputs_from(inputs)
                save(row,passed=False)
                with self.assertRaises(bench.rt.Failure):bench.inputs_from(inputs)
                save(row);inputs.write_text(json.dumps(row)+' ')
                with self.assertRaises(bench.rt.Failure):bench.inputs_from(inputs)


class ObjectObservation(unittest.TestCase):
    def test_actual_thread_and_process_sharing(self):
        for model, expected in (('threads',1),('processes',2)):
            snapshot,session=observed(model)
            result=observer.validate(snapshot,session,'kd',100)
            self.assertEqual(result['unique_mms'],expected)
            self.assertTrue(result['actual_mmap_lock_observed'])
            self.assertFalse(result['delegated_execution_proved'])

    def test_provider_selection_is_distinct_from_execution_proof(self):
        snapshot, session = observed()
        for row in snapshot['records']:
            row.update(provider=0x9000, route=2)
        result = observer.validate(snapshot, session, 'kd', 100, provider=0x9000)
        self.assertEqual(result['provider_routes'], [2])
        self.assertFalse(result['delegated_execution_proved'])
        with self.assertRaises(observer.rt.Failure):
            observer.validate(snapshot, session, 'kd', 100, provider=0x9001)
        snapshot['records'][0]['route'] = 1
        with self.assertRaises(observer.rt.Failure):
            observer.validate(snapshot, session, 'kd', 100)

    def test_task_cpu_backend_pointer_and_reference_mutations_reject(self):
        changes = [lambda s:s.update(refs_released=1),lambda s:s.update(stopped=0),
                   lambda s:s.update(overflow=1),lambda s:s.update(errors=1),
                   lambda s:s.update(repeat_equal=False),lambda s:s['records'][1].update(tid=101),
                   lambda s:s['records'][0].update(tgid=999),lambda s:s['records'][0].update(cpu=1),
                   lambda s:s['records'][0].update(use_kd=0),lambda s:s['records'][0].update(mm=0),
                   lambda s:s['records'][0].update(lock=0),lambda s:s['records'][0].update(backing=0),
                   lambda s:s['records'][0].update(start_boottime_ns=1),
                   lambda s:s['records'][0].update(lock=0x777)]
        for change in changes:
            snapshot,session=observed();change(snapshot)
            with self.subTest(change=change),self.assertRaises(observer.rt.Failure):
                observer.validate(snapshot,session,'kd',100)
        snapshot,session=observed('processes');snapshot['records'][1].update(mm=snapshot['records'][0]['mm'])
        with self.assertRaises(observer.rt.Failure):observer.validate(snapshot,session,'kd',100)
        snapshot,session=observed();session['scored']=True
        with self.assertRaises(observer.rt.Failure):observer.validate(snapshot,session,'kd',100)

    def test_receipt_replays_actual_records_instead_of_trusting_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);inputs=base/'inputs.json';binding=dict(kernel_mmap_backend='kd')
            inputs.write_text(json.dumps(dict(binary_sha256={m:'a'*64 for m in bench.MODELS})))
            receipt=dict(schema=1,passed=True,drained=True,scope='diagnostic-class-proof',boot_id='boot',
                         kernel_binding=binding,inputs_sha256=bench.rt.digest(inputs),clock_ticks=100,files={},models={})
            for model in bench.MODELS:
                snapshot,session=observed(model);session['executable_sha256']='a'*64
                session_path=base/(model+'-session.json');snapshot_path=base/(model+'-snapshot.json')
                session_path.write_text(json.dumps(session));snapshot_path.write_text(json.dumps(snapshot))
                row=observer.validate(snapshot,session,'kd',100)
                row.update(session_result=str(session_path),snapshot=str(snapshot_path),
                           session_result_sha256=bench.rt.digest(session_path),snapshot_sha256=bench.rt.digest(snapshot_path))
                receipt['models'][model]=row
                receipt['files'][str(session_path)]=row['session_result_sha256']
                receipt['files'][str(snapshot_path)]=row['snapshot_sha256']
            path=base/'result.json';path.write_text(json.dumps(receipt))
            with patch.object(bench.common,'module',return_value=observer):
                bench.diagnostic_receipt(path,inputs,binding,'boot')
                bad=copy.deepcopy(receipt);bad['models']['threads']['unique_mms']=2;path.write_text(json.dumps(bad))
                with self.assertRaises(bench.rt.Failure):bench.diagnostic_receipt(path,inputs,binding,'boot')
                path.write_text(json.dumps(receipt))
                with self.assertRaises(bench.rt.Failure):bench.diagnostic_receipt(path,inputs,binding,'other-boot')
                snapshot_path=Path(receipt['models']['threads']['snapshot'])
                changed=json.loads(snapshot_path.read_text());changed['records'][0]['use_kd']=0
                snapshot_path.write_text(json.dumps(changed))
                digest=bench.rt.digest(snapshot_path)
                receipt['files'][str(snapshot_path)]=receipt['models']['threads']['snapshot_sha256']=digest
                path.write_text(json.dumps(receipt))
                with self.assertRaises(bench.rt.Failure):bench.diagnostic_receipt(path,inputs,binding,'boot')

    def test_wire_count_bounds_unused_records_and_exact_reference_balance(self):
        snapshot,_=observed()
        words=[snapshot[name] for name in observer.HEADER]
        words += [row[name] for row in snapshot['records'] for name in observer.FIELDS]
        words += [0]*((observer.CAPACITY-2)*len(observer.FIELDS))
        encode=lambda values:struct.pack('='+str(len(values))+'Q',*values)
        self.assertEqual(observer.decode(encode(words))['records'],snapshot['records'])
        for offset,value in ((1,129),(2,1),(6,1),(len(words)-1,7)):
            bad=words.copy();bad[offset]=value
            with self.assertRaises(observer.rt.Failure):observer.decode(encode(bad))
        with self.assertRaises(observer.rt.Failure):observer.decode(encode(words)[:-8])

    def delegated_messages(self, snapshot, *, downgrade=False):
        lines = []
        stamp = 1
        for row in snapshot['records']:
            for entry in (0xA000, 0xB000):
                stages = ('enter', 'downgrade', 'read_release', 'returned') if downgrade else \
                         ('enter', 'release', 'returned')
                for stage in stages:
                    lines.append(f'6,{stamp},{stamp},-;kd_service event={stage} origin={row["tid"]} '
                        f'executor=200 identity={row["tid"] * 0x100 + entry:x} generation={entry} '
                        f'object={row["backing"]:x} depth=0 entry={entry:x} may_delegate=1')
                    stamp += 1
        return '\n'.join(lines)

    def test_actual_delegation_requires_joined_completed_roots(self):
        snapshot, session = observed()
        for row in snapshot['records']:
            row.update(provider=0x9000, route=2)
        sites = dict(mmap=[0xA000], munmap=[0xB000])
        messages = self.delegated_messages(snapshot, downgrade=True)
        checked = observer.validate_delegated(snapshot, session, 100, messages, sites, 0x9000)
        self.assertEqual(checked['completed_request_count'], 4)
        self.assertEqual(checked['downgraded_read_tails'], 4)
        self.assertTrue(checked['delegated_execution_proved'])
        self.assertFalse(checked['fresh_reader_drain_observed'])
        self.assertFalse(checked['physical_batch_length_measured'])
        self.assertTrue(all(row['request_wall_ns'] == 3000 for row in checked['completed_requests']))
        for changed in (messages.replace('executor=200', 'executor=101', 1),
                        messages.replace('object=1100', 'object=1101', 1),
                        messages.replace('event=read_release', 'event=release', 1),
                        '\n'.join(messages.splitlines()[:-1]), messages + '\n' + messages.splitlines()[0]):
            with self.assertRaises(observer.rt.Failure):
                observer.validate_delegated(snapshot, session, 100, changed, sites, 0x9000)
        with self.assertRaises(observer.rt.Failure):
            observer.validate_delegated(snapshot, session, 100, messages,
                                        dict(mmap=[0xA000], munmap=[0xC000]), 0x9000)


class ExecutionContract(unittest.TestCase):
    def expected(self, root):
        provider, daemon, preparer = root/'provider.ko', root/'daemon', root/'python'
        provider.write_text('exact module')
        daemon.write_text('exact daemon')
        preparer.write_text('exact interpreter')
        return dict(schema=1, boot_id='boot', source=dict(state=0, modules=0, writers=1),
            provider=dict(path=str(provider), sha256=bench.rt.digest(provider), note_sha256='a'*64),
            daemon=dict(pid=700, start_ticks=99, executable=str(daemon),
                        executable_sha256=bench.rt.digest(daemon), cwd=str(root), argv=[str(daemon)],
                        device_writer=dict(pid=700, start_ticks=99, fd=3, flags=os.O_RDWR|os.O_CLOEXEC,
                                           device=42, inode=77, rdev=99)),
            preparer=dict(pid=699, start_ticks=98, executable=str(preparer),
                          executable_sha256=bench.rt.digest(preparer), cwd=str(root), argv=[str(preparer)]),
            parameters=dict(rwsem_provider_active='Y', rwsem_provider_mode='active',
                            jit_timing='N', service_trace='N'),
            registry=[dict(pid=0, tgid=699, status=0, entry_abi=2, lock_kind=2,
                           entry=0x1000, code=0x2000, generation=1, requirements=896)],
            files={str(provider):bench.rt.digest(provider), str(daemon):bench.rt.digest(daemon),
                   str(preparer):bench.rt.digest(preparer)})

    def test_exact_hash_bound_contract_and_negative_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            expected=self.expected(root)
            path=root/'session.json'
            def save(value):
                path.write_text(json.dumps(value))
                return bench.execution.ExecutionSession(path,bench.rt.digest(path))
            session=save(expected)
            self.assertFalse(session.identity()['delegated_execution_proved'])
            session.expected['parameters']['service_trace']='Y'
            with self.assertRaises(bench.rt.Failure):session.verify()
            mutations=(lambda row:row['parameters'].update(rwsem_provider_active='N'),
                       lambda row:row['registry'][0].update(generation=0),
                       lambda row:row['registry'][0].update(tgid=0),
                       lambda row:row['registry'][0].update(tgid=700),
                       lambda row:row['files'].pop(row['provider']['path']),
                       lambda row:row['source'].update(writers=0),
                       lambda row:row['source'].update(writers=2),
                       lambda row:row['daemon']['device_writer'].update(flags=os.O_RDONLY),
                       lambda row:row['source'].update(frames=0))
            for mutate in mutations:
                bad=copy.deepcopy(expected);mutate(bad)
                with self.assertRaises(bench.rt.Failure):save(bad)

    def test_live_daemon_writer_and_preparer_endpoints(self):
        cases=('pass','zero_writer','extra_writer','unknown_descriptor','duplicate_descriptor',
               'changed_descriptor','preparer_changed','writer_changed_during_observation','live_frame')
        for case in cases:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
                root=Path(directory)
                expected=self.expected(root)
                note=root/'note';note.write_text('module build identity')
                expected['provider']['note_sha256']=bench.rt.digest(note)
                params=root/'parameters';params.mkdir()
                for name,value in dict(expected['parameters'],rwsem_provider_bindings='1').items():
                    (params/name).write_text(value)
                receipt=root/'session.json';receipt.write_text(json.dumps(expected))
                session=bench.execution.ExecutionSession(receipt,bench.rt.digest(receipt))
                source=dict(expected['source'],frames=0)
                if case=='zero_writer':source['writers']=0
                if case=='extra_writer':source['writers']=2
                if case=='live_frame':source['frames']=1
                writers=[copy.deepcopy(expected['daemon']['device_writer'])]
                if case=='unknown_descriptor':writers[0]['pid']=701
                if case=='duplicate_descriptor':writers.append(dict(writers[0],fd=4))
                if case=='changed_descriptor':writers[0]['flags']^=os.O_CLOEXEC
                tasks={row['pid']:{key:row[key] for key in
                       ('pid','start_ticks','executable','cwd','argv')} for row in
                       (expected['daemon'],expected['preparer'])}
                if case=='preparer_changed':tasks[699]['start_ticks']+=1
                original_read=Path.read_text
                def read(path,*args,**kwargs):
                    if str(path)=='/proc/sys/kernel/random/boot_id':return 'boot'
                    return original_read(path,*args,**kwargs)
                stack.enter_context(patch.object(bench.execution,'NOTE',note))
                stack.enter_context(patch.object(bench.execution,'PARAMETERS',params))
                stack.enter_context(patch.object(bench.execution,'module_note_sha256',return_value=bench.rt.digest(note)))
                stack.enter_context(patch.object(bench.execution,'task_identity',side_effect=lambda pid:dict(tasks[pid])))
                stack.enter_context(patch.object(bench.execution,'device_writers',return_value=writers))
                states=[source,dict(source,writers=2)] if case=='writer_changed_during_observation' else [source,source]
                stack.enter_context(patch.object(bench.rt,'status',side_effect=states))
                stack.enter_context(patch.object(bench.rt,'registry',return_value=expected['registry']))
                stack.enter_context(patch.object(bench.rt,'children',return_value=[]))
                stack.enter_context(patch.object(Path,'read_text',read))
                stack.enter_context(patch.object(Path,'iterdir',return_value=[]))
                stack.enter_context(patch.object(Path,'glob',return_value=[]))
                if case=='pass':self.assertEqual(session.verify()['source'],source)
                else:
                    with self.assertRaises(bench.rt.Failure):session.verify()

    def test_device_descriptor_observation_excludes_readonly_and_retains_other_writers(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);proc=root/'proc';proc.mkdir();device=root/'device';device.write_text('device')
            descriptors={}
            def task(pid,fd,flags):
                base=proc/str(pid);(base/'fd').mkdir(parents=True,exist_ok=True)
                (base/'fdinfo').mkdir(exist_ok=True)
                fields=['S','1',str(pid),str(pid)]+['0']*15+[str(pid+1)]
                (base/'stat').write_text(str(pid)+' (daemon) '+' '.join(fields))
                path=base/'fd'/str(fd);path.write_text('descriptor')
                (base/'fdinfo'/str(fd)).write_text('flags:\t'+format(flags,'o')+'\n')
                descriptors[str(path)]=SimpleNamespace(st_mode=stat.S_IFCHR,st_rdev=99,st_dev=42,st_ino=77)
            task(700,3,os.O_RDWR|os.O_CLOEXEC);task(700,4,os.O_RDONLY)
            original_stat=Path.stat
            def observe(path,*args,**kwargs):
                if path==device:return SimpleNamespace(st_mode=stat.S_IFCHR,st_rdev=99)
                return descriptors.get(str(path)) or original_stat(path,*args,**kwargs)
            with patch.object(bench.execution,'PROC',proc),patch.object(bench.execution,'DEVICE',device), \
                 patch.object(Path,'stat',observe):
                rows=bench.execution.device_writers()
                self.assertEqual([(row['pid'],row['fd'],row['start_ticks']) for row in rows],[(700,3,701)])
                task(701,5,os.O_WRONLY)
                self.assertEqual([(row['pid'],row['fd']) for row in bench.execution.device_writers()],[(700,3),(701,5)])
                (proc/'701/fdinfo/5').write_text('flags:\tmalformed\n')
                with self.assertRaises(ValueError):bench.execution.device_writers()

    def test_an_arbitrary_idle_waiver_is_not_a_session(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(bench,'idle') as idle:
            with self.assertRaises(bench.rt.Failure):
                bench.run_point(Path(directory)/'point',dict(model='threads',workers=2),{},lambda:None,
                                execution_session=object())
            idle.assert_not_called()


class ReachedExecutionContract(unittest.TestCase):
    def expected(self, root):
        row = ExecutionContract().expected(root)
        daemon = row.pop('daemon')
        row['files'].pop(daemon['executable'])
        row.update(schema=2, execution_mode='reached', registry=[], device_writers=[])
        row['source']['writers'] = 0
        row['parameters']['service_reached'] = 'Y'
        audit = root/'sites.json'
        audit.write_text(json.dumps(dict(records=[dict(entry=0x1000), dict(entry=0x2000)])))
        digest = bench.rt.digest(audit)
        row['files'][str(audit)] = digest
        row['writer_sites'] = dict(path=str(audit), sha256=digest, entries=[0x1000, 0x2000])
        return row

    def test_schema_two_has_no_daemon_writer_or_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);row=self.expected(root);path=root/'session.json'
            def save(value):
                path.write_text(json.dumps(value))
                return bench.execution.ExecutionSession(path,bench.rt.digest(path))
            session=save(row)
            self.assertEqual(session.identity()['execution_mode'],'reached')
            self.assertIsNone(session.identity()['daemon_pid'])
            changes=(lambda x:x.update(schema=1),lambda x:x.update(daemon={}),
                     lambda x:x['source'].update(writers=1),lambda x:x.update(registry=[dict(status=0)]),
                     lambda x:x.update(device_writers=[dict(pid=700)]),
                     lambda x:x['parameters'].update(service_reached='N'),
                     lambda x:x['writer_sites'].update(entries=[0x1000]))
            for change in changes:
                bad=copy.deepcopy(row);change(bad)
                with self.assertRaises(bench.rt.Failure):save(bad)

    def test_live_reached_contract_keeps_exact_controller_and_final_drain(self):
        for case in ('pass','writer','frame','family','unfinished','image','preparer'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
                root=Path(directory);row=self.expected(root);note=root/'note';note.write_text('module note')
                row['provider']['note_sha256']=bench.rt.digest(note)
                params=root/'parameters';params.mkdir()
                for name,value in dict(row['parameters'],rwsem_provider_bindings='1').items():(params/name).write_text(value)
                receipt=root/'session.json';receipt.write_text(json.dumps(row))
                session=bench.execution.ExecutionSession(receipt,bench.rt.digest(receipt))
                source=dict(row['source'],frames=0)
                if case=='frame':source['frames']=1
                observations=dict.fromkeys(('roots','completions','instructions','controls','primitives','memory','cache_hits','cache_misses','cache_full','unsupported','active'),0)
                if case=='family':observations['active']=1
                if case=='unfinished':observations['roots']=1
                preparer={key:row['preparer'][key] for key in ('pid','start_ticks','executable','cwd','argv')}
                if case=='preparer':preparer['start_ticks']+=1
                original=Path.read_text
                def read(path,*args,**kwargs):
                    return 'boot' if str(path)=='/proc/sys/kernel/random/boot_id' else original(path,*args,**kwargs)
                stack.enter_context(patch.object(bench.execution,'NOTE',note))
                stack.enter_context(patch.object(bench.execution,'PARAMETERS',params))
                stack.enter_context(patch.object(bench.execution,'module_note_sha256',return_value=bench.rt.digest(note)))
                stack.enter_context(patch.object(bench.execution,'task_identity',return_value=preparer))
                stack.enter_context(patch.object(bench.execution,'device_writers',return_value=[dict(pid=700)] if case=='writer' else []))
                stack.enter_context(patch.object(bench.execution,'reached_observations',return_value=observations))
                stack.enter_context(patch.object(bench.rt,'status',return_value=source))
                stack.enter_context(patch.object(bench.rt,'registry',return_value=[dict(status=0)] if case=='image' else []))
                stack.enter_context(patch.object(Path,'read_text',read))
                stack.enter_context(patch.object(Path,'iterdir',return_value=[]))
                stack.enter_context(patch.object(Path,'glob',return_value=[]))
                if case=='pass':
                    self.assertEqual(session.verify()['source'],source)
                    source['modules']=2
                    self.assertEqual(session.verify()['source']['modules'],2)
                    source['modules']=1
                    with self.assertRaises(bench.rt.Failure):session.verify()
                else:
                    with self.assertRaises(bench.rt.Failure):session.verify()


class LaunchLifetime(unittest.TestCase):
    def test_timeout_or_survivor_never_becomes_drain_or_cleanup(self):
        for behavior in ('pass','timeout','orphan','kernel_fault'):
            with self.subTest(behavior=behavior),tempfile.TemporaryDirectory() as directory:
                out=Path(directory)/'point'
                class Child:
                    pid=700
                    def poll(self):return None
                    def wait(self,timeout):
                        if behavior=='timeout':raise subprocess.TimeoutExpired('upstream',timeout)
                        return 0
                    def kill(self):raise AssertionError('forced kill forbidden')
                    def terminate(self):raise AssertionError('termination forbidden')
                def spawn(command,**kwargs):
                    self.assertEqual(command[-3:],['-s','2','-m'])
                    self.assertNotIn('LD_PRELOAD',kwargs['env'])
                    kwargs['stdout'].write(output());kwargs['stdout'].flush()
                    return Child()
                rows=[dict(tid=701,start_ticks=99),dict(tid=702,start_ticks=100)]
                reads=[b'BUG: fixture\n',BlockingIOError()] if behavior=='kernel_fault' else [BlockingIOError()]
                guards=[patch.object(bench,'idle'),patch.object(bench,'capture_workers',return_value=rows),
                        patch.object(bench,'task_gone',return_value=behavior!='orphan'),
                        patch.object(bench.os,'sched_getaffinity',return_value={63}),
                        patch.object(bench.os,'sched_setaffinity'),patch.object(bench.os,'open',return_value=77),
                        patch.object(bench.os,'lseek'),patch.object(bench.os,'close'),
                        patch.object(bench.os,'read',side_effect=reads),
                        patch.object(bench.subprocess,'Popen',side_effect=spawn)]
                for guard in guards:guard.start()
                try:
                    inputs=dict(binaries={'threads':'/tmp/mmap1_threads'},binary_sha256={'threads':'a'*64})
                    action=lambda:bench.run_point(out,dict(model='threads',workers=2,round=0,nominal_seconds=2),
                                                  inputs,lambda:None)
                    if behavior=='pass':self.assertTrue(action()['drained'])
                    else:
                        with self.assertRaises(bench.rt.Failure):action()
                    result=json.loads((out/'result.json').read_text())
                    self.assertEqual(result['passed'],behavior=='pass')
                    self.assertEqual(result['drained'],behavior in ('pass','kernel_fault'))
                    self.assertEqual(json.loads((out/'command.json').read_text())['pid'],700)
                finally:
                    for guard in reversed(guards):guard.stop()


if __name__=='__main__':unittest.main()
