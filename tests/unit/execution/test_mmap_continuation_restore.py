"""Execute actual builtin MM restore assembly in VM userspace.

The optional DI-write hook models reuse of storage below the raised stack
pointer. It is not an actual interrupt or evidence of the original failure.
"""
import os
import resource
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT


def production():
    source = (ROOT / 'kernel_integration/mmap_lock/overlay/kernel/locking/kd_mmap/provider.c').read_text()
    code = source[source.index('/* A completed instruction'):source.index('EXPORT_SYMBOL_GPL(kd_rwsem_provider_resume);')]
    return code.replace('struct kd_mmap_regs', 'struct kd_regs').replace('KD_MMAP_REG_', 'KD_REG_')


def early_stack_change(code):
    """Move the same final stack operation ahead of unread GPRs in each path."""
    tagged, ordinary = code.split('/* FULL packet storage', 1)
    final = '"popfq\\n\\t"\n\t\t     "popq %%rsp\\n\\t"'
    first_gpr = '"movq %c[r15](%%rdi), %%r15\\n\\t"'
    assert tagged.count(final) == ordinary.count('"popq %%rsp\\n\\t"') == 1
    tagged = tagged.replace(final, '').replace(first_gpr, final + '\n\t\t     ' + first_gpr)
    ordinary = ordinary.replace('"popq %%rsp\\n\\t"', '').replace(
        '"pushq %c[sp](%%rdi)\\n\\t"',
        '"pushq %c[sp](%%rdi)\\n\\t"\n\t\t     "popq %%rsp\\n\\t"')
    return tagged + '/* FULL packet storage' + ordinary


def modeled_reuse(code):
    # One flags-neutral store at the stack transition. The packet is below
    # source SP in this fixture, matching the observed helper-frame layout.
    change = '"popq %%rsp\\n\\t"'
    assert code.count(change) == 2
    return code.replace(change, change + '\n\t\t     "movq $0, fixture_packet+128(%%rip)\\n\\t"')


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    code = production()
    with tempfile.TemporaryDirectory(prefix='kd-mm-continuation-') as directory:
        path = Path(directory)
        for thunk in (None, 'CONFIG_RETHUNK', 'CONFIG_MITIGATION_RETHUNK'):
            for variant in ('production', 'reuse', 'early-reuse'):
                selected = early_stack_change(code) if variant == 'early-reuse' else code
                if variant != 'production':
                    selected = modeled_reuse(selected)
                (path / 'production.h').write_text(selected)
                binary = path / ((thunk or 'direct') + '-' + variant)
                subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                    '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-UNDEBUG',
                    '-fno-stack-protector', '-no-pie',
                    *(['-D' + thunk + '=1'] if thunk else []),
                    *(['-DMODEL_PACKET_REUSE=1'] if variant != 'production' else []),
                    '-I', str(ROOT / 'include'), '-I', str(path),
                    str(ROOT / 'tests/unit/execution/mmap_continuation_restore_fixture.c'),
                    '-o', str(binary)], check=True, timeout=30)
                for mode in (('ordinary', 'tagged') if variant == 'early-reuse' else ('',)):
                    result = subprocess.run([str(binary), *([mode] if mode else [])],
                                            capture_output=True, text=True, timeout=10)
                    if variant == 'early-reuse':
                        assert result.returncode == 1 and 'DI mismatch:' in result.stdout, result
                        print((thunk or 'direct'), variant, mode, 'detected unread packet reuse')
                    else:
                        assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
                        print((thunk or 'direct'), variant, result.stdout.strip())


if __name__ == '__main__':
    main()
