#!/usr/bin/env python3
"""VM-only flat pipe profiles using the ordinary API runner and return probes.

Attach to the idle client before its measured worker threads are created. Perf
inherits those threads. A control FIFO acknowledgement precedes measurement;
symbol resolution finishes before module teardown. All results are unscored.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import time


def save(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


class Profile:
    def __init__(self, session, perf):
        self.session, self.perf = session, perf
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
    parser.add_argument('--source-root', type=Path, default=Path('/root/host_fs/kdlock'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--perf', default='/root/kdlock-evidence/10.176.26.71/bench/mutex-admission-20261013/tools/perf')
    args = parser.parse_args()
    require(os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
            and os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1'
            and os.environ.get('KDLOCK_SNAPSHOT_TAG'), 'use the confirmed recovery VM')
    root, out = args.source_root.resolve(), args.output.resolve()
    require(not out.exists() and not out.is_relative_to(root), 'use a new external output directory')
    path = root / 'bench/real_api/run.py'
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location('mutex_profile_api', path)
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    api.idle()
    out.mkdir(parents=True)
    shutil.copyfile(__file__, out / 'mutex_profile.py')
    original_plan, original_measure = api.make_plan, api.SyscallSession.measure

    def plan(parsed):
        rows = original_plan(parsed)
        for row in rows:
            row.update(diagnostic=True, perf_record=True, pmu=False, score_eligible=False,
                       diagnostic_kind='flat-cycles-k-client-inherited-workers', source_commit=args.commit)
        return rows

    def measure(session):
        profile = Profile(session, args.perf)
        try:
            try:
                profile.start()
            except Exception as error:
                raise api.Failure('PERF_START_FAILED', str(error)) from error
            return original_measure(session)
        finally:
            try:
                profile.finish()
            except Exception as error:
                raise api.Failure('PERF_STOP_OR_CAPTURE_FAILED', str(error), unsafe=True) from error

    api.make_plan, api.SyscallSession.measure = plan, measure
    argv = [str(path), '--output', str(out / 'pipe'), '--kinds', 'pipebytes', '--queries', 'query',
            '--entries', '16', '--value-size', '64', '--backends', 'kdlock', '--threads', '8', '60',
            '--repeats', '1', '--cpus', ','.join(map(str, range(60))), '--collector-cpu', '63',
            '--duration-ms', '2000', '--warmup', '48000', '--warmup-ms', '1000', '--require-jit']
    receipt = dict(argv=argv, source_commit=args.commit, diagnostic=True, score_eligible=False,
                   started_unix=time.time(), passed=False,
                   script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    save(out / 'result.json', receipt)
    sys.argv = argv
    try:
        with (out / 'command.log').open('w') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            rc = api.main()
        receipt['exit_code'] = 0 if rc is None else rc
        records = json.loads((out / 'pipe/records.json').read_text())
        require(receipt['exit_code'] == 0 and len(records) == 2 and all(
                r['execution_status'] == 'OK' and r['drained'] and r['jit_completions'] > 0
                for r in records), 'profile runner failed or sessions did not drain')
        api.idle()
        receipt.update(passed=True, final_idle=True, sessions=2)
    except BaseException as error:
        receipt['error'] = repr(error)
        raise
    finally:
        receipt['finished_unix'] = time.time()
        save(out / 'result.json', receipt)
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
