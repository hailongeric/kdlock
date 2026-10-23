"""Execute the rwlock port's actual acquisition/return assembly in the guest."""
import re
import subprocess
import tempfile
from pathlib import Path

from test_tclock_context import C, CHECK

ROOT = Path(__file__).resolve().parents[3]


def main():
    if not str(ROOT).startswith('/root/'):
        raise RuntimeError('execute machine-code tests only in the recovery guest')
    source = (ROOT / 'tclock_backend/komb_rwlock.c').read_text()
    marker = '#pragma GCC push_options\n#pragma GCC optimize("O3")\n__attribute__((noipa)) noinline notrace void\nkombrw_spin_lock_slowpath('
    begin = source.index(marker)
    end = source.index('#pragma GCC pop_options', begin) + len('#pragma GCC pop_options')
    switch = (ROOT / 'tclock_backend/combiner.c').read_text()
    switch = switch[switch.index('#pragma GCC push_options'):]
    header = (ROOT / 'tclock_backend/include/rwlock/komb_rwlock.h').read_text()
    node = re.search(r'struct komb_rwlock_node \{.*?\n\};', header, re.S).group(0)
    prefix = ('#include <stdint.h>\nstruct qspinlock;\n'
              'typedef uint8_t u8; typedef uint16_t u16;\n'
              '#define noinline __attribute__((noinline))\n'
              '#define notrace __attribute__((no_instrument_function))\n')
    fixture = C.replace('komb_node', 'komb_rwlock_node').replace('komb_spin_lock_slowpath', 'kombrw_spin_lock_slowpath')
    fixture = fixture.replace('kombrw_spin_lock_slowpath(void *)', 'kombrw_spin_lock_slowpath(struct qspinlock *)')
    fixture = fixture.replace('TCLock C inline asm', 'TCLock rwlock C inline asm')
    declarations = ('#include <stddef.h>\n/* User-mode fixture cannot execute CLI/STI; IRQ behavior is checked live. */\n#define local_irq_disable() ((void)0)\n#define local_irq_enable() ((void)0)\nstruct komb_rwlock_node *get_komb_rwlock_node(void);\n'
                    'uint64_t *get_shadow_stack_ptr(void);\nint __kombrw_spin_lock_slowpath(void *);\n')
    with tempfile.TemporaryDirectory(prefix='tc-rw-context-') as temporary:
        p = Path(temporary)
        (p / 'test.c').write_text(prefix + node + '\n' + fixture)
        (p / 'inline.c').write_text(prefix + node + '\n' + declarations + switch + '\n' + source[begin:end])
        (p / 'check.S').write_text(CHECK)
        flags = ['-O2', '-fno-omit-frame-pointer', '-mno-red-zone', '-fno-pie',
                 '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter']
        subprocess.run(['cc', *flags, '-mpreferred-stack-boundary=3', '-c', p / 'inline.c',
                        '-o', p / 'inline.o'], check=True, timeout=30)
        subprocess.run(['cc', *flags, '-no-pie', p / 'inline.o', p / 'check.S', p / 'test.c',
                        '-o', p / 'test'], check=True, timeout=30)
        subprocess.run([p / 'test'], check=True, timeout=10)


if __name__ == '__main__':
    main()
