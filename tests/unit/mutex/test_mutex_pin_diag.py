"""Guest-only optional pin observations with actual queue/selection helpers.

Deterministic peers substitute ACKs and body execution. Compilation, assertions,
mutations and schema checks run only in the VM; enabled timings are unscored.
"""
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from source_text import ROOT, read_source, without_includes
from test_mutex_terminal import production_sources
from test_mutex_batch_diag import MOCKS


def main():
    types, helpers, loop = production_sources()
    fixture = (ROOT / 'tests/unit/mutex/mutex_terminal_fixture.c').read_text()
    mocks = MOCKS.replace('#define KDLOCK_MUTEX_DIAGNOSTICS 1',
                          '#define KDLOCK_MUTEX_DIAGNOSTICS 2')
    mocks = mocks[:mocks.index('static unsigned int fls')]
    mocks += r'''
#define __percpu
static int diag_module;
#define THIS_MODULE (&diag_module)
static bool diag_params_locked,diag_fail_alloc;
static unsigned int diag_alloc_attempts,diag_allocations,diag_frees;
static unsigned int diag_param_locks,diag_param_unlocks,diag_cpu_accesses;
static void *diag_live_storage;
static size_t diag_storage_bytes;
static void kernel_param_lock(void *module)
{
    CHECK(module==THIS_MODULE && !diag_params_locked);
    diag_params_locked=true;diag_param_locks++;
}
static void kernel_param_unlock(void *module)
{
    CHECK(module==THIS_MODULE && diag_params_locked);
    diag_params_locked=false;diag_param_unlocks++;
}
static void *diag_alloc_percpu(size_t bytes)
{
    CHECK(!diag_live_storage && !diag_params_locked);
    diag_alloc_attempts++;
    if(diag_fail_alloc)return NULL;
    diag_live_storage=calloc(1,bytes);CHECK(diag_live_storage);
    /* Production initialization must clear every byte, including optional
     * sample state; do not let the allocator hide a missing initialization. */
    memset(diag_live_storage,0xa5,bytes);diag_storage_bytes=bytes;
    diag_allocations++;
    return diag_live_storage;
}
static void *diag_cpu_ptr(void *storage,int cpu)
{
    CHECK(cpu==0 && storage && storage==diag_live_storage);
    diag_cpu_accesses++;
    return storage;
}
static void __attribute__((unused)) diag_free_percpu(void *storage);
#define alloc_percpu(type) ((type *)diag_alloc_percpu(sizeof(type)))
#define free_percpu(storage) diag_free_percpu(storage)
#define per_cpu_ptr(storage,cpu) ((__typeof__(storage))diag_cpu_ptr((storage),(cpu)))
#undef WRITE_ONCE
#define WRITE_ONCE(field,value) ({ \
    __auto_type diag_target=&(field); \
    if((void *)diag_target==(void *)&kd_mutex_pin_cpus)CHECK(diag_params_locked); \
    *diag_target=(value); \
})
#define this_cpu_inc_return(name) (++(name))
#if KDLOCK_MUTEX_PIN_TSC_SHIFT
static u64 stamp_ticks;
static u64 rdtsc_ordered(void) { stamp_ticks+=7;return stamp_ticks; }
#endif
'''
    fixture = fixture.replace('#include "helpers.h"', mocks + '\n#include "helpers.h"\n'
        '#define PIN_DIAG_FIXTURE_HELPERS\n#include "mutex_pin_diag_fixture.inc"\n'
        '#undef PIN_DIAG_FIXTURE_HELPERS')
    fixture = fixture.replace('int main(void)\n{', 'int main(void)\n{\n'
        '#define PIN_DIAG_FIXTURE_SETUP\n#include "mutex_pin_diag_fixture.inc"\n'
        '#undef PIN_DIAG_FIXTURE_SETUP')
    fixture = fixture.replace('static void cpu_relax(void)\n{',
        'static struct kd_mutex_node *diag_ack_node;\nstatic unsigned int diag_ack_polls;\n'
        'static void cpu_relax(void)\n{\n'
        '    if(diag_ack_node) { if(++diag_ack_polls==3) { '
        'diag_ack_node->locked=KD_MUTEX_PROXY_PINNED;diag_ack_node=NULL; }return; }')
    fixture = fixture.replace('    kd_mutex_proxy_wait_pinned(node);',
                              '    KD_MUTEX_PIN_WAIT(batch,node,false);')
    extra = (ROOT / 'tests/unit/mutex/mutex_pin_diag_fixture.inc').read_text()
    fixture = fixture.replace('    printf("PASS terminal queue:', extra + '\n    printf("PASS terminal queue:')
    assert fixture.count('PINMAX %s') == 1
    with tempfile.TemporaryDirectory(prefix='kd-mutex-pin-diag-') as directory:
        path = Path(directory)
        (path / 'types.h').write_text(types)
        (path / 'mutex_state_production.h').write_text(
            without_includes(read_source(ROOT / 'include/kd_mutex_state.h')))
        (path / 'loop.h').write_text(loop)
        (path / 'fixture.c').write_text(fixture)
        command = shlex.split(os.environ.get('CC', 'cc')) + [
            '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
            '-DKDLOCK_MUTEX_NUMA_BOUNDARY=256', '-I' + directory,
            '-I' + str(ROOT / 'tests/unit/mutex')]
        for shift in (0, 6):
            candidates = {
                'production': helpers,
                'lost-request': helpers.replace('KD_MUTEX_PIN_INC(batch, requested);', '', 1),
                'lost-consumed': helpers.replace('KD_MUTEX_PIN_INC(batch, consumed);', '', 1),
                'lost-cancelled': helpers.replace('KD_MUTEX_PIN_INC(batch, cancelled);', '', 1),
                'lost-occupancy': helpers.replace('(batch)->diag.occupancy_after[(batch)->nr_pins]++;', '', 1),
                'lost-ack-loops': helpers.replace('\t\tloops++;', '\t\tloops += 0;', 1),
                'uninitialized-storage': helpers.replace(
                    'memset(per_cpu_ptr(storage, cpu), 0, sizeof(*storage));', '(void)cpu;', 1),
                'unlocked-publication': helpers.replace('kernel_param_lock(THIS_MODULE);', '', 1),
                'attached-storage-free': helpers.replace('WRITE_ONCE(kd_mutex_pin_cpus, NULL);', '', 1),
                'storage-leak': helpers.replace('free_percpu(storage);', '(void)storage;', 1),
            }
            for name, candidate in candidates.items():
                assert name == 'production' or candidate != helpers, name
                (path / 'helpers.h').write_text(candidate)
                binary = path / f'{name}-{shift}'
                subprocess.run(command + [f'-DKDLOCK_MUTEX_PIN_TSC_SHIFT={shift}',
                    str(path / 'fixture.c'), '-o', str(binary)], check=True, timeout=30)
                result = subprocess.run([binary], capture_output=True, text=True, timeout=10)
                if name != 'production':
                    assert result.returncode == 1 and 'FAIL terminal' in result.stderr, (name, result)
                    print('pin diagnostic mutation detected:', name, shift)
                    continue
                assert result.returncode == 0, result
                values = {line.split(' ', 1)[0]: json.loads(line.split(' ', 1)[1])
                          for line in result.stdout.splitlines()
                          if line.startswith(('PIN ', 'PINMAX ', 'PINRESET '))}
                sample = values['PIN']
                assert sample['schema'] == 1 and sample['compiled'] == 2
                assert sample['window'] == 4 and sample['tsc_sample_shift'] == shift
                assert sample['total_cap'] == 1024 and sample['numa_boundary'] == 256
                assert sample['selections'] == sum(sample['occupancy_before']) == sum(sample['occupancy_after'])
                assert sample['selections'] == sum(sample['refill_stop'].values())
                assert sample['requested'] == sample['consumed'] + sample['cancelled']
                maximum = (1 << 64) - 1
                assert values['PINMAX']['tsc_cycles'] == maximum
                assert values['PINMAX']['occupancy_after'] == [maximum] * 5
                assert all(value == maximum for value in values['PINMAX']['refill_stop'].values())
                reset = values['PINRESET']
                metadata = ('schema', 'compiled', 'window', 'total_cap', 'numa_boundary', 'tsc_sample_shift')
                assert all(reset[key] == sample[key] for key in metadata)
                for key, value in reset.items():
                    if key not in metadata:
                        assert (all(item == 0 for item in value.values()) if isinstance(value, dict) else
                                all(item == 0 for item in value) if isinstance(value, list) else value == 0), key
                assert 'PASS pin diagnostic allocation lifecycle' in result.stdout
                print(f'pin diagnostics shift={shift}: {sample["selections"]} selection receipts; '
                      'allocation failure/reinitialization, bounded JSON and ACK accounting')


if __name__ == '__main__':
    main()
