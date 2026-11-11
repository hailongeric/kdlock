#!/usr/bin/env python3
"""Independent kernel3 byte witness before the inactive candidate is rebuilt."""
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import tarfile
import time

BASE = Path('/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f')
SOURCE = BASE / 'source'
BUILD = BASE / 'build'
RECEIPTS = BASE / 'receipts'
DEST = RECEIPTS / 'retained-kdrebuild3-1b50e373-spin-01'
OVERLAY = RECEIPTS / 'overlay-1b50e373-kdrebuild3-20261111-01'
INPUTS = OVERLAY / 'build-inputs.json'
HMP = RECEIPTS / 'kernel4-retention-preflight-01' / 'recovery.json'
INPUT_SHA = '8779c43983d5ee4c2ae7ce4886b38ba2806f8ca91d1c0dbb97a8cd2f23f777ad'
FINAL_SHA = '17bea6450bf0eb3b0b0be682389276e556b9042c85034336e9120ba988d85d6f'
COMMIT = '1b50e37382d2c739b16953027c47d7e2388562f0'
SNAPSHOT = '69ba6b030c1eb7e5f1c3f9461b70f5fef6791309'
RELEASE = '7.0.0-38-kdrebuild3'
BID = '264a4ef8e55952e5d9ceccf93f65f25f05a50c1f'
BOOT = '884c4a65-4f4c-4a6b-89a3-cefd65221615'
BUILD_FILES = ['.config', 'vmlinux', 'System.map', 'Module.symvers',
               'arch/x86/boot/bzImage', 'include/config/kernel.release',
               'include/config/auto.conf', 'include/generated/autoconf.h',
               'include/generated/utsrelease.h', 'include/generated/utsversion.h',
               'modules.order', 'modules.builtin', 'modules.builtin.modinfo',
               'certs/signing_key.x509']
PINS = {
    ".config": "31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483",
    "Module.symvers": "fea56b69a34cf90d5fb7b3b35b47d94e2bcb8afe23609351134a2f4d10964bad",
    "System.map": "e7723218a35731108e2a1ae4ea1b33942fe7c1e44cc6671bc9345f08222c4d22",
    "arch/x86/boot/bzImage": "582e7b7b7be00fe9ba6f373ed25ad27864a13949c0bff1d7fa466271d479733e",
    "certs/signing_key.x509": "d2cc0e225390e9f1b8e355a9b56ac5b7a6532cc49fb724b3d5a56622a23b35a5",
    "include/config/auto.conf": "d731f7137d4af0af8468041db3b03292d174ed184d3916fa9162a29cb8f63243",
    "include/config/kernel.release": "75cd05cda631a4e6378283831eee4c7f40d85eb7a7ae94b0019d587e13b9fd23",
    "include/generated/autoconf.h": "ba620d16cd34149765ecae7223c519826d89e1bd51ef996f25af495b7cf18314",
    "include/generated/utsrelease.h": "8891e70571a7b20ec18fa497af0a2dc97a125c3ae5bebbac0f96e200385779be",
    "include/generated/utsversion.h": "a9037592233615e63af0a90e7bb2af74aaf401261cd4771ad731002af7571615",
    "modules.builtin": "ef55d7bc5528d2c01f38fc0d8f6473c75e14ec62349898f6529be9bbac871366",
    "modules.builtin.modinfo": "f173376892f5d1a020884e4c6062b51e7cf26718928e1225be5e4fb507c34d0c",
    "modules.order": "53585e7c733e6ae2ca38882eb323756a8184adee0d878a49a2489b7f15e62f82",
    "vmlinux": "c099d66949ba99bc0ec200ef1570cc2917e7b8a3eb0acdd97811333247d2a43d"
}
GENERATED = ['include/generated', 'include/config', 'arch/x86/include/generated']
BOOT_FILES = ['/boot/vmlinuz-' + RELEASE, '/boot/config-' + RELEASE,
              '/boot/System.map-' + RELEASE, '/boot/initrd.img-' + RELEASE]
BUSY = {'make','gmake','gcc','g++','cc1','cc1plus','clang','clang++','ld','ld.bfd',
        'ld.lld','as','ar','objcopy','insmod','rmmod','depmod','modprobe'}
JOURNAL = None


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def identity(value):
    require(stat.S_ISREG(value.st_mode), 'not a regular file')
    return dict(dev=value.st_dev, ino=value.st_ino, size=value.st_size,
                allocated=value.st_blocks*512, mode=stat.S_IMODE(value.st_mode),
                uid=value.st_uid, gid=value.st_gid, nlink=value.st_nlink,
                mtime_ns=value.st_mtime_ns, ctime_ns=value.st_ctime_ns)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_exact(path):
    require(path.resolve(strict=True) == path, 'symlink or noncanonical input: ' + str(path))
    before = identity(path.lstat())
    with path.open('rb') as stream:
        data = stream.read()
    require(before == identity(path.lstat()), 'changed during read: ' + str(path))
    return data, before


def file_hash(path):
    before = identity(path.lstat())
    require(path.resolve(strict=True) == path, 'noncanonical input')
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(4*1024*1024), b''):
            value.update(data)
    require(before == identity(path.lstat()), 'changed during hash: ' + str(path))
    return dict(sha256=value.hexdigest(), size=before['size'], identity=before)


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n');stream.flush();os.fsync(stream.fileno())
    sync_dir(path.parent)


def event(phase, **fields):
    row = dict(phase=phase, unix=time.time(), **fields)
    if JOURNAL is not None:
        JOURNAL.write(json.dumps(row, sort_keys=True)+'\n');JOURNAL.flush();os.fsync(JOURNAL.fileno())
    print(json.dumps(row, sort_keys=True), flush=True)


def copy_file(source, destination, expected=None):
    require(not destination.exists(), 'existing destination: ' + str(destination))
    before = file_hash(source)
    require(expected is None or before['sha256'] == expected, 'input hash mismatch: ' + str(source))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as incoming, destination.open('xb') as output:
        for data in iter(lambda: incoming.read(4*1024*1024), b''):
            output.write(data)
        output.flush()
        os.fchown(output.fileno(), before['identity']['uid'], before['identity']['gid'])
        os.fchmod(output.fileno(), before['identity']['mode'])
        os.utime(output.fileno(), ns=(os.fstat(incoming.fileno()).st_atime_ns,before['identity']['mtime_ns']))
        os.fsync(output.fileno())
    sync_dir(destination.parent)
    retained = file_hash(destination)
    require(file_hash(source) == before, 'source changed during copy: ' + str(source))
    require(retained['sha256'] == before['sha256'] and retained['size'] == before['size'], 'retained bytes mismatch')
    require((retained['identity']['dev'],retained['identity']['ino']) !=
            (before['identity']['dev'],before['identity']['ino']), 'not an independent inode')
    require(all(retained['identity'][k] == before['identity'][k] for k in ['mode','uid','gid','mtime_ns']),
            'retained metadata mismatch')
    return dict(sha256=before['sha256'],size=before['size'],source_identity=before['identity'],
                retained_identity=retained['identity'],source=str(source),retained=str(destination))


def idle():
    result = dict(release=Path('/proc/sys/kernel/osrelease').read_text().strip(),
                  boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                  taint=int(Path('/proc/sys/kernel/tainted').read_text()))
    require(result == dict(release='7.0.0-38-kdlock1',boot=BOOT,taint=0), 'running identity changed')
    require(not any(Path('/sys/module').glob('kd_*fixture*')) and not list(Path('/dev').glob('kd*')), 'fixture/control present')
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name)==os.getpid():continue
        try:
            comm=(process/'comm').read_text().strip()
            require(comm not in BUSY and not comm.startswith(('kd-fixture','kd-scene/','kd-runtime','kd-spin')), 'active worker: '+comm)
        except FileNotFoundError:pass
    return result


def available(path):
    value=os.statvfs(path);return value.f_bavail*value.f_frsize


def main():
    global JOURNAL
    signal.signal(signal.SIGALRM,lambda number,frame: (_ for _ in ()).throw(TimeoutError('600-second retention bound')))
    signal.alarm(600)
    require(os.geteuid()==0 and not DEST.exists(), 'root and fresh destination required')
    initial=idle()
    input_data,input_meta=read_exact(INPUTS)
    require(digest(input_data)==INPUT_SHA,'input manifest pin mismatch')
    inputs=json.loads(input_data)
    require(inputs['git_head'] == SNAPSHOT and inputs['core_git_head'] == COMMIT and
            inputs['build_input_count'] == 66 and len(inputs['files']) == 66 and
            all(not Path(name).is_absolute() and '..' not in Path(name).parts
                for name in inputs['files']), 'source input identity')
    hmp_data, _ = read_exact(HMP)
    recovery = json.loads(hmp_data)
    require(0 <= time.time() - recovery['unix'] < 900 and
            recovery['commands'][0]['command'] == 'info status' and
            'VM status: running' in recovery['commands'][0]['output'] and
            recovery['commands'][1]['command'] == 'info snapshots' and
            'kdlock-builddisk-clean-20261031' in recovery['commands'][1]['output'].split('List of partial', 1)[0] and
            'List of snapshots present on all disks:' in recovery['commands'][1]['output'] and
            recovery['commands'][2]['command'] == 'info block' and
            all(device + ' (' in recovery['commands'][2]['output']
                for device in ('drive_system', 'drive_data1', 'drive_kdlock_builds2')),
            'fresh full-disk recovery check required')
    require((BUILD/'include/config/kernel.release').read_text().strip()==RELEASE,'candidate release changed')
    require(available(BASE) >= 2 * 1024**3 and recovery['host_free_bytes'] >= 2 * 1024**3,
            'less than 2GiB initial guest/host retention headroom')
    final_data, _ = read_exact(OVERLAY / 'final-identity.json')
    require(digest(final_data) == FINAL_SHA, 'final identity receipt pin mismatch')
    final = json.loads(final_data)
    artifact_pins = final['files']
    require(set(artifact_pins) == set(BUILD_FILES) == set(PINS) and final['build_id'] == BID,
            'exact final artifact and BuildID set')
    for name,expected in PINS.items():require(artifact_pins[name]['sha256']==expected,'old identity receipt mismatch')
    installed_before={name:file_hash(Path(name)) for name in BOOT_FILES}
    readelf=['/usr/bin/readelf','-n',str(BUILD/'vmlinux')]
    notes=subprocess.run(readelf,check=True,capture_output=True,text=True,timeout=30).stdout
    require('Build ID: '+BID in notes,'actual kernel3 BuildID mismatch')
    DEST.mkdir(mode=0o700);sync_dir(RECEIPTS)
    with (DEST/'journal.jsonl').open('x') as journal:
        JOURNAL=journal
        try:
            save(DEST/'preflight.json',dict(current=initial,free_bytes={p:available(p) for p in ['/',str(BASE)]},
                 installed_before=installed_before,helper=file_hash(Path(__file__).resolve()),
                 recovery=dict(source=str(HMP), sha256=digest(hmp_data), host_free_bytes=recovery['host_free_bytes'])))
            with (DEST/'kernel3-build-id-notes.txt').open('x') as stream:
                stream.write(notes);stream.flush();os.fsync(stream.fileno())
            event('RETENTION_STARTED',destination=str(DEST))
            build_files={}
            for name in BUILD_FILES:
                expected=artifact_pins.get(name,{}).get('sha256')
                build_files[name]=copy_file(BUILD/name,DEST/'build'/name,expected)
            event('BUILD_ARTIFACTS_RETAINED',count=len(build_files))
            package_files={name:copy_file(SOURCE/'kernel/kdlock'/name,DEST/'package'/name,expected)
                           for name,expected in sorted(inputs['files'].items())}
            event('PACKAGE_SOURCES_RETAINED',count=len(package_files))
            generated={}
            archive_path=DEST/'generated-config-headers.tar'
            with archive_path.open('xb') as archive_stream:
                with tarfile.open(fileobj=archive_stream,mode='w',format=tarfile.PAX_FORMAT) as archive:
                    for directory in GENERATED:
                        for path in sorted((BUILD/directory).rglob('*')):
                            require(not path.is_symlink(),'symlink in generated tree')
                            if path.is_dir():continue
                            data,meta=read_exact(path);name=str(path.relative_to(BUILD))
                            info=tarfile.TarInfo(name);info.size=len(data);info.mode=meta['mode']
                            info.uid=meta['uid'];info.gid=meta['gid'];info.mtime=meta['mtime_ns']//1000000000
                            info.pax_headers={'mtime':str(meta['mtime_ns']//1000000000)+'.'+str(meta['mtime_ns']%1000000000).zfill(9)}
                            archive.addfile(info,io.BytesIO(data))
                            generated[name]=dict(sha256=digest(data),size=len(data),source_identity=meta)
                archive_stream.flush();os.fsync(archive_stream.fileno())
            with tarfile.open(archive_path,'r') as archive:
                require(len(archive.getmembers())==len(generated),'generated archive member count')
                for member in archive:
                    require(member.isfile() and member.name in generated,'unexpected generated member')
                    data=archive.extractfile(member).read()
                    require(digest(data)==generated[member.name]['sha256'] and len(data)==generated[member.name]['size'],'generated archive mismatch')
                    require(file_hash(BUILD/member.name)['identity']==generated[member.name]['source_identity'],'generated source changed')
            save(DEST/'generated-members.json',generated)
            event('GENERATED_HEADERS_RETAINED',count=len(generated))
            receipt_files = [RECEIPTS/name for name in ('pins.json', 'preparation.json',
                'configure-core-result.json', 'integration-plan.patch')]
            for directory in ('integration-application', OVERLAY.name,
                              'install-kdrebuild3-1b50e373-v1',
                              'postboot-kdrebuild3-20261110-UTC-01',
                              'return-normal-after-live5-20261110-UTC-01'):
                path = RECEIPTS/directory
                require(path.is_dir() and not path.is_symlink(), 'missing receipt directory: ' + directory)
                receipt_files.extend(item for item in path.rglob('*') if item.is_file())
            receipt_files.append(HMP)
            receipts={str(path.relative_to(RECEIPTS)):copy_file(path,DEST/'receipts'/path.relative_to(RECEIPTS)) for path in sorted(set(receipt_files))}
            current=idle()
            for name,row in build_files.items():require(file_hash(BUILD/name)['sha256']==row['sha256'],'build changed at closure')
            for name,row in package_files.items():require(file_hash(SOURCE/'kernel/kdlock'/name)['sha256']==row['sha256'],'package changed at closure')
            require({name:file_hash(Path(name)) for name in BOOT_FILES}==installed_before,'installed kernel3 changed')
            require(file_hash(INPUTS)['sha256']==INPUT_SHA,'input manifest changed')
            retained_notes=subprocess.run(['/usr/bin/readelf','-n',str(DEST/'build/vmlinux')],check=True,capture_output=True,text=True,timeout=30).stdout
            require(retained_notes==notes,'retained ELF notes differ')
            for directory in sorted((p for p in DEST.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):
                sync_dir(directory)
            sync_dir(DEST)
            groups=[build_files,package_files,receipts]
            manifest=dict(phase='KERNEL3_WITNESS_RETAINED',kernel_code_commit=COMMIT,kernelrelease=RELEASE,
                build_id=BID,source_snapshot=SNAPSHOT,source_root=str(SOURCE),build_root=str(BUILD),destination=str(DEST),
                build_files=build_files,package_files=package_files,receipt_files=receipts,
                generated_archive=file_hash(archive_path),generated_member_count=len(generated),
                input_manifest_sha256=INPUT_SHA,final_identity_sha256=FINAL_SHA,
                recovery_sha256=digest(hmp_data),installed_kernel3_unchanged=True,current=current,
                copied_regular_files=sum(len(x) for x in groups),
                retained_logical_bytes=sum(row['size'] for group in groups for row in group.values())+archive_path.stat().st_size,
                free_bytes_after={p:available(p) for p in ['/',str(BASE)]},unix=time.time())
            save(DEST/'manifest.json',manifest)
            event('KERNEL3_WITNESS_RETAINED',manifest_sha256=file_hash(DEST/'manifest.json')['sha256'],
                  build_files=len(build_files),package_files=len(package_files),generated_members=len(generated),
                  receipt_files=len(receipts),retained_logical_bytes=manifest['retained_logical_bytes'],free_bytes_after=manifest['free_bytes_after'])
            signal.alarm(0)
        except BaseException as error:
            event('FAILED_RETAIN_PARTIAL',error_type=type(error).__name__,error=str(error));raise
        finally:JOURNAL=None


if __name__=='__main__':main()
