"""Guest-only generation boundary: MM stays local when public rwsem opts in.

This writes only an isolated temporary output, never the kernel source/build.
It does not compile a kernel or claim actual MM execution.
"""
import importlib.util
from pathlib import Path
import re
import tempfile

from source_text import ROOT
from test_spin_shadow import definition


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
        private = target / 'kernel/locking/kd_mmap'
        mutex = (private / 'kd_mmap_mutex_local.c').read_text()
        header = (private / 'kd_mmap_mutex.h').read_text()
        for name in outputs:
            if name.endswith(('.c', '.h')):
                generated = (target / name).read_text()
                assert not re.search(r'\b(?:kd_mmap_mutex_(?:custody|task_custody|note_native)\w*|'
                                     r'KD_MMAP_MUTEX_CUSTODY\w*)\b', generated), name
        assert '\tstruct kd_mmap_regs regs __attribute__((aligned(64)));' in header
        # The standalone IRQ module retains the module I/O resolver while
        # sharing precisely the builtin's removal of provider-only notes.
        original = (ROOT / 'kernel_module/kd_mutex_local.c').read_text()
        module = generator.rename(generator.local_mutex_source(original))
        assert 'kallsyms_lookup_name("io_schedule_prepare")' in module
        assert 'kd_mmap_io_prepare();' in module
        assert 'int old = io_schedule_prepare();' in mutex
        for marker in (
            'static int kd_local_lock_state(struct kd_mutex *lock, unsigned int state,',
            'int kd_mutex_trylock(struct kd_mutex *lock)',
            'void kd_mutex_local_unlock(struct kd_mutex *lock)',
        ):
            expected = definition(original, marker)
            expected = re.sub(r'kd_mutex_note_native_(?:acquire|release)\(lock\);',
                              '(void)lock; /* Local MM has no delegated owner custody. */', expected)
            for generated in (mutex, module):
                assert definition(generated, generator.rename(marker)) == generator.rename(expected)
    print('PASS generated MM retains local mutex/rwsem bodies, I/O bridges and no provider custody/delegation dependency')


if __name__ == '__main__':
    main()
