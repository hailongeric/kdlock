#!/usr/bin/env python3
"""Build and verify the isolated d21 + 003d71c entry-inlining experiment.

This is a private provider experiment, not a build of the current whole tree.
The original comparison remains immutable. Every public workload retains its
original caller, client, daemon and translator; only the provider is rebuilt.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import time

ROOT = Path('/root/host_fs/kdlock')
GROUPS = ('c08', 'rcuht', 'pipebytes', 'pipecap')
ENTRY = 'kernel_module/lock/mutex_calls.inc'
OLD_ENTRY = '0d201fc6fbb0514e1cefdea2237e35ff2b9dc67432db53592224552fd269ace3'
NEW_ENTRY = 'd7a9378ae0294bf6d16882d1b8fbeb137fd41a24299e1e9f016a3f8849d224af'
PATCH_COMMIT = '003d71c6994f7eb4b58536f95fc5adfa7efa1628'
PREPARED = 'bench/spin_cacheline/.build/provider/'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def provider_inputs(sources):
    """Select raw production and observation inputs, excluding prepared copies."""
    return {p: h for p, h in sources.items()
            if p.startswith(('include/', 'kernel_module/', 'bench/spin_cacheline/provider/'))
            or p == 'bench/spin_cacheline/Makefile'}


def validate_source_delta(original, derived, prepared_manifest_hash=None):
    require(set(original) == set(derived), 'derived source set changed')
    require(original[ENTRY] == OLD_ENTRY and derived[ENTRY] == NEW_ENTRY,
            'entry before/after hashes differ from reviewed patch')
    expected = {ENTRY}
    if PREPARED + ENTRY in original:
        require(original[PREPARED + ENTRY] == OLD_ENTRY
                and derived[PREPARED + ENTRY] == NEW_ENTRY,
                'prepared entry differs')
        require(prepared_manifest_hash is not None
                and derived[PREPARED + 'manifest.json'] == prepared_manifest_hash,
                'prepared manifest was not refreshed')
        expected |= {PREPARED + ENTRY, PREPARED + 'manifest.json'}
    require({p for p in original if original[p] != derived[p]} == expected,
            'unreviewed derived source change')


def verify_provider_tree(base, common, manifest):
    for relative, expected in common.items():
        require(sha(base/'provider-inputs'/relative) ==
                (NEW_ENTRY if relative == ENTRY else expected),
                'common provider input was changed: '+relative)
    for relative, expected in manifest['prepared'].items():
        require(sha(base/'provider'/relative) == expected,
                'prepared provider bytes disagree with manifest: '+relative)


def candidate_inputs(scheduler, original, manifest_path, expected_hash):
    """Validate provenance and all selected bytes without altering originals."""
    require(re.fullmatch(r'[0-9a-f]{64}', expected_hash or '') is not None
            and sha(manifest_path) == expected_hash, 'candidate manifest hash differs')
    candidate = read(manifest_path)
    base = manifest_path.parent.resolve()
    require(not base.is_relative_to(original) and not original.is_relative_to(base),
            'candidate overlaps original inputs')
    require(candidate['kind'] == 'd21-plus-entry-inline' and candidate['complete']
            and candidate['original'] == str(original)
            and candidate['patch_commit'] == PATCH_COMMIT,
            'candidate recipe identity differs')
    require(candidate['preparer_sha256'] == sha(Path(__file__)),
            'candidate preparation/verification code changed')
    require(candidate['original_inputs_sha256'] == scheduler.REPLAY_INPUTS_SHA256
            and candidate['original_harness_sha256'] == scheduler.REPLAY_HARNESS_SHA256,
            'candidate was not based on the pinned original')
    frozen = scheduler.replay_inputs(original, base.parent/'unused-verification-output')
    scheduler.retained_harness(original)
    for item in frozen.values():
        scheduler.verify(item['files'])
    require(set(candidate['bundles']) == {'candidate-public/'+g for g in GROUPS},
            'unexpected candidate bundle set')
    for relative, expected in candidate['immutable_files'].items():
        path = Path(relative)
        require(not path.is_absolute() and '..' not in path.parts
                and not (base/path).is_symlink()
                and (base/path).resolve().is_relative_to(base)
                and sha(base/path) == expected, 'candidate input changed: ' + relative)
    built_manifest = read(base/'provider/manifest.json')
    common = None
    for group in GROUPS:
        old = original/'current'/group
        source = read(old/'source-sha256.json')
        selected = provider_inputs(source)
        require(len(selected) == 99 and (common is None or selected == common),
                'original groups do not share the complete provider recipe')
        common = selected
        bundle = base/'candidate-public'/group
        item = candidate['bundles']['candidate-public/'+group]
        require(item['bundle'] == str(bundle), 'candidate view redirected')
        derived = read(bundle/'source-sha256.json')
        validate_source_delta(source, derived, sha(base/'provider/manifest.json'))
        require(item['source_identity'] == scheduler.identity(derived),
                'candidate source identity differs')
        for relative, expected in derived.items():
            require(sha(bundle/'source'/relative) == expected, 'derived source bytes changed')
        # The synthetic prepared map has two changed digests; every other
        # field must match the original observation preparation exactly.
        if PREPARED+'manifest.json' in source:
            old_prepared = read(old/'source'/PREPARED/'manifest.json')
            for field in ('production', 'prepared'):
                old_prepared[field][ENTRY] = NEW_ENTRY
            require(old_prepared == built_manifest, 'observation recipe changed')
        binaries = scheduler.binary_paths(old, group in ('c08', 'rcuht'))
        provider = 'binaries/kdlock_km.ko' if group in ('c08', 'rcuht') else 'build/kdlock_km.ko'
        for filename, digest in binaries.items():
            relative = str(Path(filename).relative_to(old))
            expected = candidate['provider_sha256'] if relative == provider else digest
            require(sha(bundle/relative) == expected, 'caller/control binary changed: '+relative)
        require(sha(bundle/'plan.json') == sha(old/'plan.json'), 'session template changed')
        actual = {str(p): sha(p) for p in bundle.rglob('*') if p.is_file()}
        require(actual == item['files'], 'candidate file set differs')
    require(read(base/'original-provider-inputs.json') == common,
            'common provider recipe differs from original groups')
    verify_provider_tree(base, common, built_manifest)
    require(sha(base/'provider/kernel_module/kdlock_km.ko') == candidate['provider_sha256'],
            'common provider changed')
    candidate['manifest_sha256'] = expected_hash
    candidate['manifest_path'] = str(manifest_path)
    return candidate


def prepare(scheduler, original, out, entry):
    require(not out.exists() and not out.is_relative_to(ROOT), 'new external candidate required')
    frozen = scheduler.replay_inputs(original, out)
    harness = scheduler.retained_harness(original)
    for item in frozen.values():
        scheduler.verify(item['files'])
    require(sha(entry) == NEW_ENTRY, 'entry source is not the reviewed candidate')
    syn, _, _, _ = scheduler.runners(original/'harness', harness)
    syn.idle()
    out.mkdir(parents=True)
    save(out/'state.json', dict(state='PREPARING', complete=False))
    inputs = None
    for group in GROUPS:
        selected = provider_inputs(read(original/'current'/group/'source-sha256.json'))
        require(len(selected) == 99 and (inputs is None or selected == inputs),
                'original provider inputs differ across groups')
        inputs = selected
    source = out/'provider-inputs'
    for relative, expected in inputs.items():
        old = original/'current/c08/source'/relative
        require(sha(old) == expected, 'provider recipe source changed')
        target = source/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old, target)
    shutil.copyfile(entry, source/ENTRY)
    save(out/'original-provider-inputs.json', inputs)
    shutil.copyfile(Path(__file__), out/'entry_candidate.py')
    shutil.copyfile(Path(scheduler.__file__), out/'scheduler.py')
    module = runpy.run_path(str(source/'bench/spin_cacheline/provider/prepare.py'))
    built_manifest = module['prepare'](out/'provider', root=source)
    verify_provider_tree(out, inputs, built_manifest)
    commands = []

    def command(name, argv, timeout):
        syn.idle()
        row = dict(name=name, argv=list(map(str, argv)), started_unix=time.time(),
                   timeout_seconds=timeout, state='STARTING')
        commands.append(row)
        save(out/'commands.json', commands)
        with (out/(name+'.log')).open('x') as log:
            process = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            row.update(pid=process.pid, state='RUNNING')
            save(out/'commands.json', commands)
            try:
                rc = process.wait(timeout=timeout)
            except BaseException as error:
                row.update(state='UNCERTAIN', error=repr(error))
                save(out/'commands.json', commands)
                raise  # No kill, next build or assumption of drain.
        row.update(state='FINISHED', exit_code=rc, finished_unix=time.time())
        save(out/'commands.json', commands)
        require(rc == 0, name+' failed')
        return (out/(name+'.log')).read_text()

    command('compiler', ['gcc', '--version'], 10)
    command('kernel-identity', [sys.executable, original/'harness/bench/spin_cacheline/kernel_identity.py',
            '--kernel-source', '/root/linux-6.1.159-kdclobber2',
            '--kernel-baseline', '/root/kdlock-kernel-baselines/mutex-clobber2-20260919'], 120)
    command('build', ['make', '-C', out/'provider/kernel_module',
            'KDIR=/root/linux-6.1.159-kdclobber2', 'W=1', 'KDLOCK_SELFTEST=0',
            'KDLOCK_NUMA=1', 'KDLOCK_SPIN_BATCH=1024', 'UBSAN_SANITIZE=n'], 240)
    provider = out/'provider/kernel_module/kdlock_km.ko'
    imports = command('imports', ['nm', '-u', provider], 30)
    require('__ubsan_' not in imports and not re.search(
        r'\bU (?:atomic_dec_and_mutex_lock|mutex\w*|__mutex\w*|'
        r'kd_mutex_(?:lock|unlock)_clobber_v1|osq_lock|osq_unlock)\b', imports),
        'candidate imports Linux mutex APIs or UBSAN')
    symbols = command('symbols', ['nm', '-S', '--defined-only', provider], 30)
    require('kd_mutex_lock_entry' not in symbols
            and ' kd_mutex_direct_lock_clobber_v1\n' in symbols,
            'entry helper was not inlined')
    command('disassembly', ['objdump', '-dr', provider], 30)
    for field, expected in (('spin_numa', '1'), ('spin_batch', '1024')):
        require(command(field, ['modinfo', '-F', field, provider], 10).strip() == expected,
                'compiled provider configuration differs')
    bundles = {}
    for group in GROUPS:
        old, bundle = original/'current'/group, out/'candidate-public'/group
        source_map = read(old/'source-sha256.json')
        for relative in source_map:
            target = bundle/'source'/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old/'source'/relative, target)
        shutil.copyfile(entry, bundle/'source'/ENTRY)
        if PREPARED+ENTRY in source_map:
            shutil.copyfile(entry, bundle/'source'/PREPARED/ENTRY)
            shutil.copyfile(out/'provider/manifest.json', bundle/'source'/PREPARED/'manifest.json')
        derived = {p: sha(bundle/'source'/p) for p in source_map}
        validate_source_delta(source_map, derived, sha(out/'provider/manifest.json'))
        save(bundle/'source-sha256.json', derived)
        binaries = scheduler.binary_paths(old, group in ('c08', 'rcuht'))
        binary_rows = {}
        for filename, expected in binaries.items():
            relative = Path(filename).relative_to(old)
            target = bundle/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            replacement = provider if relative.name == 'kdlock_km.ko' else Path(filename)
            shutil.copy2(replacement, target)
            binary_rows[str(relative)] = dict(original=filename, original_sha256=expected,
                                               sha256=sha(target))
        save(bundle/'candidate-binaries.json', binary_rows)
        shutil.copyfile(old/'plan.json', bundle/'plan.json')
        bundles['candidate-public/'+group] = dict(
            bundle=str(bundle), source_identity=scheduler.identity(derived),
            files={str(p): sha(p) for p in bundle.rglob('*') if p.is_file()})
    immutable = {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()
                 and p.name != 'state.json'}
    candidate = dict(kind='d21-plus-entry-inline', complete=True, original=str(original),
                     patch_commit=PATCH_COMMIT, preparer_sha256=sha(Path(__file__)),
                     original_inputs_sha256=scheduler.REPLAY_INPUTS_SHA256,
                     original_harness_sha256=scheduler.REPLAY_HARNESS_SHA256,
                     provider_sha256=sha(provider), bundles=bundles, immutable_files=immutable,
                     scope='Retained d21 inputs plus only the selected 003d71c entry patch; '
                           'not a full 003d71c build. Original-public before/after comparisons '
                           'are observational; the 120-session run has no fifth arm.')
    save(out/'candidate.json', candidate)
    candidate_inputs(scheduler, original, out/'candidate.json', sha(out/'candidate.json'))
    syn.idle()
    save(out/'state.json', dict(state='COMPLETE', complete=True, final_idle=True,
                              manifest_sha256=sha(out/'candidate.json')))
    print(json.dumps(dict(candidate=str(out/'candidate.json'),
                          manifest_sha256=sha(out/'candidate.json'),
                          provider_sha256=sha(provider))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--entry-source', type=Path, required=True)
    args = parser.parse_args()
    require(os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
            and os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1',
            'confirmed original recovery VM required')
    require(sha(Path(__file__)) == sha(ROOT/'bench/mutex_api_compare/entry_candidate.py'),
            'external driver copy differs from maintained source')
    require(not Path(__file__).resolve().is_relative_to(ROOT),
            'execute a byte-matched external copy for retained collector origin checks')
    require(Path(sys.executable) == Path('/root/kdlock-translation-venv-20261019/bin/python3')
            and shutil.which('python3') == sys.executable, 'use the original pinned Python')
    sys.dont_write_bytecode = True
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    spec = importlib.util.spec_from_file_location('candidate_scheduler', ROOT/'bench/mutex_api_compare/run.py')
    scheduler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scheduler)
    out = args.output.resolve()
    require(not out.exists(), 'candidate output already exists')
    try:
        prepare(scheduler, args.original.resolve(), out, args.entry_source.resolve())
    except BaseException as error:
        if (out/'state.json').is_file():
            save(out/'state.json', dict(state='FAILED', complete=False, error=repr(error),
                                       drain_established=False))
        raise


if __name__ == '__main__':
    main()
