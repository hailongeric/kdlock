"""VM-only actual spin batch loop with deterministic dispatcher/context returns.

This covers both cold generic and pending-FULL control paths. Physical CPU,
JIT/owner operations and scheduling are doubles; existing shadow/outer tests
retain real queue, owner and frame coverage. No concurrent kernel proof.
"""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

from source_text import ROOT, read_source
from test_spin_shadow import definition


def main():
    source = read_source(ROOT / 'kernel_module/kd_spinlock.c')
    types = (ROOT / 'include/kd_jit_batch.h').read_text()
    types += definition(read_source(ROOT / 'include/kd_exec.h'),
                        'struct kd_exec_outer_unlock {').rstrip() + ';\n'
    types += definition(source, 'struct kd_spin_batch {').rstrip() + ';\n'
    types += definition(read_source(ROOT / 'include/kd_spinlock.h'),
                        'enum kd_spin_cont_kind {').rstrip() + ';\n'
    for name in ('KD_EXE_NO_RUN', 'KD_EXE_RUN_ERROR', 'KD_EXE_NATIVE_DONE'):
        lines = [line for line in (ROOT / 'include/exe.h').read_text().splitlines()
                 if line.startswith('#define ' + name + ' ')]
        assert len(lines) == 1 and lines[0].split()[-1].isdigit(), name
        types += lines[0] + '\n'
    code = 'static __always_inline bool\n' + definition(
        source, 'kd_spin_proxy_context_matches(u8 origin, u8 executor)')
    code += definition(source, 'static void kd_spin_batch_run(void *opaque)')
    assignment = 'batch->proxy_context = kd_spin_proxy_context();'
    assert code.count(assignment) == 2
    guard = re.compile(r'if \(exe_flag != KD_EXE_NO_RUN &&\s*'
                       r'exe_flag != KD_EXE_RUN_ERROR &&\s*'
                       r'!batch->outer.released\)')
    assert len(guard.findall(code)) == 2
    candidates = {
        'production': code,
        'missing-generic-refresh': code.replace(assignment, '(void)0;'),
        'terminal-context-refresh': guard.sub('if (true)', code),
    }
    with tempfile.TemporaryDirectory(prefix='kd-spin-batch-context-') as directory:
        path = Path(directory)
        (path / 'types.h').write_text(types)
        for name, body in candidates.items():
            (path / 'production.h').write_text(body)
            for numa in (0, 1):
                binary = path / f'{name}-{numa}'
                subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                    '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-I', str(path), *(['-DNUMA_AWARE'] if numa else []),
                    str(ROOT / 'tests/unit/spin/spin_batch_context_fixture.c'),
                    '-o', str(binary)], check=True, timeout=30)
                result = subprocess.run([str(binary)], text=True,
                                        capture_output=True, timeout=10)
                if name == 'production':
                    assert result.returncode == 0, (name, numa, result.returncode,
                                                    result.stdout, result.stderr)
                    print(result.stdout, end='')
                else:
                    assert result.returncode == 1 and 'FAIL line=' in result.stderr, (
                        name, numa, result.returncode, result.stdout, result.stderr)
                    print('batch context mutation detected:', name, 'numa=', numa)


if __name__ == '__main__':
    main()
