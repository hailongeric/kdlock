#!/usr/bin/env python3
"""Host-only candidate archive, exact provider overlay and stale-leaf audit.

Archived source and ELF bytes remain data. Only the reviewed analyzer and its
hash-authenticated checkout oracle are executed. No VM, build or timing calls.
"""
import argparse
import csv
import datetime
import importlib.util
import json
from pathlib import Path
import re
import shlex
import sys
import tarfile
import tempfile

sys.dont_write_bytecode = True
BASELINE = 'acfa33a5adbc1ec6a8aa3bb02f0107052b32a20f'
CANDIDATE = '8446f4ecb08816380a4c233197a8ce5e4d333aac'
TARGET = 'ace6eaf882c54bc822b8fe4f4eea4d85fc605473'
OBSOLETE = {
    'include/kd_rwsem_direct.h', 'kernel_module/kd_rwlock.c',
    'kernel_module/mutex/custody.inc', 'kernel_module/mutex/pin_diag.inc',
    'kernel_module/mutex/pin_origin.inc', 'kernel_module/mutex/pin_window.inc',
}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--analyzer', type=Path, required=True)
parser.add_argument('--candidate-archives', type=Path, required=True)
parser.add_argument('--candidate-control', type=Path, required=True)
parser.add_argument('--candidate-host-after', type=Path, required=True)
parser.add_argument('--baseline-archives', type=Path, required=True)
parser.add_argument('--baseline-control', type=Path, required=True)
parser.add_argument('--baseline-host-after', type=Path, required=True)
parser.add_argument('--baseline-extra-review', type=Path, required=True)
parser.add_argument('--trusted-checkout', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--final-output', type=Path, required=True)
args = parser.parse_args()
spec = importlib.util.spec_from_file_location('reviewed_nano_analyzer', args.analyzer)
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
root = args.trusted_checkout.resolve(strict=True)
out = args.output.resolve()
a.need(not args.output.exists() and not args.output.is_symlink(), 'new audit output required')
a.need(not args.final_output.exists() and not args.final_output.is_symlink(), 'new final analysis output required')
for path in (args.candidate_archives, args.candidate_control, args.baseline_archives,
             args.baseline_control, root):
    a.need(not out.is_relative_to(path.resolve()) and not path.resolve().is_relative_to(out),
           'audit output must be separate from archive/source inputs')
a.need(not args.final_output.resolve().is_relative_to(out) and not out.is_relative_to(args.final_output.resolve()),
       'final analysis output must be separate from candidate audit output')
out.mkdir(parents=True, exist_ok=False)
result = dict(completed=False, validated=False, performance_accepted=False,
              source_commit=CANDIDATE, retirement_target_commit=TARGET,
              analyzer_sha256=a.file_sha(args.analyzer), audit_sha256=a.file_sha(Path(__file__)),
              arguments={k:str(v) for k,v in vars(args).items()})


def apply_exact_patch(patch, git):
    """Same complete-context reconstruction as the retained baseline audit."""
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
        current = git.blob(CANDIDATE, path).decode().splitlines(keepends=True)
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


def tokens(name):
    result = {name, Path(name).name}
    if name.endswith('.c'):
        result.add(str(Path(name).with_suffix('.o')))
        result.add(Path(name).with_suffix('.o').name)
    return result


def capture_elfs(archive, wanted):
    """Copy only independently authenticated module bytes, never tar paths."""
    prefix = a.safe(archive.meta['archive_prefix'])+'/'
    records = {}
    for group in archive.meta['groups']:
        path = archive.directory / group['file']
        a.need(a.file_sha(path) == group['sha256'], 'archive changed before ELF capture')
        with tarfile.open(path, 'r|gz') as tar:
            for member in tar:
                if not member.name.startswith(prefix):
                    continue
                name = member.name[len(prefix):]
                if name not in wanted:
                    continue
                a.need(name not in records and member.isfile(), 'duplicate/nonregular selected ELF')
                a.need(member.size <= 256*1024*1024, 'oversized selected ELF')
                data = tar.extractfile(member).read()
                a.need(len(data) == member.size and a.sha(data) == wanted[name] == archive.hashes[name],
                       'selected ELF differs from actual measured binary map: '+name)
                destination = out/'elfs'/a.safe(name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                records[name] = dict(sha256=wanted[name], bytes=len(data),
                    file=str(destination), archive_group=group['file'], archive_member=member.name,
                    modinfo=archive.modinfo[name], executed=False)
    a.need(set(records) == set(wanted), 'missing actual measured ELF')
    return records


try:
    git = a.Git(root)
    a.need(git.output('rev-parse', TARGET+'^{commit}').decode().strip() == TARGET, 'retirement target identity')
    absent = git.output('ls-tree', '-r', '--name-only', TARGET, '--', *sorted(OBSOLETE)).decode().splitlines()
    a.need(not absent, 'retirement proposal contains a path tracked by target commit')
    baseline_review = a.local_json(args.baseline_extra_review)
    a.need(isinstance(baseline_review.get('baseline'), dict), 'baseline extra-source evidence missing')
    expected = git.source_hashes(CANDIDATE)
    selected = {n:git.blob(CANDIDATE,n) for n in expected}
    target_names = git.source_hashes(TARGET)
    target_selected = {n:git.blob(TARGET,n) for n in target_names}
    for name in OBSOLETE:
        for label, source in (('candidate',selected), ('target',target_selected)):
            a.need(not any(token.encode() in data for token in tokens(name) for data in source.values()),
                   label+' selected source references obsolete leaf: '+name)
    with tempfile.TemporaryDirectory(prefix='kd-candidate-nano-audit-') as temporary:
        archive = a.Archive(args.candidate_archives, Path(temporary))
        frozen = archive.json('source-sha256.json')
        a.need(all(frozen.get(n) == value for n,value in expected.items()), 'candidate tracked Git blob mismatch')
        extras = {n:frozen[n] for n in sorted(set(frozen)-set(expected))}
        a.need(set(extras) == OBSOLETE, 'actual extra set differs from six reviewed obsolete leaves')
        for name,digest in extras.items():
            a.need(baseline_review['baseline'].get(name,{}).get('sha256') == digest,
                   'obsolete leaf changed from archived baseline: '+name)
        production = {n:v for n,v in frozen.items() if n.startswith(('include/','kernel_module/'))
                      and (Path(n).suffix in ('.c','.inc','.h','.S','.def') or Path(n).name=='Makefile')
                      and not n.endswith('.mod.c')}
        overlay = 'bench/spin_cacheline/provider/'
        patched,hunks = apply_exact_patch(git.blob(CANDIDATE,overlay+'observation.patch'),git)
        a.need(len(hunks)==26 and len(patched)==12, 'candidate observation overlay shape changed')
        prepared = production | {n:a.sha(data) for n,data in patched.items()} | {
            'kernel_module/kd_bench.c':frozen[overlay+'kd_bench.c'],
            'include/kd_bench.h':frozen[overlay+'kd_bench.h']}
        providers, wanted_elfs = [], {}
        for profile in a.PROFILES:
            a.need(archive.json(profile+'/source-sha256.json') == frozen, 'source manifests differ by profile')
            for name,digest in frozen.items():
                a.need(archive.hashes.get(profile+'/source/'+a.safe(name)) == digest, 'captured source bytes differ')
            pref = profile+'/build/provider/'
            manifest = archive.json(pref+'manifest.json')
            a.need(manifest.get('complete') is True and manifest.get('kind')=='spin_cacheline private provider',
                   'prepared provider incomplete')
            a.need(manifest['production']==production and manifest['prepared']==prepared,
                   'provider differs from exact source plus reviewed overlay')
            a.need(manifest['observation']=={n:frozen[overlay+n] for n in ('observation.patch','kd_bench.c','kd_bench.h')},
                   'provider observation inputs differ')
            a.need(all(archive.hashes.get(pref+n)==digest for n,digest in prepared.items()), 'prepared bytes mismatch')
            providers.append(dict(profile=profile,manifest_sha256=archive.hashes[pref+'manifest.json'],
                production_files=len(production),prepared_files=len(prepared),exact_patch_hunks=len(hunks)))
            for path,digest in archive.json(profile+'/binary-sha256.json').items():
                if path.endswith('.ko'):
                    name=archive.relative(path)
                    a.need(archive.hashes.get(name)==digest and name not in wanted_elfs, 'module binary map mismatch')
                    wanted_elfs[name]=digest
        cmds = {n:archive.text(n) for n in archive.saved if n.endswith('.cmd') and '/build/' in n}
        required_objects = ('.kdlock_km.o.cmd','.kd_spin_runtime.o.cmd','.kd_api_provider.o.cmd',
                            '.sys.o.cmd','.kd_bench.o.cmd')
        for profile in a.PROFILES:
            for name in required_objects:
                a.need(profile+'/build/provider/kernel_module/'+name in cmds, 'missing provider compile/link receipt')
            runtime = cmds[profile+'/build/provider/kernel_module/.kd_spin_runtime.o.cmd']
            a.need(all(name in runtime for name in ('kd_mutex.c','kd_spinlock.c','exe.c')),
                   'combined runtime receipt omits actual mutex/spin/executor source')
        for name in extras:
            a.need(not any(token in text for token in tokens(name) for text in cmds.values()),
                   'obsolete leaf/object reached a retained build dependency: '+name)
        source_proofs = ['kernel_module/Makefile','kernel_module/kd_spin_runtime.c','kernel_module/kd_spinlock.c',
                         'kernel_module/kd_mutex.c','kernel_module/exe.c','workload_modules/rwlock_bench/direct_rwsem.h',
                         'workload_modules/rwlock_bench/Makefile','bench/rwlock_compare/run.py',
                         'daemon/compiler.inc','daemon/workspace.inc']
        proofs = [dict(path=n,sha256=archive.hashes[n]) for n in sorted(cmds)]
        proofs += [dict(path='mutex-throughput/source/'+n,sha256=expected[n]) for n in source_proofs]
        reason = ('The candidate Makefile lists provider objects explicitly and does not select kd_rwlock.o. '
                  'No selected candidate source names this obsolete leaf or object; no retained compiler/link '
                  '.cmd receipt from any of the ten profiles names it. Each exact prepared tree is reconstructed '
                  'from Git plus all 26 reviewed observation hunks. The daemon executes named translator paths; '
                  'it does not load these copied C/header/inc leaves dynamically. This is a reviewed static '
                  'build-reachability conclusion, not a general proof of arbitrary runtime file access.')
        review = {n:dict(sha256=digest,reviewed=True,classification='not-built-or-imported',reason=reason,proofs=proofs)
                  for n,digest in extras.items()}
        combined = {'baseline':baseline_review['baseline'],'candidate':review}
        (out/'extra-source-review.json').write_text(json.dumps(combined,indent=2)+'\n')
        oracle,fault,oracle_hashes = a.trusted_oracles(git,BASELINE,CANDIDATE)
        campaign = a.campaign('candidate',archive,args.candidate_control,args.candidate_host_after,
                              CANDIDATE,git,oracle,fault,combined)
        a.need(len(campaign['rows'])==630, 'candidate does not contain all 630 points')
        records = capture_elfs(archive,wanted_elfs)
        (out/'elf-provenance.json').write_text(json.dumps(records,indent=2)+'\n')
        (out/'points.json').write_text(json.dumps(list(campaign['rows'].values()),indent=2)+'\n')
        columns=['profile','lock_kind','workload','write_percent','threads','repeat','arm','execution_class',
                 'jit_entries','jit_completions','completed','reads','writes','wall_ns','whole_ops_s','peak_ops_s',
                 'session_sha256','raw_measure_sha256','provider_sha256','validated','performance_accepted']
        with (out/'points.csv').open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=columns,lineterminator='\n');writer.writeheader()
            for row in campaign['rows'].values():writer.writerow({k:row[k] for k in columns})
        proposal=dict(schema=1,proposal_only=True,mutation_performed=False,source_commit=CANDIDATE,
            target_commit=TARGET,archive_receipt_sha256=archive.provenance['archive_receipt_sha256'],
            inventory_sha256=archive.provenance['inventory_sha256'],target_tracked_absence_verified=True,
            target_selected_source_reference_scan='No exact obsolete path, basename or C-object token in selected Git blobs.',
            target_selected_source_sha256=target_names,
            scope='Six exact obsolete leaves only; guarded retirement controller must independently verify idle guest, target identity, regular nonsymlink files and current hashes before any mutation.',
            leaves=[dict(path=n,sha256=extras[n],target_tracked=False,
                         archive_source_proofs=[dict(path=p+'/source/'+n,sha256=archive.hashes[p+'/source/'+n])
                                                for p in a.PROFILES],
                         archive_prepared_proofs=[dict(path=p+'/build/provider/'+n,sha256=archive.hashes[p+'/build/provider/'+n])
                                                  for p in a.PROFILES]) for n in sorted(extras)])
        (out/'obsolete-leaf-retirement-proposal.json').write_text(json.dumps(proposal,indent=2)+'\n')
        final_argv=['python3',str(args.analyzer.resolve()),
            '--baseline-archives',str(args.baseline_archives.resolve()),'--candidate-archives',str(args.candidate_archives.resolve()),
            '--baseline-control',str(args.baseline_control.resolve()),'--candidate-control',str(args.candidate_control.resolve()),
            '--baseline-host-after',str(args.baseline_host_after.resolve()),'--candidate-host-after',str(args.candidate_host_after.resolve()),
            '--trusted-checkout',str(root),'--baseline-commit',BASELINE,'--candidate-commit',CANDIDATE,
            '--extra-source-review',str(out/'extra-source-review.json'),'--output',str(args.final_output.resolve())]
        (out/'final-analysis-argv.json').write_text(json.dumps(final_argv,indent=2)+'\n')
        (out/'final-analysis-command.txt').write_text(shlex.join(final_argv)+'\n')
        control=a.local_json(args.candidate_control/'owner.json')
        before=a.local_json(args.candidate_control/'host-before.json');after=a.local_json(args.candidate_host_after)
        result.update(completed=True,validated=True,validated_points=630,archive=archive.provenance,
            provider_preparation=providers,patch_hunks=hunks,reviewed_extras=extras,
            dependency_receipts={n:archive.hashes[n] for n in cmds},captured_module_elfs=len(records),
            captured_provider_elfs=sum(n.endswith('/kdlock_km.ko') for n in records),
            oracle_sha256=oracle_hashes,
            host_endpoint_ages_seconds=dict(before=control['started']-datetime.datetime.fromisoformat(before['captured_utc']).timestamp(),
                                           after=datetime.datetime.fromisoformat(after['captured_utc']).timestamp()-control['finished']),
            campaign={k:v for k,v in campaign.items() if k not in ('rows','host_fixed_identity')},
            retirement_proposed_leaves=len(proposal['leaves']),
            limits=['One measurement per point; strict host qualification remains failed.',
                    'No comparison or no-regression acceptance is conferred by this receipt audit.',
                    'This campaign precedes the original-task instruction-service implementation.',
                    'ELFs are retained as data for static inspection; no archived code executes.'])
except BaseException as error:
    result['error']=repr(error)
    raise
finally:
    (out/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ('completed','validated','validated_points','captured_module_elfs',
                                      'retirement_proposed_leaves','performance_accepted')}))
