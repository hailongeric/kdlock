"""Guest-only exact writer queue/phase ordering and cancellation checks.

Extract actual writer functions and polls. Gate/wait/atomic doubles exercise
control flow and reservation balance; the separate OSQ fixture and live rwsem
probe cover actual queue retirement and kernel signal delivery. No concurrent
memory-order or scheduler proof is implied. Negative controls must compile and
fail by assertion, never by timeout, compiler failure or unrelated signal.
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


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new, 1)


def main():
    source = read_source(ROOT / 'kernel_module/kd_rwsem.c')
    start = source.index('#define kd_rwsem_poll(condition)')
    end = source.index('\nvoid kd_rwsem_init(', start)
    macros = source[start:end]
    names = (
        'void kd_up_read(', 'static int kd_rwsem_drain_readers(',
        'static bool kd_rwsem_reserve_local(', 'static void kd_rwsem_release_local(',
        'static __always_inline int kd_rwsem_wait_local(',
        'static __always_inline int kd_rwsem_lock_gate(',
        'static __always_inline int kd_rwsem_down_write_state(',
        'void kd_down_write(', 'int kd_down_write_interruptible(',
        'int kd_down_write_killable(', 'int kd_down_write_trylock(',
        'void kd_downgrade_write(', 'static bool kd_rwsem_reserve_delegate(',
        'void kd_rwsem_delegate_enter(',
    )
    functions = {name: definition(source, next(line for line in source.splitlines()
                 if line.startswith(name))) for name in names}
    code = macros + '\n' + '\n'.join(functions.values())
    def mutate(name, old, new):
        body = functions[name]
        return once(code, body, once(body, old, new))
    # Scope budget/signal changes to the new state-aware poll, not reader polls.
    state = macros[macros.index('#define kd_rwsem_poll_state'):]
    variants = {
        'nonfatal-poll-ignored': once(code, state, once(state, 'signal_pending(current)',
            '((false && signal_pending(current)) || signal_pending_state(state, current))')),
        'poll-budget-shortened': once(code, state, once(state, '16384', '16383')),
        'reservation-repeated': mutate(names[4], '\t\treturn 0;',
            '\t\treturn kd_rwsem_reserve_local(sem) ? 0 : -EINTR;'),
        'queued-reader-hint-ignored': mutate(names[2], 'atomic_read(&sem->reader_osq.tail)',
            '(false && atomic_read(&sem->reader_osq.tail))'),
        'unprepared-uses-phase-first': mutate(names[6], 'if (prepared)', 'if (true || prepared)'),
        'prepared-uses-gate-first': mutate(names[6], 'if (prepared)', 'if (false && prepared)'),
        'scoped-gate-ignored': mutate(names[5],
            'return kd_mutex_local_lock_signal(&sem->gate, state);',
            '(void)kd_mutex_local_lock_signal; kd_mutex_local_lock(&sem->gate); return 0;'),
        'unowned-phase-released': mutate(names[6],
            '\t\t\tkd_mutex_local_unlock(&sem->gate);',
            '\t\t\tkd_mutex_local_unlock(&sem->gate);\n\t\t\tkd_rwsem_release_local(sem);'),
        'rollback-phase-leaked': mutate(names[6], '\tkd_rwsem_release_local(sem);',
            '\t(void)kd_rwsem_release_local;'),
        'rollback-before-unlock': mutate(names[6],
            '\tkd_mutex_local_unlock(&sem->gate);\nrelease_phase:',
            '\tkd_rwsem_release_local(sem);\n\tkd_mutex_local_unlock(&sem->gate);\nrelease_phase:'),
        'reader-drain-skipped': mutate(names[6], 'ret = kd_rwsem_drain_readers(sem, state);',
            'ret = false ? kd_rwsem_drain_readers(sem, state) : 0;'),
        'timeout-treated-as-success': mutate(names[1], '} while (!ret);', '} while (false && !ret);'),
        'internal-preparation-omitted': mutate(names[13],
            'BUG_ON(!READ_ONCE(sem->prepared_writes));',
            'BUG_ON(false && !READ_ONCE(sem->prepared_writes));'),
    }
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    with tempfile.TemporaryDirectory(prefix='kd-rwsem-writer-queue-') as directory:
        path = Path(directory)
        for name, body in [('production', code), *variants.items()]:
            (path / 'rwsem_writer_production.h').write_text(body)
            binary = path / name
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-O2', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-UNDEBUG',
                '-I', str(path), str(ROOT / 'tests/unit/mutex/rwsem_writer_queue_fixture.c'),
                '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=15)
            if name == 'production':
                assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
                assert 'PASS writer queue: 82 scenarios;' in result.stdout, result.stdout
                print(result.stdout, end='')
            else:
                assert result.returncode == -signal.SIGABRT, (name, result.returncode,
                    result.stdout, result.stderr)
                assert 'Assertion' in result.stderr, (name, result.stderr)
                print('writer queue mutation detected:', name)


if __name__ == '__main__':
    main()
