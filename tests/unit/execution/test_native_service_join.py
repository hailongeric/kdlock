"""VM-only production Native registry, typed owner routing and terminal join.

Reuse the source-extraction fixture helpers. CPU/task/physical release primitives
are supplied; registry transactions, exact route consumers and continuation
retirement run their production code. This is not live kernel/JIT execution.
"""
import os
import resource
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, read_source, without_includes
from test_spin_shadow import definition


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    header = read_source(ROOT / 'include/kd_exec.h')
    continuation_header = read_source(ROOT / 'include/kd_exec_cont.h')
    wait_header = read_source(ROOT / 'include/kd_wait_queue.h')
    declarations = without_includes(read_source(ROOT / 'include/kd_regs.h'))
    for source, names in (
        (header, ('enum kd_exec_native_operation {', 'struct kd_exec_native_route {')),
        (continuation_header, ('enum kd_exec_cont_state {', 'enum kd_exec_cont_wait {')),
        (wait_header, ('enum kd_wait_state {',)),
    ):
        declarations += '\n'.join(definition(source, name).rstrip() + ';' for name in names)
    execution = read_source(ROOT / 'kernel_module/kd_exec.c')
    native = read_source(ROOT / 'kernel_module/execution/native.inc')
    continuation = read_source(ROOT / 'kernel_module/execution/continuation.inc')
    service = read_source(ROOT / 'kernel_module/kd_service.c')
    admission = read_source(ROOT / 'kernel_module/kd_admission.c')
    rwsem = read_source(ROOT / 'kernel_module/kd_rwsem.c')
    declarations += definition(execution, 'struct kd_native_request {').rstrip() + ';\n'
    code = '\n'.join(definition(source, name) for source, names in (
        (continuation, ('static bool kd_exec_cont_valid(const struct kd_exec_continuation *cont)',
                        'static bool kd_exec_cont_no_stack_service(const struct kd_exec_frame *frame)')),
        (admission, ('void kd_admission_read_to_native(struct kd_admission *a)',)),
        (service, ('static bool kd_service_native_match(const void *argument, unsigned long object,',
                   'static int kd_service_native_release(void *argument,',
                   'static bool kd_service_native_finished(const void *argument)')),
        (native, ('int kd_exec_native_service_begin(struct kd_exec_frame *frame)',
                  'static void kd_exec_native_service_request_wait(struct kd_native_request *request)',
                  'int kd_exec_native_accept(struct kd_exec_frame *frame)',
                  'bool kd_exec_native_service_active(struct task_struct *task)',
                  'bool kd_exec_native_service_owned(unsigned long object)',
                  'bool kd_exec_native_service_unlock(unsigned long object,',
                  'static int kd_exec_native_service_wait(struct kd_exec_frame *frame)')),
        (continuation, ('int kd_exec_cont_handoff(struct kd_exec_continuation *cont)',
                        'int kd_exec_cont_retire(struct kd_exec_continuation *cont)')),
        (rwsem, ('void kd_up_read(struct kd_rwsem *sem)',
                 'void kd_up_read_non_owner(struct kd_rwsem *sem)')),
    ) for name in names)
    with tempfile.TemporaryDirectory(prefix='kd-native-service-join-') as directory:
        path = Path(directory)
        (path / 'join_types.h').write_text(declarations)
        (path / 'join_production.h').write_text(code)
        binary = path / 'join'
        subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
            '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-UNDEBUG', '-pthread',
            '-I', str(path), str(ROOT / 'tests/unit/execution/native_service_join_fixture.c'),
            '-o', str(binary)], check=True, timeout=30)
        for mode in ('write', 'downgrade', 'read'):
            result = subprocess.run([str(binary), mode], capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, (mode, result.returncode, result.stdout, result.stderr)
            print(result.stdout, end='')


if __name__ == '__main__':
    main()
