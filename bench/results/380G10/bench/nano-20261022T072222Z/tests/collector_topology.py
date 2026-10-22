#!/usr/bin/env python3
"""Check the unchanged client parser against the temporary 40-vCPU topology."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path('/root/host_fs/kdlock')
WORKERS = [*range(1, 9), 12, 16, 20, 24, 28, 32, 36]
assert os.cpu_count() == 40
results = []
with tempfile.TemporaryDirectory(prefix='nano-collector-') as directory:
    folder = Path(directory)
    source = ROOT / 'bench/spin_cacheline/client.c'
    (folder / 'probe.c').write_text(
        '#define open denied_open\n#include "' + str(source) + '"\n'
        'int denied_open(const char *p, int f, ...) '
        '{ (void)p; (void)f; errno=ENOENT; return -1; }\n')
    binary = folder / 'probe'
    subprocess.run(['cc', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread',
                    folder / 'probe.c', '-o', binary], check=True, timeout=30)
    cases = []
    for workers in WORKERS:
        cpus = ','.join(map(str, range(workers)))
        for collector, expected in ((38, 1), (workers - 1, 2)):
            cases.append((workers, cpus, collector, False, expected))
    cases += [(64, ','.join(map(str, range(64))), 63, True, 2),
              (36, ','.join(map(str, range(36))), 38, True, 2)]
    for workers, cpus, collector, shared, expected in cases:
        argv = [binary, '--cachelines', '1', '--duration-ms', '2000',
                '--cpus', cpus, '--collector-cpu', str(collector)]
        if shared:
            argv.append('--share-collector')
        result = subprocess.run(argv, capture_output=True, text=True, timeout=10)
        row = dict(workers=workers, collector=collector, shared=shared,
                   expected=expected, actual=result.returncode, stderr=result.stderr)
        results.append(row)
        assert result.returncode == expected, row
print(json.dumps(dict(passed=True, online_cpus=os.cpu_count(), checks=results), indent=2))
