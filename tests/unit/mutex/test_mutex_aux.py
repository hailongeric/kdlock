"""Guest-only production auxiliary registry with concurrent lookup and retirement.

The fixture uses real pthread contention and atomic bucket locks; the allocator
and kernel scheduling are substitutes. Live mutex probes remain required.
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
    with tempfile.TemporaryDirectory(prefix='kd-mutex-aux-') as tmp:
        path = Path(tmp)
        (path / 'aux_types.h').write_text(types)
        (path / 'aux_production.h').write_text(source)
        binary = path / 'fixture'
        subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
            '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread',
            '-I', str(path), str(ROOT / 'tests/unit/mutex/mutex_aux_fixture.c'),
            '-o', str(binary)], check=True, timeout=30)
        result = subprocess.run([str(binary)], capture_output=True, text=True,
                                check=True, timeout=45)
        print(result.stdout, end='')


if __name__ == '__main__':
    main()
