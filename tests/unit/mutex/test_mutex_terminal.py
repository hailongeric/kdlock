"""Guest-only terminal mutex queue retirement with deterministic publishers.

Compile the real retirement helper and FIFO loop. JIT/body and Linux owner
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


def main():
    types = definition(read_source(ROOT/'include/kd_regs.h'), 'struct kd_regs {').rstrip()+';\n'
    types += definition(read_source(ROOT/'include/kd_spin_entry.h'), 'struct kd_spin_ref {').rstrip()+';\n'
    for name in ('exe_info', 'kd_call', 'kd_exec', 'kd_mutex'):
        types += without_includes(read_source(ROOT/f'include/{name}.h'))+'\n'
    source = read_source(ROOT/'kernel_module/kd_mutex.c')
    helpers = definition(source, 'struct kd_mutex_batch {').rstrip()+';\n'
    for name in ('kd_mutex_batch_select', 'kd_mutex_batch_rejoin'):
        marker = next(line for line in source.splitlines() if line.startswith(name+'('))
        helpers += 'static struct kd_mutex_node *\n' + definition(source, marker)+'\n'
    for marker in (
        'static bool kd_mutex_batch_can_execute(struct kd_mutex_node *node)',
        'static void kd_mutex_batch_retire_current(struct kd_mutex *lock,',
    ):
        helpers += definition(source, marker)+'\n'
    helpers += definition(source, 'static int kd_mutex_release_outer(struct kd_exec_frame *frame,')+'\n'
    loop = 'static void\n'+definition(source, 'kd_mutex_run_combiner(struct kd_mutex *lock, struct kd_mutex_node *curr_node)')
    with tempfile.TemporaryDirectory(prefix='kd-mutex-terminal-') as tmp:
        path=Path(tmp)
        (path/'types.h').write_text(types)
        (path/'mutex_state_production.h').write_text(
            without_includes(read_source(ROOT/'include/kd_mutex_state.h')))
        assert loop.count('kd_mutex_set_locked(lock);') == 2
        mutations = {
            'production': (helpers, loop),
            'skip-tail-retirement': (helpers.replace('if (batch->current_retired)', 'if (true)'), loop),
            'skip-delayed-link': (helpers.replace('} while (!next);', '} while (false);'), loop),
            'repeat-after-native-reuse': (helpers.replace('if (batch->current_retired)', 'if (false)'), loop),
            'skip-deferred-rejoin': (helpers.replace('if (batch->deferred_head) {', 'if (false) {'), loop),
            'lose-refused-successor': (helpers, loop.replace('WRITE_ONCE(curr_node->next, next_node);', '')),
            'unbounded-local-cohort': (helpers, loop.replace('counter >= 128', 'false')),
            # Each combiner return must establish the normal gate value
            # independently, including source refusal before caller cleanup.
            'skip-refusal-gate': (helpers, loop.replace('kd_mutex_set_locked(lock);', '', 1)),
            'skip-normal-gate': (helpers, ''.join(loop.rsplit('kd_mutex_set_locked(lock);', 1))),
        }
        for name, (text, candidate_loop) in mutations.items():
            (path/'helpers.h').write_text(text)
            (path/'loop.h').write_text(candidate_loop)
            binary=path/name
            subprocess.run(shlex.split(os.environ.get('CC','cc'))+[
                '-std=gnu11','-O2','-Wall','-Wextra','-Werror','-I'+str(path),
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
