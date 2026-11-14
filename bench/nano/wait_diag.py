"""Temporary aggregate wait diagnostic; no tracing or timing policy changes."""
import fcntl
import struct

from protocol import DEVICE

MODE = 0xC010420E
SNAPSHOT = 0x4210
COUNTERS = (
    'read_prepare',
    'read_first',
    'read_reinsert',
    'read_linked',
    'write_prepare',
    'write_first',
    'write_reinsert',
    'write_linked',
    'read_begin',
    'read_return',
    'read_cancel',
    'read_error',
    'read_direct',
    'read_reserved',
    'read_rollback',
    'read_wake_retry',
    'read_schedule',
    'read_progress_retry',
    'write_begin',
    'write_return',
    'write_cancel',
    'write_error',
    'write_turn_wait',
    'write_start',
    'write_wake_retry',
    'write_schedule',
    'write_refuse_read',
    'write_refuse_write',
    'write_refuse_wake',
    'release_wake_retry',
    'wake_read',
    'wake_write',
    'wake_queue',
    'wake_wait',
    'wake_cancel',
    'read_visits',
    'read_accept',
    'write_visits',
    'write_accept',
    'turn_wake_request',
    'turn_wake_accept',
)


def set_mode(enabled):
    if type(enabled) is not bool:
        raise ValueError('wait_diagnostic must be a boolean')
    buffer = bytearray(struct.pack('=2Q', int(enabled), 0))
    with open(DEVICE, 'rb', buffering=0) as device:
        fcntl.ioctl(device, MODE, buffer, True)
    actual, supported = struct.unpack('=2Q', buffer)
    if actual != int(enabled) or supported not in (0, 1) or (enabled and not supported):
        raise ValueError('wait diagnostic mode or support differs')
    return dict(enabled=bool(actual), supported=bool(supported))


def collect(started_ns, workers, backend, enabled):
    count = len(COUNTERS)
    buffer = bytearray(72 + 64 * count * 8)
    with open(DEVICE, 'rb', buffering=0) as device:
        fcntl.ioctl(device, SNAPSHOT, buffer, True)
    version, fields, active, supported, nworkers, arm, start, complete, node_wait = struct.unpack_from('=9Q', buffer)
    if ((version, fields, active, nworkers, arm, start) !=
            (2, count, int(enabled), workers, backend, started_ns) or
            supported not in (0, 1) or complete not in (0, 1) or
            node_wait not in (0, 1) or (node_wait and backend != 2)):
        raise ValueError('wait diagnostic identity differs')
    rows = [dict(zip(COUNTERS, struct.unpack_from(f'={count}Q', buffer, 72 + i * count * 8)))
            for i in range(workers)]
    return dict(version=version, enabled=bool(active), supported=bool(supported),
                complete=bool(complete), backend=arm, started_ns=start,
                node_wait=bool(node_wait),
                scheduler_activations_available=False, workers=rows,
                total={name: sum(row[name] for row in rows) for name in COUNTERS})


def validate(result, completed_reads, completed_writes):
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    require(result['complete'], 'wait diagnostic worker lifetime incomplete')
    total = result['total']
    if not result['enabled'] or result['backend'] == 0:
        require(not any(total.values()), 'disabled/Native diagnostic has KD counts')
        return
    require(result['supported'] and result['backend'] == 2, 'unsupported wait diagnostic scope')
    for row in result['workers']:
        for side in ('read', 'write'):
            require(row[side + '_prepare'] == sum(row[side + '_' + kind]
                    for kind in ('first', 'reinsert', 'linked')), 'preparation categories differ')
            if side == 'write' and result['node_wait']:
                require(row['write_first'] <= row['write_begin'], 'writer registrations exceed lifetimes')
            else:
                require(row[side + '_first'] == row[side + '_begin'], 'first registration/lifetime differs')
            require(row[side + '_begin'] == sum(row[side + '_' + kind]
                    for kind in ('return', 'cancel', 'error')), 'wait lifetime did not finish')
    for side in ('read', 'write'):
        require(total[side + '_accept'] <= total[side + '_visits'], 'accepted wakes exceed visits')
        require(total[side + '_reinsert'] <= total[side + '_accept'], 'reinsertion lacks counted removal')
        require(not total[side + '_cancel'] and not total[side + '_error'],
                'ordinary nano wait unexpectedly canceled or failed')
    require(total['read_direct'] + total['read_reserved'] ==
            total['read_return'] + total['read_rollback'], 'reader reservation accounting differs')
    require(total['turn_wake_accept'] <= total['turn_wake_request'], 'direct wakes exceed requests')
    require(total['read_return'] <= completed_reads and total['write_return'] <= completed_writes,
            'slow acquisitions exceed completed workload operations')
