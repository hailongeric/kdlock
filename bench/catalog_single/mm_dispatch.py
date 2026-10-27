#!/usr/bin/env python3
"""Guest-only exact coordinate dispatcher; keeps maintained runner validation intact.

Only the plan-producing function is narrowed. The original runner still checks
its kernel, preparation, callbacks, source hashes, operation totals and drain.
The request binds all source bytes and prior attempted coordinates; a failed or
uncertain coordinate is never selected again.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from mm_plan import key, remaining, require, select
from mm_archive import inventory


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dispatch(request, expected):
    require(sha(request) == expected, 'request hash changed')
    data = json.loads(request.read_text())
    require(ROOT == Path('/root/host_fs/kdlock') and os.geteuid() == 0, 'designated VM checkout required')
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == data['boot_id'], 'boot changed')
    manifest = Path(data['manifest'])
    require(sha(manifest) == data['manifest_sha256'], 'source manifest changed')
    for name, digest in json.loads(manifest.read_text())['files'].items():
        path = Path(name)
        require(not path.is_absolute() and '..' not in path.parts, 'unsafe source manifest path')
        require(sha(ROOT / path) == digest, 'guest source changed: ' + name)
    attempted = []
    for prior in data['prior_attempts']:
        directory = Path(prior['directory'])
        require(inventory(directory) == prior['inventory'], 'prior attempt source, workspace or phase bytes changed')
        actual = {str(p.relative_to(directory)): sha(p) for p in directory.glob('*/result.json')}
        require(actual == prior['session_receipts'], 'prior attempt coordinates or bytes changed')
        require(sha(directory / 'result.json') == prior['result_sha256'], 'prior attempt result changed')
        attempted.extend(prior['attempted_coordinates'])
    require(data['coordinates'] == remaining(data['suite'], attempted), 'only reviewed unmeasured coordinates may run')
    shared = data['suite'].startswith('shared-')
    runner = 'bench/mmap_writer/linux70.py' if shared else 'bench/mmap_fault/timing.py'
    spec = importlib.util.spec_from_file_location('selected_mm_runner', ROOT / runner)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if shared:
        original = module.plan
        module.plan = lambda mode: select(data['suite'], original(mode), data['coordinates'])
    else:
        original = module.measurement_plan
        module.measurement_plan = lambda single, workload: select(data['suite'], original(single, workload), data['coordinates'])
    require(data['argv'][0] == 'measure' and '--output' in data['argv'], 'measurement action required')
    sys.argv = [str(ROOT / runner), *data['argv']]
    module.main()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request', type=Path)
    parser.add_argument('--sha256', required=True)
    args = parser.parse_args()
    dispatch(args.request, args.sha256)
