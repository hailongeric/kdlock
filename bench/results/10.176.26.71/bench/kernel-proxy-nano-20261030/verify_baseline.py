#!/usr/bin/env python3
"""Offline baseline receipt replay and exact provider-overlay reconstruction."""
import argparse
import csv
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline-archives', type=Path, required=True)
parser.add_argument('--baseline-control', type=Path, required=True)
parser.add_argument('--baseline-host-after', type=Path, required=True)
parser.add_argument('--trusted-checkout', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
spec = importlib.util.spec_from_file_location('reviewed_nano_analyzer', HERE/'analyze.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
root = args.trusted_checkout.resolve(strict=True)
commit = 'acfa33a5adbc1ec6a8aa3bb02f0107052b32a20f'
candidate = '8446f4ecb08816380a4c233197a8ce5e4d333aac'
out = args.output.resolve()
a.need(not args.output.exists() and not args.output.is_symlink(), 'new output directory required')
for path in (args.baseline_archives, args.baseline_control, root, HERE):
    a.need(not out.is_relative_to(path.resolve()) and not path.resolve().is_relative_to(out),
           'output must be separate from archive, source and audit inputs')
out.mkdir(parents=True, exist_ok=False)
result = dict(completed=False, validated=False, performance_accepted=False,
              analyzer_sha256=a.file_sha(Path(a.__file__)),
              audit_sha256=a.file_sha(Path(__file__)), source_commit=commit,
              arguments={k:str(v) for k,v in vars(args).items()})
REVIEWED_EXTRAS = {
    'disassem/native_terminals.py', 'include/kd_api_control.h', 'include/kd_api_provider.h',
    'include/kd_native_terminals.def', 'include/kd_rwsem_direct.h',
    'kernel_integration/linux70/compose_scope.py', 'kernel_integration/linux70/scope-base-sha256.json',
    'kernel_module/execution/native_terminals.inc', 'kernel_module/kd_api_provider.c',
    'kernel_module/kd_rwlock.c', 'kernel_module/mutex/custody.inc', 'kernel_module/mutex/pin_diag.inc',
    'kernel_module/mutex/pin_origin.inc', 'kernel_module/mutex/pin_window.inc',
    'kernel_module/spin/context.inc',
}


def apply_exact_patch(patch, git):
    lines = patch.decode().splitlines(keepends=True)
    i = 0
    patched, hunks = {}, []
    while i < len(lines):
        a.need(lines[i].startswith('diff --git a/'), 'patch diff header')
        i += 1
        a.need(lines[i].startswith('--- a/'), 'patch old header')
        path = lines[i][6:].strip()
        i += 1
        a.need(lines[i] == '+++ b/'+path+'\n', 'patch new header')
        i += 1
        current = git.blob(commit, path).decode().splitlines(keepends=True)
        cursor = 0
        while i < len(lines) and lines[i].startswith('@@ '):
            header = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*\n', lines[i])
            a.need(header is not None, 'patch hunk header')
            old_count, new_count = int(header[2] or 1), int(header[4] or 1)
            i += 1
            old, new = [], []
            while len(old) < old_count or len(new) < new_count:
                line = lines[i]
                a.need(line[:1] in (' ', '+', '-'), 'patch hunk line')
                if line[0] in ' -': old.append(line[1:])
                if line[0] in ' +': new.append(line[1:])
                i += 1
            a.need(len(old) == old_count and len(new) == new_count and old, 'patch hunk lengths')
            matches = [n for n in range(cursor, len(current)-len(old)+1)
                       if current[n:n+len(old)] == old]
            a.need(len(matches) == 1, 'patch needs exactly one full-context match: '+path)
            start = matches[0]
            current[start:start+len(old)] = new
            cursor = start+len(new)
            hunks.append(dict(path=path, applied_line=start+1, header_old_line=int(header[1]),
                              old_lines=old_count, new_lines=new_count))
        a.need(path not in patched, 'duplicate patch file')
        patched[path] = ''.join(current).encode()
    return patched, hunks


try:
    with tempfile.TemporaryDirectory(prefix='kd-baseline-r2-') as temporary:
        archive = a.Archive(args.baseline_archives, Path(temporary))
        git = a.Git(root)
        expected = git.source_hashes(commit)
        frozen = archive.json('source-sha256.json')
        a.need(all(frozen.get(n) == v for n,v in expected.items()), 'Git source authentication')
        extras = {n:frozen[n] for n in sorted(set(frozen)-set(expected))}
        a.need(set(extras) == REVIEWED_EXTRAS, 'exact previously reviewed extra set required')
        production = {n:v for n,v in frozen.items() if n.startswith(('include/', 'kernel_module/'))
                      and (Path(n).suffix in ('.c','.inc','.h','.S','.def') or Path(n).name == 'Makefile')
                      and not n.endswith('.mod.c')}
        overlay_path = 'bench/spin_cacheline/provider/'
        patched, hunks = apply_exact_patch(git.blob(commit, overlay_path+'observation.patch'), git)
        prepared = dict(production)
        prepared.update({n:a.sha(v) for n,v in patched.items()})
        prepared.update({'kernel_module/kd_bench.c':frozen[overlay_path+'kd_bench.c'],
                         'include/kd_bench.h':frozen[overlay_path+'kd_bench.h']})
        provider = []
        for profile in a.PROFILES:
            pref = profile+'/build/provider/'
            manifest = archive.json(pref+'manifest.json')
            a.need(manifest.get('kind') == 'spin_cacheline private provider' and manifest.get('complete') is True,
                   'provider manifest incomplete')
            a.need(manifest['production'] == production and manifest['prepared'] == prepared,
                   'provider preparation not exactly the recorded production plus observation patch')
            a.need(manifest['observation'] == {n:frozen[overlay_path+n]
                   for n in ('observation.patch','kd_bench.c','kd_bench.h')}, 'observation input mismatch')
            a.need(all(archive.hashes.get(pref+n) == v for n,v in prepared.items()), 'actual prepared bytes differ')
            provider.append(dict(profile=profile, manifest_sha256=archive.hashes[pref+'manifest.json'],
                                 production_files=len(production), prepared_files=len(prepared),
                                 exact_patch_hunks=len(hunks)))
        result.update(archive=archive.provenance, provider_preparation=provider, patch_hunks=hunks)
        # Actual compiler dependency receipts plus explicit object/include/import review.
        cmds = {n:archive.text(n) for n in archive.saved if n.endswith('.cmd') and '/build/' in n}
        c_extras = {n for n in extras if n.startswith(('include/', 'kernel_module/'))}
        a.need(all(not any(n in t or Path(n).name in t for t in cmds.values()) for n in c_extras),
               'extra file occurs in a retained compiler dependency receipt')
        source_data = {n:git.blob(commit,n) for n in expected}
        a.need(all(not any(n.encode() in data or Path(n).name.encode() in data
                          for data in source_data.values()) for n in c_extras),
               'extra file referenced by selected source')
        # This is a reviewed import/read inventory, not a general Python reachability proof.
        for token in (b'native_terminals', b'compose_scope', b'scope-base-sha256'):
            a.need(not any(token in data for data in source_data.values()), 'extra Python/data reference')
        review = {}
        source_proofs = ['kernel_module/Makefile','kernel_module/kd_spin_runtime.c',
                         'kernel_module/kd_spinlock.c','kernel_module/kd_mutex.c', 'kernel_module/exe.c',
                         'workload_modules/rwlock_bench/direct_rwsem.h',
                         'workload_modules/rwlock_bench/Makefile','bench/rwlock_compare/run.py']
        cproofs = [dict(path=n,sha256=archive.hashes[n]) for n in sorted(cmds)]
        cproofs += [dict(path='mutex-throughput/source/'+n,sha256=expected[n]) for n in source_proofs]
        pyproof_names = [n for n in expected if n.startswith('disassem/') and n.endswith('.py')]
        pyproof_names += ['daemon/compiler.inc','daemon/workspace.inc','bench/rwlock_compare/run.py',
                          'bench/rwlock_compare/session.py','bench/spin_cacheline/kernel_identity.py',
                          'kernel_integration/linux70/verify.py','kernel_baseline/verify.py',
                          'bench/nano/best_case.py']
        pyproofs = [dict(path='mutex-throughput/source/'+n,sha256=expected[n]) for n in pyproof_names]
        for name,digest in extras.items():
            if name in c_extras:
                reason = ('The baseline Makefile lists each provider object explicitly; kd_api_provider.o and kd_rwlock.o '
                          'are absent. The common runtime translation unit and selected source include graph never name '
                          'this extra file. All retained provider, workload and guard .cmd files from all ten profiles '
                          'contain neither its path nor basename. Workload headers and compiler commands use the selected '
                          'source/include and provider trees. This leaf was copied but not compiled; no runtime loading '
                          'of C/header/inc/def leaves occurs in the reviewed daemon or runner.')
                proofs = cproofs
            else:
                reason = ('The selected daemon executes the explicit disassem/disassem.py path; its reviewed static '
                          'imports and callees do not import native_terminals or enumerate Python plugins. Linux70 identity '
                          'verification imports only the explicit kernel_baseline/verify.py helper and reads named bundle '
                          'paths. Neither the nano runner, translator nor verifier names compose_scope or scope-base-sha256. '
                          'No selected captured source contains any of these three names; all ten source manifests are '
                          'identical. This extra helper/data leaf was copied but not imported, executed or read.')
                proofs = pyproofs
            review[name] = dict(sha256=digest,reviewed=True,classification='not-built-or-imported',reason=reason,proofs=proofs)
        extra_review = dict(baseline=review,candidate={})
        (out/'extra-source-review.json').write_text(json.dumps(extra_review,indent=2)+'\n')
        result['reviewed_extras'] = extras
        result['dependency_receipts'] = {n:archive.hashes[n] for n in cmds}
        oracle,fault,oracle_hashes = a.trusted_oracles(git,commit,candidate)
        campaign = a.campaign('baseline', archive, args.baseline_control,
                             args.baseline_host_after,
                             commit,git,oracle,fault,extra_review)
        (out/'points.json').write_text(json.dumps(list(campaign['rows'].values()),indent=2)+'\n')
        columns = ['profile','lock_kind','workload','write_percent','threads','repeat','arm',
                   'execution_class','jit_entries','jit_completions','completed','reads','writes',
                   'wall_ns','whole_ops_s','peak_ops_s','session_sha256','raw_measure_sha256',
                   'provider_sha256','validated','performance_accepted']
        with (out/'points.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            for row in campaign['rows'].values():
                writer.writerow({k:row[k] for k in columns})
        control = a.local_json(args.baseline_control/'owner.json')
        before = a.local_json(args.baseline_control/'host-before.json')
        after = a.local_json(args.baseline_host_after)
        result['host_endpoint_ages_seconds'] = dict(
            before=control['started']-datetime.datetime.fromisoformat(before['captured_utc']).timestamp(),
            after=datetime.datetime.fromisoformat(after['captured_utc']).timestamp()-control['finished'])

        result.update(completed=True, validated=True, validated_points=len(campaign['rows']),
                      oracle_sha256=oracle_hashes,
                      campaign={k:v for k,v in campaign.items() if k not in ('rows','host_fixed_identity')})
except BaseException as error:
    result['error'] = repr(error)
    raise
finally:
    (out/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ('completed','validated_points')}))
