"""Guest-only batch observations against the real deterministic combiner loop.

The terminal fixture supplies ownership/ACK substitutes and immediate node
reuse. This checks diagnostic accounting and compile-out, not kernel scheduling
or the timing overhead of the enabled instrumentation.
"""
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, read_source, without_includes
from test_mutex_terminal import production_sources


MOCKS = r'''
#define KDLOCK_MUTEX_DIAGNOSTICS 1
#ifndef KDLOCK_MUTEX_BATCH
#define KDLOCK_MUTEX_BATCH 1024
#endif
#define DEFINE_PER_CPU(type, name) type name
#define this_cpu_add(name, value) ((name) += (value))
#define per_cpu(name, cpu) (name)
#define for_each_possible_cpu(cpu) for ((cpu) = 0; (cpu) < 1; (cpu)++)
#define KD_MUTEX_STAT_READ(name) (name)
#define PAGE_SIZE 4096
#define scnprintf snprintf
#define MODULE_PARM_DESC(...)
#define module_param_cb(name, ops, arg, mode) \
    static const void * const param_##name __attribute__((used)) = (ops)
struct kernel_param { int unused; };
struct kernel_param_ops { int (*get)(char *, const struct kernel_param *); };
static unsigned int fls(unsigned int value)
{ return value ? 32U - (unsigned int)__builtin_clz(value) : 0; }
'''


CHECKS = r'''
    static const enum kd_mutex_diag_reason reasons[] = {
        KD_MUTEX_DIAG_UNCLASSIFIED,
        KD_MUTEX_DIAG_EMPTY_TAIL, KD_MUTEX_DIAG_DELAYED_TAIL,
        KD_MUTEX_DIAG_EMPTY_TAIL, KD_MUTEX_DIAG_EXECUTION_REFUSAL,
        KD_MUTEX_DIAG_NATIVE_DONE, KD_MUTEX_DIAG_EARLY_OUTER_RELEASE,
        KD_MUTEX_DIAG_TOTAL_CAP, KD_MUTEX_DIAG_INITIAL_UNEXECUTABLE,
        KD_MUTEX_DIAG_INITIAL_UNEXECUTABLE, KD_MUTEX_DIAG_SOURCE_REFUSAL,
        KD_MUTEX_DIAG_EMPTY_TAIL, KD_MUTEX_DIAG_EXECUTION_REFUSAL,
        KD_MUTEX_DIAG_NATIVE_DONE, KD_MUTEX_DIAG_EARLY_OUTER_RELEASE,
        KD_MUTEX_DIAG_NUMA_BOUNDARY, KD_MUTEX_DIAG_NUMA_BOUNDARY,
        KD_MUTEX_DIAG_EMPTY_TAIL, KD_MUTEX_DIAG_TOTAL_CAP,
        KD_MUTEX_DIAG_EXECUTION_REFUSAL, KD_MUTEX_DIAG_NUMA_TAIL,
        KD_MUTEX_DIAG_UNSUPPORTED_TAIL, KD_MUTEX_DIAG_INITIAL_UNEXECUTABLE,
        KD_MUTEX_DIAG_NUMA_BOUNDARY,
        KD_MUTEX_DIAG_NATIVE_DONE, KD_MUTEX_DIAG_EARLY_OUTER_RELEASE,
    };
    static const unsigned int deferred[] = {
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        2, 2, 1, 1, 8, 64, 1, 7, 7, 64, 0, 0, 8, 0, 0,
    };
    static struct kd_mutex_batch_totals expected;
    unsigned int native = calls && (int)order[calls - 1] == native_at;
    unsigned int refused = calls && (int)order[calls - 1] == refusal_at;
    CHECK(scenario < sizeof(reasons) / sizeof(reasons[0]));
    expected.batches++;
    expected.attempts += calls;
    expected.jit_completed += completed;
    expected.native_completed += native;
    expected.execution_refusals += refused;
    for (unsigned int i = 0; i < calls; i++) {
        int index = order[i];
        if (index == native_at || index == refusal_at)
            continue;
        if (!nodes[index].numa_node) expected.jit_local++;
        else expected.jit_remote++;
    }
    expected.deferred_total += deferred[scenario];
    expected.scan_steps += deferred[scenario];
    expected.scan_exhausted_batches += scenario == 16 || scenario == 20;
    expected.small_fifo_batches += scenario == 11 ||
        scenario == 17 || scenario == 18 || scenario == 19;
    expected.completed_hist[fls(completed + native)]++;
    expected.deferred_peak_hist[fls(deferred[scenario])]++;
    if(reasons[scenario]!=KD_MUTEX_DIAG_UNCLASSIFIED)
        expected.stop_reason[reasons[scenario]-1]++;
#define CHECK_TOTAL(name) CHECK(kd_mutex_batch_totals.name == expected.name);
    KD_MUTEX_DIAG_TOTALS(CHECK_TOTAL)
#undef CHECK_TOTAL
    for (unsigned int i = 0; i < KD_MUTEX_DIAG_COMPLETED_BINS; i++)
        CHECK(kd_mutex_batch_totals.completed_hist[i] == expected.completed_hist[i]);
    for (unsigned int i = 0; i < KD_MUTEX_DIAG_DEFERRED_BINS; i++)
        CHECK(kd_mutex_batch_totals.deferred_peak_hist[i] == expected.deferred_peak_hist[i]);
    for (unsigned int i = 0; i + 1 < KD_MUTEX_DIAG_REASON_COUNT; i++)
        CHECK(kd_mutex_batch_totals.stop_reason[i] == expected.stop_reason[i]);
    CHECK(kd_mutex_batch_totals.batches == kd_mutex_combiner_count);
    CHECK(kd_mutex_batch_totals.jit_completed == kd_mutex_jit_success_count);
'''


EXTRA = r'''
    scenario=21;reset(2);nodes[1].entry_abi=KD_ENTRY_ABI_LEGACY;
    CHECK(kd_mutex_run_combiner(&lock,&nodes[0],NULL,false)==KD_MUTEX_BATCH_OWNED);
    CHECK(calls==1 && completed==1 && wakes==1 && !nodes[1].locked);finish();
    scenario=22;reset(1);CHECK(kd_mutex_run_combiner(&lock,NULL,NULL,false)==KD_MUTEX_BATCH_OWNED);
    CHECK(!calls && !wakes && !lease_gets);finish();
    char json_buffer[PAGE_SIZE];
    int length=kd_mutex_batch_stats_get(json_buffer,NULL);
    CHECK(length>0 && length<(int)sizeof(json_buffer));
    printf("DIAG %s",json_buffer);
    /* A transferred owner has accepted its queue and packet, but has not
     * finished the native suffix. Do not count a completion or a refusal. */
    memset(&kd_mutex_batch_totals,0,sizeof(kd_mutex_batch_totals));
    kd_mutex_combiner_count=1; kd_mutex_jit_success_count=kd_mutex_handoff_count=0;
    struct kd_mutex_batch_diag transfer={.attempts=1,.reason=KD_MUTEX_DIAG_OWNER_TRANSFER};
    kd_mutex_diag_result(&transfer,KD_MUTEX_EXEC_SWAPPED);
    CHECK(transfer.owner_transfers==1 && !transfer.jit_completed &&
          !transfer.native_completed && !transfer.execution_refusals);
    kd_mutex_diag_finish(&transfer);
    length=kd_mutex_batch_stats_get(json_buffer,NULL);
    CHECK(length>0 && length<(int)sizeof(json_buffer));
    printf("TRANSFER %s",json_buffer);
    /* The compact storage omits enum zero. Its JSON gap is still observable,
     * and corrupt/inconsistent totals must not wrap to a plausible count. */
    memset(&kd_mutex_batch_totals,0,sizeof(kd_mutex_batch_totals));
    kd_mutex_batch_totals.batches=1;
    length=kd_mutex_batch_stats_get(json_buffer,NULL);
    CHECK(length>0 && length<(int)sizeof(json_buffer));printf("GAP %s",json_buffer);
    kd_mutex_batch_totals.batches=0;
    kd_mutex_batch_totals.stop_reason[KD_MUTEX_DIAG_EMPTY_TAIL-1]=1;
    length=kd_mutex_batch_stats_get(json_buffer,NULL);
    CHECK(length>0 && length<(int)sizeof(json_buffer));printf("INCONSISTENT %s",json_buffer);
    /* Exercise both declared last bins independently of this fixture's
     * smaller queue. No observation may grow beyond the per-CPU budget. */
    _Static_assert(sizeof(struct kd_mutex_batch_totals)<=384,
                   "batch observations exceed the reserved per-CPU budget");
    memset(&kd_mutex_batch_totals,0,sizeof(kd_mutex_batch_totals));
    struct kd_mutex_batch_diag boundary={.attempts=32767,.jit_completed=32767,
        .jit_local=32767,.deferred_total=127,.peak_deferred=127,
        .reason=KD_MUTEX_DIAG_TOTAL_CAP};
    kd_mutex_diag_finish(&boundary);
    CHECK(kd_mutex_batch_totals.completed_hist[KD_MUTEX_DIAG_COMPLETED_BINS-1]==1);
    CHECK(kd_mutex_batch_totals.deferred_peak_hist[KD_MUTEX_DIAG_DEFERRED_BINS-1]==1);
    /* Every field at u64 maximum must still fit in one complete sysfs page. */
    memset(&kd_mutex_batch_totals,0xff,sizeof(kd_mutex_batch_totals));
    kd_mutex_combiner_count=kd_mutex_jit_success_count=kd_mutex_handoff_count=~0UL;
    length=kd_mutex_batch_stats_get(json_buffer,NULL);
    CHECK(length>0 && length<(int)sizeof(json_buffer));
    printf("MAX %s",json_buffer);
'''


def main():
    types, helpers, loop = production_sources()
    original = (ROOT/'tests/unit/mutex/mutex_terminal_fixture.c').read_text()
    fixture = original.replace('kd_mutex_batch_size=1024', 'kd_mutex_batch_size=KDLOCK_MUTEX_BATCH')
    fixture = fixture.replace('#include "helpers.h"', MOCKS+'\n#include "helpers.h"')
    fixture = fixture.replace('static void finish(void)\n{',
                              'static void finish(void)\n{'+CHECKS)
    fixture = fixture.replace('    printf("PASS terminal queue:', EXTRA+'\n    printf("PASS terminal queue:')
    assert fixture != original and fixture.count('DIAG %s') == 1
    with tempfile.TemporaryDirectory(prefix='kd-mutex-batch-diag-') as tmp:
        path = Path(tmp)
        (path/'types.h').write_text(types)
        (path/'mutex_state_production.h').write_text(
            without_includes(read_source(ROOT/'include/kd_mutex_state.h')))
        (path/'helpers.h').write_text(helpers)
        (path/'loop.h').write_text(loop)
        (path/'fixture.c').write_text(fixture)
        command = shlex.split(os.environ.get('CC', 'cc'))+[
            '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
            # This fixture retains the historical terminal-loop scenarios.
            '-DKDLOCK_MUTEX_NUMA_BOUNDARY=256',
            '-I'+str(path), '-I'+str(ROOT/'tests/unit/mutex')]
        binary = path/'enabled'
        subprocess.run(command+[str(path/'fixture.c'), '-o', str(binary)],
                       check=True, timeout=30)
        result = subprocess.run([str(binary)], text=True, capture_output=True,
                                check=True, timeout=10)
        print(result.stdout, end='')
        values = {line.split(' ', 1)[0]: json.loads(line.split(' ', 1)[1])
                  for line in result.stdout.splitlines() if line.startswith(('DIAG ', 'TRANSFER ', 'GAP ', 'INCONSISTENT ', 'MAX '))}
        sample = values['DIAG']
        assert sample['schema'] == 4 and sample['compiled'] == 1
        assert sample['total_cap'] == 1024 and sample['numa_boundary'] == 256
        assert sample['completed_hist_bins'] == len(sample['completed_hist']) == 16
        assert sample['deferred_peak_hist_bins'] == len(sample['deferred_peak_hist']) == 8
        assert sample['batches'] == 25 == sum(sample['completed_hist'])
        assert sample['batches'] == sum(sample['deferred_peak_hist'])
        assert sample['batches'] == sum(sample['stop_reason'].values())
        assert sample['stop_reason']['unclassified'] == 0
        assert sample['owner_transfers'] == sample['stop_reason']['owner_transfer'] == 0
        assert sample['attempts'] == (sample['jit_completed'] +
                                     sample['native_completed'] + sample['execution_refusals'] +
                                     sample['owner_transfers'])
        assert sample['jit_completed'] == sample['jit_local'] + sample['jit_remote']
        assert sample['deferred_total'] == sample['scan_steps']
        assert sample['legacy']['combiner'] == sample['batches']
        assert sample['legacy']['jit_success'] == sample['jit_completed']
        transfer = values['TRANSFER']
        assert transfer['schema'] == 4 and transfer['batches'] == transfer['attempts'] == 1
        assert transfer['owner_transfers'] == transfer['stop_reason']['owner_transfer'] == 1
        assert transfer['jit_completed'] == transfer['native_completed'] == transfer['execution_refusals'] == 0
        assert transfer['completed_hist'] == [1] + [0] * 15
        assert transfer['deferred_peak_hist'] == [1] + [0] * 7
        assert transfer['legacy'] == dict(combiner=1, jit_success=0, handoff=0)
        maximum = (1 << 64) - 1
        assert values['GAP']['stop_reason']['unclassified'] == 1
        assert values['INCONSISTENT']['stop_reason']['unclassified'] == maximum
        assert values['MAX']['batches'] == maximum
        assert values['MAX']['owner_transfers'] == maximum
        assert values['MAX']['completed_hist'] == [maximum] * 16
        assert values['MAX']['deferred_peak_hist'] == [maximum] * 8
        assert all(value == maximum for value in values['MAX']['stop_reason'].values())
        assert all(value == maximum for value in values['MAX']['legacy'].values())

        # The unchanged queue limit is enforced at build time for diagnostic
        # configurations; do not silently clamp or discard out-of-range data.
        for cap in (4096, 32767):
            subprocess.run(command+[f'-DKDLOCK_MUTEX_BATCH={cap}', '-fsyntax-only',
                                     str(path/'fixture.c')], check=True, timeout=30)
        for cap in (0, 32768):
            rejected = subprocess.run(command+[f'-DKDLOCK_MUTEX_BATCH={cap}', '-fsyntax-only',
                                                str(path/'fixture.c')],
                                      text=True, capture_output=True, timeout=30)
            assert rejected.returncode != 0 and (
                'mutex diagnostic completed histogram does not cover KDLOCK_MUTEX_BATCH'
                in rejected.stderr), (cap, rejected.returncode, rejected.stderr)

        # Undefined poisoned arguments must disappear before compilation. The
        # condition's own side effect still occurs once with short circuiting.
        off = '#define MODULE_INFO(...)\n'
        off += without_includes(read_source(ROOT/'kernel_module/mutex/pin_origin.inc'))
        off += without_includes(read_source(ROOT/'kernel_module/mutex/batch_diag.inc'))
        off += r'''
static unsigned int asserted;
static void kd_mutex_proxy_assert_claimed(unsigned int value) { asserted += value; }
struct off_layout { int original; KD_MUTEX_DIAG_MEMBER };
_Static_assert(sizeof(struct off_layout) == sizeof(int), "off adds storage");
int main(void)
{
    volatile unsigned int calls = 0;
    if (!(KD_MUTEX_DIAG_CONDITION(poison(), ++calls == 1, poison()) ||
          KD_MUTEX_DIAG_CONDITION(poison(), ++calls == 2, poison()))) return 1;
    KD_MUTEX_DIAG_DEFERRED(poison());
    KD_MUTEX_DIAG_SCAN_END(poison(), poison());
    KD_MUTEX_DIAG_SMALL_FIFO(poison());
    KD_MUTEX_DIAG_REQUEST(poison(), poison());
    KD_MUTEX_DIAG_RESULT(poison(), poison());
    KD_MUTEX_DIAG_STOP(poison(), poison());
    KD_MUTEX_DIAG_FINISH(poison());
    KD_MUTEX_PIN_INC(poison(), poison);
    KD_MUTEX_PIN_BEGIN(poison());
    KD_MUTEX_PIN_END(poison());
    KD_MUTEX_PIN_STOP(poison(), poison());
    KD_MUTEX_PIN_DRAIN(poison(), poison());
    if (!KD_MUTEX_PIN_CONDITION(poison(), calls == 1, poison())) return 2;
    KD_MUTEX_PIN_ASSERT(poison(), 1);
    KD_MUTEX_PIN_WAIT_ENTER();
    KD_MUTEX_PIN_BUDGET_EXPIRED();
    KD_MUTEX_PIN_EXPIRY_CHECK();
    KD_MUTEX_PIN_WITHDRAW();
    KD_MUTEX_PIN_FORCED_CANCEL();
    KD_MUTEX_PIN_INITIAL_FINISH(poison());
    if (KD_MUTEX_PIN_DIAG_INIT()) return 3;
    KD_MUTEX_PIN_DIAG_EXIT();
    return calls != 1 || asserted != 1;
}
'''
        (path/'off.c').write_text(off)
        for name, flags in (('default', []), ('explicit-off', ['-DKDLOCK_MUTEX_DIAGNOSTICS=0'])):
            binary = path/name
            subprocess.run(command+flags+[str(path/'off.c'), '-o', str(binary)],
                           check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=10)
        print('PASS mutex batch diagnostics: exact exit/count/histogram/locality observations, '
              'complete sysfs JSON, and default/explicit compile-out')


if __name__ == '__main__':
    main()
