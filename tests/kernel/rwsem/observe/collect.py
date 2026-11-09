#!/usr/bin/env python3
"""Collect/decode generic callable rwsem events; live use belongs only in the VM."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import struct
import time

ABI = 1
HEADER_FIELDS = ('abi', 'header_bytes', 'event_bytes', 'symbol_bytes', 'symbol_count',
                 'capacity', 'reserved', 'count', 'overflow', 'missed', 'inflight',
                 'errors', 'armed', 'stopped', 'start_ns', 'stop_ns', 'proxy_proof',
                 'duration_ms', 'cutoff_ns')
EVENT_FIELDS = ('sequence', 'time_ns', 'lock', 'pairing_id', 'task_start_boottime_ns',
                'result', 'tid', 'tgid', 'cpu', 'event', 'api', 'reserved')
API_NAMES = ('write', 'write_killable', 'write_interruptible', 'write_trylock',
             'read', 'read_killable', 'read_interruptible', 'read_trylock',
             'downgrade', 'write_release', 'read_release')
BASE_SYMBOLS = ('down_write', 'down_write_killable', 'down_write_interruptible',
                'down_write_trylock', 'down_read', 'down_read_killable',
                'down_read_interruptible', 'down_read_trylock', 'downgrade_write',
                'up_write', 'up_read')
CATEGORIES = (1, 1, 1, 1, 2, 2, 2, 2, 3, 4, 5)
RETURNS = (1, 2, 2, 3, 1, 2, 2, 3, 1, 1, 1)
H = struct.Struct('<19Q')
S = struct.Struct('<4I128s')
E = struct.Struct('<5Qq6I')
A = struct.Struct('<4Q64I')
ARM = (1 << 30) | (A.size << 16) | (ord('R') << 8) | 0x71
STOP = (ord('R') << 8) | 0x72
HEADER = (2 << 30) | (H.size << 16) | (ord('R') << 8) | 0x73


def require(value, text):
    if not value:
        raise ValueError(text)


def decode(data):
    """Keep API completeness separate from censored protected-body intervals."""
    require(len(data) >= H.size, 'truncated header')
    h = dict(zip(HEADER_FIELDS, H.unpack_from(data)))
    require((h['abi'], h['header_bytes'], h['event_bytes'], h['symbol_bytes'], h['symbol_count']) ==
            (ABI, H.size, E.size, S.size, 11), 'ABI or record sizes differ')
    require(0 < h['capacity'] <= 262144 and h['count'] == min(h['reserved'], h['capacity']), 'invalid count')
    require(len(data) == H.size + 11*S.size + h['count']*E.size, 'truncated or trailing snapshot bytes')
    require(h['stopped'] == 1 and h['armed'] == 0 and h['proxy_proof'] == 0, 'snapshot not stopped or unsupported capability')
    require(h['start_ns'] <= h['cutoff_ns'] <= h['stop_ns'], 'invalid observation clocks')
    symbols = []
    for i in range(11):
        api, category, returns, registered, name = S.unpack_from(data, H.size+i*S.size)
        require((api, category, returns) == (i+1, CATEGORIES[i], RETURNS[i]) and registered in (0, 1), 'invalid API descriptor')
        end = name.find(b'\0')
        require(end >= 0 and not any(name[end:]), 'unterminated/nonzero-padded symbol name')
        name = name[:end].decode('ascii')
        symbols.append(dict(api=api, category=category, return_kind=returns, registered=registered, name=name))
    names = [s['name'] for s in symbols if s['name']]
    require(len(names) == len(set(names)), 'duplicate API symbols')
    rows = []
    for i in range(h['count']):
        row = dict(zip(EVENT_FIELDS, E.unpack_from(data, H.size+11*S.size+i*E.size)))
        require(row['sequence'] == i+1 and not row['reserved'], 'unpublished/out-of-order slot')
        require(row['tid'] > 0 and row['tgid'] > 0 and row['pairing_id'] > 0 and row['lock'] > 0, 'invalid event identity')
        require(1 <= row['api'] <= 11 and 1 <= row['event'] <= 7, 'invalid event kind/API')
        require(symbols[row['api']-1]['registered'] == 1, 'event for an unregistered API')
        require(h['start_ns'] <= row['time_ns'] <= h['stop_ns'], 'event outside actual capture/drain clocks')
        rows.append(row)
    issues = []
    for key in ('overflow', 'missed', 'inflight', 'errors'):
        if h[key]:
            issues.append(f'{key}={h[key]}')
    if h['overflow'] != max(0, h['reserved']-h['capacity']):
        issues.append('overflow/reservation mismatch')
    if any(s['name'] and not s['registered'] for s in symbols):
        issues.append('configured API not registered')
    calls = {}
    for row in rows:
        calls.setdefault(row['pairing_id'], []).append(row)
    pairs = []
    for pairing_id, events in sorted(calls.items()):
        events.sort(key=lambda r: (r['time_ns'], r['sequence']))
        if len(events) != 2:
            issues.append(f'incomplete API pair {pairing_id}: {len(events)} events')
            continue
        first, last = events
        require(all(first[k] == last[k] for k in ('api', 'lock', 'tid', 'tgid', 'task_start_boottime_ns')), 'API pair identity changed')
        category = symbols[first['api']-1]['category']
        expected = (1, (2, 3)) if category in (1, 2) else (4, (5,)) if category == 3 else (6, (7,))
        require(first['event'] == expected[0] and last['event'] in expected[1], 'invalid API event order')
        require(first['result'] == 0, 'entry event has a return value')
        if category in (1, 2):
            convention = symbols[first['api']-1]['return_kind']
            successful = convention == 1 or (last['result'] == 0 if convention == 2 else last['result'] != 0)
            require(last['event'] == (2 if successful else 3), 'return convention contradicts acquisition event')
        pairs.append(dict(pairing_id=pairing_id, api=API_NAMES[first['api']-1], lock=first['lock'],
                          tid=first['tid'], task_start_boottime_ns=first['task_start_boottime_ns'],
                          invoke_ns=first['time_ns'], return_ns=last['time_ns'],
                          duration_ns=last['time_ns']-first['time_ns'], result=last['result'],
                          event=last['event'], crosses_cutoff=last['time_ns'] > h['cutoff_ns']))
    # Reconstruct only same-task API-delimited body intervals. This is not an
    # ownership ledger: transferred/non-owner releases remain unmatched.
    open_shares, intervals = {}, []
    unmatched_release = unmatched_downgrade = 0
    for row in sorted(rows, key=lambda r: (r['time_ns'], r['sequence'])):
        category = symbols[row['api']-1]['category']
        key = (row['tid'], row['task_start_boottime_ns'], row['lock'])
        shares = open_shares.setdefault(key, [])
        if row['event'] == 2:
            shares.append(dict(mode='write' if category == 1 else 'read', begin_ns=row['time_ns'], pairing_id=row['pairing_id']))
        elif row['event'] in (4, 6):
            mode = 'write' if row['event'] == 4 or category == 4 else 'read'
            indexes = [i for i, share in enumerate(shares) if share['mode'] == mode]
            if not indexes:
                if row['event'] == 4:
                    unmatched_downgrade += 1
                else:
                    unmatched_release += 1
                continue
            share = shares.pop(indexes[-1])
            intervals.append(dict(tid=key[0], task_start_boottime_ns=key[1], lock=key[2], **share,
                                  end_ns=row['time_ns'], duration_ns=row['time_ns']-share['begin_ns'],
                                  censored_at_cutoff=row['time_ns'] > h['cutoff_ns'],
                                  observed_duration_in_window_ns=max(0, min(row['time_ns'], h['cutoff_ns'])-share['begin_ns'])))
        elif row['event'] == 5:
            shares.append(dict(mode='read', begin_ns=row['time_ns'], pairing_id=row['pairing_id']))
    return dict(schema=1, passed=not issues and bool(rows), capture_complete=not issues,
                observed=bool(rows), proxy_proof=False, delegation_episodes=None, critical_section_ratio=None,
                clock='CLOCK_MONOTONIC', header=h, symbols=symbols, events=rows,
                api_pairs=pairs, issues=issues, body_intervals=intervals,
                body_boundary='successful acquire return -> release/downgrade invocation; downgrade return begins read interval',
                body_censoring=dict(open_at_final_drain=sum(len(v) for v in open_shares.values()),
                                    completed_intervals_crossing_cutoff=sum(x['censored_at_cutoff'] for x in intervals),
                                    unmatched_release=unmatched_release, unmatched_downgrade=unmatched_downgrade),
                scope='Callable API timing only; no execution-origin, delegated body or ownership-transfer proof')


def read_snapshot(device):
    with open(device, 'rb', buffering=0) as stream:
        fcntl.ioctl(stream, STOP)
        parts = []
        while True:
            chunk = stream.read(1 << 20)
            if not chunk:
                break
            parts.append(chunk)
    return b''.join(parts)


def save(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for name in ('arm', 'stop', 'decode'):
        p = sub.add_parser(name)
        p.add_argument('--output', type=Path, required=True)
        if name == 'decode':
            p.add_argument('--input', type=Path, required=True)
        else:
            p.add_argument('--device', default='/dev/kd_rwsem_observe')
        if name == 'arm':
            p.add_argument('--tids', nargs='+', type=int, required=True)
            p.add_argument('--duration-ms', type=int, default=10)
            p.add_argument('--arm-only', action='store_true')
    p = sub.add_parser('symbols')
    p.add_argument('--family', choices=('kd', 'native'), default='kd')
    p.add_argument('--prefix')
    p.add_argument('--symbols-json', type=Path)
    args = parser.parse_args()
    if args.action == 'symbols':
        prefix = args.prefix if args.prefix is not None else 'kd_' if args.family == 'kd' else ''
        symbols = [prefix+x for x in BASE_SYMBOLS]
        if args.family == 'native':
            symbols[2] = ''
        if args.symbols_json:
            overrides = json.loads(args.symbols_json.read_text())
            require(isinstance(overrides, dict) and set(overrides) <= set(API_NAMES), 'unknown API name')
            symbols = [overrides.get(name, symbol) for name, symbol in zip(API_NAMES, symbols)]
        require(all(isinstance(x, str) and ',' not in x and '\n' not in x for x in symbols), 'invalid symbol value')
        print('api_symbols='+','.join(symbols))
        return
    args.output.mkdir(parents=True, exist_ok=False)
    data = None
    try:
        if args.action == 'arm':
            require(0 < len(args.tids) <= 64 and len(set(args.tids)) == len(args.tids) and
                    all(0 < t < (1 << 31) for t in args.tids) and 1 <= args.duration_ms <= 1000, 'invalid arm selection')
            require(len(next(x for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('NSpid:')).split()) == 2,
                    'live collector must use the initial PID namespace')
            values = (ABI, args.duration_ms, len(args.tids), 0, *args.tids, *([0]*(64-len(args.tids))))
            arm = A.pack(*values)
            save(args.output/'arm.json', dict(abi=ABI, tids=args.tids, duration_ms=args.duration_ms, proxy_proof=False))
            with open(args.device, 'rb', buffering=0) as stream:
                fcntl.ioctl(stream, ARM, arm)
            if args.arm_only:
                save(args.output/'result.json', dict(schema=1, state='ARMED', capture_complete=False, proxy_proof=False))
                return
            time.sleep(args.duration_ms/1000)
        data = args.input.read_bytes() if args.action == 'decode' else read_snapshot(args.device)
        (args.output/'events.bin').write_bytes(data)
        result = decode(data)
        save(args.output/'result.json', result)
        if not result['passed']:
            raise SystemExit(2)
    except (OSError, ValueError) as error:
        # An ARM failure can still leave a stopped diagnostic in the module.
        if args.action != 'decode' and data is None:
            try:
                data = read_snapshot(args.device)
                (args.output/'events.bin').write_bytes(data)
            except OSError as collection_error:
                save(args.output/'collection-error.json', dict(error=repr(collection_error)))
        save(args.output/'result.json', dict(schema=1, passed=False, capture_complete=False,
                                            proxy_proof=False, error=repr(error)))
        raise SystemExit(2)


if __name__ == '__main__':
    main()
