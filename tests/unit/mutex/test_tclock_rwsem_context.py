"""Execute the rwsem writer's actual six-register stack-transfer assembly.

The shared context harness checks both original-waiter continuations. It does
not model rwsem reader admission, parking, IRQ state or live kernel scheduling.
"""
import re
import subprocess
import tempfile
from pathlib import Path

from test_tclock_context import C, CHECK, ROOT, TRAMPOLINE_OPTIONS, require_guest


def main():
    require_guest()
    source = (ROOT / 'tclock_backend/komb_rwsem.c').read_text()
    marker = TRAMPOLINE_OPTIONS + '__attribute__((noipa)) noinline notrace void\n__komb_write_stack_switch('
    begin = source.index(marker)
    end = source.index('#pragma GCC pop_options', begin) + len('#pragma GCC pop_options')
    switch = (ROOT / 'tclock_backend/combiner.c').read_text()
    switch = switch[switch.index('#pragma GCC push_options'):]
    # The production rwsem header includes the maintained mutex-node type.
    header = (ROOT / 'tclock_backend/include/mutex/komb_mutex.h').read_text()
    node = re.search(r'struct komb_mutex_node \{.*?\n\};', header, re.S).group(0)
    prefix = ('#include <stdint.h>\n#include <stddef.h>\n'
              'typedef uint8_t u8; typedef uint16_t u16; typedef long atomic_long_t;\n'
              'struct komb_rwsem;\n'
              '#define noinline __attribute__((noinline))\n'
              '#define notrace __attribute__((no_instrument_function))\n')
    fixture = C.replace('__komb_spin_lock_slowpath', 'komb_write_lock_slowpath')
    fixture = fixture.replace('komb_spin_lock_slowpath', '__komb_write_stack_switch')
    fixture = fixture.replace('struct komb_node', 'struct komb_mutex_node')
    fixture = fixture.replace('get_komb_node(void)', 'get_komb_mutex_node(struct komb_rwsem *unused)')
    fixture = fixture.replace('get_shadow_stack_ptr(void)', 'get_shadow_stack_ptr(struct komb_rwsem *unused)')
    fixture = fixture.replace('__komb_write_stack_switch(void *)',
                              '__komb_write_stack_switch(struct komb_rwsem *)')
    fixture = fixture.replace('PASS TCLock C', 'PASS TCLock rwsem C')
    declarations = ('struct komb_mutex_node *get_komb_mutex_node(struct komb_rwsem *);\n'
                    'uint64_t *get_shadow_stack_ptr(struct komb_rwsem *);\n'
                    'int komb_write_lock_slowpath(void *);\n')
    with tempfile.TemporaryDirectory(prefix='tc-rwsem-context-') as temporary:
        p = Path(temporary)
        (p / 'test.c').write_text(prefix + node + '\n' + fixture)
        (p / 'inline.c').write_text(prefix + node + '\n' + declarations + switch +
                                  '\n' + source[begin:end] + '\n')
        (p / 'check.S').write_text(CHECK)
        flags = ['-O2', '-fno-omit-frame-pointer', '-mno-red-zone', '-fno-pie',
                 '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter']
        subprocess.run(['cc', *flags, '-mpreferred-stack-boundary=3', '-c', p / 'inline.c',
                        '-o', p / 'inline.o'], check=True, timeout=30)
        subprocess.run(['cc', *flags, '-no-pie', p / 'inline.o', p / 'check.S',
                        p / 'test.c', '-o', p / 'test'], check=True, timeout=30)
        subprocess.run([p / 'test'], check=True, timeout=10)


if __name__ == '__main__':
    main()
