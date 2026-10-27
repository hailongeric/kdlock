"""Exact MM coordinate selection, shared by the host controller and guest dispatcher."""
WORKERS = tuple(range(1, 9)) + tuple(range(12, 61, 4))
SUITES = {'independent-mmap': ('mmap', ('native',)),
          'private-fault': ('fault', ('native', 'kdlock', 'tclock')),
          'shared-native': ('mmap-shared-mm', ('native',)),
          'shared-kd': ('mmap-shared-mm', ('kd',)),
          'shared-mm': ('mmap-shared-mm', ('native', 'kd'))}


def require(value, message):
    if not value:
        raise ValueError(message)


def key(row):
    return (row['workload'], row['threads'], row.get('backend', row['arm']))


def coordinates(suite):
    workload, arms = SUITES[suite]
    return [dict(workload=workload, threads=n, arm=arm) for n in WORKERS for arm in arms]


def select(suite, original, requested):
    expected = coordinates(suite)
    require([key(row) for row in original] == [key(row) for row in expected], 'runner full grid changed')
    require(all(row['repeat'] == 0 and row['observation'] == 'plain' and
                row['duration_ms'] == 2000 and row['cpus'] == list(range(row['threads'])) and
                row['collector_cpu'] == 63 and row.get('collector_shared') is False
                for row in original), 'runner operation, placement or repetition changed')
    keys = [key(row) for row in requested]
    require(keys and len(keys) == len(set(keys)), 'empty or duplicate selected coordinates')
    require(keys == [key(row) for row in expected if key(row) in keys], 'selected coordinates are outside the ordered grid')
    return [row for row in original if key(row) in keys]


def remaining(suite, attempted):
    all_keys = {key(row) for row in coordinates(suite)}
    used = [key(row) for row in attempted]
    require(len(used) == len(set(used)) and set(used) <= all_keys, 'duplicate or foreign prior coordinate')
    return [row for row in coordinates(suite) if key(row) not in used]


def session_name(suite, index, row):
    if suite.startswith('shared-'):
        return f'{index:02d}-shared-mm-{row["arm"]}-t{row["threads"]}-r00'
    return f'{index:02d}-{row["workload"]}-{row["threads"]}-{row["arm"]}-plain-r0'


def attempted_coordinates(suite, selected, inventory, stdout):
    names = {session_name(suite, i, row): row for i, row in enumerate(selected)}
    observed = {name.split('/')[0] for name in inventory}
    announced = {line.split()[1] for line in stdout.splitlines() if line.startswith('START ') and len(line.split()) >= 2}
    require(announced <= set(names), 'unknown announced coordinate')
    infrastructure = {'source', 'build', 'runtime-source', 'kernel-baseline'}
    directories = {name for name, row in inventory.items() if '/' not in name and row['kind'] == 'directory'}
    require(directories <= set(names) | infrastructure, 'unclassified attempt directory')
    used = observed & set(names) | announced
    return [row for name, row in names.items() if name in used]
