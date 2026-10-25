"""Explicit throughput eligibility; absent fields retain historical strict mode."""

STRICT = 'mmap-writer-proof-v1'
FUNCTIONAL = 'mmap-functional-v1'


def policy(row):
    value = row.get('eligibility_policy', STRICT)
    if value not in (STRICT, FUNCTIONAL):
        raise ValueError('unknown mmap eligibility policy')
    if value == STRICT and any(k in row for k in ('functional_complete', 'writer_observation',
                                                  'writer_observations', 'compatibility')):
        raise ValueError('prospective fields require explicit functional policy')
    return value


def fields(value):
    policy(dict(eligibility_policy=value))
    return {} if value == STRICT else dict(eligibility_policy=value)


def observation(row):
    if policy(row) == STRICT:
        return 'observed'
    value = row.get('writer_observation')
    if value not in ('observed', 'inconclusive'):
        raise ValueError('missing or invalid writer observation')
    return value


def observations(row):
    if policy(row) == STRICT:
        return {}
    values = row.get('writer_observations')
    if (not isinstance(values, dict) or set(values) != {'native', 'kd'} or
            any(v not in ('observed', 'inconclusive') for v in values.values())):
        raise ValueError('complete backend observation outcomes required')
    return values
