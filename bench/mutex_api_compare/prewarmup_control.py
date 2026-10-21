"""Ordered no-timing control around exactly one original warmup.

A refused, fully observed gate is a normal diagnostic result. Transport or
lifetime exceptions propagate: this helper cannot infer drain from a timeout.
"""


class PreWarmupRefused(Exception):
    """A fully observed precondition refused; the original warmup was skipped."""


def capture_policy(prewarmup, sequence, stage):
    expected = ('before-warmup', 'after-warmup-immediate') if prewarmup else ('after-warmup',)
    if type(sequence) is not int or not 1 <= sequence <= len(expected) or stage != expected[sequence-1]:
        raise ValueError('unexpected boundary stage or sequence')
    return 'immediate' if prewarmup and sequence == 2 else 'wait'


def run_once(exchange, warmup, record, clock):
    if 'prewarmup_control' in record:
        raise ValueError('original warmup control cannot be repeated')
    state = record['prewarmup_control'] = dict(warmup_commands=0, measurement_commands=0)
    pre = exchange('before-warmup')
    if not pre['gate']['passed']:
        state['warmup_skipped'] = True
        raise PreWarmupRefused()
    state.update(warmup_skipped=False, warmup_commands=1, command_began_ns=clock())
    result = warmup()
    # The frozen reply reader has already saved warmup.json here. Preserve its
    # behavior and expose the interval before the immediate post-stage request.
    state['reply_saved_ns'] = clock()
    record['boundary_warmup'] = result
    exchange('after-warmup-immediate')
    return result


def validate_transition(before, after, work):
    """Joined/drained work may change exact counters, never session identity."""
    if (not work['ok'] or before['client_pid'] != after['client_pid'] or
            before['publication'] != after['publication'] or
            not before['physical_idle'] or not after['physical_idle'] or
            after['calls']-before['calls'] != work['completed']):
        raise ValueError('warmup changed prepared identity or exact operation accounting')
    delta = {key: after['counters'][key]-value for key, value in before['counters'].items()}
    if not (0 <= delta['bench_jit_bodies'] == delta['bench_jit_completions'] <= work['completed'] and
            delta['address_guard_count'] == 0):
        raise ValueError('warmup returned-body or address-guard accounting differs')
    return delta
