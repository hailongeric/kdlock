"""Summarize preserved observations; no benchmark or test execution."""
import collections
import csv
import io
import json
import pathlib
import statistics
import tarfile

base = pathlib.Path(__file__).resolve().parent
summary = []
for variant, archive in [('baseline', 'baseline-results.tar.gz'),
                         ('candidate', 'candidate-results-complete.tar.gz')]:
    with tarfile.open(base / archive) as tf:
        rows = [json.loads(line) for line in tf.extractfile(
            variant + '/evidence/points.jsonl')]
    groups = collections.defaultdict(list)
    for row in rows:
        key = tuple(row[k] for k in ['phase', 'policy', 'family', 'lines',
                                    'post', 'first_cpu', 'workers', 'backend'])
        groups[key].append(row)
    for key, points in sorted(groups.items()):
        rates = [r['mops'] for r in points]
        entry = dict(zip(['phase', 'policy', 'family', 'lines', 'post',
                          'first_cpu', 'workers', 'backend'], key))
        entry.update(variant=variant, samples=len(points), all_ok=all(r['ok'] for r in points),
                     median=statistics.median(rates), minimum=min(rates), maximum=max(rates),
                     rates=rates, total_ops=sum(r['ops'] for r in points),
                     counts={k: sum(r['kd_delta'].get(k, 0) for r in points)
                             for k in sorted({k for r in points for k in r['kd_delta']})})
        summary.append(entry)
(base / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
fields = ['variant', 'phase', 'policy', 'family', 'lines', 'post', 'first_cpu',
          'workers', 'backend', 'samples', 'all_ok', 'median', 'minimum', 'maximum', 'total_ops']
with (base / 'summary.csv').open('w') as out:
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction='ignore', lineterminator='\n')
    writer.writeheader()
    writer.writerows(summary)
