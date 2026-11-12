"""Versioned rwlock workload ABI; importing this module performs no I/O."""
import errno
import fcntl
import struct

DEVICE = '/dev/kd_rwlock_bench'
CONFIG = 0x40184201
RUN = 0xC0684202
SNAPSHOT = 0x80B84203
PROGRESS = 0x82284204
PREPARE = 0x4205
DRAIN = 0x4206
RUN_FORMAT = '=3Q2I8Q2I'


def snapshot():
    buffer = bytearray(184)
    with open(DEVICE, 'rb', buffering=0) as device:
        fcntl.ioctl(device, SNAPSHOT, buffer, True)
    row = struct.unpack('=19Q8I', buffer)
    names = ('lock_addr', 'gate_addr', 'entry', 'version', 'backend', 'workload',
             'lines', 'post_work_rounds', 'cnts', 'gate', 'active')
    return dict(values=list(row[:16]), **dict(zip(names, row[16:])))


def configure(device, start, deadline, workers, percent):
    fcntl.ioctl(device, CONFIG, struct.pack('=2Q2I', start, deadline, workers, percent))


def progress(device, start, deadline, workers):
    buffer = bytearray(552)
    fcntl.ioctl(device, PROGRESS, buffer, True)
    row = struct.unpack('=4Q2I64Q', buffer)
    if (row[0], row[1], row[4], row[5]) != (start, deadline, workers, 0):
        raise ValueError('progress configuration changed')
    return dict(started_ns=row[2], finished_ns=row[3], completed=list(row[6:6 + workers]))


EVIDENCE = 0x4207
BIND = 0x40104208
DESTROY = 0x4209
RECORDING = 0xC010420A
COUNTS = ('reserved', 'freed', 'prepared', 'proxy', 'entered', 'completed',
          'forwarded', 'errors', 'live', 'attached', 'detached', 'state',
          'origin', 'proof', 'read_acquired', 'read_released')
EVENT_FIELDS = ('kind', 'task', 'state', 'origin', 'node', 'acquisition', 'parent',
                'owner', 'owner_task', 'object', 'image', 'ip', 'cursor', 'related',
                'phase', 'result', 'flags', 'source_user', 'return_user', 'notifier')


def evidence():
    buffer = bytearray(16 + 64 * (16 + 6 * 20) * 8)
    with open(DEVICE, 'rb', buffering=0) as device:
        try:
            fcntl.ioctl(device, EVIDENCE, buffer, True)
        except OSError as error:
            if error.errno != errno.EOPNOTSUPP:
                raise
            return dict(available=False, workers=None, reason='phase recorder disabled')
    version, workers = struct.unpack_from('=2Q', buffer)
    if version != 1 or not 1 <= workers <= 64:
        raise ValueError('evidence ABI or worker count differs')
    rows = []
    for index in range(workers):
        offset = 16 + index * 136 * 8
        row = dict(zip(COUNTS, struct.unpack_from('=16Q', buffer, offset)))
        row['records'] = [dict(zip(EVENT_FIELDS, struct.unpack_from('=20Q', buffer,
                           offset + 128 + record * 160))) for record in range(6)]
        rows.append(row)
    return dict(version=version, available=True, workers=rows)


def set_recording(enabled):
    buffer = bytearray(struct.pack('=2Q', int(enabled), 0))
    with open(DEVICE, 'rb', buffering=0) as device:
        fcntl.ioctl(device, RECORDING, buffer, True)
    active, trace_enabled = struct.unpack('=2Q', buffer)
    if active != int(enabled) or trace_enabled != int(enabled):
        raise ValueError('recorder state differs or another observation listener remains')
    return dict(enabled=bool(active), trace_enabled=bool(trace_enabled))
