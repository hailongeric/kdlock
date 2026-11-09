"""Guest-only canonical queue/admission checks with deterministic primitives.

Compile the production queue, admission driver and physical owner/PICKUP
attempts. Scheduler, IRQ, atomic and physical-release primitives are narrow
substitutes. These checks do not prove JIT execution or kernel concurrency.
"""
import os
import resource
import shlex
import signal
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, read_source, without_includes
from test_spin_shadow import definition


def production():
    headers = '\n'.join(without_includes(read_source(ROOT / name)) for name in (
        'include/kd_wait_queue.h', 'include/kd_mutex_types.h',
        'include/kd_rwsem_types.h', 'include/kd_admission.h'))
    physical = read_source(ROOT / 'kernel_module/kd_mutex_local.c')
    owner = '\n'.join(definition(physical, name) for name in (
        'bool kd_mutex_admission_trylock_locked(struct kd_mutex *lock,',
        'bool kd_mutex_admission_transfer_locked(struct kd_mutex *lock,'))
    body = '\n'.join(without_includes(read_source(ROOT / name)) for name in (
        'kernel_module/kd_wait_queue.c', 'kernel_module/kd_admission.c'))
    return headers, owner, body


def replace_once(text, before, after):
    assert text.count(before) == 1, (before, text.count(before))
    return text.replace(before, after, 1)


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    headers, owner, body = production()
    mutations = {
        'signal_before_actual_grant': lambda text: replace_once(text,
            'if (grant(request, argument)) {',
            'if (!signal_pending_state(request->wait_state, request->logical_origin) && grant(request, argument)) {'),
        'missing_fresh_reader_drain': lambda text: replace_once(text,
            'if (atomic_long_read_acquire(&sem->readers)) {', 'if (false) {'),
        'executor_signal_instead_of_origin': lambda text: replace_once(text,
            'if (!signal_pending_state(request->wait_state, request->logical_origin))',
            'if (!signal_pending_state(request->wait_state, current))'),
        'writer_bypasses_queued_readers': lambda text: replace_once(text,
            'if (sem->phase_wait.readers_waiting ||\n\t\t\t    atomic_long_cmpxchg',
            'if (atomic_long_cmpxchg'),
    }
    with tempfile.TemporaryDirectory(prefix='kd-admission-') as directory:
        path = Path(directory)
        (path / 'admission_types.h').write_text(headers)
        (path / 'admission_physical.h').write_text(owner)
        reader = read_source(ROOT / 'kernel_module/kd_rwsem.c')
        (path / 'reader_wait_production.h').write_text(definition(
            reader, 'static long kd_rwsem_wait_condition(struct kd_rwsem *sem,'))
        (path / 'reader_release_production.h').write_text('\n'.join(
            definition(reader, name) for name in (
                'void kd_up_read(struct kd_rwsem *sem)',
                'void kd_up_read_non_owner(struct kd_rwsem *sem)')))
        for name, mutate in [('production', None), *mutations.items()]:
            (path / 'admission_production.h').write_text(body if mutate is None else mutate(body))
            binary = path / name
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-UNDEBUG',
                '-I', str(path), str(ROOT / 'tests/unit/mutex/admission_fixture.c'),
                '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
            if mutate is None:
                assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
                assert 'PASS production canonical admission' in result.stdout, result.stdout
                print(result.stdout, end='')
            else:
                assert result.returncode == -signal.SIGABRT, (
                    name, result.returncode, result.stdout, result.stderr)
                assert 'Assertion' in result.stderr, (name, result.stderr)
                print('canonical admission mutation detected:', name)


if __name__ == '__main__':
    main()
