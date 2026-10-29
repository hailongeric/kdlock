"""VM-only production instruction handshake with two pthread participants.

Kernel owner/context/per-CPU lookup primitives are explicit doubles. The actual
request producer, waiter consumer and CPU instructions execute; release/acquire
uses compiler atomics and a deterministic post-ACK interleaving.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from source_text import ROOT


def main():
    source = (ROOT / 'kernel_module/mutex/origin_instruction.inc').read_text()
    mutations = {
        'production': None,
        'missing-rearm-before-ack': ('WRITE_ONCE(node->locked, 1);', '(void)node;'),
        'late-rearm-overwrites-next-publication': (
            'smp_store_release(&request->returned, true);',
            'smp_store_release(&request->returned, true);\n\tWRITE_ONCE(node->locked, 1);'),
        'waiter-preemption-not-checked': (
            'preempt_count() != 1 || irqs_disabled() || !current->migration_disabled ||',
            'irqs_disabled() || !current->migration_disabled ||'),
        'timestamp-high-half-lost': ('regs->dx = dx;', 'regs->dx = 0x100000000UL;'),
    }
    with tempfile.TemporaryDirectory(prefix='kd-mutex-origin-') as tmp:
        tmp = Path(tmp)
        for name, mutation in mutations.items():
            code = source
            if mutation:
                before, after = mutation
                assert before in code, name
                code = code.replace(before, after)
            (tmp / 'production.h').write_text(code)
            binary = tmp / name
            subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-pthread', '-Wall', '-Wextra', '-Werror',
                '-I', str(ROOT / 'include'), '-I', str(tmp),
                str(ROOT / 'tests/unit/mutex/mutex_origin_instruction_fixture.c'),
                '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=15)
            if mutation:
                assert result.returncode == 1 and 'FAIL line=' in result.stderr, (
                    name, result.returncode, result.stdout, result.stderr)
                print('origin handshake mutation detected:', name)
            else:
                assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
                print(result.stdout, end='')


if __name__ == '__main__':
    main()
