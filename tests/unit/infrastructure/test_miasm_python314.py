"""Keep semantic DSL string discrimination and real x86 lifting on Python 3.14."""
import ast
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'disassem'))

import miasm_python314 as compatibility
from miasm.core.sembuilder import MiasmTransformer, SemBuilder
from miasm.expression.expression import ExprId, ExprInt, ExprOp
from miasm.analysis.machine import Machine
from miasm.core.locationdb import LocationDB
from miasm.core.bin_stream import bin_stream_str
from miasm.arch.x86.arch import mn_x86


def integer_semantic(dst):
    "String docstrings remain valid semantic-builder input."
    dst = i32(7)


def string_semantic(dst, src):
    dst = '+'(src, i32(1))


def formatted_semantic(dst, src):
    dst = ('zeroExt_%d' % 32)(src)


def integer_statement(dst):
    7
    dst = i32(7)


def bytes_statement(dst):
    b'not a docstring'
    dst = i32(7)


class Python314CompatibilityTests(unittest.TestCase):
    def test_installed_runtime_has_exact_reviewed_patch(self):
        result = compatibility.verify_runtime()
        self.assertTrue(result['python314_patch_required'])
        self.assertEqual(result['dependency_sha256'], compatibility.PATCHED_SHA256)
        self.assertEqual(result['patch_sha256'], compatibility.PATCH_SHA256)

    def test_unknown_source_and_missing_runtime_patch_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError, 'unrecognized'):
            compatibility.patched_source(b'unknown dependency bytes')
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'sembuilder.py'
            target.write_bytes(b'changed dependency bytes')
            with patch.object(compatibility, 'target_path', return_value=target), \
                 self.assertRaisesRegex(RuntimeError, 'missing or changed'):
                compatibility.verify_runtime()

    def test_only_string_constant_calls_become_expression_operations(self):
        for text, expected in (("'op'(x)", True), ("('op_%d' % 8)(x)", True),
                               ('(1)(x)', False), ('(1 % 2)(x)', False),
                               ("b'op'(x)", False), ('(None)(x)', False)):
            with self.subTest(text=text):
                node = MiasmTransformer().visit(ast.parse(text, mode='eval').body)
                rewritten = isinstance(node.func, ast.Name) and node.func.id == 'ExprOp'
                self.assertEqual(rewritten, expected)

    def test_integer_and_string_semantics_keep_their_exact_expressions(self):
        dst, src = ExprId('dst', 32), ExprId('src', 32)
        for function, args, expected in ((integer_semantic, (dst,), ExprInt(7, 32)),
                (string_semantic, (dst, src), ExprOp('+', src, ExprInt(1, 32))),
                (formatted_semantic, (dst, ExprId('small', 8)), ExprOp('zeroExt_32', ExprId('small', 8)))):
            with self.subTest(function=function.__name__):
                built = SemBuilder({}).parse(function)
                assignments, extra = built(None, None, *args)
                self.assertEqual(len(assignments), 1)
                self.assertEqual(assignments[0].dst, dst)
                self.assertEqual(assignments[0].src, expected)
                self.assertEqual(extra, [])

    def test_nonstring_constants_are_not_accepted_as_docstrings(self):
        for function in (integer_statement, bytes_statement):
            with self.subTest(function=function.__name__), self.assertRaisesRegex(RuntimeError, 'Unimplemented'):
                SemBuilder({}).parse(function)

    def test_x86_semantic_lifter_still_produces_register_assignment(self):
        lifter = Machine('x86_64').lifter(LocationDB())
        line = mn_x86.dis(bin_stream_str(bytes.fromhex('48c7c007000000')), 64, 0)
        assignments, extra = lifter.instr2ir(line)
        self.assertEqual(assignments[ExprId('RAX', 64)], ExprInt(7, 64))
        self.assertEqual(extra, [])


if __name__ == '__main__':
    unittest.main()
