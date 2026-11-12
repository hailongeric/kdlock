"""VM-only focused checks of explicit candidate kernel/module identity binding."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bench/nano'))
import build as nano_build
import run as nano_run


class CandidateIdentity(unittest.TestCase):
    def test_build_requires_both_live_and_output_release(self):
        nano_build.validate_kernel_release('candidate', 'candidate', 'candidate')
        for live, built in [('baseline', 'candidate'), ('candidate', 'baseline')]:
            with self.subTest(live=live, built=built), self.assertRaises(RuntimeError):
                nano_build.validate_kernel_release('candidate', live, built)

    def test_run_rejects_old_build_release_or_elf(self):
        receipt = dict(status='NANO_MODULES_BUILT_SIGNED', kernel_release='candidate',
                       kernel_files=dict(vmlinux='candidate-elf'))
        nano_run.validate_kernel_receipt(receipt, 'candidate', 'candidate-elf')
        for key, value in [('kernel_release', 'baseline'), ('status', 'STARTED'),
                           ('kernel_files', dict(vmlinux='baseline-elf'))]:
            changed = copy.deepcopy(receipt)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                nano_run.validate_kernel_receipt(changed, 'candidate', 'candidate-elf')

    def test_return_thunk_may_move_only_with_exact_live_binding(self):
        symbols = 'ffffffff82000100 T __x86_return_thunk\nffffffff82000200 T ordinary\n'
        nano_run.validate_builtin_source(symbols, 0xffffffff82000100, b'\xc3\xcc')
        with self.assertRaisesRegex(ValueError, 'address'):
            nano_run.validate_builtin_source(symbols, 0xffffffff8276eee0, b'\xc3\xcc')
        with self.assertRaisesRegex(ValueError, 'captured'):
            nano_run.validate_builtin_source(symbols, 0xffffffff82000100, b'\x90\xc3')

    def test_thunk_binding_requires_one_nonzero_builtin_text_symbol(self):
        for symbols, start in [('', 0x100), ('100 T __x86_return_thunk [module]\n', 0x100),
                               ('100 D __x86_return_thunk\n', 0x100),
                               ('100 T __x86_return_thunk\n100 T __x86_return_thunk\n', 0x100),
                               ('000 T __x86_return_thunk\n', 0)]:
            with self.subTest(symbols=symbols), self.assertRaises(ValueError):
                nano_run.validate_builtin_source(symbols, start, b'\xc3\xcc')


if __name__ == '__main__':
    unittest.main()
