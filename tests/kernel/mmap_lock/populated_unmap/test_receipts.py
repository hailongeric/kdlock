#!/usr/bin/env python3
"""Guest-only negative controls for real removal and exact ACK evidence."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('unmap_runner', Path(__file__).with_name('run.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def pages():
    result=[]
    for i in range(48):
        value=1+i*3+(16<=i<32);h=1469598103934665603
        for _ in range(4096):h=((h^value)*1099511628211)&((1<<64)-1)
        result.append(dict(address=(100*(1+i//16)+i%16)*4096,pfn=1000+i,initial_pfn=1000+i,
                           hash=h,mapcount=0,refs_before_drop=1,charged_same=1,locked=0,group=i,page=int(16<=i<32)))
    return result


def fixture():
    origins = lambda first: [dict(tid=100+i, start=(first+i)*4096, end=(first+i+1)*4096, fault_code=1,invalidated=1) for i in range(16)]
    a = dict(calls=16, removed=16, delegated=15, native=0, post_ban=0,
             handbacks=0, acks=0, cancelled=0, refused=0, native_only=0, failed=0, populated=16, populated_remote=15, origins=origins(100))
    b = dict(a, calls=32, native=16, handbacks=15, acks=15, refused=1, native_only=1, origins=origins(200))
    c = dict(b, calls=48, native=32, post_ban=16, origins=origins(300))
    return dict(width=1,pin_total=48,rollback_checked=0,mode='body', errors=0, checks=300000, idle=1, groups=48,
                mm=0xabc, gate=0xdef, reader_peak=2, pending_peak=16, completed=48,
                cleanup_calls=144, late_fault_blocked=1, late_fault_tid=999, late_fault_code=0, late_value=0, pins_owned=0, pins_released=48, pages=pages(),
                late_fault_stack='kd_mmap_down_read\ndo_user_addr_fault', phases=[a, b, c],
                after_cleanup=dict(c, calls=192, native=176, post_ban=160))


DONE = ''.join(f'KD_MM_UNMAP done mm=abc id={i+1} origin={100+i} executor=100 '
               f'start={(100+i)*4096:x} end={(101+i)*4096:x} result=0\n' for i in range(1, 16))
PHYSICAL = ''.join(f'KD_MM_POPULATED done mm=abc id={i+1} origin={100+i} executor=100 '
    f'start={(100+i)*4096:x} end={(101+i)*4096:x} pfn={1000+i:x} pte_none=1 mapcount=0 tables_retained=1\n' for i in range(1,16))
ACKS = ''.join(f'KD_MM_UNMAP {kind} mm=abc id={i+17} origin={100+i} executor=100 '
               f'start={(200+i)*4096:x} end={(201+i)*4096:x}\n'
               for i in range(1, 16) for kind in ('handback', 'ack'))


class Receipts(unittest.TestCase):
    def test_every_page_of_a_remote_range(self):
        done = [('abc','2','101','100','10000','14000')]
        row = dict(width=4, pages=[dict(address=0x10000+i*4096, initial_pfn=1000+i) for i in range(4)])
        lines = [f'KD_MM_POPULATED_RANGE done mm=abc id=2 origin=101 executor=100 '
                 f'start=10000 end=14000 index={i} pages=4 pfn={1000+i:x} '
                 'pte_none=1 mapcount=0 tables_retained=1\n' for i in range(4)]
        log = ''.join(lines)
        self.assertEqual(runner.physical_records(row, log, done), 4)
        for bad in (''.join(lines[:3]), log+lines[-1], log.replace('index=3','index=2'),
                    log.replace('pfn=3eb','pfn=3ea'), log.replace('pages=4','pages=3'),
                    log.replace('mapcount=0','mapcount=1',1)):
            with self.assertRaises(Exception): runner.physical_records(row, bad, done)

    def test_complete(self):
        self.assertEqual(runner.validate(fixture(), DONE + PHYSICAL + ACKS)['actual_remote_vma_removals'], 15)

    def test_requires_actual_mapping_and_other_task(self):
        for log in (ACKS, DONE + PHYSICAL.replace('pfn=3e9','pfn=3f0',1) + ACKS, DONE.replace('executor=100', 'executor=101', 1) + PHYSICAL + ACKS,
                    DONE.replace('mm=abc', 'mm=abd', 1) + PHYSICAL + ACKS,
                    DONE.replace('start=65000', 'start=66000', 1) + PHYSICAL + ACKS):
            with self.assertRaises(Exception): runner.validate(fixture(), log)

        for key,value in [('pfn',999),('initial_pfn',999),('mapcount',1),('refs_before_drop',2),('hash',0),('charged_same',0),('locked',1)]:
            row=fixture();row['pages'][1][key]=value
            with self.assertRaises(Exception): runner.validate(row, DONE + PHYSICAL + ACKS)

    def test_requires_exact_ack_identity(self):
        for log in (DONE + PHYSICAL + ACKS.replace('KD_MM_UNMAP ack', 'omitted', 1),
                    DONE + PHYSICAL + ACKS.replace('ack mm=abc id=18', 'ack mm=abc id=19', 1)):
            with self.assertRaises(Exception): runner.validate(fixture(), log)

    def test_requires_readers_fault_and_cleanup(self):
        for key, value in [('reader_peak', 1), ('idle', 0), ('cleanup_calls', 143),
                           ('late_fault_blocked', 0), ('late_fault_code', 1), ('late_fault_stack', ''), ('errors', 1), ('pins_owned', 1), ('pins_released', 47)]:
            row = fixture(); row[key] = value
            with self.assertRaises(Exception): runner.validate(row, DONE + PHYSICAL + ACKS)

    def test_requires_sticky_refusal(self):
        for key, value in [('delegated', 16), ('native_only', 0), ('post_ban', 15), ('acks', 14)]:
            row = copy.deepcopy(fixture()); row['phases'][2][key] = value
            with self.assertRaises(Exception): runner.validate(row, DONE + PHYSICAL + ACKS)


if __name__ == '__main__':
    unittest.main()
