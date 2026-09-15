#!/usr/bin/env python3
"""Separate recovery-guest IP sampling, never a benchmark performance arm.

Use kernel samples inherited by the actual client workers. Do not
enable ftrace, function probes or call-chain unwinding through JIT stacks.
Prepare, validate data/JIT and drain using the ordinary benchmark session.
"""
import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import run as bench


class ProfileSession(bench.Session):
    def __init__(self, out, spec, perf, frequency, event):
        super().__init__(out, spec)
        self.perf, self.frequency = perf, frequency
        self.event = event
        self.record.update(diagnostic='kernel-ip-sampling', performance_result=False,
                           sample_event=event, sample_frequency_hz=frequency,
                           callchain=False)

    def phase(self, label, iterations):
        if label != 'measure':
            return super().phase(label, iterations)
        (self.path / 'kallsyms.txt').write_bytes(Path('/proc/kallsyms').read_bytes())
        (self.path / 'modules.txt').write_bytes(Path('/proc/modules').read_bytes())
        args = [str(self.perf), 'record', '-e', self.event, '-F', str(self.frequency),
                '--no-buildid-cache', '-m', '16M', '-o', str(self.path / 'perf.data'), '--',
                str(bench.HERE / 'client'), '--cachelines', str(self.record['cachelines']),
                '--iterations', str(iterations), '--cpus', ','.join(map(str, self.record['cpus']))]
        # Keep perf diagnostics out of the client's machine-readable result.
        # A timeout may leave a worker in ioctl: preserve processes/modules and
        # fail-stop instead of assuming a perf exit means callers have drained.
        with (self.path / 'measure.json').open('w') as output, \
                (self.path / 'perf-record.log').open('w') as log:
            process = subprocess.Popen(args, cwd=bench.ROOT, stdout=output, stderr=log,
                                       start_new_session=True,
                                       env=dict(os.environ, PERF_CONFIG='/dev/null'))
            bench.write_json(self.path / 'measure.json.command.json',
                dict(argv=args, cwd=str(bench.ROOT), pid=process.pid,
                     timeout_seconds=120, started_ns=time.monotonic_ns()))
            try:
                code = process.wait(timeout=120)
            except subprocess.TimeoutExpired as error:
                raise bench.Failure('TIMEOUT', f'perf/client PID {process.pid} did not exit',
                                    unsafe=True) from error
        bench.require(code == 0, f'perf/client exited {code}; see perf-record.log')
        self.faults()
        measurement = json.loads((self.path / 'measure.json').read_text())
        bench.validate_measurement(measurement, self.record, iterations)
        bench.require(self.counts(label)['active'] == 0, 'profile workers not drained', 'UNDRAINED')
        return measurement

    def report(self, kernel_source):
        # Flat worker-only attribution: samples represent executing kernel IPs,
        # not inclusive call costs. Save raw samples for independent reanalysis.
        common = ['-i', self.path / 'perf.data', '--kallsyms', self.path / 'kallsyms.txt']
        self.run([self.perf, 'report', '--stdio', '--no-children', '--show-nr-samples',
                  '--percent-limit', '0', '--comms', 'sc_worker', '--sort', 'dso,symbol',
                  '--vmlinux', kernel_source / 'vmlinux', *common], 'perf-report.txt', timeout=60)
        self.run([self.perf, 'script', '--ns', '-F', 'comm,ip,period', *common],
                 'perf-samples.txt', timeout=60)
        self.run([self.perf, 'report', '--header-only', '--stdio', *common],
                 'perf-header.txt', timeout=30)
        self.run(['nm', '-S', '--defined-only', kernel_source / 'vmlinux'],
                 'kernel-symbol-sizes.txt', timeout=30)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--perf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--arm', choices=('native', 'kdlock'), required=True)
    parser.add_argument('--threads', type=int, choices=(1, 4), default=1)
    parser.add_argument('--cachelines', type=int, choices=(1, 2, 4, 8, 16), default=1)
    parser.add_argument('--iterations', type=int, default=100000000)
    parser.add_argument('--frequency', type=int, default=499)
    parser.add_argument('--event', choices=('cycles:k', 'cpu-clock:k'), default='cycles:k')
    bench.kernel_identity.arguments(parser)
    args = parser.parse_args()
    bench.require(0 < args.iterations <= 100000000, 'invalid iterations')
    bench.require(1 <= args.frequency <= 999, 'use low-frequency sampling (1..999 Hz)')
    bench.require(bench.ROOT == Path('/root/host_fs/kdlock') and os.geteuid() == 0 and
                  os.environ.get('KDLOCK_RECOVERY_CONFIRMED') == '1', 'recovery guest required')
    out = args.output.resolve()
    bench.require(not out.exists() and not out.is_relative_to(bench.ROOT), 'new external output required')
    args.perf = args.perf.resolve()
    bench.require(args.perf.is_file(), 'perf executable missing')
    tracing = Path('/sys/kernel/debug/tracing')
    bench.require((tracing / 'current_tracer').read_text().strip() == 'nop' and
                  (tracing / 'function_profile_enabled').read_text().strip() == '0',
                  'ftrace/function profiling must remain disabled')
    bench.idle()
    out.mkdir()
    bench.require('ext4' in bench.command(['findmnt', '-T', bench.ROOT, '-n', '-o', 'FSTYPE'],
                                         out / 'mount.txt'), 'recovery ext4 required')
    kernel = bench.kernel_identity.capture(args, out, bench.command)
    frozen = bench.source_state()
    bench.write_json(out / 'source-sha256.json', frozen)
    for relative in frozen:
        target = out / 'source' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bench.ROOT / relative, target)
    binaries = {p: bench.digest(bench.ROOT / p) for p in bench.BINARIES}
    bench.write_json(out / 'binary-sha256.json', binaries)
    for relative in binaries:
        target = out / 'binaries' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bench.ROOT / relative, target)
    cpus = list(range(args.threads))
    spec = dict(name='profile', arm=args.arm, cachelines=args.cachelines, threads=args.threads,
                iterations=args.iterations, repeat=0, cpus=cpus)
    topology = bench.capture_topology(cpus)
    bench.annotate_topology([spec], topology)
    bench.write_json(out / 'plan.json', [spec])
    bench.write_json(out / 'environment.json', dict(kernel_identity=kernel, topology=topology,
        virtual_machine=True, host_physical_core_exclusivity=False, argv=list(map(str, os.sys.argv)),
        perf_path=str(args.perf), perf_sha256=bench.digest(args.perf),
        perf_version=bench.command([args.perf, 'version'], out / 'perf-version.txt').strip(),
        snapshot_tag=os.environ.get('KDLOCK_SNAPSHOT_TAG'),
        cmdline=Path('/proc/cmdline').read_text(),
        preemption=Path('/sys/kernel/debug/sched/preempt').read_text()))
    bench.command(['objdump', '-dr', bench.WORKLOAD / 'spin_cacheline.ko'],
                  out / 'payload-disassembly.txt')
    session = ProfileSession(out, spec, args.perf, args.frequency, args.event)
    session.execute()
    bench.capture_completed(bench.AssemblyArchive(out), session.path)
    bench.idle()
    bench.require(frozen == bench.source_state() and
                  binaries == {p: bench.digest(bench.ROOT / p) for p in bench.BINARIES},
                  'profile inputs changed')
    session.report(args.kernel_source)
    from profile_summary import summarize
    summarize(out)
    print(json.dumps(dict(output=str(out), data_ok=True, drained=True,
                          jit_bodies=session.record['jit_bodies'],
                          diagnostic=True, performance_result=False)))


if __name__ == '__main__':
    main()
