"""Guest-only bounded OSQ production extraction with adversarial interleavings.

Peer actions model the port's existing queue/cancellation steps. These checks
do not replace live OSQ scheduling or claim a bound on cancellation duration.
"""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from source_text import ROOT
from test_owned_mutex_preflight import definition


def production(core, osq, internal):
    result = definition(osq, 'struct kd_owned_osq_node {') + ';\n'
    result += 'DEFINE_PER_CPU_SHARED_ALIGNED(struct kd_owned_osq_node, kd_owned_osq_nodes);\n'
    result += definition(internal, 'enum kd_owned_mutex_preflight_result {') + ';\n'
    for prefix, marker in (
        ('static inline int ', 'kd_owned_osq_encode_cpu('),
        ('static inline int ', 'kd_owned_osq_node_cpu('),
        ('static inline struct kd_owned_osq_node *', 'kd_owned_osq_decode_cpu('),
        ('static inline struct kd_owned_osq_node *', 'kd_owned_osq_wait_next('),
        ('bool ', 'kd_owned_osq_trylock('),
        ('static __always_inline bool ', 'kd_owned_osq_budget_expired('),
        ('static __always_inline bool ', 'kd_owned_osq_lock_common('),
        ('', 'bool kd_owned_osq_lock(struct optimistic_spin_queue *lock)'),
        ('bool ', 'kd_owned_osq_lock_bounded('),
        ('void ', 'kd_owned_osq_unlock('),
    ):
        result += prefix + definition(osq, marker)
    result += 'static struct task_struct *' + definition(internal, 'kd_owned_mutex_owner(')
    result += 'static struct task_struct *' + definition(core, 'kd_owned_mutex_trylock_common(')
    result += 'enum kd_owned_mutex_preflight_result ' + definition(core, 'kd_owned_mutex_try_optimistic_pinned(')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mutations', action='store_true')
    args = parser.parse_args()
    core = (ROOT/'kernel_module/owned_mutex/core.c').read_text()
    osq = (ROOT/'kernel_module/owned_mutex/osq.c').read_text()
    internal = (ROOT/'include/kd_owned_mutex_internal.h').read_text()
    original = production(core, osq, internal)
    mutations = {
        'ignore-budget': ('return !--*remaining;', 'return false;'),
        'timeout-drops-grant': ('\t\treturn true;\n\n\t/* unqueue */',
                               '\t\treturn remaining && !*remaining ? false : true;\n\n\t/* unqueue */'),
        'step-a-drops-grant': ('if (smp_load_acquire(&node->locked))\n\t\t\treturn true;',
                              'if (smp_load_acquire(&node->locked))\n\t\t\treturn false;'),
        'skip-timeout-unlink': ('\t/* unqueue */', '\tif (remaining && !*remaining) return false;\n\t/* unqueue */'),
        'step-b-wrong-tail': ('old = prev ? prev->cpu : OSQ_UNLOCKED_VAL;',
                             'old = OSQ_UNLOCKED_VAL; (void)prev;'),
        'step-c-wrong-prev': ('WRITE_ONCE(next->prev, prev);', 'WRITE_ONCE(next->prev, node);'),
        'step-c-drops-successor': ('WRITE_ONCE(prev->next, next);', 'WRITE_ONCE(prev->next, NULL);'),
        'stale-predecessor': ('prev = READ_ONCE(node->prev);', '(void)READ_ONCE(node->prev);'),
        'preflight-retains-osq': ('\tkd_owned_osq_unlock(&lock->osq);', '\t/* leak */'),
        'budget-reset-before-owner': ('for (i = 0; i < spins; i++) {',
                                     'spins = 4;\n\tfor (i = 0; i < spins; i++) {'),
    }
    variants = [('production', original)]
    if args.mutations:
        for name, (old, new) in mutations.items():
            assert original.count(old) == 1, (name, original.count(old))
            variants.append((name, original.replace(old, new)))
    with tempfile.TemporaryDirectory(prefix='kd-owned-osq-') as directory:
        path = Path(directory)
        for name, source in variants:
            (path/'osq_production.h').write_text(source)
            binary = path/name
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-I'+directory,
                str(ROOT/'tests/unit/mutex/owned_mutex_osq_fixture.c'), '-o', str(binary),
            ], check=True, timeout=30)
            result = subprocess.run([binary], capture_output=True, text=True, timeout=10)
            if name == 'production':
                assert result.returncode == 0, result.stdout+result.stderr
                print(result.stdout, end='')
            else:
                assert result.returncode != 0, f'mutation survived: {name}'
                print(f'[PASS] bounded OSQ fixture rejects {name}')


if __name__ == '__main__':
    main()
