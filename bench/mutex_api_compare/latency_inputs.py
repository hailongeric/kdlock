#!/usr/bin/env python3
"""Prepare private operation-latency callers against the original mutex inputs.

Builds run only in the original recovery VM. Original providers, translators,
collectors and controls remain immutable. Provider/backend builds below produce
export metadata for caller compilation; the run loads the original binaries.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys

sys.dont_write_bytecode = True
ROOT = Path('/root/host_fs/kdlock')
ORIGINAL = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex-public-20261020-r2')
KERNEL = Path('/root/linux-6.1.159-kdclobber2')
GROUPS = ('c08', 'rcuht', 'pipebytes', 'pipecap')
TOOLS = ('latency.py', 'latency_overlay.py', 'latency_inputs.py', 'latency_run.py')
PAYLOADS = ('operation_latency.h', 'kernel.inc', 'client.inc')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require(value, message):
    if not value:
        raise ValueError(message)


def body_fingerprint(path, name):
    """Preserve body bytes and canonical relocation targets, including objects."""
    from elftools.elf.elffile import ELFFile
    with path.open('rb') as stream:
        elf = ELFFile(stream)
        require(elf['e_machine'] == 'EM_X86_64' and elf['e_type'] == 'ET_REL',
                'body audit requires x86-64 relocatable ELF')
        table = elf.get_section_by_name('.symtab')
        symbols = list(table.iter_symbols())
        matches = table.get_symbol_by_name(name)
        require(matches and len(matches) == 1, 'missing unique body '+name)
        body = matches[0]
        section, start, size = body['st_shndx'], body['st_value'], body['st_size']
        require(isinstance(section, int) and size > 0, 'invalid body extent')
        code = bytearray(elf.get_section(section).data()[start:start+size])
        relocations = []
        for relocs in elf.iter_sections():
            if relocs['sh_type'] != 'SHT_RELA' or relocs['sh_info'] != section:
                continue
            targets = elf.get_section(relocs['sh_link'])
            for relocation in relocs.iter_relocations():
                offset = relocation['r_offset']
                if not start <= offset < start+size:
                    continue
                kind, addend = relocation['r_info_type'], relocation['r_addend']
                require(kind in (1, 2, 4, 10, 11), 'unreviewed body relocation')
                width = 8 if kind == 1 else 4
                require(offset+width <= start+size, 'relocation crosses body end')
                target = targets.get_symbol(relocation['r_info_sym'])
                if target['st_info']['type'] == 'STT_SECTION':
                    value = target['st_value']+addend+(4 if kind in (2, 4) else 0)
                    objects = [s for s in symbols if s['st_shndx'] == target['st_shndx'] and
                               s['st_info']['type'] in ('STT_OBJECT', 'STT_FUNC') and
                               s['st_size'] > 0 and s['st_value'] <= value < s['st_value']+s['st_size']]
                    require(len(objects) == 1, 'ambiguous section-relative body target')
                    symbol = objects[0]
                    canonical = (symbol.name, value-symbol['st_value'])
                else:
                    canonical = (target.name, addend)
                code[offset-start:offset-start+width] = bytes(width)
                relocations.append((offset-start, kind, canonical))
        return dict(bytes=len(code), normalized_sha256=hashlib.sha256(code).hexdigest(),
                    relocations=relocations)


def original_inputs(scheduler, out):
    frozen = scheduler.replay_inputs(ORIGINAL, out)
    harness = scheduler.retained_harness(ORIGINAL)
    for bundle in frozen.values():
        scheduler.verify(bundle['files'])
    return frozen, harness


def validate(scheduler, manifest, expected_hash):
    require(sha(manifest) == expected_hash, 'latency manifest hash changed')
    data, base = read(manifest), manifest.parent.resolve()
    require(data['complete'] and data['kind'] == 'complete-operation-latency-v1' and
            data['original'] == str(ORIGINAL), 'latency input identity differs')
    require(data['preparer_sha256'] == sha(Path(__file__)), 'latency preparer changed')
    overlay = load(base/'tools/latency_overlay.py', 'validated_latency_overlay')
    original, harness = original_inputs(scheduler, base.parent/'unused-validation-output')
    require(data['original_inputs_sha256'] == scheduler.REPLAY_INPUTS_SHA256 and
            data['original_harness_sha256'] == scheduler.REPLAY_HARNESS_SHA256,
            'latency original manifests differ')
    require(set(data['bundles']) == {v+'/'+g for v in ('baseline', 'current') for g in GROUPS},
            'latency bundle set differs')
    for relative, expected in data['immutable_files'].items():
        path = base/relative
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts and
                path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(base) and
                sha(path) == expected, 'latency input changed: '+relative)
    for key, item in data['bundles'].items():
        bundle = base/'bundles'/key
        require(item['bundle'] == str(bundle), 'latency bundle redirected')
        scheduler.verify(item['files'])
        old = Path(original[key]['bundle'])
        source, previous = read(bundle/'source-sha256.json'), read(old/'source-sha256.json')
        require(set(source)-set(previous) == set(item['source_additions']) and
                set(previous) <= set(source), 'unexpected latency source set')
        require({p for p in previous if previous[p] != source[p]} == {item['changed_source']},
                'unexpected latency source change')
        synthetic = key.split('/')[1] in ('c08', 'rcuht')
        changed = ('workload_modules/spin_cacheline/runner.inc' if synthetic
                   else 'bench/real_api/client.c')
        additions = ({'workload_modules/spin_cacheline/operation_latency.h': 'operation_latency.h',
                      'workload_modules/spin_cacheline/latency_kernel.inc': 'kernel.inc'}
                     if synthetic else
                     {'bench/real_api/operation_latency.h': 'operation_latency.h',
                      'bench/real_api/latency_client.inc': 'client.inc'})
        require(item['changed_source'] == changed and item['source_additions'] == additions,
                'latency source recipe differs')
        transform = overlay.synthetic if synthetic else overlay.api_client
        require((bundle/'source'/changed).read_bytes() ==
                transform((old/'source'/changed).read_bytes()), 'latency overlay differs')
        for p, name in additions.items():
            require((bundle/'source'/p).read_bytes() == (base/'tools'/name).read_bytes(),
                    'latency payload differs')
        changed_binaries = ([f'variants/{backend}/mutex_cacheline.ko' for backend in
                             (('kdlock',) if key.startswith('baseline/') else
                              ('kdlock', 'native', 'tclock'))] if synthetic else ['build/client'])
        require(item['changed_binaries'] == changed_binaries and
                set(item['binaries']) == {str(Path(p).relative_to(old))
                                         for p in scheduler.binary_paths(old, synthetic)},
                'latency binary recipe differs')
        for p, expected in source.items():
            require(sha(bundle/'source'/p) == expected, 'latency source map changed')
        require(item['source_identity'] == scheduler.identity(source), 'latency source identity differs')
        for relative, pair in item['binaries'].items():
            require(sha(bundle/relative) == pair['sha256'] and sha(old/relative) == pair['original_sha256'],
                    'latency binary identity differs')
            if relative not in item['changed_binaries']:
                require(pair['sha256'] == pair['original_sha256'], 'unchanged binary was replaced')
    return data, original, harness


def prepare(out, source_commit):
    require(not out.exists() and not out.is_relative_to(ROOT), 'new external input directory required')
    scheduler = load(ROOT/'bench/mutex_api_compare/run.py', 'latency_scheduler')
    overlay = load(ROOT/'bench/mutex_api_compare/latency_overlay.py', 'latency_overlay')
    original, harness = original_inputs(scheduler, out)
    syn, _, _, _ = scheduler.runners(ORIGINAL/'harness', harness)
    syn.idle()
    out.mkdir(parents=True)
    save(out/'state.json', dict(complete=False, state='PREPARING', source_commit=source_commit))
    tools = out/'tools'
    tools.mkdir()
    for name in TOOLS:
        shutil.copyfile(ROOT/'bench/mutex_api_compare'/name, tools/name)
    shutil.copyfile(ROOT/'bench/mutex_api_compare/run.py', tools/'scheduler.py')
    shutil.copyfile(ROOT/'bench/archive_run.py', tools/'archive_run.py')
    for name in PAYLOADS:
        shutil.copyfile(ROOT/'workload_modules/latency'/name, tools/name)
    # Only generated symbol metadata from these builds is used by new callers.
    # Their newly linked provider/backend binaries are never selected for a run.
    exports = {}
    for version in ('baseline', 'current'):
        old = ORIGINAL/version/'c08'
        source = old/'source/bench/spin_cacheline/.build/provider'
        manifest = read(source/'manifest.json')
        target = out/'export-builds'/version/'provider'
        for p, expected in manifest['prepared'].items():
            require(sha(source/p) == expected, 'original prepared provider changed')
            dest = target/p
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source/p, dest)
        command = ['make', '-C', target/'kernel_module', f'KDIR={KERNEL}', 'W=1',
                   'KDLOCK_SELFTEST=0', 'KDLOCK_NUMA=1', 'KDLOCK_SPIN_BATCH=1024', 'UBSAN_SANITIZE=n']
        syn.command(command, out/f'export-build-{version}-provider.log', timeout=240)
        exports[version] = target/'kernel_module/Module.symvers'
        old_binary = old/'binaries/kdlock_km.ko'
        check_exports(syn, old_binary, exports[version], out/f'exports-{version}')
        require(all(sha(target/p) == expected for p, expected in manifest['prepared'].items()),
                'export build changed frozen source bytes')
    old = ORIGINAL/'current/c08'
    tc = out/'export-builds/tclock'
    for p, expected in read(old/'source-sha256.json').items():
        if p.startswith('tclock_backend/'):
            dest = tc/Path(p).relative_to('tclock_backend')
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(old/'source'/p, dest)
            require(sha(dest) == expected, 'original TCLock source changed')
    syn.command(['make', '-C', tc, 'TCLOCK_NUMA=1', 'TCLOCK_MUTEX=1', f'KDIR={KERNEL}'],
                out/'export-build-tclock.log', timeout=240)
    exports['tclock'] = tc/'Module.symvers'
    check_exports(syn, old/'binaries/tclock_mutex_backend_km.ko', exports['tclock'], out/'exports-tclock')

    bundles, body_audits = {}, {}
    for version in ('baseline', 'current'):
        for group in GROUPS:
            key = version+'/'+group
            old, bundle = ORIGINAL/key, out/'bundles'/key
            source = bundle/'source'
            old_map = read(old/'source-sha256.json')
            for p, expected in old_map.items():
                dest = source/p
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(old/'source'/p, dest)
                require(sha(dest) == expected, 'original source changed: '+key+'/'+p)
            binaries, changed_binaries = {}, []
            for filename, expected in scheduler.binary_paths(old, group in ('c08', 'rcuht')).items():
                relative = str(Path(filename).relative_to(old))
                dest = bundle/relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(filename, dest)
                require(sha(dest) == expected, 'copied original binary changed')
                binaries[relative] = dict(original_sha256=expected, sha256=expected)
            shutil.copyfile(old/'plan.json', bundle/'plan.json')
            if group in ('c08', 'rcuht'):
                changed_source = 'workload_modules/spin_cacheline/runner.inc'
                shared = source/'workload_modules/spin_cacheline'
                (source/changed_source).write_bytes(overlay.synthetic((source/changed_source).read_bytes()))
                additions = {'workload_modules/spin_cacheline/operation_latency.h': 'operation_latency.h',
                             'workload_modules/spin_cacheline/latency_kernel.inc': 'kernel.inc'}
                for p, name in additions.items():
                    shutil.copyfile(tools/name, source/p)
                backends = ('kdlock',) if version == 'baseline' else ('kdlock', 'native', 'tclock')
                for backend in backends:
                    build = out/'caller-builds'/version/group/backend
                    build.mkdir(parents=True)
                    for name in ('module.c', 'Makefile'):
                        shutil.copyfile(source/'workload_modules/mutex_cacheline'/name, build/name)
                    arguments = ['make', '-C', build, f'KDIR={KERNEL}', f'SC_BACKEND={backend}',
                        'SC_WORKLOAD='+('cacheline' if group == 'c08' else 'rcuht'),
                        'SC_MUTEX_API='+('outer' if version == 'baseline' else 'public'), 'SC_SCENARIO=0',
                        f'KDLOCK_INCLUDE={source}/include', f'SC_SHARED={shared}',
                        f'TCLOCK_INCLUDE={source}/tclock_backend/include']
                    if backend != 'native':
                        arguments += ['KBUILD_EXTRA_SYMBOLS='+str(exports['tclock' if backend == 'tclock' else version])]
                    syn.command(arguments, out/f'build-{version}-{group}-{backend}.log', timeout=180)
                    relative = f'variants/{backend}/mutex_cacheline.ko'
                    binary = build/'mutex_cacheline.ko'
                    name = 'mc_body_8' if group == 'c08' else 'mc_body_0'
                    before, after = body_fingerprint(old/relative, name), body_fingerprint(binary, name)
                    body_audits[key+'/'+backend] = dict(before=before, after=after, equal=before == after)
                    save(out/'body-audits.json', body_audits)
                    require(before == after, 'latency overlay changed measured body: '+key+'/'+backend)
                    syn.command(['objdump', '-dr', binary], out/f'assembly-{version}-{group}-{backend}.txt', timeout=30)
                    shutil.copyfile(binary, bundle/relative)
                    changed_binaries.append(relative)
            else:
                changed_source = 'bench/real_api/client.c'
                (source/changed_source).write_bytes(overlay.api_client((source/changed_source).read_bytes()))
                additions = {'bench/real_api/operation_latency.h': 'operation_latency.h',
                             'bench/real_api/latency_client.inc': 'client.inc'}
                for p, name in additions.items():
                    shutil.copyfile(tools/name, source/p)
                syn.command(['gcc', '-O2', '-g', '-Wall', '-Wextra', '-Werror', '-std=gnu11', '-pthread',
                             source/changed_source, '-o', bundle/'build/client'],
                            out/f'build-{version}-{group}-client.log', timeout=60)
                changed_binaries.append('build/client')
            derived = {p: sha(source/p) for p in (*old_map, *additions)}
            save(bundle/'source-sha256.json', derived)
            for p in changed_binaries:
                binaries[p]['sha256'] = sha(bundle/p)
            bundles[key] = dict(bundle=str(bundle), changed_source=changed_source,
                source_additions=additions, changed_binaries=changed_binaries, binaries=binaries,
                source_identity=scheduler.identity(derived),
                files={str(p): sha(p) for p in bundle.rglob('*') if p.is_file()})
    syn.idle()
    for item in original.values():
        scheduler.verify(item['files'])
    scheduler.verify(harness)
    result = dict(kind='complete-operation-latency-v1', complete=True, original=str(ORIGINAL),
        source_commit=source_commit, preparer_sha256=sha(Path(__file__)),
        original_inputs_sha256=scheduler.REPLAY_INPUTS_SHA256,
        original_harness_sha256=scheduler.REPLAY_HARNESS_SHA256, bundles=bundles,
        immutable_files={str(p.relative_to(out)): sha(p) for p in out.rglob('*')
                         if p.is_file() and p.name != 'state.json'},
        scope='Private callers only; measured providers and translated bodies retain original identities')
    save(out/'inputs.json', result)
    validate(scheduler, out/'inputs.json', sha(out/'inputs.json'))
    save(out/'state.json', dict(complete=True, state='COMPLETE', idle=True,
                               manifest_sha256=sha(out/'inputs.json')))
    print(json.dumps(dict(complete=True, manifest=str(out/'inputs.json'), sha256=sha(out/'inputs.json'))))


def export_crcs(binary):
    """Read the actual CRC words in the original module, not a rebuilt proxy."""
    from elftools.elf.elffile import ELFFile
    with binary.open('rb') as stream:
        elf = ELFFile(stream)
        require(elf['e_machine'] == 'EM_X86_64', 'unexpected export ELF architecture')
        symbols = list(elf.get_section_by_name('.symtab').iter_symbols())
        exports = {s.name.removeprefix('__ksymtab_') for s in symbols
                   if s.name.startswith('__ksymtab_')}
        crcs = {}
        for symbol in symbols:
            if not symbol.name.startswith('__crc_'):
                continue
            index, offset = symbol['st_shndx'], symbol['st_value']
            require(isinstance(index, int), 'export CRC must be a retained section word')
            section = elf.get_section(index)
            require(section.name in ('__kcrctab', '__kcrctab_gpl') and
                    0 <= offset <= section.data_size-4 and offset % 4 == 0,
                    'unexpected export CRC location')
            require(not any(s['sh_type'] in ('SHT_REL', 'SHT_RELA') and s['sh_info'] == index
                            for s in elf.iter_sections()), 'relocated export CRC needs separate review')
            name = symbol.name.removeprefix('__crc_')
            require(name not in crcs, 'duplicate export CRC')
            crcs[name] = struct.unpack_from('<I', section.data(), offset)[0]
        require(exports and set(crcs) == exports, 'export names and CRCs differ')
        return crcs


def check_exports(syn, binary, symvers, output):
    vermagic = syn.command(['modinfo', '-F', 'vermagic', binary], output.with_suffix('.vermagic.txt'))
    require('modversions' in vermagic, 'original MODVERSIONS kernel required')
    syn.command(['nm', '--defined-only', binary], output.with_suffix('.symbols.txt'))
    expected = export_crcs(binary)
    rows = [line.split() for line in symvers.read_text().splitlines()]
    actual = {r[1]: int(r[0], 16) for r in rows}
    require(len(actual) == len(rows) and actual == expected,
            'rebuilt export names/CRCs differ from the original loaded backend')
    save(output.with_suffix('.crc.json'), dict(original=expected, rebuilt=actual, equal=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-commit', required=True)
    args = parser.parse_args()
    require(os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2' and
            Path('/proc/sys/kernel/random/boot_id').read_text().strip() ==
            'b65f0205-c8f9-4385-8b13-039cbce243a6', 'original recovery VM required')
    require(not Path(__file__).resolve().is_relative_to(ROOT) and
            sha(Path(__file__)) == sha(ROOT/'bench/mutex_api_compare/latency_inputs.py'),
            'execute a byte-matched external copy; retain collector-origin checks')
    require(sys.executable == '/root/kdlock-translation-venv-20261019/bin/python3' and
            shutil.which('python3') == sys.executable and
            re.fullmatch(r'[0-9a-f]{40}', args.source_commit), 'pinned Python and source revision required')
    out = args.output.resolve()
    try:
        prepare(out, args.source_commit)
    except BaseException as error:
        if (out/'state.json').is_file():
            save(out/'failure.json', dict(complete=False, error=repr(error)))
        raise


if __name__ == '__main__':
    main()
