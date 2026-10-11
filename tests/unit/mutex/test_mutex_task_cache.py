"""Compile production task-cache decisions with controlled allocation/RCU.

The live task probe separately exercises real RCU readers and owner ACKs.
This fixture controls collisions, eviction/reactivation and allocation failure.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from source_text import ROOT, read_source, without_includes


def main():
    source = without_includes(read_source(ROOT / 'kernel_module/kd_mutex_tasks.c'))
    with tempfile.TemporaryDirectory(prefix='kd-mutex-cache-') as tmp:
        path = Path(tmp)
        (path / 'task_cache_production.h').write_text(source)
        binary = path / 'fixture'
        subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
            '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-I', str(path),
            str(ROOT / 'tests/unit/mutex/mutex_task_cache_fixture.c'),
            '-o', str(binary)], check=True, timeout=30)
        result = subprocess.run([str(binary)], text=True, capture_output=True,
                                check=True, timeout=15)
        print(result.stdout, end='')


if __name__ == '__main__':
    main()
