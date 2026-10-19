#!/usr/bin/env python3
"""Offline data audit. Reads tar members in memory; never extracts or runs them."""
import collections
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import socket
import stat
import subprocess
import tarfile

REPO = Path.cwd()
RAW = REPO / 'bench/results/10.176.26.71/raw/bench/mutex32-index-20261019'
OUT = REPO / 'bench/results/10.176.26.71/bench/mutex32-index-20261019'
AR = json.loads((RAW / 'archives.json').read_text())
INV = json.loads((RAW / 'input-inventory.json').read_text())
PREFIX = AR['archive_prefix'] + '/'
BASE = AR['guest_base'] + '/'
issues = []
checks = collections.Counter()

def check(ok, label, detail=None):
    checks[label] += 1
    if not ok:
        issues.append(dict(check=label, detail=detail))
    return ok

def sha(data):
    return hashlib.sha256(data).hexdigest()

def hashfile(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()

def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

check(AR['completed'] is True and AR['guest_idle'] is True, 'archive_completed_idle')
check(hashfile(RAW / 'input-inventory.json') == AR['input_inventory_sha256'], 'inventory_hash')
check(hashfile(RAW / 'archive_run.py') == AR['script_sha256'], 'archiver_hash')
files, contents, members, groups, links = {}, {}, {}, [], []
for group in AR['groups']:
    p = RAW / group['file']
    check(p.stat().st_size == group['bytes'], 'archive_bytes', group['file'])
    check(hashfile(p) == group['sha256'], 'archive_hash', group['file'])
    counts = collections.Counter()
    with tarfile.open(p, 'r:gz') as archive:
        for m in archive:
            check(m.name.startswith(PREFIX), 'member_prefix', m.name)
            relative = m.name.removeprefix(PREFIX)
            check(not PurePosixPath(relative).is_absolute() and '..' not in PurePosixPath(relative).parts,
                  'member_safe_path', relative)
            check(relative not in members, 'member_unique', relative)
            check(any(m.name == root or m.name.startswith(root + '/') for root in group['roots']),
                  'member_assigned_group', relative)
            kind = 'file' if m.isfile() else 'dir' if m.isdir() else 'symlink' if m.issym() else 'unsupported'
            counts[kind] += 1
            members[relative] = dict(archive=group['file'], kind=kind, bytes=m.size)
            expected = INV.get(relative)
            if not check(expected is not None, 'member_in_inventory', relative):
                continue
            etype = 'file' if stat.S_ISREG(expected['mode']) else 'dir' if stat.S_ISDIR(expected['mode']) else 'symlink' if stat.S_ISLNK(expected['mode']) else 'unsupported'
            check(kind == etype and kind != 'unsupported', 'member_type', relative)
            check(m.mode == stat.S_IMODE(expected['mode']), 'member_mode', relative)
            check((m.uid, m.gid) == (expected['uid'], expected['gid']), 'member_owner', relative)
            sec, ns = divmod(expected['mtime_ns'], 1_000_000_000)
            check(m.mtime == sec + ns * 1e-9, 'member_mtime_exact_tar_projection', relative)
            if kind == 'file':
                check(m.size == expected['bytes'], 'member_bytes', relative)
                content = archive.extractfile(m).read()
                check(len(content) == m.size, 'member_read_bytes', relative)
                files[relative] = sha(content)
                # Source, manifests and logs are inert bytes, not imported modules.
                if m.size < 5_000_000 and (relative.endswith(('.json', '.log', '.patch', '.c', '.h', '.inc', '.S', '.py', '.def')) or '/source/' in relative and '/.build/' not in relative or '/.build/provider/' in relative):
                    if b'\x00' not in content:
                        contents[relative] = content
            elif kind == 'symlink':
                check(m.linkname == expected['link'], 'symlink_target', relative)
                check(len(m.linkname.encode()) == expected['bytes'], 'symlink_target_bytes', relative)
                check(m.size == 0, 'symlink_tar_payload_empty', relative)
                target = m.linkname.removeprefix(BASE) if m.linkname.startswith(BASE) else None
                check(target in INV, 'symlink_target_retained_in_inventory', dict(path=relative, target=m.linkname))
                links.append(dict(path=relative, target=m.linkname, target_retained=target in INV))
            elif kind == 'dir':
                check(m.size == 0, 'directory_tar_payload_empty', relative)
    groups.append(dict(file=group['file'], sha256=group['sha256'], bytes=group['bytes'], members=sum(counts.values()), types=dict(counts)))
check(set(members) == set(INV), 'inventory_exact_set', dict(missing=sorted(set(INV)-set(members)), extra=sorted(set(members)-set(INV))))
check(files.get(AR['health_path']) == AR['health_sha256'], 'health_hash')

def jread(name):
    return json.loads(contents[name])

def normalized(value, folder):
    if value.startswith(BASE):
        return value[len(BASE):]
    if value.startswith('/root/host_fs/kdlock/') or value == '/root/kdlock-evidence/10.176.26.71/bench/mutex-admission-20261013/tools/perf':
        return folder + '/binaries/' + value.rsplit('/', 1)[1]
    return folder + '/' + value

source_manifest_rows, binary_rows = [], []
for name in sorted(files):
    folder = name.rsplit('/', 1)[0] if '/' in name else ''
    if name.endswith('/source-sha256.json'):
        manifest = jread(name)
        for path, expected in manifest.items():
            check(files.get(folder + '/source/' + path) == expected, 'source_manifest_hash', dict(manifest=name, path=path))
        source_manifest_rows.append(dict(path=name, entries=len(manifest), sha256=files[name]))
    elif name.endswith('/prepared-source-sha256.json'):
        manifest = jread(name)
        for path, expected in manifest.items():
            check(files.get(folder + '/build/provider/' + path) == expected, 'prepared_source_manifest_hash', dict(manifest=name, path=path))
        source_manifest_rows.append(dict(path=name, entries=len(manifest), prepared=True, sha256=files[name]))
    elif name.endswith('/binary-sha256.json') or name.endswith('/binaries.json'):
        manifest = jread(name)
        for key, value in manifest.items():
            path, expected = (value['path'], value['sha256']) if isinstance(value, dict) else (key, value)
            member = normalized(path, folder)
            check(files.get(member) == expected, 'binary_manifest_hash', dict(manifest=name, path=path, member=member))
            binary_rows.append(dict(manifest=name, key=key, member=member, sha256=expected))

# Every compact file that was part of the frozen inventory must match byte for byte.
# This script and later independent reviews/README are additional report-only files.
receipts = []
for p in sorted(OUT.rglob('*')):
    if p.is_file() and not p.is_symlink():
        rel = str(p.relative_to(OUT))
        if rel in files:
            check(hashfile(p) == files[rel], 'compact_receipt_hash', rel)
            receipts.append(dict(path=rel, sha256=files[rel]))
        elif rel == 'archives.json':
            check(hashfile(p) == hashfile(RAW / 'archives.json'), 'copied_archive_receipt_hash')

# JIT artifacts have no independent checksum manifest; compute content hashes,
# retain workspace assembly/object/binary triplets and publication pairs, and
# reconcile them against exact inventory and corresponding workspace bytes.
jit = []
for name in sorted(files):
    if name.endswith('/jit.bin'):
        prefix = name[:-len('jit.bin')]
        present = {suffix: prefix + suffix in files for suffix in ('jit.S', 'jit.o', 'jit.bin')}
        if '/publications/' in prefix:
            check(present['jit.S'] and present['jit.bin'], 'jit_publication_pair', dict(prefix=prefix, present=present))
            session_root = prefix.split('/publications/', 1)[0]
            matching_workspaces = [other for other in files if other.startswith(session_root+'/workspace/') and other.endswith('/jit.bin') and files[other] == files[name] and files.get(other[:-7]+'jit.S') == files[prefix+'jit.S']]
            check(bool(matching_workspaces), 'jit_publication_matches_workspace', prefix)
        else:
            check(all(present.values()), 'jit_artifact_triplet', dict(prefix=prefix, present=present))
        jit.append(dict(path=name, bytes=members[name]['bytes'], sha256=files[name], assembly_sha256=files.get(prefix+'jit.S'), object_sha256=files.get(prefix+'jit.o')))
check({n for n in INV if n.endswith(('/jit.S','/jit.o','/jit.bin'))} == {n for n in files if n.endswith(('/jit.S','/jit.o','/jit.bin'))}, 'jit_inventory_exact')

# Read Git objects only; no checkout, archived script execution, compiler or VM.
CHECK_ARMS = {'checks': 'compact-index', 'checks-transfer': 'compact-transfer'}
checked_labels = {folder: jread(folder+'/result.json')['source_revision'] for folder in CHECK_ARMS}
candidate = jread('compact-transfer/matrix.json')['source_commit']
comparison = jread('comparison.json')
COMMITS = {}
for arm in ('compact-rcu', 'precompact-256', 'compact-index', 'compact-transfer'):
    versions = {p['source_commit'] for p in comparison['provenance'] if p['arm'] == arm}
    if len(versions) != 1:
        raise ValueError('Missing or mixed source versions: ' + arm)
    COMMITS[arm] = versions.pop()
check(COMMITS['compact-transfer'] == candidate, 'candidate_matrix_revision')
check(COMMITS['compact-rcu'].startswith('f0bd68d') and COMMITS['precompact-256'].startswith('0324e60'),
      'selected_baseline_revisions')
check(COMMITS['compact-index'].startswith('44f8eb6'), 'first_index_candidate_revision')
check(COMMITS['compact-index'] == jread('compact-index/matrix.json')['source_commit'],
      'first_index_matrix_revision')
if not all(re.fullmatch(r'[0-9a-f]{7,40}', commit) for commit in COMMITS.values()):
    raise ValueError('Invalid retained source revision')
git_cache, git_names = {}, {}
def git_bytes(commit, path):
    key = commit, path
    if key not in git_cache:
        git_cache[key] = subprocess.check_output(['git', 'show', commit + ':' + path], cwd=REPO)
    return git_cache[key]
for commit in COMMITS.values():
    git_names[commit] = set(subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', commit], cwd=REPO).decode().splitlines())

# The fresh RCU arm retains the report commit as its source label. Establish
# production equivalence with the prior implementation commit independently;
# never silently relabel the measured source or pool the older measurements.
prior_rcu = 'fcbacbe'
git_names[prior_rcu] = set(subprocess.check_output(
    ['git', 'ls-tree', '-r', '--name-only', prior_rcu], cwd=REPO).decode().splitlines())
def production_paths(commit):
    return {p for p in git_names[commit] if p.startswith(('include/', 'kernel_module/'))
            and (p.endswith(('.c', '.h', '.inc', '.S', '.def')) or p.endswith('/Makefile'))}
rcu_paths, prior_paths = production_paths(COMMITS['compact-rcu']), production_paths(prior_rcu)
same_rcu_paths = check(rcu_paths == prior_paths, 'rcu_baseline_production_paths')
rcu_mismatches = []
for path in sorted(rcu_paths & prior_paths):
    if not check(git_bytes(COMMITS['compact-rcu'], path) == git_bytes(prior_rcu, path),
                 'rcu_baseline_production_bytes', path):
        rcu_mismatches.append(path)
rcu_equivalence = dict(recorded_commit=COMMITS['compact-rcu'],
    earlier_implementation_commit=prior_rcu, production_files=len(rcu_paths),
    identical=same_rcu_paths and not rcu_mismatches, mismatches=rcu_mismatches,
    scope='Production include/kernel_module source only; the fresh benchmark block keeps its recorded source label.')

def source_commit(folder):
    prefix = folder.split('/')[0]
    if prefix in COMMITS:
        return COMMITS[prefix]
    if prefix in CHECK_ARMS:
        return COMMITS[CHECK_ARMS[prefix]]
    raise ValueError('Source snapshot has no explicit version mapping: ' + folder)

# Parse unified diff as inert data and replace each exact old hunk in order.
# Require unambiguous matches. No patch utility or retained program is executed.
def reconstruct_patch(commit, patch):
    output = {}
    lines = patch.decode().splitlines(keepends=True)
    i = 0
    while i < len(lines):
        if not lines[i].startswith('diff --git '):
            i += 1
            continue
        path = lines[i].split(' b/', 1)[1].strip()
        original = git_bytes(commit, path).decode().splitlines(keepends=True)
        result, cursor = [], 0
        i += 1
        while i < len(lines) and not lines[i].startswith('diff --git '):
            if not lines[i].startswith('@@ '):
                i += 1
                continue
            header = lines[i]
            i += 1
            old, new = [], []
            while i < len(lines) and not lines[i].startswith(('@@ ', 'diff --git ')):
                line = lines[i]
                if line.startswith(' '):
                    old.append(line[1:]); new.append(line[1:])
                elif line.startswith('-'):
                    old.append(line[1:])
                elif line.startswith('+'):
                    new.append(line[1:])
                elif line.startswith('\\ No newline'):
                    raise ValueError('Unexpected no-newline patch marker')
                else:
                    raise ValueError('Unexpected patch body: ' + repr(line))
                i += 1
            positions = [k for k in range(cursor, len(original)-len(old)+1) if original[k:k+len(old)] == old]
            if len(positions) != 1:
                raise ValueError('Patch old hunk not unique: ' + commit + ':' + path + ':' + header + ':' + str(positions))
            at = positions[0]
            result.extend(original[cursor:at]); result.extend(new)
            cursor = at + len(old)
        result.extend(original[cursor:])
        output[path] = ''.join(result).encode()
    return output

original_rows, prepared_rows = [], []
for row in source_manifest_rows:
    name = row['path']
    if row.get('prepared'):
        continue
    folder = name.rsplit('/', 1)[0]
    commit = source_commit(folder)
    manifest = jread(name)
    original = {p:h for p,h in manifest.items() if not p.startswith('bench/spin_cacheline/.build/provider/')}
    production = {p:h for p,h in original.items() if p.startswith(('include/', 'kernel_module/'))}
    expected_production = {p for p in git_names[commit] if p.startswith(('include/','kernel_module/')) and (p.endswith(('.c','.h','.inc','.S','.def')) or p.endswith('/Makefile'))}
    selected_production = {p for p in production if p in expected_production}
    check(selected_production == expected_production, 'original_production_complete', dict(manifest=name, missing=sorted(expected_production-selected_production), extra=sorted(selected_production-expected_production)))
    untracked, mismatches = [], []
    for path, digest in original.items():
        if path not in git_names[commit]:
            untracked.append(path)
            continue
        expected = sha(git_bytes(commit,path))
        check(expected == digest, 'original_source_git_hash', dict(manifest=name, commit=commit, path=path, actual=digest, expected=expected))
        if expected != digest:
            mismatches.append(path)
    check(not untracked, 'original_source_git_paths', dict(manifest=name, paths=untracked))
    original_rows.append(dict(manifest=name, commit=commit, original_files=len(original), production_files=len(production), private_inc_files=sum(p.endswith('.inc') for p in production), matched=len(original)-len(untracked)-len(mismatches), missing_from_git=untracked, mismatches=mismatches))
    prepared = {p.removeprefix('bench/spin_cacheline/.build/provider/'): folder+'/source/'+p for p in manifest if p.startswith('bench/spin_cacheline/.build/provider/')}
    if prepared:
        prepared_rows.append(dict(folder=folder, commit=commit, original_root=folder+'/source/', prepared=prepared))
for row in source_manifest_rows:
    if row.get('prepared'):
        folder = row['path'].rsplit('/',1)[0]
        prepared_rows.append(dict(folder=folder, commit=source_commit(folder), original_root=folder+'/source/', prepared={p:folder+'/build/provider/'+p for p in jread(row['path'])}))

prepared_result = []
for row in prepared_rows:
    root, commit = row['original_root'], row['commit']
    patch_path = root+'bench/spin_cacheline/provider/observation.patch'
    changes = reconstruct_patch(commit, contents[patch_path])
    classification = collections.Counter()
    exceptions = []
    for path, member in row['prepared'].items():
        if path == 'manifest.json':
            generated = jread(member)
            check(generated.get('complete') is True, 'generated_provider_manifest_complete', row['folder'])
            for target, digest in generated['prepared'].items():
                check(files.get(row['prepared'].get(target,'')) == digest, 'generated_provider_prepared_hash', dict(folder=row['folder'], path=target))
            for target, digest in generated['production'].items():
                check(sha(git_bytes(commit,target)) == digest, 'generated_provider_production_hash', dict(folder=row['folder'], path=target))
            for target, digest in generated['observation'].items():
                check(sha(git_bytes(commit,'bench/spin_cacheline/provider/'+target)) == digest, 'generated_provider_observation_hash', dict(folder=row['folder'], path=target))
            classification['generated_manifest'] += 1
            exceptions.append(dict(path=path, category='generated_manifest', sha256=files[member]))
            continue
        if path == 'include/kd_bench.h':
            expected = git_bytes(commit, 'bench/spin_cacheline/provider/kd_bench.h'); category='benchmark_overlay'
        elif path == 'kernel_module/kd_bench.c':
            expected = git_bytes(commit, 'bench/spin_cacheline/provider/kd_bench.c'); category='benchmark_overlay'
        elif path in changes:
            expected = changes[path]; category='observation_patch'
        else:
            expected = git_bytes(commit,path); category='unchanged_original'
        check(files[member] == sha(expected), 'prepared_reconstructed_hash', dict(folder=row['folder'], path=path, category=category))
        classification[category] += 1
        if category != 'unchanged_original':
            exceptions.append(dict(path=path, category=category, sha256=files[member]))
    check(set(changes).issubset(row['prepared']), 'prepared_patch_targets_retained', dict(folder=row['folder'], missing=sorted(set(changes)-set(row['prepared']))))
    prepared_result.append(dict(folder=row['folder'], commit=commit, files=len(row['prepared']), classification=dict(classification), patch_sha256=files[patch_path], expected_exceptions=exceptions))

# Current production byte identity is a separate check, not inferred from HEAD.
current_paths = sorted({p for p in git_names[candidate] if p.startswith(('include/','kernel_module/')) and (p.endswith(('.c','.h','.inc','.S','.def')) or p.endswith('/Makefile'))})
for path in current_paths:
    check((REPO/path).is_file() and hashfile(REPO/path) == sha(git_bytes(candidate,path)), 'current_production_git_hash', path)

dependency = 'tests/kernel/execution/exec_relay_exit_probe.c'
base_controls = ('missing-post-pin-key-validation','missing-observation-sequence-validation','free-before-retirement')
validation_rows = {}
for folder, arm in CHECK_ARMS.items():
    commit = COMMITS[arm]
    controls = base_controls
    if arm == 'compact-transfer':
        controls += ('borrow-ignores-current-owner','borrow-ignores-key',
                     'borrow-ignores-sequence-validation','fast-owner-restores-reference-pair',
                     'fast-owner-drops-transferred-reference','unlock-restores-temporary-reference',
                     'unlock-error-drops-owner-reference','unlock-drops-owner-before-gate')
    check(files.get(folder+'/source/'+dependency) == sha(git_bytes(commit,dependency)), 'kernel_probe_dependency_present_exact', folder)
    unit_log = contents[folder+'/unit.log'].decode()
    check(re.findall(r'Unit tests: (\d+) passed, (\d+) failed',unit_log) == [('14','0')], 'basic_and_affected_unit_totals', folder)
    check(all('mutation detected: '+c in unit_log for c in controls), 'aux_negative_controls_retained', folder)
    result = jread(folder+'/result.json')
    check(result['passed'] is True and result['final_idle'] is True and result['source_unchanged'] is True,
          'checks_result_passed_idle', folder)
    for probe in ('local','rwsem','instruction-exit'):
        live = jread(folder+'/'+probe+'/result.json')
        check(live['passed'] is True and live['drained'] is True, 'live_check_passed_drained', folder+'/'+probe)
    validation_rows[arm] = dict(log=folder+'/unit.log',kernel_probe_dependency=dependency,
        source_revision=commit,checked_source_label=checked_labels[folder],negative_controls=list(controls))
preparation = jread('preparation-failure.json')
failed_folder = preparation['retained_guest_directory']
check(preparation.get('workloads_started') is False and preparation.get('exit_code') != 0
      and failed_folder in members and members[failed_folder]['kind'] == 'dir', 'preparation_failure_retained')
check(not any(n.startswith(failed_folder+'/') and n.endswith(('/session.json','/records.json','/kernel.log')) for n in members),
      'preparation_failure_no_measured_session')
for arm in COMMITS:
    aux_paths = [p for p in files if p.startswith(arm+'/') and '/source/' in p and p.endswith(('/include/kd_mutex_aux.h','/kernel_module/kd_mutex_aux.c'))]
    check(bool(aux_paths) == (arm != 'precompact-256'), 'obsolete_aux_source_absent_from_old256', arm)

source_report = dict(schema=1, audit_script_sha256=hashfile(Path(__file__)), passed=not issues, scope='Read-only offline source and binary data audit; no build, test, VM command, extraction or execution of archived code', commits=COMMITS, original_source_manifests=original_rows, prepared_provider_snapshots=prepared_result, prepared_api_limitation='The eight API collections retain original sources, the preparation recipe and exact built binaries; they do not retain expanded private provider source trees. The eight synthetic/profile collections and both instruction-exit validations retain prepared provider sources reconstructed above.', binary_manifests=binary_rows, current_production=dict(commit=candidate, files=len(current_paths), private_inc_files=sum(p.endswith('.inc') for p in current_paths)), validation=validation_rows, preparation_failure=preparation, issues=issues)
source_report['rcu_baseline_production_equivalence'] = rcu_equivalence
archive_report = dict(schema=1, audit_script_sha256=hashfile(Path(__file__)), passed=not issues, scope='Read-only offline archive data audit; tar members read in memory without extraction or execution', host=socket.gethostname(), archive_receipt_sha256=hashfile(RAW/'archives.json'), inventory_sha256=hashfile(RAW/'input-inventory.json'), archived_groups=groups, inventory_members=len(INV), total_members=len(members), regular_files=len(files), regular_file_hash_map_sha256=sha(json.dumps(files,sort_keys=True,separators=(',',':')).encode()), metadata_checked=['path/type/mode/uid/gid','regular file byte length','symlink target and target byte length','mtime: (mtime_ns // 1_000_000_000) + (mtime_ns % 1_000_000_000) * 1e-9'], metadata_limits='Tar does not preserve inode, device, ctime, original directory st_size or original link counts; these remain in the hashed source inventory. Inventory contains stat metadata, not per-file hashes. All regular bytes were independently hashed; expected hashes are checked for source/binary manifests and compact copies, while whole-archive hashes bind all other content.', symlinks=links, compact_receipts=receipts, jit_artifacts=jit, source_manifest_count=len(source_manifest_rows), binary_manifest_entries=len(binary_rows), checks=dict(checks), issues=issues)
save('archive-review.json', archive_report)
save('source-review.json', source_report)
print(json.dumps(dict(passed=not issues, members=len(members), files=len(files), receipts=len(receipts), jit_binaries=len(jit), source_manifests=len(source_manifest_rows), binaries=len(binary_rows), checks=sum(checks.values()), issues=issues),indent=2))

raise SystemExit(1 if issues else 0)
