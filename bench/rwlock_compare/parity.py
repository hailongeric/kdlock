"""Strict observed throughput comparison; consumes validated summary groups."""


def assess(plan, summary):
    points = {}
    for spec in plan:
        if spec['functional']:
            continue
        key = (spec['workload'], spec['cachelines'], spec['write_percent'], spec['threads'])
        points.setdefault(key, {})[spec['arm']] = spec['variant']
    result = []
    for (workload, lines, percent, threads), variants in sorted(points.items()):
        row = dict(workload=workload, cachelines=lines, write_percent=percent,
                   threads=threads, status='INCOMPLETE')
        cohorts = {arm: [s for s in summary if s['variant'] == variant and
                        s['write_percent'] == percent and s['threads'] == threads]
                   for arm, variant in variants.items()}
        # Mixed JIT/NO_JIT groups remain separate. A partial group is never
        # promoted to a three-round result or pooled to manufacture parity.
        if (set(cohorts) != {'native', 'tclock', 'kdlock'} or
                any(len(groups) != 1 or not groups[0]['complete'] or
                    groups[0]['valid_rounds'] != 3 for groups in cohorts.values())):
            row['reason'] = 'Need three validated rounds per backend in one execution-status group'
        else:
            kd = cohorts['kdlock'][0]
            row['kd_jit_status'] = kd['jit_status']
            row['ratios'] = {arm: {
                'best_peak': kd['best_peak_ops_s'] / cohorts[arm][0]['best_peak_ops_s'],
                'median_whole': kd['whole_median_ops_s'] / cohorts[arm][0]['whole_median_ops_s'],
            } for arm in ('native', 'tclock')}
            row['status'] = ('PASS' if all(ratio >= 1 for values in row['ratios'].values()
                                         for ratio in values.values()) else 'FAIL')
        result.append(row)
    return dict(criterion='KD best warmed peak and median whole-run throughput >= both comparators',
                status=('PASS' if result and all(r['status'] == 'PASS' for r in result) else
                        'FAIL' if any(r['status'] == 'FAIL' for r in result) else 'INCOMPLETE'),
                points=result)
