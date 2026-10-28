"""Direct comparison matrix and result exclusion; no modules are loaded."""
from argparse import Namespace
import copy
import contextlib
import io
import sys
from unittest.mock import Mock, patch
import json
import re
from pathlib import Path
import tempfile
import unittest
import subprocess

import run
from session import (BackendSession, hash_layout, tc_quiescent, check_jit_evidence,
                     check_kd_parameters)
from bench_session import Session
from context_audit import audit as audit_context
from mutex_api_audit import audit_public_entries


class DirectTests(unittest.TestCase):

    def test_public_spin_plan_preserves_default_and_separates_callers(self):
        args = dict(cachelines=[1, 16], threads=[*range(1, 9), *range(12, 61, 4)],
                    repeats=1, iterations=100, backends=['native', 'tclock', 'kdlock'],
                    lock_kind='spin')
        direct = run.make_plan(Namespace(**args))
        self.assertEqual(direct, run.make_plan(Namespace(**args, spin_api='direct')))
        public = run.make_plan(Namespace(**args, spin_api='public'))
        self.assertEqual(len(public), 2 * 21 * 3)
        self.assertEqual(len({row['name'] for row in public}), len(public))
        for row, control in zip(public, direct):
            if row['arm'] == 'kdlock':
                self.assertEqual(row['caller_shell'], 'spin_public_clobber')
                self.assertEqual(row['cookie_storage'], 'provider_acquisition_ledger')
                self.assertNotEqual(row['name'], control['name'])
                self.assertEqual({k: v for k, v in row.items()
                                  if k not in ('name', 'caller_shell', 'cookie_storage')},
                                 {k: v for k, v in control.items()
                                  if k not in ('name', 'caller_shell', 'cookie_storage')})
            else:
                self.assertEqual(row, control)
        for extra in (dict(lock_kind='mutex'), dict(scenario='nested'), dict(scenario='early')):
            with self.subTest(extra=extra), self.assertRaises(run.Failure):
                run.make_plan(Namespace(**(args | extra), spin_api='public'))
        with self.assertRaises(run.Failure):
            run.make_plan(Namespace(**args, spin_api='unknown'))

    def test_report_keeps_public_spin_separate_from_direct(self):
        args = dict(cachelines=[1], threads=[8], repeats=1, iterations=100,
                    backends=['kdlock'], lock_kind='spin')
        plan = [run.make_plan(Namespace(**args, spin_api=api))[0]
                for api in ('direct', 'public')]
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plan)
            for spec, wall in zip(plan, (100000, 200000)):
                (out/spec['name']).mkdir()
                run.write_json(out/spec['name']/'session.json', dict(spec,
                    execution_status='OK', drained=True, jit_bodies=100, jit_completions=100,
                    measurement=dict(complete=True, data_ok=True, completed=100, wall_ns=wall)))
            run.report(out)
            rows = json.loads((out/'summary.json').read_text())
            self.assertEqual(len(rows), 2)
            self.assertEqual({row['caller_shell']: row['best_throughput_ops_s'] for row in rows},
                             {'cold_clobber': 1000000, 'spin_public_clobber': 500000})
            self.assertTrue(all(row['sessions'] == row['valid'] == 1 for row in rows))

    def test_compiled_public_spin_alias_matches_captured_rip(self):
        # Compile the actual public assembly/macro and workload alias. This is
        # ELF evidence only; real Kbuild and returned JIT bodies are separate.
        header = (run.ROOT/'include/kd_spin_direct.h').read_text()
        call = '#define KD_SPIN_DIRECT_CALL' + header.split(
            '#define KD_SPIN_DIRECT_CALL', 1)[1].split('\n\n', 1)[0]
        api = re.sub(r'^#include .*$', '',
                     (run.ROOT/'include/kd_spin_api.h').read_text(), flags=re.M)
        workload = re.sub(r'^#include .*$', '',
                         (run.ROOT/'workload_modules/spin_cacheline/direct.h').read_text(),
                         flags=re.M)
        source = '\n'.join((
            'typedef unsigned int kd_spinlock_t;',
            'register unsigned long current_stack_pointer asm("rsp");',
            '#define ASM_CALL_CONSTRAINT "+r" (current_stack_pointer)',
            '#define _ASM_PTR ".quad"', '#define SC_DIRECT_KDLOCK 1',
            '#define SC_SPIN_PUBLIC_API 1', call, api, workload,
            'static kd_spinlock_t sc_lock; static volatile unsigned long value;',
            '__attribute__((noipa, used)) static void sc_body_1(void) {',
            'SC_LOCK(1); value++; SC_UNLOCK(); }',
        ))
        audit_args = dict(lock_symbol='kd_spin_lock_clobber_v1',
                          unlock_symbol='kd_spin_unlock_clobber_v1')
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            caller, binary = folder/'caller.c', folder/'caller.o'
            for shifted in (False, True):
                caller.write_text(source.replace(', 1b\\n', ', 1b + 1\\n') if shifted else source)
                subprocess.run(['gcc', '-O2', '-fno-omit-frame-pointer',
                                '-fno-optimize-sibling-calls', '-mno-red-zone',
                                '-Wall', '-Wextra', '-Werror', '-c', str(caller),
                                '-o', str(binary)], check=True, capture_output=True, timeout=30)
                if shifted:
                    with self.assertRaisesRegex(ValueError, 'captured RIP'):
                        audit_public_entries(binary, {'sc_entry_1': 'sc_body_1'}, **audit_args)
                else:
                    result = audit_public_entries(binary, {'sc_entry_1': 'sc_body_1'}, **audit_args)
                    self.assertEqual(result['sc_entry_1']['entry_offset'],
                                     result['sc_entry_1']['call_offset'] + 5)
                    with self.assertRaisesRegex(ValueError, 'public lock CALL'):
                        audit_public_entries(binary, {'sc_entry_1': 'sc_body_1'})
                    with self.assertRaisesRegex(ValueError, 'valid DIRECT unlock'):
                        audit_public_entries(binary, {'sc_entry_1': 'sc_body_1'},
                                             lock_symbol=audit_args['lock_symbol'])


    def test_jit_requires_returned_bodies_and_separates_local_repeats(self):
        base = dict(workload='cacheline', arm='kdlock', threads=8, jit_bodies=10,
                    jit_completions=10, lock_kind='mutex', functional=True)
        check_jit_evidence(base)
        self.assertEqual(base['jit_acceptance'], 'PASS')
        for values in (dict(jit_completions=0), dict(jit_completions=11),
                       dict(jit_bodies=0, jit_completions=0)):
            with self.assertRaises(run.Failure):
                check_jit_evidence(dict(base, **values))
        self.assertEqual(run.execution_class(base), 'RETURNED_JIT')
        self.assertEqual(run.execution_class(dict(base, jit_bodies=0, jit_completions=0)),
                         'NO_JIT')
        self.assertEqual(run.execution_class(dict(base, jit_completions=0)), 'PARTIAL_JIT')
        self.assertEqual(run.execution_class({k:v for k,v in base.items()
                                              if k != 'jit_completions'}), 'UNMEASURED')

    def test_public_mutex_plan_is_distinct_on_every_standard_cohort(self):
        threads = [*range(1, 9), *range(12, 61, 4)]
        args = dict(cachelines=[1], threads=threads, repeats=3, iterations=100,
                    backends=['native', 'tclock', 'kdlock'], lock_kind='mutex')
        public = run.make_plan(Namespace(**args, mutex_api='public'))
        outer = run.make_plan(Namespace(**args, mutex_api='outer'))
        self.assertEqual(len(public), 21 * 3 * 3)
        self.assertEqual(len({r['name'] for r in public}), len(public))
        for row, control in zip(public, outer):
            if row['arm'] == 'kdlock':
                self.assertEqual(row['caller_shell'], 'mutex_public_direct')
                self.assertEqual(row['cookie_storage'], 'provider_acquisition_ledger')
                self.assertNotEqual(row['name'], control['name'])
            else:
                self.assertEqual(row, control)
        with self.assertRaises(run.Failure):
            run.make_plan(Namespace(**(args | dict(lock_kind='spin')), mutex_api='public'))

    def test_public_entry_audit_rejects_shifted_label_and_wrong_saved_rip(self):
        # Real relocatable ELF, with independent faults in the named entry and
        # in the RIP captured for the provider. Never execute these fixtures.
        assembly = """
.text
.globl body
.type body,@function
body:
mov %rsp,%rsi
lea saved(%rip),%rdx
mov %rbp,%rcx
call kd_mutex_direct_lock_clobber_v1
after:
nop
shifted:
call kd_mutex_direct_unlock_clobber_v1
ret
.size body,.-body
.globl entry
.set entry,ENTRY
.set saved,SAVED
"""
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for entry, saved in (('after', 'after'), ('shifted', 'after'),
                                 ('after', 'shifted')):
                source, binary = folder/'entry.S', folder/'entry.o'
                source.write_text(assembly.replace('ENTRY', entry).replace('SAVED', saved))
                subprocess.run(['gcc', '-c', str(source), '-o', str(binary)], check=True,
                               capture_output=True)
                if entry == saved == 'after':
                    result = audit_public_entries(binary, {'entry': 'body'})
                    self.assertEqual(result['entry']['entry_offset'],
                                     result['entry']['call_offset'] + 5)
                else:
                    with self.assertRaisesRegex(ValueError, 'captured RIP'):
                        audit_public_entries(binary, {'entry': 'body'})

    def test_performance_diagnostics_are_unscored_for_every_backend(self):
        for mode in ('pmu', 'perf_record'):
            plan = run.make_plan(Namespace(cachelines=[1], threads=[16], repeats=1,
                iterations=100, backends=['native', 'tclock', 'kdlock'],
                lock_kind='mutex', **{mode: True}))
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                run.write_json(out/'plan.json', plan)
                for spec in plan:
                    self.assertTrue(spec['diagnostic'] and spec[mode])
                    (out/spec['name']).mkdir()
                    run.write_json(out/spec['name']/'session.json', dict(spec,
                        execution_status='OK', drained=True, jit_bodies=100,
                        measurement=dict(complete=True, data_ok=True, completed=100, wall_ns=100000), jit_completions=100))
                run.report(out)
                records = json.loads((out/'records.json').read_text())
                self.assertTrue(all(not r['score_eligible'] for r in records))
                self.assertTrue(all(r['whole_throughput_ops_s'] == 1000000 for r in records))
                self.assertTrue(all(r['valid'] == 0 and r['best_session'] is None for r in
                                    json.loads((out/'summary.json').read_text())))

    def test_cpu_samples_cannot_mix_with_pmu(self):
        with self.assertRaisesRegex(run.Failure, 'separate diagnostic runs'):
            run.make_plan(Namespace(cachelines=[1], threads=[16], repeats=1,
                iterations=100, backends=['native'], pmu=True, perf_record=True))

    def test_cpu_samples_resolve_modules_before_cleanup(self):
        session = BackendSession.__new__(BackendSession)
        session.lock_kind = 'spin'
        session.record = dict(perf_record=True)
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(Path, 'read_text', return_value='captured symbols'), \
                patch.object(Session, 'run', return_value='measurement') as invoke:
            session.path = Path(temporary)
            result = session.run([run.HERE/'client', '--iterations', 100], 'measure.json', timeout=120)
            self.assertEqual(result, 'measurement')
            self.assertEqual([call.args[0][1] for call in invoke.call_args_list],
                             ['record', 'report', 'script'])
            self.assertIn('--sample-cpu', invoke.call_args_list[0].args[0])
            self.assertEqual(invoke.call_args_list[0].kwargs['timeout'], 120)
            self.assertTrue((session.path/'kallsyms').is_file())
            self.assertTrue((session.path/'modules').is_file())

    def test_provider_identity_rejects_mutex_jit_switch(self):
        record = dict(spin_entry_ratio_limit=2, spin_prefetch=2,
                      spin_delegate='on')
        params = dict(bench_quiet='Y', jit_timing='N', bench_lock_addr='4096',
                      bench_complete_probe='Y',
                      spin_entry_ratio_limit='2', spin_prefetch='2', spin_delegate='Y')
        check_kd_parameters(params, record, 4096)
        for workload in ('cacheline', 'rcuht'):
            record_for_workload = dict(record, workload=workload)
            check_kd_parameters(dict(params, bench_complete_probe='Y'), record_for_workload, 4096)
            for incomplete in (dict(params, bench_complete_probe='N'),
                               {k:v for k,v in params.items() if k != 'bench_complete_probe'}):
                with self.assertRaises(run.Failure):
                    check_kd_parameters(incomplete, record_for_workload, 4096)
        for value in ('0', '1'):
            with self.subTest(value=value), self.assertRaises(run.Failure):
                check_kd_parameters(dict(params, mutex_jit=value), record, 4096)

    def test_mutex_runner_rejects_spin_disabled_control(self):
        args = Namespace(cachelines=[1], threads=[16], repeats=1,
                         iterations=100, backends=['kdlock'],
                         lock_kind='mutex', spin_delegate='off')
        with self.assertRaisesRegex(run.Failure, 'mutex JIT is required'):
            run.make_plan(args)
        argv = ['run_mutex.py', '--output', '/tmp/unused', '--dry-run',
                '--spin-delegate', 'off']
        with patch.object(sys, 'argv', argv), \
                self.assertRaisesRegex(run.Failure, 'mutex JIT is required'):
            run.main('mutex')

    def test_mutex_cannot_bypass_returned_body_acceptance(self):
        record = dict(arm='kdlock', lock_kind='mutex', threads=16,
                      jit_bodies=0, scenario='plain', spin_delegate='off', jit_completions=0)
        with self.assertRaisesRegex(run.Failure, 'no actual JIT'):
            check_jit_evidence(record)
        self.assertEqual(record['jit_acceptance'], 'NO_JIT')
        check_jit_evidence(record := dict(record, jit_bodies=1, jit_completions=1))
        self.assertEqual(record['jit_acceptance'], 'PASS')

    def test_rwlock_context_accepts_only_original_irq_prefix(self):
        saves = [f'push %{r}' for r in ('rbp', 'rbx', 'r12', 'r13', 'r14', 'r15')]
        restores = [f'pop %{r}' for r in ('r15', 'r14', 'r13', 'r12', 'rbx', 'rbp')]
        def function(name, instructions):
            return f'0000 <{name}>:\n' + ''.join(
                f' {i:x}: {instruction}\n' for i, instruction in enumerate(instructions))
        switch = function('komb_context_switch', saves +
                          ['mov %rsp,(%rsi)', 'mov (%rdi),%rsp'] + restores + ['ret'])
        helpers = function('get_komb_rwlock_node', ['mov %gs:0,%rax', 'ret']) + \
                  function('get_shadow_stack_ptr', ['mov %gs:0,%rax', 'ret'])
        for prefix in (['cli'], ['call *0x0(%rip)\n 2: R_X86_64_PC32 pv_ops+0xec']):
            body = prefix + saves + ['call 0'] + restores + ['ret'] + restores + ['ret']
            text = switch + function('kombrw_spin_lock_slowpath', body) + helpers
            self.assertTrue(audit_context(text, 'rwlock')['six_register_switch'])
            if prefix[0].startswith('call'):
                for invalid in (text.replace('pv_ops+0xec', 'pv_ops+0xfc'),
                                text.replace('pv_ops+0xec', 'pv_ops+0xf4'),
                                text.replace('pv_ops+0xec', 'unrelated'),
                                text.replace('push %rbp', 'push %rbp\n 0: mov %rsp,%rbp', 1)):
                    with self.assertRaises(ValueError):
                        audit_context(invalid, 'rwlock')

    def test_rwlock_linux70_pv_argument_dataflow_is_exact(self):
        saves = [f'push %{r}' for r in ('rbp', 'rbx', 'r12', 'r13', 'r14', 'r15')]
        restores = [f'pop %{r}' for r in ('r15', 'r14', 'r13', 'r12', 'rbx', 'rbp')]

        def function(name, instructions):
            return f'0000 <{name}>:\n' + ''.join(
                f' {i:x}: {instruction}\n' for i, instruction in enumerate(instructions))

        def irq(offset):
            return 'call *0x0(%rip)\n 0: R_X86_64_PC32 pv_ops+' + offset

        switch = function('komb_context_switch', saves +
                          ['mov %rsp,(%rsi)', 'mov (%rdi),%rsp'] + restores + ['ret'])
        helpers = function('get_komb_rwlock_node', ['mov %gs:0,%rax', 'ret']) + \
                  function('get_shadow_stack_ptr', ['mov %gs:0,%rax', 'ret'])
        body = ['mov %rdi,%r8', irq('0xec')] + saves + [
            'call 180 <get_komb_rwlock_node>', 'mov %rsp,0x28(%rax)',
            'call 150 <get_shadow_stack_ptr>', 'mov (%rax),%rsp',
            irq('0xf4'), 'mov %r8,%rdi', 'call 7b0 <__kombrw_spin_lock_slowpath>',
            'mov %eax,%r8d', irq('0xec'), 'test %r8d,%r8d', 'je a6b'] + \
            restores + ['ret'] + restores + ['ret']

        def text(instructions):
            return switch + function('kombrw_spin_lock_slowpath', instructions) + helpers

        self.assertTrue(audit_context(text(body), 'rwlock')['rwlock_pv_preserves_argument'])
        mutations = {
            'wrong saved register': (0, 'mov %rdi,%r9'),
            'missing disable': (1, 'nop'),
            'wrong IRQ call operand': (1, 'call *%r8\n 0: R_X86_64_PC32 pv_ops+0xec'),
            'old disable offset': (1, irq('0xf4')),
            'wrong node offset': (9, 'mov %rsp,0x30(%rax)'),
            'missing enable': (12, 'nop'),
            'wrong enable offset': (12, irq('0xec')),
            'missing argument restore': (13, 'nop'),
            'wrong argument restore': (13, 'mov %r9,%rdi'),
            'wrong slowpath': (14, 'call 7b0 <unrelated>'),
            'return value lost': (15, 'mov %eax,%ecx'),
            'missing second disable': (16, 'nop'),
            'wrong second disable offset': (16, irq('0xf4')),
            'wrong return test': (17, 'test %eax,%eax'),
        }
        for name, (index, replacement) in mutations.items():
            broken = list(body)
            broken[index] = replacement
            with self.subTest(name=name), self.assertRaises(ValueError):
                audit_context(text(broken), 'rwlock')
        for name, broken in (
                ('extra R8 clobber', body[:12] + ['xor %r8d,%r8d'] + body[12:]),
                ('extra compiler frame', ['push %rbp', 'mov %rsp,%rbp'] + body),
                ('extra saved RBP', body[:2] + ['push %rbp'] + body[2:]),
                ('missing restore', body[:-2] + body[-1:])):
            with self.subTest(name=name), self.assertRaises(ValueError):
                audit_context(text(broken), 'rwlock')
        with self.assertRaises(ValueError):
            audit_context(text(body).replace('mov %gs:0,%rax', 'xor %r8d,%r8d', 1), 'rwlock')
        thunk_helpers = function('get_komb_rwlock_node', [
            'mov %gs:0,%rax', 'jmp 193 <get_komb_rwlock_node+0x13>\n'
            ' 0: R_X86_64_PLT32 __x86_return_thunk-0x4']) + \
            function('get_shadow_stack_ptr', ['mov %gs:0,%rax', 'ret'])
        bound = switch + function('kombrw_spin_lock_slowpath', body) + thunk_helpers
        self.assertTrue(audit_context(bound, 'rwlock')['hidden_helpers_preserve_lock'])
        for broken in (
                bound.replace('R_X86_64_PLT32 __x86_return_thunk-0x4',
                              'R_X86_64_PLT32 unrelated-0x4'),
                bound.replace('R_X86_64_PLT32 __x86_return_thunk-0x4', ''),
                bound.replace('jmp 193 <get_komb_rwlock_node+0x13>', 'jmp *%r8')):
            with self.assertRaises(ValueError):
                audit_context(broken, 'rwlock')

    def test_source_snapshot_covers_tclock_fragments(self):
        # A frozen run must include the bodies behind the C entry files;
        # omitting them would allow protocol changes during measurement.
        state = run.source_state()
        fragments = sorted((run.ROOT / 'tclock_backend').glob('*/*.inc'))
        self.assertTrue(fragments)
        for path in fragments:
            with self.subTest(path=path):
                self.assertEqual(state[str(path.relative_to(run.ROOT))],
                                 run.digest(path))
        reader = 'tests/unit/infrastructure/source_text.py'
        self.assertEqual(state[reader], run.digest(run.ROOT / reader))

    def test_collect_no_jit_preserves_failure_and_requires_verified_drain(self):
        record = dict(execution_status='NO_JIT', jit_acceptance='NO_JIT',
                      jit_bodies=0, drained=True,
                      measurement=dict(complete=True, data_ok=True), jit_completions=0)
        before = copy.deepcopy(record)
        session = Mock(record=record)
        session.execute.side_effect = run.Failure('NO_JIT', 'missing body')
        with self.assertRaises(run.Failure):
            run.execute_session(session)
        self.assertFalse(run.execute_session(session, True))
        self.assertEqual(record, before)
        # No unsafe, incomplete or contradictory session may be hidden by
        # the optional evidence-collection mode. The original verdict stays.
        variants = [dict(record, drained=False), dict(record, cleanup_error='busy'),
                    dict(record, execution_status='OK'), dict(record, jit_bodies=1, jit_completions=1),
                    dict(record, jit_acceptance='PASS'),
                    dict(record, measurement=dict(complete=False, data_ok=True)),
                    dict(record, measurement=dict(complete=True, data_ok=False))]
        for bad in variants:
            with self.subTest(record=bad), self.assertRaises(run.Failure):
                run.execute_session(Mock(record=bad, execute=Mock(
                    side_effect=run.Failure('NO_JIT', 'missing body'))), True)
        for status, unsafe in [('NO_JIT', True), ('UNDRAINED', False),
                               ('PREPARATION_FAILED', False)]:
            with self.subTest(status=status, unsafe=unsafe), self.assertRaises(run.Failure):
                run.execute_session(Mock(record=record, execute=Mock(
                    side_effect=run.Failure(status, 'failure', unsafe=unsafe))), True)
        good = Mock(record=dict(execution_status='OK', drained=True))
        self.assertTrue(run.execute_session(good, True))

    def test_collect_no_jit_does_not_change_score_exclusion(self):
        plans = run.make_plan(Namespace(cachelines=[1], threads=[16], repeats=3,
            iterations=100, backends=['kdlock'], cpus=list(range(16))))
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plans)
            for i, spec in enumerate(plans):
                folder = out/spec['name']; folder.mkdir()
                run.write_json(folder/'session.json', dict(spec, drained=True,
                    execution_status='OK' if i == 0 else 'NO_JIT',
                    jit_bodies=1 if i == 0 else 0,
                    measurement=dict(completed=100, wall_ns=100000 if i == 0 else 100,
                                     data_ok=True, complete=True), jit_completions=1 if i == 0 else 0))
            run.report(out)
            summary = json.loads((out/'summary.json').read_text())[0]
            self.assertEqual(summary['valid'], 1)
            self.assertEqual(summary['best_session'], plans[0]['name'])
            records = json.loads((out/'records.json').read_text())
            self.assertTrue(all(r['throughput_ops_s'] is None for r in records[1:]))

    def test_mutex_entrypoint_and_delegation_identity(self):
        argv = ['run_mutex.py', '--output', '/tmp/unused', '--dry-run',
                '--threads', '16', '36', '--cachelines', '1']
        with patch.object(sys, 'argv', argv), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(run.main('mutex'), 0)
        plan = json.loads(output.getvalue())
        self.assertEqual(len(plan), 18)
        self.assertTrue(all(s['lock_kind'] == 'mutex' for s in plan))
        self.assertTrue(all(s['caller_shell'] == 'mutex_outer_cookie'
                            for s in plan if s['arm'] == 'kdlock'))
        self.assertTrue(all(s['cookie_storage'] == 'outer_acquisition_local'
                            for s in plan if s['arm'] == 'kdlock'))
        params = dict(target_lock=4096, komb_batch_size=1024, quiescent=1,
                      delegated=8192, batches=8, parks=4)
        tc_quiescent(params, 'mutex')
        for bad in (dict(params, quiescent=0),
                    {k: v for k, v in params.items() if k != 'delegated'}):
            with self.assertRaises(run.Failure):
                tc_quiescent(bad, 'mutex')
        # Successful data with zero JIT does not establish a contended positive.
        with self.assertRaisesRegex(run.Failure, 'no actual JIT'):
            check_jit_evidence(dict(arm='kdlock', lock_kind='mutex', threads=16,
                                    jit_bodies=0, scenario='plain', jit_completions=0))

    def test_explicit_placement_and_collector(self):
        args = Namespace(cachelines=[1], threads=[8, 16], repeats=1,
                         iterations=100, backends=['native', 'kdlock'],
                         cpus=run.runtime.cpu_list('0-7,20-27'),
                         duration_ms=2000, collector_cpu=38)
        plans = run.make_plan(args)
        self.assertTrue(all(s['cpus'] == args.cpus[:s['threads']] for s in plans))
        args.collector_cpu = 20
        with self.assertRaisesRegex(run.Failure, 'collector CPU'):
            run.make_plan(args)
        args.collector_cpu, args.cpus = 38, [0, 1]
        with self.assertRaisesRegex(run.Failure, 'placement'):
            run.make_plan(args)

    def test_summary_keeps_placement_separate(self):
        # Different node geometries must never supply each other's winner or
        # Linux denominator, even when thread counts and policies match.
        plans = []
        for suffix, cpus in (('local', [0, 1]), ('split', [0, 20])):
            cohort = run.make_plan(Namespace(cachelines=[1], threads=[2], repeats=1,
                iterations=100, backends=['native', 'kdlock'], cpus=cpus))
            plans.extend(dict(s, name=s['name']+'-'+suffix) for s in cohort)
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plans)
            for i, spec in enumerate(plans):
                folder = out/spec['name']; folder.mkdir()
                run.write_json(folder/'session.json', dict(spec,
                    jit_bodies=0, jit_completions=0, execution_status='OK', drained=True,
                    measurement=dict(completed=100, wall_ns=(i+1)*100000,
                                     data_ok=True, complete=True)))
            run.report(out)
            rows = json.loads((out/'summary.json').read_text())
            self.assertEqual(len(rows), 4)
            kd = [r for r in rows if r['arm'] == 'kdlock']
            self.assertEqual([r['throughput_over_linux'] for r in kd], [0.5, 0.75])

    def test_legacy_mutex_batch_option_reaches_the_independent_build_knob(self):
        for kind in ('spin', 'mutex'):
            for cap in (1, 128, 1024):
                args = Namespace(numa='on', kd_batch_size=cap, cachelines=[1],
                                 threads=[8], repeats=1, iterations=100,
                                 backends=['kdlock'], lock_kind=kind)
                build = run.provider_build(args)
                self.assertIn(f'KDLOCK_SPIN_BATCH={cap}', build)
                self.assertIn(f'KDLOCK_MUTEX_BATCH={cap if kind == "mutex" else 1024}', build)
                self.assertIn('KDLOCK_MUTEX_NUMA_BOUNDARY=1024', build)
                row, = run.make_plan(args)
                self.assertEqual(row['delegation_batch_limit'], cap)
                self.assertEqual(row['provider_mutex_policy'], dict(
                    total_cap=cap if kind == 'mutex' else 1024,
                    numa_boundary=1024, deferred_handoff=8, scan_budget=64))

    def test_provider_ubsan_option_and_private_build(self):
        # Both entrypoints default to off; explicit policies and direct helper
        # callers must agree with the policy saved in every new session.
        for lock_kind, option in ((kind, policy) for kind in ('spin', 'mutex')
                                  for policy in (None, 'kernel', 'off')):
            policy = option or 'off'
            argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                    '--threads', '8', '--cachelines', '1', '--repeats', '1']
            if option is not None:
                argv += ['--kd-provider-ubsan', option]
            with self.subTest(lock_kind=lock_kind, option=option), \
                    patch.object(sys, 'argv', argv), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(run.main(lock_kind), 0)
            plan = json.loads(output.getvalue())
            for spec in plan:
                self.assertEqual(spec['kd_provider_ubsan'],
                                 policy if spec['arm'] == 'kdlock' else 'not_applicable')
            args = Namespace(numa='on', kd_batch_size=1024, cachelines=[1],
                             threads=[8], repeats=1, iterations=100,
                             backends=['kdlock'], lock_kind=lock_kind)
            if option is not None:
                args.kd_provider_ubsan = option
            build = run.provider_build(args)
            self.assertEqual(build[:4], ['make', '-C', run.HERE, 'provider'])
            self.assertEqual('UBSAN_SANITIZE=n' in build, policy == 'off')
            self.assertEqual(run.make_plan(args)[0]['kd_provider_ubsan'], policy)
            # Exercise real session serialization without opening the kernel log.
            spec, = [spec for spec in plan if spec['arm'] == 'kdlock']
            with tempfile.TemporaryDirectory() as temporary, \
                    patch('bench_session.os.open', return_value=17), \
                    patch('bench_session.os.lseek'):
                session = BackendSession(Path(temporary), spec)
                record = json.loads((session.path/'session.json').read_text())
                self.assertEqual(record['kd_provider_ubsan'], policy)

    def test_provider_ubsan_off_rejects_instrumented_elf(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            imported = ' U __ubsan_handle_load_invalid_value\n U printk\n'
            with patch.object(run, 'command', return_value=imported) as command:
                run.audit_provider_ubsan(out, 'kernel')
                with self.assertRaisesRegex(run.Failure, 'still imports UBSAN'):
                    run.audit_provider_ubsan(out, 'off')
                command.assert_called_with(['nm', '-u', run.PROVIDER],
                                           out/'imports-kdlock-provider.txt')
            with patch.object(run, 'command', return_value=' U printk\n'):
                run.audit_provider_ubsan(out, 'off')
            self.assertEqual(json.loads((out/'kdlock-provider-ubsan.json').read_text()),
                             dict(policy='off', imports=[]))

    def test_summary_keeps_provider_ubsan_policies_separate(self):
        spec, = run.make_plan(Namespace(cachelines=[1], threads=[8], repeats=1,
            iterations=100, backends=['kdlock']))
        plan = []
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            for index, policy in enumerate(('kernel', 'off', 'unrecorded'), 1):
                candidate = dict(spec, name=f'provider-{policy}', kd_provider_ubsan=policy)
                if policy == 'unrecorded':
                    del candidate['kd_provider_ubsan']
                plan.append(candidate)
                folder = out/candidate['name']; folder.mkdir()
                run.write_json(folder/'session.json', dict(candidate,
                    jit_bodies=0, jit_completions=0, execution_status='OK', drained=True,
                    measurement=dict(completed=index * 1000, wall_ns=1000000,
                                     data_ok=True, complete=True)))
            run.write_json(out/'plan.json', plan)
            run.report(out)
            rows = json.loads((out/'summary.json').read_text())
            self.assertEqual(len(rows), 3)
            self.assertEqual({r['kd_provider_ubsan']: r['best_throughput_ops_s']
                              for r in rows},
                             dict(kernel=1e6, off=2e6, unrecorded=3e6))
            self.assertTrue(all(r['sessions'] == r['valid'] == 1 for r in rows))

    def test_numa_expanded_matrix(self):
        plan = run.make_plan(Namespace(cachelines=[1],
            threads=[1,2,3,4,5,6,7,8,12,16,20,24,28,32,36], repeats=3,
            iterations=100000, backends=['native','tclock','kdlock'],
            duration_ms=2000, collector_cpu=38, numa='on', kd_batch_size=128))
        self.assertEqual(len(plan), 135)
        for spec in plan:
            self.assertNotIn(38, spec['cpus'])
            if spec['arm'] == 'kdlock':
                self.assertEqual(spec['numa_policy'], 'on')
                self.assertEqual(spec['delegation_batch_limit'], 128)
            elif spec['arm'] == 'tclock':
                self.assertEqual(spec['delegation_batch_limit'], 1024)
        with self.assertRaises(run.Failure):
            run.make_plan(Namespace(cachelines=[1], threads=[36], repeats=1,
                iterations=100000, backends=['kdlock'], duration_ms=2000,
                collector_cpu=30))

    def test_timed_session_uses_fixed_warmup_and_continuous_measurement(self):
        session = BackendSession.__new__(BackendSession)
        spec, = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=1,
            iterations=100, backends=['native'], duration_ms=2000))
        session.record = spec
        session.counts = Mock(return_value=dict(active=0))
        session.faults = Mock()
        session.run = Mock(return_value='{}')
        peak = dict(throughput_ops_s=1e6)
        with patch('bench_session.validate_measurement', side_effect=[None, peak]) as validate:
            session.phase('warmup', 48000)
            warmup = session.run.call_args.args[0]
            self.assertIn('--iterations', warmup)
            self.assertNotIn('--duration-ms', warmup)
            self.assertEqual(validate.call_args.args[1]['duration_ms'], 0)
            result = session.phase('measure', 100)
            measure = session.run.call_args.args[0]
            self.assertNotIn('--iterations', measure)
            self.assertIn('--duration-ms', measure)
            self.assertEqual(validate.call_args.args[1]['duration_ms'], 2000)
            self.assertEqual(result['peak'], peak)

    def test_timed_plan_and_peak_summary_keep_whole_run_visible(self):
        args = Namespace(cachelines=[1], threads=[3], repeats=2, iterations=100,
            backends=['native', 'tclock', 'kdlock'],
            duration_ms=2000)
        plan = run.make_plan(args)
        self.assertTrue(all(s['peak_window_ms'] == s['peak_settle_ms'] == 300 and
                            s['sample_ms'] == 10 and s['collector_cpu'] == 63 and
                            s['measurement_mode'] == 'timed_peak' for s in plan))
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plan)
            for spec in plan:
                folder = out/spec['name']; folder.mkdir()
                # Winning peak and winning whole-run mean belong to different
                # rounds. Selection must keep the peak's matching whole rate.
                rate = (2 - spec['repeat']) * 1e6
                whole = (1 + spec['repeat']) * 0.5e6
                run.write_json(folder/'session.json', dict(spec,
                    jit_bodies=0, jit_completions=0, execution_status='OK', drained=True,
                    measurement=dict(completed=whole * 2, wall_ns=2e9,
                        data_ok=True, complete=True,
                        peak=dict(throughput_ops_s=rate, amortized_ns_op=1e9/rate))))
            run.report(out)
            rows = json.loads((out/'summary.json').read_text())
            for row in rows:
                self.assertEqual(row['comparison_policy'], 'best_valid_warmed_peak')
                self.assertEqual(row['best_throughput_ops_s'], 2e6)
                self.assertEqual(row['best_whole_throughput_ops_s'], 0.5e6)
                self.assertEqual(row['best_amortized_ns_op'], 500)
                self.assertEqual(row['throughput_over_linux'], 1)
                self.assertEqual(row['min_throughput_ops_s'], 1e6)
        args.collector_cpu = 1
        with self.assertRaisesRegex(run.Failure, 'collector CPU'):
            run.make_plan(args)
        args.collector_cpu, args.duration_ms = 30, 600
        with self.assertRaisesRegex(run.Failure, 'timing intervals'):
            run.make_plan(args)

    def test_warmup_uses_all_workers_without_changing_preparation(self):
        cpus, nodes = [2, 7, 11], [0, 1, 0]
        warmup = dict(schema=1, complete=True, data_ok=True, workload='cacheline',
            cachelines=1, threads=3, iterations=48000, completed=144000,
            worker_cpu_ns=60, started_ns=100, finished_ns=300, wall_ns=200,
            before=[0]*16, after=[144000]+[0]*15,
            workers=[dict(cpu=cpu, observed_cpu=cpu, error=0, completed=48000,
                          cpu_ns=20, finished_ns=300) for cpu in cpus])

        def initialize(session, out, spec):
            # Substitute only module/device setup; retain BackendSession init.
            session.record = copy.deepcopy(spec)
            session.path = Path(out)/spec['name']
            session.workload_module = Path('/unused/spin_cacheline.ko')
            session.loaded_kd = session.loaded_source = False

        for arm in ('native', 'tclock', 'kdlock'):
            with self.subTest(arm=arm), patch.object(Session, '__init__', initialize):
                spec, = run.make_plan(Namespace(cachelines=[1], threads=[3],
                    repeats=1, iterations=17, backends=[arm],
                    pmu=True))
                spec.update(cpus=cpus, cpu_nodes=nodes)
                self.assertEqual((spec['warmup_policy'],
                                  spec['warmup_iterations_per_worker'],
                                  spec['warmup_pause_seconds']),
                                 ('all_workers', 48000, 0))
                session = BackendSession('/unused', spec)
                commands = []

                def command(args, log, **kwargs):
                    commands.append((args, log))
                    return json.dumps({'layout.json': {'lock_addr': 4096},
                                       'prepare.json': {}, 'warmup.json': warmup}.get(log, {}))

                session.counts = Mock(return_value=dict(active=0, values=[0]*16))
                session.faults = session.save = Mock()
                with patch.object(Session, 'run', side_effect=command), \
                        patch('session.time.sleep') as pause, \
                        patch('bench_session.validate_measurement',
                              wraps=run.runtime.validate_measurement) as validate:
                    if arm == 'native':
                        # Exercise the production 48,000-per-worker call and
                        # require separate preparation before worker warmup.
                        session.prepare()
                        labels = [label for _, label in commands]
                        self.assertLess(labels.index('prepare.json'), labels.index('warmup.json'))
                        preparation, = [args for args, label in commands if label == 'prepare.json']
                        self.assertEqual(preparation, [run.HERE/'client', '--prepare', '--cachelines', 1])
                        pause.assert_not_called()
                    else:
                        session.phase('warmup', 48000)
                args, = [args for args, label in commands if label == 'warmup.json']
                self.assertEqual(args[0], run.HERE/'client')  # No measured PMU wrapper.
                self.assertEqual(args[args.index('--cpus')+1], '2,7,11')
                self.assertEqual(args[args.index('--iterations')+1], 48000)
                actual, geometry, iterations = validate.call_args.args
                self.assertEqual((actual, iterations), (warmup, 48000))
                self.assertEqual((geometry['threads'], geometry['cpus'], geometry['cpu_nodes']),
                                 (3, cpus, nodes))
                self.assertNotIn('preparation_cpus', session.record)
                self.assertNotIn('measurement', session.record)
                self.assertNotIn('jit_before', session.record)

    def test_jit_measurement_starts_after_unmeasured_warmup(self):
        session = BackendSession.__new__(BackendSession)
        session.record = dict(arm='kdlock', threads=3, iterations=17,
                              hotlock_mode='adaptive', scenario='plain')
        session.loaded_kd = True
        session.save = Mock()
        events, counts = [], iter(('Y', 700, 650, 705, 654))

        def counter():
            events.append('counter')
            return str(next(counts))

        def publication():
            events.append('publication')
            return {'source': {'writers': 0}}

        def phase(label, iterations):
            self.assertEqual((label, iterations), ('measure', 17))
            self.assertEqual(session.record['jit_before'], 700)
            events.append(label)
            return dict(completed=51)

        session.publication, session.phase = publication, phase
        with patch.object(Path, 'read_text', side_effect=counter):
            session.measure()
        self.assertEqual(events, ['counter', 'publication', 'counter', 'counter',
                                  'measure', 'counter', 'publication', 'counter'])
        self.assertEqual(session.record['jit_bodies'], 5)
        self.assertEqual(session.record['jit_completions'], 4)
        self.assertEqual(session.record['jit_complete_share'], 4/51)
        self.assertEqual(session.record['jit_share'], 5/51)
        self.assertEqual(session.record['measurement']['completed'], 51)

    def test_functional_report_has_no_performance_scores(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out/'plan.json').write_text(json.dumps([
                dict(name='plain', scenario='plain', functional=True,
                     spin_entry_ratio_limit=4),
                dict(name='missing', scenario='early', functional=True),
                dict(name='historical', scenario='plain', functional=True,
                     spin_contention_pct=37)]))
            (out/'plain').mkdir()
            (out/'plain/session.json').write_text(json.dumps(dict(
                execution_status='PASS', drained=True, jit_bodies=9,
                jit_acceptance='PASS', measurement=dict(completed=10, wall_ns=100), jit_completions=9)))
            run.report(out)
            rows = json.loads((out/'functional.json').read_text())
            self.assertEqual(rows[0]['completed'], 10)
            self.assertEqual(rows[0]['spin_entry_ratio_limit'], 4)
            self.assertEqual(rows[0]['spin_contention_pct'], 'unrecorded')
            self.assertEqual(rows[1]['status'], 'NOT_RUN')
            self.assertFalse(rows[1]['drained'])
            self.assertEqual(rows[2]['spin_contention_pct'], 37)
            self.assertEqual(rows[2]['spin_entry_ratio_limit'], 'unrecorded')
            self.assertFalse((out/'summary.csv').exists())
            self.assertFalse((out/'summary.json').exists())
            self.assertFalse(any('throughput' in key or 'ns_op' in key for row in rows for key in row))

    def test_disabled_control_rejects_any_jit(self):
        record = dict(arm='kdlock', threads=4, jit_bodies=0,
                      hotlock_mode='adaptive', spin_delegate='off', jit_completions=0)
        check_jit_evidence(record)
        self.assertEqual(record['jit_acceptance'], 'DISABLED_CONTROL')
        with self.assertRaisesRegex(run.Failure, 'disabled control executed JIT'):
            check_jit_evidence(dict(record, jit_bodies=1, jit_completions=1))

    def test_policy_no_jit_is_not_protocol_acceptance(self):
        record = dict(arm='kdlock', threads=4, jit_bodies=0, hotlock_mode='adaptive', jit_completions=0)
        check_jit_evidence(record)
        self.assertEqual(record['jit_acceptance'], 'NO_JIT')
        check_jit_evidence(record := dict(record, jit_bodies=1, jit_completions=1))
        self.assertEqual(record['jit_acceptance'], 'PASS')

    def test_single_thread_native_completion_is_not_jit_acceptance(self):
        record = dict(arm='kdlock', threads=1, jit_bodies=0,
            hotlock_mode='adaptive', caller_shell='cold_clobber', scenario='plain', jit_completions=0)
        check_jit_evidence(record)
        self.assertEqual(record['jit_acceptance'], 'NO_JIT')

    def test_queue_depth_option_is_removed(self):
        argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                '--spin-hot-min-queue', '4']
        with patch.object(sys, 'argv', argv), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                run.main()
        self.assertEqual(result.exception.code, 2)

    def test_shell_selection_option_is_removed(self):
        # Old commands must fail explicitly rather than silently select a
        # different caller from the one recorded in their original evidence.
        for choice in ('on', 'off'):
            argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                    '--spin-cold-fastpath', choice]
            with self.subTest(choice=choice), patch.object(sys, 'argv', argv), \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    run.main()
                self.assertEqual(result.exception.code, 2)

    def test_small_plain_native_completion_is_not_jit_acceptance(self):
        for threads in (2, 3):
            with self.subTest(threads=threads):
                record = dict(arm='kdlock', threads=threads, jit_bodies=0,
                    hotlock_mode='adaptive', caller_shell='cold_clobber', scenario='plain', jit_completions=0)
                check_jit_evidence(record)
                self.assertEqual(record['jit_acceptance'], 'NO_JIT_LOW_CONTENTION')
                check_jit_evidence(record := dict(record, jit_bodies=1, jit_completions=1))
                self.assertEqual(record['jit_acceptance'], 'PASS')

    def test_nested_protocol_cases_still_require_jit(self):
        for threads in (2, 3, 4, 8, 20):
            for scenario in ('nested', 'early'):
                with self.subTest(threads=threads, scenario=scenario):
                    record = dict(arm='kdlock', threads=threads, jit_bodies=0,
                        hotlock_mode='adaptive', caller_shell='cold_clobber',
                        spin_entry_ratio_limit=0, scenario=scenario, jit_completions=0)
                    with self.assertRaisesRegex(run.Failure, 'no actual JIT'):
                        check_jit_evidence(record)
                    check_jit_evidence(record := dict(record, jit_bodies=1, jit_completions=1))
                    self.assertEqual(record['jit_acceptance'], 'PASS')

    def test_admission_mode_option_is_removed(self):
        # Old commands must not silently select a different admission contract.
        for choice in ('observe', 'adaptive'):
            argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                    '--hotlock-mode', choice]
            with self.subTest(choice=choice), patch.object(sys, 'argv', argv), \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    run.main()
            self.assertEqual(result.exception.code, 2)

    def test_high_contention_requires_jit(self):
        for threads in (20, 24, 28, 32, 36):
            record = dict(arm='kdlock', threads=threads, jit_bodies=0,
                hotlock_mode='adaptive', caller_shell='cold_clobber', scenario='plain', jit_completions=0)
            with self.assertRaisesRegex(run.Failure, 'no actual JIT'):
                check_jit_evidence(record)
            check_jit_evidence(record := dict(record, jit_bodies=1, jit_completions=1))
            self.assertEqual(record['jit_acceptance'], 'PASS')

    def test_contended_functional_plain_requires_jit(self):
        # Adaptive native completion is a valid performance result, but it
        # cannot satisfy an explicitly requested functional JIT positive.
        for threads in (2, 3, 4, 8, 16, 20):
            record = dict(arm='kdlock', threads=threads, jit_bodies=0,
                          functional=True, scenario='plain', jit_completions=0)
            with self.subTest(threads=threads):
                with self.assertRaisesRegex(run.Failure, 'no actual JIT'):
                    check_jit_evidence(record)
                check_jit_evidence(record := dict(record, jit_bodies=1, jit_completions=1))
                self.assertEqual(record['jit_acceptance'], 'PASS')

    def test_hash_layout_rejects_scheduling_enabled_module(self):
        layout = dict(workload='rcuht', buckets=1024, entries=4096,
                      key_range=8192, resched=0)
        hash_layout(layout)
        with self.assertRaisesRegex(run.Failure, 'hash payload configuration differs'):
            hash_layout(dict(layout, resched=1))

    def test_no_counter_quiescence_rejects_busy_or_old_provider(self):
        params = dict(target_lock=4096, komb_batch_size=1024, quiescent=1)
        tc_quiescent(params)
        for bad in (dict(params, quiescent=0), dict(params, delegated=0, completed=0)):
            with self.assertRaises(run.Failure):
                tc_quiescent(bad)

    def test_inline_audit_rejects_compiler_stack_prologue(self):
        # An extra compiler push invalidates the saved return-address offset
        # even though all six upstream register pushes still appear later.
        bad = '0000 <komb_context_switch>:\n 0: push %rbp\n 1: mov %rsp,%rbp\n'
        with self.assertRaisesRegex(ValueError, 'unexpected stack/register layout'):
            audit_context(bad)

    def test_hash_timed_matrix(self):
        plan = run.make_plan(Namespace(workload='rcuht', cachelines=None,
            threads=[1,2,3,4,5,6,7,8,12,16,20,24,28,32,36], repeats=3,
            iterations=100000, backends=['native', 'tclock', 'kdlock'],
            duration_ms=2000, collector_cpu=38))
        self.assertEqual(len(plan), 135)
        self.assertTrue(all(s['workload'] == 'rcuht' and s['cachelines'] == 0 and
                            s['measurement_mode'] == 'timed_peak' and
                            s['warmup_iterations_per_worker'] == 48000 for s in plan))

    def test_hash_matrix_and_outcome_oracle(self):
        plan = run.make_plan(Namespace(workload='rcuht', cachelines=None,
            threads=[1, 4, 8, 16, 20], repeats=2, iterations=100000,
            backends=['native', 'tclock', 'kdlock']))
        self.assertEqual(len(plan), 30)
        self.assertTrue(all(s['workload'] == 'rcuht' and s['cachelines'] == 0 for s in plan))
        spec = dict(workload='rcuht', cachelines=0, threads=1, cpus=[0])
        measurement = dict(schema=1, complete=True, data_ok=True, workload='rcuht',
            hash_integrity_ok=True, cachelines=0, threads=1, iterations=10,
            completed=10, worker_cpu_ns=100, started_ns=100, finished_ns=300,
            wall_ns=200, before=[3, 1, 1, 1] + [0]*12,
            after=[13, 4, 3, 6] + [0]*12,
            workers=[dict(cpu=0, observed_cpu=0, error=0, completed=10,
                          cpu_ns=100, finished_ns=300)])
        run.runtime.validate_measurement(measurement, spec, 10)
        # Lost/doubled outcomes and failed structure checks cannot be OK samples.
        for mutation in ('lost_outcome', 'extra_operation', 'bad_structure', 'wrong_payload'):
            broken = copy.deepcopy(measurement)
            if mutation == 'lost_outcome': broken['after'][1] -= 1
            if mutation == 'extra_operation': broken['after'][0] += 1
            if mutation == 'bad_structure': broken['hash_integrity_ok'] = False
            if mutation == 'wrong_payload': broken['workload'] = 'cacheline'
            with self.assertRaises(run.Failure):
                run.runtime.validate_measurement(broken, spec, 10)

    def test_cli_defaults_to_three_rounds(self):
        # Performance defaults to repeated measurements for both payloads;
        # explicit one-round performance and functional runs remain available.
        for extra, sessions, repeats in (
                ([], 45, 3), (['--workload', 'rcuht'], 45, 3),
                (['--repeats', '1'], 15, 1),
                (['--functional', '--backends', 'kdlock', '--repeats', '1'], 5, 1)):
            with self.subTest(args=extra):
                output = io.StringIO()
                argv = ['run.py', '--output', '/tmp/unused', '--dry-run', *extra]
                with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(output):
                    self.assertEqual(run.main(), 0)
                plan = json.loads(output.getvalue())
                self.assertEqual(len(plan), sessions)
                self.assertEqual(len({s['name'] for s in plan}), sessions)
                self.assertEqual({s['cachelines'] for s in plan},
                                 {0} if 'rcuht' in extra else {1})
                self.assertEqual({s['repeat'] for s in plan}, set(range(repeats)))
                self.assertEqual({s['hotlock_mode'] for s in plan if s['arm'] == 'kdlock'},
                                 {'adaptive'})

    def test_functional_mode_requires_explicit_single_round(self):
        argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                '--functional', '--backends', 'kdlock']
        with patch.object(sys, 'argv', argv):
            with self.assertRaisesRegex(run.Failure, 'functional mode requires'):
                run.main()

    def test_native_tclock_functional_controls_have_no_scores(self):
        for family in ('spin', 'mutex'):
            output = io.StringIO()
            argv = ['run.py', '--output', '/tmp/unused', '--dry-run', '--functional',
                    '--backends', 'native', 'tclock', '--repeats', '1',
                    '--threads', '8', '--cachelines', '1', '--iterations', '10000']
            with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(output):
                self.assertEqual(run.main(family), 0)
            plan = json.loads(output.getvalue())
            self.assertEqual(len(plan), 2)
            self.assertEqual({s['arm'] for s in plan}, {'native', 'tclock'})
            self.assertTrue(all(s['functional'] and not s['performance_accepted']
                                and s['lock_kind'] == family and s['duration_ms'] == 0
                                and s['iterations'] == 10000 for s in plan))
            with tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                (out/'plan.json').write_text(json.dumps(plan))
                for spec in plan:
                    (out/spec['name']).mkdir()
                    record = dict(spec, execution_status='OK', drained=True,
                                  measurement=dict(completed=80000, wall_ns=100000))
                    (out/spec['name']/'session.json').write_text(json.dumps(record))
                run.report(out)
                rows = json.loads((out/'functional.json').read_text())
                self.assertEqual({r['arm'] for r in rows}, {'native', 'tclock'})
                self.assertTrue(all(r['completed'] == 80000 and r['drained'] and
                                    r['jit_acceptance'] == 'NOT_APPLICABLE' and
                                    not r['performance_accepted'] for r in rows))
                self.assertFalse((out/'summary.json').exists())
                self.assertFalse((out/'summary.csv').exists())
                self.assertFalse(any('throughput' in key or 'ns_op' in key
                                     for row in rows for key in row))

    def test_cli_small_and_numa_thread_matrix(self):
        # The 64-worker point explicitly shares collector 63; smaller cohorts do not.
        output = io.StringIO()
        argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                '--cachelines', '1', '--duration-ms', '2000', '--collector-cpu', '63',
                '--cpus', '0-63', '--share-collector',
                '--threads', '1', '2', '3', '4', '5', '6', '7', '8',
                '12', '16', '20', '24', '28', '32', '36',
                '40', '44', '48', '52', '56', '60', '64']
        with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(output):
            self.assertEqual(run.main(), 0)
        plan = json.loads(output.getvalue())
        self.assertEqual(len(plan), 198)
        self.assertEqual(len({s['name'] for s in plan}), 198)
        self.assertEqual({s['threads'] for s in plan},
                         set(range(1, 9)) | set(range(12, 65, 4)))
        self.assertEqual({s['repeat'] for s in plan}, {0, 1, 2})
        for spec in plan:
            self.assertEqual(spec['cpus'], list(range(spec['threads'])))
            self.assertEqual(spec['collector_shared'], spec['threads'] == 64)
            self.assertEqual(spec['collector_cpu'] in spec['cpus'], spec['collector_shared'])
            self.assertEqual(spec['cpu_heat_policy'],
                             'mcs_reset1024_shift10_lock512_head6' if spec['arm'] == 'kdlock' else 'not_applicable')
            self.assertEqual(spec['spin_entry_ratio_limit'],
                             run.DEFAULT_SPIN_ENTRY_RATIO_LIMIT if spec['arm'] == 'kdlock' else None)
            self.assertNotIn('spin_contention_pct', spec)
            self.assertNotIn('spin_hot_min_queue', spec)
            self.assertNotIn('spin_cold_fastpath', spec)


    def test_shared_collector_rejects_unlabelled_or_partial_overlap(self):
        args = dict(cachelines=[1], threads=[64], repeats=3, iterations=100,
                    backends=['native'], duration_ms=2000, collector_cpu=63,
                    cpus=list(range(64)))
        with self.assertRaisesRegex(run.Failure, 'collector CPU'):
            run.make_plan(Namespace(**args))
        for change in (dict(collector_cpu=62), dict(threads=[60]),
                       dict(cpus=list(range(1,65))), dict(share_collector=1),
                       dict(duration_ms=0)):
            with self.subTest(change=change), self.assertRaises(run.Failure):
                run.make_plan(Namespace(**(args | {'share_collector': True} | change)))


    def test_contention_cli_preserves_explicit_threshold_and_zero_bypass(self):
        # A diagnostic zero must survive parsing;
        # non-KD baselines have no contention-policy setting.
        for threshold in (0, 2, 4, 1 << 31):
            with self.subTest(threshold=threshold):
                output = io.StringIO()
                argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                        '--cachelines', '1', '--threads', '4', '--repeats', '1',
                        '--spin-entry-ratio-limit', str(threshold)]
                with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(output):
                    self.assertEqual(run.main(), 0)
                plan = json.loads(output.getvalue())
                self.assertEqual(len(plan), 3)
                for spec in plan:
                    self.assertEqual(spec['spin_entry_ratio_limit'],
                                     threshold if spec['arm'] == 'kdlock' else None)

    def test_contention_threshold_rejects_out_of_range_and_non_integer(self):
        for threshold in ('-1', '1', '3', '4294967296', '2.5'):
            with self.subTest(threshold=threshold):
                argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                        '--spin-entry-ratio-limit', threshold]
                with patch.object(sys, 'argv', argv), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as result:
                        run.main()
                self.assertEqual(result.exception.code, 2)
        for threshold in (-1, 1, 3, 1 << 32):
            with self.subTest(plan_threshold=threshold):
                with self.assertRaisesRegex(run.Failure, 'invalid spin entry ratio limit'):
                    run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=1,
                        iterations=100, backends=['kdlock'], spin_entry_ratio_limit=threshold))

    def test_percentage_option_is_removed(self):
        # The new inverse ratio must not silently reinterpret an old percent.
        argv = ['run.py', '--output', '/tmp/unused', '--dry-run',
                '--spin-contention-pct', '100']
        with patch.object(sys, 'argv', argv), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                run.main()
        self.assertEqual(result.exception.code, 2)

    def test_empty_summary_has_no_winner(self):
        plan = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=2,
            iterations=100, backends=['native', 'tclock', 'kdlock']))
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plan)
            run.report(out)
            for row in json.loads((out/'summary.json').read_text()):
                self.assertEqual(row['valid'], 0)
                for key in ('best_session', 'best_throughput_ops_s',
                            'best_amortized_ns_op', 'throughput_over_linux',
                            'min_throughput_ops_s', 'median_throughput_ops_s',
                            'max_throughput_ops_s', 'throughput_spread_pct'):
                    self.assertIsNone(row[key])

    def test_matrix_and_balanced_order(self):
        plan = run.make_plan(Namespace(cachelines=[1, 16], threads=[1, 4, 8, 16, 20],
            repeats=3, iterations=100000, backends=['native', 'tclock', 'kdlock']))
        self.assertEqual(len(plan), 90)
        self.assertEqual([(s['arm'], s['hotlock_mode']) for s in plan[:9]],
                         [('native', 'not_applicable'), ('tclock', 'not_applicable'),
                          ('kdlock', 'adaptive'), ('tclock', 'not_applicable'),
                          ('kdlock', 'adaptive'), ('native', 'not_applicable'),
                          ('kdlock', 'adaptive'), ('native', 'not_applicable'),
                          ('tclock', 'not_applicable')])
        self.assertTrue(all(s['api_mode'] == 'direct' for s in plan))

    def test_summary_excludes_bad_and_undrained_samples(self):
        plan = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=3,
            iterations=100, backends=['native', 'tclock', 'kdlock']))
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plan)
            for spec in plan:
                folder = out/spec['name']; folder.mkdir()
                # Vary rates between rounds; reject the fastest corrupt/undrained rows.
                bad = spec['repeat'] == 2 and spec['arm'] != 'native'
                rate = {'native': 1, 'tclock': 2, 'kdlock': 4}[spec['arm']] * (spec['repeat'] + 1)
                record = dict(spec, jit_bodies=0, jit_completions=0, execution_status='OK', drained=not (bad and spec['arm'] == 'kdlock'),
                    measurement=dict(completed=400, wall_ns=1 if bad else 400000/rate,
                                     data_ok=not (bad and spec['arm'] == 'tclock'), complete=True))
                run.write_json(folder/'session.json', record)
            run.report(out)
            rows = {r['arm']: r for r in json.loads((out/'summary.json').read_text())}
            for arm, rate, repeat in [('native', 3, 2), ('tclock', 4, 1), ('kdlock', 8, 1)]:
                self.assertEqual(rows[arm]['throughput_over_linux'], rate / 3)
                self.assertEqual(rows[arm]['valid'], 3 if arm == 'native' else 2)
                self.assertEqual(rows[arm]['best_throughput_ops_s'], rate * 1e6)
                self.assertAlmostEqual(rows[arm]['best_amortized_ns_op'], 1000 / rate)
                winner = next(s['name'] for s in plan if s['arm'] == arm and s['repeat'] == repeat)
                self.assertEqual(rows[arm]['best_session'], winner)
                self.assertEqual(rows[arm]['comparison_policy'], 'best_valid_throughput')
                minimum, median = {'native': (1, 2), 'tclock': (2, 3),
                                   'kdlock': (4, 6)}[arm]
                self.assertEqual(rows[arm]['sessions'], 3)
                self.assertEqual(rows[arm]['min_throughput_ops_s'], minimum * 1e6)
                self.assertEqual(rows[arm]['median_throughput_ops_s'], median * 1e6)
                self.assertEqual(rows[arm]['max_throughput_ops_s'], rate * 1e6)
                self.assertAlmostEqual(rows[arm]['throughput_spread_pct'],
                                       (rate - minimum) / median * 100)
            self.assertEqual(len(json.loads((out/'records.json').read_text())), 9)

    def test_summary_preserves_historical_admission_identity(self):
        # Reporting old frozen records must not merge their admission modes.
        # The live planner below creates adaptive sessions only.
        plan = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=2,
            iterations=100, backends=['native', 'tclock', 'kdlock']))
        plan += [dict(spec, name=spec['name'].replace('-adaptive', '-observe'),
                      hotlock_mode='observe') for spec in plan if spec['arm'] == 'kdlock']
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plan)
            for spec in plan:
                folder = out/spec['name']; folder.mkdir()
                mode = spec['hotlock_mode']
                rate = {'not_applicable': 1, 'observe': 2, 'adaptive': 4}[mode]
                bad = mode == 'adaptive' and spec['repeat'] == 1
                run.write_json(folder/'session.json', dict(spec,
                    jit_bodies=0, jit_completions=0, execution_status='OK', drained=not bad,
                    measurement=dict(completed=400, wall_ns=1 if bad else 400000/rate,
                                     data_ok=True, complete=True)))
            run.report(out)
            rows = {(r['arm'], r['hotlock_mode']): r
                    for r in json.loads((out/'summary.json').read_text())}
            self.assertEqual(len(rows), 4)
            for mode, rate, count in [('observe', 2, 2), ('adaptive', 4, 1)]:
                row = rows['kdlock', mode]
                self.assertEqual(row['sessions'], 2)
                self.assertEqual(row['valid'], count)
                self.assertEqual(row['best_throughput_ops_s'], rate * 1e6)
                self.assertEqual(row['throughput_over_linux'], rate)
                self.assertTrue(row['best_session'].endswith('-' + mode))
            self.assertEqual(rows['native', 'not_applicable']['sessions'], 2)
            self.assertEqual(rows['tclock', 'not_applicable']['sessions'], 2)

    def test_default_heat_caller_uses_one_adaptive_session(self):
        plan = run.make_plan(Namespace(cachelines=[1], threads=[1], repeats=1,
            iterations=100, backends=['native', 'tclock', 'kdlock']))
        self.assertEqual(len(plan), 3)
        self.assertEqual(len({s['name'] for s in plan}), 3)
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plan)
            for spec in plan:
                folder = out/spec['name']; folder.mkdir()
                run.write_json(folder/'session.json', dict(spec,
                    jit_bodies=0, jit_completions=0, execution_status='OK', drained=True,
                    measurement=dict(completed=100, wall_ns=100000,
                                     data_ok=True, complete=True)))
                if spec['arm'] == 'kdlock':
                    self.assertEqual(spec['caller_abi'], 'clobber')
                    self.assertEqual(spec['caller_shell'], 'cold_clobber')
                    self.assertEqual(spec['cookie_storage'], 'percpu_direct_gate')
                    self.assertEqual(spec['delegation_batch_limit'], 1024)
                    self.assertNotIn('spin_cold_fastpath', spec)
            run.report(out)
            rows = json.loads((out/'summary.json').read_text())
            self.assertEqual(len(rows), 3)
            self.assertEqual({r['hotlock_mode'] for r in rows if r['arm'] == 'kdlock'},
                             {'adaptive'})
            self.assertTrue(all('spin_cold_fastpath' not in r for r in rows))
            self.assertTrue(all(r['sessions'] == r['valid'] == 1 for r in rows))
            self.assertTrue(all(r['min_throughput_ops_s'] == r['median_throughput_ops_s'] ==
                                r['max_throughput_ops_s'] == r['best_throughput_ops_s']
                                for r in rows))
            self.assertTrue(all(r['throughput_spread_pct'] is None for r in rows))
            self.assertEqual({r['cookie_storage'] for r in rows}, {'percpu_direct_gate', 'not_applicable'})

    def test_summary_keeps_gate_storage_separate(self):
        # An old indirect-gate archive must not supply the winner for the new
        # direct scalar even when admission and workload settings match.
        base = run.make_plan(Namespace(cachelines=[1], threads=[1], repeats=1,
            iterations=100, backends=['kdlock']))[0]
        plans = [dict(base, name=base['name']+'-'+storage, cookie_storage=storage)
                 for storage in ('percpu_rate_hot', 'percpu_direct_gate')]
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plans)
            for index, spec in enumerate(plans):
                folder = out/spec['name']; folder.mkdir()
                run.write_json(folder/'session.json', dict(spec,
                    jit_bodies=0, jit_completions=0, execution_status='OK', drained=True,
                    measurement=dict(completed=100, wall_ns=100000*(index+1),
                                     data_ok=True, complete=True)))
            run.report(out)
            rows = {r['cookie_storage']: r
                    for r in json.loads((out/'summary.json').read_text())}
            self.assertEqual(set(rows), {'percpu_rate_hot', 'percpu_direct_gate'})
            for index, spec in enumerate(plans):
                row = rows[spec['cookie_storage']]
                self.assertEqual(row['valid'], 1)
                self.assertEqual(row['best_session'], spec['name'])
                self.assertEqual(row['best_throughput_ops_s'], 1e6/(index+1))

    def test_summary_keeps_heat_policies_separate(self):
        base = run.make_plan(Namespace(cachelines=[1], threads=[2], repeats=1,
            iterations=100, backends=['kdlock']))[0]
        # Keep each resettable cadence separate from percentage samplers and
        # older native-head policies, even when their ratio cutoffs match.
        plans = [dict(base, name=base['name']+'-'+policy, cpu_heat_policy=policy)
                 for policy in ('mcs_reset1024_shift10_lock512_head6', 'mcs_reset_shift9_head6', 'mcs_entry_ratio512_head6', 'mcs_entry_ratio512_head5', 'mcs_entry_ratio512_simple', 'mcs_entry_ratio512_batch128', 'mcs_entry_ratio512_confirm2', 'mcs_entry_ratio512', 'mcs_entry_ratio',
                                'mcs_entry', 'historical_queue_depth')]
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plans)
            for spec in plans:
                folder = out/spec['name']; folder.mkdir()
                run.write_json(folder/'session.json', dict(spec,
                    execution_status='OK', drained=True,
                    jit_bodies=int(spec['cpu_heat_policy'] == 'mcs_reset1024_shift10_lock512_head6'),
                    measurement=dict(completed=200, wall_ns=100000,
                                     data_ok=True, complete=True), jit_completions=int(spec['cpu_heat_policy'] == 'mcs_reset1024_shift10_lock512_head6')))
            run.report(out)
            rows = json.loads((out/'summary.json').read_text())
            self.assertEqual(len(rows), 11)
            self.assertEqual({r['cpu_heat_policy'] for r in rows},
                             {'mcs_reset1024_shift10_lock512_head6', 'mcs_reset_shift9_head6', 'mcs_entry_ratio512_head6', 'mcs_entry_ratio512_head5', 'mcs_entry_ratio512_simple', 'mcs_entry_ratio512_batch128', 'mcs_entry_ratio512_confirm2', 'mcs_entry_ratio512', 'mcs_entry_ratio',
                              'mcs_entry', 'historical_queue_depth'})
            self.assertEqual(sum(r['actual_jit_sessions'] for r in rows), 1)

    def test_summary_keeps_contention_thresholds_separate(self):
        # Historical percentages and current limits each remain independent
        # tuning inputs, including zero's bypass in either unit.
        plans = []
        rates = {('spin_entry_ratio_limit', 0): 1,
                 ('spin_entry_ratio_limit', 2): 2,
                 ('spin_entry_ratio_limit', 4): 4,
                 ('spin_contention_pct', 0): 8,
                 ('spin_contention_pct', 37): 16,
                 ('spin_contention_pct', 100): 32}
        for field, threshold in rates:
            candidate = run.make_plan(Namespace(cachelines=[1], threads=[4], repeats=2,
                iterations=100, backends=['kdlock']))
            for spec in candidate:
                if field == 'spin_contention_pct':
                    del spec['spin_entry_ratio_limit']
                    spec['cpu_heat_policy'] = 'mcs_entry_ratio512_head6'
                spec[field] = threshold
                spec['name'] += f'-{field}-{threshold}'
                plans.append(spec)
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            run.write_json(out/'plan.json', plans)
            for spec in plans:
                folder = out/spec['name']; folder.mkdir()
                field = ('spin_contention_pct' if 'spin_contention_pct' in spec
                         else 'spin_entry_ratio_limit')
                rate = rates[field, spec[field]] * (spec['repeat'] + 1)
                run.write_json(folder/'session.json', dict(spec,
                    execution_status='OK', drained=True, jit_bodies=1,
                    measurement=dict(completed=400, wall_ns=400000/rate,
                                     data_ok=True, complete=True), jit_completions=1))
            run.report(out)
            rows = json.loads((out/'summary.json').read_text())
            self.assertEqual(len(rows), len(rates))
            self.assertEqual({row['hotlock_mode'] for row in rows}, {'adaptive'})
            observed = set()
            for row in rows:
                field = ('spin_contention_pct' if row['spin_contention_pct'] != 'unrecorded'
                         else 'spin_entry_ratio_limit')
                threshold = row[field]
                observed.add((field, threshold))
                self.assertEqual(row['sessions'], 2)
                self.assertEqual(row['valid'], 2)
                self.assertEqual(row['best_throughput_ops_s'], rates[field, threshold] * 2e6)
                self.assertEqual(row['best_amortized_ns_op'], 500 / rates[field, threshold])
                self.assertTrue(row['best_session'].endswith(f'-{field}-{threshold}'))
            self.assertEqual(observed, set(rates))

    def test_provider_load_has_no_admission_mode_parameter(self):
        session = BackendSession.__new__(BackendSession)
        session.record = dict(arm='kdlock', hotlock_mode='adaptive',
                              spin_entry_ratio_limit=4, spin_delegate='on', spin_prefetch=0)
        commands = []

        def command(args, log):
            commands.append((args, log))
            if log == 'load-kdlock.log':
                raise RuntimeError('stop after provider command')

        session.run = command
        with self.assertRaisesRegex(RuntimeError, 'stop after provider command'):
            session.prepare()
        args, = [args for args, log in commands if log == 'load-kdlock.log']
        self.assertFalse(any(str(arg).startswith('hotlock_mode=') for arg in args))
        self.assertFalse(any(str(arg).startswith('spin_contention_pct=') for arg in args))
        self.assertIn('spin_entry_ratio_limit=4', args)
        self.assertIn('spin_delegate=1', args)
        self.assertIn('spin_prefetch=0', args)
        self.assertIn('bench_complete_probe=1', args)

    def test_provider_enables_returned_body_probe(self):
        for workload in ('cacheline', 'rcuht'):
            session = BackendSession.__new__(BackendSession)
            session.record = dict(arm='kdlock', workload=workload,
                                  spin_entry_ratio_limit=2, spin_delegate='on', spin_prefetch=2)
            commands = []

            def command(args, log):
                if log == 'load-kdlock.log':
                    commands.append(args)
                    raise RuntimeError('stop after provider command')

            session.run = command
            with self.assertRaisesRegex(RuntimeError, 'stop after provider command'):
                session.prepare()
            self.assertIn('bench_complete_probe=1', commands[0])


if __name__ == '__main__':
    unittest.main()
