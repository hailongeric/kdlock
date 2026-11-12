#!/usr/bin/env python3
"""VM-only isolated module build/sign and emitted TCLock context audit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from context_audit import audit


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_kernel_release(expected, running, built):
    if not expected or running != expected or built != expected:
        raise RuntimeError('exact running/build kernel release differs')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--kernel-source', type=Path, required=True)
    parser.add_argument('--kernel-output', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-release', default='7.0.0-38-kdrebuild9',
                        help='Exact running/build release; default preserves the kernel9 baseline')
    parser.add_argument('--backends', nargs='+', choices=('native', 'kdlock', 'tclock'),
                        default=['native', 'kdlock', 'tclock'])
    args = parser.parse_args()
    if len(args.backends) != len(set(args.backends)):
        raise ValueError('duplicate backend selection')
    validate_kernel_release(args.expected_release, os.uname().release,
                            (args.kernel_output / 'include/config/kernel.release').read_text().strip())
    args.output.mkdir()
    result = dict(status='STARTED', kernel_release=os.uname().release, backends=args.backends,
                  commands=[], modules={})

    def save(name, value):
        with (args.output / name).open('x') as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())

    def command(label, argv, seconds=180):
        row = dict(argv=list(map(str, argv)), started_unix=time.time())
        result['commands'].append(row)
        log = args.output / (label + '.log')
        with log.open('xb') as stream:
            child = subprocess.Popen(row['argv'], stdout=stream, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, start_new_session=True,
                env=dict(os.environ, PATH='/usr/sbin:/usr/bin:/sbin:/bin', LC_ALL='C',
                         PYTHONDONTWRITEBYTECODE='1'))
            row['pid'] = child.pid
            save(label + '-started.json', row)
            end = time.monotonic() + seconds
            while child.poll() is None:
                space = os.statvfs(args.output)
                if (time.monotonic() >= end or space.f_bavail * space.f_frsize < 4 * 1024**3 or
                        log.stat().st_size > 128 * 1024**2):
                    row['returncode'] = None
                    save(label + '-incomplete.json', row)
                    raise TimeoutError('build observer ended; original child retained: ' + label)
                time.sleep(0.1)
            stream.flush(); os.fsync(stream.fileno())
        row.update(returncode=child.returncode, elapsed_seconds=time.time() - row['started_unix'],
                   log_sha256=digest(log))
        save(label + '-result.json', row)
        if child.returncode:
            raise RuntimeError('command failed: ' + label)
        return log.read_text()

    tools = ('make', 'x86_64-linux-gnu-gcc', 'as', 'ld', 'objcopy', 'objdump', 'nm', 'modinfo')
    result['tools'] = {}
    for name in tools:
        path = shutil.which(name)
        if not path:
            raise RuntimeError('missing tool: ' + name)
        result['tools'][name] = dict(path=path, resolved=str(Path(path).resolve()), sha256=digest(path))
    result['kernel_files'] = {name: digest(args.kernel_output / name)
                              for name in ('vmlinux', '.config', 'Module.symvers', 'certs/signing_key.x509',
                                           'include/config/kernel.release')}
    sign = args.kernel_output / 'scripts/sign-file'
    result['sign_tool_sha256'] = digest(sign)
    save('started.json', result)

    def build(key, source, name, extra):
        directory = args.output / key
        directory.mkdir()
        command('build-' + key, [result['tools']['make']['path'], '-C', args.kernel_source,
            'O=' + str(args.kernel_output), 'M=' + str(source), 'MO=' + str(directory),
            'KERNELRELEASE=' + args.expected_release, '-j8', 'W=1', 'V=1', *extra, 'modules'])
        unsigned = directory / name
        if sorted(directory.glob('*.ko')) != [unsigned]:
            raise ValueError('unexpected module outputs: ' + key)
        signed = args.output / ('signed-' + key + '.ko')
        with unsigned.open('rb') as src, signed.open('xb') as dst:
            shutil.copyfileobj(src, dst)
            dst.flush(); os.fsync(dst.fileno())
        item = dict(unsigned=str(unsigned), unsigned_sha256=digest(unsigned), signed=str(signed))
        command('sign-' + key, [sign, 'sha512', args.kernel_output / 'certs/signing_key.pem',
                                args.kernel_output / 'certs/signing_key.x509', signed], 60)
        item['signed_sha256'] = digest(signed)
        item['metadata'] = {field: command('metadata-' + key + '-' + field,
            [result['tools']['modinfo']['path'], '-F', field, signed], 30).strip()
            for field in ('vermagic', 'signer', 'sig_key', 'sig_hashalgo', 'depends')}
        metadata = item['metadata']
        if (metadata['vermagic'].split()[0] != args.expected_release or
                not metadata['signer'] or not metadata['sig_key'] or metadata['sig_hashalgo'] != 'sha512'):
            raise ValueError('signed module identity differs: ' + key)
        result['modules'][key] = item
        if key.startswith('tclock-'):
            family = key.removeprefix('tclock-')
            text = command('context-' + key, [result['tools']['objdump']['path'], '-dr',
                                              '--no-show-raw-insn', signed], 60)
            item['emitted_context_audit'] = audit(text, family)
            numa = command('numa-' + key, [result['tools']['modinfo']['path'], '-F', family + '_numa', signed], 30)
            if numa.strip() != '1':
                raise ValueError('TCLock NUMA identity differs')
        else:
            command('source-' + key, [result['tools']['objdump']['path'], '-drw', signed], 60)
        print(json.dumps(dict(built=key, signed_sha256=item['signed_sha256'])), flush=True)
        return directory

    try:
        for family in ('mutex', 'rwsem'):
            if 'tclock' in args.backends:
                tc = build('tclock-' + family, args.repo / 'tclock_backend',
                    'tclock_' + family + '_backend_km.ko',
                    ['TCLOCK_NUMA=1', 'TCLOCK_RWLOCK=0', 'TCLOCK_MUTEX=' + str(int(family == 'mutex')),
                     'TCLOCK_RWSEM=' + str(int(family == 'rwsem'))])
            for backend in args.backends:
                extra = ['RB_LOCK_KIND=' + family, 'RB_BACKEND=' + backend,
                         'KD_SOURCE_ROOT=' + str(args.repo),
                         'TCLOCK_INCLUDE=' + str(args.repo / 'tclock_backend/include')]
                if backend == 'tclock':
                    extra.append('KBUILD_EXTRA_SYMBOLS=' + str(tc / 'Module.symvers'))
                build(family + '-' + backend, args.repo / 'workload_modules/nano', 'kd_nano.ko', extra)
        if result['kernel_files'] != {name: digest(args.kernel_output / name) for name in result['kernel_files']}:
            raise ValueError('kernel build inputs changed')
        result['status'] = 'NANO_MODULES_BUILT_SIGNED'
        save('result.json', result)
        return 0
    except BaseException as error:
        result.update(status='FAILED_OR_INCOMPLETE_RETAINED', error=repr(error))
        save('result.json', result)
        raise


if __name__ == '__main__':
    raise SystemExit(main())
