"""VM-only production observation helpers: off/on, time bounds and conservation."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from source_text import ROOT, read_source, without_includes
from test_spin_shadow import definition


def main():
    code = without_includes(read_source(ROOT / 'kernel_module/kd_service_observe.inc'))
    code += definition(read_source(ROOT / 'kernel_module/kd_service.c'),
                       'static int kd_service_observe_local(int index, bool no_image, void *object,')
    with tempfile.TemporaryDirectory(prefix='kd-service-observe-') as directory:
        path = Path(directory)
        (path / 'observe_production.h').write_text(code)
        binary = path / 'observe'
        subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
            '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-UNDEBUG',
            '-I', str(path), str(ROOT / 'tests/unit/execution/service_observe_fixture.c'),
            '-o', str(binary)], check=True, timeout=30)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
        print(result.stdout, end='')


if __name__ == '__main__':
    main()
