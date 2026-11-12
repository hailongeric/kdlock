#!/usr/bin/env python3
"""VM-only independent kernel9 changed-object, bzImage and one-NLS build.
No installer reapply, installation, boot or test. Observer refusal retains the
child/session/logs without signals and does not prove drain.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import time

RELEASE = '7.0.0-38-kdrebuild9'
CORE = '6e486ecec398111fb5d5e30ffc76495f32f557b7'
NLS = 'fs/nls/nls_iso8859-1.ko'
ORDER = b'fs/nls/nls_iso8859-1.o\n'

# Offline build/stage runs on the preserved NORMAL kernel. The future candidate
# still builds and installs only its declared NLS closure; its loaded-module
# check belongs to actual candidate postboot, not this normal-kernel preflight.
NORMAL_MODULE_WITNESS_SHA256 = 'e21b41772bc494af225070c4a817af70e54c2f377605ef307340f55b07e4ce6a'
NORMAL_MODULE_NAMES = frozenset(('aesni_intel', 'async_memcpy', 'async_pq', 'async_raid6_recov', 'async_tx', 'async_xor', 'autofs4', 'binfmt_misc', 'bochs', 'btrfs', 'cfg80211', 'dm_multipath', 'dmi_sysfs', 'efi_pstore', 'floppy', 'ghash_clmulni_intel', 'i2c_piix4', 'i2c_smbus', 'input_leds', 'intel_rapl_common', 'intel_rapl_msr', 'intel_uncore_frequency_common', 'irqbypass', 'joydev', 'kvm', 'kvm_intel', 'libblake2b', 'linear', 'mac_hid', 'nfit', 'nfnetlink', 'nls_iso8859_1', 'parport', 'parport_pc', 'pata_acpi', 'ppdev', 'psmouse', 'qemu_fw_cfg', 'raid0', 'raid1', 'raid10', 'raid456', 'raid6_pq', 'rapl', 'sch_fq_codel', 'serio_raw', 'skx_edac_common', 'vga16fb', 'vgastate', 'virtiofs', 'vmw_vsock_virtio_transport', 'vmw_vsock_virtio_transport_common', 'vsock', 'xor'))
ENV_KEYS = {'KCFLAGS', 'KAFLAGS', 'KCPPFLAGS', 'CFLAGS_KERNEL', 'CFLAGS_MODULE',
            'AFLAGS_KERNEL', 'AFLAGS_MODULE', 'LLVM', 'LLVM_IAS', 'CC', 'LD',
            'HOSTCC', 'HOSTCXX', 'CROSS_COMPILE', 'KBUILD_OUTPUT', 'KBUILD_EXTMOD',
            'KCONFIG_CONFIG', 'ARCH', 'MAKEFLAGS', 'MFLAGS', 'INSTALL_MOD_PATH',
            'INSTALL_MOD_STRIP', 'KBUILD_MODPOST_WARN', 'KBUILD_MODPOST_NOFINAL'}
FILE_NAMES = ('.config', 'Module.symvers', 'System.map', 'arch/x86/boot/bzImage',
              'certs/signing_key.x509', 'include/config/auto.conf',
              'include/config/kernel.release', 'include/generated/autoconf.h',
              'include/generated/utsrelease.h', 'include/generated/utsversion.h',
              'modules.builtin', 'modules.builtin.modinfo', 'modules.order', 'vmlinux',
              'vmlinux.symvers', NLS)
import io
import shutil
import stat
import tarfile
from pathlib import PurePosixPath
ENV_KEYS.update({'PYTHONPATH','PYTHONHOME','PYTHONOPTIMIZE','GCC_EXEC_PREFIX',
                 'COMPILER_PATH','LIBRARY_PATH','CPATH','C_INCLUDE_PATH'})
record = None
out = None
def require(value, message):
    if not value:
        raise RuntimeError(message)




def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()




def canonical(path):
    value = Path(path)
    require(value.is_absolute() and value.resolve(strict=True) == value,
            'canonical existing absolute path required: ' + str(value))
    return value




def checked_json(path, expected):
    value = canonical(path)
    require(re.fullmatch('[0-9a-f]{64}', expected) is not None and sha(value) == expected,
            'receipt SHA mismatch: ' + str(value))
    return value, json.loads(value.read_text())




def atomic_json(name, value):
    target = out / name
    temporary = target.with_name('.' + target.name + '.new')
    with temporary.open('xb') as stream:
        stream.write((json.dumps(value, sort_keys=True, indent=2) + '\n').encode())
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)
    descriptor = os.open(out, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)




def pins(root, expected):
    require(isinstance(expected, dict) and expected, 'empty file-pin set')
    result = {}
    for name, digest in expected.items():
        relative = Path(name)
        require(not relative.is_absolute() and '..' not in relative.parts,
                'invalid pinned relative path')
        path = root / relative
        require(path.resolve(strict=True) == path and path.is_file(),
                'nonregular or aliased pinned file: ' + str(path))
        before = path.stat()
        actual = sha(path)
        after = path.stat()
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                 before.st_ctime_ns) == (after.st_dev, after.st_ino, after.st_size,
                                        after.st_mtime_ns, after.st_ctime_ns),
                'pinned file changed while reading: ' + str(path))
        require(actual == digest, 'pinned bytes differ: ' + str(path))
        result[name] = actual
    return result




def available(path):
    stat = os.statvfs(path)
    return stat.f_bavail * stat.f_frsize




def environment():
    bad = sorted(key for key in os.environ if key in ENV_KEYS or
                 key.startswith(('CFLAGS', 'AFLAGS', 'KBUILD_', 'INSTALL_MOD_')))
    require(not bad, 'unreviewed build environment overrides: ' + ','.join(bad))




def idle_sample(expected, names):
    value = {'unix': time.time(), 'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
             'release': os.uname().release, 'taint': Path('/proc/sys/kernel/tainted').read_text().strip(),
             'modules': Path('/proc/modules').read_text(), 'busy': [], 'dthreads': []}
    require(all(str(value[key]) == str(expected[key]) for key in ('boot', 'release', 'taint')) and
            value['release'] == '7.0.0-38-kdlock1' and value['taint'] == '0', 'normal identity differs')
    require({line.split()[0] for line in value['modules'].splitlines()} == set(names), 'actual normal54 modules differ')
    require(not any('fixture' in path.name or path.name in ('kd_mmap_api', 'kd_mmap_api_events', 'kd_rwsem_api')
                    for path in Path('/dev').iterdir()), 'fixture/API device remains')
    commands = {'make', 'gmake', 'cc1', 'cc1plus', 'gcc', 'gcc-15', 'clang', 'ld', 'ld.bfd',
                'as', 'objtool', 'fstrim', 'depmod', 'insmod', 'rmmod', 'mmap-userspace'}
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            comm = (process / 'comm').read_text().strip()
            argv = [word.decode('utf-8', errors='replace') for word in (process / 'cmdline').read_bytes().split(b'\0') if word]
            project_check = any('/tests/kernel/' in word or 'test_source_boundaries.py' in word for word in argv)
            if (comm in commands or project_check or
                    comm.startswith(('kd-fixture/', 'kd-scene/', 'kd-reader/', 'kd-killable/'))):
                value['busy'].append({'pid': int(process.name), 'comm': comm, 'argv': argv})
            for task in (process / 'task').iterdir():
                if '\nState:\tD ' in '\n' + (task / 'status').read_text():
                    value['dthreads'].append({'pid': int(process.name), 'tid': int(task.name),
                                             'comm': (task / 'comm').read_text().strip(),
                                             'wchan': (task / 'wchan').read_text().strip()})
        except (FileNotFoundError, ProcessLookupError):
            pass
    return value




def final_idle(expected, names):
    deadline = time.monotonic() + 60
    clear_at = None
    samples = []
    while True:
        sample = idle_sample(expected, names)
        samples.append(sample)
        record['final_idle_samples'] = samples
        atomic_json('result.json', record)
        if sample['busy'] or sample['dthreads']:
            clear_at = None
        elif clear_at is None:
            clear_at = time.monotonic()
        elif time.monotonic() - clear_at >= 10:
            return sample
        require(time.monotonic() < deadline, 'final strict idle not established within60s; all samples retained')
        time.sleep(min(10, max(0, deadline - time.monotonic())))




def idle(expected):
    sample = idle_sample(expected, NORMAL_MODULE_NAMES)
    require(not sample['busy'] and not sample['dthreads'], 'strict idle refused: ' + json.dumps(sample, sort_keys=True))
    sample['normal_module_names'] = sorted(NORMAL_MODULE_NAMES)
    sample['normal_module_witness_sha256'] = NORMAL_MODULE_WITNESS_SHA256
    return sample





def boot_files():
    result = {}
    for root in (Path('/boot'), Path('/etc/grub.d')):
        for path in sorted(root.rglob('*')):
            if path.is_symlink():
                result[str(path)] = {'symlink': os.readlink(path)}
            elif path.is_file():
                result[str(path)] = {'bytes': path.stat().st_size, 'sha256': sha(path)}
    for path in (Path('/etc/default/grub'), Path('/boot/grub/grubenv')):
        if path.is_file():
            result[str(path)] = {'bytes': path.stat().st_size, 'sha256': sha(path)}
    result['/lib/modules namespaces'] = sorted(item.name for item in Path('/lib/modules').iterdir())
    return result



def diagnostic_rows(path):
    # Recognize diagnostic records, not echoed GCC recipes whose flags include
    # -Wmissing-declarations after an unrelated vmlinux.export.o argument.
    prefix = re.compile(r'^(?:(?:ERROR|WARNING|error|warning|fatal error):|'
                        r'(?:ld|ld\.bfd|modpost):|'
                        r'[^\n]+:[0-9]+(?::[0-9]+)?:\s*(?:fatal error|error|warning|note):)')
    rows = []
    for number, line in enumerate(path.read_text(errors='replace').splitlines(), 1):
        if prefix.match(line.strip()):
            rows.append({'line': number, 'text': line})
    return rows




def export_rows(path):
    rows = []
    for line in path.read_text().splitlines():
        fields = line.split()
        require(len(fields) >= 4, 'invalid native symbol-version row')
        if fields[2] == 'vmlinux':
            rows.append(line)
    require(rows, 'fresh vmlinux export rows absent')
    return sorted(rows)




def elf_bytes(path, address, length):
    with path.open('rb') as stream:
        header = stream.read(64)
        require(header[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', header, 18)[0] == 62,
                'actual ELF64 x86-64 required')
        offset = struct.unpack_from('<Q', header, 32)[0]
        size, count = struct.unpack_from('<HH', header, 54)
        require(size == 56 and 0 < count < 1024, 'ELF program-header bounds')
        matches = []
        for index in range(count):
            stream.seek(offset + index * size)
            kind, flags, file_offset, va, unused, file_size, unused2, unused3 = \
                struct.unpack('<IIQQQQQQ', stream.read(size))
            if kind == 1 and flags & 1 and va <= address and address + length <= va + file_size:
                matches.append(file_offset + address - va)
        require(len(matches) == 1, 'symbol does not map to one executable file-backed ELF segment')
        stream.seek(matches[0])
        data = stream.read(length)
        require(len(data) == length, 'short ELF symbol data')
        return data




def linked_identity(source, build, deadline, args):
    notes = run('elf-notes', ['readelf', '-nW', str(build / 'vmlinux')], deadline, build, args)
    identifiers = re.findall(r'Build ID:\s*([0-9a-f]+)', notes.read_text())
    require(len(identifiers) == 1, 'one actual linked GNU Build ID required')
    nm = run('elf-symbols', ['nm', '-S', '-n', '--defined-only', str(build / 'vmlinux')],
             deadline, build, args)
    wanted = {'current_task', 'const_current_task', '__per_cpu_start',
              'its_return_thunk', '__x86_return_thunk'}
    symbols = {}
    for line in nm.read_text().splitlines():
        fields = line.split()
        if len(fields) in (3, 4) and fields[-1] in wanted:
            require(fields[-1] not in symbols, 'duplicate linked symbol')
            symbols[fields[-1]] = {'address': int(fields[0], 16),
                                   'bytes': int(fields[1], 16) if len(fields) == 4 else 0}
    require(set(symbols) == wanted, 'required actual linked GS/return symbols absent')
    gs = {key: symbols[key]['address'] for key in ('current_task', 'const_current_task', '__per_cpu_start')}
    require(gs['current_task'] == gs['const_current_task'] and gs['current_task'] >= 1 << 63,
            'current_task must be the full linked alias, without a second subtraction')
    mapped = {}
    for line in (build / 'System.map').read_text().splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[2] in wanted:
            require(fields[2] not in mapped, 'duplicate System.map symbol')
            mapped[fields[2]] = int(fields[0], 16)
    require(mapped == {key: row['address'] for key, row in symbols.items()},
            'System.map and linked ELF symbols differ')
    disassembly = run('gs-disassembly', ['objdump', '-dw', '-M', 'intel',
                       '--disassemble=kd_mutex_release_request', str(build / 'vmlinux')],
                      deadline, build, args)
    witnesses = []
    for line in disassembly.read_text().splitlines():
        match = re.match(r'\s*([0-9a-f]+):\s*((?:[0-9a-f]{2}\s+)+)', line)
        if match is None:
            continue
        raw = bytes.fromhex(match[2])
        if len(raw) == 8 and raw[:1] == b'\x65' and raw[1] in (0x48, 0x4c) and \
                raw[2] == 0x8b and raw[3] & 0xc7 == 5:
            site = int(match[1], 16)
            target = (site + 8 + int.from_bytes(raw[4:], 'little', signed=True)) & ((1 << 64) - 1)
            if target == gs['current_task']:
                require(elf_bytes(build / 'vmlinux', site, len(raw)) == raw, 'GS witness bytes differ')
                witnesses.append({'function': 'kd_mutex_release_request', 'site': hex(site),
                                  'source_next_ip': hex(site + 8), 'instruction_hex': raw.hex(),
                                  'current_task': hex(target), 'line': line})
    require(witnesses, 'fresh linked full-VMA GS:RIP witness absent')
    thunks = {}
    for name in ('its_return_thunk', '__x86_return_thunk'):
        row = symbols[name]
        require(1 <= row['bytes'] <= 4096, 'bounded actual return-symbol size required')
        data = elf_bytes(build / 'vmlinux', row['address'], row['bytes'])
        (out / (name + '.bin')).write_bytes(data)
        thunks[name] = dict(row, hex=data.hex(), sha256=hashlib.sha256(data).hexdigest())
    files = {name: {'bytes': (build / name).stat().st_size, 'sha256': sha(build / name)}
             for name in FILE_NAMES}
    result = {'build_id': identifiers[0], 'files': files, 'gs_symbols': gs,
              'gs_witness': witnesses[0], 'return_symbols': thunks,
              'module_count': 1, 'module_scope': 'Only the declared NLS boot closure was built.',
              'source': str(source), 'build': str(build), 'kernelrelease': RELEASE,
              'scope': 'Linked-image and selected-module evidence; no boot, API runtime or performance result.'}
    atomic_json('final-identity.json', result)
    atomic_json('gs-config.json', {'kernel_elf': str(build / 'vmlinux'),
                'kernel_elf_sha256': files['vmlinux']['sha256'],
                'system_map': str(build / 'System.map'),
                'system_map_sha256': files['System.map']['sha256'],
                'kernel_config': str(build / '.config'),
                'kernel_config_sha256': files['.config']['sha256'],
                'current_task_gs_offset': gs['current_task'],
                'percpu_section_va': gs['__per_cpu_start'], 'build_id': identifiers[0],
                'verified_for_running_kernel': False,
                'scope': 'Fresh linked ELF metadata only. A later actual postboot proof is required.'})
    return result




def run(label, argv, deadline, build, args):
    require(time.monotonic() < deadline, 'observer deadline before dispatch')
    row={'label':label,'argv':list(argv),'started_unix':time.time()}
    record['commands'].append(row);atomic_json('result.json',record)
    log=out/(label+'.log')
    with log.open('xb') as stream:
        child=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=stream,
            stderr=subprocess.STDOUT,start_new_session=True,
            env=dict(os.environ,LC_ALL='C',PYTHONDONTWRITEBYTECODE='1'))
        row.update(pid=child.pid,session=os.getsid(child.pid),process_group=os.getpgid(child.pid))
        atomic_json('result.json',record)
        while child.poll() is None:
            if time.monotonic()>=deadline or available('/')<args.root_floor or available(build)<args.output_floor or log.stat().st_size>args.log_limit:
                row.update(status='CHILD_RETAINED',elapsed_seconds=time.time()-row['started_unix'],log_bytes=log.stat().st_size)
                record['status']='INCOMPLETE_CHILD_RETAINED';atomic_json('result.json',record)
                raise RuntimeError('observer stopped; child/session retained without signals or cleanup')
            time.sleep(.25)
        row.update(returncode=child.returncode,elapsed_seconds=time.time()-row['started_unix'])
    row.update(log_bytes=log.stat().st_size,log_sha256=sha(log))
    atomic_json('result.json',record)
    require(child.returncode==0,label+' failed; exact output retained')
    require(row['log_bytes']<=args.log_limit,label+' exceeded observed log allowance')
    return log


def tool_pins(plan):
    result={}
    aliases={'cp':'/usr/bin/cp','make':'/usr/bin/make','python':'/usr/bin/python3',
             'gcc':'/usr/bin/gcc','gcc-15':'/usr/bin/gcc-15','as':'/usr/bin/as',
             'ld':'/usr/bin/ld','nm':'/usr/bin/nm','readelf':'/usr/bin/readelf',
             'objdump':'/usr/bin/objdump','modinfo':'/usr/sbin/modinfo','openssl':'/usr/bin/openssl'}
    for name,alias in aliases.items():
        p=Path(alias).resolve(strict=True);before=p.stat();digest=sha(p);after=p.stat()
        require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'tool changed while read')
        result[name]={'alias':alias,'resolved':str(p),'bytes':after.st_size,'sha256':digest}
        if name in plan['tools']:
            expected=plan['tools'][name]
            require(alias==expected['path'] and str(p)==expected['resolved_path'] and digest==expected['sha256'],'pinned tool changed: '+name)
    return result


def recovery_check(args,plan):
    unused,value=checked_json(args.recovery_json,args.recovery_sha256)
    p=plan['recovery'];stamp=datetime.datetime.fromisoformat(value['utc'])
    require(stamp.tzinfo is not None and 0<=time.time()-stamp.timestamp()<=plan['bounds']['recovery_maximum_age_seconds'],'fresh recovery required')
    require(value['hostname']==p['hostname'] and value['exe']==p['exe'] and value['pid']==p['pid'],'QEMU host/process identity differs')
    require(int(value['stat'].rsplit(')',1)[1].split()[19])==p['start_ticks'],'QEMU start identity differs')
    images=value['images'];require(len(images)==3 and {x['path'] for x in images}==set(p['image_paths']),'exact three backing images required')
    for image in images:
        require(image['path']==image['realpath'] and image['open_fds'] and image['host_available']>=plan['bounds']['host_floor_bytes'],'backing image or host headroom differs')
    hmp={x['command']:x['output'] for x in value['hmp']}
    require('No active jobs' in hmp['info block-jobs'] and 'VM status: running' in hmp['info status'],'QEMU idle jobs/running state differs')
    marker='List of snapshots present on all disks:'
    require(marker in hmp['info snapshots'],'all-disk snapshot inventory absent')
    complete=hmp['info snapshots'].split(marker,1)[1].split('List of partial',1)[0]
    require(all(any(tag in line.split() for line in complete.splitlines()) for tag in p['required_all_disk_tags']),'required complete recovery/failure snapshot absent')
    return {'sha256':args.recovery_sha256,'captured_utc':value['utc'],'required_all_disk_tags':p['required_all_disk_tags'],'all_disk_tags_verified':True,'raw':value}


def protected(plan):
    seed=canonical(plan['seed_source']);build=canonical(plan['seed_build'])
    value={'kernel8_output16':pins(build,plan['seed_output_files']),
           'kernel8_package78':pins(seed/'kernel/kdlock',plan['prior_package_files']),
           'kernel8_integration8':pins(seed,plan['integration_files']),
           'kernel8_native_mm11':pins(seed,plan['native_mm_files']),
           'normal_source8':pins(canonical(plan['normal_source']),plan['normal_source_files'])}
    require(sha(canonical(plan['normal_manifest']))==plan['normal_manifest_sha256'],'normal authenticated manifest changed')
    value['normal_manifest_sha256']=plan['normal_manifest_sha256']
    return value


def candidate_pins(plan,source):
    return {'package78':pins(source/'kernel/kdlock',plan['package_files']),
            'integration8':pins(source,plan['integration_files']),
            'native_mm11':pins(source,plan['native_mm_files'])}


def unpack_package(archive,expected,destination):
    seen=set();total=0
    with tarfile.open(archive,'r:') as tar:
        for member in tar:
            name=member.name;rel=PurePosixPath(name)
            require(member.isfile() and not rel.is_absolute() and '..' not in rel.parts and name==str(rel) and name not in seen and name in expected,'unsafe/duplicate package member')
            data=tar.extractfile(member).read();require(len(data)==member.size and hashlib.sha256(data).hexdigest()==expected[name],'package member mismatch: '+name)
            target=destination/name;target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as f:f.write(data)
            os.chmod(target,member.mode & 0o777);seen.add(name);total+=len(data)
    require(seen==set(expected) and len(seen)==78,'complete78 regular package required')
    return {'members':len(seen),'source_bytes':total}


def main():
    global out,record
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('plan-json','plan-sha256','recovery-json','recovery-sha256'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();require(os.geteuid()==0,'guest root required')
    plan_path,plan=checked_json(args.plan_json,args.plan_sha256)
    require(plan['format']=='kdlock.kernel9.cohort-build-plan.v1' and plan['selected_commit']==CORE and plan['release']==RELEASE,'plan identity differs')
    base=Path(plan['target']);source=base/'source';build=base/'build'
    require(base==Path('/mnt/kdlock-builds2/kdlock-main-kernel9-6e486ece-01') and not os.path.lexists(base),'fresh exclusive kernel9 target required')
    require(plan_path.parent==canonical(plan['input']) and sha(Path(__file__))==plan['driver_sha256'],'frozen driver/input identity differs')
    require(len(plan['package_files'])==len(plan['prior_package_files'])==78 and len(plan['integration_files'])==8 and len(plan['native_mm_files'])==11,'pin-set counts differ')
    require([n for n in plan['package_files'] if plan['package_files'][n]!=plan['prior_package_files'][n]]==['kernel/mutex.c'],'only mutex package delta required')
    require(plan['no_installer_reapply'] and plan['no_install_boot_tests'],'build-only plan required')
    environment();tools=tool_pins(plan);initial=idle(plan['normal_identity']);rec=recovery_check(args,plan)
    b=plan['bounds'];require(b['jobs']==16 and 1<=b['seconds']<=3600 and b['initial_output_floor_bytes']>=40*1024**3 and b['observed_output_floor_bytes']>=8*1024**3 and b['root_floor_bytes']>=1024**3,'reviewed bounds differ')
    args.root_floor=b['root_floor_bytes'];args.output_floor=b['observed_output_floor_bytes'];args.log_limit=b['command_log_bytes']
    require(available('/')>=args.root_floor and available(canonical('/mnt/kdlock-builds2'))>=b['initial_output_floor_bytes'],'initial guest headroom below reviewed40GiB/root floors')
    archive=canonical(plan_path.parent/'package.tar');package_path=canonical(plan_path.parent/'package.json')
    require(sha(archive)==plan['package_tar_sha256'] and sha(package_path)==plan['package_json_sha256'],'frozen package transport changed')
    package=json.loads(package_path.read_text());require(package['core_git_head']==package['source_snapshot_git_head']==CORE and package['files']==plan['package_files'] and package['intended_kernelrelease']==RELEASE,'package manifest differs')
    input_pins=pins(plan_path.parent,plan['provenance_files'])
    before=protected(plan);boot=boot_files()
    base.mkdir(mode=0o700);build.mkdir();(base/'receipts').mkdir();out=base/'receipts/build-01';out.mkdir(mode=0o700)
    record={'status':'PREPARED','scope':'Fresh source/O kernel9 mutex-object + bzImage + single NLS build only; no installer reapply/install/boot/test.',
            'selected_commit':CORE,'kernelrelease':RELEASE,'source':str(source),'build':str(build),'plan_sha256':args.plan_sha256,'driver_sha256':sha(Path(__file__)),
            'started_unix':time.time(),'commands':[],'identity_before':initial,'recovery':rec,'protected_before':before,'boot_before':boot,'tools_before':tools,'input_pins_before':input_pins,
            'headroom_before':{'root':available('/'),'output':available(build)},'space_reason':plan['space_reason'],'no_signals_or_cleanup_on_observer_stop':True}
    atomic_json('result.json',record);deadline=time.monotonic()+b['seconds']
    run('clone-source',['/usr/bin/cp','-a','--reflink=auto',plan['seed_source'],str(source)],deadline,build,args)
    pins(source/'kernel/kdlock',plan['prior_package_files']);pins(source,plan['integration_files']);pins(source,plan['native_mm_files'])
    for name in plan['prior_package_files']:
        old=(Path(plan['seed_source'])/'kernel/kdlock'/name).stat();new=(source/'kernel/kdlock'/name).stat()
        require((old.st_dev,old.st_ino)!=(new.st_dev,new.st_ino),'source clone must not hardlink preserved package')
    inputs=base/'input/package';inputs.mkdir(parents=True)
    record['package_export']=unpack_package(archive,plan['package_files'],inputs)
    # Integrated seed already has v3 hooks. Change only the reviewed core file.
    shutil.copyfile(inputs/'kernel/mutex.c',source/'kernel/kdlock/kernel/mutex.c')
    record['source_before']=candidate_pins(plan,source)
    config=build/'.config';shutil.copyfile(Path(plan['seed_build'])/'.config',config)
    require(sha(config)==plan['config_seed_sha256'],'independent config seed differs')
    make=['make','-C',str(source),'O='+str(build),'KERNELRELEASE='+RELEASE,'V=1']
    run('olddefconfig',make+['olddefconfig'],deadline,build,args)
    require(sha(config)==plan['config_seed_sha256'],'olddefconfig changed reviewed configuration')
    run('mutex-object',make+['-j16','kernel/kdlock/kernel/mutex.o'],deadline,build,args)
    require((build/'kernel/kdlock/kernel/mutex.o').is_file(),'changed mutex object absent')
    record['focused_object']={'path':'kernel/kdlock/kernel/mutex.o','bytes':(build/'kernel/kdlock/kernel/mutex.o').stat().st_size,'sha256':sha(build/'kernel/kdlock/kernel/mutex.o')}
    require(not (build/'vmlinux').exists() and not (build/NLS).exists(),'fresh first linked build required')
    run('kernel',make+['-j16','bzImage'],deadline,build,args)
    require((build/'vmlinux.symvers').is_file(),'fresh builtin exports absent')
    run('nls',make+['-j16',NLS],deadline,build,args)
    require(export_rows(build/'Module.symvers')==export_rows(build/'vmlinux.symvers'),'selected module and builtin export rows differ')
    require(not os.path.lexists(build/'modules.order'),'single-module temporary order not removed')
    with (build/'modules.order').open('xb') as f:f.write(ORDER);f.flush();os.fsync(f.fileno())
    require({str(p.relative_to(build)) for p in build.rglob('*.ko')}=={NLS},'only one NLS module output permitted')
    record['diagnostics']={name:diagnostic_rows(out/(name+'.log')) for name in ('olddefconfig','mutex-object','kernel','nls')}
    missing=re.compile(r'(undefined!|undefined (?:symbol|reference)|unresolved symbol|Symbol version dump.*missing|vmlinux(?:\.symvers|\.o)?.*missing)',re.I)
    require(not any(missing.search(row['text']) for rows in record['diagnostics'].values() for row in rows),'unresolved/missing-export diagnostic retained')
    vermagic=run('module-vermagic',['modinfo','-F','vermagic',str(build/NLS)],deadline,build,args)
    require(vermagic.read_text().strip().split()[0]==RELEASE,'NLS release differs')
    depends=run('module-dependencies',['modinfo','-F','depends',str(build/NLS)],deadline,build,args)
    require(not depends.read_text().strip(),'NLS has undeclared dependencies')
    linked=linked_identity(source,build,deadline,args);linked['module_vermagic']=vermagic.read_text().strip();atomic_json('final-identity.json',linked)
    for fn in ('kd_mutex_await','kd_mutex_acquire'):
        run(fn+'-disassembly',['objdump','-dw','-M','intel','--disassemble='+fn,str(build/'vmlinux')],deadline,build,args)
    require((build/'include/config/kernel.release').read_text().strip()==RELEASE and sha(config)==plan['config_seed_sha256'],'final release/config differs')
    record['final_identity_sha256']=sha(out/'final-identity.json')
    record['source_after']=candidate_pins(plan,source);record['protected_after']=protected(plan);record['boot_after']=boot_files()
    record['tools_after']=tool_pins(plan);record['input_pins_after']=pins(plan_path.parent,plan['provenance_files'])
    require(record['source_before']==record['source_after'] and before==record['protected_after'] and boot==record['boot_after'] and tools==record['tools_after'] and input_pins==record['input_pins_after'],'source/protected/boot/tool/input drift')
    record['identity_after']=final_idle(plan['normal_identity'],NORMAL_MODULE_NAMES)
    record.update(status='KERNEL9_BUILD_AND_LINKED_IDENTITY_COMPLETE',elapsed_seconds=time.time()-record['started_unix'],headroom_after={'root':available('/'),'output':available(build)},installed=False,booted=False,behavioral_test_performed=False)
    atomic_json('result.json',record);print(json.dumps({'status':record['status'],'receipt':str(out/'result.json')}))


if __name__=='__main__':
    try:main()
    except Exception as error:
        if record is not None:
            record['error']=str(error)
            if record.get('status')!='INCOMPLETE_CHILD_RETAINED':record['status']='FAILED_OR_INCOMPLETE'
            atomic_json('result.json',record)
        raise
