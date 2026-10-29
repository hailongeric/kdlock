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
#define this_cpu_inc_return(name) (++(name))
#if KDLOCK_MUTEX_PIN_TSC_SHIFT
static u64 stamp_ticks;
static u64 rdtsc_ordered(void) { stamp_ticks+=7;return stamp_ticks; }
#endif
'''
    fixture = fixture.replace('#include "helpers.h"', mocks + '\n#include "helpers.h"')
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
                          for line in result.stdout.splitlines() if line.startswith(('PIN ', 'PINMAX '))}
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
                print(f'pin diagnostics shift={shift}: {sample["selections"]} selection receipts; bounded storage/JSON/ACK accounting')


if __name__ == '__main__':
    main()
