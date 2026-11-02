"""Guest-only production common queue with deterministic primitive substitutes.

The fixture checks topology, grant/cancel order and retained lifecycle custody;
it does not establish concurrent kernel scheduling, memory ordering or timing.
"""
import os
import resource
import shlex
import signal
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, read_source, without_includes


def production():
    return (without_includes(read_source(ROOT / 'include/kd_wait_queue.h')) + '\n' +
            without_includes(read_source(ROOT / 'kernel_module/kd_wait_queue.c')))


def replace_once(text, before, after):
    assert text.count(before) == 1, (before, text.count(before))
    return text.replace(before, after, 1)


def replace_function(text, start, before, after):
    # The real definition follows its header declaration in the combined text.
    first = text.rindex(start)
    last = text.index('\n}', first) + 2
    return text[:first] + replace_once(text[first:last], before, after) + text[last:]


def run_cases(head_only=False, mutations=None):
    source = production()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    fixture = 'mutex_head_fixture.c' if head_only else 'wait_queue_fixture.c'
    with tempfile.TemporaryDirectory(prefix='kd-wait-queue-') as directory:
        path = Path(directory)
        for name, mutate in [('production', None), *(mutations or {}).items()]:
            candidate = source if mutate is None else mutate(source)
            (path / 'wait_queue_production.h').write_text(candidate)
            binary = path / name
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-UNDEBUG',
                '-I', str(path), str(ROOT / 'tests/unit/mutex' / fixture),
                '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary), *(['head'] if head_only else [])],
                                    capture_output=True, text=True, timeout=15)
            if mutate is None:
                assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
                assert 'PASS production common queue' in result.stdout, result.stdout
                print(result.stdout, end='')
            else:
                assert result.returncode == -signal.SIGABRT, (
                    name, result.returncode, result.stdout, result.stderr)
                assert 'Assertion' in result.stderr, (name, result.stderr)
                print('common queue mutation detected:', name)


if __name__ == '__main__':
    run_cases()
