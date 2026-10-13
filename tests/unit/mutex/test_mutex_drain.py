"""Guest-only native mutex drain invariant, with and without Linux OSQ."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from source_text import ROOT
from test_spin_shadow import definition


def main():
    source = (ROOT/'workload_modules/mutex_cacheline/module.c').read_text()
    body = definition(source, 'static int sc_workers_drain(void)')
    with tempfile.TemporaryDirectory(prefix='kd-mutex-drain-') as tmp:
        tmp = Path(tmp)
        (tmp/'drain_code.h').write_text(body)
        for osq in (False, True):
            binary = tmp/f'osq-{int(osq)}'
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                *(['-DCONFIG_MUTEX_SPIN_ON_OWNER'] if osq else []), '-I'+str(tmp),
                str(ROOT/'tests/unit/mutex/mutex_drain_fixture.c'), '-o', str(binary)],
                check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == '__main__':
    main()
