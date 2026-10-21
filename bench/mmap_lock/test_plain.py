"""VM-only tests for actual-MM identities and plain business oracles."""
import copy
import unittest
import tempfile
from pathlib import Path
import plain
import summary

MS=1000000


def fixture(task, mode='native'):
    spec=plain.specification(task,2,mode)
    who=dict(object=101,mm=102,mmap_lock=103,tid=100,tgid=100)
    workers=[dict(cpu=i,observed_cpu=i,pid=200+i,identity=dict(who,tid=200+i),error=0,
        completed=8192,cpu_ns=1800*MS,active_started_ns=(110+i)*MS,
        kernel_finished_ns=(2110+i)*MS,finished_ns=(2120+i)*MS,latency_ns=[]) for i in range(2)]
    m=dict(event='measurement',complete=True,data_ok=True,threads=2,joined=2,backend=0,
        workload='mmap-shared-mm' if task=='mmap' else 'fault',observation='plain',
        completed=16384,worker_cpu_ns=3600*MS,started_ns=100*MS,deadline_ns=2100*MS,
        finished_ns=2121*MS,wall_ns=2021*MS,duration_ns=2000*MS,peak_window_ns=300*MS,
        peak_settle_ns=300*MS,sample_period_ns=10*MS,progress_batch=256,
        collector_cpu=63,collector_observed_cpu=63,collector_error=0,workers=workers,
        samples=[dict(started_ns=(200+i*100)*MS,finished_ns=(200+i*100)*MS,
                      completed=[(i+1)*256]*2) for i in range(19)])
    if task=='mmap':
        before=dict(object=101,maps=0,closes=0,clones=0,vmas=0,faults=0,context_errors=0,
                    foreign_rejects=0,contended_mmaps=0,observe=0)
        after=dict(before,maps=16384,closes=16384)
    else:
        before={key:0 for key in ('backend','features','vmas','active_probe','epoch','faults','reads',
            'read_ends','writes','write_ends','downgrades','context_errors','data_errors','fallback','scopes','scope_ends')}
        after=dict(before,faults=16384,reads=16384,read_ends=16384);before['vmas']=2
    m.update(before=before,after=after)
    return [dict(event='ready',identity=who,pids=[200,201]),m],spec


class PlainTests(unittest.TestCase):
    def test_plain_workloads_and_modes(self):
        for task in ('mmap','fault'):
            for mode in plain.MODES:
                with self.subTest(task=task,mode=mode):
                    rows,spec=fixture(task,mode);saved=copy.deepcopy(rows)
                    result=plain.validate_plain(rows,spec)
                    self.assertEqual(result['p95_status'],'DEFERRED')
                    self.assertIsNone(result['completed_operation_p95_ns'])
                    self.assertEqual(result['kernel_mmap_mode'],mode)
                    self.assertEqual(rows,saved)
                    self.assertEqual(len(plain.reject_mutations(rows,spec)),9)

    def test_no_provider_or_sampled_relabelling(self):
        rows,spec=fixture('fault')
        for change in (dict(arm='kdlock'),dict(kernel_mmap_mode='tclock'),dict(observation='sampled')):
            with self.subTest(change=change),self.assertRaises(plain.rt.Failure):
                plain.validate_plain(rows,dict(spec,**change))

    def test_exact_candidate_identity(self):
        modules=['module'+str(i) for i in range(73)]
        transition=dict(passed=True,boot_id='new-boot',mode='native',release=plain.RELEASE,
                        build_id=plain.BUILD_ID,recovery_preserved=True)
        cmdline=('BOOT_IMAGE=/boot/vmlinuz-'+plain.RELEASE+
                 ' root=UUID=aa0bde06-47f6-4049-aaaf-13d052e53961 ro nokaslr nopvspin'
                 ' console=tty1 console=ttyS0 kd_mmap=off')
        args=[plain.RELEASE,'new-boot',cmdline,modules,'native',transition,modules]
        plain.identity(*args)
        for index,value in ((0,'6.1.159-kdclobber2'),(1,'old-boot'),
            (2,cmdline.replace('kd_mmap=off','kd_mmap=on')),(2,cmdline+' kd_mmap=off'),
            (2,cmdline.replace('nopvspin','')),(3,modules[:-1]),
            (5,dict(transition,recovery_preserved=False)),(5,dict(transition,build_id='wrong'))):
            altered=list(args);altered[index]=value
            with self.subTest(index=index,value=value),self.assertRaises(plain.rt.Failure):
                plain.identity(*altered)

    def test_callback_mode_and_release_mutations(self):
        rows,spec=fixture('fault')
        for field in ('backend','features','fallback','scopes','scope_ends','downgrades','data_errors','context_errors'):
            bad=copy.deepcopy(rows);bad[1]['after'][field]=1
            with self.subTest(field=field),self.assertRaises(plain.rt.Failure):
                plain.validate_plain(bad,spec)
        bad=copy.deepcopy(rows);bad[1]['workers'][0]['kernel_finished_ns']=bad[1]['started_ns']
        with self.assertRaises(ValueError):plain.validate_plain(bad,spec)

    def test_failed_preparation_cannot_qualify(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'inputs.json'
            plain.rt.write_json(path,dict(files={},build_id=plain.BUILD_ID,native_backing_only=True))
            receipt=dict(action='prepare',passed=True,drained=True,final_idle=True,basic_programs=2,
                         inputs_sha256=plain.rt.digest(path))
            plain.rt.write_json(root/'result.json',receipt);plain.prepared_inputs(path)
            for key in ('passed','drained','final_idle'):
                plain.rt.write_json(root/'result.json',dict(receipt,**{key:False}))
                with self.subTest(key=key),self.assertRaises(plain.rt.Failure):plain.prepared_inputs(path)

    def test_plain_summary_preserves_blocks_and_deferred_latency(self):
        runs=[]
        for block,(repeat,mode) in enumerate(((0,'native'),(0,'kd'),(1,'kd'),(1,'native'),(2,'native'),(2,'kd'))):
            sessions=[]
            for task in ('mmap','fault'):
                for n in (1,16):
                    sessions.append(dict(task=task,threads=n,repeat=repeat,kernel_mmap_mode=mode,
                        observation='plain',passed=True,drained=True,measurement=dict(whole_ops_s=100+block,
                        peak=dict(throughput_ops_s=110+block),latency_samples=0,completed_operation_p95_ns=None)))
            runs.append((str(block),dict(action='measure',passed=True,drained=True,final_idle=True,
                boot_id=str(block),inputs_sha256='same',kernel_mmap_mode=mode,sessions=sessions,host_endpoint='PENDING')))
        result=summary.summarize(runs)
        self.assertEqual((len(result['rows']),len(result['groups']),len(result['paired_ratios'])),(24,8,12))
        self.assertFalse(result['accepted']);self.assertFalse(result['endpoints_passed'])
        self.assertEqual(result['p95_status'],'DEFERRED')
        for change in (lambda r:r.pop(),lambda r:r[1][1].update(boot_id='0'),
                       lambda r:r[1][1].update(inputs_sha256='other')):
            bad=copy.deepcopy(runs);change(bad)
            with self.assertRaises(plain.rt.Failure):summary.summarize(bad)


if __name__=='__main__': unittest.main(verbosity=2)
