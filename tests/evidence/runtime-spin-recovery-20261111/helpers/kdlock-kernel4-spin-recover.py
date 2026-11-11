#!/usr/bin/env python3
"""One authorized ordinary recovery, with every actual effect retained."""
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import time

WORK = Path('/mnt/kdlock-builds/kdlock-main-work/kernel4-fixtures-0a07f678-01a1bc4f')
SOURCE = WORK / 'input'
ORIGINAL = WORK / 'live-spin-output'
CONTROLLER = WORK / 'live-spin-controller'
DIAGNOSTICS = WORK / 'live-spin-readonly-diag-1'
OUTPUT = WORK / 'recovery-spin-approved-01'
BOOT = '84e4ba94-b616-4b65-9efe-820921f36c16'
RELEASE = '7.0.0-38-kdrebuild4'
MODULE = 'kd_spin_runtime_fixture'
MODULE_SHA = '180d36459307576ff3c54b874186a058da710acf9c8c76ba28e5929efffe8b47'
RESULT_SHA = '9c89f7eade4ddb8b65d07403d10ab63856c396bbbeb43bfdc7e0fa239d2fd97b'
CONTROLLER_SHA = 'dbf5a4407d65bc75a78c46110e52f346f738873e8fbf42ef26900184ed5d7703'
END_SHA = '2b49346f611c6ba6802ffd5cc3bb7f0e704ed54ca09bca671c95f74ff9667296'
END_FRAME = bytes.fromhex('0100000000000000060000000000000030000000000000000000000000000000c88a6c0d010011ff0410000000000000')
FACT_FIELDS = ('identity', 'incarnation', 'producer_identity', 'image_identity', 'kind',
               'detail', 'source_ip', 'target', 'cursor', 'phase', 'classification', 'entry_result_word')


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    sync_directory(path.parent)


def saved_bytes(path, data):
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    sync_directory(path.parent)


def read_file(path, maximum):
    require(path.resolve(strict=True) == path, 'noncanonical input: ' + str(path))
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_size <= maximum, 'input type/size: ' + str(path))
    with path.open('rb') as stream:
        value = stream.read(maximum + 1)
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) and
            len(value) == before.st_size, 'input changed: ' + str(path))
    return value


def task_rows():
    rows = []
    for path in Path('/proc').iterdir():
        if not path.name.isdecimal():
            continue
        try:
            name = (path / 'comm').read_text().strip()
            if name.startswith(('kd-fixture/', 'kd-scene/')):
                raw = (path / 'stat').read_text()
                start = raw.rsplit(') ', 1)[1].split()[19]
                rows.append(dict(pid=int(path.name), name=name, start=start, stat=raw))
        except (FileNotFoundError, ProcessLookupError):
            continue
    return rows


def immutable_history(args):
    history = []
    total = 0
    for root in (ORIGINAL, CONTROLLER, DIAGNOSTICS):
        require(root.resolve(strict=True) == root, 'noncanonical history root')
        for path in sorted(root.rglob('*')):
            require(not path.is_symlink(), 'history contains a symlink')
            if path.is_dir():
                continue
            value = read_file(path, args.max_file_bytes)
            total += len(value)
            require(total <= args.max_history_bytes, 'history exceeds explicit total byte limit')
            history.append(dict(origin=str(path), bytes=len(value), sha256=sha(value), bytes_hex=value.hex()))
    return history, total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-file-bytes', type=int, required=True)
    parser.add_argument('--max-history-bytes', type=int, required=True)
    parser.add_argument('--max-archive-bytes', type=int, required=True)
    args = parser.parse_args()
    require(all(value > 0 for value in vars(args).values()), 'explicit positive byte bounds required')
    require(os.geteuid() == 0 and os.uname().release == RELEASE and
            Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT and
            Path('/proc/sys/kernel/tainted').read_text().strip() == '12288', 'actual failed boot differs')
    require(not OUTPUT.exists(), 'fresh recovery directory required')
    failed_raw = read_file(ORIGINAL / 'result.json', args.max_file_bytes)
    control_raw = read_file(CONTROLLER / 'result.json', args.max_file_bytes)
    require(sha(failed_raw) == RESULT_SHA and sha(control_raw) == CONTROLLER_SHA, 'failed result pins differ')
    failed, controller = json.loads(failed_raw), json.loads(control_raw)
    require(failed['status'] == 'failed_or_incomplete' and failed['module_sha256'] == MODULE_SHA and
            controller['returncode'] == 1 and controller['status'] == 'FAILED_OR_INCOMPLETE',
            'exact failed-run disposition differs')
    attempt = ORIGINAL / 'wire/attempt-00000022'
    require(read_file(attempt / 'request.bin', args.max_file_bytes) == END_FRAME and
            read_file(attempt / 'reply.bin', args.max_file_bytes) == END_FRAME and
            sha(END_FRAME) == END_SHA, 'saved cached END21 differs')
    last = json.loads(read_file(attempt / 'result.json', args.max_file_bytes))
    require(last['operation'] == 6 and last['sequence'] == last['returned_sequence'] == 21 and
            last['status'] == 0 and last['completed_response'] is True, 'saved END21 receipt not complete')
    history, history_size = immutable_history(args)
    source_raw = read_file(ORIGINAL / 'source-export.bin', args.max_file_bytes)
    metadata = json.loads(read_file(ORIGINAL / 'source-metadata.json', args.max_file_bytes))
    require(len(source_raw) >= 88, 'source export truncated')
    source_epoch = struct.unpack_from('<Q', source_raw, 32)[0]
    require(source_epoch != 0, 'source epoch is absent')
    OUTPUT.mkdir(mode=0o700)
    sync_directory(OUTPUT.parent)
    record = dict(phase='PREPARED', started_unix=time.time(), original_result_sha256=RESULT_SHA,
                  original_controller_sha256=CONTROLLER_SHA, source_epoch=source_epoch,
                  original_history_bytes=history_size, exchanges=[])
    journal = (OUTPUT / 'journal.jsonl').open('x')
    transport = None
    control = -1

    def phase(name, **fields):
        record.update(phase=name, **fields)
        journal.write(json.dumps(dict(phase=name, unix=time.time(), **fields), sort_keys=True) + '\n')
        journal.flush()
        os.fsync(journal.fileno())
        print(json.dumps(dict(phase=name, **fields), sort_keys=True), flush=True)

    def fixture_status(label):
        os.lseek(control, 0, os.SEEK_SET)
        raw = os.read(control, 16384)
        saved_bytes(OUTPUT / label, raw)
        return dict(part.split('=', 1) for part in raw.decode('ascii').split())

    try:
        # Imports use the retained exact VM source. No decoder, compiler,
        # assembler, source execution, producer catalog or ACK is constructed.
        sys.path.insert(0, str(SOURCE))
        from disassem.session import FdTransport
        from disassem.wire import Operation, WireLimits, decode, encode
        limits = WireLimits(2 * 1024 * 1024, 4096, 256, 256, 512 * 1024)
        phase('ORDINARY_STOP_PRECHECK')
        before_tasks = task_rows()
        require(len(before_tasks) == 5, 'exact five parked workers are absent')
        save(OUTPUT / 'tasks-before-stop.json', before_tasks)
        before_dmesg = subprocess.run(['dmesg', '--color=never'], capture_output=True, check=True, timeout=15).stdout
        saved_bytes(OUTPUT / 'dmesg-before.txt', before_dmesg)
        control = os.open('/dev/' + MODULE + '_ctl', os.O_RDWR | os.O_CLOEXEC)
        before = fixture_status('fixture-before-stop.txt')
        expected = dict(mode='1', workers='5', finished='5', iterations='1', completed='5', calls='3',
                        a='2', b='1', errors='1', core_errors='0', origin_errors='0', pin_errors='0',
                        locks_clear='1', runtime='1', child='0', overflow='0')
        require(all(before.get(key) == value for key, value in expected.items()), 'actual failed scene changed')
        phase('ORDINARY_STOP_DISPATCHING')
        stop = dict(command='stop', dispatches=1)
        try:
            stop['write_bytes'] = os.write(control, b'stop\n')
            require(stop['write_bytes'] == 5, 'ordinary stop did not consume command')
            stop['errno'] = 0
        except OSError as error:
            stop.update(errno=error.errno, error=str(error))
        save(OUTPUT / 'ordinary-stop-result.json', stop)
        after = fixture_status('fixture-after-stop.txt')
        after_tasks = task_rows()
        save(OUTPUT / 'tasks-after-stop.json', after_tasks)
        require(after.get('workers') == '0' and after.get('locks_clear') == '1' and
                after.get('runtime') == '1' and not after_tasks and stop['errno'] in (0, errno.ETIMEDOUT),
                'stop did not establish exact joined/inactive state')
        for row in before_tasks:
            path = Path('/proc') / str(row['pid']) / 'stat'
            if path.exists():
                raw = path.read_text()
                require(raw.rsplit(') ', 1)[1].split()[19] != row['start'], 'an old worker remains')
        phase('ORDINARY_STOP_JOINED', stop_errno=stop['errno'], workers=0)
        transport = FdTransport.open('/dev/' + MODULE, limits, 4 * 1024 * 1024 + 48)
        ioctl = transport._ioctl

        def capture(flight):
            directory = OUTPUT / ('wire-' + str(flight.sequence).zfill(2))
            directory.mkdir()
            saved_bytes(directory / 'request.bin', flight.request)
            save(directory / 'request.json', dict(operation=int(flight.operation), sequence=flight.sequence))
            try:
                reply = ioctl(flight)
            except BaseException:
                saved_bytes(directory / 'uncertain-envelope.bin', bytes(flight.header))
                raise
            saved_bytes(directory / 'returned-envelope.bin', bytes(flight.header))
            saved_bytes(directory / 'reply.bin', reply.payload)
            save(directory / 'result.json', dict(operation=int(flight.operation), sequence=reply.sequence,
                 status=reply.status, reply_bytes=len(reply.payload)))
            return reply
        transport._ioctl = capture
        phase('QUERY_EXACT_END21')
        cache = transport.query()
        require((cache.operation, cache.sequence, cache.status) == (6, 21, 0) and
                cache.request == cache.response == END_FRAME, 'actual QUERY cache differs from saved END21')
        save(OUTPUT / 'query-binding.json', dict(operation=cache.operation, sequence=cache.sequence,
             status=cache.status, request_sha256=sha(cache.request), reply_sha256=sha(cache.response)))
        transport.adopt_recovery(cache)
        phase('ACTUAL_END21_ADOPTED')

        def send(operation, sequence, fixed=(), rows=(), blobs=(), bounds=()):
            payload = encode(operation, fixed, rows, blobs, bounds, limits)
            phase('COMMAND_DISPATCHING', operation=int(operation), sequence=sequence)
            reply = transport.exchange(operation, payload)
            record['exchanges'].append(dict(operation=int(operation), sequence=reply.sequence,
                                            status=reply.status, reply_bytes=len(reply.payload)))
            require(reply.sequence == sequence and reply.status == 0, 'actual recovery command failed')
            phase('COMMAND_RETURNED_ZERO', operation=int(operation), sequence=sequence)
            return reply.payload

        raw = send(Operation.SHUTDOWN, 22)
        shutdown = decode(raw, Operation.SHUTDOWN, 1, 0, (), limits)
        require(shutdown.fixed == (source_epoch,), 'shutdown epoch differs')
        phase('ACTUAL_SOURCE_IMAGE_NATIVE_DRAIN_CONFIRMED')
        holder = 0x9001
        claim_raw = send(Operation.ARCHIVE_CLAIM, 23, (source_epoch, holder, 4096))
        claim = decode(claim_raw, Operation.ARCHIVE_CLAIM, 3, 12, (limits.version_bytes,), limits)
        require(claim.fixed[0] and claim.fixed[1:] == (holder, source_epoch) and
                claim.blobs[0] == metadata['version'].encode('utf-8'), 'actual archive claim binding differs')
        keys = tuple((row[0], row[1]) for row in claim.rows)
        require(all(identity and incarnation for identity, incarnation in keys) and len(keys) == len(set(keys)),
                'archive claim keys are absent or repeated')
        document = dict(format='kdlock.saved-runtime-recovery-archive.v1',
             original_disposition='failed_or_incomplete', source_epoch=source_epoch,
             claim=dict(identity=claim.fixed[0], holder=holder, keys=[list(key) for key in keys]),
             raw_claim=dict(bytes_hex=claim_raw.hex(), bytes=len(claim_raw), sha256=sha(claim_raw)),
             facts=[dict(zip(FACT_FIELDS, row)) for row in claim.rows],
             source_export=dict(bytes_hex=source_raw.hex(), bytes=len(source_raw), sha256=sha(source_raw)),
             source_metadata=metadata, original_history=history,
             shutdown_reply=dict(bytes_hex=raw.hex(), sha256=sha(raw)),
             scope='Exact copied source, producer BUILD/STAGE/wire history and pending facts. No producer objects, retranslation or coverage ACK is fabricated.')
        phase('EXACT_RAW_ARCHIVE_WRITING', claim_rows=len(keys))
        archive = OUTPUT / 'shutdown-raw-archive.json'
        encoder = json.JSONEncoder(ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(',', ':'))
        digest = hashlib.sha256()
        length = 0
        with archive.open('xb') as output:
            os.fchmod(output.fileno(), 0o600)
            for chunk in encoder.iterencode(document):
                data = chunk.encode('utf-8')
                require(len(data) <= args.max_archive_bytes - length, 'actual archive exceeds explicit byte bound')
                output.write(data)
                digest.update(data)
                length += len(data)
            output.flush()
            os.fsync(output.fileno())
        sync_directory(OUTPUT)
        actual_digest = sha(read_file(archive, args.max_archive_bytes))
        require(actual_digest == digest.hexdigest(), 'independently reread archive hash differs')
        archive_receipt = dict(path=str(archive), bytes=length, sha256=actual_digest,
                               claim=claim.fixed[0], holder=holder, keys=[list(key) for key in keys])
        save(OUTPUT / 'durable-archive-receipt.json', archive_receipt)
        phase('EXACT_RAW_ARCHIVE_FSYNCED', archive=archive_receipt)
        settled_raw = send(Operation.SETTLE, 24, (claim.fixed[0], holder), keys,
                           (bytes.fromhex(actual_digest),), (32,))
        settled = decode(settled_raw, Operation.SETTLE, 3, 2, (), limits)
        require(settled.fixed[0] and settled.fixed[1:] == (claim.fixed[0], holder) and settled.rows == keys,
                'actual settled identities differ from the archived exact claim')
        raw = send(Operation.CLAIM_END, 25, (claim.fixed[0], holder))
        ended = decode(raw, Operation.CLAIM_END, 2, 0, (), limits)
        require(ended.fixed == (claim.fixed[0], holder), 'actual claim end differs')
        transport.close()
        transport = None
        phase('EXACT_ARCHIVE_SETTLEMENT_END_AND_CHANNEL_CLOSE_COMPLETE', settled_rows=len(keys))
        current = fixture_status('fixture-before-destroy.txt')
        require(current.get('workers') == '0' and current.get('locks_clear') == '1', 'fixture is active before destroy')
        phase('ORDINARY_DESTROY_DISPATCHING')
        require(os.write(control, b'destroy\n') == 8, 'ordinary destroy did not consume command')
        current = fixture_status('fixture-after-destroy.txt')
        require(current.get('workers') == '0' and current.get('locks_clear') == '1' and current.get('runtime') == '0',
                'ordinary destroy did not finish')
        os.close(control)
        control = -1
        phase('ORDINARY_RMMOD_DISPATCHING')
        result = subprocess.run(['/usr/sbin/rmmod', MODULE], capture_output=True, timeout=20)
        saved_bytes(OUTPUT / 'rmmod.stdout', result.stdout)
        saved_bytes(OUTPUT / 'rmmod.stderr', result.stderr)
        save(OUTPUT / 'rmmod-result.json', dict(argv=['/usr/sbin/rmmod', MODULE], returncode=result.returncode))
        require(result.returncode == 0, 'ordinary rmmod failed')
        modules = Path('/proc/modules').read_bytes()
        saved_bytes(OUTPUT / 'modules-after.txt', modules)
        require(not Path('/sys/module', MODULE).exists() and
                not list(Path('/dev').glob(MODULE + '*')) and not task_rows(), 'module, devices or workers remain')
        after_dmesg = subprocess.run(['dmesg', '--color=never'], capture_output=True, check=True, timeout=15).stdout
        saved_bytes(OUTPUT / 'dmesg-after.txt', after_dmesg)
        require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT and
                Path('/proc/sys/kernel/tainted').read_text().strip() == '12288', 'boot or taint changed during recovery')
        record.update(status='EXACT_ORDINARY_RECOVERY_COMPLETE', archive=archive_receipt,
                      settled_rows=len(keys), new_dmesg_bytes=len(after_dmesg) - len(before_dmesg),
                      dmesg_unchanged=after_dmesg == before_dmesg)
        phase('ORDINARY_UNLOAD_VERIFIED')
    except BaseException as error:
        record.update(status='FAILED_RETAIN_STATE', error_type=type(error).__name__, error=str(error),
                      pending_sequence=transport.pending_sequence if transport is not None else None)
        phase('FAILED_RETAIN_STATE')
        raise
    finally:
        # Closing process fds performs no guessed protocol cleanup. The core
        # keeps its actual session/module retention if a command is incomplete.
        if transport is not None:
            os.close(transport.fd)
        if control >= 0:
            os.close(control)
        record['finished_unix'] = time.time()
        save(OUTPUT / 'result.json', record)
        journal.close()
        print(json.dumps(record, indent=2, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
