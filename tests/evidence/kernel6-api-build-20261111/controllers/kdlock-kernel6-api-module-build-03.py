#!/usr/bin/env python3
"""VM-only cold external API fixture builds and separate signed copies.

Requires exact kernel6/frozen source receipts. A timeout retains its child.
This helper neither loads a module nor executes fixture/syscall bodies.
Private signing-key data is never copied, hashed or printed by this helper.
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
import tarfile
import shutil
from pathlib import PurePosixPath

RELEASE = '7.0.0-38-kdrebuild6'
CORE = '532b68a65bdf96504e2cede6c23a5bc1476d94e9'
NLS = 'fs/nls/nls_iso8859-1.ko'
ORDER = b'fs/nls/nls_iso8859-1.o\n'

# Offline build/stage runs on the preserved NORMAL kernel. The future candidate
# still builds and installs only its declared NLS closure; its loaded-module
# check belongs to actual candidate postboot, not this normal-kernel preflight.
NORMAL_MODULE_WITNESS_SHA256 = '600efa6a36995c46e8c1be54f93de9f97ef919148ca50c780e78fa338e1af60a'
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


def idle(expected):
    current = {'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
               'release': os.uname().release,
               'taint': Path('/proc/sys/kernel/tainted').read_text().strip(),
               'modules': Path('/proc/modules').read_text(), 'busy': [], 'blocked': []}
    require((current['boot'], current['release'], current['taint']) ==
            (expected['boot'], expected['release'], str(expected['taint'])),
            'running identity differs from focused normal boot')
    require(current['release'] == '7.0.0-38-kdlock1' and current['taint'] == '0',
            'untainted normal kernel required for offline build')
    loaded = {line.split()[0] for line in current['modules'].splitlines()}
    require(loaded == NORMAL_MODULE_NAMES, 'normal loaded-module names differ: ' + repr(sorted(loaded)))
    current['normal_module_names'] = sorted(loaded)
    current['normal_module_witness_sha256'] = NORMAL_MODULE_WITNESS_SHA256
    require(not any('fixture' in item.name for item in Path('/dev').iterdir()),
            'fixture control remains')
    commands = {'make', 'gmake', 'cc1', 'cc1plus', 'gcc', 'gcc-15', 'clang',
                'ld', 'ld.bfd', 'as', 'objtool', 'fstrim', 'depmod', 'insmod', 'rmmod'}
    for item in Path('/proc').iterdir():
        if not item.name.isdigit() or int(item.name) == os.getpid():
            continue
        try:
            command = (item / 'comm').read_text().strip()
            if command in commands or command.startswith(('kd-fixture/', 'kd-scene/', 'kd-reader/')):
                current['busy'].append({'pid': int(item.name), 'comm': command})
            for task in (item / 'task').iterdir():
                if '\nState:\tD ' in '\n' + (task / 'status').read_text():
                    current['blocked'].append({'pid': int(item.name), 'tid': int(task.name), 'comm': (task / 'comm').read_text().strip(), 'wchan': (task / 'wchan').read_text().strip()})
        except (FileNotFoundError, ProcessLookupError):
            pass
    require(not current['busy'] and not current['blocked'], 'build/workload or blocked task remains: ' + json.dumps(current, sort_keys=True))
    return current


def recovery(path, expected, floor):
    unused, value = checked_json(path, expected)
    if 'hmp' in value:
        require(value['hostname'] == 'Super-Server' and value['pid'] == 257489 and
                value['exe'] == '/usr/bin/qemu-system-x86_64', 'host/QEMU identity differs')
        captured = datetime.datetime.fromisoformat(value['utc']).timestamp()
        commands = value['hmp']
        images = value['images']
        require(len(images) == 3 and all(row['open_fds'] and row['path'] == row['realpath']
                                       for row in images), 'three attached image references absent')
        free = min(row['host_available'] for row in images)
    else:
        captured, commands, free = value['unix'], value['commands'], value['host_free_bytes']
    require(0 <= time.time() - captured <= 900, 'fresh actual recovery receipt required')
    texts = {row['command']: row['output'] for row in commands}
    require('VM status: running' in texts.get('info status', ''), 'VM not running')
    snapshots = texts.get('info snapshots', '')
    marker = 'List of snapshots present on all disks:'
    require(marker in snapshots and 'kdlock-builddisk-clean-20261031' in
            snapshots.split(marker, 1)[1].split('List of partial', 1)[0],
            'complete all-disk recovery snapshot absent')
    require(free >= floor, 'host headroom below explicit floor')
    return {'sha256': expected, 'captured_unix': captured, 'host_available': free}


def protected(focused):
    normal = canonical(focused['normal_source'])
    old = canonical(focused['kernel5_preserved'])
    return {'normal': pins(normal, focused['normal_after']),
            'kernel5': pins(old / 'build', focused['kernel5_after']),
            'kernel5_core': pins(old / 'source/kernel/kdlock', focused['kernel5_core_after'])}


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


def source_pins(focused, source):
    result = {'package': pins(source / 'kernel/kdlock', focused['package_after']),
              'bodies': pins(source, focused['body_after']),
              'integration': pins(source, focused['source_after_after']),
              'immutable_input': pins(canonical(focused['package_input']), focused['package_after'])}
    for key, digest_key in (('package_manifest', 'package_manifest_sha256'),
                            ('applied_manifest', 'applied_manifest_sha256'),
                            ('inspect_receipt', 'inspect_sha256'),
                            ('journal_receipt', 'journal_sha256'),
                            ('prior_failed_result', 'prior_failed_result_sha256')):
        path = canonical(focused[key])
        require(sha(path) == focused[digest_key], 'focused provenance changed: ' + str(path))
        result[key] = focused[digest_key]
    return result


def run(label, argv, deadline, build, args):
    require(time.monotonic() < deadline, 'deadline expired before dispatch')
    row = {'label': label, 'argv': list(argv), 'started_unix': time.time()}
    record['commands'].append(row)
    atomic_json('result.json', record)
    log = out / (label + '.log')
    with log.open('xb') as output:
        child = subprocess.Popen(argv, stdout=output, stderr=subprocess.STDOUT,
                                 env=dict(os.environ, LC_ALL='C', PYTHONDONTWRITEBYTECODE='1'))
        row['pid'] = child.pid
        atomic_json('result.json', record)
        while child.poll() is None:
            if time.monotonic() >= deadline or available('/') < args.root_floor or \
                    available(build) < args.output_floor:
                row.update(status='CHILD_RETAINED', elapsed_seconds=time.time() - row['started_unix'])
                record['status'] = 'INCOMPLETE_CHILD_RETAINED'
                atomic_json('result.json', record)
                raise RuntimeError('deadline/space observer stopped; child retained, no drain proof')
            time.sleep(0.25)
        row.update(returncode=child.returncode, elapsed_seconds=time.time() - row['started_unix'])
    row['log_sha256'] = sha(log)
    atomic_json('result.json', record)
    require(child.returncode == 0, label + ' failed; output retained')
    return log


FIXTURE='80c272e5f134d9a499c03782f71064d04fae25c3'

def unpack(archive, manifest, destination):
    files=manifest['files'];require(len(files)==manifest['file_count']==83 and sum(v['bytes'] for v in files.values())==manifest['source_bytes']<=2*1024**2,'exact bounded source membership required')
    payload={}
    with tarfile.open(archive,'r:') as stream:
        for member in stream:
            path=PurePosixPath(member.name);require(member.name==str(path) and not path.is_absolute() and '..' not in path.parts and member.isfile() and member.name in files and member.name not in payload,'unexpected archive member')
            row=files[member.name];require(member.size==row['bytes']<=2*1024**2,'archive member size differs')
            with stream.extractfile(member) as source:data=source.read(member.size+1)
            require(len(data)==member.size and hashlib.sha256(data).hexdigest()==row['sha256'],'archive member bytes differ');payload[member.name]=data
    require(set(payload)==set(files),'archive membership differs')
    destination.mkdir(mode=0o700)
    for name,data in payload.items():
        path=destination/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
    source_files(destination,files)


def source_files(root,files):
    entries=list(root.rglob('*'));require(not any(p.is_symlink() for p in entries),'immutable source contains a symlink')
    actual={str(p.relative_to(root)) for p in entries if p.is_file()}
    require(actual==set(files),'immutable source membership differs')
    for name,row in files.items():
        path=root/name;require(not path.is_symlink() and path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],'immutable source bytes differ: '+name)


def main():
    global record,out
    ap=argparse.ArgumentParser(description='VM-only two API fixture builds and signing; no load or API execution.')
    for key in ('archive','archive-sha','manifest','manifest-sha','state','state-sha','build-receipt','build-sha','offroot-receipt','offroot-sha','client-receipt','client-sha','recovery','recovery-sha','output'):
        ap.add_argument('--'+key,required=True)
    for key in ('jobs','seconds','root-floor','output-floor','host-floor'):ap.add_argument('--'+key,type=int,required=True)
    args=ap.parse_args();require(os.geteuid()==0 and args.jobs==8 and 1<=args.seconds<=300,'explicit8jobs/300s root controller required');require(args.root_floor>=1024**3 and args.output_floor>=1024**3 and args.host_floor>=8*1024**3,'reviewed space floors required');environment()
    manifest_path,manifest=checked_json(args.manifest,args.manifest_sha);unused,state=checked_json(args.state,args.state_sha);archive=canonical(args.archive);require(sha(archive)==args.archive_sha==manifest['archive_sha256'] and archive.stat().st_size==manifest['archive_bytes'],'archive pin differs');require(state['commit']==manifest['source_git_head']==FIXTURE and manifest['kernel_core_git_head']==CORE and manifest['kernel_source_snapshot_git_head']=='3512f5dd639701f3f9953cfc6add1e4bbdd85e88','fixture/kernel source identities differ')
    build_path,built=checked_json(args.build_receipt,args.build_sha);require(built['status']=='BUILT_AND_LINKED_IDENTITY_VERIFIED' and built['core_git_head']==CORE and built['kernelrelease']==RELEASE,'actual kernel6 successful metadata required');unused,identity=checked_json(build_path.parent/'final-identity.json',built['final_identity_sha256']);require(identity['module_count']==1 and len(identity['files'])==16,'actual16core output pins required')
    unused,focused=checked_json(built['focused_receipt'],built['focused_sha256']);source,build=canonical(built['source']),canonical(built['build']);require(source==Path(focused['source']) and build==Path(focused['build']),'exact actual source/O required')
    for name,digest in focused['package_after'].items():require(manifest['files'][name]['sha256']==digest,'snapshot kernel input differs from linked source: '+name)
    require(len(focused['package_after'])==77,'exact linked package membership required');pins(source/'kernel/kdlock',focused['package_after']);pins(build,{n:v['sha256'] for n,v in identity['files'].items()})
    unused,staged=checked_json(args.offroot_receipt,args.offroot_sha);require(staged['status']=='OFFROOT_MODULE_STAGE_COMPLETE' and staged['stage']['build_receipt_sha256']==args.build_sha and staged['source']==str(source) and staged['build']==str(build),'exact signed NLS provenance required');signature=staged['stage']['modinfo'];require(signature['signer'] and signature['sig_key'] and signature['sig_hashalgo']=='sha512','actual signing metadata differs')
    config=(build/'.config').read_text().splitlines();require('CONFIG_MODULE_SIG_KEY="certs/signing_key.pem"' in config and 'CONFIG_MODULE_SIG_HASH="sha512"' in config,'actual normal signing configuration differs');sign_tool=canonical(build/'scripts/sign-file');key=canonical(build/'certs/signing_key.pem');certificate=canonical(build/'certs/signing_key.x509');require(sign_tool.is_file() and key.is_file() and certificate.is_file() and not key.is_symlink(),'actual built signing tool/key/certificate required')
    client_path,client=checked_json(args.client_receipt,args.client_sha);require(client['status']=='FOCUSED_CHECKS_COMPLETE' and client['boundary_tests']==4,'actual checked client prerequisite required');client_root=client_path.parent.parent;binary=canonical(client_root/'build/mmap-userspace');require(sha(binary)==client['binary_sha256'],'previously built client bytes changed')
    for name in ('tests/kernel/mmap_api/userspace.c','tests/kernel/mmap_api/abi.h'):
        require(sha(client_root/'input'/name)==manifest['files'][name]['sha256'],'reused client source/ABI differs')
    state_before=idle(focused['identity_after']);rec=recovery(args.recovery,args.recovery_sha,args.host_floor);root=Path(args.output);work=Path('/mnt/kdlock-builds/kdlock-main-work');require(root.is_absolute() and root.parent.resolve(strict=True)==work and root==work/'kernel6-api-modules-80c272e5-03' and not os.path.lexists(root),'fresh exact cold source/output root required');require(available('/')>=args.root_floor and available(work)>=args.output_floor,'module build headroom floor')
    protected_before=protected(focused);kernel_source_before=source_pins(focused,source);boot_before=boot_files();root.mkdir(mode=0o700);out=root/'receipts';out.mkdir(mode=0o700);inp=root/'input';record={'status':'PREPARED','source_commit':FIXTURE,'kernel_core_commit':CORE,'kernel_source_snapshot_commit':manifest['kernel_source_snapshot_git_head'],'kernelrelease':RELEASE,'kernel_source':str(source),'kernel_build':str(build),'build_receipt':str(build_path),'build_receipt_sha256':args.build_sha,'final_identity_sha256':built['final_identity_sha256'],'core_pins_before':identity['files'],'offroot_receipt_sha256':args.offroot_sha,'archive_sha256':args.archive_sha,'manifest_sha256':args.manifest_sha,'state_sha256':args.state_sha,'source_input':str(inp),'commands':[],'modules':{},'identity_before':state_before,'protected_before':protected_before,'kernel_source_before':kernel_source_before,'boot_before':boot_before,'recovery':rec,'reused_client':{'path':str(binary),'sha256':client['binary_sha256'],'receipt':str(client_path),'receipt_sha256':args.client_sha,'source_and_abi_match':True,'executed_in_this_stage':False},'signing':{'public_certificate_sha256':identity['files']['certs/signing_key.x509']['sha256'],'expected_signature_metadata':signature,'private_key_data_recorded':False},'scope':'Two ordinary external Kbuild modules and separately signed copies only. No module load, control operation, test, syscall or boot.'};atomic_json('result.json',record);unpack(archive,manifest,inp);deadline=time.monotonic()+args.seconds;signed_dir=root/'signed';signed_dir.mkdir(mode=0o700)
    for label,relative,module_name in (('rwsem','tests/kernel/rwsem_api/payload','kd_rwsem_api_fixture.ko'),('mmap','tests/kernel/mmap_api/payload','kd_mmap_api_provider.ko')):
        module_out=root/(label+'-build');module_out.mkdir(mode=0o700)
        run(label+'-build',['make','-C',str(source),'O='+str(build),'M='+str(inp/relative),'MO='+str(module_out),'KERNELRELEASE='+RELEASE,'-j8','V=1','modules'],deadline,root,args)
        module=module_out/module_name;require(module.is_file() and not module.is_symlink() and list(module_out.glob('*.ko'))==[module],'exact external module output required');unsigned={'path':str(module),'bytes':module.stat().st_size,'sha256':sha(module)};target=signed_dir/module_name
        with module.open('rb') as src,target.open('xb') as dst:shutil.copyfileobj(src,dst);dst.flush();os.fsync(dst.fileno())
        run(label+'-sign',[str(sign_tool),'sha512',str(key),str(certificate),str(target)],deadline,root,args);require(sha(module)==unsigned['sha256'],'unsigned build artifact changed during signing')
        fields={}
        for field in ('vermagic','signer','sig_key','sig_hashalgo','depends'):
            log=run(label+'-'+field,['modinfo','-F',field,str(target)],deadline,root,args);fields[field]=log.read_text().strip()
        require(fields['vermagic'].split()[0]==RELEASE and fields['signer']==signature['signer'] and fields['sig_key']==signature['sig_key'] and fields['sig_hashalgo']==signature['sig_hashalgo'] and not fields['depends'],'signed module metadata differs from actual kernel6 signing provenance')
        record['modules'][label]={'unsigned':unsigned,'signed':{'path':str(target),'bytes':target.stat().st_size,'sha256':sha(target)},'modinfo':fields};atomic_json('result.json',record)
    source_files(inp,manifest['files']);pins(build,{n:v['sha256'] for n,v in identity['files'].items()});record['core_pins_after']=identity['files'];record['protected_after']=protected(focused);record['kernel_source_after']=source_pins(focused,source);record['boot_after']=boot_files();require(record['protected_after']==protected_before and record['kernel_source_after']==kernel_source_before and record['boot_after']==boot_before,'protected inputs changed');require(sha(build_path)==args.build_sha and sha(manifest_path)==args.manifest_sha and sha(client_path)==args.client_sha and sha(binary)==client['binary_sha256'] and sha(Path(built['focused_receipt']))==built['focused_sha256'] and sha(Path(args.offroot_receipt))==args.offroot_sha and sha(build_path.parent/'final-identity.json')==built['final_identity_sha256'] and sha(Path(args.state))==args.state_sha and sha(archive)==args.archive_sha,'retained prerequisite changed');record['identity_after']=idle(focused['identity_after']);record['headroom_after']={'root':available('/'),'output':available(root)};record['status']='API_MODULES_BUILT_AND_SIGNED';atomic_json('result.json',record);print(json.dumps({'status':record['status'],'receipt':str(out/'result.json'),'modules':record['modules']},sort_keys=True))

if __name__=='__main__':
    try:main()
    except Exception as error:
        if record is not None:
            if record.get('status')!='INCOMPLETE_CHILD_RETAINED':record['status']='FAILED_OR_INCOMPLETE'
            record['error']=str(error);atomic_json('result.json',record)
        raise
