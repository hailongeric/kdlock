"""Guest-only production parking transitions and blocking-image admission."""
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from unittest.mock import patch
from source_text import ROOT


def main():
    sys.path.insert(0, str(ROOT/'disassem'))
    from translation_image import mutex_context_error as check
    assert check('MOV R14, Stack_RGS', 'mutex')
    assert check('MOV R14, PT_GS', 'mutex')
    assert check('.include "unknown.S"', 'mutex')
    assert check(None, 'mutex')
    for kind in ('spin', 'rwlock', 'unknown'):
        assert check('MOV R14, Stack_RGS', kind) is None
    assert check('MOV R14, Stack_TASK', 'mutex') is None
    assert check('/* Stack_RGS */ MOV R14, Stack_RCT', 'mutex') is None
    # Exercise the coordinator too: final-image admission must reject GS for
    # both mutex ABIs without consulting a loaded provider's sysfs selector.
    from test_jit_diagnostics import render, translator
    symbols = {'kd_mutex_direct_lock_clobber_v1': 0x5000,
               'kd_mutex_direct_unlock_clobber_v1': 0x6000}
    for abi in (0, 2):
        for lowered in ('MOV R14, Stack_RGS', 'MOV R14, PT_GS'):
            with patch.object(translator, 'emit_jit_assembly', return_value=lowered):
                assembly, log, status = render('c3', lock_kind='mutex', abi=abi,
                    kernel_symbols=symbols, return_status=True)
            assert status == 2 and not assembly, (abi, status, log)
            assert 'mutex cannot delegate origin-CPU GS storage' in log, log
        assembly, log, status = render('c3', lock_kind='mutex', abi=abi,
            kernel_symbols=symbols, return_status=True)
        assert status == 0 and assembly, (abi, status, log)
    with tempfile.TemporaryDirectory(prefix='kd-mutex-parking-') as tmp:
        binary = Path(tmp)/'fixture'
        subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
            '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
            '-I'+str(ROOT/'kernel_module/mutex'),
            str(ROOT/'tests/unit/mutex/mutex_parking_fixture.c'), '-o', str(binary)],
            check=True, timeout=30)
        subprocess.run([str(binary)], check=True, timeout=10)
    print('PASS: sleeping mutex rejects origin GS and permits logical-task input')


if __name__ == '__main__':
    main()
