"""Versioned rwlock workload ABI; importing this module performs no I/O."""
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
