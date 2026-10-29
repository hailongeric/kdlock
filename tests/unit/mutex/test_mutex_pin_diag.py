"""Guest-only optional pin observations with actual queue/selection helpers.

Deterministic peers substitute body execution and origin scheduling. Compilation,
assertions, mutations and schema checks run only in the VM; enabled timings are
unscored.
"""
import json
import os
import re
from pathlib import Path
import shlex
import subprocess
import tempfile

from source_text import ROOT, read_source, without_includes
from test_mutex_terminal import production_sources
from test_mutex_batch_diag import MOCKS
from test_spin_shadow import definition


def main():
    types, helpers, loop = production_sources()
    fixture = (ROOT / 'tests/unit/mutex/mutex_terminal_fixture.c').read_text()
    # The terminal body substitute does not inspect entry IP. READY candidate
    # observations require a concrete nonzero same-entry prefix.
    node_init = 'nodes[i].counted_lock=&lock;nodes[i].count_seq=2;'
    assert fixture.count(node_init) == 1
    fixture = fixture.replace(node_init, node_init + 'nodes[i].regs.ip=0xcafe;')
    mocks = MOCKS.replace('#define KDLOCK_MUTEX_DIAGNOSTICS 1',
                          '#define KDLOCK_MUTEX_DIAGNOSTICS 2')
    mocks = mocks[:mocks.index('static unsigned int fls')]
    mocks += r'''
#define __percpu
static u64 *diag_generation_target;
static unsigned int diag_generation_reads;
#undef READ_ONCE
#define READ_ONCE(field) ({ \
    __auto_type diag_address=&(field); \
    if((void *)diag_address==(void *)diag_generation_target && ++diag_generation_reads==2) \
        *diag_generation_target+=2; \
    __atomic_load_n(diag_address,__ATOMIC_RELAXED); \
})
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
    /* Production initialization must clear every byte, including padding;
     * do not let the allocator hide a missing initialization. */
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
'''
    fixture = fixture.replace('#include "helpers.h"', mocks + '\n#include "helpers.h"\n'
        '#define PIN_DIAG_FIXTURE_HELPERS\n#include "mutex_pin_diag_fixture.inc"\n'
        '#undef PIN_DIAG_FIXTURE_HELPERS')
    fixture = fixture.replace('int main(void)\n{', 'int main(void)\n{\n'
        '#define PIN_DIAG_FIXTURE_SETUP\n#include "mutex_pin_diag_fixture.inc"\n'
        '#undef PIN_DIAG_FIXTURE_SETUP')
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
        candidates = {
            'production': helpers,
            'lost-claim': helpers.replace('KD_MUTEX_PIN_INC(batch, claims);', '', 1),
            'lost-retirement': helpers.replace('KD_MUTEX_PIN_INC(batch, retired_claims);', '', 1),
            'lost-cancellation': helpers.replace('KD_MUTEX_PIN_INC(batch, cancelled_claims);', '', 1),
            'lost-occupancy': helpers.replace('(batch)->diag.occupancy_after[(batch)->nr_pins]++;', '', 1),
            'lost-epoch-attempt': helpers.replace('(batch)->diag.epoch_admission_attempts++;', '', 1),
            'lost-ready-observation': helpers.replace('diag->epoch_ready_candidates[count]++;', '(void)diag;', 1),
            'missing-ready-generation-recheck': helpers.replace('READ_ONCE(node->count_seq) != generation ||', 'false ||', 1),
            'duplicate-ready-cpu': helpers.replace('i != count || READ_ONCE(node->count_seq)', 'false || READ_ONCE(node->count_seq)', 1),
            'lost-epoch-refusal': helpers.replace('(batch)->diag.epoch_admission_refusals += !(accepted);', '', 1),
            'lost-expiry-checks': helpers.replace(
                'this_cpu_add(kd_mutex_pin_totals.expiry_checks, origin->expiry_checks);', '', 1),
            'retained-is-within-budget': helpers.replace('retained && !origin->budget_expired', 'retained', 1),
            'uninitialized-storage': helpers.replace(
                'memset(per_cpu_ptr(storage, cpu), 0, sizeof(*storage));', '(void)cpu;', 1),
            'unlocked-publication': helpers.replace('kernel_param_lock(THIS_MODULE);', '', 1),
            'attached-storage-free': helpers.replace('WRITE_ONCE(kd_mutex_pin_cpus, NULL);', '', 1),
            'storage-leak': helpers.replace('free_percpu(storage);', '(void)storage;', 1),
        }
        for name, candidate in candidates.items():
            assert name == 'production' or candidate != helpers, name
            (path / 'helpers.h').write_text(candidate)
            binary = path / name
            subprocess.run(command + [str(path / 'fixture.c'), '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([binary], capture_output=True, text=True, timeout=10)
            if name != 'production':
                assert result.returncode == 1 and 'FAIL terminal' in result.stderr, (name, result)
                print('pin diagnostic mutation detected:', name)
                continue
            assert result.returncode == 0, result
            values = {line.split(' ', 1)[0]: json.loads(line.split(' ', 1)[1])
                      for line in result.stdout.splitlines()
                      if line.startswith(('PIN ', 'PINMAX ', 'PINRESET '))}
            sample = values['PIN']
            assert sample['schema'] == 4 and sample['compiled'] == 2
            assert sample['claim_slots'] == 1 and sample['ready_policy'] == 'epoch' and sample['initial_spin_budget'] == 65536
            assert sample['total_cap'] == 1024 and sample['numa_boundary'] == 256
            assert sample['selections'] == sum(sample['occupancy_before']) == sum(sample['occupancy_after'])
            assert sample['selections'] == sum(sample['selection_result'].values())
            assert sample['claims'] == sample['retired_claims'] + sample['cancelled_claims']
            assert sample['claims'] == sample['occupancy_after'][1] == sample['selection_result']['claimed']
            assert sum(sample['epoch_ready_candidates']) == sample['epoch_admission_attempts'] - sample['epoch_admission_refusals']
            assert sample['wait_episodes'] == sample['initial_pin_retained'] + sample['initial_pin_dropped'] == 4
            assert sample['initial_budget_completed'] == 1 and sample['initial_pin_retained'] == 2
            assert not any('ack' in key or 'tsc' in key or key == 'requested' for key in sample)
            maximum = (1 << 64) - 1
            assert values['PINMAX']['expiry_checks'] == maximum
            assert values['PINMAX']['occupancy_after'] == [maximum] * 2
            assert values['PINMAX']['epoch_ready_candidates'] == [maximum] * 9
            assert all(value == maximum for value in values['PINMAX']['selection_result'].values())
            reset = values['PINRESET']
            metadata = ('schema', 'compiled', 'claim_slots', 'ready_policy', 'total_cap', 'numa_boundary', 'initial_spin_budget')
            assert all(reset[key] == sample[key] for key in metadata)
            for key, value in reset.items():
                if key not in metadata:
                    assert (all(item == 0 for item in value.values()) if isinstance(value, dict) else
                            all(item == 0 for item in value) if isinstance(value, list) else value == 0), key
            assert 'PASS pin diagnostic allocation lifecycle' in result.stdout
            print(f'READY pin diagnostics: {sample["selections"]} selection receipts; '
                  'allocation failure/reinitialization, bounded JSON and initial-spin accounting')
        (path / 'helpers.h').write_text(helpers)
        retired = subprocess.run(command + ['-DKDLOCK_MUTEX_PIN_TSC_SHIFT=6', '-fsyntax-only',
            str(path / 'fixture.c')], capture_output=True, text=True, timeout=30)
        assert retired.returncode != 0 and 'mutex pin TSC sampling is retired' in retired.stderr, retired
        print('PASS READY diagnostics reject retired ACK TSC sampling')
    check_origin_hooks()


def check_origin_hooks():
    """Observe-only wait entry plus actual local accumulator/merge implementation."""
    source = read_source(ROOT / 'kernel_module/kd_mutex.c')
    diag = read_source(ROOT / 'kernel_module/mutex/pin_diag.inc')
    origin = without_includes(read_source(ROOT / 'kernel_module/mutex/pin_origin.inc'))
    constants = '\n'.join(re.findall(
        r'^#define KD_MUTEX_(?:WAIT|PROXY_READY|PROXY_CLAIMED|QUEUE_INIT) \d+$',
        (ROOT / 'include/kd_mutex.h').read_text(), re.M))
    constants += '\n' + '\n'.join(line for line in (ROOT / 'include/kd_mutex.h').read_text().splitlines()
                                     if line.startswith('#define KD_MUTEX_GATE_'))
    state = without_includes(read_source(ROOT / 'include/kd_mutex_state.h'))
    declarations = diag[diag.index('#define KD_MUTEX_PIN_REASONS'):diag.index('static int kd_mutex_pin_diag_init')]
    merge = definition(diag, 'static void kd_mutex_pin_origin_finish(const struct kd_mutex_pin_origin *origin,')
    code = constants + r'''
#define KDLOCK_MUTEX_DIAGNOSTICS 2
#define KD_MUTEX_CLAIM_SLOTS 1
#define __percpu
#define this_cpu_add(name,value) do { CHECK(pins==1); (name)+=(value); } while(0)
#define this_cpu_inc(name) do { CHECK(pins==1); (name)++; } while(0)
''' + state + '\n' + origin + '\n' + declarations + '\n' + merge + '\n'
    code += '\n'.join(definition(source, signature) for signature in (
        'static __always_inline void kd_mutex_wait_for_result(struct kd_mutex_node *node)',
        'static __always_inline bool kd_mutex_proxy_request(struct kd_mutex *lock,',
        'static __always_inline void kd_mutex_proxy_assert_claimed(struct kd_mutex_node *node)',
        'static void kd_mutex_wait_and_lock_node(struct kd_mutex *lock,',
    ))
    fixture = (ROOT / 'tests/unit/mutex/mutex_proxy_pin_fixture.c').read_text()
    fixture = fixture.replace('#include <stdlib.h>', '#include <stdlib.h>\n#include <string.h>')
    main_entry = 'int main(void)\n{'
    assert fixture.count(main_entry) == 1
    fixture = fixture.replace(main_entry, main_entry + '\n'
        ' static struct kd_mutex_pin_cpu origin_storage;kd_mutex_pin_cpus=&origin_storage;')
    anchor = 'reset(selected);node.locked=initial;kd_mutex_wait_for_result(&node);'
    assert fixture.count(anchor) == 1
    fixture = fixture.replace(anchor, 'memset(&kd_mutex_pin_totals,0,sizeof(kd_mutex_pin_totals));\n ' + anchor + r'''
 bool dropped=selected==EXPIRE || selected==CANCEL || selected==CANCEL_AT_ENTRY || selected==WAKE_AT_UNPIN || selected==RELEASE_RACE;
 bool expired=selected==EXPIRE || selected==CLAIM_RACE || selected==WAKE_RACE || selected==WAKE_AT_UNPIN || selected==NO_RESCHED || selected==RELEASE_RACE || selected==STALE_READY || selected==READY_EPOCH;
 /* Publication belongs to the queue caller, never this result-wait entry. */
 CHECK(!publish_attempts && !publications);
 CHECK(kd_mutex_pin_totals.wait_episodes==1);
 if(selected==DONE_AT_ENTRY) {
  CHECK(!pauses && !need_checks && !unpin_calls);
  CHECK(kd_mutex_pin_totals.initial_pin_retained==1 && kd_mutex_pin_totals.initial_budget_completed==1);
 }
 CHECK(kd_mutex_pin_totals.initial_pin_retained==!dropped && kd_mutex_pin_totals.initial_pin_dropped==dropped);
 CHECK(kd_mutex_pin_totals.initial_budget_completed==(!dropped && !expired));
 CHECK(kd_mutex_pin_totals.budget_expired_episodes==expired);
 CHECK(kd_mutex_pin_totals.expiry_checks==((selected==NO_RESCHED || selected==READY_EPOCH)?3U:expired?1U:0U));
 CHECK(kd_mutex_pin_totals.withdrawals==(selected==EXPIRE || selected==WAKE_AT_UNPIN || selected==RELEASE_RACE));
 CHECK(kd_mutex_pin_totals.forced_cancellations==(selected==CANCEL || selected==CANCEL_AT_ENTRY));
 CHECK(kd_mutex_pin_totals.withdrawal_reservations==(selected==EXPIRE || selected==WAKE_RACE ||
       selected==WAKE_AT_UNPIN || selected==RELEASE_RACE || selected==STALE_READY));
''')
    mutations = {
        'production': code,
        'missing-episode-finish': code.replace('KD_MUTEX_PIN_INITIAL_FINISH(true);', '', 1),
        'missing-budget-expiry': code.replace('KD_MUTEX_PIN_BUDGET_EXPIRED();', '(void)0;', 1),
        'missing-expiry-check': code.replace('KD_MUTEX_PIN_EXPIRY_CHECK();', '', 1),
        'missing-withdrawal': code.replace('KD_MUTEX_PIN_WITHDRAW();', '', 1),
        'missing-reservation': code.replace('KD_MUTEX_PIN_WITHDRAW_RESERVED();', '', 1),
        'missing-forced-cancel': code.replace('KD_MUTEX_PIN_FORCED_CANCEL();', '', 1),
        'finish-after-unpin': code.replace(
            'KD_MUTEX_PIN_INITIAL_FINISH(false);\n\tpreempt_enable();',
            'preempt_enable();\n\tKD_MUTEX_PIN_INITIAL_FINISH(false);', 1),
    }
    with tempfile.TemporaryDirectory(prefix='kd-mutex-origin-diag-') as directory:
        path = Path(directory)
        (path / 'fixture.c').write_text(fixture)
        for name, candidate in mutations.items():
            assert name == 'production' or candidate != code, name
            (path / 'proxy_production.h').write_text(candidate)
            binary = path / name
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-I' + directory,
                str(path / 'fixture.c'), '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([binary], capture_output=True, text=True, timeout=10)
            if name == 'production':
                assert result.returncode == 0, result
                print('PASS actual origin diagnostic hooks: observe-only entry, already-completed episode, loop budget, retained-late, expiry and races')
            else:
                assert result.returncode == 1 and 'FAIL proxy pin' in result.stderr, (name, result)
                print('origin diagnostic mutation detected:', name)


if __name__ == '__main__':
    main()
