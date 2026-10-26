"""Plain aggregate completion, separate from paired-campaign qualification.

The strict validator checks identities, exact accounting, worker timing and
progress samples before requiring a positive full-cohort peak. Only that final
peak-availability outcome is optional here. Historical receipts are untouched.
Normal process exit, backend identity and module drain remain runner duties.
"""
import paired


def validate(rows, spec):
    paired.rt.require(spec['observation'] == 'plain', 'aggregate requires plain workload')
    peak_reason = None
    try:
        strict = paired.writer.validate(rows, spec)
        peak = strict['peak']
    except ValueError as error:
        if type(error) is not ValueError or str(error) != 'no positive full-cohort peak window':
            raise
        # No other malformed timing, accounting or progress result is optional.
        peak = None
        peak_reason = str(error)
    m = rows[1]
    paired.rt.require(all(not w['latency_ns'] for w in m['workers']),
                      'aggregate plain workload has latency samples')
    return dict(aggregate_valid=True, run_kind='single_aggregate_control',
                paired_campaign_accepted=False, threads=m['threads'],
                completed_pairs=m['completed'], wall_ns=m['wall_ns'],
                pairs_s=m['completed'] * 1e9 / m['wall_ns'],
                peak_status='available' if peak is not None else 'unavailable',
                peak=peak, peak_unavailable_reason=peak_reason)
