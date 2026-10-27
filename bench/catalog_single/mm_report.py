"""Publish separate single-round MM suites from preserved attempted coordinates."""
import csv
import json
from pathlib import Path

from mm_plan import coordinates, key, require


def rows(suite, attempts):
    indexed = {}
    for attempt in attempts:
        root = Path(attempt['preserved'])
        attempted = {key(row) for row in attempt['attempted_coordinates']}
        require(len(attempted) == len(attempt['attempted_coordinates']) and not attempted & set(indexed),
                'cannot pool repeated MM attempts')
        for coordinate in attempted:
            indexed[coordinate] = dict(status='ATTEMPTED_NO_RECEIPT', completed=None, wall_ns=None,
                whole_mops_s=None, peak_mops_s=None, execution='UNMEASURED', drained=attempt.get('drained') is True,
                receipt=None, attempt=attempt['name'], performance_accepted=False)
        observed = set()
        for path in sorted(root.glob('*/result.json')):
            session = json.loads(path.read_text())
            coordinate = key(session)
            require(coordinate in attempted and coordinate not in observed, 'foreign or duplicate MM session receipt')
            observed.add(coordinate)
            qualified = attempt.get('endpoint_checked') is True
            m = session.get('measurement') or {}
            valid = session.get('passed') is True and session.get('drained') is True and qualified
            wall_ns = None
            if valid:
                receipt = [json.loads(line) for line in (path.parent / 'client.jsonl').read_text().splitlines()]
                require(len(receipt) == 2, 'missing raw timing receipt')
                raw = receipt[1]
                wall_ns = raw['wall_ns']
                require(type(m.get('completed')) is int and m['completed'] > 0 and
                        raw.get('completed') == m['completed'] and raw.get('complete') is True and
                        raw.get('data_ok') is True and type(wall_ns) is int and wall_ns > 0 and
                        m.get('errors') == 0 and m.get('delegated') is False,
                        'invalid completed MM measurement')
            indexed[coordinate] = dict(
                status='MEASURED_EXPLORATORY' if valid else ('FAILED' if session.get('state') == 'FAILED' else 'UNQUALIFIED'),
                completed=m.get('completed'), wall_ns=wall_ns,
                whole_mops_s=m['completed'] * 1000 / wall_ns if valid else None,
                peak_mops_s=(m.get('peak') or {}).get('throughput_ops_s', 0) / 1e6 if valid and m.get('peak') else None,
                execution=m.get('execution', 'UNMEASURED'), drained=session.get('drained') is True,
                receipt=str(path), attempt=attempt['name'], performance_accepted=False)
    plan = coordinates(suite)
    require(set(indexed) <= {key(row) for row in plan}, 'foreign MM coordinate in publication')
    return [dict(workers=row['threads'], backend=row['arm'],
                 **indexed.get(key(row), dict(status='NOT_RUN', completed=None, wall_ns=None,
                    whole_mops_s=None, peak_mops_s=None, execution='UNMEASURED', drained=False,
                    receipt=None, attempt=None, performance_accepted=False))) for row in plan]


def render(suite, attempts, output):
    values = rows(suite, attempts)
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'table.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(values[0]))
        writer.writeheader(); writer.writerows(values)
    (output / 'table.json').write_text(json.dumps(values, indent=2) + '\n')
    arms = list(dict.fromkeys(row['backend'] for row in values))
    text = ['# ' + suite, '', 'One two-second plain round per coordinate. Host policy: 2.0 GHz; timing remains exploratory.',
            'No repeat-based variance estimate. Missing or failed points have no throughput value.', '']
    if suite == 'independent-mmap':
        text += ['Independent native mm mappings; untouched mmap/munmap pairs. No KD/TCLock mmap arm.', '']
    elif suite == 'private-fault':
        text += ['MADV_DONTNEED plus checked read; Native/KD/TCLock protect private backing state. Kernel mmap locking stays Native; KD/TCLock readers execute locally.', '']
    else:
        text += ['Actual shared-mm mmap/munmap pairs with the selected built-in local backend. Native MM bodies execute on the original task; no body delegation.', '']
    text += ['| Workers | ' + ' | '.join(arm + ' Mops/s' for arm in arms) + ' |',
             '| ---: | ' + ' | '.join('---:' for _ in arms) + ' |']
    for n in sorted({row['workers'] for row in values}):
        entries = [next(row for row in values if row['workers'] == n and row['backend'] == arm) for arm in arms]
        text.append(f'| {n} | ' + ' | '.join(f"{row['whole_mops_s']:.6f}" if row['whole_mops_s'] is not None else row['status'] for row in entries) + ' |')
    text += ['', '[Full receipt table](table.csv)', '', '![Throughput](throughput.png)', '']
    (output / 'README.md').write_text('\n'.join(text))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axis = plt.subplots(figsize=(9, 5))
    for arm in arms:
        selected = [row for row in values if row['backend'] == arm]
        axis.plot([row['workers'] for row in selected],
                  [row['whole_mops_s'] if row['whole_mops_s'] is not None else float('nan') for row in selected],
                  marker='o', label=arm)
    axis.set(xlabel='Workers', ylabel='Whole-operation Mops/s', ylim=(0, None), title=suite + ' · one round')
    axis.grid(alpha=.2); axis.legend()
    fig.text(.5, .01, 'Exploratory · configured 2.0 GHz · n=1 · no error bars', ha='center')
    fig.tight_layout(rect=(0, .04, 1, 1)); fig.savefig(output / 'throughput.png', dpi=160)
    fig.savefig(output / 'throughput.svg'); plt.close(fig)
    return values
