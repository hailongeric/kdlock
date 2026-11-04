"""Guest-only checks of the reference source-fetch and cache component."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from source_text import ROOT, read_source
from test_spin_shadow import definition


def main():
    source = read_source(ROOT / 'tests/unit/execution/reached_reference_adapter.inc')
    production = definition(source, 'static int kd_reached_frame_fetch(void *context, unsigned long address,')
    with tempfile.TemporaryDirectory(prefix='kd-reached-fetch-') as temporary:
        directory = Path(temporary)
        (directory / 'production.h').write_text(production)
        binary = directory / 'reached-fetch'
        subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
            '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
            '-I', str(directory),
            str(ROOT / 'tests/unit/execution/reached_fetch_fixture.c'), '-o', str(binary),
        ], check=True, timeout=30)
        subprocess.run([str(binary)], check=True, timeout=15)


if __name__ == '__main__':
    main()
