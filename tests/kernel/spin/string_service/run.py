#!/usr/bin/env python3
"""Guest-only audited original strcmp with short and long valid strings."""
import fcntl
import importlib.util
from pathlib import Path


_shared = Path(__file__).resolve().parent.parent / "address_guard/run.py"
_spec = importlib.util.spec_from_file_location("checked_spin_probe", _shared)
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)

# Reuse source freezing, worker placement, exact-effect checks and retirement.
# Only the payload and the evidence specific to this boundary differ.
probe.DEVICE = "/dev/kd_jit_string_service_test"
probe.WORKER_COMM = "ks_worker"
probe.RUNNER = "tests/kernel/spin/string_service"
probe.PAYLOAD = "tests/kernel/spin/string_service/fixture"
probe.MODULE = "jit_string_service_test"
probe.CAP_VERSIONS, probe.CAP_BIT, probe.IMAGE_REQUIREMENT = (11, 12), 10, 4 | 16
probe.SUCCESS_MESSAGE = (
    "PASS: original strcmp delegated with short and long valid strings; "
    "exact effects/task/value; unchanged image; final drain")


class StringSession(probe.EscapeSession):
    def measure(self):
        self.record["execution_status"] = "MEASURING"
        self.phase("cold-warmup", self.record["warmup_iterations"], 0)
        cold = self.phase("cold-delegated", self.record["iterations"], 0)
        probe.rt.require(cold["jit_delta"]["bench_jit_bodies"] ==
                         cold["jit_delta"]["bench_jit_completions"] > 0,
                         "cold strcmp lacks returned delegated bodies", "NO_JIT")
        probe.rt.require(self.registry("cold", 0) == self.record["image_registry"],
                         "cold immutable image identity changed", "DATA_ERROR")
        probe.rt.require(self.publication() == self.record["publication"],
                         "cold image changed")
        with open(probe.DEVICE, "rb", buffering=0) as device:
            fcntl.ioctl(device, probe.HOT)
        hot = self.phase("long-delegated", self.record["iterations"], 1)
        delta = hot["jit_delta"]
        probe.rt.require(delta["bench_jit_bodies"] == delta["bench_jit_completions"] > 0 and
                         delta["address_guard_count"] == 0,
                         "valid long strings did not complete delegated strcmp", "DATA_ERROR")
        probe.rt.require(self.registry("long", 0) == self.record["image_registry"],
                         "long-string immutable image identity changed", "DATA_ERROR")
        self.faults()
        probe.rt.require("reason=STRING_PREFLIGHT_NATIVE" not in self.messages and
                         self.publication() == self.record["publication"],
                         "audited strings refused or changed the published image", "DATA_ERROR")
        post = self.phase("long-repeat", self.record["iterations"], 1)
        delta = post["jit_delta"]
        probe.rt.require(delta["bench_jit_bodies"] == delta["bench_jit_completions"] > 0 and
                         delta["address_guard_count"] == 0,
                         "repeated long strings lost complete delegation", "DATA_ERROR")
        probe.rt.require(self.registry("long-repeat", 0) == self.record["image_registry"],
                         "repeated long-string immutable image identity changed", "DATA_ERROR")
        probe.rt.require(self.publication() == self.record["publication"],
                         "long-string image changed")
        self.record.update(jit_status="SHORT_AND_LONG_COMPLETE", escape_events=[], accepted=True,
                           final_parameters=probe.rt.parameters())
        self.verify()


probe.EscapeSession = StringSession

if __name__ == "__main__":
    raise SystemExit(probe.main())
