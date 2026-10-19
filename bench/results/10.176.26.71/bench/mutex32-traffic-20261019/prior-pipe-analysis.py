#!/usr/bin/env python3
"""Read-only investigation of retained prior pipe evidence; never executes archive code."""
import csv, hashlib, json, re, subprocess, tarfile
from pathlib import Path
root = Path(__file__).resolve().parents[5]
report = root/'bench/results/10.176.26.71/bench/mutex32-index-20261019'
raw = root/'bench/results/10.176.26.71/raw/bench/mutex32-index-20261019'
rows = list(csv.DictReader((report/'sessions.csv').open()))
index = {(r['arm'], r['name']): r for r in rows}
manifest = json.loads((raw/'archives.json').read_text())
groups = {group['group']: group for group in manifest['groups']}
out = {'schema': 1, 'scope': 'Read-only source and retained offline archive investigation. No build/test or archived code execution.',
       'source_report': str(report.relative_to(root)), 'samples': [], 'workload_batch_ratios': [],
       'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
       'sessions_csv_sha256': hashlib.sha256((report/'sessions.csv').read_bytes()).hexdigest(),
       'archives_manifest_sha256': hashlib.sha256((raw/'archives.json').read_bytes()).hexdigest(),
       'archives': {}, 'source_inspection': {},
       'limits': ['All provider and heat counters cover whole sessions, including warmup; measured-phase JIT fractions are separately retained.',
                  'The heat sampler is approximate admission state, not an ownership or retirement authority. Counter reconstruction is diagnostic only.',
                  'Ratio lines with zero unfinished entry counts are omitted at teardown; missing worker rows make reconstructed contentions incomplete.',
                  'Batch lengths are ratio of aggregate JIT successes to combiner starts, not a distribution.',
                  'The mechanism of slower producer circulation shortening batches is an inference, not causal attribution from a controlled ablation.']}
for revision in ('0324e60', 'e999008'):
    out['source_inspection'][revision] = {}
    for source in ('include/kd_mutex_direct.h', 'include/kd_hotlock.h',
                   'kernel_module/kd_hotlock.c', 'kernel_module/lock/mutex_calls.inc',
                   'bench/real_api/run.py', 'bench/real_api/client.c'):
        original = subprocess.run(['git', 'show', revision+':'+source], cwd=root,
                                  check=True, capture_output=True).stdout
        out['source_inspection'][revision][source] = hashlib.sha256(original).hexdigest()
for archive, arm in [('old256', 'precompact-256'), ('transfer', 'compact-transfer')]:
    archive_path = raw/(archive+'.tar.gz')
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    assert digest == groups[archive]['sha256'], (archive, 'archive checksum mismatch')
    assert archive_path.stat().st_size == groups[archive]['bytes']
    out['archives'][archive] = dict(sha256=digest, bytes=archive_path.stat().st_size)
    with tarfile.open(archive_path) as t:
        for m in t:
            if not m.name.endswith('kernel.log') or '/pipe/' not in m.name:
                continue
            prefix = m.name.rsplit('/', 1)[0]+'/'
            data = t.extractfile(m).read()
            ratios, finals = [], []
            for line in data.decode().splitlines():
                fields = dict((k, int(v)) for k, v in re.findall(r'(\w+)=(\d+)\b', line))
                if 'kd_hotlock mutex ratio:' in line:
                    ratios.append(fields)
                if 'kd_hotlock final:' in line and 'type=mutex' in line:
                    finals.append(fields)
            row = index[(arm, prefix.rstrip('/').split('/')[-1])]
            st = json.loads(row['whole_session_diagnostics'])['mutex_stats']
            aux = json.loads(row['whole_session_diagnostics']).get('mutex_aux')
            stats_lines = [line for line in data.decode().splitlines() if 'kd_mutex stats:' in line]
            assert len(stats_lines) == 1, m.name
            raw_stats = dict((k, int(v)) for k, v in re.findall(r'(\w+)=(\d+)\b', stats_lines[0]))
            assert raw_stats == st, (m.name, 'summary/raw stats mismatch')
            assert hashlib.sha256(data).hexdigest() == json.loads(row['whole_session_diagnostics'])['sha256']
            workers = int(row['threads'])
            bycpu = {r['cpu']: r for r in ratios}
            missing = [cpu for cpu in range(workers) if cpu not in bycpu]
            contentions = sum(r['checks']*1024+r['contentions'] for r in ratios)
            warm_data = t.extractfile(prefix+'warmup.json').read()
            measure_data = t.extractfile(prefix+'measure.json').read()
            warm, measure = json.loads(warm_data), json.loads(measure_data)
            session_data = t.extractfile(prefix+'session.json').read()
            session = json.loads(session_data)
            assert session['learning_waves'] == []
            assert session['jit_completions'] == int(row['jit_completions'])
            assert session['jit_bodies'] == session['jit_completions']
            assert measure['completed'] == int(row['completed']) == session['redirected_calls']
            assert session['threads'] == workers
            assert set(session['cpus']) == set(range(workers))
            assert not (set(bycpu) - set(session['cpus']) - {session['collector_cpu']})
            assert len(finals) == workers and all(r['cpu_hot'] and r['lock_hot'] for r in finals)
            # This runner performs one redirected check before and after its
            # single warmup and measurement; pipe has no helper learning waves.
            total = warm['completed']+measure['completed']+2
            other = None if missing else contentions-st['jit_success']-st['origin_acquires']
            fast = None if missing else total-contentions
            out['samples'].append(dict(arm=arm, name=row['name'], threads=workers,
                source_commit=row['source_commit'], kernel_log_member=m.name,
                kernel_log_sha256=hashlib.sha256(data).hexdigest(),
                session_json_sha256=hashlib.sha256(session_data).hexdigest(),
                warmup_sha256=hashlib.sha256(warm_data).hexdigest(),
                measure_sha256=hashlib.sha256(measure_data).hexdigest(),
                warmup_operations=warm['completed'], measured_operations=measure['completed'],
                whole_operations_including_checks=total, missing_ratio_cpus=missing,
                reconstructed_contentions=None if missing else contentions,
                incomplete_observed_contention_sum=contentions if missing else None,
                reconstructed_native_fast=fast, reconstructed_other_contended=other,
                native_fast_whole_fraction=None if fast is None else fast/total,
                measured_returned_jit_fraction=float(row['measured_returned_jit_share']),
                whole_jit_success=st['jit_success'], whole_origin_acquires=st['origin_acquires'],
                whole_combiner_starts=st['combiner'], bodies_per_combiner=st['jit_success']/st['combiner'],
                remaining_after_2047_per_worker_and_busy=None if other is None else other-2047*workers-(aux['busy'] if aux else 0),
                aux=aux, all_reported_final_mutex_heat_hot=all(r['cpu_hot'] and r['lock_hot'] for r in finals),
                last_sample_entries_min=min(r['last_entries'] for r in ratios),
                last_sample_entries_max=max(r['last_entries'] for r in ratios),
                failure_counters={k:st[k] for k in ['handoff','jit_not_ready','jit_failure','context_busy','node_overflow','frame_failure']}))
for row in rows:
    if row['arm'] not in ('precompact-256','compact-transfer') or row['collection']=='profile':
        continue
    st=json.loads(row['whole_session_diagnostics'])['mutex_stats']
    out['workload_batch_ratios'].append(dict(arm=row['arm'],workload=row['workload'],threads=int(row['threads']),repeat=int(row['repeat']),bodies_per_combiner=st['jit_success']/st['combiner'],gate_origin_acquires_per_1000_jit=1000*st['origin_acquires']/st['jit_success']))
out['conclusions'] = [
    'All old and transfer pipe sessions have zero handoff, JIT readiness/failure, context-busy, overflow and frame-failure counters.',
    'All three transfer pipe runs at 60 workers reconcile other contended entries to 60*2047 plus their 4/1/4 BUSY refusals; complete old records reconcile to 60*2047. This matches the startup admission threshold and gives no evidence for additional cooling-driven fallback.',
    'Transfer pipe repeats 1/2 at eight workers reconcile to 8*2047 plus BUSY. Repeat 0 retains an additional 16384 diagnostic residual and must not be treated as identical warmup.',
    'Whole-session native fast acquisitions rise from approximately 4.9% to 12.1-12.8% at 60 workers, and bodies/combiner fall from 127.3-127.7 to 66.6-67.1.',
    'Seek and c08 at 60 workers retain approximately 128 bodies/combiner, while short c01 and pipe do not. This supports investigating producer arrival/reference/hint overhead before changing batching or admission.',
    'The compact outer busy probe invokes external kd_mutex_combiner_active for a hash/sequence/key/gate observation; the old path used one inline gate load. The unchanged eight-probe count now includes up to eight such calls, extending the elapsed retry window and potentially creating additional native wins before admission. This is a mechanism to test, not a measured causal attribution.'
]
out['valid'] = True
print(json.dumps(out, indent=2))
