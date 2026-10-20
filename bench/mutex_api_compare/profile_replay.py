#!/usr/bin/env python3
"""Profile original frozen mutex inputs with all checks and matched controls.

Execute a byte-matched external copy so retained-collector import verification
continues to reject every unrelated current-checkout module. This driver adds
only explicit diagnostic plan flags and a perf wrapper around API measurement;
the collector still owns every oracle, admission decision and drain operation.
Flat API recording follows the reviewed cacheline profile's FIFO ACK protocol.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import shutil
import subprocess
import sys
import time

ROOT = Path('/root/host_fs/kdlock')
PERF = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex-admission-20261013/tools/perf')


def save(path, data):
    with path.open('w') as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write('\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def profile_order(order):
    """The first complete rotated round at each point, before seeing outcomes."""
    return [row for row in order if row[2] == 0]


def profile_spec(spec, perf_hash):
    return dict(spec, diagnostic=True, perf_record=True, pmu=False,
                score_eligible=False, perf_binary_sha256=perf_hash,
                diagnostic_kind='flat-cycles-k-199hz-original-inputs')


class Profile:
    def __init__(self, session, perf, *, clock_id=None):
        self.session, self.perf = session, perf
        require(clock_id in (None, 'mono'), 'only the original or monotonic perf clock is supported')
        self.clock_id = clock_id
        self.process = self.log = None
        self.control = self.ack = None
        self.ack_data = b''

    def command(self, text):
        os.write(self.control, (text + '\n').encode())
        deadline = time.monotonic() + 10
        while b'\n' not in self.ack_data:
            left = deadline - time.monotonic()
            require(left > 0, 'perf control acknowledgement timed out')
            if select.select([self.ack], [], [], min(left, .1))[0]:
                self.ack_data += os.read(self.ack, 1024)
            elif self.process.poll() is not None:
                raise RuntimeError('perf exited before control acknowledgement')
        data, self.ack_data = self.ack_data.split(b'\n', 1)
        # v6.1 includes the C string's trailing NUL in each acknowledgement.
        require(data.strip(b'\0') == b'ack', 'unexpected perf acknowledgement: ' + repr(data))
        self.ack_data = self.ack_data.lstrip(b'\0')
        self.session.record.setdefault('perf_control_acks', []).append(text)
        self.session.save()

    def start(self):
        session = self.session
        for name in ('kallsyms', 'modules'):
            (session.path / name).write_bytes(Path('/proc', name).read_bytes())
        for name in ('perf-control', 'perf-ack'):
            os.mkfifo(session.path / name)
        self.control = os.open(session.path / 'perf-control', os.O_RDWR | os.O_NONBLOCK)
        self.ack = os.open(session.path / 'perf-ack', os.O_RDWR | os.O_NONBLOCK)
        argv = ['taskset', '-c', str(session.record['collector_cpu']),
                self.perf, 'record', '--quiet', '--sample-cpu', '-e', 'cycles:k',
                '-F', '199', '--inherit', '--pid', str(session.client.pid), '--delay=-1',
                '--control=fifo:' + str(session.path / 'perf-control') + ',' + str(session.path / 'perf-ack'),
                '-o', str(session.path / 'perf.data')]
        if self.clock_id is not None:
            argv.extend(['--clockid', self.clock_id])
            session.record['perf_clock_id'] = self.clock_id
        session.record['perf_command'] = argv
        session.record['perf_binary_sha256'] = hashlib.sha256(Path(self.perf).read_bytes()).hexdigest()
        session.save()
        self.log = (session.path / 'perf-record.log').open('wb')
        self.process = subprocess.Popen(argv, stdout=self.log, stderr=subprocess.STDOUT)
        session.record['perf_pid'] = self.process.pid
        session.save()
        self.command('enable')

    def finish(self):
        error = None
        try:
            if self.process is not None:
                if self.process.poll() is None:
                    try:
                        self.command('disable')
                    except Exception as failure:
                        error = failure
                    self.command('stop')
                rc = self.process.wait(timeout=15)
                self.session.record['perf_exit_code'] = rc
                self.session.save()
                require(rc == 0, 'perf record exited ' + str(rc))
            if error:
                raise error
        finally:
            if self.log is not None:
                self.log.close()
            for descriptor in (self.control, self.ack):
                if descriptor is not None:
                    os.close(descriptor)
            # FIFO contents are control transport, not evidence. Remove only
            # the two FIFOs this instance created, after stopping its recorder.
            if self.process is None or self.process.poll() is not None:
                for name in ('perf-control', 'perf-ack'):
                    path = self.session.path / name
                    if path.exists():
                        path.unlink()
        if self.process is None:
            return
        for arguments, output in (
                (['report', '--stdio', '--no-children', '--sort', 'comm,dso,symbol', '--percent-limit', '0.2'], 'perf-report.txt'),
                (['script', '--show-lost-events', '-F', 'comm,pid,tid,cpu,time,event,ip,sym,dso,period'], 'perf-samples.txt')):
            self.session.run([self.perf, *arguments, '--kallsyms', self.session.path / 'kallsyms',
                              '-i', self.session.path / 'perf.data'], output, timeout=60)
        samples = (self.session.path / 'perf-samples.txt').read_text()
        require(any(line.lstrip().startswith('sc_worker ') for line in samples.splitlines()),
                'profile has no measured worker samples')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--host-state', type=Path, required=True)
    parser.add_argument('--source-commit', required=True)
    args = parser.parse_args()
    require(ROOT.is_dir() and os.geteuid() == 0 and
            os.uname().release == '6.1.159-kdclobber2' and
            os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1' and
            os.environ.get('KDLOCK_SNAPSHOT_TAG'), 'confirmed original recovery VM required')
    require(not Path(__file__).resolve().is_relative_to(ROOT) and
            sha(Path(__file__)) == sha(ROOT/'bench/mutex_api_compare/profile_replay.py'),
            'execute a byte-matched external driver; retain current-collector refusal')
    require(sys.executable == '/root/kdlock-translation-venv-20261019/bin/python3'
            and shutil.which('python3') == sys.executable, 'original translation Python required')
    require(re.fullmatch(r'[0-9a-f]{40}', args.source_commit) is not None,
            'record a concrete diagnostic-driver source commit')
    sys.dont_write_bytecode = True
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    scheduler = ROOT/'bench/mutex_api_compare/run.py'
    module = importlib.util.spec_from_file_location('diagnostic_scheduler', scheduler)
    replay = importlib.util.module_from_spec(module)
    module.loader.exec_module(replay)
    prepared, out = args.prepared.resolve(strict=True), args.output.resolve()
    require(not out.exists() and not out.is_relative_to(ROOT), 'new external output required')
    replay.replay_inputs(prepared, out)
    original_status = replay.load(prepared/'matrix/status.json')
    require(original_status['state'] == 'COMPLETE' and original_status['completed'] == 1764,
            'the completed original 1764-session comparison is required')
    harness = replay.retained_harness(prepared)
    syn, syn_session, bench_session, api = replay.runners(prepared/'harness', harness)
    syn.idle()
    out.mkdir()
    shutil.copyfile(__file__, out/'profile_replay.py')
    shutil.copyfile(scheduler, out/'scheduler.py')
    perf = out/'tools/perf'
    perf.parent.mkdir()
    perf_hash = sha(PERF)
    shutil.copyfile(PERF, perf)
    perf.chmod(0o755)
    require(sha(perf) == sha(PERF) == perf_hash, 'perf changed during retention')
    old_path = os.environ['PATH']
    os.environ['PATH'] = str(perf.parent)+os.pathsep+old_path
    require(Path(shutil.which('perf')) == perf, 'retained perf was not selected')
    original_order, original_spec = replay.replay_order, replay.specification
    ordinary_session = api.SyscallSession
    order = profile_order(original_order())
    require(len(order) == len(set(order)) == 40, 'expected 10 complete four-arm diagnostic points')
    receipt = dict(passed=False, state='STARTING', diagnostic=True, score_eligible=False,
        source_commit=args.source_commit, script_sha256=sha(Path(__file__)),
        scheduler_sha256=sha(scheduler), perf_source=str(PERF), perf_sha256=perf_hash,
        measured_collection='d21a1e3', prepared=str(prepared), order=order,
        started_unix=time.time(), planned=40, modules_or_binaries_changed=False,
        limits='One diagnostic repeat, not throughput acceptance or p95 latency. '
               'Perf samples differ from plain and host-observed collections.')
    save(out/'result.json', receipt)
    save(out/'tool-sha256.json', {'tools/perf': perf_hash})

    class ProfiledSession(ordinary_session):
        def measure(self):
            profile = Profile(self, str(perf))
            try:
                try:
                    profile.start()
                except Exception as error:
                    raise api.Failure('PERF_START_FAILED', str(error)) from error
                return super().measure()
            finally:
                try:
                    profile.finish()
                except Exception as error:
                    raise api.Failure('PERF_STOP_OR_CAPTURE_FAILED', str(error), unsafe=True) from error

    # The reviewed driver is an explicit instrumentation layer. No collector
    # predicates, required publication, worker checks or retirement are changed.
    replay.replay_order = lambda: order
    replay.specification = lambda *a, **k: profile_spec(original_spec(*a, **k), perf_hash)
    api.SyscallSession = ProfiledSession
    try:
        receipt['state'] = 'RUNNING'
        save(out/'result.json', receipt)
        result = replay.measure(prepared, out/'matrix', syn, syn_session, bench_session,
            api, 2400, False, args.host_state, replay=True)
        records = replay.load(out/'matrix/records.json')
        require(result == 0 and len(records) == 40 and all(
            r['drained'] and r['execution_status'] in ('OK', 'NO_JIT') and
            r['diagnostic'] and r['perf_record'] and not r['score_eligible'] for r in records),
            'diagnostic sessions failed or did not drain')
        for row in records:
            folder = Path(row['evidence_path'])
            require((folder/'perf.data').stat().st_size > 0 and
                    (folder/'perf-samples.txt').stat().st_size > 0,
                    'missing perf evidence: '+row['name'])
        syn.idle()
        receipt.update(passed=True, state='COMPLETE', final_idle=True, sessions=40)
    except BaseException as error:
        receipt.update(state='FAILED', error=repr(error))
        raise
    finally:
        receipt['finished_unix'] = time.time()
        save(out/'result.json', receipt)
        replay.replay_order, replay.specification = original_order, original_spec
        api.SyscallSession = ordinary_session
        os.environ['PATH'] = old_path
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
