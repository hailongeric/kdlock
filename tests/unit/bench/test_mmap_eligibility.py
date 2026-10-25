"""Offline eligibility oracles; kernel commands are mocked, C runs in the VM."""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'bench/mmap_lock'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import eligibility as policy
import paired
import report
import reuse
import test_mmap_scaling as scaling


def fixed_rows(mode='kd', observation='observed', functional=True):
    sites = paired.common.load(paired.SITES)
    chain = sites['chains'][mode]
    identity = dict(event='identity', mm=100, mmap_lock=200, object=300, tid=1, tgid=1)
    before = dict(event='before', object=300, faults=0, context_errors=0, maps=0,
                  clones=0, closes=0, vmas=0, observe=1, foreign_rejects=0, contended_mmaps=0)
    complete = dict(event='complete', mode='cycle', passed=True, joined=16, completed=80000,
        workers=[dict(cpu=i, tid=i+2, tgid=1, mm=100, mmap_lock=200, object=300,
                      completed=5000, errors=0) for i in range(16)])
    if functional:
        complete.update(eligibility_policy=policy.FUNCTIONAL, functional_complete=True,
                        writer_observation=observation)
    rows = [identity, before]
    if observation == 'observed':
        frames = [(chain['waiter'], chain['wait_returns'][0])]
        if chain['waiter'] != sites['adapter']:
            frames.append((sites['adapter'], chain['adapter_return']))
        frames.append(('vm_mmap_pgoff', sites['sites']['vm_mmap_pgoff']['return_offset']))
        rows.append(dict(event='writer_stack', proof='EXACT_MMAP_WRITER_CHAIN', tid=2,
            mm=100, mmap_lock=200, acquire=sites['adapter'], caller='vm_mmap_pgoff',
            waiter=chain['waiter'], wait_return_offset=chain['wait_returns'][0],
            adapter_return_offset=chain['adapter_return'], return_offset=frames[-1][1],
            state_before='D', state_after='D', wchan_before=chain['waiter'], wchan_after=chain['waiter'],
            schedstat_before='10 20 30\n', schedstat_after='10 20 30\n',
            raw_stack=''.join(f'[<0>] {name}+0x{offset:x}/0x400\n' for name, offset in frames)))
    rows += [dict(before, event='after', maps=80000, closes=80000, contended_mmaps=70000), complete]
    return rows


def validate(rows, mode='kd', selected=policy.FUNCTIONAL):
    with patch.object(paired.mapping, 'SITES', paired.common.load(paired.SITES)):
        return paired.mapping.validate(rows, 'cycle', 16, 5000, mode, selected)


class Eligibility(unittest.TestCase):
    def test_strict_default_and_explicit_selection(self):
        self.assertEqual(policy.policy({}), policy.STRICT)
        self.assertEqual(policy.fields(policy.STRICT), {})
        for value in (None, '', 'unknown'):
            with self.assertRaises(ValueError):
                policy.policy(dict(eligibility_policy=value))
        for name in ('functional_complete', 'writer_observation', 'writer_observations', 'compatibility'):
            with self.assertRaises(ValueError):
                policy.policy({name: True})

    def test_same_functional_rule_for_both_backends(self):
        for mode in ('native', 'kd'):
            for observation in ('observed', 'inconclusive'):
                with self.subTest(mode=mode, observation=observation):
                    result = validate(fixed_rows(mode, observation), mode)
                    self.assertTrue(result['passed'])
                    self.assertEqual(result['writer_observation'], observation)

    def test_strict_missing_witness_fails_and_positive_proof_unchanged(self):
        for mode in ('native', 'kd'):
            validate(fixed_rows(mode, functional=False), mode, policy.STRICT)
            with self.assertRaises(paired.rt.Failure):
                validate(fixed_rows(mode, 'inconclusive', False), mode, policy.STRICT)
            with patch.object(paired.mapping, 'SITES', paired.common.load(paired.SITES)):
                self.assertEqual(paired.mapping.reject_mutations(fixed_rows(mode), mode, policy.FUNCTIONAL),
                                 paired.PROOF_MUTATIONS)

    def test_no_policy_inference_or_malformed_witness_downgrade(self):
        edits = [lambda r: r[-1].pop('eligibility_policy'),
                 lambda r: r[-1].pop('functional_complete'),
                 lambda r: r[-1].__setitem__('passed', 'true'),
                 lambda r: r[-1].__setitem__('writer_observation', 'inconclusive'),
                 lambda r: r.pop(2),
                 lambda r: r[2].__setitem__('raw_stack', 'malformed'),
                 lambda r: r[2].__setitem__('state_after', 'R')]
        for edit in edits:
            bad = fixed_rows(); edit(bad)
            with self.subTest(edit=edit), self.assertRaises((ValueError, paired.rt.Failure)):
                validate(bad)

    def test_inconclusive_requires_every_functional_invariant(self):
        edits = [lambda r: r[-1].__setitem__('joined', 15),
                 lambda r: r[-1].__setitem__('completed', 79999),
                 lambda r: r[-1]['workers'][0].__setitem__('errors', 1),
                 lambda r: r[-1]['workers'][0].__setitem__('mm', 999),
                 lambda r: r[-1]['workers'][0].__setitem__('cpu', 63),
                 lambda r: r[-1]['workers'][0].__setitem__('tid', 3),
                 lambda r: r[-2].__setitem__('closes', 79999),
                 lambda r: r[-2].__setitem__('faults', 1),
                 lambda r: r[-2].__setitem__('context_errors', 1),
                 lambda r: r[-2].__setitem__('foreign_rejects', 1),
                 lambda r: r[-2].__setitem__('contended_mmaps', 0)]
        for edit in edits:
            bad = fixed_rows(observation='inconclusive'); edit(bad)
            with self.subTest(edit=edit), self.assertRaises(paired.rt.Failure):
                validate(bad)

    def test_nonzero_client_exit_is_never_reinterpreted(self):
        inputs = dict(binaries=dict(payload='fixture.ko', fixed='fixture-fixed'))
        with patch.object(paired.rt, 'command', side_effect=['', paired.rt.Failure('COMMAND', 'exit 1')]) as cmd, \
             patch.object(paired, 'fault_check'), patch.object(paired, 'health'):
            with self.assertRaises(paired.rt.Failure):
                paired.fixed(inputs, Path('/fixture'), 'kd', policy.FUNCTIONAL)
            self.assertEqual(cmd.call_count, 2)
            self.assertEqual(cmd.call_args.args[0][-2:], ['--eligibility-policy', policy.FUNCTIONAL])

    def test_fixed_runner_preserves_drain_and_fault_checks(self):
        inputs = dict(binaries=dict(payload='fixture.ko', fixed='fixture-fixed'))
        for failure in ('none', 'health', 'fault'):
            def command(argv, *args, **kwargs):
                return '\n'.join(map(json.dumps, fixed_rows(observation='inconclusive'))) if argv[0]=='fixture-fixed' else ''
            with patch.object(paired.rt, 'command', side_effect=command) as cmd, \
                 patch.object(paired, 'health', side_effect=[None, paired.rt.Failure('DRAIN', 'busy')]
                              if failure=='health' else [None, 'files=0 mm_refs=0 destroyed=1 release_errors=0']), \
                 patch.object(paired, 'fault_check', side_effect=[None, paired.rt.Failure('FAULT', 'warning')]
                              if failure=='fault' else None):
                if failure=='none':
                    result=paired.fixed(inputs, Path('/fixture'), 'kd', policy.FUNCTIONAL)
                    self.assertEqual(result['writer_observation'], 'inconclusive')
                    self.assertEqual(result['rejected_mutations'], [])
                    self.assertEqual(cmd.call_args.args[0][0], 'rmmod')
                else:
                    with self.assertRaises(paired.rt.Failure):
                        paired.fixed(inputs, Path('/fixture'), 'kd', policy.FUNCTIONAL)
                    self.assertEqual(cmd.call_count, 2)

    def test_validation_shape_binds_observation_and_grid(self):
        row=scaling.validation()
        row.update(eligibility_policy=policy.FUNCTIONAL, writer_observation='inconclusive')
        row['fixed'].update(eligibility_policy=policy.FUNCTIONAL, writer_observation='inconclusive', rejected_mutations=[])
        paired.validation_shape(row, 'kd', {}, paired.SCALING_PLAN)
        for edit in (lambda r:r['fixed'].pop('eligibility_policy'), lambda r:r['cases'].pop(),
                     lambda r:r.__setitem__('writer_observation','observed'),
                     lambda r:r.__setitem__('drained',False)):
            bad=copy.deepcopy(row); edit(bad)
            with self.assertRaises((ValueError, paired.rt.Failure)):
                paired.validation_shape(bad, 'kd', {}, paired.SCALING_PLAN)

    def test_run_propagates_policy_and_both_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            for name in ('ready','prepared','native','kd','host'):(base/name).write_text('{}')
            ready=dict(passed=True,mode='kd',boot_id='new',block=1,plan=paired.SCALING_PLAN,
                prepared=paired.bind(base/'prepared'), eligibility_policy=policy.FUNCTIONAL,
                measurement_policy=paired.window.POLICY)
            a=argparse.Namespace(ready=base/'ready',output=base/'run',repeat=0,case=0,previous=None,
                native_validation=base/'native',kd_validation=base/'kd',host_state=base/'host')
            validations=[dict(eligibility_policy=policy.FUNCTIONAL,writer_observation=o,
                             measurement_policy=paired.window.POLICY) for o in ('observed','inconclusive')]
            def timed(inputs,out,*args,**kwargs):(out/'window-control.json').write_text('{}')
            with patch.object(paired,'readiness',return_value=(ready,{})), \
                 patch.object(paired,'validation_receipt',side_effect=validations), \
                 patch.object(paired,'host_check'), patch.object(paired,'environment',return_value=({},{})), \
                 patch.object(paired,'host_environment',return_value={}),patch.object(paired,'fault_check'), \
                 patch.object(paired,'timed',side_effect=timed),patch.dict(os.environ,KDLOCK_WINDOW_NONCE='fixture'):
                paired.run(a)
            row=json.loads((a.output/'client-result.json').read_text())
            self.assertEqual(row['eligibility_policy'],policy.FUNCTIONAL)
            self.assertEqual(row['writer_observations'],dict(native='observed',kd='inconclusive'))

    def test_summary_rejects_missing_mixed_or_unknown_policies_and_outcomes(self):
        rows=scaling.rows()
        for r in rows:r.update(eligibility_policy=policy.FUNCTIONAL,measurement_policy=paired.window.POLICY,
                               writer_observations=dict(native='observed',kd='inconclusive'))
        result=report.summarize(rows,scaling.bindings())
        self.assertEqual(result['writer_observations'],dict(native='observed',kd='inconclusive'))
        for edit in (lambda r:r.pop('eligibility_policy'), lambda r:r.pop('writer_observations'),
                     lambda r:r.__setitem__('eligibility_policy','unknown'),
                     lambda r:r['writer_observations'].__setitem__('kd','observed'),
                     lambda r:r.__setitem__('drained',False), lambda r:r.__setitem__('endpoint_checked',False)):
            bad=copy.deepcopy(rows);edit(bad[0])
            with self.assertRaises((ValueError,paired.rt.Failure)):report.summarize(bad,scaling.bindings())

    def test_report_replay_binds_client_readiness_and_validation_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            row=scaling.rows()[0]
            row.update(eligibility_policy=policy.FUNCTIONAL,measurement_policy=paired.window.POLICY,
                       writer_observations=dict(native='observed',kd='inconclusive'))
            for name in ('prepared','native','kd','controller','endpoint','admission'):
                (base/name).write_text('{}')
            row['prepared']=paired.bind(base/'prepared')
            row['validated']=[paired.bind(base/n) for n in ('native','kd')]
            ready={k:row[k] for k in ('mode','boot_id','block','plan','prepared','eligibility_policy','measurement_policy')}
            ready['passed']=True
            (base/'ready').write_text(json.dumps(ready));row['ready']=paired.bind(base/'ready')
            client=copy.deepcopy(row)
            for k in ('passed','drained','accepted'):client[k]=False
            evidence={k:paired.bind(base/k) for k in ('controller','endpoint','admission')}
            evidence['captured_utc']='fixture'
            row.update(qualification=evidence,endpoint_captured_utc='fixture')
            (base/'client.jsonl').write_text('{}\n')
            validations=[dict(eligibility_policy=policy.FUNCTIONAL,writer_observation=o,
                             measurement_policy=paired.window.POLICY) for o in ('observed','inconclusive')]
            for change in ('none','client_policy','ready_policy','observation'):
                r,c,rd=copy.deepcopy(row),copy.deepcopy(client),copy.deepcopy(ready)
                if change=='client_policy':c.pop('eligibility_policy')
                if change=='ready_policy':rd.pop('eligibility_policy')
                if change=='observation':
                    r['writer_observations']['kd']=c['writer_observations']['kd']='observed'
                (base/'ready').write_text(json.dumps(rd));r['ready']=c['ready']=paired.bind(base/'ready')
                (base/'result.json').write_text(json.dumps(r))
                (base/'client-result.json').write_text(json.dumps(c))
                with patch.object(paired,'validation_receipt',side_effect=validations), \
                     patch.object(paired,'qualify',return_value=evidence), \
                     patch.object(paired,'measurement',return_value=r['measurement']):
                    if change=='none':self.assertEqual(report.replay(base/'result.json'),r)
                    else:
                        with self.assertRaises(ValueError):report.replay(base/'result.json')


class CompletionC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        out=Path(cls.temp.name)
        source=out/'completion.c'
        source.write_text('#define main original_client_main\n#include "'+str(ROOT/'bench/mmap_writer/client.c')+
            '"\n#undef main\nint main(int argc,char **argv) { CHECK(argc==3); struct worker w[2]={0}; '
            'return !emit_completion("cycle",atoi(argv[1]),atoi(argv[2]),w,2,0); }\n')
        cls.binary=out/'completion'
        subprocess.run(['gcc','-O2','-Wall','-Wextra','-Werror','-pthread',
            '-I'+str(ROOT/'workload_modules/mmap_writer'),str(source),'-o',str(cls.binary)],check=True,timeout=30)

    def test_real_completion_json_and_status_in_four_policy_outcomes(self):
        for functional in (0,1):
            for observed in (0,1):
                result=subprocess.run([str(self.binary),str(observed),str(functional)],capture_output=True,text=True,timeout=5)
                row=json.loads(result.stdout)
                self.assertEqual(result.returncode,int(not (functional or observed)))
                self.assertIs(row['passed'],bool(functional or observed))
                self.assertEqual(policy.policy(row),policy.FUNCTIONAL if functional else policy.STRICT)
                if functional:
                    self.assertTrue(row['functional_complete'])
                    self.assertEqual(row['writer_observation'],'observed' if observed else 'inconclusive')


if __name__=='__main__':unittest.main()
