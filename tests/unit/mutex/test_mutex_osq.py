"""Guest-only actual shared-node OSQ, reservation and optimistic-spin checks.

Deterministic primitive callbacks model delayed links and cancellation races.
They establish control-flow/lifetime coverage, not weak-memory or scheduling
proof; affected live probes still exercise the real sleeping physical mutex.
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
    local = read_source(ROOT / 'kernel_module/kd_mutex_local.h')
    types += local[local.index('#define KD_MUTEX_TAIL_IDX_OFFSET'):
                   local.index('DECLARE_PER_CPU_SHARED_ALIGNED')]
    mutex = read_source(ROOT / 'kernel_module/kd_mutex.c')
    types += definition(mutex, 'struct kd_mutex_cpu_state {').rstrip() + ';\n'
    code = ''
    for marker in (
        'static inline u32 kd_mutex_encode_tail(int cpu, int idx)',
        'static struct kd_mutex_node *kd_mutex_reserve_node(void)',
        'static void kd_mutex_release_node(struct kd_mutex_node *node)',
        'struct kd_mutex_osq_node *kd_mutex_osq_node_get(struct kd_mutex *lock)',
        'void kd_mutex_osq_node_put(struct kd_mutex_osq_node *osq)',
    ):
        code += definition(mutex, marker) + '\n'
    code += without_includes(read_source(ROOT / 'kernel_module/kd_mutex_osq.c'))
    local_source = read_source(ROOT / 'kernel_module/kd_mutex_local.c')
    common = definition(local_source,
                        'static __always_inline bool kd_local_spin_common(struct kd_mutex *lock, bool waiter,')
    code += common
    code += definition(local_source,
                       'static __always_inline bool kd_local_spin(struct kd_mutex *lock, bool waiter,')
    mutations = {
        'predecessor-polled-every-iteration': (
            '#define KD_MUTEX_OSQ_PREDECESSOR_POLLS 64U',
            '#define KD_MUTEX_OSQ_PREDECESSOR_POLLS 1U'),
        'predecessor-observation-too-late': (
            '#define KD_MUTEX_OSQ_PREDECESSOR_POLLS 64U',
            '#define KD_MUTEX_OSQ_PREDECESSOR_POLLS 128U'),
        'decode-loses-slot': ('& KD_MUTEX_TAIL_IDX_MASK;', '& 0;'),
        'vcpu-decodes-encoded-slot': (
            'return (node->tail >> KD_MUTEX_TAIL_CPU_OFFSET) - 1;',
            'return node->tail - 1;'),
        'cancel-loses-backlink': ('WRITE_ONCE(next->prev, prev);', '(void)next;'),
        'cancel-loses-forward-link': ('WRITE_ONCE(prev->next, next);', '(void)prev;'),
        'cancel-ignores-grant': (
            'if (smp_load_acquire(&node->locked) == KD_MUTEX_OSQ_GRANTED)',
            'if (false && smp_load_acquire(&node->locked) == KD_MUTEX_OSQ_GRANTED)'),
        'retirement-keeps-membership': (
            'WRITE_ONCE(node->locked, KD_MUTEX_OSQ_IDLE);',
            'WRITE_ONCE(node->locked, KD_MUTEX_OSQ_WAITING);'),
        'release-borrowed-reservation': ('if (node && !borrowed)', 'if (node)'),
        'leak-temporary-reservation': ('if (node && !borrowed)', 'if (false && node && !borrowed)'),
        'skip-spin-queue-retirement': (
            'if (!waiter)\n\t\tkd_mutex_osq_unlock(&lock->osq, node);',
            'if (false && !waiter)\n\t\tkd_mutex_osq_unlock(&lock->osq, node);'),
        'reuse-before-osq-retirement': (
            'BUG_ON(READ_ONCE(node->osq.locked) != KD_MUTEX_OSQ_IDLE);',
            '(void)node;'),
        'ordinary-queue-polls-signals': (
            'return kd_mutex_osq_lock_common(lock, node, false);',
            'return kd_mutex_osq_lock_common(lock, node, true);'),
        'scoped-queue-ignores-signals': (
            'return kd_mutex_osq_lock_common(lock, node, true);',
            'return kd_mutex_osq_lock_common(lock, node, false);'),
        'scoped-owner-spin-ignores-signals': (
            common, common.replace('stop_signals && signal_pending(current)',
                                   'false && signal_pending(current)')),
        'signal-precedes-completed-acquisition': (
            '\tfor (;;) {\n\t\towner = kd_try_common(lock, false);',
            '\tfor (;;) {\n\t\tif (stop_signals && signal_pending(current))\n'
            '\t\t\tgoto done;\n\t\towner = kd_try_common(lock, false);'),
    }
    with tempfile.TemporaryDirectory(prefix='kd-mutex-osq-') as tmp:
        path = Path(tmp)
        (path / 'mutex_osq_types.h').write_text(types)
        for name, mutation in [('production', None), *mutations.items()]:
            candidate = code
            if mutation:
                before, after = mutation
                assert candidate.count(before) == (2 if name == 'reuse-before-osq-retirement' else 1), (name, candidate.count(before))
                candidate = candidate.replace(before, after)
            (path / 'mutex_osq_actual.h').write_text(candidate)
            binary = path / name
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-I' + str(path),
                str(ROOT / 'tests/unit/mutex/mutex_osq_fixture.c'),
                '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], capture_output=True,
                                    text=True, timeout=10)
            if mutation:
                assert result.returncode == 1 and 'FAIL osq' in result.stderr, (
                    name, result.returncode, result.stdout, result.stderr)
                print('mutex osq mutation detected:', name)
            else:
                assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
                print(result.stdout, end='')


if __name__ == '__main__':
    main()
