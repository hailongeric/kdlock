"""Core-only symbol reuse against the production live lookup boundary."""

import contextlib
import io
import unittest
from unittest.mock import patch

from test_jit_diagnostics import translator


symbols = translator.kernel_symbols


def image(core, later=''):
    return '0001 T _stext\n' + core + '0100 T _etext\n' + later


class Table:
    def __init__(self):
        self.text = image('0010 T core\n0020 t other\n', '0030 t dynamic [old]\n')
        self.opens = 0
        self.responses = []

    def open(self, *args, **kwargs):
        self.opens += 1
        if self.responses:
            return self.responses.pop(0)()
        return io.StringIO(self.text)


class CoreSymbolTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.table = Table()
        self.stack.enter_context(patch.object(translator, 'open', self.table.open, create=True))
        self.stack.enter_context(patch.object(translator.memread.device_session, 'require', return_value=19))

    def lookup(self, name, default=0):
        return translator.get_kernel_symbol(name, default)

    def test_core_reuse_is_lazy_and_stops_at_text_endpoint(self):
        with symbols.translation_scope():
            self.assertEqual(self.table.opens, 0)
            self.assertEqual(self.lookup('core'), 0x10)
            self.assertEqual(self.lookup('other'), 0x20)
            self.assertEqual(self.lookup('core'), 0x10)
            self.assertEqual(self.table.opens, 1)

    def test_lookup_without_scope_stays_live(self):
        self.assertEqual(self.lookup('core'), 0x10)
        self.table.text = image('0040 T core\n')
        self.assertEqual(self.lookup('core'), 0x40)
        self.assertEqual(self.table.opens, 2)

    def test_lookup_without_lease_stays_live(self):
        with patch.object(translator.memread.device_session, 'require', side_effect=RuntimeError('no lease')):
            with symbols.translation_scope():
                self.assertEqual(self.lookup('core'), 0x10)
                self.table.text = image('0040 T core\n')
                self.assertEqual(self.lookup('core'), 0x40)
        self.assertEqual(self.table.opens, 2)

    def test_dynamic_replacement_is_live(self):
        with symbols.translation_scope():
            self.assertEqual(self.lookup('dynamic'), 0x30)
            self.table.text = image('0010 T core\n', '0040 t dynamic [new]\n0030 t dynamic [old]\n')
            self.assertEqual(self.lookup('dynamic'), 0x40)

    def test_dynamic_removal_is_live(self):
        with symbols.translation_scope():
            self.assertEqual(self.lookup('dynamic'), 0x30)
            self.table.text = image('0010 T core\n')
            self.assertEqual(self.lookup('dynamic', 73), 73)

    def test_missing_name_can_appear(self):
        with symbols.translation_scope():
            self.assertEqual(self.lookup('later', 73), 73)
            self.table.text += '0040 t later [new]\n'
            self.assertEqual(self.lookup('later', 73), 0x40)

    def test_dynamic_duplicate_priority_changes(self):
        with symbols.translation_scope():
            self.assertEqual(self.lookup('dynamic'), 0x30)
            self.table.text = image('0010 T core\n', '0050 T dynamic [head]\n0030 t dynamic [old]\n')
            self.assertEqual(self.lookup('dynamic'), 0x50)

    def test_core_first_raw_token_wins_over_all_duplicates(self):
        self.table.text = image('0010 t same\n0020 T same\n', '0030 T same [module]\n')
        with symbols.translation_scope():
            self.assertEqual(self.lookup('same'), 0x10)
            self.assertEqual(self.lookup('same'), 0x10)
        self.assertEqual(self.table.opens, 1)

    def test_zero_first_token_blocks_later_duplicate_and_stays_live(self):
        self.table.text = image('0000 t same\n0020 T same\n', '0030 T same [module]\n')
        with symbols.translation_scope():
            self.assertEqual(self.lookup('same', 99), 0)
            self.assertEqual(self.lookup('same', 83), 0)
        self.assertEqual(self.table.opens, 3)

    def test_zero_name_is_rechecked(self):
        self.table.text = image('0000 t zero\n')
        with symbols.translation_scope():
            self.assertEqual(self.lookup('zero', 99), 0)
            self.table.text = image('0040 t zero\n')
            self.assertEqual(self.lookup('zero', 83), 0x40)

    def test_missing_defaults_are_call_local(self):
        with symbols.translation_scope():
            self.assertEqual(self.lookup('missing', 71), 71)
            self.assertEqual(self.lookup('missing', 83), 83)

    def test_generated_owner_suffix_stays_live(self):
        for owner in ('__builtin__ftrace', 'bpf', '__builtin__kprobes'):
            with self.subTest(owner=owner):
                self.table.text = image('0010 t core\n', f'0030 t generated [{owner}]\n0040 t later\n')
                with symbols.translation_scope():
                    self.assertEqual(self.lookup('core'), 0x10)
                    self.assertEqual(self.lookup('later'), 0x40)
                    self.table.text = image('0010 t core\n', f'0030 t generated [{owner}]\n0050 t later\n')
                    self.assertEqual(self.lookup('later'), 0x50)

    def test_ownerless_dynamic_suffix_is_not_reused(self):
        self.table.text = image('0010 t core\n', '0030 t dynamic\n0040 t generated [later]\n')
        with symbols.translation_scope():
            self.assertEqual(self.lookup('dynamic'), 0x30)
            self.table.text = image('0010 t core\n', '0050 t dynamic\n0040 t generated [later]\n')
            self.assertEqual(self.lookup('dynamic'), 0x50)

    def test_later_core_data_stays_live(self):
        self.table.text = image('0010 t core\n', '0300 d data\n')
        with symbols.translation_scope():
            self.assertEqual(self.lookup('data'), 0x300)
            self.table.text = image('0010 t core\n', '0400 d data\n')
            self.assertEqual(self.lookup('data'), 0x400)

    def test_missing_zero_malformed_or_incoherent_markers_keep_live_lookup(self):
        for markers in ('', '0001 T _stext\n', '0000 T _stext\n0100 T _etext\n',
                        '0001 T _stext\n0000 T _etext\n', 'wrong T _stext\n0100 T _etext\n',
                        '0001 T _stext\nwrong T _etext\n', '0200 T _stext\n0100 T _etext\n',
                        '0001 T _stext\n0000 T _etext\n0100 T _etext\n'):
            with self.subTest(markers=markers):
                self.table.text = '0010 t core\n' + markers
                with symbols.translation_scope():
                    self.assertEqual(self.lookup('core'), 0x10)
                    self.table.text = '0040 t core\n' + markers
                    self.assertEqual(self.lookup('core'), 0x40)

    def test_owner_before_endpoint_discards_tentative_prefix(self):
        self.table.text = '0001 T _stext\n0010 t core\n0030 t dynamic [early]\n0100 T _etext\n'
        with symbols.translation_scope():
            self.assertEqual(self.lookup('core'), 0x10)
            self.table.text = self.table.text.replace('0010 t core', '0040 t core')
            self.assertEqual(self.lookup('core'), 0x40)

    def test_unrelated_malformed_token_is_not_converted(self):
        self.table.text = image('wrong t malformed\nshort line\n0010 t core\n')
        with symbols.translation_scope():
            self.assertEqual(self.lookup('core'), 0x10)

    def test_matching_malformed_token_raises(self):
        self.table.text = image('wrong t malformed\n')
        with symbols.translation_scope(), self.assertRaises(ValueError):
            self.lookup('malformed')

    def test_fill_open_failure_uses_fresh_live_scan(self):
        def failed():
            raise OSError('fixture open failure')
        self.table.responses = [failed]
        with symbols.translation_scope():
            self.assertEqual(self.lookup('core'), 0x10)
            self.table.text = image('0040 t core\n')
            self.assertEqual(self.lookup('core'), 0x40)
        self.assertEqual(self.table.opens, 3)

    def test_fill_iteration_failure_discards_partial_prefix(self):
        class Partial:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def __iter__(self):
                yield '0020 t core\n'
                raise OSError('fixture iteration failure')
        self.table.responses = [Partial]
        with symbols.translation_scope():
            self.assertEqual(self.lookup('core'), 0x10)
            self.table.text = image('0040 t core\n')
            self.assertEqual(self.lookup('core'), 0x40)
        self.assertEqual(self.table.opens, 3)

    def test_fill_close_failure_discards_prefix(self):
        class CloseFailure(io.StringIO):
            def __exit__(self, *args):
                self.close()
                raise OSError('fixture close failure')
        self.table.responses = [lambda: CloseFailure(image('0020 t core\n'))]
        with symbols.translation_scope():
            self.assertEqual(self.lookup('core'), 0x10)
            self.table.text = image('0040 t core\n')
            self.assertEqual(self.lookup('core'), 0x40)
        self.assertEqual(self.table.opens, 3)

    def test_live_open_errors_keep_defaults_and_retry(self):
        def failed():
            raise OSError('fixture open failure')
        self.table.responses = [failed, failed, failed]
        with symbols.translation_scope():
            self.assertEqual(self.lookup('core', 71), 71)
            self.assertEqual(self.lookup('core', 83), 83)
            self.assertEqual(self.lookup('core'), 0x10)
        self.assertEqual(self.table.opens, 4)

    def test_live_close_error_after_match_returns_default(self):
        class CloseFailure(io.StringIO):
            def __exit__(self, *args):
                self.close()
                raise OSError('fixture close failure')
        def failed():
            raise OSError('fixture preparation failure')
        self.table.responses = [failed, lambda: CloseFailure('0010 t core\n')]
        with symbols.translation_scope():
            self.assertEqual(self.lookup('core', 71), 71)
            self.assertEqual(self.lookup('core'), 0x10)

    def test_scopes_reset_after_return_and_exception(self):
        @symbols.translation_scope()
        def run(fail=False):
            value = self.lookup('core')
            if fail:
                raise RuntimeError('fixture body failure')
            return value
        self.assertEqual(run(), 0x10)
        self.assertIsNone(symbols.current())
        self.table.text = image('0040 t core\n')
        self.assertEqual(run(), 0x40)
        with self.assertRaisesRegex(RuntimeError, 'fixture body failure'):
            run(fail=True)
        self.assertIsNone(symbols.current())

    def test_nested_scopes_restore_outer_cache(self):
        with symbols.translation_scope() as outer:
            self.assertEqual(self.lookup('core'), 0x10)
            self.table.text = image('0040 t core\n')
            with symbols.translation_scope() as inner:
                self.assertIsNot(inner, outer)
                self.assertEqual(self.lookup('core'), 0x40)
            self.assertIs(symbols.current(), outer)
            self.assertEqual(self.lookup('core'), 0x10)
        self.assertIsNone(symbols.current())

    def test_replaced_lookup_boundary_is_not_bypassed(self):
        with symbols.translation_scope(), patch.object(translator, 'get_kernel_symbol', return_value=73) as lookup:
            self.assertEqual(translator.get_percpu_symbol_offset('current_task'), 0)
            self.assertEqual([call.args for call in lookup.call_args_list], [('current_task',), ('__per_cpu_start',)])
        self.assertEqual(self.table.opens, 0)


if __name__ == '__main__':
    unittest.main()
