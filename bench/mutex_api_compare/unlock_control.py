#!/usr/bin/env python3
"""Build a separately identified OUTER-acquire/general-unlock pipecap control.

Only one macro in the frozen workload changes. Never rebuild or substitute the
measured provider, translator, client, headers or original control binary.
Run an exact external copy in the recorded recovery VM, while idle.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys

ROOT = Path('/root/host_fs/kdlock')
ORIGINAL = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex-public-20261020-r2')
KERNEL = Path('/root/linux-6.1.159-kdclobber2')
BOOT = '88449cfc-cea9-4647-a294-bc601e372146'
SOURCE = 'workload_modules/real_api/mutex.c'
SOURCE_SHA = '78ea089c8c6e103068f9a4d166e015d0587890a6d78723e96d4a92298dd3ba9e'
SYMVERS = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex-latency-20261021/'
               'inputs-4/export-builds/baseline/provider/kernel_module/Module.symvers')
SYMVERS_SHA = '1f548958d0979e1a484f0cbc6eded6dd04c99f2e46c3ebe4faad467e70ad3cbe'
BINARY = 'build/kdlock-pipecap/real_api.ko'
OLD = b'#define RA_UNLOCK() KD_MUTEX_OUTER_UNLOCK(&kd_lock, cookie)'
NEW = b'#define RA_UNLOCK() KD_MUTEX_DIRECT_UNLOCK(&kd_lock)'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def transform(data):
    require(hashlib.sha256(data).hexdigest() == SOURCE_SHA and data.count(OLD) == 1,
            'expected exact frozen OUTER workload')
    return data.replace(OLD, NEW)


def context(out):
    scheduler = load(ROOT/'bench/mutex_api_compare/run.py', 'unlock_scheduler')
    frozen = scheduler.replay_inputs(ORIGINAL, out)
    harness = scheduler.retained_harness(ORIGINAL)
    for item in frozen.values():
        scheduler.verify(item['files'])
    syn, _, _, api = scheduler.runners(ORIGINAL/'harness', harness)
    syn.idle()
    return scheduler, frozen, harness, syn, api


def elf_audit(path, general):
    """Require the actual OUTER hot RIP and DIRECT terminal call in the ELF."""
    from elftools.elf.elffile import ELFFile
    with path.open('rb') as stream:
        elf = ELFFile(stream)
        require(elf['e_type'] == 'ET_REL' and elf['e_machine'] == 'EM_X86_64',
                'expected relocatable x86-64 caller')
        symbols = elf.get_section_by_name('.symtab')

        def one(name):
            found = symbols.get_symbol_by_name(name) or []
            require(len(found) == 1, 'missing unique symbol ' + name)
            return found[0]

        body, entry, lock = one('rb_body'), one('rb_entry'), one('kd_lock')
        section, start, size = body['st_shndx'], body['st_value'], body['st_size']
        require(isinstance(section, int) and entry['st_shndx'] == section and
                start < entry['st_value'] < start+size, 'hot entry outside body')
        require(lock['st_size'] == 32 and lock['st_value'] % 8 == 0,
                'physical mutex layout changed')
        code = elf.get_section(section).data()
        imports = sorted(s.name for s in symbols.iter_symbols()
                         if s['st_shndx'] == 'SHN_UNDEF' and s.name)
        calls = {}
        for relocs in elf.iter_sections():
            if relocs['sh_type'] != 'SHT_RELA' or relocs['sh_info'] != section:
                continue
            targets = elf.get_section(relocs['sh_link'])
            for relocation in relocs.iter_relocations():
                offset = relocation['r_offset']
                name = targets.get_symbol(relocation['r_info_sym']).name
                if start <= offset < start+size and name.startswith('kd_mutex_'):
                    require(relocation['r_info_type'] in (2, 4) and
                            relocation['r_addend'] == -4 and code[offset-1] == 0xe8,
                            'non-CALL mutex control relocation')
                    calls.setdefault(name, []).append(offset)
        acquire = calls.get('kd_mutex_outer_contended_clobber_v1', [])
        unlock = calls.get('kd_mutex_direct_unlock_clobber_v1', [])
        require(len(acquire) == len(unlock) == 1, 'expected one OUTER and DIRECT call')
        offset = acquire[0]
        capture = bytes.fromhex('4889e6488d150a0000004889e9e8')
        require(code[offset-len(capture):offset] == capture and
                entry['st_value'] == offset+6 and
                code[offset:offset+8] == bytes(4)+bytes.fromhex('eb0231c0'),
                'OUTER saved RIP/physical-return jump/routed entry changed')
        capture = bytes.fromhex('4889e6488d15080000004889e9e8')
        offset = unlock[0]
        require(code[offset-len(capture):offset] == capture,
                'DIRECT unlock capture changed')
        require(('kd_mutex_local_unlock' in imports) != general and
                'kd_mutex_direct_lock_clobber_v1' not in imports,
                'unexpected acquisition/unlock import shell')
        require(not any(name.startswith(('__ubsan_', 'mutex_', '__mutex_'))
                        for name in imports), 'native mutex/UBSAN import')
        return dict(imports=imports, control_calls=calls, body_size=size,
                    entry_in_body=entry['st_value']-start, lock_size=lock['st_size'],
                    lock_section=elf.get_section(lock['st_shndx']).name,
                    lock_offset=lock['st_value'],
                    lock_section_alignment=elf.get_section(lock['st_shndx'])['sh_addralign'],
                    lock_section_relative_mod64=lock['st_value'] % 64)


def validate(scheduler, manifest, digest):
    require(sha(manifest) == digest, 'diagnostic manifest changed')
    data, base = read(manifest), manifest.parent.resolve()
    require(data['kind'] == 'outer-general-unlock-v1' and data['complete'] and
            data['original'] == str(ORIGINAL) and
            data['preparer_sha256'] == sha(Path(__file__)), 'diagnostic identity differs')
    require(data['original_inputs_sha256'] == scheduler.REPLAY_INPUTS_SHA256 and
            data['original_harness_sha256'] == scheduler.REPLAY_HARNESS_SHA256 and
            sha(ORIGINAL/'frozen-inputs.json') == scheduler.REPLAY_INPUTS_SHA256 and
            sha(ORIGINAL/'harness-inputs.json') == scheduler.REPLAY_HARNESS_SHA256,
            'original input manifests changed')
    original = ORIGINAL/'baseline/pipecap'
    bundle = base/'bundle'
    actual = {str(p): sha(p) for p in bundle.rglob('*') if p.is_file()}
    require(actual == data['bundle']['files'] and all(
        not p.is_symlink() and p.resolve().is_relative_to(bundle)
        for p in bundle.rglob('*')), 'bundle membership or containment changed')
    scheduler.verify(data['bundle']['files'])
    before, after = read(original/'source-sha256.json'), read(bundle/'source-sha256.json')
    require(set(before) == set(after) and
            {p for p in before if before[p] != after[p]} == {SOURCE},
            'workload-only source delta changed')
    require((bundle/'source'/SOURCE).read_bytes() ==
            transform((original/'source'/SOURCE).read_bytes()), 'workload overlay differs')
    require(data['bundle']['bundle'] == str(bundle) and
            data['bundle']['source_identity'] == scheduler.identity(after),
            'bundle identity redirected')
    require(data['changed_source'] == SOURCE and data['changed_binary'] == BINARY and
            data['symvers_sha256'] == sha(base/'Module.symvers') == SYMVERS_SHA and
            data['provider_sha256'] == sha(original/'build/kdlock_km.ko') ==
            sha(bundle/'build/kdlock_km.ko') and
            data['original_workload_sha256'] == sha(original/BINARY) and
            data['derivative_workload_sha256'] == sha(bundle/BINARY),
            'declared provider/workload/export identity differs')
    require(sha(bundle/'plan.json') == sha(original/'plan.json'), 'original template changed')
    for relative, expected in after.items():
        require(sha(bundle/'source'/relative) == expected, 'source map differs')
    for filename, expected in scheduler.binary_paths(original, False).items():
        relative = str(Path(filename).relative_to(original))
        if relative != BINARY:
            require(sha(bundle/relative) == expected, 'non-workload binary changed')
    for relative, expected in data['immutable_files'].items():
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts and
                not (base/relative).is_symlink() and (base/relative).resolve().is_relative_to(base) and
                sha(base/relative) == expected,
                'diagnostic input changed: ' + relative)
    return data


def prepare(out, commit):
    require(not out.exists() and not out.is_relative_to(ROOT), 'new external output required')
    scheduler, frozen, harness, syn, _ = context(out)
    out.mkdir(parents=True)
    save(out/'state.json', dict(state='PREPARING', complete=False, source_commit=commit))
    original, bundle = ORIGINAL/'baseline/pipecap', out/'bundle'
    source_map = read(original/'source-sha256.json')
    for relative, expected in source_map.items():
        target = bundle/'source'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original/'source'/relative, target)
        require(sha(target) == expected, 'copied source changed')
    path = bundle/'source'/SOURCE
    path.write_bytes(transform(path.read_bytes()))
    for filename, expected in scheduler.binary_paths(original, False).items():
        target = bundle/Path(filename).relative_to(original)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(filename, target)
        require(sha(target) == expected, 'copied binary changed')
    shutil.copyfile(original/'plan.json', bundle/'plan.json')
    shutil.copyfile(Path(__file__), out/'unlock_control.py')
    shutil.copyfile(Path(scheduler.__file__), out/'scheduler.py')
    require(sha(SYMVERS) == SYMVERS_SHA, 'retained export metadata changed')
    shutil.copyfile(SYMVERS, out/'Module.symvers')
    utilities = load(ROOT/'bench/mutex_api_compare/latency_inputs.py', 'unlock_elf_utilities')
    shutil.copyfile(ROOT/'bench/mutex_api_compare/latency_inputs.py', out/'elf-utilities.py')
    utilities.check_exports(syn, original/'build/kdlock_km.ko', out/'Module.symvers', out/'exports')
    syn.command([sys.executable, ORIGINAL/'harness/bench/spin_cacheline/kernel_identity.py',
        '--kernel-source', KERNEL, '--kernel-baseline',
        '/root/kdlock-kernel-baselines/mutex-clobber2-20260919'], out/'kernel-identity.json', timeout=120)
    build = out/'caller-build'
    build.mkdir()
    for name in ('module.c', 'mutex.c', 'uts.c', 'control.h', 'Makefile'):
        shutil.copyfile(bundle/'source/workload_modules/real_api'/name, build/name)
    syn.command(['make', '-C', build, f'KDIR={KERNEL}', 'RB_BACKEND=kdlock',
        'RB_KIND=PIPECAP', 'RB_MUTEX_API=outer',
        f'KDLOCK_INCLUDE={bundle}/source/include',
        f'TCLOCK_INCLUDE={bundle}/source/tclock_backend/include',
        f'KBUILD_EXTRA_SYMBOLS={out}/Module.symvers'], out/'build.log', timeout=180)
    binary = build/'real_api.ko'
    for label, path in (('original', original/BINARY), ('derivative', binary)):
        syn.command(['objdump', '-dr', path], out/f'{label}-assembly.txt')
        syn.command(['nm', '-u', path], out/f'{label}-imports.txt')
        syn.command(['modprobe', '--dump-modversions', path], out/f'{label}-versions.txt')
    before, after = elf_audit(original/BINARY, False), elf_audit(binary, True)
    require(set(after['imports']) == set(before['imports']) - {'kd_mutex_local_unlock'},
            'unexpected import delta')
    require(all(before[k] == after[k] for k in
                ('lock_size', 'lock_section', 'lock_offset', 'lock_section_alignment',
                 'lock_section_relative_mod64')),
            'mutex object placement changed')
    old_versions = dict(line.split()[::-1] for line in (out/'original-versions.txt').read_text().splitlines())
    new_versions = dict(line.split()[::-1] for line in (out/'derivative-versions.txt').read_text().splitlines())
    require(new_versions == {k: v for k, v in old_versions.items() if k != 'kd_mutex_local_unlock'},
            'caller symbol versions changed beyond removed local unlock')
    save(out/'elf-audit.json', dict(before=before, after=after, symbol_versions_match=True,
        scope='Actual capture/control calls/imports and object layout. Changed shell may change spills; '
              'assembly retained for business-body inspection. No instruction timing inferred.'))
    shutil.copyfile(binary, bundle/BINARY)
    derived = {p: sha(bundle/'source'/p) for p in source_map}
    save(bundle/'source-sha256.json', derived)
    syn.idle()
    for item in frozen.values():
        scheduler.verify(item['files'])
    scheduler.verify(harness)
    item = dict(bundle=str(bundle), source_identity=scheduler.identity(derived),
                files={str(p): sha(p) for p in bundle.rglob('*') if p.is_file()})
    data = dict(kind='outer-general-unlock-v1', complete=True, source_commit=commit,
        original=str(ORIGINAL), original_inputs_sha256=scheduler.REPLAY_INPUTS_SHA256,
        original_harness_sha256=scheduler.REPLAY_HARNESS_SHA256,
        preparer_sha256=sha(Path(__file__)), bundle=item,
        provider_sha256=sha(original/'build/kdlock_km.ko'),
        original_workload_sha256=sha(original/BINARY), derivative_workload_sha256=sha(binary),
        changed_source=SOURCE, changed_binary=BINARY, symvers_sha256=SYMVERS_SHA,
        immutable_files={str(p.relative_to(out)): sha(p) for p in out.rglob('*')
                         if p.is_file() and p.name != 'state.json'}, accepted=False)
    save(out/'inputs.json', data)
    validate(scheduler, out/'inputs.json', sha(out/'inputs.json'))
    save(out/'state.json', dict(state='COMPLETE', complete=True, final_idle=True,
                                manifest_sha256=sha(out/'inputs.json')))
    print(json.dumps(dict(complete=True, manifest=str(out/'inputs.json'), sha256=sha(out/'inputs.json'))))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--source-commit', required=True)
    args = p.parse_args()
    require(os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2' and
            Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT,
            'recorded same recovery VM required')
    require(sys.executable == '/root/kdlock-translation-venv-20261019/bin/python3' and
            shutil.which('python3') == sys.executable and
            re.fullmatch('[0-9a-f]{40}', args.source_commit), 'pinned Python/commit required')
    require(not Path(__file__).resolve().is_relative_to(ROOT) and
            sha(Path(__file__)) == sha(ROOT/'bench/mutex_api_compare/unlock_control.py'),
            'execute an exact external driver copy')
    sys.dont_write_bytecode = True
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    out = args.output.resolve()
    try:
        prepare(out, args.source_commit)
    except BaseException as error:
        if (out/'state.json').exists():
            save(out/'failure.json', dict(passed=False, error=repr(error), drain_established=False))
        raise


if __name__ == '__main__':
    main()
