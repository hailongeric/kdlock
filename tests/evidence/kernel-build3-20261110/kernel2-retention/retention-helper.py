#!/usr/bin/env python3
"""Independent kernel2 byte witness before the inactive candidate is rebuilt."""
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
DEST = RECEIPTS / 'retained-kdrebuild2-81feb2d7-20261110-UTC-01'
OVERLAY = RECEIPTS / 'overlay-81feb2d7'
INPUTS = OVERLAY / 'kdlock-main-81feb2d7-build-inputs.json'
INPUT_SHA = 'fc93427521aaa3bab2af9eccb9dc10f300f040bd07ffc4ac4b365bb16200a369'
COMMIT = '81feb2d749ebbca468c0ab2eb895dcdd82fe519e'
RELEASE = '7.0.0-38-kdrebuild2'
BID = 'fd2262c047e130787ef669419111eba6eb9ebb2c'
BOOT = 'ca0b717b-c19d-4027-b598-6a1cf58b93d2'
BUILD_FILES = ['.config', 'vmlinux', 'System.map', 'Module.symvers',
               'arch/x86/boot/bzImage', 'include/config/kernel.release',
               'include/config/auto.conf', 'include/generated/autoconf.h',
               'include/generated/utsrelease.h', 'include/generated/utsversion.h',
               'modules.order', 'modules.builtin', 'modules.builtin.modinfo',
               'certs/signing_key.x509']
PINS = {
 'vmlinux':'7de39e303412b36ea7dd36f7260183669bc4d2829569dd1e3ac9bc2426e91809',
 'arch/x86/boot/bzImage':'a5fc091793ac0b4dbe9ccb59a390743967d89aa61192eb29e497ac066f356439',
 '.config':'31d9701e739a1f6a596ecca0a76fa913e3938ec80e90560b68a72d0bf1628483',
 'System.map':'47cc1e87e95f2e118f9a20ff01ec8e31dee1f9d0f650ef9649392a25db98395f',
 'Module.symvers':'2533c2a4becc4f99f8dacc38e9480608c9032e4c0f3d06a9b4a2fe51fda6752b'}
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
    require(not Path('/sys/module/kd_runtime_fixture').exists() and not list(Path('/dev').glob('kd*')), 'fixture/control present')
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name)==os.getpid():continue
        try:
            comm=(process/'comm').read_text().strip()
            require(comm not in BUSY and not comm.startswith(('kd-fixture','kd-scene/','kd-runtime')), 'active worker: '+comm)
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
    require(inputs['git_head']==COMMIT and inputs['build_input_count']==64 and len(inputs['files'])==64,'source input identity')
    require((BUILD/'include/config/kernel.release').read_text().strip()==RELEASE,'candidate release changed')
    require(available(BASE)>1024*1024*1024,'less than 1GiB destination headroom')
    final=json.loads((OVERLAY/'final-identity.json').read_text())
    artifact_pins={str(Path(x['path']).relative_to(BUILD)):x for x in final['artifacts']}
    for name,expected in PINS.items():require(artifact_pins[name]['sha256']==expected,'old identity receipt mismatch')
    installed_before={name:file_hash(Path(name)) for name in BOOT_FILES}
    readelf=['/usr/bin/readelf','-n',str(BUILD/'vmlinux')]
    notes=subprocess.run(readelf,check=True,capture_output=True,text=True,timeout=30).stdout
    require('Build ID: '+BID in notes,'actual kernel2 BuildID mismatch')
    DEST.mkdir(mode=0o700);sync_dir(RECEIPTS)
    with (DEST/'journal.jsonl').open('x') as journal:
        JOURNAL=journal
        try:
            save(DEST/'preflight.json',dict(current=initial,free_bytes={p:available(p) for p in ['/',str(BASE)]},
                 installed_before=installed_before,helper=file_hash(Path(__file__).resolve()),
                 recovery_check='Controller freshly queried QEMU info snapshots: kdlock-builddisk-clean-20261031 present on all3disks; raw output in controller transcript.'))
            with (DEST/'kernel2-build-id-notes.txt').open('x') as stream:
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
            receipt_files=[]
            receipt_files += [RECEIPTS/name for name in ['pins.json','preparation.json','configure-core-result.json','integration-plan.patch']]
            receipt_files += [path for path in (RECEIPTS/'integration-application').rglob('*') if path.is_file()]
            receipt_files += [OVERLAY/name for name in ['kdlock-main-81feb2d7-build-inputs.json','controller.py','final-identity.json','result.json','build.log']]
            install=RECEIPTS/'install-kdrebuild2-81feb2d7-v1'
            receipt_files += [path for path in install.iterdir() if path.is_file() and path.name!='stage-protected-before.json']
            receipt_files += [RECEIPTS/'postboot4-20261111-01'/name for name in ['result.json','gs-proof.json','running-kernel-notes.bin','vmlinux-notes.txt','vmlinux-sections.txt']]
            receipts={str(path.relative_to(RECEIPTS)):copy_file(path,DEST/'receipts'/path.relative_to(RECEIPTS)) for path in sorted(set(receipt_files))}
            current=idle()
            for name,row in build_files.items():require(file_hash(BUILD/name)['sha256']==row['sha256'],'build changed at closure')
            for name,row in package_files.items():require(file_hash(SOURCE/'kernel/kdlock'/name)['sha256']==row['sha256'],'package changed at closure')
            require({name:file_hash(Path(name)) for name in BOOT_FILES}==installed_before,'installed kernel2 changed')
            require(file_hash(INPUTS)['sha256']==INPUT_SHA,'input manifest changed')
            retained_notes=subprocess.run(['/usr/bin/readelf','-n',str(DEST/'build/vmlinux')],check=True,capture_output=True,text=True,timeout=30).stdout
            require(retained_notes==notes,'retained ELF notes differ')
            for directory in sorted((p for p in DEST.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):
                sync_dir(directory)
            sync_dir(DEST)
            groups=[build_files,package_files,receipts]
            manifest=dict(phase='KERNEL2_WITNESS_RETAINED',kernel_code_commit=COMMIT,kernelrelease=RELEASE,
                build_id=BID,source_root=str(SOURCE),build_root=str(BUILD),destination=str(DEST),
                build_files=build_files,package_files=package_files,receipt_files=receipts,
                generated_archive=file_hash(archive_path),generated_member_count=len(generated),
                input_manifest_sha256=INPUT_SHA,installed_kernel2_unchanged=True,current=current,
                copied_regular_files=sum(len(x) for x in groups),
                retained_logical_bytes=sum(row['size'] for group in groups for row in group.values())+archive_path.stat().st_size,
                free_bytes_after={p:available(p) for p in ['/',str(BASE)]},unix=time.time())
            save(DEST/'manifest.json',manifest)
            event('KERNEL2_WITNESS_RETAINED',manifest_sha256=file_hash(DEST/'manifest.json')['sha256'],
                  build_files=len(build_files),package_files=len(package_files),generated_members=len(generated),
                  receipt_files=len(receipts),retained_logical_bytes=manifest['retained_logical_bytes'],free_bytes_after=manifest['free_bytes_after'])
            signal.alarm(0)
        except BaseException as error:
            event('FAILED_RETAIN_PARTIAL',error_type=type(error).__name__,error=str(error));raise
        finally:JOURNAL=None


if __name__=='__main__':main()
