#!/usr/bin/env python3
"""Guest-only original strcmp, no-effect preflight refusal and waiter resumption."""
import fcntl
import importlib.util
from pathlib import Path
import re


_shared = Path(__file__).resolve().parent.parent / "address_guard/run.py"
_spec = importlib.util.spec_from_file_location("checked_spin_probe", _shared)
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)

# Reuse source freezing, worker placement, exact-effect checks and retirement.
# Only the payload and the evidence specific to this boundary differ.
probe.DEVICE = "/dev/kd_jit_string_service_test"
probe.WORKER_COMM = "ks_worker"
probe.RUNNER = "tests/kernel/spin/string_service"
probe.PAYLOAD = "workload_modules/jit_string_service"
probe.MODULE = "jit_string_service_test"
probe.CAP_VERSIONS, probe.CAP_BIT, probe.IMAGE_REQUIREMENT = (8, 9), 7, 4
probe.SUCCESS_MESSAGE = (
    "PASS: original strcmp delegated; long valid strings resumed the unexecuted CALL; "
    "exact effects/task/value; permanent native-only state; final drain")


class StringSession(probe.EscapeSession):
    def measure(self):
        self.record["execution_status"] = "MEASURING"
        self.phase("cold-warmup", self.record["warmup_iterations"], 0)
        cold = self.phase("cold-delegated", self.record["iterations"], 0)
        probe.rt.require(cold["jit_delta"]["bench_jit_bodies"] ==
                         cold["jit_delta"]["bench_jit_completions"] > 0,
                         "cold strcmp lacks returned delegated bodies", "NO_JIT")
        self.registry("cold", 0)
        probe.rt.require(self.publication() == self.record["publication"],
                         "cold image changed")
        with open(probe.DEVICE, "rb", buffering=0) as device:
            fcntl.ioctl(device, probe.HOT)
        hot = self.phase("hot-escape", self.record["iterations"], 1)
        delta = hot["jit_delta"]
        probe.rt.require(delta["bench_jit_bodies"] > 0 and
                         delta["bench_jit_completions"] == delta["address_guard_count"] == 0,
                         "preflight refusal did not precede helper completion", "DATA_ERROR")
        self.registry("hot", -3)
        self.faults()
        pattern = re.compile(
            r"reason=STRING_PREFLIGHT_NATIVE\s+entry=(0x[0-9a-f]+)\s+"
            r"ip=(0x[0-9a-f]+)\s+action=native_call_and_disable", re.I)
        events = [dict(entry=int(match[1], 16), helper=int(match[2], 16))
                  for match in pattern.finditer(self.messages)]
        self.record["escape_events"] = events
        self.save()
        probe.rt.require(events and len(events) <= delta["bench_jit_bodies"] and
                         all(event["entry"] == self.record["layout"]["entry"] and
                             event["helper"] == self.record["layout"]["marker"]
                             for event in events),
                         "missing or mismatched preflight refusal", "DATA_ERROR")
        post = self.phase("post-ban", self.record["iterations"], 1)
        probe.rt.require(all(value == 0 for value in post["jit_delta"].values()),
                         "delegation resumed after permanent refusal", "DATA_ERROR")
        self.registry("post-ban", -3)
        self.record.update(jit_status="COLD_JIT_THEN_NATIVE_ONLY", accepted=True,
                           final_parameters=probe.rt.parameters())
        self.verify()


probe.EscapeSession = StringSession

if __name__ == "__main__":
    raise SystemExit(probe.main())
