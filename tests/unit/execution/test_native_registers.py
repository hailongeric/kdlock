"""Guest userspace: the actual assembly probe/checker, not kernel JIT evidence."""

import os
import shlex
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from native_register_protocol import STAMPS, validate


def run_probe():
    fixture = Path(__file__).with_name("native_register_fixture.c")
    with tempfile.TemporaryDirectory(prefix="kdlock-register-unit-") as directory:
        binary = Path(directory) / "probe"
        subprocess.run(
            shlex.split(os.environ.get("CC", "cc"))
            + [
                "-std=gnu11",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-fno-omit-frame-pointer",
                "-mno-red-zone",
                str(fixture),
                "-o",
                str(binary),
            ],
            check=True,
            timeout=30,
        )
        subprocess.run([str(binary)], check=True, timeout=10)


def fixture():
    row = {
        "task": "123",
        "record": "0",
        "seed": "1",
        "buffer": "ffff800000001000",
        "calls": "1",
        "mask": "0",
        "sp": "ffff800000002000",
        "bp": "ffff800000003000",
        "ip": "ffffffffc0010100",
        "ret": "ffffffffc0010100",
        "tag0": "13579bdf2468ace1",
        "tag1": "fedcba9876543211",
        "returned": "5a3cc396a5696997",
    }
    gpr = [STAMPS[index] ^ 1 if index in STAMPS else 0 for index in range(16)]
    gpr[5:8] = [int(row[key], 16) for key in ("buffer", "bp", "sp")]
    raw = struct.pack("<16Q", *gpr).hex()
    row.update(gpr0=raw[:128], gpr1=raw[128:])
    return row


def render(row=None):
    row = fixture() if row is None else row
    sample = " ".join(f"{key}={value}" for key, value in row.items())
    return (
        "kd_native begin: task=123 ip=ffffffffc0010000 sp=ffff800000002000\n"
        f"kd_regs sample: {sample}\n"
        "kd_regs summary: requests=1 checked=1 marked=1 omitted=0 failures=0\n"
        "kd_native stats: started=1 completed=1 unlocks=1\n"
    )


def check(text):
    return validate(text, 0xFFFFFFFFC0010000, 1)


class NativeRegisterTests(unittest.TestCase):
    def test_actual_native_assembly_and_checker(self):
        run_probe()

    def test_positive_and_ancestor_relay(self):
        self.assertEqual(check(render())["jit_samples"], 1)
        text = render()
        text = text.splitlines()[0] + "\n" + text
        text = text.replace("started=1 completed=1", "started=2 completed=2")
        self.assertEqual(check(text)["native_frames"], 2)
        self.assertFalse(check(text)["flags_checked"])

    def test_native_only_control_cannot_pass_as_jit(self):
        text = "\n".join(render().splitlines()[1:]).replace(
            "started=1 completed=1 unlocks=1", "started=0 completed=0 unlocks=0"
        )
        result = validate(text, 0xFFFFFFFFC0010000, 1, expect_jit=False)
        self.assertEqual(result["jit_samples"], 0)
        self.assertEqual(result["samples"], 1)
        with self.assertRaises(AssertionError):
            check(text)
        for corrupted in (
            render(),
            text.replace("unlocks=0", "unlocks=1"),
            *(
                text + line
                for line in (
                    "JIT_ENTRY test\n",
                    "JIT body witness: entry=1 lock=2 body=1\n",
                    "install JIT chunk: status=0\n",
                    "kd_native ack: task=123 lock=1\n",
                    "kd_native complete: task=123 outer=1\n",
                )
            ),
        ):
            with self.subTest(log=corrupted), self.assertRaises(AssertionError):
                validate(corrupted, 0xFFFFFFFFC0010000, 1, expect_jit=False)

    def test_each_register_corruption_with_zero_kernel_mask(self):
        row = fixture()
        gprs = list(struct.unpack("<16Q", bytes.fromhex(row["gpr0"] + row["gpr1"])))
        for index in range(16):
            with self.subTest(index=index), self.assertRaises(AssertionError):
                altered = gprs.copy()
                altered[index] ^= 1
                raw = struct.pack("<16Q", *altered).hex()
                check(render(row | {"gpr0": raw[:128], "gpr1": raw[128:]}))

    def test_stack_return_and_identity_corruption(self):
        for key in (
            "record",
            "task",
            "seed",
            "calls",
            "mask",
            "buffer",
            "sp",
            "bp",
            "ip",
            "ret",
            "tag0",
            "tag1",
            "returned",
        ):
            with self.subTest(key=key), self.assertRaises(AssertionError):
                check(
                    render(fixture() | {key: "1" if key in {"record", "mask"} else "0"})
                )

    def test_missing_duplicate_and_malformed_fields(self):
        text = render()
        for key in fixture():
            row = fixture()
            del row[key]
            with self.subTest(key=key), self.assertRaises(AssertionError):
                check(render(row))
        for corrupted in (
            "",
            text + text,
            text.replace("seed=1", "seed=1 seed=1"),
            text.replace("seed=1", "seed=-1"),
            text.replace("seed=1", "seed=gg"),
            text.replace("seed=1", "seed=" + "f" * 17),
            text.replace("gpr0=", "gpr0=0"),
            text.replace("calls=1", "calls=1x"),
            text.replace("marked=1", "marked=0"),
            text.replace("omitted=0", "omitted=1"),
            text.replace("failures=0", "failures=1"),
            text.replace("checked=1", "checked=0"),
        ):
            with self.subTest(log=corrupted), self.assertRaises(AssertionError):
                check(corrupted)

    def test_handoff_target_stack_and_completion_required(self):
        text = render()
        for corrupted in (
            "\n".join(text.splitlines()[1:]),
            text.replace("ip=ffffffffc0010000", "ip=ffffffffc0010001"),
            text.replace("sp=ffff800000002000", "sp=ffff800000002008", 1),
            text.replace("task=123", "task=124", 1),
            text.replace("completed=1", "completed=0"),
            text.replace("unlocks=1", "unlocks=0"),
        ):
            with self.subTest(log=corrupted), self.assertRaises(AssertionError):
                check(corrupted)


if __name__ == "__main__":
    unittest.main(verbosity=2)
