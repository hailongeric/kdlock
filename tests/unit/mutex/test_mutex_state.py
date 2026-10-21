"""Guest-only actual embedded mutex state and current-owner interleavings.

Compile the production helpers and ownership/acquire/release functions. Versioned
node records retain exact waiter lifetimes; deterministic primitive
callbacks place ordinary owners in acquisition/release windows. Physical
sleeping, kernel scheduling and weak-memory hardware remain live-probe duties.
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
    types += without_includes(read_source(ROOT / 'include/kd_mutex_types.h'))
    types += without_includes(read_source(ROOT / 'include/kd_mutex.h'))
    source = without_includes(read_source(ROOT / 'include/kd_mutex_state.h'))
    mutex = read_source(ROOT / 'kernel_module/kd_mutex.c')
    source += '\n' + definition(read_source(ROOT / 'kernel_module/kd_mutex_local.c'),
                                 'void kd_mutex_init(struct kd_mutex *lock)')
    for marker in (
        'bool kd_mutex_delegation_owned(struct kd_mutex *lock, struct task_struct *task)',
        'bool kd_mutex_combiner_active(struct kd_mutex *lock)',
        'static void kd_mutex_claim_origin_node(struct kd_mutex *lock,',
        'static void kd_mutex_claim_origin(struct kd_mutex *lock)',
    ):
        source += '\n' + definition(mutex, marker)
    source += '\nint ' + definition(mutex, '_kd_mutex_unlock_checked(struct kd_mutex *lock)')
    mutations = {
        'gate-claim-accepts-held': ('atomic_cmpxchg(&lock->delegation_state, KD_MUTEX_GATE_FREE,',
                                 'atomic_cmpxchg(&lock->delegation_state, kd_mutex_gate_read(lock),'),
        'record-overflow-not-rejected': ('BUG_ON((seq & 1) || seq > U64_MAX - 2);', 'BUG_ON(seq & 1);'),
        'record-odd-not-rejected': ('BUG_ON((seq & 1) || seq > U64_MAX - 2);', 'BUG_ON(seq > U64_MAX - 2);'),
        'record-identity-not-checked': ('BUG_ON(READ_ONCE(node->counted_lock) != expected);', '(void)expected;'),
        'record-generation-not-advanced': ('WRITE_ONCE(node->count_seq, seq + 2);', 'WRITE_ONCE(node->count_seq, seq);'),
        'record-exit-keeps-key': ('kd_mutex_count_transition(node, lock, NULL);', 'kd_mutex_count_transition(node, lock, lock);'),
        'invalid-phase-not-rejected': ('BUG_ON(phase > KD_MUTEX_GATE_RELEASING);', '(void)phase;'),
        'foreign-task-query-authorized': ('if (!lock || task != current)', 'if (!lock || (false && task != current))'),
        'pickup-authorized': ('(owner & 4UL)', '(owner & 0UL)'),
        'physical-owner-ignored': ('(owner & ~KD_MUTEX_OWNER_FLAGS) != (unsigned long)current', 'false'),
        'acquiring-authorized': ('return phase == KD_MUTEX_GATE_HELD || phase == KD_MUTEX_GATE_COMBINER;',
                                 'return phase == KD_MUTEX_GATE_HELD || phase == KD_MUTEX_GATE_COMBINER || phase == KD_MUTEX_GATE_ACQUIRING;'),
        'releasing-authorized': ('return phase == KD_MUTEX_GATE_HELD || phase == KD_MUTEX_GATE_COMBINER;',
                                 'return phase == KD_MUTEX_GATE_HELD || phase == KD_MUTEX_GATE_COMBINER || phase == KD_MUTEX_GATE_RELEASING;'),
        'combiner-not-authorized': ('return phase == KD_MUTEX_GATE_HELD || phase == KD_MUTEX_GATE_COMBINER;',
                                    'return phase == KD_MUTEX_GATE_HELD;'),
        'held-before-physical': ('kd_mutex_local_lock_node(lock, node);\n\tkd_mutex_gate_set(lock, KD_MUTEX_GATE_HELD);',
                                 'kd_mutex_gate_set(lock, KD_MUTEX_GATE_HELD);\n\tkd_mutex_local_lock_node(lock, node);'),
        'free-before-physical-release': ('kd_mutex_gate_set(lock, KD_MUTEX_GATE_RELEASING);',
                                         'kd_mutex_gate_set(lock, KD_MUTEX_GATE_FREE);'),
        'releasing-phase-skipped': ('kd_mutex_gate_set(lock, KD_MUTEX_GATE_RELEASING);', '(void)lock;'),
        'post-release-clears-successor': ('kd_mutex_gate_set(lock, KD_MUTEX_GATE_FREE);\n\treturn 0;',
                                         'kd_mutex_gate_set(lock, KD_MUTEX_GATE_FREE);\n\tkd_mutex_gate_set(lock, KD_MUTEX_GATE_FREE);\n\treturn 0;'),
    }
    with tempfile.TemporaryDirectory(prefix='kdlock-mutex-state-') as tmp:
        path = Path(tmp)
        (path / 'mutex_state_types.h').write_text(types)
        for name, mutation in [('production', None), *mutations.items()]:
            candidate = source
            if mutation:
                before, after = mutation
                assert candidate.count(before) == 1, (name, candidate.count(before))
                candidate = candidate.replace(before, after)
            (path / 'mutex_state_actual.h').write_text(candidate)
            binary = path / name
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-pthread', '-Wall', '-Wextra', '-Werror',
                '-I', str(path), '-I', str(ROOT / 'include'),
                str(ROOT / 'tests/unit/mutex/mutex_state_fixture.c'),
                '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], capture_output=True,
                                    text=True, timeout=20)
            if mutation:
                assert result.returncode == 1 and 'FAIL line' in result.stderr, (
                    name, result.returncode, result.stdout, result.stderr)
                print('mutex state mutation detected:', name)
            else:
                assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
                print(result.stdout, end='')


if __name__ == '__main__':
    main()
