"""Read-only audit of focused NUMA/mutex experiments; never runs benchmarks."""
import argparse
import collections
import importlib.util
import json
import re
from pathlib import Path
import shutil

p = argparse.ArgumentParser()
p.add_argument('--root', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--helpers', type=Path)
a = p.parse_args()
root, out = a.root.resolve(), a.output.resolve()
out.mkdir(parents=True, exist_ok=True)
bundled = Path(__file__).with_name('matrix-audit-helpers.py')
export_path = a.helpers or (bundled if bundled.exists() else Path('/root/host_fs/kdlock/bench/full_compare/export.py'))
spec = importlib.util.spec_from_file_location('matrix_audit', export_path)
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
counts = collections.Counter()
samples, diagnoses, failures, groups = [], [], [], []
for folder in sorted(root.iterdir()):
    if not folder.is_dir() or not (folder/'plan.json').exists():
        continue
    name = folder.name
    plan = json.loads((folder/'plan.json').read_text())
    rows = [json.loads((folder/r['name']/'session.json').read_text())
            if (folder/r['name']/'session.json').exists() else r for r in plan]
    if (folder/'failure.json').exists():
        failures.append(dict(group=name, failure=json.loads((folder/'failure.json').read_text())))
    if not (folder/'source-sha256.json').exists():
        if not (folder/'failure.json').exists() or any(r.get('execution_status') not in (None, 'NOT_RUN') for r in rows):
            raise ValueError(f'missing frozen source for executed group: {name}')
        groups.append(dict(group=name, planned=len(plan), executed=0, accepted=0,
                           statuses={'BUILD_FAILED_BEFORE_FREEZE': len(plan)}))
        continue
    for relative, expected in json.loads((folder/'source-sha256.json').read_text()).items():
        if e.digest(folder/'source'/relative) != expected:
            raise ValueError(f'frozen source differs: {name}/{relative}')
        counts['source_hashes'] += 1
    if (folder/'binary-sha256.json').exists():
        for original, expected in json.loads((folder/'binary-sha256.json').read_text()).items():
            _, marker, relative = original.partition('/'+name+'/')
            binary = folder/relative if marker else folder/'binaries'/Path(original).name
            if e.digest(binary) != expected:
                raise ValueError(f'ELF differs: {binary}')
            counts['binary_hashes'] += 1
    info = dict(group=name, planned=len(plan), executed=0, accepted=0, statuses=collections.Counter())
    for row in rows:
        info['statuses'][row.get('execution_status', 'NOT_RUN')] += 1
        if row.get('execution_status') in (None, 'NOT_RUN'):
            continue
        info['executed'] += 1
        if not row.get('drained'):
            raise ValueError(f'undrained: {name}/{row["name"]}')
        if row['arm'] == 'kdlock':
            if row.get('published_before') != row.get('published_after'):
                raise ValueError('publication changed')
            if row.get('retired') != dict(state=2, modules=0, frames=0, writers=0):
                raise ValueError('source retirement differs')
            publication = row.get('published_before')
            if publication:
                entry = publication['entry']
                images = folder/row['name']/'workspace/daemon'/hex(entry['entry'])/str(entry['tgid'])/'asm'
                for image, expected in publication['images'].items():
                    if e.digest(images/image) != expected:
                        raise ValueError('JIT image differs')
                    counts['jit_image_hashes'] += 1
        if not row.get('performance_result', True) or row.get('measurement_mode') == 'functional':
            diagnoses.append(dict(group=name,name=row['name'],status=row.get('execution_status'),
                                  drained=row['drained'], jit_bodies=row.get('jit_bodies'),
                                  lost_samples=row.get('lost_samples')))
            continue
        if e.accepted(row):
            e.independently_check_peak(row)
            counts['independent_peaks'] += 1
            info['accepted'] += 1
        result = e.sample(name,row)
        log = (folder/row['name']/'kernel.log').read_text()
        if re.search(r'BUG:|WARNING:|Oops:|general protection fault|kernel panic|KASAN:|UBSAN:', log, re.I):
            raise ValueError(f'kernel error in {name}/{row["name"]}')
        pattern = r'kd_spin lock stats: [^\n]+' if row['lock_kind']=='spin' else r'kd_mutex stats: [^\n]+'
        diagnostics = [dict((k,int(v)) for k,v in re.findall(r'([a-z_]+)=([0-9]+)(?= |$)',line)) for line in re.findall(pattern,log)]
        result['lifetime_combiner_count'] = sum(d.get('combiner',0) for d in diagnostics)
        result['lifetime_jit_success'] = sum(d.get('jit_success',0) for d in diagnostics)
        result['lifetime_jit_bodies_per_combiner'] = (result['lifetime_jit_success']/result['lifetime_combiner_count'] if result['lifetime_combiner_count'] else None)
        peak = row.get('measurement',{}).get('peak',{}).get('worker_completed',[])
        result['min_worker_peak_ops'] = min(peak) if peak else None
        result['min_worker_whole_ops'] = min((w['completed'] for w in row.get('measurement',{}).get('workers',[])),default=None)
        result['peak_node_share'] = {k:v/sum(result['peak_node_completed'].values()) for k,v in result['peak_node_completed'].items()}
        samples.append(result)
    groups.append(info)
buckets = collections.defaultdict(list)
for row in samples:
    buckets[(row['group'], row['write_percent'], row['threads'], row['arm'])].append(row)
statistics = [e.aggregate(key,rows) for key,rows in buckets.items()]
e.csv_write(out/'samples.csv',samples)
e.csv_write(out/'statistics.csv',statistics)
e.json_write(out/'samples.json',samples)
e.json_write(out/'statistics.json',statistics)
e.json_write(out/'audit.json',dict(groups=groups,checks=dict(counts),timed_sessions=len(samples),
    accepted=sum(r['accepted'] for r in samples),diagnostic_sessions=diagnoses,failures=failures))
shutil.copyfile(__file__,out/'audit.py')
shutil.copyfile(export_path,out/'matrix-audit-helpers.py')
print(json.dumps(dict(groups=len(groups),checks=dict(counts),sessions=len(samples),
                     accepted=sum(r['accepted'] for r in samples),diagnoses=len(diagnoses),failures=len(failures))))
