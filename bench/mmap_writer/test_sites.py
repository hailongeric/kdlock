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
