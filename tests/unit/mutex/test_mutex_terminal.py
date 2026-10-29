"""Guest-only terminal mutex queue retirement with deterministic publishers.

Compile the real retirement helper and FIFO loop. JIT/body and KD owner
operations are substitutes; these controlled interleavings do not prove kernel
concurrency, native ACK scheduling, or hardware performance.
"""
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from source_text import ROOT, read_source, without_includes
from test_spin_shadow import definition


def production_sources():
    types = definition(read_source(ROOT/'include/kd_regs.h'), 'struct kd_regs {').rstrip()+';\n'
    types += definition(read_source(ROOT/'include/kd_spin_entry.h'), 'struct kd_spin_ref {').rstrip()+';\n'
    # Includes are stripped below, so retain the real physical-object header
    # explicitly before the queue/API declarations that depend on it.
    for name in ('exe_info', 'kd_call', 'kd_exec', 'kd_mutex_types', 'kd_mutex'):
        types += without_includes(read_source(ROOT/f'include/{name}.h'))+'\n'
    source = read_source(ROOT/'kernel_module/kd_mutex.c')
    helpers = '#define MODULE_INFO(...)\n'
    helpers += without_includes(read_source(ROOT/'kernel_module/mutex/pin_origin.inc'))+'\n'
    helpers += next(line for line in source.splitlines() if line.startswith('#define KD_MUTEX_EXEC_SWAPPED '))+'\n'
    helpers += without_includes(read_source(ROOT/'kernel_module/mutex/batch_diag.inc'))+'\n'
    helpers += definition(source, 'enum kd_mutex_batch_result {').rstrip()+';\n'
    helpers += definition(source, 'struct kd_mutex_batch {').rstrip()+';\n'
    for marker in ('static __always_inline bool kd_mutex_proxy_request(struct kd_mutex *lock,',
                   'static __always_inline void kd_mutex_proxy_assert_claimed(struct kd_mutex_node *node)'):
        helpers += definition(source, marker)+'\n'
    helpers += without_includes(read_source(ROOT/'kernel_module/mutex/pin_window.inc'))+'\n'
    for marker in ("static bool kd_mutex_batch_epoch_begin(struct kd_mutex_batch *batch)",
                   "static void kd_mutex_batch_epoch_end(struct kd_mutex_batch *batch, bool keep_current)"):
        helpers += definition(source, marker) + "\n"
    for name in ('kd_mutex_batch_select', 'kd_mutex_batch_rejoin'):
        marker = next(line for line in source.splitlines() if line.startswith(name+'('))
        helpers += 'static struct kd_mutex_node *\n' + definition(source, marker)+'\n'
    for marker in (
        'static bool kd_mutex_batch_can_execute(struct kd_mutex_node *node)',
        'static bool kd_mutex_batch_try_retire_current(struct kd_mutex *lock,',
        'static void kd_mutex_batch_retire_current(struct kd_mutex *lock,',
    ):
        helpers += definition(source, marker)+'\n'
    helpers += definition(source, 'static int kd_mutex_release_outer(struct kd_exec_frame *frame,')+'\n'
    marker = next(line for line in source.splitlines() if line.startswith('kd_mutex_run_combiner('))
    loop = 'static enum kd_mutex_batch_result\n' + definition(source, marker)
    # Test-only phase observation leaves the actual body/retirement code intact.
    # A delayed publication must poll only after the normal execution loop ends.
    loop = loop.replace("\twhile (curr_node) {", "\tnormal_proxy_loop = true;\n\twhile (curr_node) {", 1)
    loop = loop.replace("\tif (completed_pending_tail) {", "\tnormal_proxy_loop = false;\n\tif (completed_pending_tail) {", 1)
    return types, helpers, loop


def main():
    types, helpers, loop = production_sources()
    with tempfile.TemporaryDirectory(prefix='kd-mutex-terminal-') as tmp:
        path=Path(tmp)
        (path/'types.h').write_text(types)
        (path/'mutex_state_production.h').write_text(
            without_includes(read_source(ROOT/'include/kd_mutex_state.h')))
        assert loop.count('kd_mutex_set_locked(lock);') == 1
        assert helpers.count('kd_mutex_set_locked(batch->lock);') == 1
        mutations = {
            'production': (helpers, loop),
            'poll-inside-normal-loop': (helpers, loop.replace(
                'if (!kd_mutex_batch_try_retire_current(lock, &batch)) {',
                'if ((kd_mutex_batch_retire_current(lock, &batch), !kd_mutex_batch_try_retire_current(lock, &batch))) {', 1)),
            'withdraw-pending-current': (helpers, loop.replace(
                '\tif (completed_pending_tail) {',
                '\tif (completed_pending_tail) {\n\t\tsmp_store_release(&curr_node->locked, KD_MUTEX_WAIT);', 1)),
            'wake-before-cold-retirement': (helpers, loop.replace(
                '\tif (completed_pending_tail) {',
                '\tif (completed_pending_tail) {\n\t\tkd_mutex_clear_locked_set_completed(curr_node);', 1)),
            'cold-body-skips-fresh-admission': (helpers, loop.replace(
                'if (!batch.proxy_epoch && !kd_mutex_batch_epoch_begin(&batch)) {',
                'if (false && !batch.proxy_epoch && !kd_mutex_batch_epoch_begin(&batch)) {', 1)),
            'ignore-local-pin-budget': (helpers.replace('if (left > local_left)', 'if (false && left > local_left)'), loop),
            'underflow-late-local-budget': (helpers.replace('counter >= KDLOCK_MUTEX_NUMA_BOUNDARY ?', 'false ?'), loop),
            'skip-tail-retirement': (helpers.replace('if (batch->current_retired)', 'if (true)'), loop),
            'skip-delayed-link': (helpers.replace('} while (!next);', '} while (false);'), loop),
            'repeat-after-native-reuse': (helpers.replace('if (batch->current_retired)', 'if (false)'), loop),
            'skip-deferred-rejoin': (helpers.replace('if (batch->deferred_head) {', 'if (false) {'), loop),
            'lose-refused-successor': (helpers, loop.replace('WRITE_ONCE(curr_node->next, next_node);', '')),
            'unbounded-local-cohort': (helpers, loop.replace('counter >= KDLOCK_MUTEX_NUMA_BOUNDARY', 'false')),
            'short-local-cohort': (helpers, loop.replace('counter >= KDLOCK_MUTEX_NUMA_BOUNDARY', 'counter >= 128')),
            'late-local-cohort': (helpers, loop.replace('counter >= KDLOCK_MUTEX_NUMA_BOUNDARY', 'counter >= 512')),
            'skip-numa-owner-handoff': (helpers, loop.replace('if (batch.deferred_count >= 8)', 'if (false)')),
            'bypass-rejoined-prefix': (helpers, loop.replace('batch.numa_node = -1;', 'batch.numa_node = 0;')),
            'overrun-total-batch': (helpers, loop.replace(
                'counter >= kd_mutex_batch_size', 'counter >= kd_mutex_batch_size + 1')),
            # Every return preserves the physical owner's HELD phase. Before epoch
            # admission the refusal assignment is idempotent; test an illicit
            # FREE transition, rather than require that redundant write.
            'refusal-opens-gate': (helpers, loop.replace('kd_mutex_set_locked(lock);', 'kd_mutex_gate_set(lock, KD_MUTEX_GATE_FREE);', 1)),
            'skip-normal-gate': (helpers.replace('kd_mutex_set_locked(batch->lock);', ''), loop),
        }
        for name, (text, candidate_loop) in mutations.items():
            (path/'helpers.h').write_text(text)
            (path/'loop.h').write_text(candidate_loop)
            binary=path/name
            subprocess.run(shlex.split(os.environ.get('CC','cc'))+[
                '-std=gnu11','-O2','-Wall','-Wextra','-Werror','-I'+str(path),
                # Preserve the original interleaving/mutation scenarios at
                # their explicit historical boundary; policy tests cover defaults.
                '-DKDLOCK_MUTEX_NUMA_BOUNDARY=256',
                str(ROOT/'tests/unit/mutex/mutex_terminal_fixture.c'),'-o',str(binary)],
                check=True,timeout=30)
            result=subprocess.run([str(binary)],text=True,capture_output=True,timeout=10)
            if name=='production':
                assert result.returncode==0,(result.stdout,result.stderr)
                print(result.stdout,end='')
            else:
                assert result.returncode==1 and 'FAIL terminal' in result.stderr,(name,result.returncode,result.stdout,result.stderr)
                print('terminal mutation detected:',name)


if __name__=='__main__':
    main()
