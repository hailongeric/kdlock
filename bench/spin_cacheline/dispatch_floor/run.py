#!/usr/bin/env python3
"""Measure native/selector/minimal-callback floors; these are not kdlock/JIT arms.

Run only in the recovery guest, after snapshot confirmation, under an external
timeout. Reuse the real payload/client, preparation, counter oracle, fault
detection and fail-stop cleanup. No clocks or observations inside a lock op.
"""
import argparse
import importlib.util
import json
import os
import shutil
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
spec = importlib.util.spec_from_file_location("cacheline_runner", HERE.parent / "run.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
PROVIDER = HERE / "kd_dispatch_floor.ko"


class FloorSession(bench.Session):
    def __init__(self, out, spec):
        super().__init__(out, spec)
        self.loaded_floor = False
        self.record.update(diagnostic="native_dispatch_floor", kdlock_arm=False)

    def prepare(self):
        if self.record["arm"] != "native":
            args = ["insmod", PROVIDER,
                    f"callbacks={int(self.record['arm'] in ('callbacks', 'combined'))}"]
            if self.record['arm'] == 'combined':
                args.append('combined=1')
            self.run(args, "load-floor.log")
            self.loaded_floor = True
        super().prepare()

    def cleanup(self):
        super().cleanup()
        self.record["drained"] = False
        if self.loaded_floor:
            try:
                self.run(["rmmod", "kd_dispatch_floor"], "unload-floor.log")
            except bench.Failure as error:
                raise bench.Failure("UNDRAINED", str(error), unsafe=True) from error
            self.loaded_floor = False
        self.faults()
        self.record["drained"] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=100000)
    parser.add_argument("--repeats", type=int, default=4)
    bench.kernel_identity.arguments(parser)
    args = parser.parse_args()
    bench.require(os.geteuid() == 0 and bench.ROOT == Path("/root/host_fs/kdlock") and
                  os.environ.get("KDLOCK_RECOVERY_CONFIRMED") == "1", "recovery guest required")
    bench.require(args.repeats > 0 and args.repeats % 2 == 0, "positive even repeats required")
    bench.require(0 < args.iterations <= 100000000, "invalid iterations")
    out = args.output.resolve()
    bench.require(not out.exists() and not out.is_relative_to(bench.ROOT), "new external output required")
    bench.idle()
    bench.require(not Path("/sys/module/kd_dispatch_floor").exists(), "existing diagnostic provider")
    out.mkdir(parents=True)
    topology = bench.capture_topology([0])
    kernel = bench.kernel_identity.capture(args, out, bench.command)
    bench.require("ext4" in bench.command(["findmnt", "-T", bench.ROOT, "-n", "-o", "FSTYPE"],
                                         out / "mount.txt"), "recovery ext4 required")
    bench.command(["make", "-C", HERE], out / "build.log", timeout=120)
    # The optional fourth arm measures one unconditional native callback pair,
    # without selection, cache, S, tickets or JIT. Keep legacy controls intact.
    unresolved = bench.command(["nm", "-u", PROVIDER], out / "provider-imports.txt")
    arms = ("native", "selector", "callbacks")
    if 'kd_spin_static_install_dispatch' in unresolved:
        arms += ("combined",)
    bench.write_json(out / "environment.json", dict(topology=topology, kernel_identity=kernel,
        uname=list(os.uname()), cmdline=Path("/proc/cmdline").read_text(),
        preemption=Path("/sys/kernel/debug/sched/preempt").read_text(),
        snapshot_tag=os.environ.get("KDLOCK_SNAPSHOT_TAG"), virtual_machine=True))
    frozen = bench.source_state()
    bench.write_json(out / "source-sha256.json", frozen)
    for relative in frozen:
        target = out / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bench.ROOT / relative, target)
    binaries = [PROVIDER, bench.WORKLOAD / "spin_cacheline.ko", HERE.parent / "client"]
    hashes = {str(p.relative_to(bench.ROOT)): bench.digest(p) for p in binaries}
    bench.write_json(out / "binary-sha256.json", hashes)
    for relative in hashes:
        target = out / "binaries" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bench.ROOT / relative, target)
    plan = []
    for repeat in range(args.repeats):
        for arm in arms if repeat % 2 == 0 else reversed(arms):
            plan.append(dict(name=f"r{repeat:02d}-{arm}", cachelines=1, threads=1,
                iterations=args.iterations, repeat=repeat, arm=arm, cpus=[0], cpu_nodes=[0]))
    bench.write_json(out / "plan.json", plan)
    results = []
    for item in plan:
        bench.idle()
        bench.require(frozen == bench.source_state(), "inputs changed")
        session = FloorSession(out, item)
        session.execute()
        results.append(session.record)
        print(item["name"], session.record["measurement"]["wall_ns"] / args.iterations,
              "ns/op; data correct and drained", flush=True)
    bench.idle()
    bench.require(not Path("/sys/module/kd_dispatch_floor").exists(), "provider not drained")
    bench.require(frozen == bench.source_state() and
                  hashes == {str(p.relative_to(bench.ROOT)): bench.digest(p) for p in binaries},
                  "inputs changed")
    summary = {arm: dict(
        wall_ns_op=statistics.median(r["measurement"]["wall_ns"] / args.iterations
                                    for r in results if r["arm"] == arm),
        cpu_ns_op=statistics.median(r["measurement"]["worker_cpu_ns"] / args.iterations
                                   for r in results if r["arm"] == arm))
               for arm in arms}
    bench.write_json(out / "summary.json", dict(diagnostic=True, samples=len(results), arms=summary))
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
