#!/usr/bin/env python3
"""One-off read-only postboot identity proof. Preparation executes nothing.

Only fresh output receipts are written. No build, module, boot-selection or
mitigation command is present. Validation failures precede GS-proof creation.
Consumers require helper exit 0 AND result phase POSTBOOT_IDENTITY_VERIFIED;
a later receipt-I/O failure can leave an already-written proof file behind.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import stat
import struct
import subprocess
import sys
import time

BASE = Path('/mnt/kdlock-builds2/kdlock-main-kernel6-532b68a6-rwsem-04')
BUILD = BASE / 'build'
RELEASE = '7.0.0-38-kdrebuild6'
OLD_BOOT = '51b49fa4-4d99-457e-a73e-632b690eb95e'
BUILD_ID = '5ed6cd8cffed6960ce901261dfab3bb019a0442d'
UUID = 'aa0bde06-47f6-4049-aaaf-13d052e53961'
NORMAL_DEFAULT = ('gnulinux-advanced-' + UUID +
                  '>gnulinux-7.0.0-38-kdlock1-advanced-' + UUID)
CANDIDATE_ENTRY = 'kdlock-kdrebuild6-api-01'
INSTALL_RECEIPTS = BASE / 'receipts/install-kdrebuild6-api-01'
EXPECTED_CURRENT_TASK = 0xffffffff84416018
EXPECTED_PERCPU_START = 0xffffffff843fe000
EXPECTED = {
    'vmlinux': 'a05068b9dfddd7ac6fc842b44ae97e29816a43c9c5870be188b9fe71ea5b759d',
    '.config': '31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483',
    'arch/x86/boot/bzImage': 'f283c3f4af86ee23c82e28e0e248f06f5452bf10eb83c2aa8b16429b7da124fe',
    'System.map': '7853a104680d6e693d97a9eb927852376b10e27d6157adb5dedf512282dedb83',
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def signature(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def digest(path):
    path = Path(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode), 'not a regular artifact: ' + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        require(signature(os.fstat(fd)) == signature(before), 'artifact changed on open')
        value = hashlib.sha256()
        while True:
            data = os.read(fd, 1024 * 1024)
            if not data:
                break
            value.update(data)
        require(signature(os.fstat(fd)) == signature(before), 'artifact changed during hash')
        require(signature(path.lstat()) == signature(before), 'artifact path changed during hash')
        return value.hexdigest()
    finally:
        os.close(fd)


def bounded_read(path, limit):
    with open(path, 'rb') as stream:
        value = stream.read(limit + 1)
    require(len(value) <= limit, 'read exceeds explicit bound: ' + str(path))
    return value


def save(path, data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    with open(path, 'xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def save_json(path, data):
    save(path, json.dumps(data, indent=2, sort_keys=True) + '\n')


def parse_notes(data):
    """Parse the actual x86_64 ELF-note stream exposed by /sys/kernel/notes."""
    rows, offset = [], 0
    while offset < len(data):
        require(len(data) - offset >= 12, 'truncated ELF note header')
        namesz, descsz, kind = struct.unpack_from('<III', data, offset)
        start = offset + 12
        desc_start = start + ((namesz + 3) & ~3)
        end = desc_start + ((descsz + 3) & ~3)
        require(end <= len(data), 'ELF note extent exceeds actual bytes')
        name = data[start:start + namesz]
        descriptor = data[desc_start:desc_start + descsz]
        rows.append({'type': kind, 'name_hex': name.hex(), 'descriptor_hex': descriptor.hex()})
        offset = end
    ids = [row['descriptor_hex'] for row in rows
           if row['type'] == 3 and row['name_hex'] == b'GNU\0'.hex()]
    require(len(ids) == 1, 'missing or ambiguous running GNU Build ID')
    return rows, ids[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=float, required=True)
    parser.add_argument('--max-command-bytes', type=int, required=True)
    parser.add_argument('--max-notes-bytes', type=int, required=True)
    args = parser.parse_args()
    require(os.geteuid() == 0, 'run only as the designated VM root controller')
    require(isinstance(BUILD_ID, str) and re.fullmatch(r'[0-9a-f]{40}', BUILD_ID),
            'actual final kernel6 Build ID has not been pinned')
    require(all(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value)
                for value in EXPECTED.values()), 'actual final kernel6 artifacts have not been pinned')
    require(isinstance(EXPECTED_CURRENT_TASK, int) and isinstance(EXPECTED_PERCPU_START, int),
            'actual new kernel6 GS and per-CPU linkage have not been pinned')
    require(math.isfinite(args.timeout) and args.timeout > 0, 'invalid command timeout')
    require(args.max_command_bytes > 0 and args.max_notes_bytes > 0, 'invalid byte bounds')
    output = args.output.resolve()
    require(output.parent == BASE/'receipts', 'fresh output must be a direct child of candidate receipts')
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    report = {'phase': 'COLLECTING', 'source_commit': '532b68a65bdf96504e2cede6c23a5bc1476d94e9',
              'started_unix': time.time(), 'commands': [], 'checks': {}}

    def run(label, argv):
        executable = shutil.which(argv[0], path='/usr/sbin:/usr/bin:/sbin:/bin')
        require(executable is not None, 'missing read-only tool: ' + argv[0])
        actual = [executable] + argv[1:]
        path = output / (label + '.txt')

        def file_bound():
            resource.setrlimit(resource.RLIMIT_FSIZE, (args.max_command_bytes, args.max_command_bytes))

        with path.open('xb') as stream:
            proc = subprocess.Popen(actual, stdout=stream, stderr=subprocess.STDOUT,
                                    env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C',
                                         'LANG': 'C', 'LANGUAGE': 'C'},
                                    start_new_session=True, preexec_fn=file_bound)
            try:
                code = proc.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    killed_code = proc.wait(timeout=args.timeout)
                except subprocess.TimeoutExpired:
                    report['commands'].append({'argv': actual, 'pid': proc.pid, 'timed_out': True,
                                               'post_kill_reap_timed_out': True,
                                               'output': path.name, 'drain_established': False})
                    raise RuntimeError('read-only child remains outstanding after bounded kill/reap: ' + label)
                report['commands'].append({'argv': actual, 'pid': proc.pid, 'timed_out': True,
                                           'returncode': killed_code, 'output': path.name})
                raise RuntimeError('read-only command timed out: ' + label)
            stream.flush()
            os.fsync(stream.fileno())
        report['commands'].append({'argv': actual, 'returncode': code, 'output': path.name,
                                   'sha256': digest(path)})
        require(code == 0, 'read-only command failed: ' + label)
        return bounded_read(path, args.max_command_bytes).decode('utf-8', errors='strict')

    try:
        uname = list(os.uname())
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        taint = Path('/proc/sys/kernel/tainted').read_text().strip()
        cmdline = bounded_read('/proc/cmdline', args.max_command_bytes).decode().strip()
        modules = bounded_read('/proc/modules', args.max_command_bytes).decode()
        cpuinfo = bounded_read('/proc/cpuinfo', args.max_command_bytes).decode()
        report.update(uname=uname, boot_id=boot, tainted=taint, cmdline=cmdline)
        save_json(output / 'uname.json', uname)
        save(output / 'cmdline.txt', cmdline + '\n')
        save(output / 'modules.txt', modules)
        save(output / 'cpuinfo.txt', cpuinfo)
        run('boot-kernel-journal', ['journalctl', '-b', '-k', '--no-pager', '-o', 'short-monotonic'])
        run('dmesg', ['dmesg', '--color=never'])
        require(uname[2] == RELEASE and uname[4] == 'x86_64', 'wrong running release/architecture')
        require(boot != OLD_BOOT, 'boot ID did not change from the earlier kernel')
        require(taint == '0', 'running kernel is tainted')
        require('nokaslr' in cmdline.split(), 'actual command line lacks nokaslr')
        names = [line.split()[0].lower() for line in modules.splitlines()]
        require(set(names) <= {'nls_iso8859_1'}, 'running candidate modules exceed the exact rebuilt NLS closure')
        require(not any(name.startswith(('kd_', 'kdlock', 'komb', 'tclock')) for name in names),
                'KD/fixture module already loaded before postboot proof')
        flags = []
        for block in cpuinfo.split('\n\n'):
            row = dict(line.split(':', 1) for line in block.splitlines() if ':' in line)
            row = {key.strip(): value.strip() for key, value in row.items()}
            if 'processor' in row:
                require('flags' in row, 'CPU has no exported flag row')
                flags.append({'processor': row['processor'], 'flags': row['flags'].split()})
        require(bool(flags), 'no CPU flag rows')
        vulnerabilities = {}
        for name in ('retbleed', 'indirect_target_selection', 'spectre_v2'):
            path = Path('/sys/devices/system/cpu/vulnerabilities') / name
            vulnerabilities[name] = bounded_read(path, args.max_command_bytes).decode().strip() if path.exists() else None
        report.update(cpu_flag_rows=flags, vulnerabilities=vulnerabilities)
        report['call_depth_observation'] = {
            'flag_present': any('call_depth' in row['flags'] for row in flags),
            'scope': 'Public CPU flags/sysfs only; the runtime cpu_feature_enabled guard is authoritative for admission.',
        }
        require(not any('call_depth' in row['flags'] for row in flags), 'active call_depth flag')
        require('stuffing' not in (vulnerabilities['retbleed'] or '').lower(),
                'active retbleed call-depth stuffing reported')
        notes = bounded_read('/sys/kernel/notes', args.max_notes_bytes)
        save(output / 'running-kernel-notes.bin', notes)
        parsed, running_id = parse_notes(notes)
        report.update(running_notes=parsed, running_build_id=running_id)
        require(running_id == BUILD_ID, 'running GNU Build ID differs from final kernel ELF')
        hashes = {name: digest(BUILD / name) for name in EXPECTED}
        report['artifact_sha256'] = hashes
        require(hashes == EXPECTED, 'retained final artifact hash mismatch')
        require(digest('/boot/vmlinuz-' + RELEASE) == EXPECTED['arch/x86/boot/bzImage'],
                'installed image differs from final bzImage')
        require(digest('/boot/config-' + RELEASE) == EXPECTED['.config'],
                'installed configuration differs from final configuration')
        elf_notes = run('vmlinux-notes', ['readelf', '-n', str(BUILD / 'vmlinux')])
        require(re.findall(r'Build ID: ([0-9a-f]+)', elf_notes) == [BUILD_ID], 'ELF Build ID mismatch')
        symbols = run('vmlinux-symbols', ['nm', '-n', str(BUILD / 'vmlinux')])
        gs = {}
        for name in ('current_task', 'const_current_task', '__per_cpu_start'):
            matches = re.findall(r'^([0-9a-fA-F]+)\s+\S\s+' + re.escape(name) + r'$', symbols, re.M)
            require(len(matches) == 1, 'missing or ambiguous actual ELF symbol: ' + name)
            gs[name] = int(matches[0], 16)
        sections = run('vmlinux-sections', ['readelf', '-SW', str(BUILD / 'vmlinux')])
        match = re.findall(r'\]\s+\.data\.\.percpu\s+PROGBITS\s+([0-9a-fA-F]+)', sections)
        require(len(match) == 1, 'missing/ambiguous actual per-CPU section')
        percpu_va = int(match[0], 16)
        require(gs['current_task'] == gs['const_current_task'] == EXPECTED_CURRENT_TASK,
                'actual full linked current_task/alias differs')
        require(percpu_va == gs['__per_cpu_start'] == EXPECTED_PERCPU_START,
                'actual per-CPU section/start differs')
        report.update(gs_symbols=gs, percpu_section_va=percpu_va)
        grub = bounded_read('/boot/grub/grub.cfg', args.max_command_bytes).decode()
        save(output / 'grub.cfg', grub)
        environment = run('grub-environment', ['grub-editenv', '/boot/grub/grubenv', 'list'])
        env = dict(line.split('=', 1) for line in environment.splitlines() if '=' in line)
        arm_raw = bounded_read(INSTALL_RECEIPTS / 'arm-complete.json', args.max_command_bytes)
        armed_raw = bounded_read(INSTALL_RECEIPTS / 'arm-grub-after-arm.json', args.max_command_bytes)
        arm, armed = json.loads(arm_raw), json.loads(armed_raw)
        save(output / 'prior-arm-complete.json', arm_raw)
        save(output / 'prior-armed-grub.json', armed_raw)
        require(arm.get('status') == 'COMPLETE' and arm.get('phase') == 'arm', 'missing completed prior arm')
        require(armed.get('environment', {}).get('next_entry') == CANDIDATE_ENTRY,
                'prior armed receipt does not name the exact candidate')
        grub_sha256 = hashlib.sha256(grub.encode()).hexdigest()
        require(armed.get('grub_cfg_sha256') == grub_sha256 and
                armed.get('normal_default') == NORMAL_DEFAULT,
                'GRUB configuration/default differs from the exact prior arm')
        custom_raw = bounded_read('/boot/grub/custom.cfg', args.max_command_bytes)
        prefix_raw = bounded_read(INSTALL_RECEIPTS/'custom.cfg-before', args.max_command_bytes)
        append_raw = bounded_read(INSTALL_RECEIPTS/'candidate-entry.cfg', args.max_command_bytes)
        menu_raw = bounded_read(INSTALL_RECEIPTS/'stage-grub-sources.json', args.max_command_bytes)
        menu = json.loads(menu_raw)
        custom_sha = hashlib.sha256(custom_raw).hexdigest()
        require(menu['candidate_entry'] == CANDIDATE_ENTRY and
                menu['grub_cfg_sha256'] == grub_sha256 and
                hashlib.sha256(prefix_raw).hexdigest() == menu['custom_cfg_before_sha256'] and
                len(prefix_raw) == menu['custom_cfg_before_size'] and
                hashlib.sha256(append_raw).hexdigest() == menu['append_sha256'] and
                custom_raw == prefix_raw + append_raw and
                custom_sha == menu['custom_cfg_after_sha256'] == armed.get('custom_cfg_sha256'),
                'old custom menu prefix or exact candidate append changed')
        save(output/'custom.cfg', custom_raw)
        save(output/'prior-menu-sources.json', menu_raw)
        protected_raw = bounded_read(INSTALL_RECEIPTS / 'stage-protected-before.json',
                                     args.max_command_bytes)
        protected = json.loads(protected_raw)
        required_boot = {str(Path('/boot') / (prefix + release))
                         for release in ('7.0.0-38-kdlock1', '6.1.159-kdclobber2')
                         for prefix in ('vmlinuz-', 'System.map-', 'config-', 'initrd.img-')}
        old_boot = [row for row in protected['files'] if row['path'] in required_boot]
        require(len(old_boot) == len(required_boot) and
                {row['path'] for row in old_boot} == required_boot,
                'normal/recovery boot snapshot is incomplete or duplicated')
        for row in old_boot:
            path = Path(row['path'])
            value = path.lstat()
            require('symlink' not in row and stat.S_ISREG(value.st_mode) and
                    stat.S_IMODE(value.st_mode) == row['mode'] and
                    value.st_size == row['size'] and digest(path) == row['sha256'],
                    'normal/recovery boot file changed: ' + row['path'])
        previous_releases = tuple('7.0.0-38-kdrebuild' + str(number) for number in range(1, 6))
        previous_names = {str(Path('/boot') / (prefix + release))
                          for release in previous_releases
                          for prefix in ('vmlinuz-', 'System.map-', 'config-', 'initrd.img-')}
        previous_rows = [row for row in protected['files'] if row['path'] in previous_names]
        require(len(previous_rows) == len(previous_names) and
                {row['path'] for row in previous_rows} == previous_names,
                'prior candidate boot snapshot is incomplete or duplicated')
        for row in previous_rows:
            path = Path(row['path'])
            metadata = path.lstat()
            require(stat.S_ISREG(metadata.st_mode) and metadata.st_size == row['size'] and
                    stat.S_IMODE(metadata.st_mode) == row['mode'] and digest(path) == row['sha256'],
                    'prior candidate boot file changed: ' + row['path'])
        require(all((Path('/lib/modules') / release).is_dir() for release in previous_releases),
                'prior candidate installed module namespace missing')
        save_json(output / 'prior-candidate-boot-unchanged.json', {
            'files': previous_rows,
            'scope': 'Twenty exact prior candidate boot files. Installer separately verified protected modules before arm.'})
        installed = json.loads((INSTALL_RECEIPTS / 'installed-boot.json').read_text())
        expected_initrd = '/boot/initrd.img-' + RELEASE
        initrds = [row for row in installed['files'] if row['path'] == expected_initrd]
        require(len(initrds) == 1 and Path(expected_initrd).stat().st_size == initrds[0]['size'] and
                digest(expected_initrd) == initrds[0]['sha256'], 'candidate initramfs differs from install')
        installed_modules_raw = bounded_read(INSTALL_RECEIPTS/'install-modules-installed.json',
                                              args.max_command_bytes)
        installed_modules = json.loads(installed_modules_raw)
        expected_module = '/lib/modules/' + RELEASE + '/kernel/fs/nls/nls_iso8859-1.ko'
        module_rows = installed_modules['modules']
        require(installed_modules['count'] == installed_modules['signed'] == len(module_rows) == 1 and
                installed_modules['unsigned'] == 0 and module_rows[0]['path'] == expected_module and
                module_rows[0]['vermagic'].split()[0] == RELEASE and module_rows[0]['signer'] and
                module_rows[0]['sig_hashalgo'] and module_rows[0]['sig_key'],
                'exact signed installed NLS module receipt differs')
        module_row = module_rows[0]
        require(Path(expected_module).stat().st_size == module_row['size'] and
                digest(expected_module) == module_row['sha256'], 'installed rebuilt NLS module bytes changed')
        require(run('installed-nls-vermagic', ['modinfo', '-F', 'vermagic', expected_module]).strip() ==
                module_row['vermagic'], 'installed rebuilt NLS vermagic differs')
        save(output/'installed-nls-receipt.json', installed_modules_raw)
        for target in ('/', '/boot/efi', '/mnt/kdlock-builds', '/mnt/kdlock-builds2'):
            mount = run('mount-' + (target.strip('/').replace('/', '-') or 'root'),
                        ['findmnt', '-M', target, '-rn', '-o', 'TARGET,SOURCE,FSTYPE']).split()
            require(len(mount) == 3 and mount[0] == target and mount[2] ==
                    ('vfat' if target == '/boot/efi' else 'ext4'), 'required VM mount missing: ' + target)
        require(run('ssh-service', ['systemctl', 'is-active', 'ssh.service']).strip() == 'active',
                'SSH service is inactive in candidate boot')
        require(Path('/lib/modules/7.0.0-38-kdlock1').is_dir() and
                Path('/lib/modules/6.1.159-kdclobber2').is_dir(),
                'normal/recovery installed module namespace missing')
        save_json(output / 'normal-recovery-boot-unchanged.json', {
            'files': old_boot, 'stage_snapshot_sha256': hashlib.sha256(protected_raw).hexdigest(),
            'scope': 'Eight exact normal/recovery boot files rehashed here; the installer verified all protected module files before arm.'})
        report['normal_recovery'] = {'boot_files_unchanged': len(old_boot),
                                    'module_namespaces_present': True,
                                    'stage_snapshot_sha256': hashlib.sha256(protected_raw).hexdigest()}
        require(not env.get('next_entry') and not env.get('prev_saved_entry'), 'one-shot GRUB selection not consumed')
        require('set default="' + NORMAL_DEFAULT + '"' in grub, 'normal GRUB default no longer pinned')
        report['grub'] = {'environment': env, 'normal_default': NORMAL_DEFAULT,
                          'prior_next_entry': CANDIDATE_ENTRY, 'one_shot_consumed': True,
                          'configuration_sha256': grub_sha256, 'custom_cfg_sha256': custom_sha,
                          'old_custom_prefix_sha256': menu['custom_cfg_before_sha256'],
                          'old_custom_prefix_preserved': True}
        require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot, 'boot changed during proof')
        require(Path('/proc/sys/kernel/tainted').read_text().strip() == '0', 'taint changed during proof')
        require(Path('/proc/modules').read_text() == modules, 'module set changed during proof')
        proof = {'verified_for_running_kernel': True, 'kernel_release': RELEASE,
                 'boot_id': boot, 'build_id': running_id, 'gs_symbol': 'current_task',
                 'current_task_gs_offset': hex(gs['current_task']),
                 'const_current_task': hex(gs['const_current_task']),
                 'percpu_section_va': hex(percpu_va), 'kaslr_disabled': True,
                 'kernel_elf_sha256': hashes['vmlinux'], 'kernel_config_sha256': hashes['.config'],
                 'scope': 'Exact linked/running kernel identity and full GS symbol input; fixture GS relocation and execution remain separate.'}
        save_json(output / 'gs-proof.json', proof)
        report['phase'] = 'POSTBOOT_IDENTITY_VERIFIED'
    except BaseException as error:
        report.update(phase='FAILED_RETAIN_OUTPUT', error=repr(error))
        save_json(output / 'result.json', report)
        raise
    save_json(output / 'result.json', report)
    fd = os.open(output, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    print(json.dumps({'phase': report['phase'], 'output': str(output), 'boot_id': report['boot_id']}))


if __name__ == '__main__':
    main()
