"""Exact ELF-call and sleeping writer witness checks; run only in the VM."""
import copy
import unittest

import sites


ASM = '''0000000000001000 <vm_mmap_pgoff>:
    1000: 0f 1f 44 00 00       nopl 0x0(%rax,%rax,1)
    1005: e8 f6 00 00 00       call 1100 <down_write_killable>
    100a: 90                   nop
'''


class WriterSites(unittest.TestCase):
    def assembly(self, name, start, target, address, *, tail=False):
        opcode = bytes([0xe9 if tail else 0xe8])+(address-start-5).to_bytes(4, 'little', signed=True)
        return (f'{start:016x} <{name}>:\n {start:x}: {opcode.hex(" ")} '
                f'{"jmp" if tail else "call"} {address:x} <{target}>\n {start+5:x}: 90 nop\n')

    def test_exact_direct_call_return(self):
        row = sites.call_return(ASM, 'vm_mmap_pgoff')
        self.assertEqual(row['return_offset'], 10)
        self.assertEqual(row['return_address'], '0x100a')
        self.assertEqual(row['target_address'], '0x1100')

    def test_wrong_bytes_target_boundary_and_ambiguity_are_refused(self):
        variants = [ASM.replace('e8 f6', 'e8 f5'),
                    ASM.replace('e8 f6', 'e9 f6'),
                    ASM.replace('100a:', '100b:'),
                    ASM.replace('<down_write_killable>', '<down_write_killable+0x1>'),
                    ASM.replace('call 1100', 'jmp 1100'),
                    ASM.replace('call 1100', 'call *0x1100'),
                    ASM.replace('    100a: 90                   nop\n', ''),
                    ASM+'    100b: e8 f0 00 00 00 call 1100 <down_write_killable>\n'
                        '    1010: 90 nop\n',
                    ASM+ASM]
        for text in variants:
            with self.subTest(text=text), self.assertRaises(sites.rt.Failure):
                sites.call_return(text, 'vm_mmap_pgoff')

    def test_another_function_call_cannot_be_borrowed(self):
        text = ASM.replace('<vm_mmap_pgoff>', '<unrelated>')
        with self.assertRaises(sites.rt.Failure):
            sites.call_return(text, 'vm_mmap_pgoff')

    def test_gate_call_and_tail_edges_keep_only_real_return_words(self):
        writer, gate, slow = 'kd_mmap_down_write_killable', 'kd_mmap_mutex_local_lock_signal', 'kd_mmap_local_lock_slow_signal'
        for tail in (False, True):
            assembly = {writer:self.assembly(writer,0x1000,gate,0x2000),
                        gate:self.assembly(gate,0x2000,slow,0x3000,tail=tail),
                        slow:self.assembly(slow,0x3000,'schedule',0x4000)}
            chain=sites.gate_chain(assembly,writer,43)
            self.assertEqual(chain['waiter'],slow)
            self.assertEqual(chain['wait_returns'],[5,5])
            self.assertEqual([frame['symbol'] for frame in chain['intermediate']],
                             [writer] if tail else [gate,writer])
            self.assertEqual(chain['edges'][1]['kind'],'tail' if tail else 'call')
            self.assertTrue(chain['waiter_argument'].endswith('|'+writer+'@5'))
            bad=dict(assembly);bad[gate]=bad[gate].replace('fb 0f','fa 0f')
            with self.assertRaises(sites.rt.Failure):sites.gate_chain(bad,writer,43)

    def test_outlined_scheduler_keeps_its_actual_caller_return(self):
        writer, gate, slow, scheduling = ('kd_mmap_down_write_killable', 'kd_mmap_mutex_local_lock_signal',
                                         'kd_mmap_local_lock_slow_signal', 'kd_mmap_local_schedule')
        assembly={writer:self.assembly(writer,0x1000,gate,0x2000),
                  gate:self.assembly(gate,0x2000,slow,0x3000,tail=True),
                  slow:self.assembly(slow,0x3000,scheduling,0x5000),
                  scheduling:self.assembly(scheduling,0x5000,'schedule',0x4000)}
        chain=sites.gate_chain(assembly,writer,43)
        self.assertEqual(chain['waiter'],scheduling)
        self.assertEqual(chain['intermediate'],[dict(symbol=slow,return_offsets=[5]),dict(symbol=writer,return_offsets=[5])])
        bad=dict(assembly);bad[slow]+=' 3006: e8 f5 0f 00 00 call 4000 <schedule>\n 300b: 90 nop\n'
        with self.assertRaises(sites.rt.Failure):sites.gate_chain(bad,writer,43)

    def test_tail_target_and_intermediate_description_are_bounded(self):
        text=self.assembly('gate',0x2000,'slow',0x3000,tail=True)
        for bad in (text.replace('e9','e8'),text.replace('fb 0f','fa 0f'),text.replace('jmp','jmp *')):
            with self.assertRaises(sites.rt.Failure):sites.linked_edge(bad,'gate','slow')
        chain=dict(waiter='slow',intermediate=[dict(symbol='writer',return_offsets=[12,20])])
        self.assertEqual(sites.waiter_argument(chain),'slow|writer@12:20')
        for frames in ([dict(symbol='writer',return_offsets=[0])],
                       [dict(symbol='writer',return_offsets=[1,2,3])],
                       [dict(symbol='writer|other',return_offsets=[1])],
                       [dict(symbol='writer',return_offsets=[1])]*7):
            with self.assertRaises(sites.rt.Failure):sites.waiter_argument(dict(waiter='slow',intermediate=frames))

    def test_python_proof_requires_the_same_intermediate_call_returns(self):
        mapping=sites.common.module('writer_chain_test_mapping',sites.ROOT/'tests/kernel/mmap_lock/mapping.py')
        original=mapping.SITES
        mapping.SITES=dict(adapter='adapter',sites={'vm_mmap_pgoff':dict(return_offset=10)},chains={'kd':dict(
            waiter='slow',wait_returns=[5,9],adapter_return=43,
            intermediate=[dict(symbol='writer',return_offsets=[12,20])])})
        row=dict(proof='EXACT_MMAP_WRITER_CHAIN',acquire='adapter',caller='vm_mmap_pgoff',
                 waiter='slow',wait_return_offset=5,adapter_return_offset=43,return_offset=10,
                 raw_stack='[<0>] slow+0x5/0x80\n[<0>] writer+0xc/0x80\n[<0>] adapter+0x2b/0x80\n'
                           '[<0>] vm_mmap_pgoff+0xa/0x100\n',
                 state_before='D',state_after='D',wchan_before='slow',wchan_after='slow',
                 schedstat_before='1 2 3\n',schedstat_after='1 2 3\n')
        try:
            mapping.chain_proof(row,'kd')
            for change in (dict(raw_stack=row['raw_stack'].replace('writer+0xc/','writer+0xd/')),
                           dict(raw_stack=row['raw_stack'].replace('[<0>] writer+0xc/0x80\n','')),
                           dict(raw_stack=row['raw_stack'].replace('writer+','other+')),
                           dict(state_after='R'),dict(schedstat_after='2 2 3\n')):
                with self.assertRaises(sites.rt.Failure):mapping.chain_proof(dict(row,**change),'kd')
        finally:
            mapping.SITES=original

    def witness(self):
        return dict(proof='FILTERED_SCHED_RETURN_SITE', acquire='down_write_killable',
                    caller='vm_mmap_pgoff', return_offset=10,
                    raw_stack='[<0>] vm_mmap_pgoff+0xa/0x100\n[<0>] other+0x4/0x10\n',
                    state_before='D', state_after='D', wchan_before='vm_mmap_pgoff',
                    wchan_after='vm_mmap_pgoff', schedstat_before='100 200 3\n',
                    schedstat_after='100 200 3\n')

    def test_elf_offset_and_sleeping_task_bracket_required(self):
        captured = dict(sites={'vm_mmap_pgoff': sites.call_return(ASM, 'vm_mmap_pgoff')})
        row = self.witness()
        sites.validate_witness(row, captured)
        changes = [dict(return_offset=11), dict(state_before='R'), dict(state_after='R'),
                   dict(wchan_before='rwsem_down_write_slowpath'), dict(wchan_after='other'),
                   dict(schedstat_after='101 200 3\n'), dict(schedstat_before='x y z', schedstat_after='x y z'),
                   dict(proof='GENERIC_QUEUE'), dict(acquire='down_read'),
                   dict(raw_stack='[<0>] other+0x4/0x10\n[<0>] vm_mmap_pgoff+0xa/0x100\n'),
                   dict(raw_stack='[<0>] vm_mmap_pgoff+0xb/0x100\n')]
        for change in changes:
            bad = copy.deepcopy(row)
            bad.update(change)
            with self.subTest(change=change), self.assertRaises(sites.rt.Failure):
                sites.validate_witness(bad, captured)


if __name__ == '__main__':
    unittest.main()
