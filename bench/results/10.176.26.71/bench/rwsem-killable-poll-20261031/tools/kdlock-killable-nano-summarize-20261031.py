#!/usr/bin/env python3
"""Summarize already-validated fresh nano pairs; no measurements or archived code."""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import statistics

VALIDATION = '4db452836c12a1d8d05ff280c9731bf8008f6f51f714f5e8bac94740564eb858'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    validation = args.analysis / 'validation.json'
    assert sha(validation) == VALIDATION
    audit = json.loads(validation.read_bytes())
    assert audit['completed'] and audit['validated'] and audit['strict_qualified']
    assert audit['points'] == 420 and audit['pairs'] == 210 and not audit['performance_accepted']
    source = args.analysis / 'comparison/points.json'
    rows = json.loads(source.read_bytes())
    assert len(rows) == 210 and all(r['score_eligible'] for r in rows)
    for row in rows:
        old, new = row['reference_kd'], row['current_kd']
        for metric in ('whole', 'peak'):
            loss = new[metric + '_numerator'] * old[metric + '_denominator_ns'] < old[metric + '_numerator'] * new[metric + '_denominator_ns']
            assert loss is row['metrics'][metric]['observed_loss']
        assert row['any_observed_loss'] is any(row['metrics'][m]['observed_loss'] for m in ('whole', 'peak'))

    def label(row):
        return f"{row['lock_kind']} {row['workload']} w{row['write_percent']}"

    def point(row):
        return dict(workload=label(row), threads=row['threads'], execution=row['execution_transition'],
                    whole_change_pct=row['metrics']['whole']['change_pct'],
                    peak_change_pct=row['metrics']['peak']['change_pct'],
                    **{prefix + '_' + metric + '_ops_s': row[key][metric + '_ops_s']
                       for prefix, key in (('baseline', 'reference_kd'), ('candidate', 'current_kd'))
                       for metric in ('whole', 'peak')})

    def stats(values):
        result = dict(points=len(values), either_metric_losses=sum(r['any_observed_loss'] for r in values),
                      unscored=sum(not r['score_eligible'] for r in values))
        for metric in ('whole', 'peak'):
            changes = [r['metrics'][metric]['change_pct'] for r in values]
            result[metric] = dict(losses=sum(r['metrics'][metric]['observed_loss'] for r in values),
                                  median_change_pct=statistics.median(changes),
                                  minimum=point(min(values, key=lambda r: r['metrics'][metric]['change_pct'])),
                                  maximum=point(max(values, key=lambda r: r['metrics'][metric]['change_pct'])))
        return result

    profiles = collections.defaultdict(list)
    classes = collections.defaultdict(list)
    workers = collections.defaultdict(list)
    for row in rows:
        profiles[label(row)].append(row)
        classes[row['execution_transition']].append(row)
        workers[row['threads']].append(row)
    total = stats(rows)
    assert total['whole']['losses'] == audit['summary']['whole_losses']
    assert total['peak']['losses'] == audit['summary']['peak_losses']
    assert total['either_metric_losses'] == audit['summary']['either_metric_losses']
    image_equal = image_different = image_absent = 0
    for row in rows:
        images = []
        for key in ('reference_kd', 'current_kd'):
            published = row[key].get('published')
            images.append(published.get('images', {}).get('jit.bin') if isinstance(published, dict) else None)
        if not all(images):
            image_absent += 1
        elif images[0] == images[1]:
            image_equal += 1
        else:
            image_different += 1
    output = dict(schema=1, validation_sha256=VALIDATION, source_points_sha256=sha(source),
                  source_csv_sha256=sha(args.analysis / 'comparison/points.csv'),
                  script_sha256=sha(Path(__file__)), total=total,
                  profiles={name: stats(values) for name, values in profiles.items()},
                  execution_classes={name: stats(values) for name, values in classes.items()},
                  workers={str(n): stats(values) for n, values in sorted(workers.items())},
                  key_points=[point(r) for r in rows if r['threads'] in (20, 32, 60)],
                  worst_whole=[point(r) for r in sorted(rows, key=lambda r: r['metrics']['whole']['change_pct'])[:10]],
                  worst_peak=[point(r) for r in sorted(rows, key=lambda r: r['metrics']['peak']['change_pct'])[:10]],
                  full_elf_hashes=dict(provider_equal=sum(r['reference_kd']['provider_sha256'] == r['current_kd']['provider_sha256'] for r in rows),
                                       workload_equal=sum(r['reference_kd']['workload_binary_sha256'] == r['current_kd']['workload_binary_sha256'] for r in rows)),
                  jit_image_hashes=dict(equal=image_equal, different=image_different, absent_in_either=image_absent),
                  rounds_per_point=1, strict_qualified=True, no_regression_evidence_gate=False,
                  performance_accepted=False,
                  limits=['All negative signs retained; no magnitude threshold changes a result.',
                          'Sequential one-round arms; no variance or causal inference.',
                          'Full ELF hash differences do not identify differing instructions or a performance cause.',
                          'Matching JIT image bytes do not prove identical data placement or execution context.'])
    assert not args.output.exists()
    args.output.mkdir()
    (args.output / 'summary.json').write_text(json.dumps(output, indent=2, sort_keys=True) + '\n')
    with (args.analysis / 'comparison/points.csv').open() as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        selected = [r for r in reader if int(r['threads']) in (20, 32, 60)]
    assert len(selected) == 30
    with (args.output / 'key-points.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(selected)
    lines = ['# Fresh nano comparison: measured results', '',
             'All 210 matched pairs passed offline validation and strict host qualification. '
             'Whole-interval losses: 120; peak losses: 120; either metric: 123. '
             'No points were unscored. The no-regression evidence gate failed; the candidate remains unaccepted.', '',
             'Each profile has 21 worker counts and one round per point. Changes below compare 22d with f7; '
             'every negative counts, regardless of magnitude.', '',
             '| Workload | Whole losses | Peak losses | Either | Worst whole change | Worst peak change |',
             '| --- | ---: | ---: | ---: | --- | --- |']
    for name, values in profiles.items():
        s = stats(values)
        w, p = s['whole']['minimum'], s['peak']['minimum']
        lines.append(f"| {name} | {s['whole']['losses']}/21 | {s['peak']['losses']}/21 | {s['either_metric_losses']}/21 | {w['whole_change_pct']:+.4f}% at {w['threads']} | {p['peak_change_pct']:+.4f}% at {p['threads']} |")
    lines += ['', 'Selected worker counts; each cell is whole / peak change:', '',
              '| Workload | 20 workers | 32 workers | 60 workers |', '| --- | ---: | ---: | ---: |']
    for name, values in profiles.items():
        by_n = {r['threads']: r for r in values}
        cells = [f"{by_n[n]['metrics']['whole']['change_pct']:+.4f}% / {by_n[n]['metrics']['peak']['change_pct']:+.4f}%" for n in (20, 32, 60)]
        lines.append('| ' + name + ' | ' + ' | '.join(cells) + ' |')
    lines += ['', 'Exact baseline/candidate whole and peak rates for these 30 points are in `key-points.csv`. '
              'The original 210-row CSV is unchanged in the validated comparison directory.', '',
              'Execution classes:', '']
    for name, values in classes.items():
        s = stats(values)
        lines.append(f"- `{name}`: {s['points']} pairs; whole losses {s['whole']['losses']}, peak losses {s['peak']['losses']}, either {s['either_metric_losses']}.")
    lines += ['', 'The new helper is confined to killable writer admission. Ordinary/prepared nano writer paths '
              'do not directly call it, so this matrix is a regression check rather than a direct measurement '
              'of the proposed admission benefit. The signs are observed results; neither a parking fraction '
              'nor a causal explanation follows from these one-round sequential measurements. '
              'Full ELF hashes and JIT image comparisons are identity evidence only.', '']
    (args.output / 'README.md').write_text('\n'.join(lines))
    print(json.dumps(dict(completed=True, output=str(args.output), summary_sha256=sha(args.output / 'summary.json'),
                          whole_losses=total['whole']['losses'], peak_losses=total['peak']['losses'],
                          either_metric_losses=total['either_metric_losses'], performance_accepted=False)))


if __name__ == '__main__':
    main()
