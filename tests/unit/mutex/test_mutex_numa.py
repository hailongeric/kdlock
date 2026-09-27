"""Run production mutex selection, rollback, splice and combiner boundaries.

The wrapper, owner primitives and ACK wait are deterministic substitutes. Node
layout and the full batch loop are real; this is not a concurrency/fairness proof.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from source_text import ROOT, read_source, without_includes
from test_spin_shadow import definition


def main():
    kernel = Path(f'/lib/modules/{os.uname().release}/build')
    ptrace = (kernel/'arch/x86/include/asm/ptrace.h').read_text().split('#else /* __i386__ */', 1)[1]
    types = definition(ptrace, 'struct pt_regs {').rstrip() + ';\n'
    types += definition(read_source(ROOT/'include/kd_spin_entry.h'), 'struct kd_spin_ref {').rstrip() + ';\n'
    for name in ('exe_info', 'kd_call', 'kd_exec', 'kd_mutex'):
        types += without_includes(read_source(ROOT/f'include/{name}.h')) + '\n'
    source = read_source(ROOT/'kernel_module/kd_mutex.c')
    helpers = source[source.index('struct kd_mutex_batch {'):
                     source.index('static struct kd_exe_info *\nkd_mutex_batch_find_ready')]
    helpers += definition(source, 'static int kd_mutex_release_outer(struct kd_exec_frame *frame,') + '\n'
    loop = 'static void\n' + definition(source, 'run_combiner(struct kd_mutex *lock, struct kd_mutex_node *curr_node)')
    with tempfile.TemporaryDirectory(prefix='kd-mutex-numa-') as tmp:
        path = Path(tmp)
        (path/'types.h').write_text(types)
        (path/'helpers.h').write_text(helpers)
        (path/'loop.h').write_text(loop)
        for numa in (False, True):
            binary = path/f'numa-{int(numa)}'
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) +
                           ['-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-I'+str(path), *(['-DNUMA_AWARE'] if numa else []),
                            str(ROOT/'tests/unit/mutex/mutex_numa_fixture.c'), '-o', str(binary)],
                           check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=15)


if __name__ == '__main__':
    main()
