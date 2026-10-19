"""Guest-only production auxiliary registry with concurrent lookup and retirement.

The fixture uses real pthread contention and atomic bucket locks. Its conservative
RCU substitute defers callbacks until all readers leave, without preventing
concurrent unlink/publication. Slab allocation, kernel RCU and physical ownership
still require live mutex probes.
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
        'zero-reference-resurrected': (
            'if (!refs)\n\t\t\treturn false;',
            'if (false && !refs)\n\t\t\treturn false;',
        ),
        'free-before-grace-period': (
            'call_rcu(&aux->rcu, kd_mutex_aux_free);',
            '{ if (false) call_rcu(&aux->rcu, kd_mutex_aux_free);\n'
            '\t\t  else kd_mutex_aux_free(&aux->rcu); }',
        ),
        'missing-exit-callback-drain': (
            '\t\trcu_barrier();',
            '\t\t/* Mutation: destroy the cache before callbacks drain. */',
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
