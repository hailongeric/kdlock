"""Verify the real shared-stack control exit, not an ordinary native CALL miss.

The holder supplies the write; production kdlock supplies the guard/native/ACK
events. Registry snapshots and the loaded module's CALL relocations distinguish
post-control continuation from running the observer by some other native path.
"""

import argparse
import json
import re
import subprocess
from pathlib import Path

from mutex_signal_protocol import wait_ready
from native_only_protocol import entries

ROOT = Path(__file__).resolve().parents[2]
OLD = 0x123456789ABCDEF0
NEW = 0x0FEDCBA987654321


def snapshot():
    return [
        {
            "entry": e.rip,
            "target": e.target,
            "code": e.code,
            "pid": e.pid,
            "tgid": e.tgid,
            "kind": e.lock_kind,
            "status": e.status,
        }
        for e in entries()
    ]


def control_returns(text, function, symbol="run_nested_mutex_cs"):
    """Relocate only actual E8 CALLs with the mutex_lock relocation.

    Use the module built/loaded by this test, not a guessed source label or
    the observer's own CALL successor. This is a source-packet check, not an
    assertion that every instruction in the published image was executed.
    """
    # The shared-B workload has two constant-lane wrappers. Keep the same
    # checked relocation parser instead of guessing their entry offsets.
    starts = re.findall(
        r"^([0-9a-f]+) <" + re.escape(symbol) + r">:", text, re.MULTILINE
    )
    assert len(starts) == 1, "missing source function"
    base = int(starts[0], 16)
    calls = {}
    for match in re.finditer(
        r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)callq?\s", text, re.MULTILINE
    ):
        raw = bytes.fromhex(match[2])
        if len(raw) == 5 and raw[0] == 0xE8:
            calls[int(match[1], 16) + 1] = int(match[1], 16) + len(raw)
    returns = []
    for relocation in re.findall(
        r"^\s*([0-9a-f]+):\s+R_X86_64_PLT32\s+mutex_lock-0x4\s*$", text, re.MULTILINE
    ):
        position = int(relocation, 16)
        if position in calls:
            returns.append(function + calls[position] - base)
    assert len(returns) >= 2, "missing outer/inner mutex CALLs"
    return returns


def validate(text, before, after, source, assembly, statuses):
    def rows(label):
        return [
            (m.start(), dict(re.findall(r"(\w+)=(-?\w+)", m[1])))
            for m in re.finditer(re.escape(label) + r"[ :]([^\n]+)", text)
        ]

    def one(label):
        found = rows(label)
        assert len(found) == 1, (label, found)
        return found[0]

    def expect(row, **wanted):
        assert all(row.get(k) == str(v) for k, v in wanted.items()), (row, wanted)

    def addr(row, key):
        return int(row[key], 16)

    publish_at, publish = one("kd_stack publish:")
    write_at, write = one("kd_stack changed:")
    guard_at, guard = one("reason=MUTEX_STACK_CHANGED")
    begin_at, begin = one("kd_native begin:")
    read_at, read = one("kd_stack observed:")
    done_at, done = one("kd_stack complete:")
    pid = int(publish["task"])
    for row in (write, guard, begin, read, done):
        expect(row, task=pid)
    expect(write, queued=1, valid=1, holder_comm="kd_native")
    expect(read, reads=1, valid=1)
    expect(done, completed=1, valid=1)
    expect(begin, held=2, remaining=2, mutex=1, outer_released=0)
    assert len({addr(write, k) for k in ("waiter", "combiner", "holder")}) == 3
    assert all(addr(write, k) for k in ("waiter", "combiner", "holder"))
    assert len({pid, int(write["combiner_pid"]), int(write["holder_pid"])}) == 3
    assert addr(publish, "waiter") == addr(write, "waiter") == addr(read, "waiter")
    assert addr(read, "a_owner") == addr(read, "b_owner") == addr(write, "combiner")
    assert addr(publish, "slot") == addr(write, "slot")
    assert addr(publish, "old") == addr(write, "old") == OLD
    assert addr(write, "new") == addr(read, "value") == NEW
    assert addr(begin, "outer") == addr(write, "outer") != addr(write, "lock")
    assert addr(guard, "target") == source["mutex_lock"]
    assert addr(guard, "ip") in source["returns"]
    assert addr(guard, "ip") not in (source["mutex_lock"], source["observer"])
    assert addr(guard, "ip") != addr(guard, "entry")
    for key in ("entry", "ip", "sp"):
        assert addr(begin, key) == addr(guard, key), (begin, guard)
    assert addr(guard, "sp") <= addr(write, "slot") <= addr(guard, "sp") + 256 - 8
    assert addr(write, "slot") % 8 == 0

    acks = rows("kd_native ack:")
    assert len(acks) == 2
    for (_, ack), key in zip(acks, ("lock", "outer")):
        expect(ack, task=pid, mutex=1, last_spin=0)
        assert addr(ack, "lock") == addr(write, key)
    assert (
        publish_at
        < write_at
        < guard_at
        < begin_at
        < read_at
        < acks[0][0]
        < acks[1][0]
        < done_at
    )
    _, completed = one("kd_native complete:")
    expect(completed, task=pid, mutex=1)
    expect(one("kd_native stats:")[1], started=1, completed=1, unlocks=2)
    expect(one("kd_stack stats:")[1], writes=1, reads=1, completed=1)
    expect(one("kd_mutex stack checks:")[1], bytes=256, changed=1, unavailable=0)
    expect(one("kd_resume records:")[1], requests=12002, failures=0)
    expect(one("kd_pending mutex:")[1], observed=0, acquired=0)

    # A real control exit does not request callee learning. Reading before
    # retire is essential: retire itself would replace NORMAL with NATIVE_ONLY.
    assert len(before) == 1
    entry = before[0]
    identity = lambda row: (row["pid"], row["entry"])
    assert len({identity(row) for row in after}) == len(after)
    assert [row for row in after if identity(row) == identity(entry)] == before
    # Other role functions register their own cold entries while the daemon
    # is stopped. They must stay UNINIT, with no learned target or JIT body;
    # they are not additional executions of the root under observation.
    for row in after:
        if identity(row) != identity(entry):
            assert row["status"] == -1 and row["target"] == 0 and row["kind"] == 2
            assert row["code"] and row["tgid"] > 0
    assert entry["entry"] == addr(guard, "entry")
    assert entry["status"] == 0 and entry["kind"] == 2 and entry["target"] == 0
    assert entry["code"] and entry["tgid"] > 0
    _, body = one("JIT body witness:")
    expect(body, body=1)
    assert addr(body, "entry") == entry["entry"]
    assert addr(body, "lock") == addr(write, "outer")
    assert f"loc_{entry['entry']:x}:" in assembly
    assert "Stack_JIT_WITNESS" in assembly
    assert statuses == {role: 0 for role in range(7)}
    for forbidden in (
        "reason=PENDING_LOCK_NATIVE",
        "reason=MUTEX_STACK_UNAVAILABLE",
        "kd_stack error:",
        "valid=0",
        "JIT retry",
    ):
        assert forbidden not in text, forbidden
    return {
        "task": pid,
        "entry": hex(entry["entry"]),
        "post_call": hex(addr(guard, "ip")),
        "slot": hex(addr(write, "slot")),
        "value": hex(NEW),
        "owners_retained": 2,
        "native_frames": 1,
        "owner_acks": 2,
        "jit_bodies": 1,
        "requests": 12002,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "snapshot", "check"))
    parser.add_argument("out", type=Path)
    parser.add_argument("artifact", nargs="?", type=Path)
    args = parser.parse_args()
    if args.action == "snapshot":
        (args.out / "stack-after.json").write_text(json.dumps(snapshot(), indent=2))
        return
    assert args.artifact is not None
    if args.action == "prepare":
        wait_ready(args.artifact)
        symbols = {}
        for line in Path("/proc/kallsyms").read_text().splitlines():
            words = line.split()
            if words[2] in (
                "mutex_lock",
                "run_nested_mutex_cs",
                "kd_stack_change_observe",
            ):
                symbols[words[2]] = int(words[0], 16)
        code = subprocess.check_output(
            [
                "objdump",
                "-dr",
                "--disassemble=run_nested_mutex_cs",
                str(ROOT / "workload_modules/lock_scenarios/klock_module.ko"),
            ],
            text=True,
            timeout=10,
        )
        (args.out / "stack-source.asm").write_text(code)
        source = {
            "mutex_lock": symbols["mutex_lock"],
            "observer": symbols["kd_stack_change_observe"],
            "returns": control_returns(code, symbols["run_nested_mutex_cs"]),
        }
        (args.out / "stack-source.json").write_text(json.dumps(source, indent=2))
        (args.out / "stack-before.json").write_text(json.dumps(snapshot(), indent=2))
        return
    statuses = [
        line.split() for line in (args.out / "role-status.tsv").read_text().splitlines()
    ]
    assert len(statuses) == 7
    print(
        json.dumps(
            validate(
                (args.out / "stack-change.log").read_text(),
                json.loads((args.out / "stack-before.json").read_text()),
                json.loads((args.out / "stack-after.json").read_text()),
                json.loads((args.out / "stack-source.json").read_text()),
                (args.artifact / "jit.S").read_text(),
                {int(role): int(status) for role, status in statuses},
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
