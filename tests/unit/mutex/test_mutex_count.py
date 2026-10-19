"""Guest-only actual versioned-node count snapshot and cold drain checks.

Deterministic read boundaries expose impossible mixed snapshots, same-key reuse
and paused writers. Concurrent writers use real pthread atomics; this fixture
checks algorithmic interleavings, not Linux weak-memory or scheduling behavior.
"""
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from source_text import ROOT, read_source, without_includes
from test_spin_shadow import definition


def main():
    types = definition(read_source(ROOT / 'include/kd_regs.h'),
                       'struct kd_regs {').rstrip() + ';\n'
    types += without_includes(read_source(ROOT / 'include/kd_mutex.h'))
    source = without_includes(read_source(ROOT / 'include/kd_mutex_state.h'))
    source += read_source(ROOT / 'kernel_module/mutex/count.inc')
    mutations = {
        'validation-accepts-new-generation': (
            'if (READ_ONCE(node->count_seq) !=\n\t\t\t\t    versions[',
            'if (READ_ONCE(node->count_seq) <\n\t\t\t\t    versions['),
        'snapshot-accepts-odd': ('if (seq & 1)', 'if (false && (seq & 1))'),
        'snapshot-ignores-lock-identity': ('count += key == lock;', 'count += key != NULL;'),
        'allocation-failure-is-zero': ('return -ENOMEM;', 'return 0;'),
        'retry-exhaustion-is-zero': ('\t\tcount = -EAGAIN;', '\t\tcount = 0;'),
        'scan-skips-last-cpu': ('for_each_possible_cpu(cpu)',
                              'for (cpu = 0; cpu < TEST_CPUS - 1; cpu++)'),
        'scan-skips-last-slot': ('idx < KD_MUTEX_MAX_NODES', 'idx + 1 < KD_MUTEX_MAX_NODES'),
        'global-drain-ignores-odd': ('(READ_ONCE(node->count_seq) & 1)', '(false)'),
        'global-drain-ignores-record': ('\t\t\t    READ_ONCE(node->counted_lock))',
                                       '\t\t\t    (false && READ_ONCE(node->counted_lock)))'),
        'object-idle-ignores-record': ('if (READ_ONCE(node->counted_lock) == lock)',
                                      'if (false && READ_ONCE(node->counted_lock) == lock)'),
        'snapshot-leaks-scratch': ('\t\tkfree(versions);\n\t\treturn count;', '\t\treturn count;'),
        'writer-skips-odd-publication': ('WRITE_ONCE(node->count_seq, seq + 1);', '(void)seq;'),
    }
    with tempfile.TemporaryDirectory(prefix='kdlock-mutex-count-') as tmp:
        path = Path(tmp)
        (path / 'mutex_count_types.h').write_text(types)
        for name, mutation in [('production', None), *mutations.items()]:
            candidate = source
            if mutation:
                before, after = mutation
                expected = 4 if name in ('scan-skips-last-cpu', 'scan-skips-last-slot') else 1
                assert candidate.count(before) == expected, (name, candidate.count(before))
                candidate = candidate.replace(before, after)
            (path / 'mutex_count_actual.h').write_text(candidate)
            binary = path / name
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-pthread', '-Wall', '-Wextra', '-Werror',
                '-I', str(path), '-I', str(ROOT / 'include'),
                str(ROOT / 'tests/unit/mutex/mutex_count_fixture.c'),
                '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], capture_output=True,
                                    text=True, timeout=20)
            if mutation:
                assert result.returncode == 1 and 'FAIL line' in result.stderr, (
                    name, result.returncode, result.stdout, result.stderr)
                print('mutex count mutation detected:', name)
            else:
                assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
                print(result.stdout, end='')


if __name__ == '__main__':
    main()
