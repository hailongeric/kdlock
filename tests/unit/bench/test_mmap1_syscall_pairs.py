"""VM-only checks of bounded origin syscall-return and exact-root pairing."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('syscall_pair_unit', ROOT / 'tests/kernel/mmap1_identity/syscall_pairs.py')
pairing = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pairing)


def fixture(fd='ffffffff'):
    row = dict(tid=11, tgid=11, start_boottime_ns=1234, mm=0x3000, lock=0x3100,
               backing=0x3200, provider=0x4000, route=2, cpu=2)
    roots = [dict(origin=11, executor=22, identity=i, generation=7,
                  entry=entry) for i, entry in ((0xa1, 0x1000), (0xa2, 0x2000))]
    common = 'tid=11 tgid=11 start=1234 mm=3000 lock=3100 backing=3200 provider=4000 route=2'
    def marker(event, op, sequence, args, result='0'):
        return (f'kd_mm_pair: event={event} op={op} {common} sequence={sequence} pair=1 '
                f'cpu=2 time={100 + sequence * 2 + (event == "return")} args={args} result={result}')
    def event(stage, root):
        return (f'kd_service event={stage} origin=11 executor=22 identity={root["identity"]:x} '
                f'generation=7 object=3200 depth=0 entry={root["entry"]:x} may_delegate=1')
    map_args, unmap_args = f'0,8000000,3,22,{fd},0', '5000,8000000,0,0,0,0'
    lines = [marker('enter', 'mmap', 1, map_args)]
    lines += [event(stage, roots[0]) for stage in ('enter', 'release', 'returned')]
    lines += [marker('return', 'mmap', 1, map_args, '5000'), marker('enter', 'munmap', 2, unmap_args)]
    lines += [event(stage, roots[1]) for stage in ('enter', 'downgrade', 'read_release', 'returned')]
    lines += [marker('return', 'munmap', 2, unmap_args),
              'kd_mm_pair: event=stop limit=8 tasks=1 pairs=1 unfinished=0 inflight=0 errors=0 '
              'identity_missed=0 mmap_missed=0 mmap_suppressed=0 munmap_missed=0 munmap_suppressed=0']
    return lines, dict(records=[row]), dict(completed_requests=roots), dict(mmap=[0x1000], munmap=[0x2000])


def render(lines):
    return '\n'.join(f'6,{index + 1},{index + 100},-;{line}' for index, line in enumerate(lines))


class SyscallPairs(unittest.TestCase):
    def validate(self, value):
        lines, snapshot, proof, sites = value
        return pairing.validate(render(lines), snapshot, proof, sites, 8)

    def test_exact_return_address_pair_and_downgraded_root(self):
        result = self.validate(fixture())
        self.assertEqual(result['completed_pairs'], 1)
        self.assertEqual([row['operation'] for row in result['syscalls']], ['mmap', 'munmap'])
        self.assertEqual(result['syscalls'][0]['result'], result['syscalls'][1]['args'][0])
        self.assertTrue(result['origin_wrapper_returns_observed'])
        self.assertEqual(result['sampled_munmap_read_tails'], 1)
        for name in ('all_application_invocations_accounted', 'vma_contents_or_structure_observed',
                     'final_user_return_instruction_observed', 'fresh_reader_drain_observed'):
            self.assertFalse(result[name])

    def test_both_native_fd_upper_half_representations(self):
        for fd in ('ffffffff', 'ffffffffffffffff'):
            with self.subTest(fd=fd):
                self.assertTrue(self.validate(fixture(fd))['passed'])

    def test_executor_return_cannot_replace_origin_return(self):
        value = fixture()
        del value[0][4]
        with self.assertRaises(ValueError):
            self.validate(value)
        value = fixture()
        returned = value[0].pop(3)
        value[0].insert(4, returned)
        with self.assertRaises(ValueError):
            self.validate(value)

    def test_each_missed_probe_kind_and_partial_drain_fail(self):
        for name in ('identity_missed', 'mmap_missed', 'mmap_suppressed', 'munmap_missed', 'munmap_suppressed',
                     'inflight', 'unfinished', 'errors'):
            value = fixture()
            value[0][-1] = value[0][-1].replace(name + '=0', name + '=1')
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.validate(value)

    def test_changed_identity_arguments_address_result_and_summary_fail(self):
        changes = ((0, 'start=1234', 'start=1235'), (0, 'cpu=2', 'cpu=3'),
                   (0, ',3,22,', ',3,12,'), (4, 'result=5000', 'result=fffffffffffffff4'),
                   (5, 'args=5000,', 'args=6000,'), (10, 'result=0', 'result=1'),
                   (-1, 'pairs=1', 'pairs=2'), (-1, 'tasks=1', 'tasks=2'))
        for index, before, after in changes:
            value = fixture()
            self.assertIn(before, value[0][index])
            value[0][index] = value[0][index].replace(before, after)
            with self.subTest(change=(index, before)), self.assertRaises(ValueError):
                self.validate(value)

    def test_missing_duplicate_and_mixed_root_identity_fail(self):
        for index, change in ((3, lambda text: text.replace('event=returned', 'event=release')),
                              (2, lambda text: text.replace('identity=a1', 'identity=a3'))):
            value = fixture()
            value[0][index] = change(value[0][index])
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.validate(value)
        value = fixture()
        value[0].insert(2, value[0][1])
        with self.assertRaises(ValueError):
            self.validate(value)
        value = fixture()
        value[0].pop()
        with self.assertRaises(ValueError):
            self.validate(value)

    def test_multiple_complete_roots_in_one_syscall_remain_exact(self):
        value = fixture()
        extra = copy.deepcopy(value[2]['completed_requests'][0])
        extra['identity'] = 0xa3
        value[2]['completed_requests'].append(extra)
        value[0][4:4] = [line.replace('identity=a1', 'identity=a3') for line in value[0][1:4]]
        result = self.validate(value)
        self.assertEqual(result['syscalls'][0]['roots'], [[11, 0xa1, 7], [11, 0xa3, 7]])

    def test_read_tail_from_another_lifetime_operation_cannot_satisfy_sample(self):
        value = fixture()
        value[0][7] = value[0][7].replace('event=downgrade', 'event=release')
        del value[0][8]
        value[0][2] = value[0][2].replace('event=release', 'event=downgrade')
        value[0].insert(3, value[0][2].replace('event=downgrade', 'event=read_release'))
        with self.assertRaises(ValueError):
            self.validate(value)

    def test_original_raw_register_words_and_record_order_are_checked(self):
        value = fixture('1ffffffffffffffff')
        with self.assertRaises(ValueError):
            self.validate(value)
        value = fixture()
        messages = render(value[0]).splitlines()
        messages[2] = messages[2].replace('6,3,', '6,2,')
        with self.assertRaises(ValueError):
            pairing.validate('\n'.join(messages), value[1], value[2], value[3], 8)


if __name__ == '__main__':
    unittest.main()
