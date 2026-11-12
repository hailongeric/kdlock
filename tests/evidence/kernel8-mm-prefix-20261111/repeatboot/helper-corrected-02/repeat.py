#!/usr/bin/env python3
"""Separate kernel8 repeat preflight, one-shot arm and fresh postboot proof.

This helper never reboots, installs, builds, loads modules or changes tracing.
It preserves the original install arm and adds an independent repeat binding.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import resource
import runpy
import shutil
import stat
import subprocess
import time

KERNEL = Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01')
FIXTURES = Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
INPUT = KERNEL/'receipts/repeat-kdrebuild8-mm-input-02'
OUTPUT = KERNEL/'receipts/repeat-kdrebuild8-mm-frontier-01'
POSTOUT = KERNEL/'receipts/postboot-kdrebuild8-mm-frontier-01'
OLD_INSTALL = KERNEL/'receipts/install-kdrebuild8-finalize-01'
INSTALL_INPUT = Path('/mnt/kdlock-builds2/kdlock-main-kernel8-input-0d42063e-01/install-finalize-helpers-01')
OLD_BOOT = 'e001a3d2-3fcc-4e89-80ec-9187eb8ddfa0'
RELEASE = '7.0.0-38-kdrebuild8'
BUILD_ID = 'a33dd4d11d0f0c6649107507e685b6e86e716c1a'
ENTRY = 'kdlock-kdrebuild8-api-01'
DEFAULT = ('gnulinux-advanced-aa0bde06-47f6-4049-aaaf-13d052e53961>'
           'gnulinux-7.0.0-38-kdlock1-advanced-aa0bde06-47f6-4049-aaaf-13d052e53961')
PLAN_SHA = '35f093be246a4959e4e495d4e3e96d54dd9324257c27ad661881e7d1831b5ae9'
REFERENCE_SHA = '759208ec01cb280364a8a558bae8e49cdaec88733f5bd72f342d91697268516d'
POST_SHA = '7ba6bd53f6d281715f21dfdb11280cde751fc3bb6a471f5f33f40274c32146a7'
MENU_SHA = '2610bc0c19dafc9ccf87b56dd85802ac4f22d0dce2ac1b9ae6d0dd4c3cb8ecab'
MAX_JSON = 4*1024**2
MAX_COMMAND = 32*1024**2
record = None
phase_out = None
deadline = None
command_number = 0


def need(value, message):
    if not value:
        raise RuntimeError(message)


def signature(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def facts(path, limit):
    path = Path(path)
    before = path.lstat()
    need(path.resolve(strict=True) == path and stat.S_ISREG(before.st_mode)
         and before.st_size <= limit, 'strict regular/canonical extent differs: ' + str(path))
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    value = hashlib.sha256()
    try:
        need(signature(os.fstat(descriptor)) == signature(before), 'input changed on open')
        for block in iter(lambda: os.read(descriptor, 1048576), b''):
            value.update(block)
        need(signature(os.fstat(descriptor)) == signature(before)
             and signature(path.lstat()) == signature(before), 'input changed while hashing')
    finally:
        os.close(descriptor)
    return {'path': str(path), 'bytes': before.st_size, 'sha256': value.hexdigest()}


def checked_json(path, expected):
    row = facts(path, MAX_JSON)
    need(row['sha256'] == expected, 'exact receipt differs: ' + str(path))
    return json.loads(Path(path).read_bytes())


def helper(path, expected):
    need(facts(path, 1048576)['sha256'] == expected, 'reviewed helper differs: ' + str(path))
    return runpy.run_path(str(path))


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def save(path, value):
    data = value if isinstance(value, bytes) else (json.dumps(value, indent=2, sort_keys=True)+'\n').encode()
    with Path(path).open('xb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    sync_directory(Path(path).parent)


def update():
    temporary = phase_out/'.result-new'
    save(temporary, record)
    os.replace(temporary, phase_out/'result.json')
    sync_directory(phase_out)


def command(label, argv, seconds):
    global command_number
    need(time.monotonic() < deadline, 'phase deadline expired before command dispatch')
    executable = shutil.which(str(argv[0]), path='/usr/sbin:/usr/bin:/sbin:/bin')
    need(executable is not None, 'required operation tool absent')
    alias = Path(executable)
    actual = [str(alias)] + list(map(str, argv[1:]))
    resolved = alias.resolve(strict=True)
    row = {'label': label, 'argv': actual, 'tool': facts(resolved, 32*1024**2),
           'tool_alias': str(alias), 'started_unix': time.time()}
    log = phase_out/f'{command_number:02d}-{label}.log'
    command_number += 1
    record['commands'].append(row)
    update()

    def file_limit():
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_COMMAND, MAX_COMMAND))

    with log.open('xb') as stream:
        child = subprocess.Popen(actual, stdin=subprocess.DEVNULL, stdout=stream,
                                 stderr=subprocess.STDOUT, start_new_session=True,
                                 preexec_fn=file_limit,
                                 env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
        row['pid'] = child.pid
        update()
        try:
            remaining = min(seconds, deadline-time.monotonic())
            if remaining <= 0:
                raise subprocess.TimeoutExpired(actual, seconds)
            code = child.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            row.update(status='OBSERVER_EXPIRED_CHILD_RETAINED', log=str(log))
            record['status'] = 'INCOMPLETE_CHILD_RETAINED'
            update()
            raise
        stream.flush(); os.fsync(stream.fileno())
    row.update(returncode=code, elapsed_seconds=time.time()-row['started_unix'],
               log=facts(log, MAX_COMMAND))
    update()
    need(code == 0, 'operation failed without automatic retry: ' + label)
    return log.read_text()


def recovery(path, expected):
    value = checked_json(path, expected)
    age = time.time()-datetime.datetime.fromisoformat(value['utc']).timestamp()
    need(0 <= age <= 900 and value['hostname'] == 'Super-Server'
         and value['pid'] == 257489 and value['exe'] == '/usr/bin/qemu-system-x86_64',
         'fresh exact QEMU recovery observation required')
    wanted = {'/home/eric/vm/qemu-disks/ubuntu22.04.img', '/home/eric/vm/qemu-disks/sda.qcow2',
              '/home/eric/vm/qemu-disks/kdlock-builds2-20261031/builds.qcow2'}
    need(len(value['images']) == 3 and {row['path'] for row in value['images']} == wanted
         and all(row['open_fds'] and row['path'] == row['realpath']
                 and row['host_available'] >= 8*1024**3 for row in value['images']),
         'three attached image references or host floor differ')
    replies = {row['command']: row['output'] for row in value['hmp']}
    need(len(replies) == len(value['hmp']) and 'VM status: running' in replies['info status'],
         'actual QEMU running state differs')
    common = replies['info snapshots'].split('List of snapshots present on all disks:', 1)[1].split('List of partial', 1)[0]
    need(any('kdlock-builddisk-clean-20261031' in line.split() for line in common.splitlines()),
         'complete three-disk recovery point absent')
    return {'path': str(path), 'sha256': expected, 'utc': value['utc']}


def installed():
    final = checked_json(OLD_INSTALL/'result.json',
                         '21980a9b699e13733f584efc9665e89aa2e37e233cfa24cc7ce0e4925bc0e5bc')
    need(final['status'] == 'INSTALLED_BYTES_VERIFIED', 'original installed-byte verification differs')
    boot = checked_json(OLD_INSTALL/'installed-boot.json',
                        'f53772dc4f7a1f6da5122cabd3ad27d6288e154d62eefa1a3eb178494c845449')
    limited = checked_json(OLD_INSTALL/'limited-stage.json',
                           '0f6805ef4a6127f1066a37718dc3a6f14a28130f57c3c1a86124ec3f05bd19a7')
    for row in boot['files']:
        current = facts(row['path'], 64*1024**2)
        need(current['bytes'] == row['size'] and current['sha256'] == row['sha256'],
             'installed candidate boot bytes differ')
    root = (Path('/lib/modules')/RELEASE).resolve(strict=True)
    need(root == Path('/usr/lib/modules')/RELEASE, 'verified usr-merged module root differs')
    names = set()
    for row in limited['namespace']:
        path = root/row['name']; current = facts(path, 2*1024**2)
        need(current['bytes'] == row['size'] and current['sha256'] == row['sha256']
             and stat.S_IMODE(path.lstat().st_mode) == row['mode'],
             'installed limited namespace differs: ' + row['name'])
        names.add(row['name'])
    actual = {path.relative_to(root).as_posix() for path in root.rglob('*')
              if path.is_file() or path.is_symlink()}
    need(actual == names and len(names) == 16, 'installed candidate namespace membership differs')
    return {'boot_files': boot['files'], 'limited_namespace': limited['namespace']}


def main():
    global phase_out, record, deadline
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('preflight', 'arm', 'postproof'), required=True)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--helper-sha256', required=True)
    parser.add_argument('--recovery-sha256')
    parser.add_argument('--preflight-sha256')
    parser.add_argument('--arm-sha256')
    args = parser.parse_args()
    need(os.geteuid() == 0 and args.plan_sha256 == PLAN_SHA
         and Path(__file__) == INPUT/'repeat.py'
         and facts(Path(__file__), 1048576)['sha256'] == args.helper_sha256,
         'VM root and exact staged helper/plan required')
    plan = checked_json(INPUT/'plan.json', PLAN_SHA)
    reference = checked_json(INPUT/'reference-state.json', REFERENCE_SHA)
    ns = helper(FIXTURES/'transport/build.py',
                '56f289a956e6ac301afe41321a5de7f41c18c8bee119881e4bad1a72733922cb')
    native = helper(FIXTURES/'native-api-input-01/controller.py',
                    '2c2082e0bf7c807819ec7e28f744c34aaa94f38aa07faf5be1a197b1baced074')
    k = helper(FIXTURES/'managed-killable-input-04/controller.py',
               'd760565b7ca37b1ed5cd3a8404ca8e4448e4203050e9007e467737bd1ee6789d')
    menu = helper(INSTALL_INPUT/'checks-menu.py', MENU_SHA)
    need(facts(INSTALL_INPUT/'postboot.py', 1048576)['sha256'] == POST_SHA,
         'unchanged postboot helper required')
    ns['environment']()
    need(not any(name in os.environ for name in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP',
              'PYTHONOPTIMIZE', 'LD_PRELOAD', 'LD_LIBRARY_PATH', 'GCC_EXEC_PREFIX',
              'COMPILER_PATH', 'LIBRARY_PATH', 'CPATH', 'C_INCLUDE_PATH')), 'inherited override refused')
    before_idle = k['idle'](native)
    before_id = before_idle['identity']
    need(before_id['release'] == RELEASE and native['running_notes']()[1] == BUILD_ID,
         'actual candidate release/Build ID differs')
    need({line.split()[0] for line in before_idle['modules'].splitlines()} == {'nls_iso8859_1'},
         'exact rebuilt NLS module set required')
    if args.phase == 'postproof':
        need(before_id['boot'] != OLD_BOOT and before_id['taint'] == 0,
             'independent new boot and taint0 required before postproof')
    else:
        need(before_id == {'boot': OLD_BOOT, 'release': RELEASE, 'taint': 4096},
             'exact prior e001/4096 boot required')
    built = checked_json(KERNEL/'receipts/full-01/result.json',
                         '024f19157ed85228fc9dccde8009936b25def135b3f0cd1c77c6204c68e57ba5')
    focused = checked_json(Path(built['focused_receipt']), built['focused_sha256'])
    linked = checked_json(KERNEL/'receipts/full-01/final-identity.json', built['final_identity_sha256'])
    pins = {name: row['sha256'] for name, row in linked['files'].items()}

    def preserved():
        result = {'linked16': ns['pins'](KERNEL/'build', pins),
                  'source': ns['source_pins'](focused, KERNEL/'source'),
                  'protected': ns['protected'](focused), 'boot': ns['boot_files'](),
                  'installed': installed()}
        need(len(result['linked16']) == 16 and len(focused['package_after']) == 78
             and result['source'] == built['source_after']
             and result['protected'] == built['protected_after'], 'kernel/source/protected state differs')
        boot = {name: row for name, row in result['boot'].items() if name != '/boot/grub/grubenv'}
        expected = {name: row for name, row in reference['boot_files'].items() if name != '/boot/grub/grubenv'}
        need(boot == expected, 'protected boot files/namespaces changed')
        return result

    evidence = {
        'managed-killable-receipts-04/result.json': 'd7b47fa9e366f666d577b906189e5ca806da2ac769692de380884d89c325f488',
        'managed-killable-live-03/result.json': '56dcf7cfa9e75645d0ab56cb61809550639119ee0701db84af05c34da302005a',
        'recovery-killable-final-01/result.json': '40872340905c520739493208ba84323e3f16b6aed40e7119cefc08bf8f5fd1f0',
        'mm-provider-context-build-de76da8a-01/receipts/result.json': '21d6d90b4d2c91ab2760a0319d5eef8933148ab6452cf1a3f523d2b98b8c63cf',
        'mm-provider-ioctl-build-0798c1ab-01/receipts/result.json': '73f57b2690b98c442160b576b757429a0090674f75f6eeafb60d7499ac473052',
    }
    for name, expected in evidence.items():
        checked_json(FIXTURES/name, expected)
    before_pins = preserved()
    if args.phase == 'preflight':
        need(before_pins['boot'] == reference['boot_files'],
             'exact reference boot/GRUB state changed before preflight')
    need(ns['available']('/') >= 1024**3 and ns['available'](KERNEL) >= 4*1024**3,
         'explicit root/build headroom floor not met')
    prior_preflight = prior_arm = None
    if args.phase != 'postproof':
        need(args.recovery_sha256 is not None, 'fresh recovery SHA required')
        recovered = recovery(INPUT/'recovery.json', args.recovery_sha256)
    else:
        need(args.recovery_sha256 is None, 'postproof binds prior fresh arm proof, not a stale new observation')
        recovered = None
    if args.phase == 'preflight':
        need(args.preflight_sha256 is None and args.arm_sha256 is None and not os.path.lexists(OUTPUT),
             'fresh preflight only; no receipt reuse')
        OUTPUT.mkdir(mode=0o700)
    else:
        need(args.preflight_sha256 is not None, 'exact completed preflight SHA required')
        prior_preflight = checked_json(OUTPUT/'preflight/result.json', args.preflight_sha256)
        need(prior_preflight['status'] == 'REPEAT_PREFLIGHT_COMPLETE'
             and prior_preflight['helper_sha256'] == args.helper_sha256,
             'completed same-helper preflight required')
        if args.phase == 'postproof':
            need(args.arm_sha256 is not None, 'exact actual arm SHA required')
            prior_arm = checked_json(OUTPUT/'arm/result.json', args.arm_sha256)
            need(prior_arm['status'] == 'REPEAT_ONESHOT_ARM_COMPLETE'
                 and prior_arm['preflight_sha256'] == args.preflight_sha256
                 and prior_arm['grub_after']['environment']['next_entry'] == ENTRY,
                 'actual repeat one-shot arm required')
        else:
            need(args.arm_sha256 is None, 'unexpected arm SHA before arm execution')
    phase_out = OUTPUT/args.phase
    need(not os.path.lexists(phase_out), 'fresh separate phase leaf required')
    phase_out.mkdir(mode=0o700)
    deadline = time.monotonic()+({'preflight': 180, 'arm': 240, 'postproof': 300}[args.phase])
    record = {'status': 'PREPARED', 'phase': args.phase, 'helper_sha256': args.helper_sha256,
              'plan_sha256': PLAN_SHA, 'reference_sha256': REFERENCE_SHA, 'identity_before': before_idle,
              'recovery': recovered, 'preflight_sha256': args.preflight_sha256,
              'arm_sha256': args.arm_sha256, 'pins_before': before_pins, 'commands': [],
              'reboot_performed': False, 'module_load_performed': False, 'one_shot_may_be_set': False,
              'scope': 'Separate repeat boot identity control; no MM runtime or native-context equivalence claim.'}
    update()

    def menu_state(armed):
        def menu_run(argv, seconds=30):
            return command('menu-read', argv, min(30, seconds))
        menu['grub'].__globals__['run'] = menu_run
        value = menu['grub'](armed)
        need(value['normal_default'] == DEFAULT and value['candidate_entry'] == ENTRY,
             'normal persistent default or exact candidate differs')
        return value

    before_grub = menu_state(False)
    record['grub_before'] = before_grub
    if args.phase == 'arm':
        need(before_grub == prior_preflight['grub_after'] and before_pins == prior_preflight['pins_after']
             and before_idle == prior_preflight['identity_after'], 'preflight state changed before arm')
        record['one_shot_may_be_set'] = True
        update()
        command('one-shot', ['/usr/sbin/grub-reboot', ENTRY], 30)
        after_grub = menu_state(True)
        need({k: v for k, v in after_grub.items() if k != 'environment'} ==
             {k: v for k, v in before_grub.items() if k != 'environment'}
             and {k: v for k, v in after_grub['environment'].items() if k != 'next_entry'} ==
             {k: v for k, v in before_grub['environment'].items() if k != 'next_entry'},
             'one-shot changed any other GRUB field')
        command('sync', ['/usr/bin/sync'], 30)
        record['grub_after'] = after_grub
        status = 'REPEAT_ONESHOT_ARM_COMPLETE'
    elif args.phase == 'postproof':
        need(not os.path.lexists(POSTOUT), 'fresh postboot helper output required')
        expected_other = {k: v for k, v in prior_arm['grub_after']['environment'].items() if k != 'next_entry'}
        need({k: v for k, v in before_grub['environment'].items() if k != 'next_entry'} == expected_other,
             'non-next-entry GRUB environment changed across reboot')
        argv = plan['postboot']['argv']
        need(argv[2] == str(INSTALL_INPUT/'postboot.py') and argv[4] == str(POSTOUT),
             'exact unchanged postboot helper and fresh output required')
        command('postboot-proof', argv, 240)
        post = json.loads((POSTOUT/'result.json').read_bytes())
        gs = json.loads((POSTOUT/'gs-proof.json').read_bytes())
        need(post['phase'] == 'POSTBOOT_IDENTITY_VERIFIED' and post['boot_id'] == before_id['boot']
             and post['tainted'] == '0' and post['running_build_id'] == BUILD_ID,
             'actual successful fresh postboot receipt differs')
        need(gs['verified_for_running_kernel'] is True and gs['boot_id'] == before_id['boot']
             and gs['kernel_release'] == RELEASE and gs['build_id'] == BUILD_ID
             and gs['kernel_elf_sha256'] == pins['vmlinux'] and gs['kernel_config_sha256'] == pins['.config']
             and gs['current_task_gs_offset'] == gs['const_current_task'] == '0xffffffff84425018'
             and gs['percpu_section_va'] == '0xffffffff8440d000', 'fresh exact GS proof differs')
        record['postboot_result'] = facts(POSTOUT/'result.json', MAX_JSON)
        record['gs_proof'] = facts(POSTOUT/'gs-proof.json', MAX_JSON)
        record['repeat_binding'] = {'old_boot': OLD_BOOT, 'new_boot': before_id['boot'],
                                    'arm_sha256': args.arm_sha256, 'candidate_entry': ENTRY,
                                    'consumed_next_entry': before_grub['environment'].get('next_entry', '') == '',
                                    'normal_default': DEFAULT,
                                    'original_install_arm_is_separate_historical_evidence': True}
        record['grub_after'] = menu_state(False)
        status = 'REPEAT_POSTBOOT_IDENTITY_COMPLETE'
    else:
        record['grub_after'] = before_grub
        status = 'REPEAT_PREFLIGHT_COMPLETE'
    after_pins = preserved()
    need({k: v for k, v in after_pins.items() if k != 'boot'} ==
         {k: v for k, v in before_pins.items() if k != 'boot'}, 'protected state changed within phase')
    if args.phase != 'arm':
        need(after_pins == before_pins, 'boot fields changed within read-only phase')
    after_idle = k['idle'](native)
    need(after_idle == before_idle and native['running_notes']()[1] == BUILD_ID,
         'actual same phase identity/idle changed')
    for name, expected in evidence.items():
        checked_json(FIXTURES/name, expected)
    need(facts(INSTALL_INPUT/'postboot.py', 1048576)['sha256'] == POST_SHA
         and facts(INSTALL_INPUT/'checks-menu.py', 1048576)['sha256'] == MENU_SHA
         and facts(Path(__file__), 1048576)['sha256'] == args.helper_sha256,
         'frozen helpers changed')
    need(time.monotonic() <= deadline, 'phase elapsed bound expired during final proof')
    record.update(status=status, pins_after=after_pins, identity_after=after_idle,
                  free_root_bytes=ns['available']('/'), free_build_bytes=ns['available'](KERNEL))
    update()
    print(json.dumps({'status': status, 'receipt': str(phase_out/'result.json')}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        if record is not None:
            record['error'] = repr(error)
            if record['status'] != 'INCOMPLETE_CHILD_RETAINED':
                record['status'] = 'FAILED_OR_INCOMPLETE'
            update()
        raise
