#!/usr/bin/env python3
"""VM-only ordinary return after successful live5; source preparation runs nothing.

`reboot` is the sole mutating action and invokes only ordinary systemctl reboot.
`post-normal` only reads identity/boot files and writes a fresh proof directory.
Neither phase selects a GRUB entry, unloads code, resets controls or infers drain.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import time

ROOT = Path('/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f')
BASE = ROOT / 'receipts/return-normal-after-live5-20261110-UTC-01'
POSTBOOT = ROOT / 'receipts/postboot-kdrebuild3-20261110-UTC-01'
WORK = Path('/mnt/kdlock-builds/kdlock-main-work')
LIVE = WORK / 'live5-runtime-69ba6b03-20261110-UTC-01'
CONTROLLER = WORK / 'live5-controller-69ba6b03-20261110-UTC-01/result.json'
SOURCE = '69ba6b030c1eb7e5f1c3f9461b70f5fef6791309'
CORE = '1b50e37382d2c739b16953027c47d7e2388562f0'
NORMAL = '7.0.0-38-kdlock1'
CANDIDATE = '7.0.0-38-kdrebuild3'
NORMAL_BID = 'b61c7bef25d2068f2a05ca3c31a5714c20c4aa62'
CANDIDATE_BID = '264a4ef8e55952e5d9ceccf93f65f25f05a50c1f'
MODULE_SHA = '2be5cd04f9b7e5aa570c56dd1e940619e03696b33ef8d14bbc4262d2ac11a2a3'
BUSY = {'make', 'gmake', 'gcc', 'gcc-15', 'cc1', 'cc1plus', 'clang', 'ld', 'ld.bfd',
        'ld.lld', 'as', 'objtool', 'insmod', 'rmmod', 'modprobe', 'depmod', 'perf', 'fio', 'fstrim'}
LIMIT = 16 * 1024 * 1024


def require(value, message):
    if not value:
        raise RuntimeError(message)


def read(path):
    with Path(path).open('rb') as stream:
        value = stream.read(LIMIT + 1)
    require(len(value) <= LIMIT, 'receipt exceeds reviewed 16MiB bound: ' + str(path))
    return value


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def identity():
    return {'release': os.uname().release, 'machine': os.uname().machine,
        'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'taint': int(Path('/proc/sys/kernel/tainted').read_text())}


def activity():
    require(not Path('/sys/module/kd_runtime_fixture').exists(), 'fixture module remains')
    devices = sorted(str(p) for p in Path('/dev').glob('kd*'))
    require(not devices, 'KD devices remain: ' + repr(devices))
    ps = subprocess.run(['ps', '-eo', 'pid,ppid,comm,args'], capture_output=True,
                        text=True, check=True, timeout=10)
    bad = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdecimal() or int(proc.name) == os.getpid():
            continue
        try:
            comm = (proc / 'comm').read_text().strip()
            command = (proc / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
        except (FileNotFoundError, ProcessLookupError):
            continue
        if comm in BUSY or comm.startswith(('kd-fixture', 'kd-scene/', 'kd-runtime')) or any(
                text in command for text in ('run_runtime_fixture.py', 'unittest discover', 'pytest')):
            bad.append({'pid': proc.name, 'comm': comm, 'command': command})
    require(not bad, 'build/test/fixture activity remains: ' + repr(bad))
    return {'ps': ps.stdout, 'module_absent': True, 'devices': devices, 'unexpected': bad}


def protected_files(rows):
    expected = {str(Path('/boot') / (prefix + release))
        for release in (NORMAL, '6.1.159-kdclobber2')
        for prefix in ('vmlinuz-', 'config-', 'System.map-', 'initrd.img-')}
    require(len(rows) == 8 and {row['path'] for row in rows} == expected,
            'exact eight normal/recovery boot identities required')
    for row in rows:
        path = Path(row['path']); value = path.lstat()
        require(stat.S_ISREG(value.st_mode) and stat.S_IMODE(value.st_mode) == row['mode'] and
                value.st_size == row['size'] and digest(path) == row['sha256'],
                'normal/recovery boot file differs: ' + str(path))
    require(Path('/lib/modules/' + NORMAL).is_dir() and
            Path('/lib/modules/6.1.159-kdclobber2').is_dir(), 'normal/recovery module namespace missing')


def grub(expected):
    raw = read('/boot/grub/grub.cfg')
    require(hashlib.sha256(raw).hexdigest() == expected['configuration_sha256'],
            'GRUB configuration differs from the new kernel3 postboot proof')
    require(('set default="' + expected['normal_default'] + '"').encode() in raw,
            'normal default is not retained')
    result = subprocess.run(['grub-editenv', '/boot/grub/grubenv', 'list'],
                            capture_output=True, text=True, check=True, timeout=10)
    env = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    require(not env.get('next_entry') and not env.get('prev_saved_entry'),
            'one-shot or previous selection remains')
    return {'configuration_sha256': hashlib.sha256(raw).hexdigest(),
            'normal_default': expected['normal_default'], 'environment': env}


def notes_build_id(raw):
    offset = 0; ids = []
    while offset < len(raw):
        require(len(raw) - offset >= 12, 'truncated running note header')
        namesz, descsz, kind = struct.unpack_from('<III', raw, offset)
        start = offset + 12; desc = start + ((namesz + 3) & ~3)
        end = desc + ((descsz + 3) & ~3)
        require(end <= len(raw), 'truncated running note payload')
        if kind == 3 and raw[start:start + namesz] == b'GNU\0':
            ids.append(raw[desc:desc + descsz].hex())
        offset = end
    require(len(ids) == 1, 'running GNU BuildID is missing/ambiguous')
    return ids[0]


def reboot():
    BASE.mkdir(mode=0o700)
    report = {'phase': 'CHECKING', 'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'source_commit': SOURCE, 'core_commit': CORE, 'reboot_invoked': False}
    try:
        post_raw = read(POSTBOOT / 'result.json'); post = json.loads(post_raw)
        require(post['phase'] == 'POSTBOOT_IDENTITY_VERIFIED' and post['running_build_id'] == CANDIDATE_BID,
                'actual completed kernel3 postboot proof required')
        actual = identity()
        require(actual['release'] == CANDIDATE and actual['machine'] == 'x86_64' and
                actual['boot'] == post['boot_id'] and actual['taint'] & ~12288 == 0,
                'running candidate boot/taint differs')
        result_raw = read(LIVE / 'result.json'); result = json.loads(result_raw)
        control_raw = read(CONTROLLER); control = json.loads(control_raw)
        require(control['returncode'] == 0 and control['status'] == 'RETURNED' and
                control['host_source_commit'] == SOURCE and control['kernel_code_commit'] == CORE and
                control['boot_id'] == actual['boot'], 'actual completed live5 controller required')
        require(result['status'] == 'protected_jit_recursive_mechanism_pass' and
                result['module_sha256'] == MODULE_SHA and
                result['returned_full_jit_body'] == 'protected_episode_completed' and
                result['full_c_function_jit_return'] == 'outside_protected_episode_scope' and
                result['warm_claim_empty'] is True and result['observation_overflow'] == 0 and
                result['observation_records'] > 0 and
                result['managed_fork_exit']['shutdown_native_holds_drained'] is True,
                'protected completion/managed native-hold drain is not established')
        warm = result['warm_completion']
        require(any(row['name'] == 'warm-plain' and row['end'] > row['start'] for row in warm),
                'fixed-image plain completion evidence missing')
        for mode in (1, 2):
            rows = [row for row in warm if row['name'] == 'warm-recursive-' + str(mode) and row['mode'] == mode]
            require(len(rows) == 1, 'exact recursive completion case missing')
            proof = rows[0]; root, child, returned = proof['root_completion'], proof['child_completion'], proof['child_return']
            require(root['node'] == proof['root'] and child['node'] == proof['child'] and
                    proof['root'] != proof['child'] and root['state'] == child['state'] == proof['state'] and
                    root['result'] == 3 and child['result'] == (5 if mode == 2 else 3) and
                    root['flags'] & 1536 == 1536 and child['flags'] & 1536 == 1536 and
                    returned['flags'] & 1024 and returned['related'] == proof['child'] and
                    returned['source_user'] and returned['return_user'] and
                    returned['source_user'] != returned['return_user'], 'positive exact root/child return proof differs')
        wires = []
        for path in sorted((LIVE / 'wire').glob('attempt-*/result.json')):
            row = json.loads(read(path)); row['receipt_path'] = str(path); wires.append(row)
        require(len(wires) >= 4 and all(row['status'] == 0 and row['completed_response'] is True for row in wires)
                and [row['operation'] for row in wires[-4:]] == [9, 10, 11, 6],
                'actual wire completion/shutdown/archive/settle/end is incomplete')
        require(digest(LIVE / 'shutdown-archive.json') == result['archive_sha256'], 'durable archive bytes differ')
        protected_raw = read(POSTBOOT / 'normal-recovery-boot-unchanged.json')
        protected = json.loads(protected_raw); protected_files(protected['files'])
        report.update(actual_before=actual, activity=activity(), grub=grub(post['grub']),
            protected_boot_files=protected['files'], stage_snapshot_sha256=protected['stage_snapshot_sha256'],
            postboot_sha256=hashlib.sha256(post_raw).hexdigest(),
            protected_postboot_sha256=hashlib.sha256(protected_raw).hexdigest(),
            live_result_sha256=hashlib.sha256(result_raw).hexdigest(),
            live_controller_sha256=hashlib.sha256(control_raw).hexdigest(),
            wire_count=len(wires), wire_operations=[row['operation'] for row in wires],
            all_wire_completed_zero=True, archive_sha256=result['archive_sha256'],
            settled_keys=result['settled_keys'], acknowledged_keys=len(result['ordinary_indirect_learning']['acknowledged']),
            argv=['systemctl', 'reboot'], timeout_seconds=30,
            policy='Ordinary reboot only after successful actual completion/unload; no force, selection, reset or cleanup.')
        report['phase'] = 'PRE_REBOOT_VERIFIED'
        save(BASE / 'pre-reboot.json', report)
        print(json.dumps({k: v for k, v in report.items() if k != 'activity'}, indent=2), flush=True)
        report['reboot_invoked'] = True
        started = time.monotonic()
        command = subprocess.run(report['argv'], capture_output=True, text=True, timeout=30)
        report.update(phase='REBOOT_COMMAND_RETURNED', returncode=command.returncode,
            stdout=command.stdout, stderr=command.stderr, elapsed_seconds=time.monotonic() - started)
        save(BASE / 'reboot-result.json', report)
        require(command.returncode == 0, 'ordinary reboot command returned failure')
    except BaseException as error:
        report.update(phase='FAILED_RETAIN_OUTPUT', error_type=type(error).__name__, error=str(error))
        save(BASE / 'failure.json', report)
        raise


def post_normal():
    output = BASE / 'post-normal'; output.mkdir(mode=0o700)
    report = {'phase': 'CHECKING', 'utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        before = json.loads(read(BASE / 'pre-reboot.json'))
        require(before['phase'] == 'PRE_REBOOT_VERIFIED', 'verified prior reboot preconditions missing')
        actual = identity()
        require(actual['release'] == NORMAL and actual['machine'] == 'x86_64' and
                actual['taint'] == 0 and actual['boot'] != before['actual_before']['boot'],
                'normal fresh untainted boot is not established')
        raw_notes = read('/sys/kernel/notes'); build_id = notes_build_id(raw_notes)
        require(build_id == NORMAL_BID, 'normal running BuildID differs')
        protected_files(before['protected_boot_files'])
        report.update(actual=actual, build_id=build_id, grub=grub(before['grub']),
            protected_boot_files=before['protected_boot_files'], activity=activity(),
            pre_reboot_sha256=digest(BASE / 'pre-reboot.json'),
            scope='Read-only fresh normal boot, eight protected boot files and idle proof; no build/test/module operation.')
        with (output / 'running-kernel-notes.bin').open('xb') as stream:
            stream.write(raw_notes); stream.flush(); os.fsync(stream.fileno())
        require(identity() == actual, 'boot identity changed during normal proof')
        report['phase'] = 'NORMAL_IDENTITY_VERIFIED'
        save(output / 'result.json', report)
        print(json.dumps({k: v for k, v in report.items() if k != 'activity'}, indent=2), flush=True)
    except BaseException as error:
        report.update(phase='FAILED_RETAIN_OUTPUT', error_type=type(error).__name__, error=str(error))
        save(output / 'failure.json', report)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('reboot', 'post-normal'))
    args = parser.parse_args()
    require(os.geteuid() == 0, 'designated VM root required')
    reboot() if args.phase == 'reboot' else post_normal()
