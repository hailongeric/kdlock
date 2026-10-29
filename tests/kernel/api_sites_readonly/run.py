#!/usr/bin/env python3
"""VM-only build or live proof; source may live in an external frozen DATA copy."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BUILD = Path('/mnt/kdlock-builds/linux-7.0.0-38-kdscope1/build')
RELEASE = '7.0.0-38-kdscope1'
CONFIG_SHA = '7131e48d4bb556e54f9fc287c04e6fab33a3de80eb923a215872a01a07609f4b'
SYMVERS_SHA = 'e28cfc4bb5d25918157353fa0aeca12b741018c0f988d4f0ada2159f508dac6b'
MODULE = 'kd_api_sites_readonly'
FILES = ('README.md', 'run.py', 'payload/Makefile', 'payload/module.c')


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked(path, expected):
    require(path.is_absolute() and path.resolve() == path and path.is_file() and
            re.fullmatch('[0-9a-f]{64}', expected or '') and sha(path) == expected,
            'reviewed file/hash differs: '+str(path))
    return json.loads(path.read_text())


def build_id(data):
    offset, found = 0, []
    while offset < len(data):
        require(len(data)-offset >= 12, 'truncated live note')
        size, length, kind = struct.unpack_from('<III', data, offset)
        start = offset+12
        desc = start+((size+3)&~3)
        end = desc+((length+3)&~3)
        require(end <= len(data), 'truncated live note payload')
        if data[start:start+size] == b'GNU\0' and kind == 3:
            found.append(data[desc:desc+length].hex())
        offset = end
    require(len(found) == 1, 'exactly one live Build ID required')
    return found[0]


def idle():
    for path in Path('/sys/module').iterdir():
        require(not path.name.startswith(('kd_', 'kdlock', 'tc_', 'tclock_', 'jit_')),
                'project module still loaded: '+path.name)
    for path in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
        try:
            name = path.read_text().strip()
        except (FileNotFoundError, ProcessLookupError):
            continue
        require(name not in ('daemon', 'make', 'cc1', 'ld.bfd', 'mmap1_threads', 'mmap1_processes')
                and not name.startswith(('kd_', 'kdlock', 'sc_worker', 'mw_worker', 'mw_time_worker')),
                'project/build task still running: '+name)


def validate_report(value, audit):
    address = int(audit['site_table_address'], 16)
    require(value.get('schema') == 1 and value.get('readonly') is True and
            value.get('bytes') == 48 and int(value['address'], 16) == address,
            'live table identity differs')
    expected = [address]
    if address >> 12 != (address+47) >> 12:
        expected.append((address & ~4095)+4096)
    pages = value['pages']
    require([int(row['address'], 16) for row in pages] == expected and
            all(row['level'] in (1, 2, 3) and int(row['entry'], 16) & 1 and
                not int(row['entry'], 16) & 6 for row in pages), 'live table leaf is not present/read-only/kernel')
    rows = value['sites']
    require(len(rows) == 3 and {row['site'] for row in rows} == {1, 2, 3} and
            all(row['reserved'] == 0 for row in rows), 'invalid live table rows')
    raw = b''.join(struct.pack('<QII', int(row['entry'], 16), row['site'], row['reserved']) for row in rows)
    require(hashlib.sha256(raw).hexdigest() == audit['site_table_sha256'], 'live/linked table bytes differ')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('build', 'verify'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--boot-id', required=True)
    p.add_argument('--snapshot', required=True)
    p.add_argument('--probe-commit', required=True)
    for name in ('source-manifest', 'preinstall-result', 'linked-audit'):
        p.add_argument('--'+name, type=Path, required=True)
        p.add_argument('--'+name+'-sha256', required=True)
    p.add_argument('--build-result', type=Path)
    p.add_argument('--build-result-sha256')
    a = p.parse_args()
    require(os.geteuid() == 0 and os.uname().release in (RELEASE, '7.0.0-38-kdlock1') and
            str(HERE).startswith('/mnt/kdlock-builds/') and not os.environ.get('KERNELRELEASE') and
            not os.environ.get('KBUILD_OUTPUT'), 'VM root and frozen external DATA source required')
    require(os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
            os.environ.get('KDLOCK_SNAPSHOT_TAG') == a.snapshot, 'confirmed real recovery snapshot required')
    require(a.output.is_absolute() and a.output.is_relative_to(Path('/mnt/kdlock-builds')) and
            not a.output.is_relative_to(HERE) and not a.output.exists(), 'new separate DATA output required')
    a.output.mkdir(parents=True)
    result = dict(schema=1, action=a.action, passed=False, drained=False, drain_unknown=False,
                  boot_id=a.boot_id, recovery_snapshot=a.snapshot, probe_commit=a.probe_commit, build=str(BUILD),
                  release=RELEASE, commands=[], mutation='probe storage and ordinary module lifecycle only')
    child = None

    def save():
        temporary = a.output/'result.tmp'
        with temporary.open('w') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        temporary.replace(a.output/'result.json')

    def command(label, argv, timeout=60):
        nonlocal child
        row = dict(label=label, argv=list(map(str, argv)))
        result['commands'].append(row)
        with (a.output/(label+'.log')).open('x') as log:
            child = subprocess.Popen(row['argv'], cwd=a.output, stdout=log, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, start_new_session=True,
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', LC_ALL='C'))
            row['pid'] = child.pid; save()
            code = child.wait(timeout=timeout)
            row['returncode'] = code; row['log_sha256'] = sha(a.output/(label+'.log')); save()
            require(code == 0, 'command failed: '+label)
        child = None
        return (a.output/(label+'.log')).read_text()

    def boot():
        require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == a.boot_id, 'boot changed')

    def source_files():
        manifest = checked(a.source_manifest, a.source_manifest_sha256)
        require(manifest.get('schema') == 1 and manifest.get('commit') == a.probe_commit and
                re.fullmatch('[0-9a-f]{40}', a.probe_commit) and set(manifest['files']) == set(FILES),
                'probe source manifest scope/commit differs')
        for name, expected in manifest['files'].items():
            require((HERE/name).resolve() == HERE/name and sha(HERE/name) == expected,
                    'frozen probe source changed: '+name)
        return manifest

    save()
    try:
        boot(); idle()
        manifest = source_files()
        pre = checked(a.preinstall_result, a.preinstall_result_sha256)
        audit = checked(a.linked_audit, a.linked_audit_sha256)
        require(pre.get('passed') is True and pre.get('state') == 'PREINSTALL_ARTIFACTS_VERIFIED_NOT_INSTALLED'
                and pre.get('source_commit') == '8446f4ecb08816380a4c233197a8ce5e4d333aac'
                and pre.get('release') == RELEASE and pre['linked_audit_sha256'] == a.linked_audit_sha256,
                'original kernel linked proof differs')
        require(sha(BUILD/'.config') == CONFIG_SHA and sha(BUILD/'Module.symvers') == SYMVERS_SHA and
                sha(BUILD/'vmlinux') == audit['vmlinux_sha256'], 'scope build/config/ELF differs')
        exports = {line.split()[1]:line.split() for line in (BUILD/'Module.symvers').read_text().splitlines()}
        require(all(name in exports and exports[name][2] == 'vmlinux' and
                    exports[name][3] in ('EXPORT_SYMBOL', 'EXPORT_SYMBOL_GPL')
                    for name in ('lookup_address', 'kd_api_sites')), 'required built-in lookup exports absent')
        result.update(source_manifest_sha256=a.source_manifest_sha256,
                      preinstall_result_sha256=a.preinstall_result_sha256, linked_audit_sha256=a.linked_audit_sha256,
                      config_sha256=CONFIG_SHA, symvers_sha256=SYMVERS_SHA,
                      vmlinux_sha256=audit['vmlinux_sha256'], exports={name:exports[name] for name in ('lookup_address','kd_api_sites')})
        if a.action == 'build':
            target = a.output/'payload'; target.mkdir()
            for name in ('Makefile', 'module.c'):
                shutil.copyfile(HERE/'payload'/name, target/name)
            command('build', ['make', '-C', target, 'KDIR='+str(BUILD),
                'CC=x86_64-linux-gnu-gcc', 'W=1'], 600)
            copied = {name:sha(target/name) for name in ('Makefile', 'module.c')}
            require(all(value == manifest['files']['payload/'+name] for name, value in copied.items()),
                    'copied probe source changed during build')
            result['build_source_sha256'] = copied
            module = target/(MODULE+'.ko')
            require(command('vermagic', ['modinfo','-F','vermagic',module]).split()[0] == RELEASE,
                    'module release differs')
            require(not command('intree', ['modinfo','-F','intree',module]).strip(), 'probe must retain honest external-module metadata')
            signer = command('signer', ['modinfo','-F','signer',module]).strip()
            result.update(module=str(module), module_sha256=sha(module), signer=signer)
        else:
            require(os.uname().release == RELEASE and a.build_result is not None, 'scope boot and build receipt required')
            built = checked(a.build_result, a.build_result_sha256)
            require(built.get('passed') is True and built.get('action') == 'build' and
                    all(built.get(key) == result[key] for key in ('probe_commit','build','source_manifest_sha256',
                        'linked_audit_sha256','config_sha256','symvers_sha256','vmlinux_sha256')), 'probe build generation differs')
            module = Path(built['module'])
            require(module.is_absolute() and module.is_relative_to(Path('/mnt/kdlock-builds')) and
                    module.resolve() == module and sha(module) == built['module_sha256'], 'built module changed')
            cmdline = Path('/proc/cmdline').read_text().split()
            require('nokaslr' in cmdline and not any(word in ('rodata=off','rodata=0') for word in cmdline) and
                    len([word for word in cmdline if word in ('kd_mmap=off','kd_mmap=on')]) == 1,
                    'explicit fixed-address scope boot required')
            notes = command('build-id', ['readelf','-n',BUILD/'vmlinux'])
            ids = re.findall(r'Build ID: ([0-9a-f]+)', notes)
            require(len(ids) == 1 and build_id(Path('/sys/kernel/notes').read_bytes()) == ids[0], 'live/build Build ID differs')
            taint = Path('/proc/sys/kernel/tainted')
            before = int(taint.read_text()); require(before == 0, 'fresh untainted scope boot required')
            expected = (1 << 12) | (0 if built['signer'] else 1 << 13)
            result.update(build_result_sha256=a.build_result_sha256, module_sha256=built['module_sha256'],
                          build_id=ids[0], cmdline=' '.join(cmdline), taint_before=before,
                          expected_taint=expected, drain_unknown=True, state='LOAD_STARTED')
            save()
            command('load', ['insmod',module,'expected_address='+audit['site_table_address']])
            value = json.loads((Path('/sys/module')/MODULE/'parameters/report').read_text())
            result['report'] = value; save(); validate_report(value,audit)
            require(int(taint.read_text()) == expected, 'unexpected taint after probe load')
            command('unload', ['rmmod', MODULE])
            require(not (Path('/sys/module')/MODULE).exists() and sha(module) == built['module_sha256'] and
                    int(taint.read_text()) == expected, 'probe unload/module/taint differs')
            result.update(taint_after=expected, unloaded=True)
        boot(); idle(); require(source_files() == manifest, 'probe source changed')
        result.update(state='COMPLETE', passed=True, drained=True, drain_unknown=False, final_idle=True)
        save()
    except BaseException as error:
        result.update(state='FAILED', passed=False, error=repr(error),
                      child_returncode=child.poll() if child is not None else None)
        if child is not None or result.get('action') == 'verify' and result.get('state') != 'COMPLETE':
            result['drain_unknown'] = True
        save()
        raise
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
