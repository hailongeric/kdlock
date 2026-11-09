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
    declarations += without_includes(read_source(ROOT / 'include/exe_info.h'))
    declarations += '\n'.join(line for line in read_source(ROOT / 'include/exe.h').splitlines()
                              if line.startswith('#define KD_EXE_')) + '\n'
    declarations += '#include "kd_learning_api.h"\n'
    declarations += '\n'.join(line for line in read_source(ROOT / 'include/kd_jit_batch.h').splitlines()
                              if line.startswith('#define KD_JIT_ABI_OFFSET ')) + '\n'
    declarations += definition(read_source(ROOT / 'include/kd_image.h'),
                               'struct kd_jit_image {').rstrip() + ';\n'
    for name in ('struct kd_image_learning_receipt {', 'struct kd_image_learning_state {'):
        declarations += definition(read_source(ROOT / 'include/kd_image.h'), name).rstrip() + ';\n'
    declarations += 'static struct kd_image_learning_state kd_image_learning[KD_MAX_EXE];\n'
    declarations += 'static unsigned long kd_image_report_superseded;\n'
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
        (read_source(ROOT / 'kernel_module/execution/wrapper_entry.inc'),
            ('static int kd_jit_source_frontier(struct kd_exe_info *exe,',)),
        (continuation, ('static bool kd_exec_cont_valid(const struct kd_exec_continuation *cont)',
                        'static bool kd_exec_cont_no_stack_service(const struct kd_exec_frame *frame)')),
        (admission, ('void kd_admission_read_to_native(struct kd_admission *a)',)),
        (read_source(ROOT / 'kernel_module/execution/images.inc'),
            ('unsigned int kd_exe_slot_index(const struct kd_exe_info *entry)',
             'static bool kd_image_miss_kind(unsigned int kind)',
             'static bool kd_image_miss_matches(const struct kd_learning_record *record,',
             'static void kd_image_pending_tuple(struct kd_exe_info *entry,',
             'static bool kd_image_miss_acknowledged(const struct kd_learning_record *record,',
             'static bool kd_image_batch_has_survivors(const struct kd_image_learning_state *learning,',
             'static void kd_image_ack_misses(struct kd_image_learning_state *learning,',
             'int kd_image_publish_learned(struct kd_exe_info *entry, struct kd_jit_image *image,',
             'int kd_image_publish(struct kd_exe_info *entry, struct kd_jit_image *image,',
             'void kd_image_report(struct kd_exe_info *entry, const struct kd_jit_image *image,')),
        (read_source(ROOT / 'kernel_module/exe.c'),
            ('const struct kd_jit_image *kd_exe_capture_image(struct kd_exe_info *exe,',)),
        (service, ('static bool kd_service_native_match(const void *argument, unsigned long object,',
                   'static int kd_service_native_release(void *argument,',
                   'static bool kd_service_native_finished(const void *argument)',
                   'static int kd_service_release_boundary(struct kd_service_root *root, int status)')),
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
            '-I', str(path), '-I', str(ROOT / 'include'),
            str(ROOT / 'tests/unit/execution/native_service_join_fixture.c'),
            '-o', str(binary)], check=True, timeout=30)
        for mode in ('write', 'downgrade', 'read', 'release'):
            result = subprocess.run([str(binary), mode], capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, (mode, result.returncode, result.stdout, result.stderr)
            print(result.stdout, end='')


if __name__ == '__main__':
    main()
