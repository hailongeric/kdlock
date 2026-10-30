"""Guest-only bounded killable writer admission and exact phase rollback.

Extract production functions without replacing their admission, poll or rollback
logic. Atomic, scheduler and wait primitives are deterministic control-flow
doubles, not a proof of concurrent memory ordering, kernel signal delivery or
exact waitqueue membership. Synthetic wait-boundary counts include attempts a
real prepare_to_wait_event may refuse without enqueueing.
All negative controls must compile and terminate with an assertion failure;
compile errors, timeouts and unrelated crashes are not detected mutations.
"""
import os
import resource
import shlex
import signal
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, read_source
from test_spin_shadow import definition


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new, 1)


def main():
    source = read_source(ROOT / 'kernel_module/kd_rwsem.c')
    names = (
        'void kd_up_read(struct kd_rwsem *sem)',
        'static int kd_rwsem_drain_readers(struct kd_rwsem *sem, unsigned int state)',
        'static bool kd_rwsem_reserve_local(struct kd_rwsem *sem)',
        'static __always_inline bool kd_rwsem_poll_killable(struct kd_rwsem *sem)',
        'static void kd_rwsem_release_local(struct kd_rwsem *sem)',
        'int kd_down_write_killable(struct kd_rwsem *sem)',
        'void kd_downgrade_write(struct kd_rwsem *sem)',
    )
    functions = [definition(source, name) for name in names]
    code = '\n'.join(functions)
    helper, acquire = functions[3], functions[5]
    success = '\t\tif (kd_rwsem_reserve_local(sem))\n\t\t\treturn true;\n'
    stop = ('\t\tif (need_resched() || signal_pending_state(TASK_KILLABLE, current))\n'
            '\t\t\treturn false;\n')
    # Keep these mutations scoped to the new helper or exact killable path.
    # Every substitute remains syntactically referenced, including deliberately
    # skipped calls, so -Werror does not turn a missing behavior into a pass.
    mutations = {
        'successful-reservation-repeated': (helper, replace_once(
            helper, success, success.replace('return true;',
                                            'return kd_rwsem_reserve_local(sem);'))),
        'stop-before-reservation': (helper, replace_once(helper, success + stop, stop + success)),
        'fatal-signal-ignored': (helper, replace_once(
            helper, 'signal_pending_state(TASK_KILLABLE, current)',
            '(false && signal_pending_state(TASK_KILLABLE, current))')),
        'poll-budget-shortened': (helper, replace_once(helper, 'budget = 16384;', 'budget = 16383;')),
        'fallback-reservation-skipped': (acquire, replace_once(
            acquire, 'wait_event_killable(sem->phase_wait, kd_rwsem_reserve_local(sem))',
            'wait_event_killable(sem->phase_wait, (false && kd_rwsem_reserve_local(sem)))')),
        'queued-readers-ignored': (functions[2], replace_once(
            functions[2], 'atomic_read(&sem->reader_osq.tail)',
            '(false && atomic_read(&sem->reader_osq.tail))')),
        'reader-drain-skipped': (acquire, replace_once(
            acquire, 'kd_rwsem_drain_readers(sem, TASK_KILLABLE)',
            '(false ? kd_rwsem_drain_readers(sem, TASK_KILLABLE) : 0)')),
        'phase-released-before-gate': (acquire, replace_once(
            acquire, '\t\tkd_mutex_local_unlock(&sem->gate);',
            '\t\tkd_rwsem_release_local(sem);\n\t\tkd_mutex_local_unlock(&sem->gate);')),
        'phase-reservation-leaked': (acquire, replace_once(
            acquire, '\tkd_rwsem_release_local(sem);', '\t(void)kd_rwsem_release_local;')),
    }
    # Assertion failures in negative controls should not leave core artifacts.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    with tempfile.TemporaryDirectory(prefix='kd-rwsem-killable-') as directory:
        path = Path(directory)
        compiler = shlex.split(os.environ.get('CC', 'cc'))
        for name, replacement in [('production', None), *mutations.items()]:
            body = code if replacement is None else replace_once(code, *replacement)
            (path / 'rwsem_killable_production.h').write_text(body)
            binary = path / name
            subprocess.run(compiler + ['-O2', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                       '-UNDEBUG', '-I', str(path),
                                       str(ROOT / 'tests/unit/mutex/rwsem_killable_poll_fixture.c'),
                                       '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            if replacement is None:
                assert result.returncode == 0, result.stdout + result.stderr
                assert 'PASS killable admission: 22 ' in result.stdout, result.stdout
                print(result.stdout, end='')
            else:
                assert result.returncode == -signal.SIGABRT, (name, result.returncode,
                                                            result.stdout, result.stderr)
                assert 'Assertion' in result.stderr, (name, result.stderr)
                print('killable admission mutation detected:', name)


if __name__ == '__main__':
    main()
