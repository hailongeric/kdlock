#!/usr/bin/env python3
"""VM-only installed-byte verification or a separately receipted one-shot arm.

No file installation, menu append, build, module operation or reboot is present.
The original failed install and its source helpers are immutable prerequisites.
"""
import argparse
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import runpy
import stat
import time

BASE = Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01')
OLD = BASE / 'receipts/install-kdrebuild8-api-01'
FINAL = BASE / 'receipts/install-kdrebuild8-finalize-01'
ARM = BASE / 'receipts/arm-kdrebuild8-finalize-01'
INPUT = Path('/mnt/kdlock-builds2/kdlock-main-kernel8-input-0d42063e-01/install-finalize-helpers-01')
RELEASE = '7.0.0-38-kdrebuild8'
ENTRY = 'kdlock-kdrebuild8-api-01'
MAX_FILE = 50331648
MAX_COPY = 134217728
PINS_SHA = '8550478a37e6dcb4bea6ee99a2d6082b8fd9b5b7dbc225f679d4f51a439bdbb3'
CHECKS_SHA = '2610bc0c19dafc9ccf87b56dd85802ac4f22d0dce2ac1b9ae6d0dd4c3cb8ecab'
OLD_HASHES = {'controller.py': '409f640efa69425ee8b8849c4f1897b9df83e4c1a7eccbea2b596ab7bb99a99b',
              'checks.py': '1726d01a4794f82ca8cb1a92218a70dd59272fa2e5e8bdd27a266bd31d92a472',
              'stage-complete.json': 'fedb5a315041a7503167df8d83f0c70960625a5922b14f25fa2847cb871a918c',
              'check-complete.json': '9bd3fcd4671643ab461846684d1093e4c8754ec35d0ad3b49e2a617b9a90fa9b',
              'install-failure.json': '83904a07c1a200e22d28c0f8a6102c241c0aa622ec1397f1193edd51e9655b1a',
              'install-journal.jsonl': 'f37038c75ff65f7908dd92b78668a24c0fd3635dbb30e8ce77dad8383882d345'}
COPY_NAMES = ('stage-grub-sources.json', 'custom.cfg-before', 'candidate-entry.cfg', 'stage-protected-before.json',
              'install-modules-installed.json', 'configuration.json', 'identity-pin.json', 'limited-stage.json',
              'helper-hashes.json', 'root-budget-before-install.json')
record = None
out = None
functions = None
checks = None


def need(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1048576), b''):
            result.update(block)
    return result.hexdigest()


def save(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2) + chr(10)).encode()
    with Path(path).open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_result():
    temporary = out / '.result.new'
    save(temporary, record)
    os.replace(temporary, out / 'result.json')
    fd = os.open(out, os.O_RDONLY | os.O_DIRECTORY)
    os.fsync(fd)
    os.close(fd)


def recovery(path, expected):
    need(digest(path) == expected, 'fresh actual recovery bytes differ')
    value = json.loads(Path(path).read_text())
    age = time.time() - datetime.datetime.fromisoformat(value['utc']).timestamp()
    need(0 <= age <= 900 and value['hostname'] == 'Super-Server' and value['pid'] == 257489 and
         value['exe'] == '/usr/bin/qemu-system-x86_64', 'current host/QEMU or recovery age differs')
    paths = {'/home/eric/vm/qemu-disks/ubuntu22.04.img', '/home/eric/vm/qemu-disks/sda.qcow2',
             '/home/eric/vm/qemu-disks/kdlock-builds2-20261031/builds.qcow2'}
    need(len(value['images']) == 3 and {row['path'] for row in value['images']} == paths and
         all(row['path'] == row['realpath'] and row['open_fds'] and row['host_available'] >= 8*1024**3
             for row in value['images']), 'three attached image identities/headroom differ')
    texts = {row['command']: row['output'] for row in value['hmp']}
    need(len(texts) == len(value['hmp']) and 'VM status: running' in texts['info status'], 'VM not observed running')
    listing = texts['info snapshots'].split('List of snapshots present on all disks:', 1)[1].split('List of partial', 1)[0]
    need(any('kdlock-builddisk-clean-20261031' in row.split() for row in listing.splitlines()), 'all-disk recovery absent')
    return {'path': str(path), 'sha256': expected, 'utc': value['utc']}


def original():
    for name, expected in OLD_HASHES.items():
        need(digest(OLD/name) == expected, 'original install prerequisite changed: ' + name)
    failure = json.loads((OLD/'install-failure.json').read_text())
    need(failure['error'] == "RuntimeError('command failed; preserve partial state: grub-installed')" and
         failure['one_shot_may_be_set'] is False, 'different original failure')
    journal = [json.loads(row) for row in (OLD/'install-journal.jsonl').read_text().splitlines()]
    done = [row for row in journal if row['event'] == 'command_finished']
    need(len(done) == 15 and all(row['returncode'] == 0 and row['timed_out'] is False for row in done[:-1]) and
         done[-1]['label'] == 'grub-installed' and done[-1]['returncode'] == 1 and done[-1]['timed_out'] is False,
         'actual fourteen rc0 commands and sole menu-classification failure required')
    need(not (OLD/'install-complete.json').exists() and not (OLD/'installed-boot.json').exists(),
         'original incomplete outcome was changed')
    logs = {}
    for row in done:
        need(not Path('/proc', str(row['pid'])).exists(), 'original command actor remains')
        result = json.loads((OLD/('install-'+row['label']+'-result.json')).read_text())
        need(all(result[key] == row[key] for key in result) and digest(row['log']) == row['log_sha256'],
             'original command result/output changed')
        logs[row['log']] = row['log_sha256']
    text = (OLD/'install-grub-installed.log').read_text()
    need('missing/ambiguous advanced entry: 7.0.0-38-kdrebuild6' in text, 'different menu failure')
    return logs


def origin_pins():
    path = INPUT/'origin-pins.json'
    need(digest(path) == PINS_SHA, 'external original receipt identity table changed')
    rows = json.loads(path.read_text())
    need(set(rows) == set(COPY_NAMES) and sum(row['bytes'] for row in rows.values()) <= MAX_COPY, 'exact bounded copy roles required')
    for name, row in rows.items():
        path = OLD/name
        value = path.lstat()
        actual = [value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns]
        need(row['path'] == str(path) and path.resolve(strict=True) == path and stat.S_ISREG(value.st_mode) and
             value.st_size == row['bytes'] <= MAX_FILE and actual == row['identity'] and digest(path) == row['sha256'],
             'original role identity/bytes changed: ' + name)
    return rows


def verify_installed(config):
    functions['verify_linked'](config)
    current_identity = checks['identity']()
    need(current_identity == json.loads((OLD/'identity-pin.json').read_text()), 'linked source/output/tool identities changed')
    protected = checks['protected']()
    need(protected == json.loads((OLD/'stage-protected-before.json').read_text()), 'retained boot/modules/default changed')
    staged = json.loads((OLD/'limited-stage.json').read_text())
    need(functions['tree_table'](Path('/lib/modules')/RELEASE) == staged['namespace'], 'installed namespace differs from exact stage')
    modules = checks['modules'](Path('/'))
    need(modules == json.loads((OLD/'install-modules-installed.json').read_text()), 'actual installed NLS identity changed')
    closure = functions['required_closure'](Path('/'))
    need(closure == staged['closure'], 'installed dependency closure differs')
    functions['verify_initrd'](Path('/boot')/('initrd.img-'+RELEASE), closure)
    linked = json.loads(Path(config['final_identity']).read_text())
    rows = []
    for prefix, name in (('vmlinuz-', 'arch/x86/boot/bzImage'), ('System.map-', 'System.map'), ('config-', '.config')):
        path = Path('/boot')/(prefix+RELEASE)
        need(path.resolve(strict=True) == path and digest(path) == linked['files'][name]['sha256'] and
             path.stat().st_size == linked['files'][name]['bytes'], 'actual installed boot bytes differ')
        rows.append({'path': str(path), 'size': path.stat().st_size, 'sha256': digest(path)})
    path = Path('/boot')/('initrd.img-'+RELEASE)
    need(path.resolve(strict=True) == path and digest(path) == staged['initrd']['sha256'] ==
         '188febc028a662326553252d4973dd3869250434c9e4202d55e543242c9e58a2' and
         path.stat().st_size == staged['initrd']['size'], 'installed initrd differs')
    rows.append({'path': str(path), 'size': path.stat().st_size, 'sha256': digest(path)})
    budget = functions['budget'](config)
    need(budget['root_free'] >= budget['needed'], 'conservative root reserve/working budget not available')
    need(digest('/boot/grub/grub.cfg') == '4cb0e54c275387c4e725b1dc3d6c69393ec98207a5ea71d1c736c227b5eb93be' and
         digest('/boot/grub/custom.cfg') == 'caae2caa937b2888237daeabf110fb70a5a6de6573f88bde1e91c40efec6a6fc',
         'actual existing menu prefix/append changed')
    return {'files': rows, 'dependencies': closure}, current_identity, budget


def copy_record(source, target, expected):
    before = source.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_FILE and digest(source) == expected, 'invalid source role')
    with source.open('rb') as src, target.open('xb') as dst:
        count = 0
        for block in iter(lambda: src.read(1048576), b''):
            count += len(block)
            need(count <= before.st_size, 'source role grew')
            dst.write(block)
        dst.flush()
        os.fsync(dst.fileno())
    after = source.lstat()
    need((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns) ==
         (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns) and count == before.st_size and
         digest(source) == digest(target) == expected, 'source/copy changed')
    return {'source': str(source), 'destination': str(target), 'bytes': count, 'sha256': expected}


def main():
    global out, record, functions, checks
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('finalize','arm'), required=True)
    parser.add_argument('--recovery', type=Path, required=True)
    parser.add_argument('--recovery-sha', required=True)
    parser.add_argument('--finalized-sha')
    args = parser.parse_args()
    need(os.geteuid() == 0, 'VM root required')
    logs = original()
    pins = origin_pins()
    need(digest(INPUT/'checks-menu.py') == CHECKS_SHA, 'reviewed menu-check correction changed')
    checks = runpy.run_path(str(INPUT/'checks-menu.py'))
    functions = runpy.run_path(str(OLD/'controller.py'))
    need(not any(name in os.environ for name in ('PYTHONPATH','PYTHONHOME','PYTHONSTARTUP','PYTHONOPTIMIZE','MAKEFLAGS',
              'MFLAGS','GCC_EXEC_PREFIX','COMPILER_PATH','LIBRARY_PATH','CPATH','C_INCLUDE_PATH')), 'unreviewed inherited override')
    before = checks['idle']()
    rec = recovery(args.recovery, args.recovery_sha)
    out = FINAL if args.phase == 'finalize' else ARM
    need(not os.path.lexists(out) and out.parent.resolve(strict=True) == BASE/'receipts', 'fresh direct-child result required')
    finalized = None
    if args.phase == 'arm':
        need(args.finalized_sha and digest(FINAL/'result.json') == args.finalized_sha, 'actual verified installed receipt required')
        finalized = json.loads((FINAL/'result.json').read_text())
        need(finalized['status'] == 'INSTALLED_BYTES_VERIFIED', 'installed-byte finalization incomplete')
    else:
        need(args.finalized_sha is None, 'unexpected arm provenance on finalization')
    out.mkdir(mode=0o700)
    config = json.loads((OLD/'configuration.json').read_text())
    g = functions['main'].__globals__
    g.update(RECEIPTS=out, PHASE=args.phase, FULL=Path(json.loads(Path(config['offroot_receipt']).read_text())['stage']['root']))
    g['EVENTS'] = (out/'journal.jsonl').open('x')
    record = {'status':'PREPARED','phase':args.phase,'old_install':str(OLD),'old_failure_sha256':OLD_HASHES['install-failure.json'],
              'original_command_logs':logs,'source_roles':pins,'corrected_checks_sha256':CHECKS_SHA,'identity_before':before,
              'recovery':rec,'commands_scope':'Metadata readers only, except one grub-reboot plus sync in arm phase.',
              'kernel_core_git_head':'0d42063ead37dc8fc1631fa56c8348890ede9c5f','kernelrelease':RELEASE,
              'module_load_performed':False,'reboot_performed':False}
    write_result()
    installed, identity, budget = verify_installed(config)
    before_grub = checks['grub'](False)
    if args.phase == 'finalize':
        origins = []
        for name, row in pins.items():
            origins.append(copy_record(OLD/name, FINAL/name, row['sha256']))
        save(FINAL/'origin-manifest.json', {'files':origins,'scope':'Byte-exact original source receipts; original failed install unchanged.'})
        installed['grub'] = before_grub
        save(FINAL/'installed-boot.json', installed)
        record.update(status='INSTALLED_BYTES_VERIFIED',installed=installed,identity=identity,budget=budget,
                      scope='Existing exact installed bytes verified after a corrected prior-menu classification. No installation or append repeated.')
    else:
        need(installed['files'] == finalized['installed']['files'] and
             installed['dependencies'] == finalized['installed']['dependencies'], 'verified installed state changed before arm')
        functions['command']('one-shot', ['grub-reboot', ENTRY], 30)
        after_grub = checks['grub'](True)
        need(before_grub['grub_cfg_sha256'] == after_grub['grub_cfg_sha256'] and
             before_grub['custom_cfg_sha256'] == after_grub['custom_cfg_sha256'] and
             {k:v for k,v in before_grub['environment'].items() if k!='next_entry'} ==
             {k:v for k,v in after_grub['environment'].items() if k!='next_entry'}, 'one-shot altered other GRUB state')
        functions['command']('sync', ['sync'], 30)
        save(ARM/'arm-grub-after-arm.json', after_grub)
        record.update(status='ARMED_ONESHOT_VERIFIED',finalized_sha256=args.finalized_sha,grub=after_grub)
    need(original() == logs and origin_pins() == pins, 'original records changed during verification')
    record['identity_after'] = checks['idle']()
    if args.phase == 'arm':
        save(ARM/'arm-complete.json', {'status':'COMPLETE','phase':'arm','reboot_performed':False,'module_load_performed':False,
                                    'finalized_sha256':args.finalized_sha,'unix_time':time.time()})
        origins=[]
        for name in ('arm-grub-after-arm.json','arm-complete.json'):
            origins.append(copy_record(ARM/name, FINAL/name, digest(ARM/name)))
        save(FINAL/'arm-origin-manifest.json', {'files':origins})
    write_result()
    g['EVENTS'].close()
    print(json.dumps({'status':record['status'],'receipt':str(out/'result.json')}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        if record is not None:
            record['status'] = 'INCOMPLETE_CHILD_RETAINED' if isinstance(error, functions['CommandObserverExpired']) else 'FAILED_OR_INCOMPLETE'
            record['error'] = repr(error)
            record['one_shot_may_be_set'] = record['phase'] == 'arm'
            write_result()
        raise
