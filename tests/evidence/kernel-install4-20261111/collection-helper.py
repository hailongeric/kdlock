#!/usr/bin/env python3
"""Read immutable guest receipts and retain exact source-host copies."""
import argparse
import datetime
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import time

REPO = Path('/home/eric/vm/vm-shared/kdlock-main')
BASE = '/mnt/kdlock-builds2/kdlock-main-build-c6becf81-01a1bc4f'
RECEIPTS = BASE + '/receipts'
WORK = '/mnt/kdlock-builds/kdlock-main-work/kernel4-core-2d0ad60b-spin-01'
SSH = ['ssh', '-p', '2222', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', 'root@10.176.26.71']
MAXIMUM = 128 * 1024 * 1024
FILE_MAXIMUM = 48 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    with path.open('xb') as stream:
        stream.write(data)


def document(path, data):
    save(path, (json.dumps(data, indent=2, sort_keys=True) + '\n').encode())


def selected(mode):
    if mode == 'build':
        trees = {'build': RECEIPTS + '/overlay-kdrebuild4-spin-01',
                 'kernel3-retention/preflight': RECEIPTS + '/kernel4-retention-preflight-01'}
        files = {'build-config': BASE + '/build/.config'}
        for name in ('manifest.json', 'journal.jsonl', 'preflight.json',
                     'kernel3-build-id-notes.txt', 'generated-members.json'):
            files['kernel3-retention/' + name] = RECEIPTS + '/retained-kdrebuild3-1b50e373-spin-01/' + name
        for name in ('archive-inputs.json', 'build-inputs.json', 'kdlock-kernel4-build.py',
                     'controller-command.json', 'controller-result.json', 'controller.stdout.log'):
            files['controller/' + name] = WORK + '/' + name
        host = {'kernel3-retention/recovery-controller.json': '/tmp/kdlock-kernel3-retention-recovery-spin-01.json',
                'controller/evidence-plan.md': '/tmp/kdlock-kernel4-evidence-plan.md'}
    else:
        trees = {'install': RECEIPTS + '/install-kdrebuild4-spin-01',
                 'helpers': RECEIPTS + '/kernel4-install-helpers-spin-01',
                 'postboot': RECEIPTS + '/postboot-kdrebuild4-spin-01'}
        files = {name: RECEIPTS + '/overlay-kdrebuild4-spin-01/' + name.rsplit('/', 1)[1]
                 for name in ('build/final-identity.json', 'build/result.json', 'build/gs-config.json')}
        host = {'controller/reconnect.json': '/tmp/kdlock-kernel4-reconnect-spin-01.json',
                'controller/postproof-observer-note.json': '/tmp/kdlock-kernel4-postproof-observer-note.json',
                'controller/ops-recipe.md': '/tmp/kdlock-kdrebuild4-ops.recipe.md'}
    return trees, files, host


INVENTORY = '''import datetime,hashlib,json,pathlib,stat
config=json.loads(CONFIG)
selected=dict(config['files'])
for label,name in config['trees'].items():
 root=pathlib.Path(name)
 assert root.resolve(strict=True)==root and root.is_dir()
 for path in root.rglob('*'):
  assert not path.is_symlink(),str(path)
  if path.is_dir():continue
  key=label+'/'+path.relative_to(root).as_posix()
  assert key not in selected
  selected[key]=str(path)
assert 0<len(selected)<=512
rows={};total=0
for label,name in sorted(selected.items()):
 path=pathlib.Path(name)
 assert path.resolve(strict=True)==path
 before=path.stat()
 assert stat.S_ISREG(before.st_mode) and before.st_size<=FILE_MAX
 h=hashlib.sha256()
 with path.open('rb') as stream:
  for value in iter(lambda:stream.read(4*1024*1024),b''):h.update(value)
 after=path.stat()
 a=(before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)
 b=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
 assert a==b
 rows[label]={'path':name,'bytes':before.st_size,'sha256':h.hexdigest(),
              'dev':before.st_dev,'ino':before.st_ino,'mtime_ns':before.st_mtime_ns,'ctime_ns':before.st_ctime_ns}
 total+=before.st_size
 assert total<=TOTAL_MAX
print(json.dumps({'files':rows,'count':len(rows),'bytes':total,
 'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'scope':'Read-only immutable receipts/configuration. No protocol, build, test, process or live-state operations.'}))
'''
ARCHIVE = '''import hashlib,io,json,pathlib,stat,sys,tarfile
rows=json.loads(ROWS)
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
 for label,row in sorted(rows.items()):
  path=pathlib.Path(row['path']);before=path.stat()
  assert path.resolve(strict=True)==path and stat.S_ISREG(before.st_mode)
  assert (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(row['dev'],row['ino'],row['bytes'],row['mtime_ns'],row['ctime_ns'])
  value=path.read_bytes();after=path.stat()
  assert len(value)==row['bytes'] and hashlib.sha256(value).hexdigest()==row['sha256']
  assert (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)==(row['dev'],row['ino'],row['bytes'],row['mtime_ns'],row['ctime_ns'])
  member=tarfile.TarInfo(label);member.size=len(value);member.mode=0o600
  archive.addfile(member,io.BytesIO(value))
'''


def run(code, timeout):
    argv = SSH + ['timeout ' + str(timeout - 5) + ' python3 -']
    start = time.time()
    result = subprocess.run(argv, input=code.encode(), capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError((argv, result.returncode, result.stderr.decode(errors='replace')))
    record = dict(argv=argv, input_script_sha256=digest(code.encode()), returncode=result.returncode, started_unix=start, finished_unix=time.time(),
                  stdout_bytes=len(result.stdout), stdout_sha256=digest(result.stdout),
                  stderr=result.stderr.decode(errors='replace'))
    return result.stdout, record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('build', 'install'))
    args = parser.parse_args()
    output = REPO / ('tests/evidence/kernel-' + args.mode + '4-20261111')
    if output.exists():
        raise RuntimeError('fresh evidence directory required')
    trees, files, host = selected(args.mode)
    config = json.dumps(dict(trees=trees, files=files))
    code = INVENTORY.replace('CONFIG', repr(config)).replace('FILE_MAX', str(FILE_MAXIMUM)).replace('TOTAL_MAX', str(MAXIMUM))
    raw_index, inventory_command = run(code, 90)
    index = json.loads(raw_index)
    code = ARCHIVE.replace('ROWS', repr(json.dumps(index['files'])))
    archive, copy_command = run(code, 120)
    payloads = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as incoming:
        for member in incoming:
            name = member.name
            if not member.isfile() or name not in index['files'] or name in payloads:
                raise RuntimeError('unexpected copied member: ' + name)
            data = incoming.extractfile(member).read()
            row = index['files'][name]
            if len(data) != row['bytes'] or digest(data) != row['sha256']:
                raise RuntimeError('remote/readback identity differs: ' + name)
            payloads[name] = data
    if set(payloads) != set(index['files']):
        raise RuntimeError('incomplete immutable receipt copy')
    output.mkdir()
    document(output / 'remote-index.json', index)
    copies = []
    for label, data in sorted(payloads.items()):
        compress = len(data) > 131072 and label != 'build-config'
        path = output / (label + '.gz' if compress else label)
        path.parent.mkdir(parents=True, exist_ok=True)
        stored = gzip.compress(data, compresslevel=9, mtime=0) if compress else data
        save(path, stored)
        if (gzip.decompress(path.read_bytes()) if compress else path.read_bytes()) != data:
            raise RuntimeError('stored copy differs: ' + label)
        copies.append(dict(path=str(path.relative_to(output)), encoding='gzip (lossless)' if compress else 'exact bytes',
                           origin_kind='guest immutable receipt', origin_path=index['files'][label]['path'],
                           origin_bytes=len(data), origin_sha256=digest(data), storage_bytes=len(stored),
                           storage_sha256=digest(stored)))
    for label, origin in sorted(host.items()):
        data = Path(origin).read_bytes()
        path = output / label
        path.parent.mkdir(parents=True, exist_ok=True)
        save(path, data)
        copies.append(dict(path=label, origin_kind='source-host retained artifact', origin_path=origin,
                           origin_bytes=len(data), origin_sha256=digest(data), storage_bytes=len(data),
                           storage_sha256=digest(data), encoding='exact bytes'))
    document(output / 'copy-index.json', dict(copies=copies, remote_files=index['count'], remote_bytes=index['bytes']))
    document(output / 'collection.json', dict(commands=[inventory_command, copy_command],
             archive_bytes=len(archive), archive_sha256=digest(archive),
             scope='Only receipt/configuration reads and source-host lossless copies. No guest writes, process inspection, protocol commands, builds, tests or module operations.'))
    print(json.dumps(dict(path=str(output), remote_files=index['count'], remote_bytes=index['bytes'],
                         retained_files=len(copies), stored_bytes=sum(p.stat().st_size for p in output.rglob('*') if p.is_file())), indent=2))


if __name__ == '__main__':
    main()
