"""Guest-only production parking transitions and blocking-image admission."""
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from source_text import ROOT


def main():
    sys.path.insert(0, str(ROOT/'disassem'))
    from translation_image import blocking_mutex_context_error as check
    assert check('MOV R14, Stack_RGS', True)
    assert check('MOV R14, PT_GS', True)
    assert check('.include "unknown.S"', True)
    assert check(None, True)
    assert check('MOV R14, Stack_RGS', False) is None
    assert check('MOV R14, Stack_TASK', True) is None
    assert check('/* Stack_RGS */ MOV R14, Stack_RCT', True) is None
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
