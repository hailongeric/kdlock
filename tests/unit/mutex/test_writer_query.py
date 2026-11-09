"""Guest-only production ownership query and descriptor-consumer fixture.

Physical task/frame observations and Native scheduling are supplied. This
executes the actual query, origin transaction lookup and provider initializer;
it is not a live MM or concurrent registry-lifetime test.
"""
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, read_source, without_includes
from test_spin_shadow import definition


def main():
    service = read_source(ROOT / 'kernel_module/kd_service.c')
    provider = read_source(ROOT / 'kernel_module/kd_rwsem_provider.c')
    source = '\n'.join((
        definition(service, 'static struct kd_service_root *kd_service_origin_scope(void)'),
        definition(service, 'bool kd_service_write_owned(void *object, struct task_struct *task)'),
        definition(provider, 'int kd_rwsem_provider_init(void)'),
    ))
    with tempfile.TemporaryDirectory(prefix='kd-writer-query-') as directory:
        path = Path(directory)
        (path / 'provider_types.h').write_text(without_includes(
            read_source(ROOT / 'include/kd_rwsem_provider.h')))
        (path / 'query_production.h').write_text(source)
        binary = path / 'query'
        subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
            '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-UNDEBUG',
            '-I', str(path), str(ROOT / 'tests/unit/mutex/writer_query_fixture.c'),
            '-o', str(binary)], check=True, timeout=30)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
        print(result.stdout, end='')


if __name__ == '__main__':
    main()
