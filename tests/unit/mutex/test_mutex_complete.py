"""Guest-only composed COMPLETE retirement, with actual frame and caller code.

Only primitive peers, image lookup and wrapper execution are substitutes. This
is deterministic protocol evidence, not emitted-wrapper or Linux scheduling proof.
"""

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, read_source, without_includes
from test_spin_shadow import definition


def production():
    frame = read_source(ROOT / 'kernel_module/kd_exec.c')
    mutex = read_source(ROOT / 'kernel_module/kd_mutex.c')
    diag = read_source(ROOT / 'kernel_module/mutex/batch_diag.inc')
    types = definition(read_source(ROOT / 'include/kd_spin_entry.h'),
                       'struct kd_spin_ref {').rstrip() + ';\n'
    for name in ('exe_info', 'kd_call', 'kd_exec', 'kd_mutex_types', 'kd_mutex', 'kd_jit_batch'):
        types += without_includes(read_source(ROOT / f'include/{name}.h')) + '\n'
    types += '\n'.join(line for line in read_source(ROOT / 'include/exe.h').splitlines()
                       if line.startswith('#define KD_EXE_')) + '\n'
    types += '\n'.join(line for line in mutex.splitlines()
                       if line.startswith('#define KD_MUTEX_EXEC_')) + '\n'
    completion = [line for line in mutex.splitlines()
                  if line.startswith('#define KD_MUTEX_WAITER_PROCESSED ')]
    assert len(completion) == 1, 'expected the production completion marker'
    types += completion[0] + '\n'
    types += diag[diag.index('#define KD_MUTEX_DIAG_REASONS(X)'):
                  diag.index('#define KD_MUTEX_DIAG_TOTALS(X)')]
    types += '#define KD_MUTEX_DIAG_MEMBER struct kd_mutex_batch_diag diag;\n'
    for marker in ('enum kd_mutex_batch_result {', 'struct kd_mutex_batch {'):
        types += definition(mutex, marker).rstrip() + ';\n'

    frames = ''
    for marker in (
        'static int kd_exec_invariant_failure(void)',
        'static bool kd_exec_frame_state_is_active(int state)',
        'int kd_exec_frame_state(const struct kd_exec_frame *frame)',
        'static void kd_exec_frame_set_state(struct kd_exec_frame *frame, int state)',
        'bool kd_exec_frame_remote_pending(const struct kd_exec_frame *frame)',
        'bool kd_exec_frame_validate(const struct kd_exec_frame *frame)',
        'static bool kd_exec_context_validate(const struct kd_exec_context *ctx)',
        'static struct kd_exec_context *kd_exec_current_context(void)',
        'bool kd_exec_context_busy(void)',
        'struct kd_exec_frame *kd_exec_frame_push_mutex_batch(',
        'int kd_exec_frame_prepare_mutex_complex(struct kd_exec_frame *frame)',
        'kd_exec_frame_mutex_batch_valid(',
        'kd_exec_frame_mutex_batch_commit(',
        'int kd_exec_frame_retire_mutex_batch(struct kd_exec_frame *frame,',
        'int kd_exec_frame_pop(struct kd_exec_frame *frame, struct kd_regs *regs)',
    ):
        actual_marker = next(line for line in frame.splitlines() if line.startswith(marker)) if marker.startswith('kd_exec_frame_mutex_batch_') else marker
        part = definition(frame, actual_marker)
        if marker.startswith('kd_exec_frame_mutex_batch_valid('):
            part = 'static __always_inline bool\n' + part
        elif marker.startswith('kd_exec_frame_mutex_batch_commit('):
            part = 'static __always_inline int\n' + part
        # Context validation and the generic invariant reporter are SELFTEST
        # dependencies; retain their bodies without an unused-static warning.
        if marker in ('static int kd_exec_invariant_failure(void)',
                      'static void kd_exec_frame_set_state(struct kd_exec_frame *frame, int state)',
                      'static bool kd_exec_context_validate(const struct kd_exec_context *ctx)'):
            part = '#ifdef KDLOCK_SELFTEST\n' + part + '\n#endif'
        frames += part + '\n'

    # A fixture observer checks descriptor-before-frame ordering at the real
    # commit entry; it neither replaces nor supplies any production validation.
    assert frames.count('\tframe->jit_lock_released[0] = true;') == 1
    frames = frames.replace('\tframe->jit_lock_released[0] = true;',
                            '\tcomplete_commit_observe(ctx, frame);\n\tframe->jit_lock_released[0] = true;', 1)

    code = ''
    for marker in (
        'static bool kd_mutex_diag_condition(struct kd_mutex_batch_diag *diag,',
        'static void kd_mutex_diag_deferred(struct kd_mutex_batch_diag *diag,',
        'static void kd_mutex_diag_scan_end(struct kd_mutex_batch_diag *diag,',
        'static void kd_mutex_diag_request(struct kd_mutex_batch_diag *diag,',
        'static void kd_mutex_diag_result(struct kd_mutex_batch_diag *diag, int result)',
    ):
        code += definition(diag, marker) + '\n'
    code += diag[diag.index('#define KD_MUTEX_DIAG_CONDITION(batch, condition, reason)'):
                 diag.index('#else\n/* Discard diagnostic arguments')]
    for marker in (
        'bool kd_mutex_delegation_owned(struct kd_mutex *lock, struct task_struct *task)',
        'static __always_inline bool kd_mutex_proxy_request(struct kd_mutex *lock,',
        'static __always_inline void kd_mutex_proxy_assert_claimed(struct kd_mutex_node *node)',
        'kd_mutex_clear_locked_set_completed(struct kd_mutex_node *node)',
        'static __always_inline void kd_mutex_set_locked(struct kd_mutex *lock)',
    ):
        part = definition(mutex, marker)
        if marker.startswith('kd_mutex_clear_'):
            part = 'static __always_inline void\n' + part
        code += part + '\n'
    code += without_includes(read_source(ROOT / 'kernel_module/mutex/pin_window.inc')) + '\n'
    for marker in (
        'static bool kd_mutex_batch_epoch_begin(struct kd_mutex_batch *batch)',
        'static void kd_mutex_batch_epoch_end(struct kd_mutex_batch *batch, bool keep_current)',
        'static bool kd_mutex_batch_can_execute(struct kd_mutex_node *node)',
        'static __always_inline bool kd_mutex_batch_try_retire_current(struct kd_mutex *lock,',
        'static void kd_mutex_batch_retire_current(struct kd_mutex *lock,',
        'kd_mutex_batch_complete_inline(',
        'static void kd_mutex_prefetch_successor(struct kd_mutex_node *next)',
    ):
        actual_marker = next(line for line in mutex.splitlines() if line.startswith(marker)) if marker.startswith('kd_mutex_batch_complete_inline(') else marker
        part = definition(mutex, actual_marker)
        if marker.startswith('kd_mutex_batch_complete_inline('):
            part = '#ifndef KDLOCK_SELFTEST\nstatic __always_inline int\n' + part + '\n#endif'
        code += part + '\n'
    for name in ('kd_mutex_batch_select', 'kd_mutex_batch_rejoin', 'kd_mutex_batch_find_ready'):
        marker = next(line for line in mutex.splitlines() if line.startswith(name + '('))
        result = 'struct kd_exe_info *' if name.endswith('find_ready') else 'struct kd_mutex_node *'
        code += 'static ' + result + '\n' + definition(mutex, marker) + '\n'
    for name, result in (('kd_mutex_execute_cs', 'int'),
                         ('kd_mutex_run_combiner', 'enum kd_mutex_batch_result')):
        marker = next(line for line in mutex.splitlines() if line.startswith(name + '('))
        code += 'static ' + result + '\n' + definition(mutex, marker) + '\n'
    # Observe the ordinary-loop boundary without replacing retirement logic.
    assert code.count('\twhile (curr_node) {') == 1
    code = code.replace('\twhile (curr_node) {',
                        '\tnormal_loop = true;\n\twhile (curr_node) {', 1)
    assert code.count('\tif (completed_pending_tail) {') == 1
    code = code.replace('\tif (completed_pending_tail) {',
                        '\tnormal_loop = false;\n\tif (completed_pending_tail) {', 1)
    wrapper = definition(read_source(ROOT / 'kernel_module/exe.c'),
                         'bool kd_exe_mutex_batch_completed(const struct kd_jit_batch_call *call,')
    return types, frames, wrapper, code


def mutations(code):
    # Alter only the real joint body or its actual caller routing. Every mutant
    # must build and fail an explicit fixture assertion; a crash is not a pass.
    marker = 'kd_mutex_batch_complete_inline(struct kd_mutex *lock, struct kd_mutex_node *node,'
    joint = definition(code, marker)
    changes = {
        'missing-packet-pairing': ('frame->borrowed_regs != &node->regs ||', 'false ||'),
        'missing-regs-ref-check': ('batch->current_retired || frame->regs_ref ||', 'batch->current_retired || false ||'),
        'missing-hook-pairing': ('frame->outer_unlock_hook != &batch->outer ||', 'false ||'),
        'claimed-bypasses-ready': ('smp_load_acquire(&node->locked) != KD_MUTEX_PROXY_READY ||',
                                  '(smp_load_acquire(&node->locked) != KD_MUTEX_PROXY_READY && node->locked != KD_MUTEX_PROXY_CLAIMED) ||'),
        'lost-origin-reread': ('!kd_origin_mutex_owned(lock, current)', 'false'),
        'clear-before-frame-commit': ('retired = kd_mutex_batch_try_retire_current(lock, batch);',
                                     'retired = kd_mutex_batch_try_retire_current(lock, batch);\n\tbatch->pin.node = NULL; batch->nr_pins = 0;'),
        'wake-before-frame-commit': ('BUG_ON(kd_exec_frame_mutex_batch_commit(ctx, frame));',
                                    'kd_mutex_clear_locked_set_completed(node);\n\tBUG_ON(kd_exec_frame_mutex_batch_commit(ctx, frame));'),
        'hot-tail-poll': ('retired = kd_mutex_batch_try_retire_current(lock, batch);',
                         'retired = kd_mutex_batch_try_retire_current(lock, batch);\n\twhile (!retired) { cpu_relax(); retired = kd_mutex_batch_try_retire_current(lock, batch); }'),
        'lost-retired-count': ('KD_MUTEX_PIN_INC(batch, retired_claims);', '(void)batch;'),
        'post-wake-read': ('kd_mutex_clear_locked_set_completed(node);',
                          'kd_mutex_clear_locked_set_completed(node);\n\t(void)READ_ONCE(node->locked);'),
    }
    for name, (before, after) in changes.items():
        assert joint.count(before) == 1, (name, joint.count(before))
        yield name, code.replace(joint, joint.replace(before, after, 1), 1)
    caller_changes = {
        'published-diagnosed-refusal': ('exe_flag == KD_MUTEX_EXEC_COMPLETE_PENDING_TAIL ? 0 : exe_flag);',
                                       'exe_flag == KD_MUTEX_EXEC_COMPLETE_PENDING_TAIL ? exe_flag : exe_flag);'),
        'published-retired-twice': ('goto current_completed;',
                                  '{ if (false) goto current_completed; exe_flag = 0; }'),
        'pending-does-not-end-loop': ('if (exe_flag == KD_MUTEX_EXEC_COMPLETE_PENDING_TAIL) {',
                                     'if (false && exe_flag == KD_MUTEX_EXEC_COMPLETE_PENDING_TAIL) {'),
        'pending-drops-source': ('\tif (completed_pending_tail) {',
                                '\tif (completed_pending_tail) {\n\t\tkd_source_frame_put();'),
    }
    for name, (before, after) in caller_changes.items():
        assert code.count(before) == 1, (name, code.count(before))
        yield name, code.replace(before, after, 1)


def main():
    types, frames, wrapper, code = production()
    candidates = [('production', False, code), ('selftest', True, code)]
    candidates += [(name, False, candidate) for name, candidate in mutations(code)]
    with tempfile.TemporaryDirectory(prefix='kdlock-mutex-complete-unit-') as tmp:
        path = Path(tmp)
        (path / 'complete_types.h').write_text(types)
        (path / 'mutex_state_production.h').write_text(
            without_includes(read_source(ROOT / 'include/kd_mutex_state.h')))
        (path / 'complete_wrapper.h').write_text(wrapper)
        (path / 'complete_frame.h').write_text(frames)
        for name, selftest, candidate in candidates:
            (path / 'complete_mutex.h').write_text(candidate)
            binary = path / name
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                *(['-DKDLOCK_SELFTEST=1'] if selftest else []),
                '-I', str(path), str(ROOT / 'tests/unit/mutex/mutex_complete_fixture.c'),
                '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            if name in {'production', 'selftest'}:
                assert result.returncode == 0, (name, result.returncode, result.stdout, result.stderr)
                print(result.stdout, end='')
            else:
                assert result.returncode == 1 and 'FAIL complete case=' in result.stderr, (
                    name, result.returncode, result.stdout, result.stderr)
                print(f'complete mutation detected: {name}')


if __name__ == '__main__':
    main()
