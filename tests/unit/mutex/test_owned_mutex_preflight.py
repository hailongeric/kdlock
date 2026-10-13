"""Guest-only production preflight/OSQ extraction and meaningful fault mutations.

The fixture models scheduling and atomics deterministically. It does not claim
concurrent OSQ validation or replace actual compiled/JIT outer-cookie checks.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from source_text import ROOT


def definition(source, marker):
    start = source.index(marker)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end] + '\n'


def main():
    core = (ROOT/'kernel_module/owned_mutex/core.c').read_text()
    osq = (ROOT/'kernel_module/owned_mutex/osq.c').read_text()
    delegate = (ROOT/'kernel_module/owned_mutex/delegation.c').read_text()
    internal = (ROOT/'include/kd_owned_mutex_internal.h').read_text()
    types = definition(internal, 'enum kd_owned_mutex_preflight_result {') + ';\n'
    types += definition(osq, 'struct kd_owned_osq_node {') + ';\n'
    production = 'static inline int ' + definition(osq, 'kd_owned_osq_encode_cpu(int cpu_nr)')
    production += 'static inline struct kd_owned_osq_node *' + definition(osq, 'kd_owned_osq_wait_next(')
    production += 'bool ' + definition(osq, 'kd_owned_osq_trylock(')
    production += 'void ' + definition(osq, 'kd_owned_osq_unlock(')
    production += 'static struct task_struct *' + definition(internal, 'kd_owned_mutex_owner(')
    production += 'static struct task_struct *' + definition(core, 'kd_owned_mutex_trylock_common(')
    production += 'enum kd_owned_mutex_preflight_result ' + definition(core, 'kd_owned_mutex_try_optimistic_pinned(')
    production += 'static bool ' + definition(delegate, 'kd_owned_mutex_preflight_spins_valid(')
    production += 'static bool ' + definition(delegate, 'kd_owned_mutex_delegation_eligible(')
    production += 'bool ' + definition(delegate, 'kd_owned_mutex_outer_preflight_v1(')
    # Run the real prepared entry too: false from the C gate grants capture
    # permission, with no eligibility lease or resource carried across it.
    prepared = definition(delegate, 'kd_owned_mutex_contended(')
    assert 'kd_hotlock_' not in prepared
    assert prepared.index('kd_owned_mutex_delegation_eligible()') < prepared.index('kd_mutex_task_get(current)')
    production += 'static unsigned long ' + prepared
    capture = 'unsigned long ' + definition(delegate, 'kd_owned_mutex_outer_contended_clobber_v1(')
    production += capture
    production += 'unsigned long ' + definition(delegate, 'kd_owned_mutex_outer_prepared_clobber_v1(')
    mutations = {
        'retain-osq': ('\tkd_owned_osq_unlock(&lock->osq);', '\t/* deliberately retain OSQ */'),
        'ignore-budget': ('i < spins; i++', 'i < spins + 1; i++'),
        'ignore-scheduler': ('if (need_resched())', 'if (false && need_resched())'),
        'ignore-owner-cpu': ('if (!owner_on_cpu(owner))', 'if (false && !owner_on_cpu(owner))'),
        'zero-budget-retries': ('if (!spins)\n\t\treturn result;', 'if (false)\n\t\treturn result;'),
        'omit-node-initialization': ('\tnode->next = NULL;', '\t/* stale successor */'),
        'duplicate-observation': ('\tkd_hotlock_owned_mutex_entry();', '\tkd_hotlock_owned_mutex_entry();\n\tkd_hotlock_owned_mutex_entry();'),
        'skip-prepared-eligibility': ('if (owned_mutex_self_route || !kd_owned_mutex_delegation_eligible())',
                                      'if (owned_mutex_self_route || (false && !kd_owned_mutex_delegation_eligible()))'),
        'duplicate-gate-eligibility': ('result == KD_OWNED_MUTEX_PREFLIGHT_BUSY)',
                                       'result == KD_OWNED_MUTEX_PREFLIGHT_BUSY && kd_owned_mutex_delegation_eligible())'),
        'prepared-resamples-attempt': ('\t/* The selected outer endpoint already made the exact heat observation.',
                                       '\tkd_hotlock_owned_mutex_entry();\n\t/* The selected outer endpoint already made the exact heat observation.'),
        'reference-before-eligibility': ('\tif (owned_mutex_self_route || !kd_owned_mutex_delegation_eligible())',
                                         '\t(void)kd_mutex_task_get(current);\n\tif (owned_mutex_self_route || !kd_owned_mutex_delegation_eligible())'),
        'ignore-task-get-failure': ('if (!kd_mutex_task_get(current))',
                                    'if ((kd_mutex_task_get(current), false))'),
        'consume-ref-on-self-refusal': ('self:\n\tkd_owned_mutex_lock_self(lock);',
                                        'self:\n\tkd_mutex_task_put(current);\n\tkd_owned_mutex_lock_self(lock);'),
        'omit-capture-first-observation': (
            capture, capture.replace('\tkd_hotlock_owned_mutex_entry();\n', '')),
        'leak-prepared-reference': ('\tkd_mutex_task_put(current);',
                                    '\tif (false) kd_mutex_task_put(current);'),
    }
    variants = [('production', production)]
    for name, (old, new) in mutations.items():
        assert old in production, name
        variants.append((name, production.replace(old, new)))
    with tempfile.TemporaryDirectory(prefix='kd-owned-preflight-') as directory:
        path = Path(directory)
        (path/'preflight_types.h').write_text(types)
        for name, body in variants:
            (path/'preflight_production.h').write_text(body)
            binary = path/name
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-I'+directory,
                str(ROOT/'tests/unit/mutex/owned_mutex_preflight_fixture.c'),
                '-o', str(binary),
            ], check=True, timeout=30)
            result = subprocess.run([binary], capture_output=True, text=True, timeout=10)
            if name == 'production':
                assert result.returncode == 0, result.stdout + result.stderr
                print(result.stdout, end='')
            else:
                assert result.returncode != 0, f'mutation survived: {name}'
                print(f'[PASS] owned preflight fixture rejects {name}')


if __name__ == '__main__':
    main()
