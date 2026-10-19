"""Guest-only production fixed-slot auxiliary registry and deterministic races.

Permanent table storage, real pthread atomics and scheduled pause points expose
reference/key ABA, cross-generation observations and premature slot reuse. The
fixture also checks contention, refusal and exact owner/frame lifetimes. Kernel
allocation, weak-memory ordering and physical fallback need the affected live
and queue probes; this fixture does not substitute for them.
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
    for name in ('kd_mutex', 'kd_mutex_aux'):
        types += without_includes(read_source(ROOT / f'include/{name}.h')) + '\n'
    source = without_includes(read_source(ROOT / 'kernel_module/kd_mutex_aux.c'))
    mutations = {
        'missing-post-pin-key-validation': (
            'if (likely(READ_ONCE(aux->lock) == lock))',
            'if (likely(true))',
        ),
        'missing-observation-sequence-validation': (
            'return READ_ONCE(aux->sequence) == sequence;',
            'return (void)aux, (void)sequence, true;',
        ),
        'free-before-retirement': (
            'BUG_ON(READ_ONCE(aux->physical_owner) || atomic_read(&aux->state) ||',
            'atomic_long_set_release(&aux->refs, KD_MUTEX_AUX_FREE);\n\t'
            'BUG_ON(READ_ONCE(aux->physical_owner) || atomic_read(&aux->state) ||',
        ),
        'skip-final-zero-reservation': (
            'if (refs != 1 || atomic_long_cmpxchg(&aux->refs, 0, KD_MUTEX_AUX_BUSY))',
            'if (refs != 1)',
        ),
        'publication-erases-rejected-pin': (
            'atomic_long_add_return(1 - KD_MUTEX_AUX_BUSY, &aux->refs);',
            'atomic_long_set_release(&aux->refs, 1);',
        ),
        'retirement-erases-rejected-pin': (
            'never access the slot after this add. */\n\t'
            'atomic_long_add_return(KD_MUTEX_AUX_FREE - KD_MUTEX_AUX_BUSY, &aux->refs);',
            'never access the slot after this add. */\n\t'
            'atomic_long_set_release(&aux->refs, KD_MUTEX_AUX_FREE);',
        ),
        'rejected-pin-skips-live-retirement': (
            'kd_mutex_aux_put(aux);\n\treturn false;',
            '(void)atomic_long_fetch_dec(&aux->refs);\n\treturn false;',
        ),
        'accept-negative-pin': (
            'if (likely((unsigned long)refs < KD_MUTEX_AUX_MAX_REFS))',
            'if (likely(true))',
        ),
        'pin-accepts-admission-bound': (
            'if (likely((unsigned long)refs < KD_MUTEX_AUX_MAX_REFS))',
            'if (likely((unsigned long)refs <= KD_MUTEX_AUX_MAX_REFS))',
        ),
        'pin-ignores-invalid-positive': (
            'BUG_ON(refs >= 0 || ((unsigned long)refs & KD_MUTEX_AUX_COUNT_MASK) >=\n\t'
            '       KD_MUTEX_AUX_MAX_REFS);',
            'BUG_ON(((unsigned long)refs & KD_MUTEX_AUX_COUNT_MASK) >=\n\t'
            '       KD_MUTEX_AUX_MAX_REFS);',
        ),
        'pin-ignores-negative-admission-bound': (
            'BUG_ON(refs >= 0 || ((unsigned long)refs & KD_MUTEX_AUX_COUNT_MASK) >=\n\t'
            '       KD_MUTEX_AUX_MAX_REFS);',
            'BUG_ON(refs >= 0);',
        ),
        'put-fast-accepts-zero': (
            'if (likely((unsigned long)refs - 2 <',
            'if (likely((unsigned long)refs <',
        ),
        'put-imposes-getter-admission-bound': (
            'refs > (long)KD_MUTEX_AUX_COUNT_MASK);',
            'refs > (long)KD_MUTEX_AUX_MAX_REFS);',
        ),
        'put-ignores-count-underflow': (
            'BUG_ON(!((unsigned long)refs & KD_MUTEX_AUX_COUNT_MASK) ||\n\t'
            '       refs > (long)KD_MUTEX_AUX_COUNT_MASK);',
            'BUG_ON(refs > (long)KD_MUTEX_AUX_COUNT_MASK);',
        ),
        'put-ignores-invalid-positive': (
            'BUG_ON(!((unsigned long)refs & KD_MUTEX_AUX_COUNT_MASK) ||\n\t'
            '       refs > (long)KD_MUTEX_AUX_COUNT_MASK);',
            'BUG_ON(!((unsigned long)refs & KD_MUTEX_AUX_COUNT_MASK));',
        ),
        'fault-rollback-erases-rejected-pin': (
            'this_cpu_inc(kd_mutex_aux_injected_failures);\n\t\t'
            'atomic_long_add_return(KD_MUTEX_AUX_FREE - KD_MUTEX_AUX_BUSY, &aux->refs);',
            'this_cpu_inc(kd_mutex_aux_injected_failures);\n\t\t'
            'atomic_long_set_release(&aux->refs, KD_MUTEX_AUX_FREE);',
        ),
        'exhaustion-rollback-erases-rejected-pin': (
            'smp_store_release(&aux->sequence, U64_MAX);\n\t\t'
            'atomic_long_add_return(KD_MUTEX_AUX_FREE - KD_MUTEX_AUX_BUSY, &aux->refs);',
            'smp_store_release(&aux->sequence, U64_MAX);\n\t\t'
            'atomic_long_set_release(&aux->refs, KD_MUTEX_AUX_FREE);',
        ),
        'borrow-ignores-current-owner': (
            'READ_ONCE(aux->physical_owner) == current;',
            'READ_ONCE(aux->physical_owner) != NULL;',
        ),
        'borrow-ignores-key': (
            'owned = READ_ONCE(aux->lock) == lock &&\n\t\tREAD_ONCE(aux->physical_owner) == current;',
            'owned = READ_ONCE(aux->physical_owner) == current;',
        ),
        'borrow-ignores-sequence-validation': (
            'if (!kd_mutex_aux_observation_valid(aux, sequence) || !owned)',
            'if (!owned)',
        ),
    }
    candidates = {'production': source}
    for name, (old, new) in mutations.items():
        assert source.count(old) == 1, (name, source.count(old))
        candidates[name] = source.replace(old, new)
    with tempfile.TemporaryDirectory(prefix='kd-mutex-aux-') as tmp:
        path = Path(tmp)
        (path / 'aux_types.h').write_text(types)
        for name, candidate in candidates.items():
            (path / 'aux_production.h').write_text(candidate)
            binary = path / name
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread',
                '-I', str(path), str(ROOT / 'tests/unit/mutex/mutex_aux_fixture.c'),
                '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], capture_output=True, text=True,
                                    timeout=45)
            if name == 'production':
                assert result.returncode == 0, (result.stdout, result.stderr)
                print(result.stdout, end='')
            else:
                # Compiler errors, crashes and timeouts do not kill a mutant.
                assert result.returncode == 1 and 'FAIL aux line ' in result.stderr, (
                    name, result.returncode, result.stdout, result.stderr)
                print(f'mutation detected: {name}')


if __name__ == '__main__':
    main()
