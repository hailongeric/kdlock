"""Linux 7 identity and host gates for the private backing-lock MM suites.

These gates do not qualify a completed measurement: its immediate host endpoint
and the existing callback/data/drain oracles remain separate obligations.
"""
import datetime
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
RELEASE = '7.0.0-38-kdlock1'
PYTHON = '/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'
PACKAGES = dict(miasm='0.1.5', future='1.0.0', pyparsing='2.4.7', pyelftools='0.27')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


host_capture = load_module('mm_host_capture', ROOT/'bench/basic/capture_host.py')


def arguments(parser):
    parser.add_argument('--boot-id', required=True, help='exact verified Linux 7 boot UUID')
    parser.add_argument('--host-reference', type=Path, required=True,
                        help='recorded Linux 7 fixed-frequency host reference')
    parser.add_argument('--host-reference-sha256', required=True)


def guest(boot_id=None, *, release=RELEASE):
    actual = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    require(os.geteuid() == 0 and ROOT == Path('/root/host_fs/kdlock') and
            release in (RELEASE, '7.0.0-38-kdmm1', '7.0.0-38-kdscope1', '7.0.0-38-kdscope3') and
            os.uname().release == release and
            (boot_id is None or actual == boot_id),
            'verified Linux 7 development guest and selected boot required')
    tag = os.environ.get('KDLOCK_SNAPSHOT_TAG', '')
    require(os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
            bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', tag)),
            'explicit confirmed recovery snapshot required')
    require(sys.executable == PYTHON and shutil.which('python3') == PYTHON,
            'pinned Linux 7 translation Python required')
    return actual


def dependency_identity():
    packages = {name: importlib.metadata.version(name) for name in PACKAGES}
    require(packages == PACKAGES, 'translation dependency versions differ')
    patch = load_module('mm_miasm_patch', ROOT/'disassem/miasm_python314.py').verify_runtime()
    return dict(packages=packages, python=sys.executable, semantic_builder=patch)


def kernel_binding(identity, build, baseline, *, private_backing_locks=True):
    require(identity.get('ok') is True and identity.get('schema') == 2 and
            identity.get('runtime_policy_verified') is True and
            bool(identity.get('running_build_id')), 'verified live schema-2 identity required')
    config = (build/'.config').read_bytes()
    require(b'CONFIG_KDLOCK_MMAP=y' not in config.splitlines(),
            'private-backing suite requires native kernel mmap locking')
    require(b'# CONFIG_KDLOCK_MMAP is not set' in config.splitlines(),
            'explicit disabled MM adapter configuration required')
    return dict(release=RELEASE, build_id=identity['running_build_id'],
                configuration_sha256=hashlib.sha256(config).hexdigest(),
                manifest_sha256=hashlib.sha256((baseline/'manifest.json').read_bytes()).hexdigest(),
                runtime_policy=identity['runtime_policy'], kernel_mmap_backend='native',
                private_backing_locks=private_backing_locks)


def compare_host(reference, current, now, snapshot, strict):
    """Only pinned worker lifetimes may vary under explicit exploration."""
    for host in (reference, current):
        host_capture.validate(host)
        require(host['pins_verified'] and host['frequency_verified'], 'unverified host capture')
    stamp = datetime.datetime.fromisoformat(current['captured_utc'])
    require(datetime.datetime.fromisoformat(reference['captured_utc']) <= stamp and
            0 <= (now-stamp).total_seconds() <= 300, 'stale host capture')
    require(current['recovery_snapshot'] == snapshot, 'selected recovery snapshot differs')
    for key in ('host_boot_id', 'cpufreq', 'no_turbo', 'numa', 'monitor_path', 'recovery_snapshot'):
        require(reference[key] == current[key], 'host reference differs: '+key)
    old, new = reference['qemu'][0], current['qemu'][0]
    require(all(old[key] == new[key] for key in ('pid', 'start_ticks', 'args')),
            'QEMU process/configuration differs')
    require(host_capture.memory_bindings(old) == host_capture.memory_bindings(new),
            'host memory bindings differ')
    before = {row['tid']: row for row in old['tasks']}
    after = {row['tid']: row for row in new['tasks']}
    permanent = lambda tasks:{tid:row for tid,row in tasks.items() if row['comm'] != 'worker'}
    require(permanent(before) == permanent(after),
            'permanent QEMU task identity/placement differs')
    extra = [row for tid,row in after.items() if before.get(tid) != row]
    retired = [row for tid,row in before.items() if after.get(tid) != row]
    require(all(row['comm'] == 'worker' and row['affinity'] == [63] for row in extra+retired),
            'only pinned worker lifetimes may differ')
    require(not strict or before == after, 'strict QEMU task set differs')
    return dict(strict_host_gate='PASS' if strict else 'FAILED',
                exploratory=not strict, task_set_unchanged=before == after,
                additional_workers=extra, retired_workers=retired,
                original_threads=len(before), observed_threads=len(after),
                fixed_frequency_khz=2000000, performance_accepted=False,
                host_endpoint='PENDING')


def host_reference(path, expected):
    require(bool(re.fullmatch('[0-9a-f]{64}', expected or '')),
            'explicit host-reference SHA256 required')
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == expected, 'host reference SHA256 differs')
    return data, json.loads(data)
