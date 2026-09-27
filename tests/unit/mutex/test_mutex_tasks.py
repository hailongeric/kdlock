"""Guest-only stable task-cache C concurrency and lifecycle checks.

Task references are substitutes. The kernel SELFTEST separately exercises
real task references, physical owners and final native ACK ordering.
"""
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, without_includes


def main():
    code = without_includes((ROOT / 'kernel_module/kd_mutex_tasks.c').read_text())
    mutations = {
        'inactive-key-routes': ('return entry && atomic_read(&entry->refs) > 0;',
                               'return entry != NULL;'),
        'acquisition-ref-overwritten': ('atomic_inc(&entry->refs);',
                                       'atomic_store(&entry->refs.value, 1);'),
        'losing-publication-leaks-task': ('if (seen)\n\t\t\t\tput_task_struct(task);',
                                         'if (false && seen)\n\t\t\t\tput_task_struct(task);'),
        'task-released-before-unload': ('/* A final put makes the cache entry inactive',
                                       'put_task_struct(task);\n\t/* A final put makes the cache entry inactive'),
    }
    with tempfile.TemporaryDirectory(prefix='kdlock-mutex-tasks-') as tmp:
        path = Path(tmp)
        for name, mutation in [('production', None), *mutations.items()]:
            source = code
            if mutation:
                before, after = mutation
                assert source.count(before) == 1, (name, source.count(before))
                source = source.replace(before, after)
            (path/'mutex_tasks_production.h').write_text(source)
            binary = path/name
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread',
                '-I', str(path), str(ROOT/'tests/unit/mutex/mutex_tasks_fixture.c'),
                '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
            if mutation:
                assert result.returncode == 1 and 'FAIL line' in result.stderr, (
                    name, result.returncode, result.stdout, result.stderr)
                print('mutex task mutation detected:', name)
            else:
                print(result.stdout, end='')
                assert result.returncode == 0, result.stderr


if __name__ == '__main__':
    main()
