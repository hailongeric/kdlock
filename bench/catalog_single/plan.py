"""One-round catalog commands; execution belongs exclusively to the recovery VM."""
THREADS = list(range(1, 9)) + list(range(12, 61, 4))
GUEST = '/root/kdlock-evidence/10.176.26.71/bench/catalog-single-20261026'


def commands():
    common = ['--threads', *map(str, THREADS), '--collector-cpu', '63',
              '--repeats', '1', '--duration-ms', '2000',
              '--kernel-source', '/root/linux-6.1.159-kdclobber2',
              '--kernel-baseline', '/root/kdlock-kernel-baselines/mutex-clobber2-20260919']
    arms = ['--backends', 'native', 'tclock', 'kdlock']
    payloads = [('c01', 'cacheline', ['--cachelines', '1']),
                ('c08', 'cacheline', ['--cachelines', '8']),
                ('rcuht', 'rcuht', []), ('list16', 'list', ['--list-nodes', '16'])]
    for family in ('spin', 'mutex'):
        for label, workload, extra in payloads:
            name = family + '-' + label
            runner = 'run_mutex.py' if family == 'mutex' else 'run.py'
            args = [f'bench/tclock_compare/{runner}', *arms, *common,
                    '--cpus', '0-59', '--workload', workload, *extra, '--keep-going-no-jit']
            if family == 'mutex':
                args += ['--mutex-api', 'public']
            yield name, args + ['--output', GUEST + '/' + name]
    for family in ('rwlock', 'rwsem'):
        for label, workload, extra in payloads:
            for percent in (1, 20):
                name = f'{family}-{label}-w{percent:02d}'
                yield name, ['bench/rwlock_compare/run.py', *arms, *common,
                             '--cpus', *map(str, range(60)), '--lock-kind', family,
                             '--workloads', workload, *extra, '--write-percent', str(percent),
                             '--output', GUEST + '/' + name]
    for workload in ('argbounds', 'taskname'):
        for percent in (0, 20):
            name = f'{workload}-w{percent:02d}'
            yield name, ['bench/rwlock_compare/run.py', *arms, *common,
                         '--cpus', *map(str, range(60)), '--lock-kind', 'spin',
                         '--workloads', workload, '--write-percent', str(percent),
                         *(['--helper-waves', '0'] if workload == 'taskname' and percent else []),
                         '--output', GUEST + '/' + name]
    apis = [('ofd', ('front', 'tail', 'miss'), (16, 128)),
            ('setfd', ('toggle',), (16, 512)),
            ('pipebytes', ('query',), (16, 128)),
            ('pipecap', ('query',), (16,)),
            ('seek', ('set', 'end'), (16,)),
            ('utsname', ('host', 'domain'), (20,)),
            ('xattr', ('front', 'tail', 'miss', 'size'), (16, 128))]
    for kind, queries, counts in apis:
        for query in queries:
            for count in counts:
                name = f'{kind}-{query}-n{count}'
                yield name, ['bench/real_api/run.py', *arms, *common,
                             '--kinds', kind, '--queries', query, '--entries', str(count),
                             '--mutex-api', 'public', '--output', GUEST + '/' + name]


if __name__ == '__main__':
    import json
    print(json.dumps([dict(workload=name, argv=args) for name, args in commands()], indent=2))
