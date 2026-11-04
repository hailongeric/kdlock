"""VM-only execution of actual generated code against the reference effects."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from source_text import ROOT


def main():
    with tempfile.TemporaryDirectory(prefix='kd-reached-jit-') as name:
        out = Path(name)
        for source, target in [('kd_reached.c', 'reference.h'), ('kd_reached_atomic.c', 'native.h')]:
            text = (ROOT / 'kernel_module' / source).read_text()
            text = '\n'.join(line for line in text.splitlines()
                             if not line.startswith(('#include <linux/', '#include <asm/')))
            (out / target).write_text(text)
        binary = out / 'jit-check'
        subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
            '-std=gnu11', '-O2', '-no-pie', '-Wall', '-Wextra', '-Werror',
            '-I', str(ROOT / 'include'), '-I', str(ROOT / 'kernel_module'), '-I', str(out),
            str(ROOT / 'tests/unit/execution/jit_compile_fixture.c'), '-o', str(binary),
        ], check=True, timeout=45)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, (result.returncode, result.stdout, result.stderr[-3500:])
        print(result.stdout, end='')


if __name__ == '__main__':
    main()
