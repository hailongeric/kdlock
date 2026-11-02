"""Guest-only generation boundary: MM stays local when public rwsem opts in.

This writes only an isolated temporary output, never the kernel source/build.
It does not compile a kernel or claim actual MM execution.
"""
import importlib.util
from pathlib import Path
import re
import tempfile

from source_text import ROOT


def main():
    spec = importlib.util.spec_from_file_location(
        'mmap_local_generator', ROOT / 'kernel_integration/mmap_lock/prepare.py')
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    with tempfile.TemporaryDirectory(prefix='kd-mmap-local-') as directory:
        target = Path(directory)
        inputs, outputs = generator.generated_sources(target)
        source = (target / 'kernel/locking/kd_mmap/kd_mmap_rwsem.c').read_text()
        unlock = re.search(r'void kd_mmap_up_write\([^)]*\)\s*\{([^}]+)\}', source).group(1)
        assert 'kd_mmap_mutex_local_unlock(&sem->gate);' in unlock
        assert 'kd_mmap_rwsem_release_local(sem);' in unlock
        assert not re.search(r'kd_mmap_(?:mutex_api_unlock|rwsem_(?:write_release|delegate_\w+|reserve_delegate))\s*\(', source)
        assert not any(name.endswith(('kd_rwsem_api.c', 'kd_rwsem_api.h')) for name in inputs)
        assert all(generator.digest(target / name) == expected for name, expected in outputs.items())
        assert 'void kd_mmap_downgrade_write(' in source
        assert 'kd_mmap_rwsem_spin_read' in source
        assert 'kd_mmap_wait_link_locked' in source
        assert 'kd_mmap_wait_set_state_locked' in source
        common = target / 'kernel/locking/kd_mmap/kd_mmap_wait_queue.c'
        assert common.is_file() and 'kd_mmap_wait_decide_locked' in common.read_text()
        assert (target / 'include/linux/kd_mmap_wait_queue.h').is_file()
        assert 'KD_MMAP_RWSEM_CONDITION_DELEGATE_WRITE' not in source
        assert 'kernel_module/kd_wait_queue.c' in inputs and 'include/kd_wait_queue.h' in inputs
    print('PASS generated MM retains local unlock/downgrade and no public delegation dependency')


if __name__ == '__main__':
    main()
