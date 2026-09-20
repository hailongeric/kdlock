"""Compare the production hash body against its previous poisoned unlink.

Guest userspace only: use the actual guest kernel's three hlist primitives,
then check operation outcomes and every link against the old body and a key-set
oracle. This is sequential payload validation, not proof of live JIT execution.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


def function(text, name):
    start = text.index('static inline void ' + name + '(')
    brace = text.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end] + '\n'


class HashRelinkTests(unittest.TestCase):
    def test_relink_matches_poisoned_body_and_key_set(self):
        source = (ROOT/'workload_modules/spin_cacheline/hash_payload.h').read_text()
        body = source[source.index('struct sc_hash_bucket {'):
                      source.index('/* Deterministic per-worker')]
        self.assertEqual(body.count('__hlist_del(&src_entry->node);'), 1)
        kernel = Path(os.environ.get('KDIR', '/root/linux-6.1.159-kdclobber2'))
        header = (kernel/'include/linux/list.h').read_text()
        helpers = ''.join(function(header, name) for name in
                          ('__hlist_del', 'hlist_del', 'hlist_add_head'))
        names = ('sc_hash_bucket', 'sc_hash_entry', 'sc_hash_stats',
                 'sc_hash_table', 'sc_hash_nodes', 'sc_hash_moves',
                 'sc_hash_dests', 'sc_hash_misses', 'sc_body_0')
        # Restore the previous post-mutation count order in the control body.
        old = body.replace('__hlist_del(', 'hlist_del(').replace(
            '\t\tstats->moves++;\n\t\tsrc_entry->value = dst_value;',
            '\t\tsrc_entry->value = dst_value;\n\t\tstats->moves++;')
        old = old.replace('\n\tstats->moves++;\n', '\n').replace(
            '\thlist_add_head(&src_entry->node, &sc_hash_table[dst_bucket].head);',
            '\thlist_add_head(&src_entry->node, &sc_hash_table[dst_bucket].head);\n\tstats->moves++;')
        copies = []
        for prefix, payload in [('old', old),
                                ('new', body)]:
            copies.append(''.join(f'#define {n} {prefix}_{n}\n' for n in names)
                          + payload + ''.join(f'#undef {n}\n' for n in names))
        fixture = Path(__file__).with_name('hash_relink_fixture.c').read_text()
        code = fixture.replace('/* KERNEL_HLIST_HELPERS */', helpers).replace(
            '/* PRODUCTION_HASH_BODIES */', '\n'.join(copies))
        with tempfile.TemporaryDirectory(prefix='kd-hash-relink-') as tmp:
            src, exe = Path(tmp)/'fixture.c', Path(tmp)/'fixture'
            src.write_text(code)
            subprocess.run(['gcc', '-O2', '-g', '-Wall', '-Wextra', '-Werror',
                            '-Wno-unused-variable', '-fsanitize=address,undefined',
                            '-fno-pie', '-no-pie', str(src), '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True, timeout=60)


if __name__ == '__main__':
    unittest.main()
