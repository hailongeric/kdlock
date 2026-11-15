"""Explicitly authorized offline checks; no kernel build, load or timing."""
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bench/nano'))
import build
import evidence
import oracle
import run


class SpinSelection(unittest.TestCase):
    def test_build_pair_refuses_mislabel_and_unsupported_combinations(self):
        build.validate_selection(['spin'], ['native', 'kdlock'])
        for families, backends in [(['spin'], ['tclock']), (['spin'], ['native']),
                (['spin', 'mutex'], ['native', 'kdlock']), (['spin', 'spin'], ['native', 'kdlock']),
                (['rwlock'], ['native']), (['spin'], ['native', 'kdlock', 'tclock'])]:
            with self.subTest(families=families, backends=backends), self.assertRaises(ValueError):
                build.validate_selection(families, backends)

    def test_private_header_mismatch_refused(self):
        with tempfile.TemporaryDirectory() as td:
            repo, kernel = Path(td)/'repo', Path(td)/'linux'
            for base in (repo, kernel/'kernel/kdlock'):
                (base/'include').mkdir(parents=True)
                (base/'include/kd_spin_api.h').write_text('struct spin { long queue; };')
            build.validate_spin_headers(repo, kernel)
            (repo/'include/kd_spin_api.h').write_text('struct spin { long queue, epoch; };')
            with self.assertRaisesRegex(ValueError, 'ABI'):
                build.validate_spin_headers(repo, kernel)

    def test_makefile_routes_only_explicit_pair(self):
        for backend in ('native', 'kdlock', 'tclock', 'typo'):
            r = subprocess.run(['make', '--no-print-directory', '-f', str(ROOT/'workload_modules/nano/Makefile'),
                '-f', '-', 'RB_LOCK_KIND=spin', 'RB_BACKEND='+backend, 'show'],
                input='show:\n\t@echo $(ccflags-y)\n', capture_output=True, text=True)
            if backend in ('native', 'kdlock'):
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn('-DRB_SPIN', r.stdout)
                self.assertNotIn('-DRB_RWSEM', r.stdout)
                self.assertEqual('-DRB_KDLOCK' in r.stdout, backend == 'kdlock')
            else:
                self.assertNotEqual(r.returncode, 0)

    def test_direct_header_expands_real_selected_calls(self):
        # Mock dependency types only. Preprocess the actual changed direct.h;
        # absent mutex/rwsem stubs make unintended fallback fail immediately.
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            stubs={'kernel/runtime.h':'', 'kernel/task_state.h':'', 'kernel/observation.h':'',
              'include/kd_spin_api.h':'''struct kd_spinlock { struct { void *tail, *owner; } queue; };
void kd_spin_lock(struct kd_spinlock *); void kd_spin_unlock(struct kd_spinlock *);
#define KD_OPERATION_SPIN_UNLOCK 5
#define KD_LOCK_FAMILY_SPIN 2
''',
              'linux/spinlock.h':'''typedef struct { int locked; } spinlock_t;
void spin_lock(spinlock_t *); void spin_unlock(spinlock_t *); int spin_is_locked(spinlock_t *);
'''}
            for name, value in stubs.items():
                f=p/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(value)
            source='''#define __aligned(n) __attribute__((aligned(n)))
#define READ_ONCE(x) (x)
struct rw_bench_snapshot { unsigned long lock_addr, gate_addr; unsigned gate, cnts; };
'''+f'#include "{ROOT}/workload_modules/nano/direct.h"\n'+'''void exercise(void) { RB_WRITE_LOCK(); RB_WRITE_UNLOCK(); }
'''
            for backend in ('native','kdlock'):
                args=['cc','-x','c','-I',str(p),'-DRB_SPIN']+(['-DRB_KDLOCK'] if backend=='kdlock' else [])
                r=subprocess.run(args+['-fsyntax-only','-Werror=implicit-function-declaration','-'],input=source,capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stderr)
                r=subprocess.run(args+['-E','-P','-'],input=source,capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stderr)
                body=r.stdout[r.stdout.index('void exercise'):]
                prefix='kd_spin_' if backend=='kdlock' else 'spin_'
                self.assertIn(prefix+'lock(&rb_lock)',body)
                self.assertIn(prefix+'unlock(&rb_lock)',body)
                self.assertNotIn('rwsem',body)
                self.assertNotIn('mutex',body)

    def test_spin_scope_and_placement_are_explicit(self):
        for backend in ('native','kdlock'):
            run.validate_family_scope('spin','spin-pair',backend)
        for family,scope,backend in [('spin','comparison','kdlock'),('rwsem','spin-pair','kdlock'),('spin','spin-pair','tclock')]:
            with self.assertRaises(ValueError):run.validate_family_scope(family,scope,backend)
        run.validate_spin_placement(list(range(8)),8,set(range(40)))
        for cpus,collector in [(None,8),([0]*8,8),(list(range(8)),7),(list(range(8)),40)]:
            with self.assertRaises(ValueError):run.validate_spin_placement(cpus,collector,set(range(40)))

    def test_spin_build_receipt_cannot_relabel_rwsem(self):
        good=dict(families=['spin'],backends=['native','kdlock'],modules={'spin-'+b:dict(metadata=dict(nano_family='spin',nano_backend=b)) for b in ('native','kdlock')},spin_abi_headers_sha256={'a':'digest'})
        run.validate_spin_build(good)
        wrong = copy.deepcopy(good)
        wrong['modules']['spin-kdlock']['metadata']['nano_backend'] = 'native'
        with self.assertRaisesRegex(ValueError, 'metadata'):
            run.validate_spin_build(wrong)
        for key,value in [('families',['rwsem']),('modules',{'rwsem-native':{},'rwsem-kdlock':{}}),('spin_abi_headers_sha256',{})]:
            bad=copy.deepcopy(good);bad[key]=value
            with self.assertRaises(ValueError):run.validate_spin_build(bad)

    def test_paired_plan_same_counts_and_no_tclock(self):
        for backend in ('native','kdlock'):
            plan=run.measurement_plan('spin-pair','timing',backend)
            self.assertEqual([r[1] for r in plan],[1,2,4,8]*2)
            self.assertEqual([r[2] for r in plan],[False]*4+[True]*4)
            self.assertEqual({r[3] for r in plan},{'on' if backend=='kdlock' else 'unavailable'})
        with self.assertRaises(ValueError):run.measurement_plan('spin-pair','timing','tclock')

    def test_snapshot_refuses_nonspin_and_wrong_backend(self):
        spec=dict(arm='kdlock',lock_kind='spin',workload='cacheline',cachelines=1,post_work_rounds=256)
        row=dict(version=2,backend=2,workload=0,lines=1,post_work_rounds=256,active=0,cnts=0,gate=0,values=[0]*16)
        oracle.check_snapshot(row,spec)
        for key,value in [('version',1),('backend',0),('gate',1)]:
            bad=dict(row,**{key:value})
            with self.assertRaises(ValueError):oracle.check_snapshot(bad,spec)

    def test_pair_prerequisites_bind_family_boot_and_placement(self):
        rows=[dict(status='FUNCTIONAL_PASS',stage='functional',family='spin',backend=b,scope='spin-pair',
            build_receipt_sha256='build',boot_id='boot',runner_sha256='runner',
            recorder_modes=['on'] if b=='kdlock' else ['unavailable'],
            placement=dict(workers=list(range(8)),collector=8)) for b in ('native','kdlock')]
        def check(r):run.validate_prerequisites(r,'spin-pair','spin','build','boot','runner')
        check(rows)
        for key,value in [('family','rwsem'),('boot_id','old'),('runner_sha256','old'),('placement',{}),('recorder_modes',['off'])]:
            bad=copy.deepcopy(rows);bad[1][key]=value
            with self.assertRaises(ValueError):check(bad)
        with self.assertRaises(ValueError):check(rows[:1])

    def test_nonspin_unlock_cannot_be_spin_jit_evidence(self):
        records=[dict(kind=k,state=100,node=300,acquisition=400,origin=200,task=201,image=500,
                      result=0,flags=0,related=300,ip=600,cursor=605,
                      source_user=0,return_user=0,notifier=0) for k in (22,23,24,25,27,2)]
        records[2]['result']=1;records[3]['result']=5
        records[4].update(result=3,flags=1536);records[5]['flags']=96
        counts=dict(attached=1,detached=1,state=100,origin=200,errors=0,live=0,reserved=1,freed=1,
                    fast_acquired=0,fast_released=0,fast_read_acquired=0,fast_read_released=0,
                    read_acquired=0,read_released=0,entered=1,completed=1,proof=1,records=records)
        m=dict(spec=dict(lock_kind='spin'),kd_evidence=dict(workers=[counts]),
               workers=[dict(completed=1,reads=0,writes=1)],writes=1)
        compiler=SimpleNamespace(old=500,unlock=dict(site=600,length=5))
        self.assertEqual(evidence.validate_kd(m,compiler)['jit_status'],'PASS')
        for operation in (2,9,14):
            records[3]['result']=operation
            with self.assertRaisesRegex(ValueError,'non-spin'):evidence.validate_kd(m,compiler)

    def test_pristine_spin_guest_allowed_without_waiving_fault_taints(self):
        run.validate_initial_taint('spin', 0)
        run.validate_initial_taint('spin', 4096)
        for value in (1, 512, 12288):
            with self.assertRaises(ValueError):run.validate_initial_taint('spin', value)
        with self.assertRaises(ValueError):run.validate_initial_taint('mutex', 0)

    def test_raw_only_cannot_bypass_other_family_peak_rules(self):
        with self.assertRaisesRegex(ValueError, 'raw-only'):
            oracle.validate({}, dict(lock_kind='rwsem', raw_only=True))

    def test_raw_spin_timing_validates_counts_without_peak_claim(self):
        spec=dict(arm='native',lock_kind='spin',raw_only=True,write_percent=100,
                  workload='cacheline',cachelines=1,post_work_rounds=256,threads=1,
                  cpus=[0],duration_ms=1)
        before=dict(version=2,backend=0,workload=0,lines=1,post_work_rounds=256,
                    active=0,cnts=0,gate=0,values=[0]*16)
        after=copy.deepcopy(before);after['values'][0]=256
        worker=dict(cpu=0,observed_cpu=0,cpu_ns=10,completed=256,reads=0,writes=256,
                    read_errors=0,read_hits=0,checksum=oracle.post_work_checksum(256,256),
                    active_started_ns=2,kernel_finished_ns=3,finished_ns=4)
        m=dict(schema=1,complete=True,started_ns=1,finished_ns=5,wall_ns=4,
               workers=[worker],completed=256,reads=0,writes=256,before=before,after=after)
        self.assertIsNone(oracle.validate(m,spec))
        after['values'][0]=255
        with self.assertRaisesRegex(ValueError,'lost/duplicated'):
            oracle.validate(m,spec)
