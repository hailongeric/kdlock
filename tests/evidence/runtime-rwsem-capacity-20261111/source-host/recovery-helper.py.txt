#!/usr/bin/env python3
"""Exact ordinary cleanup of the retained unpublished STAGE4 ENOSPC cycle.

Source-only draft: no STOP, compilation replay, coverage ACK, forced unload or
automatic retry. Execute only in the authorized bounded guest recovery window.
"""
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

WORK = Path('/mnt/kdlock-builds/kdlock-main-work/kernel5-fixtures-e990fde3-rw-01')
SOURCE = WORK / 'input'
ORIGINAL = WORK / 'live-rwsem-01'
CONTROLLER = WORK / 'live-rwsem-receipts-01'
OUTPUT = WORK / 'recovery-rwsem-capacity-01'
BOOT = '6f99fdb9-8d47-46dd-9e72-dfa6ecd774f4'
RELEASE = '7.0.0-38-kdrebuild5'
MODULE = 'kd_rwsem_runtime_fixture'
MODULE_SHA = 'ad0caa3a6de4ea0decc6498bb23a11d408b024cfd41c64e66cae09e5977e19fb'
RESULT_SHA = 'f108689ebdc7eaaac94e49a110f1feabd5ef3467835816505be07d93fa0cec1f'
CONTROLLER_SHA = 'e0c1d9665dab3a562c90112558efa082b33c39cfce0a11788de5a5fa935ace72'
STAGE_SHA = '7b2f9996d028c1ca10a0fec265f18849a5ca7ce3a89c625d35cc46149345e7e6'
SOURCE_SHA = 'e884ebf438beed3f62fb014dab9b0f6e845ce9f015c6096e0b40b4b78de8e08e'
METADATA_SHA = 'ec7e5e539a96fdd2faf364047dbb84590af2f174627628417fa8b051ebaf27f2'
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
            if name.startswith(('kd-fixture/', 'kd-scene/', 'kd-reader/')):
                raw = (path / 'stat').read_text()
                start = raw.rsplit(') ', 1)[1].split()[19]
                rows.append(dict(pid=int(path.name), name=name, start=start, stat=raw))
        except (FileNotFoundError, ProcessLookupError):
            continue
    return rows


def immutable_history(args):
    history = []
    total = 0
    for root in (ORIGINAL, CONTROLLER):
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
    attempt = ORIGINAL / 'wire/attempt-00000005'
    stage_raw = read_file(attempt / 'request.bin', args.max_file_bytes)
    stage_reply = read_file(attempt / 'reply.bin', args.max_file_bytes)
    require(sha(stage_raw) == STAGE_SHA and len(stage_raw) == 643258 and stage_reply == b'',
            'saved failed STAGE request/reply differs')
    last = json.loads(read_file(attempt / 'result.json', args.max_file_bytes))
    require(last['operation'] == 3 and last['sequence'] == last['returned_sequence'] == 4 and
            last['status'] == -28 and last['completed_response'] is True,
            'saved STAGE4 ENOSPC receipt not complete')
    history, history_size = immutable_history(args)
    source_raw = read_file(ORIGINAL / 'source-export.bin', args.max_file_bytes)
    metadata_raw = read_file(ORIGINAL / 'source-metadata.json', args.max_file_bytes)
    require(sha(source_raw) == SOURCE_SHA and sha(metadata_raw) == METADATA_SHA and len(history) == 54,
            'exact saved source/version/54-file history differs')
    metadata = json.loads(metadata_raw)
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
        phase('ALREADY_JOINED_PRECHECK')
        before_tasks = task_rows()
        save(OUTPUT / 'tasks-before.json', before_tasks)
        require(not before_tasks and Path('/sys/module', MODULE).is_dir() and
                Path('/sys/module', MODULE, 'refcnt').read_text().strip() == '2',
                'workers or loaded module retention differs')
        before_dmesg = subprocess.run(['dmesg', '--color=never'], capture_output=True,
                                      check=True, timeout=15).stdout
        saved_bytes(OUTPUT / 'dmesg-before.txt', before_dmesg)
        control = os.open('/dev/' + MODULE + '_ctl', os.O_RDWR | os.O_CLOEXEC)
        before = fixture_status('fixture-before.txt')
        expected = dict(workers='0', finished='0', locks_clear='1', runtime='1',
                        errors='0', core_errors='0', origin_errors='0', overflow='0', events='287')
        require(all(before.get(key) == value for key, value in expected.items()),
                'actual already-joined fixture state differs')
        # Decode only exact saved wire scalars. No image is rebuilt or replayed.
        original_claim_raw = read_file(ORIGINAL / 'wire/attempt-00000003/reply.bin', args.max_file_bytes)
        original_claim = decode(original_claim_raw, Operation.CLAIM, 3, 12, (limits.version_bytes,), limits)
        build_request_raw = read_file(ORIGINAL / 'wire/attempt-00000004/request.bin', args.max_file_bytes)
        build_request = decode(build_request_raw, Operation.BUILD_START, 5, 0, (), limits)
        build_reply_raw = read_file(ORIGINAL / 'wire/attempt-00000004/reply.bin', args.max_file_bytes)
        build_reply = decode(build_reply_raw, Operation.BUILD_START, 12, 0, (limits.symbol_bytes,) * 4, limits)
        stage = decode(stage_raw, Operation.STAGE_LOAD, 1, 0,
                       (limits.artifact_bytes,) * 3 + (128 * 1024, 256 * 1024), limits)
        original_claim_id, original_holder, original_epoch = original_claim.fixed
        candidate = stage.fixed[0]
        require(not original_claim.rows and original_claim_id and original_holder and
                original_epoch == source_epoch and original_claim.blobs[0] == metadata['version'].encode('utf-8') and
                build_request.fixed == (original_claim_id, original_holder, source_epoch, metadata['slot'], 0) and
                build_reply.fixed[0] == candidate and candidate and build_reply.fixed[1] == metadata['slot'] and
                build_reply.fixed[7] == 0 and build_reply.fixed[9] == source_epoch,
                'saved empty-claim/build/stage bindings differ')
        save(OUTPUT / 'saved-control-binding.json', dict(candidate=candidate, claim=original_claim_id,
             holder=original_holder, epoch=source_epoch, stage_sha256=STAGE_SHA,
             build_request_sha256=sha(build_request_raw), build_reply_sha256=sha(build_reply_raw),
             original_claim_sha256=sha(original_claim_raw), stage_blob_bytes=[len(blob) for blob in stage.blobs]))
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
        phase('QUERY_EXACT_STAGE4_ENOSPC')
        cache = transport.query()
        require((cache.operation, cache.sequence, cache.status) == (3, 4, -28) and
                cache.request == stage_raw and cache.response == stage_reply,
                'actual QUERY cache differs from saved STAGE4 ENOSPC')
        save(OUTPUT / 'query-binding.json', dict(operation=cache.operation, sequence=cache.sequence,
             status=cache.status, request_sha256=sha(cache.request), reply_sha256=sha(cache.response)))
        transport.adopt_recovery(cache)
        phase('ACTUAL_STAGE4_ENOSPC_ADOPTED')

        def send(operation, sequence, fixed=(), rows=(), blobs=(), bounds=()):
            payload = encode(operation, fixed, rows, blobs, bounds, limits)
            phase('COMMAND_DISPATCHING', operation=int(operation), sequence=sequence)
            reply = transport.exchange(operation, payload)
            record['exchanges'].append(dict(operation=int(operation), sequence=reply.sequence,
                                            status=reply.status, reply_bytes=len(reply.payload)))
            require(reply.sequence == sequence and reply.status == 0, 'actual recovery command failed')
            phase('COMMAND_RETURNED_ZERO', operation=int(operation), sequence=sequence)
            return reply.payload

        raw = send(Operation.ABORT, 5, (candidate, original_claim_id, original_holder))
        aborted = decode(raw, Operation.ABORT, 3, 0, (), limits)
        require(aborted.fixed == (candidate, original_claim_id, original_holder), 'actual abort differs')
        raw = send(Operation.CLAIM_END, 6, (original_claim_id, original_holder))
        ended = decode(raw, Operation.CLAIM_END, 2, 0, (), limits)
        require(ended.fixed == (original_claim_id, original_holder), 'original empty claim end differs')
        raw = send(Operation.SHUTDOWN, 7)
        shutdown = decode(raw, Operation.SHUTDOWN, 1, 0, (), limits)
        require(shutdown.fixed == (source_epoch,), 'shutdown epoch differs')
        phase('ACTUAL_SOURCE_IMAGE_NATIVE_DRAIN_CONFIRMED')
        holder = 0x9001
        claim_raw = send(Operation.ARCHIVE_CLAIM, 8, (source_epoch, holder, 4096))
        claim = decode(claim_raw, Operation.ARCHIVE_CLAIM, 3, 12, (limits.version_bytes,), limits)
        require(claim.fixed[0] and claim.fixed[1:] == (holder, source_epoch) and
                claim.blobs[0] == metadata['version'].encode('utf-8'), 'actual archive claim binding differs')
        require(not claim.rows, 'unexpected nonempty archive claim; retain actual controls')
        keys = tuple((row[0], row[1]) for row in claim.rows)
        require(all(identity and incarnation for identity, incarnation in keys) and len(keys) == len(set(keys)),
                'archive claim keys are absent or repeated')
        document = dict(format='kdlock.saved-runtime-capacity-recovery-archive.v1',
             original_disposition='failed_or_incomplete', original_error='STAGE_LOAD ENOSPC before publication', source_epoch=source_epoch,
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
        settled_raw = send(Operation.SETTLE, 9, (claim.fixed[0], holder), keys,
                           (bytes.fromhex(actual_digest),), (32,))
        settled = decode(settled_raw, Operation.SETTLE, 3, 2, (), limits)
        require(settled.fixed[0] and settled.fixed[1:] == (claim.fixed[0], holder) and settled.rows == keys,
                'actual settled identities differ from the archived exact claim')
        raw = send(Operation.CLAIM_END, 10, (claim.fixed[0], holder))
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
        post_tasks = task_rows()
        post_devices = sorted(str(path) for path in Path('/dev').glob(MODULE + '*'))
        post_module = Path('/sys/module', MODULE).exists()
        save(OUTPUT / 'poststate.json', dict(boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
             release=os.uname().release, taint=int(Path('/proc/sys/kernel/tainted').read_text()),
             module_present=post_module, devices=post_devices, tasks=post_tasks,
             modules_sha256=sha(modules)))
        require(not post_module and not post_devices and not post_tasks, 'module, devices or workers remain')
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
