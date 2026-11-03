#!/usr/bin/env python3
"""Build only the shared-mm fixture/clients against a restored candidate tree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import sys
import subprocess
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt
from elftools.elf.elffile import ELFFile


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda: f.read(1 << 20), b''):
            h.update(data)
    return h.hexdigest()


def split_btf(base, payload, out):
    """Reuse the pahole parser that verified this candidate at installation."""
    tool = Path('/usr/bin/pahole')
    records = []
    for label, argv in [('base', [str(tool), '-F', 'btf', str(base)]),
                        ('split', [str(tool), '-F', 'btf', '--btf_base=' + str(base), str(payload)])]:
        log = out / ('btf-' + label + '.stderr')
        with log.open('w') as errors:
            child = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=errors,
                                     start_new_session=True)
            row = dict(argv=argv, pid=child.pid, timeout_seconds=30,
                       started_ns=time.monotonic_ns(), completion_unconfirmed=True)
            records.append(row)
            rt.write_json(out / 'btf-parse.json', records)
            try:
                row['returncode'] = child.wait(timeout=30)
            except subprocess.TimeoutExpired as error:
                raise rt.Failure('TIMEOUT', 'BTF parser completion unconfirmed; no cleanup', unsafe=True) from error
        row.update(completion_unconfirmed=False, stderr=log.read_text())
        rt.write_json(out / 'btf-parse.json', records)
        rt.require(row['returncode'] == 0 and not row['stderr'], 'BTF parse failed: ' + label)
    return dict(passed=True, tool=str(tool), sha256=sha(tool), method='pahole -F btf, base then split')


def rebuild_client(a, out):
    """Reuse candidate binaries; replace only the explicitly selected client."""
    prior = json.loads(a.reuse_payload.read_text())
    profile = json.loads(Path(__file__).with_name('kdmm31.json').read_text())
    rt.require(prior['passed'] and prior['built_only'] and not prior['modules_loaded'] and
               prior['profile'] == profile, 'matching successful build-only receipt required')
    fixed_only = getattr(a, 'fixed_client_only', False)
    filename = 'client.c' if fixed_only else 'timed_client.c'
    changed_source = str(ROOT / 'bench/mmap_writer' / filename)
    files = {name: digest for name, digest in prior['files'].items() if name != changed_source}
    if fixed_only:
        rt.require(getattr(a, 'prior_source', None) is not None, 'frozen original sources required')
        origin = Path('/root/host_fs/kdlock')
        files = {str(a.prior_source.resolve() / Path(name).relative_to(origin))
                 if Path(name).is_relative_to(origin) else name: digest
                 for name, digest in prior['files'].items()}
    rt.require(all(sha(Path(name)) == digest for name, digest in files.items()), 'reused build input changed')
    manifest = json.loads(a.source_manifest.read_text())
    for name in ('bench/mmap_writer/' + filename, 'bench/mmap_writer/control.h',
                 'workload_modules/mmap_writer/mmap_writer_uapi.h'):
        digest = manifest['files'][name]
        rt.require(sha(ROOT / name) == digest, 'new client source differs: ' + name)
        dest = out / 'source' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dest)
        files[str(dest)] = digest
        if not fixed_only:
            files[str(ROOT / name)] = digest
    target = out / ('fixed' if fixed_only else 'timed')
    rt.command(['gcc', '-O2', '-g', '-Wall', '-Wextra', '-Werror', '-pthread',
                '-I' + str(out / 'source/workload_modules/mmap_writer'),
                out / 'source/bench/mmap_writer' / filename, '-o', target],
               out / ('build-' + target.name + '.log'), timeout=60)
    files[str(target)] = sha(target)
    files[str(a.reuse_payload.resolve())] = sha(a.reuse_payload)
    shutil.copyfile(a.source_manifest, out / 'source-manifest.json')
    return dict(passed=True, built_only=True, modules_loaded=False, booted=False,
                client_only=True, reused_payload=True, profile=profile, files=files,
                binaries=dict(prior['binaries'], **{target.name: str(target)}),
                **(dict(fixed_eligibility_policy='mmap-functional-v1') if fixed_only else {}),
                **(dict(prior_source=str(a.prior_source.resolve())) if fixed_only else {}),
                reused_from=dict(path=str(a.reuse_payload.resolve()), sha256=sha(a.reuse_payload)),
                source_manifest_sha256=sha(a.source_manifest), driver_sha256=sha(Path(__file__)))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kernel-source', type=Path)
    p.add_argument('--reuse-payload', type=Path)
    p.add_argument('--fixed-client-only', action='store_true', help='reuse fixture/timed binary; rebuild fixed userspace only')
    p.add_argument('--prior-source', type=Path, help='frozen original sources for fixed-client-only reconstruction')
    p.add_argument('--source-manifest', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    if a.fixed_client_only and not a.reuse_payload:
        p.error('--fixed-client-only requires --reuse-payload')
    if a.fixed_client_only != bool(a.prior_source):
        p.error('--fixed-client-only and --prior-source must be selected together')
    if bool(a.kernel_source) == bool(a.reuse_payload):
        p.error('select exactly one of --kernel-source or --reuse-payload')
    rt.require(os.geteuid() == 0 and (str(ROOT) == '/root/host_fs/kdlock' or
               (a.fixed_client_only and ROOT.is_relative_to('/root/kdlock-evidence'))) and
               os.uname().release == '6.1.159-kdclobber2', 'idle recovery VM required')
    runpy.run_path(str(ROOT / 'bench/archive_run.py'))['idle'](Path('/root'), rt.idle)
    out = a.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT), 'new private output required')
    out.mkdir(parents=True)
    shutil.copyfile(__file__, out / 'prepare.py')
    shutil.copyfile(Path(__file__).with_name('kdmm31.json'), out / 'profile.json')
    result = dict(passed=False, built_only=True, modules_loaded=False, booted=False,
                  driver_sha256=sha(Path(__file__)))
    try:
        if a.reuse_payload:
            result = rebuild_client(a, out)
            runpy.run_path(str(ROOT / 'bench/archive_run.py'))['idle'](Path('/root'), rt.idle)
            return
        profile = json.loads(Path(__file__).with_name('kdmm31.json').read_text())
        tree = a.kernel_source.resolve()
        bundle = Path(profile['bundle'])
        rt.require(sha(bundle / 'manifest.json') == profile['baseline_manifest_sha256'], 'bundle differs')
        rt.require(sha(tree / 'vmlinux') == profile['vmlinux_sha256'] and
                   sha(tree / 'Module.symvers') == profile['module_symvers_sha256'], 'ELF/CRCs differ')
        verify = runpy.run_path(str(ROOT / 'kernel_baseline/verify.py'))['verify']
        result['kernel_identity'] = verify(bundle, tree, build=True)
        manifest = json.loads(a.source_manifest.read_text())
        selected = {name: h for name, h in manifest['files'].items() if name.startswith(
            ('workload_modules/mmap_writer/', 'bench/mmap_writer/')) and
            (Path(name).suffix in ('.c', '.h', '.inc') or Path(name).name == 'Makefile')}
        rt.require(len(selected) == 6, 'expected payload, two clients and control header')
        files = {}
        for name, h in selected.items():
            rt.require(sha(ROOT / name) == h, 'source changed: ' + name)
            dest = out / 'source' / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, dest)
            files[str(dest)] = files[str(ROOT / name)] = h
        shutil.copyfile(a.source_manifest, out / 'source-manifest.json')
        payload = out / 'source/workload_modules/mmap_writer/kd_mmap_writer_native.ko'
        rt.command(['make', '-C', payload.parent, 'KDIR=' + str(tree), 'W=1', 'UBSAN_SANITIZE=n'],
                   out / 'build-payload.log', timeout=180)
        imports = rt.command(['nm', '-u', payload], out / 'imports.txt')
        rt.require('kd_mmap_is_contended' in imports and not re.search(r'\b(?:kd_(?!mmap_)\w+|komb_\w+|tclock_\w+)\b', imports),
                   'payload must use only the built-in mmap adapter')
        vermagic = rt.command(['modinfo', '-F', 'vermagic', payload], out / 'vermagic.log').strip()
        rt.require(vermagic == profile['release'] + ' SMP preempt mod_unload modversions', 'vermagic differs')
        versions = rt.command(['modprobe', '--dump-modversions', payload], out / 'versions.log')
        known = {r.split()[1]: int(r.split()[0], 16) for r in (tree / 'Module.symvers').read_text().splitlines()}
        used = {r.split()[1]: int(r.split()[0], 16) for r in versions.splitlines()}
        rt.require(used and all(known.get(name) == crc for name, crc in used.items()), 'import CRC differs')
        with (tree / 'vmlinux').open('rb') as f:
            btf = hashlib.sha256(ELFFile(f).get_section_by_name('.BTF').data()).hexdigest()
        with payload.open('rb') as f:
            rt.require(ELFFile(f).get_section_by_name('.BTF') is not None, 'payload has no split BTF')
        rt.require(btf == profile['btf_sha256'], 'BTF base differs')
        result['split_btf'] = split_btf(tree / 'vmlinux', payload, out)
        binaries = dict(payload=str(payload))
        for name, filename in [('fixed', 'client.c'), ('timed', 'timed_client.c')]:
            target = out / name
            rt.command(['gcc', '-O2', '-g', '-Wall', '-Wextra', '-Werror', '-pthread',
                        '-I' + str(payload.parent), out / 'source/bench/mmap_writer' / filename, '-o', target],
                       out / ('build-' + name + '.log'), timeout=60)
            binaries[name] = str(target)
        for path in binaries.values():
            files[path] = sha(Path(path))
        result['kernel_after_build'] = verify(bundle, tree, build=True)
        rt.require(all(sha(Path(path)) == h for path, h in files.items()), 'frozen source/binary changed')
        runpy.run_path(str(ROOT / 'bench/archive_run.py'))['idle'](Path('/root'), rt.idle)
        result.update(passed=True, files=files, binaries=binaries, import_crcs=len(used),
                      profile=profile, profile_sha256=sha(Path(__file__).with_name('kdmm31.json')),
                      base_btf_sha256=btf, source_manifest_sha256=sha(a.source_manifest))
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        rt.write_json(out / 'result.json', result)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
