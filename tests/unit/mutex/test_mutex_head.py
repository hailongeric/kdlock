"""Guest-only production queue-head retirement with deterministic publishers.

The actual helper must avoid writing the shared lock line for an existing
successor, while preserving the last-node CAS and delayed-link handshake.
Primitive callbacks exercise the competing publications; they do not prove
kernel scheduling, weak-memory ordering or a hardware performance benefit.
"""
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, read_source
from test_spin_shadow import definition


def main():
    source = read_source(ROOT / 'kernel_module/kd_mutex.c')
    code = 'static struct kd_mutex_node *\n' + definition(
        source,
        'kd_mutex_head_successor(struct kd_mutex *lock, struct kd_mutex_node *curr_node)')
    mutations = {
        'touch-tail-with-linked-successor': (
            'if (next)\n\t\treturn next;', 'if (false && next)\n\t\treturn next;'),
        'rmw-known-successor-tail': (
            'READ_ONCE(lock->delegation_tail) == (u32)curr_node->tail &&',
            '(READ_ONCE(lock->delegation_tail), true) &&'),
        'retire-without-cas': (
            'cmpxchg(&lock->delegation_tail, (u32)curr_node->tail, 0) ==\n\t\t    (u32)curr_node->tail',
            'true'),
        'ignore-cas-race': (
            'cmpxchg(&lock->delegation_tail, (u32)curr_node->tail, 0) ==\n\t\t    (u32)curr_node->tail',
            '(cmpxchg(&lock->delegation_tail, (u32)curr_node->tail, 0), true)'),
        'skip-delayed-link': ('} while (!next);', '} while (false);'),
        'lose-delayed-successor': ('\n\treturn next;\n}', '\n\treturn NULL;\n}'),
    }
    with tempfile.TemporaryDirectory(prefix='kd-mutex-head-') as tmp:
        path = Path(tmp)
        for name, mutation in [('production', None), *mutations.items()]:
            candidate = code
            if mutation:
                before, after = mutation
                assert candidate.count(before) == 1, (name, candidate.count(before))
                candidate = candidate.replace(before, after)
            (path / 'head_production.h').write_text(candidate)
            binary = path / name
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-I' + str(path),
                str(ROOT / 'tests/unit/mutex/mutex_head_fixture.c'),
                '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], capture_output=True,
                                    text=True, timeout=10)
            if mutation:
                assert result.returncode == 1 and 'FAIL head' in result.stderr, (
                    name, result.returncode, result.stdout, result.stderr)
                print('mutex head mutation detected:', name)
            else:
                assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
                print(result.stdout, end='')


if __name__ == '__main__':
    main()
