#!/usr/bin/env python3
"""Run reviewed analysis and validation in the idle VM; retain actual statuses."""
import json
from pathlib import Path
import subprocess
import time

ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex32-traffic-20261019')
ARMS = ['baseline', 'fetchadd', 'old256', 'hint', 'inline']


def main():
    assert Path.cwd() == ROOT
    output = BASE / 'final-analysis-commands.json'
    assert not output.exists(), 'preserve previous attempt before retrying'
    commands = []
    for name in ('summarize.py', 'profile-analysis.py', 'finalize.py'):
        argv = ['python3', str(BASE / name), '--base', str(BASE), '--arms', *ARMS]
        if name == 'finalize.py':
            for arm in ('fetchadd', 'hint', 'inline'):
                argv += ['--check', arm + '=checks-' + arm]
            argv += ['--current-arm', 'inline']
        start = time.time()
        result = subprocess.run(argv, cwd=ROOT, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=240)
        commands.append(dict(argv=argv, cwd=str(ROOT), started_unix=start,
                             finished_unix=time.time(), exit_code=result.returncode,
                             stdout=result.stdout.decode(errors='replace')))
        output.write_text(json.dumps(commands, indent=2) + '\n')
        print(result.stdout.decode(errors='replace'), end='', flush=True)
        if result.returncode:
            raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
