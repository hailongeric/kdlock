#!/usr/bin/env python3
"""Bounded source-host MM campaign phases; never builds or boots a kernel.

Guest runners own correctness and normal drain. This controller binds actual
synchronized inputs, preserves every attempted phase, checks host endpoints and
publishes separate one-round suites. A failed coordinate is never retried.
"""
import argparse
import datetime
import fcntl
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import tarfile
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
from mm_plan import SUITES, attempted_coordinates, coordinates, key, remaining, require
from mm_report import render

SPEC = importlib.util.spec_from_file_location('mm_bounded_transport', HERE / 'linux70.py')
transport = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(transport)
sha, save = transport.sha, transport.save
GUEST_ROOT = Path('/root/host_fs/kdlock')
EVIDENCE_ROOT = Path('/root/kdlock-evidence/10.176.26.71/bench')
PYTHON = transport.PYTHON
PROFILES = {
    'private': ('7.0.0-38-kdlock1', 'kdlock1'),
    'native': ('7.0.0-38-kdmm1', 'kdmm1-native'),
    'kd': ('7.0.0-38-kdmm1', 'kdmm1-kd')}
SOURCE_DIRS = ('include/', 'kernel_module/', 'daemon/', 'disassem/', 'tclock_backend/',
               'workload_modules/mmap_fault/', 'workload_modules/mmap_writer/',
               'bench/mmap_fault/', 'bench/mmap_writer/', 'bench/mmap_lock/',
               'bench/spin_cacheline/', 'bench/tclock_compare/allocator_guard/',
               'bench/basic/', 'bench/catalog_single/', 'tests/protocols/', 'tests/unit/',
               'tests/kernel/mmap_fault/', 'tests/kernel/mmap_lock/', 'tests/kernel/mmap_writer/',
               'kernel_baseline/', 'kernel_integration/linux70/')
SOURCE_SUFFIXES = {'.c', '.h', '.inc', '.S', '.s', '.py', '.json', '.def', '.patch', '.sh'}


def profile(mode):
    release, variant = PROFILES[mode]
    return dict(release=release, variant=variant,
                build='/mnt/kdlock-builds/linux-' + release + '/build',
                bundle='/root/kdlock-kernel-baselines/linux70-' + variant + '-20261027')


def source_manifest():
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT).decode().split('\0')
    selected = {}
    for name in sorted(set(names)):
        path = ROOT / name
        if not name or not path.is_file() or path.is_symlink():
            continue
        if name != 'bench/archive_run.py' and not name.startswith(SOURCE_DIRS):
            continue
        if path.suffix not in SOURCE_SUFFIXES and path.name not in ('Makefile', 'Kbuild', 'requirements.txt'):
            continue
        selected[name] = sha(path)
    for name in ('bench/catalog_single/mm_dispatch.py', 'bench/catalog_single/mm_plan.py',
                 'bench/mmap_fault/timing.py', 'bench/mmap_writer/linux70.py',
                 'disassem/requirements.txt', 'kernel_integration/linux70/verify.py'):
        require(name in selected, 'required synchronized input omitted: ' + name)
    return dict(schema=1, translation_policy='trusted-kernel-and-module-source', commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                worktree_dirty=bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)),
                scope='Exact selected working-tree bytes, checked against the guest after idle synchronization; not a clean-commit claim',
                files=selected)


def checked_telemetry(path):
    events = [json.loads(line) for line in path.read_text().splitlines()]
    require(events and events[0]['event'] == 'start' and events[-1]['event'] == 'complete'
            and events[-1]['stop_requested'] is True, 'incomplete frequency telemetry')
    samples = [row for row in events if row['event'] == 'sample']
    require(samples and events[-1]['samples'] == len(samples), 'missing frequency samples')
    for row in samples:
        require(row['policy_ok'] is True and len(row['cpus']) == 64 and
                {cpu['cpu'] for cpu in row['cpus']} == set(range(64)), 'frequency coverage or policy changed')
    require(all(b['monotonic_ns'] > a['monotonic_ns'] for a, b in zip(samples, samples[1:])), 'frequency clock regressed')
    return dict(samples=len(samples), fixed_policy_khz=2000000, sha256=sha(path),
                thermal_before=events[0]['thermal'], thermal_after=events[-1]['thermal'],
                scope='APERF/MPERF samples retained separately; configured frequency is not an effective-frequency assertion')


def parse_health_capture(path, command_path, *, boot_id, release):
    """Accept drain only from a completed same-boot guest idle capture.

    A guest failure can leave an empty stdout file. Preserve that failure;
    neither a parse error nor a transport exit establishes workload retirement.
    """
    captured = []
    for selected in (path, command_path):
        try:
            value = json.loads(selected.read_text())
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError('unreadable endpoint evidence: ' + str(selected) + ': ' + repr(error)) from error
        require(isinstance(value, dict), 'endpoint evidence must be an object: ' + str(selected))
        captured.append(value)
    health, command = captured
    require(type(command.get('returncode')) is int and command['returncode'] == 0
            and command.get('completion_unconfirmed') is False,
            'endpoint command did not complete successfully')
    require(health.get('idle') is True and health.get('boot_id') == boot_id
            and health.get('release') == release, 'endpoint lacks an exact same-boot idle proof')
    require(all(isinstance(health.get(name), str) for name in ('modules', 'dmesg'))
            and all(type(health.get(name)) is int and health[name] >= 0
                    for name in ('taint', 'root_free', 'data_free')),
            'endpoint health fields are missing or invalid')
    return health


def record_phase_exit(row, command):
    row.update(completion_confirmed=command['returncode'] != 255, returncode=command['returncode'])
    if command['returncode'] not in (0, 255):
        row['primary_failure'] = dict(kind='GUEST_EXIT', returncode=command['returncode'],
            command_receipt=row['name'] + '-command.json', stdout=row['name'] + '.stdout',
            stderr=row['name'] + '.stderr',
            error='guest phase exited with status ' + str(command['returncode']) + ': ' + row['name'])


def stop_phase(row, error):
    """Keep a failed workload primary even if endpoint collection also fails."""
    row['state'] = 'STOPPED'
    if row.get('primary_failure'):
        row['error'] = row['primary_failure']['error']
        row['secondary_error'] = repr(error)
    else:
        row['error'] = repr(error)


def verify_preservation(row, raw):
    base = Path(row['preserved'])
    require(sha(raw / (row['name'] + '-archive.stdout')) == row['archive_sha256'], 'preserved archive changed')
    require(sha(base / 'preservation.json') == row['preservation_sha256'], 'preserved inventory changed')
    inventory = json.loads((base / 'preservation.json').read_text())['inventory']
    expected = {name for name, entry in inventory.items() if entry['kind'] == 'file'}
    actual = {str(path.relative_to(base)) for path in base.rglob('*') if path.is_file()}
    require(actual == expected | {'preservation.json'} and not any(path.is_symlink() for path in base.rglob('*')),
            'preserved regular-file scope changed')
    for name in expected:
        require(sha(base / name) == inventory[name]['sha256'], 'preserved evidence bytes changed: ' + name)
    require(sha(base / 'result.json') == row['result_sha256'], 'preserved phase result changed')


def validate_review(review, suite, campaign, context, manifest_sha, attempts):
    require(review.get('schema') == 1 and review.get('approved') is True and
            review.get('purpose') == 'resume-unmeasured-mm-coordinates', 'explicit reviewed continuation receipt required')
    require(review.get('suite') == suite and review.get('campaign') == campaign and
            review.get('context') == context and review.get('source_manifest_sha256') == manifest_sha,
            'review belongs to another campaign, source or boot')
    expected = [{key: row[key] for key in ('name', 'result_sha256', 'archive_sha256', 'preservation_sha256', 'session_receipts', 'attempted_coordinates')}
                for row in attempts]
    require(review.get('prior_attempts') == expected, 'review does not bind every prior attempt')
    require(all(row.get('preserved') and row.get('completion_confirmed') and row.get('drained')
                for row in attempts), 'unknown completion or drain cannot authorize continuation')
    attempted = [coordinate for row in attempts for coordinate in row['attempted_coordinates']]
    result = remaining(suite, attempted)
    require(review.get('coordinates') == result and result, 'review must select exactly unmeasured coordinates')
    return result


def existing_attempts(index, action, context, suite=None):
    if suite:
        attempts = [row for row in index if row.get('suite') == suite]
        require(all(row['context'] == context for row in attempts),
                'suite already attempted on another boot/context; never rerun its coordinates')
        return attempts
    return [row for row in index if row['action'] == action and row['context'] == context]


class Controller:
    def __init__(self, args):
        self.args, self.platform = args, profile(args.mode)
        require(re.fullmatch(r'catalog-linux70-mm-[a-z0-9-]+', args.campaign), 'invalid campaign identity')
        require(args.guest_base == EVIDENCE_ROOT / args.campaign, 'canonical guest evidence base required')
        require(re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', args.boot_id), 'exact boot UUID required')
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', args.snapshot), 'explicit snapshot tag required')
        self.raw = ROOT / 'bench/results/10.176.26.71/raw/bench' / args.campaign
        self.public = ROOT / 'bench/results/10.176.26.71/bench' / args.campaign
        self.raw.mkdir(parents=True, exist_ok=True); self.public.mkdir(parents=True, exist_ok=True)
        self.context = dict(mode=args.mode, boot_id=args.boot_id, snapshot=args.snapshot, **self.platform)
        self.prefix = args.mode + '-' + args.boot_id
        self.guest = args.guest_base
        self.env = [value for value in transport.ENV if not value.startswith('KDLOCK_SNAPSHOT_TAG=')]
        self.env += ['KDLOCK_SNAPSHOT_TAG=' + args.snapshot]
        transport.RAW, transport.GUEST, transport.SNAPSHOT, transport.ENV = self.raw, str(self.guest), args.snapshot, self.env
        self.index_path = self.raw / 'phases.json'
        self.index = json.loads(self.index_path.read_text()) if self.index_path.exists() else []

    def remote(self, label, argv, **kwargs):
        return transport.remote(label, argv, **kwargs)

    def upload(self, label, local, target):
        data = local.read_bytes()
        # Structured bytes are emitted as Python literals, never shell substitutions.
        code = ('from pathlib import Path\nimport hashlib\np=Path(%r)\nb=%r\n'
                'assert hashlib.sha256(b).hexdigest()==%r\np.parent.mkdir(parents=True,exist_ok=True)\n'
                'if p.exists(): assert p.read_bytes()==b\n'
                'else:\n with p.open("xb") as stream: stream.write(b)\n') % (str(target), data, sha(local))
        self.remote(label, [*self.env, PYTHON, '-'], code=code)

    def health(self, label):
        code = '''import json,os,runpy,shutil,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,'/root/host_fs/kdlock/bench/spin_cacheline')
import bench_runtime as rt
runpy.run_path('/root/host_fs/kdlock/bench/archive_run.py')['idle'](Path(%r),rt.idle)
for proc in Path('/proc').glob('[0-9]*/cmdline'):
 try: argv=proc.read_bytes().split(bytes([0]))
 except (FileNotFoundError,ProcessLookupError): continue
 assert not any(v.startswith((b'/root/host_fs/kdlock/bench/',b'/root/host_fs/kdlock/tests/kernel/')) for v in argv),str(proc)
assert os.uname().release==%r
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==%r
print(json.dumps(dict(idle=True,release=os.uname().release,boot_id=%r,
modules=Path('/proc/modules').read_text(),taint=int(Path('/proc/sys/kernel/tainted').read_text()),
root_free=shutil.disk_usage('/root').free,data_free=shutil.disk_usage('/mnt/kdlock-builds').free,
dmesg=subprocess.check_output(['dmesg'],text=True))))
''' % ('/root/kdlock-evidence', self.platform['release'], self.args.boot_id, self.args.boot_id)
        self.remote(label, [*self.env, 'taskset', '-c', '63', PYTHON, '-'], code=code)
        row = parse_health_capture(self.raw / (label + '.stdout'), self.raw / (label + '-command.json'),
                                   boot_id=self.args.boot_id, release=self.platform['release'])
        require(row['root_free'] >= 2 * 1024**3, 'guest root reserve below 2 GiB')
        return row

    def admission(self, label):
        row = self.health(label + '-health')
        require(not re.search(r'BUG:|Oops:|Kernel panic|general protection fault|WARNING: CPU:', row['dmesg']), 'kernel fault/warning at admission')
        captured = transport.capture(label + '-host')
        reference_path = self.raw / (self.prefix + '-host-reference.json')
        if not reference_path.exists():
            save(reference_path, captured)
            self.upload(label + '-reference-upload', reference_path, self.guest / (self.prefix + '-host-reference.json'))
        reference = json.loads(reference_path.read_text())
        require(not transport.compare(reference, captured), 'host identity/pinning/frequency differs from selected reference')
        guest_host = self.guest / (label + '-host.json')
        self.upload(label + '-host-upload', self.raw / (label + '-host.stdout'), guest_host)
        common = ['--boot-id', self.args.boot_id, '--host-state', str(guest_host),
                  '--host-reference', str(self.guest / reference_path.name), '--host-reference-sha256', sha(reference_path),
                  '--kernel-variant', self.platform['variant'], '--kernel-source', self.platform['build'],
                  '--kernel-baseline', self.platform['bundle']]
        if self.args.mode != 'private': common += ['--mode', self.args.mode]
        return row, captured, common

    def freeze(self):
        local = self.raw / 'source-manifest.json'
        if local.exists():
            frozen = json.loads(local.read_text())
            require(frozen['files'] == source_manifest()['files'],
                    'campaign source changed; do not mix revisions')
        else:
            frozen = source_manifest(); save(local, frozen)
        for name, digest in frozen['files'].items():
            target = self.raw / 'inputs' / name
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as output:
                    output.write((ROOT / name).read_bytes())
            require(sha(target) == digest and sha(ROOT / name) == digest,
                    'source changed during exact input preservation: ' + name)
        self.manifest, self.manifest_sha = local, sha(local)
        label = self.prefix + '-source-verify-' + str(time.time_ns())
        self.upload(label + '-upload', local, self.guest / local.name)
        code = '''import hashlib,json,os
from pathlib import Path
p=Path(%r)
assert hashlib.sha256(p.read_bytes()).hexdigest()==%r
m=json.loads(p.read_text());root=Path('/root/host_fs/kdlock')
assert os.uname().release==%r
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==%r
for name,digest in m['files'].items():
 q=Path(name);assert not q.is_absolute() and '..' not in q.parts
 assert hashlib.sha256((root/q).read_bytes()).hexdigest()==digest,name
print(json.dumps(dict(passed=True,files=len(m['files']),source_manifest_sha256=%r)))
''' % (str(self.guest / local.name), self.manifest_sha, self.platform['release'], self.args.boot_id, self.manifest_sha)
        self.remote(label, [*self.env, PYTHON, '-'], code=code, seconds=120)

    def persist(self):
        save(self.index_path, self.index)
        save(self.public / 'phases.json', self.index)
        lines = ['# Linux 7 single-round MM catalog', '',
                 'Configured host policy: 2.0 GHz. One plain two-second round per point; timing remains exploratory.',
                 'Private backing locks and actual shared-mm locking are separate suites. Kernel/boot/source identities remain in the phase receipts.', '',
                 '| Suite | Measured / planned | Attempted without qualified rate | Results |',
                 '| --- | ---: | ---: | --- |']
        for suite in ('independent-mmap', 'private-fault', 'shared-mm'):
            path = self.public / suite / 'table.json'
            rows = json.loads(path.read_text()) if path.exists() else []
            measured = sum(row['whole_mops_s'] is not None for row in rows)
            failures = sum(row['status'] != 'NOT_RUN' and row['whole_mops_s'] is None for row in rows)
            lines.append(f'| {suite} | {measured} / {len(coordinates(suite))} | {failures} | ' +
                         (f'[Table and chart]({suite}/README.md)' if path.exists() else 'Pending') + ' |')
        lines += ['', '[Phase and preservation receipts](phases.json). Failed and uncertain attempts are retained; no retries or repetition variance are inferred.', '']
        (self.public / 'README.md').write_text('\n'.join(lines))

    def verified_phase(self, action, *, mode=None, same_boot=True):
        mode = mode or self.args.mode
        matches = [row for row in self.index if row['action'] == action and row['context']['mode'] == mode
                   and (not same_boot or row['context']['boot_id'] == self.args.boot_id)]
        require(matches and matches[-1]['state'] == 'COMPLETE', 'required completed phase missing: ' + action + '/' + mode)
        row = matches[-1]
        verify_preservation(row, self.raw)
        require(row['source_manifest_sha256'] == self.manifest_sha, 'prerequisite source revision differs')
        return row

    def check_sources(self, label, output, inputs=None, required_manifests=()):
        code = '''import hashlib,json,re
from pathlib import Path
p=Path(%r)
assert hashlib.sha256(p.read_bytes()).hexdigest()==%r
for name,digest in json.loads(p.read_text())['files'].items():
 assert hashlib.sha256((Path('/root/host_fs/kdlock')/name).read_bytes()).hexdigest()==digest,name
base=Path(%r)
for name in %r:
 q=base/name;assert q.is_file(),name
 values=json.loads(q.read_text());assert isinstance(values,dict) and values,name
 if name.endswith('-sha256.json'):
  scope=base
  if name=='source-sha256.json' and (base/'source').is_dir():scope=base/'source'
  elif name=='prepared-source-sha256.json':scope=base/'build/provider'
  for relative,digest in values.items():
   part=Path(relative);assert '..' not in part.parts
   assert isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest),relative
   if name=='runtime-source-sha256.json':assert part.is_absolute();target=part
   else:assert not part.is_absolute();target=scope/part
   assert hashlib.sha256(target.read_bytes()).hexdigest()==digest,relative
binary=base/'binary-sha256.json'
if binary.exists():
 for name,digest in json.loads(binary.read_text()).items():
  assert hashlib.sha256((base/name).read_bytes()).hexdigest()==digest,name
inputs=Path(%r) if %r else base/'inputs.json'
if inputs.exists():
 for name,digest in json.loads(inputs.read_text())['files'].items():
  assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
phase=json.loads((base/'result.json').read_text())
if 'probe_sha256' in phase:
 assert hashlib.sha256((base/'source/tests/kernel/mmap_lock/payload/kd_mmap_probe.ko').read_bytes()).hexdigest()==phase['probe_sha256']
if 'binary_sha256' in phase:
 assert hashlib.sha256((base/'fault_cases').read_bytes()).hexdigest()==phase['binary_sha256']
print(json.dumps(dict(passed=True,source_manifest_sha256=%r)))
''' % (str(self.guest / self.manifest.name), self.manifest_sha, str(output), tuple(required_manifests),
       str(inputs), bool(inputs), self.manifest_sha)
        self.remote(label, [*self.env, PYTHON, '-'], code=code, seconds=120)

    def preserve(self, name, guest_directory):
        inventory_code = '''import json,sys
from pathlib import Path
sys.path.insert(0,'/root/host_fs/kdlock/bench/catalog_single')
from mm_archive import inventory
print(json.dumps(inventory(Path(%r)),sort_keys=True))
''' % str(guest_directory)
        self.remote(name + '-inventory-before', [*self.env, PYTHON, '-'], code=inventory_code, seconds=180)
        before = json.loads((self.raw / (name + '-inventory-before.stdout')).read_text())
        self.remote(name + '-archive', ['timeout', '240', 'tar', '--hard-dereference', '-czf', '-', '-C', str(guest_directory.parent), guest_directory.name], seconds=260)
        self.remote(name + '-inventory-after', [*self.env, PYTHON, '-'], code=inventory_code, seconds=180)
        require(before == json.loads((self.raw / (name + '-inventory-after.stdout')).read_text()), 'evidence changed while preserving')
        destination = self.raw / name
        require(not destination.exists(), 'preserved destination exists')
        destination.mkdir()
        seen = set()
        with tarfile.open(self.raw / (name + '-archive.stdout')) as archive:
            for member in archive:
                path = PurePosixPath(member.name)
                require(not path.is_absolute() and '..' not in path.parts and path.parts[0] == guest_directory.name, 'unsafe archive member')
                relative = str(PurePosixPath(*path.parts[1:]))
                if not path.parts[1:]:
                    require(member.isdir(), 'archive root is not a directory'); continue
                require(relative in before and relative not in seen, 'unlisted or duplicate archive member')
                seen.add(relative); expected = before[relative]
                require(member.mode & 0o7777 == expected['mode'] & 0o7777, 'archive mode changed: ' + relative)
                if member.isdir():
                    require(expected['kind'] == 'directory', 'archive directory changed'); continue
                if member.issym():
                    require(expected['kind'] == 'link' and expected['target'] == member.linkname, 'archive link changed')
                    continue  # Retained inside tar; never materialize an external link on the source host.
                require(member.isfile() and expected['kind'] == 'file', 'unsupported archive member')
                target = destination / relative; target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open('xb') as output:
                    import shutil
                    shutil.copyfileobj(source, output)
                require(sha(target) == expected['sha256'], 'archive file hash changed: ' + relative)
        require(seen == set(before), 'archive omitted evidence')
        save(destination / 'preservation.json', dict(complete=True, files=len(seen), inventory=before,
             archive_sha256=sha(self.raw / (name + '-archive.stdout')), links_materialized=False))
        return destination

    def run(self, action, runner, argv, *, suite=None, request=None):
        attempts = existing_attempts(self.index, action, self.context, suite)
        if attempts and not suite:
            require(attempts[-1]['state'] == 'COMPLETE', 'failed prerequisite needs explicit diagnosis/new campaign')
            return self.verified_phase(action)
        selected = coordinates(suite) if suite else None
        if attempts:
            if attempts[-1]['state'] == 'COMPLETE': return self.verified_phase(action)
            for prior in attempts:
                verify_preservation(prior, self.raw)
            require(self.args.resume_review and self.args.resume_sha256 and sha(self.args.resume_review) == self.args.resume_sha256,
                    'interrupted measurement needs a hash-bound reviewed continuation')
            selected = validate_review(json.loads(self.args.resume_review.read_text()), suite, self.args.campaign,
                                       self.context, self.manifest_sha, attempts)
        else:
            require(not self.args.resume_review, 'continuation review without a prior attempt')
        name = self.prefix + '-' + action + '-a' + str(len(attempts)).zfill(2)
        require(not (self.raw / (name + '-command.json')).exists(), 'attempt command already exists')
        row = dict(name=name, action=action, suite=suite, context=self.context, state='PREFLIGHT',
                   source_manifest_sha256=self.manifest_sha, endpoint_checked=False, drained=False,
                   completion_confirmed=False, performance_accepted=False)
        self.index.append(row); self.persist()
        monitor = None
        guest_output = self.guest / name
        try:
            require(not (self.raw / 'STOP').exists(), 'STOP requested at drained phase boundary')
            before, host_before, common = self.admission(name + '-before')
            actual = [*argv, '--output', str(guest_output), *common]
            if request is not None:
                data = dict(schema=1, suite=suite, boot_id=self.args.boot_id,
                            manifest=str(self.guest / self.manifest.name), manifest_sha256=self.manifest_sha,
                            coordinates=selected, argv=actual,
                            prior_attempts=[dict(directory=r['guest_output'], result_sha256=r['result_sha256'],
                                session_receipts=r['session_receipts'], attempted_coordinates=r['attempted_coordinates'],
                                inventory=json.loads((Path(r['preserved'])/'preservation.json').read_text())['inventory']) for r in attempts])
                local = self.raw / (name + '-request.json'); save(local, data)
                self.upload(name + '-request-upload', local, self.guest / local.name)
                runner = 'bench/catalog_single/mm_dispatch.py'
                actual = [str(self.guest / local.name), '--sha256', sha(local)]
            monitor = transport.monitor_start(name)
            row.update(state='RUNNING', guest_output=str(guest_output)); self.persist()
            command = self.remote(name, [*self.env, PYTHON, str(GUEST_ROOT / runner), *actual], seconds=3400, allowed=tuple(range(256)))
            record_phase_exit(row, command)
            self.persist()
            require(row['completion_confirmed'], 'SSH failure leaves guest completion unknown')
            health_error = None
            try:
                after = self.health(name + '-after-health')
            except Exception as error:
                health_error = repr(error)
                row['health_error'] = health_error
                self.persist()
                # A local reserve check can fail after the guest proved idle.
                # A missing/failed guest idle proof still forbids preservation.
                after = parse_health_capture(self.raw / (name + '-after-health.stdout'),
                    self.raw / (name + '-after-health-command.json'),
                    boot_id=self.args.boot_id, release=self.platform['release'])
            row['drained'] = after['idle'] is True
            row['drain_proof'] = dict(kind='SAME_BOOT_GUEST_IDLE',
                health_sha256=sha(self.raw / (name + '-after-health.stdout')),
                command_sha256=sha(self.raw / (name + '-after-health-command.json')))
            capture_error = None
            try:
                host_after = transport.capture(name + '-after-host')
            except Exception as error:
                capture_error = repr(error); host_after = None
            telemetry_error = None
            try:
                transport.monitor_stop(name, monitor)
                row['telemetry'] = checked_telemetry(self.raw / (name + '-frequency.jsonl'))
            except Exception as error:
                telemetry_error = repr(error)
                row['telemetry_error'] = telemetry_error
            row['telemetry_stopped'] = monitor[0].poll() is not None
            if row['telemetry_stopped']: monitor = None
            faults = bool(re.search(r'BUG:|Oops:|Kernel panic|general protection fault|WARNING: CPU:', after['dmesg']))
            problems = transport.compare(host_before, host_after) if host_after else ['host endpoint capture failed: ' + capture_error]
            if health_error: problems.append('endpoint health check: ' + health_error)
            if after['modules'] != before['modules'] or (after['taint'] & ~12288) != (before['taint'] & ~12288):
                problems.append('unexpected module or taint change')
            row['endpoint_checked'] = not faults and not problems and not telemetry_error and row['telemetry_stopped']
            row['endpoint_problems'] = problems + (['kernel fault/warning'] if faults else [])
            preserved = self.preserve(name, guest_output)
            row.update(preserved=str(preserved), result_sha256=sha(preserved / 'result.json'),
                       archive_sha256=sha(self.raw / (name + '-archive.stdout')),
                       preservation_sha256=sha(preserved/'preservation.json'),
                       session_receipts={str(p.relative_to(preserved)): sha(p) for p in sorted(preserved.glob('*/result.json'))})
            if suite:
                row['attempted_coordinates'] = attempted_coordinates(suite, selected,
                    json.loads((preserved/'preservation.json').read_text())['inventory'],
                    (self.raw/(name+'.stdout')).read_text())
            try:
                inputs = actual[actual.index('--inputs') + 1] if request is None and '--inputs' in actual else None
                if request is not None and '--inputs' in data['argv']:
                    inputs = data['argv'][data['argv'].index('--inputs') + 1]
                required = {
                    'correctness-kd': ('source-sha256.json', 'binary-sha256.json', 'prepared-source-sha256.json'),
                    'correctness-tc': ('source-sha256.json', 'binary-sha256.json'),
                    'preparation': ('inputs.json',),
                    'mapping': ('source-sha256.json', 'binary-sha256.json', 'runtime-source-sha256.json'),
                    'completed': ('source-sha256.json', 'binary-sha256.json', 'runtime-source-sha256.json'),
                    'api': ('source-sha256.json', 'runtime-source-sha256.json'),
                    'faults': ('source-sha256.json', 'runtime-source-sha256.json'),
                    'shared-preparation': ('inputs.json', 'runtime-source-sha256.json')}.get(action, ('inputs.json',))
                self.check_sources(name + '-source-after', guest_output, inputs, required)
                row['source_verified_after'] = True
            except Exception as source_error:
                row['source_verified_after'] = False
                row['endpoint_checked'] = False
                row['source_error'] = repr(source_error)
            self.persist()
            if suite:
                measured = render(suite, [r for r in self.index if r.get('suite') == suite and r.get('preserved')], self.public / suite)
                row['measured'] = sum(r['whole_mops_s'] is not None for r in measured)
                print('TABLE_READY', suite, self.public / suite / 'README.md', flush=True)
                if suite.startswith('shared-'):
                    shared = [r for r in self.index if r.get('suite') in ('shared-native', 'shared-kd') and r.get('preserved')]
                    images = [json.loads((Path(r['preserved'])/'result.json').read_text()).get('image_identity') for r in shared]
                    require(images and all(image and image == images[0] for image in images), 'shared plot would mix kernel image identities')
                    first_host = json.loads((self.raw/(shared[0]['name']+'-before-host.stdout')).read_text())
                    for other in shared[1:]:
                        other_host = json.loads((self.raw/(other['name']+'-before-host.stdout')).read_text())
                        # Each mode has its own explicitly confirmed recovery tag.
                        # All actual host/QEMU/NUMA/frequency identities must agree.
                        comparable = dict(first_host, recovery_snapshot=other_host['recovery_snapshot'])
                        require(not transport.compare(comparable, other_host), 'shared plot would mix host identities')
                    render('shared-mm', shared, self.public/'shared-mm')
            result = json.loads((preserved / 'result.json').read_text())
            require(command['returncode'] == 0 and result.get('passed') is True and result.get('drained') is True,
                    'phase failed; preserved partial results do not authorize retry')
            require(row['endpoint_checked'], 'host/kernel endpoint failed')
            if suite:
                require([key(item) for item in result['sessions']] == [key(item) for item in selected]
                        and all(item['passed'] and item['drained'] for item in result['sessions']), 'selected coordinates incomplete')
            elif action in ('correctness-kd', 'correctness-tc'):
                require(result.get('split') is True and result.get('basic_programs') == 2 and
                        len(result['split_cases']) == (12 if action == 'correctness-kd' else 6),
                        'full private split correctness coverage missing')
            elif action == 'preparation':
                require(len(result['sessions']) == 8 and result.get('basic_programs') == 2 and
                        all(s['passed'] and s['drained'] and s['observation'] == 'plain' for s in result['sessions']),
                        'eight plain preparation controls required')
            row.update(state='COMPLETE', strict_timing_qualified=False, exploratory=True)
            self.persist(); return row
        except BaseException as error:
            stop_phase(row, error); self.persist()
            if monitor is not None and monitor[0].poll() is None:
                try: transport.monitor_stop(name, monitor)
                except Exception as monitor_error: row['monitor_error'] = repr(monitor_error); self.persist()
            raise

    def execute(self):
        for path in self.raw.glob('*-command.json'):
            command = json.loads(path.read_text())
            require(command.get('completion_unconfirmed') is not True and command.get('returncode') != 255,
                    'unconfirmed transport requires operator diagnosis before any further guest work: ' + path.name)
        require(not any(row['state'] in ('RUNNING', 'STOPPED') and
                        (not row.get('completion_confirmed') or not row.get('drained') or
                         row.get('telemetry_stopped') is False) for row in self.index),
                'prior completion/drain is unknown; operator diagnosis is required before any further guest work')
        require(not (self.raw/'STOP').exists(), 'STOP requested before guest admission')
        self.health(self.prefix + '-idle-admission-' + str(time.time_ns()))
        self.freeze()
        if self.args.action == 'private-prepare':
            require(self.args.mode == 'private', 'private mode required')
            common = ['--source-manifest', str(self.guest / self.manifest.name)]
            kd = self.run('correctness-kd', 'tests/kernel/mmap_fault/run.py', [*common, '--backends', '0,1', '--split'])
            tc = self.run('correctness-tc', 'tests/kernel/mmap_fault/run.py', [*common, '--backends', '2', '--split', '--native-kd-result', kd['guest_output'] + '/result.json'])
            prep = self.run('preparation', 'bench/mmap_fault/timing.py', ['prepare', *common, '--plain-only',
                '--correctness-kd', kd['guest_output'], '--correctness-tc', tc['guest_output']])
            label = self.prefix + '-negative-oracles'
            if not (self.raw / (label + '-command.json')).exists():
                self.remote(label, [*self.env, PYTHON, str(GUEST_ROOT / 'bench/mmap_fault/check_oracles.py'), prep['guest_output']], seconds=120)
            oracle_command = json.loads((self.raw / (label + '-command.json')).read_text())
            require(oracle_command.get('returncode') == 0 and oracle_command.get('completion_unconfirmed') is False,
                    'negative oracle process completion is unconfirmed or failed')
            oracle = json.loads((self.raw / (label + '.stdout')).read_text())
            require(oracle['passed'] is True and oracle['positive_receipts'] == 1 and len(set(oracle['rejected'])) == 9,
                    'private preparation negative oracles did not pass')
            save(self.raw / (self.prefix + '-private-ready.json'), dict(passed=True, context=self.context,
                 preparation=prep['name'], oracle_sha256=sha(self.raw / (label + '.stdout'))))
        elif self.args.action == 'private-measure':
            require(self.args.mode == 'private' and self.args.suite in ('independent-mmap', 'private-fault'), 'private suite required')
            ready = json.loads((self.raw / (self.prefix + '-private-ready.json')).read_text())
            require(ready['passed'] is True and ready['context'] == self.context and
                    ready['oracle_sha256'] == sha(self.raw / (self.prefix + '-negative-oracles.stdout')), 'same-boot preparation/oracles required')
            prep = self.verified_phase('preparation')
            self.run(self.args.suite, '', ['measure', '--inputs', prep['guest_output'] + '/inputs.json',
                '--single-round-grid', '--workload', SUITES[self.args.suite][0], '--exploratory-host'], suite=self.args.suite, request=True)
        elif self.args.action == 'shared-sites':
            require(self.args.mode != 'private', 'shared mode required')
            # Site capture has no workload and no result.json; preserve its own exact receipt.
            label = self.prefix + '-writer-sites'
            self.admission(label + '-before')
            argv = [*self.env, PYTHON, str(GUEST_ROOT / 'bench/mmap_writer/sites.py'), '--mode', self.args.mode,
                    '--boot-id', self.args.boot_id, '--kernel-variant', self.platform['variant'],
                    '--kernel-source', self.platform['build'], '--kernel-baseline', self.platform['bundle'],
                    '--output', str(self.guest / label)]
            self.remote(label, argv, seconds=300)
            self.health(label + '-after-health'); self.preserve(label, self.guest / label)
            print('REVIEW_WRITER_SITES', self.raw / label / 'writer-sites.json', flush=True)
        else:
            require(self.args.mode != 'private', 'shared mode required')
            if self.args.action == 'shared-correctness':
                label = self.prefix + '-writer-sites'
                sites = self.raw / label / 'writer-sites.json'
                require(self.args.writer_sites_sha256 and sha(sites) == self.args.writer_sites_sha256,
                        'explicit reviewed current-ELF writer-site hash required')
                api = self.run('api', 'tests/kernel/mmap_lock/run.py', [])
                self.run('mapping', 'tests/kernel/mmap_lock/mapping.py', ['--api-result', api['guest_output'] + '/result.json',
                    '--writer-sites', str(self.guest / label / 'writer-sites.json'), '--writer-sites-sha256', sha(sites)])
                self.run('faults', 'tests/kernel/mmap_lock/faults.py', [])
                self.run('completed', 'tests/kernel/mmap_lock/page_fault_completed/run.py', [])
            else:
                prerequisites = []
                for kind in ('api', 'mapping', 'faults', 'completed'):
                    row = self.verified_phase(kind)
                    prerequisites += ['--' + kind + '-result', row['guest_output'] + '/result.json']
                if self.args.action == 'shared-prepare':
                    extra = []
                    if self.args.mode == 'kd':
                        native = self.verified_phase('shared-preparation', mode='native', same_boot=False)
                        extra = ['--reuse-inputs', native['guest_output'] + '/inputs.json']
                    self.run('shared-preparation', 'bench/mmap_writer/linux70.py', ['prepare', *prerequisites, *extra])
                else:
                    own = self.verified_phase('shared-preparation', same_boot=False)
                    other = self.verified_phase('shared-preparation', mode='kd' if self.args.mode == 'native' else 'native', same_boot=False)
                    suite = 'shared-' + self.args.mode
                    self.run(suite, '', ['measure', *prerequisites, '--inputs', own['guest_output'] + '/inputs.json',
                        '--other-preparation', other['guest_output'] + '/result.json', '--exploratory-host'], suite=suite, request=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('private-prepare', 'private-measure', 'shared-sites', 'shared-correctness', 'shared-prepare', 'shared-measure'))
    parser.add_argument('--campaign', required=True)
    parser.add_argument('--guest-base', type=Path, required=True)
    parser.add_argument('--mode', choices=tuple(PROFILES), required=True)
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--suite', choices=('independent-mmap', 'private-fault'))
    parser.add_argument('--writer-sites-sha256')
    parser.add_argument('--resume-review', type=Path)
    parser.add_argument('--resume-sha256')
    args = parser.parse_args()
    require(ROOT == Path('/home/eric/vm/vm-shared/kdlock'), 'controller belongs on source host 380G10')
    controller = Controller(args)
    with (controller.raw / 'owner.lock').open('a') as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        controller.execute()


if __name__ == '__main__':
    main()
