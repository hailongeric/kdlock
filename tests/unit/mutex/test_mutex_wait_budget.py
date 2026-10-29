"""Guest-only event traces through the actual READY-first waiter helper.

Notification/gate atomics and scheduler peers are deterministic substitutes.
These checks do not execute a kernel or establish weak-memory/performance behavior.
"""
import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, read_source, without_includes
from test_spin_shadow import definition


def production():
    header = read_source(ROOT / 'include/kd_mutex.h')
    constants = '\n'.join(re.findall(
        r'^#define KD_MUTEX_(?:WAIT|PROXY_READY|PROXY_CLAIMED|QUEUE_INIT) \d+$', header, re.M))
    assert len(constants.splitlines()) == 4
    constants += '\n' + '\n'.join(line for line in header.splitlines()
                                   if line.startswith(('#define KD_MUTEX_GATE_', '#define KD_MUTEX_CLAIM_SLOTS ')))
    origin = without_includes(read_source(ROOT / 'kernel_module/mutex/pin_origin.inc'))
    # Observe the actual local assignment; retain its value and merge semantics.
    expiry = '#define KD_MUTEX_PIN_BUDGET_EXPIRED() (pin_origin.budget_expired = true)'
    assert origin.count(expiry) == 1
    origin = origin.replace(expiry,
        '#define KD_MUTEX_PIN_BUDGET_EXPIRED() (observe_expiry(), (pin_origin.budget_expired = true))', 1)
    diag = read_source(ROOT / 'kernel_module/mutex/pin_diag.inc')
    declarations = diag[diag.index('#define KD_MUTEX_PIN_REASONS'):diag.index('static int kd_mutex_pin_diag_init')]
    merge = definition(diag, 'static void kd_mutex_pin_origin_finish(const struct kd_mutex_pin_origin *origin,')
    helper = definition(read_source(ROOT / 'kernel_module/mutex/queue.inc'),
                        'static __always_inline void kd_mutex_wait_for_result(struct kd_mutex_node *node)')
    code = constants + '\n#define KDLOCK_MUTEX_DIAGNOSTICS 2\n'
    code += without_includes(read_source(ROOT / 'include/kd_mutex_state.h')) + '\n'
    code += origin + '\n' + declarations + '\n' + merge + '\n' + helper
    return code, helper


def mutations(code, helper):
    changes = {
        'initial-validity-lost': ('BUG_ON(state != KD_MUTEX_PROXY_CLAIMED);',
                                  'BUG_ON(false && state != KD_MUTEX_PROXY_CLAIMED);'),
        'post-validity-lost': ('BUG_ON(state != KD_MUTEX_PROXY_READY && state != KD_MUTEX_PROXY_CLAIMED);',
                               'BUG_ON(false && state != KD_MUTEX_PROXY_READY && state != KD_MUTEX_PROXY_CLAIMED);'),
        'withdrawn-validity-lost': ('BUG_ON(state != KD_MUTEX_WAIT);', 'BUG_ON(false && state != KD_MUTEX_WAIT);'),
        'claimed-does-not-spend-budget': ('} while (--budget);',
                                          '} while (state == KD_MUTEX_PROXY_CLAIMED || --budget);'),
        'initial-budget-shortened': ('} while (--budget);', '} while (--budget && budget > 1);'),
        'threshold-reloads-state': ('KD_MUTEX_PIN_BUDGET_EXPIRED();',
                                    'KD_MUTEX_PIN_BUDGET_EXPIRED();\n\tstate = smp_load_acquire(&node->locked);'),
        'threshold-extra-pause': ('KD_MUTEX_PIN_BUDGET_EXPIRED();',
                                  'cpu_relax();\n\tKD_MUTEX_PIN_BUDGET_EXPIRED();'),
        'cas-wait-shortcuts-reload': ('kd_mutex_gate_end_withdraw(node->lock);',
                                     'kd_mutex_gate_end_withdraw(node->lock);\n\t\t\tif (state == KD_MUTEX_WAIT) goto forced_cancel;'),
        'reservation-release-lost': ('kd_mutex_gate_end_withdraw(node->lock);', '(void)node;'),
        'expiry-marked-again': ('next_poll:', 'next_poll:\n\t\tKD_MUTEX_PIN_BUDGET_EXPIRED();'),
        'finish-after-unpin': ('KD_MUTEX_PIN_INITIAL_FINISH(false);\n\tpreempt_enable();',
                               'preempt_enable();\n\tKD_MUTEX_PIN_INITIAL_FINISH(false);'),
    }
    for name, (before, after) in changes.items():
        assert helper.count(before) == 1, (name, helper.count(before))
        yield name, code.replace(helper, helper.replace(before, after, 1), 1)
    # The two plain assignment sites are the initial and post-expiry loads;
    # the withdrawn condition is a different source spelling.
    load = 'state = smp_load_acquire(&node->locked);'
    assert helper.count(load) == 2
    position = helper.rindex(load)
    candidate = helper[:position] + '(void)node; /* stale snapshot */' + helper[position + len(load):]
    yield 'post-expiry-reuses-state', code.replace(helper, candidate, 1)


def main():
    code, helper = production()
    candidates = [('production', code), *mutations(code, helper)]
    with tempfile.TemporaryDirectory(prefix='kdlock-wait-budget-unit-') as tmp:
        path = Path(tmp)
        for name, candidate in candidates:
            (path / 'wait_budget_production.h').write_text(candidate)
            outcomes = []
            for budget in (1, 4):
                binary = path / f'{name}-{budget}'
                subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                    '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                    f'-DKDLOCK_MUTEX_SPIN_BUDGET={budget}', '-I', str(path),
                    str(ROOT / 'tests/unit/mutex/mutex_wait_budget_fixture.c'),
                    '-o', str(binary)], check=True, timeout=30)
                result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
                if name == 'production':
                    assert result.returncode == 0, (budget, result.returncode, result.stdout, result.stderr)
                    print(result.stdout, end='')
                else:
                    assert result.returncode in (0, 1), (name, budget, result.returncode, result.stderr)
                    if result.returncode:
                        assert 'FAIL wait budget' in result.stderr, (name, budget, result.stderr)
                outcomes.append(result.returncode)
            if name != 'production':
                assert 1 in outcomes, (name, 'mutation survived both budgets')
                print(f'wait budget mutation detected: {name}')


if __name__ == '__main__':
    main()
