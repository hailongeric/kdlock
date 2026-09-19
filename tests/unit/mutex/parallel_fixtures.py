"""Shared immutable fixture constructors for the parallel protocol tests."""
import copy
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

PUBLISHED = [{"entry": 0x100 + i, "code": 0x200 + i, "kind": 2} for i in range(2)]


def reloaded_fixture(first):
    original = fixture(first)
    lines = [f"kd_parallel native queued: lane={i} waiters=3" for i in (0, 1)]
    for line in original.splitlines():
        if not line.startswith("kd_parallel "):
            continue
        line = line.replace("owner=20", "owner=10").replace("owner=21", "owner=11")
        if line.startswith("kd_parallel lane:"):
            lane = int(line.split("lane=")[1][0])
            line = f"kd_parallel lane: lane={lane} sequence=3 digest=486 claimed=15 a=0 b=0"
        lines.append(line)
    for lane in (0, 1):
        for role in (1, 2, 3):
            task = lane + 20 if role == 2 else 100 + lane * 8 + role
            owner = f"1{lane}" if role == 2 else f"ff{task:x}"
            lines.append(
                f"kd_parallel retired record: lane={lane} role={role} task={task} waiter={owner} owner={owner} before=1 held=1 called=1 after=1 value={((lane * 8 + role + 1) * 3 + 17) ^ 0x5A5A:x}"
            )
    symbols = {
        "kd_parallel_cs0": 0x10,
        "kd_parallel_cs1": 0x20,
        "kd_parallel_native": 0xFF,
        "parallel_lanes": 0xA0,
    }
    metadata = {
        "before": symbols,
        "after": dict(symbols),
        "first": first,
        "sites": {str(0x100 + i): f"kd_parallel_cs{i}" for i in (0, 1)},
        "module_sha256": "a" * 64,
        "completed": True,
        "registry": [dict(p, status=-3) for p in PUBLISHED],
        "state": {"state": 2, "modules": 0, "frames": 0, "writers": 0},
    }
    text = original + "\nkd_source reload: phase=begin\n"
    text += "\n".join(lines) + "\nkd_source reload: phase=end\n"
    return text, metadata


def fixture(first):
    lines = []
    for lane in (0, 1):
        lines += [
            f"JIT body witness: entry={0x100 + lane:x} lock=a{lane} body=1",
            f"kd_native begin: task={lane + 20} outer=a{lane} entry={0x100 + lane:x} ip=ff sp=f{lane} held=2 mutex=1 cpu={lane * 4 + 1} outer_released=0 remaining=2",
            f"kd_parallel arrive: lane={lane} task={lane + 20} waiter=1{lane} owner=2{lane} outer=a{lane} inner=b{lane} record=c{lane} before=1 held=1 called=0 after=0 value={(lane * 8 + 3) * 3 + 17:x} cpu={lane * 4 + 2} valid=1",
        ]
    for lane in (first, 1 - first):
        lines += [
            f"kd_parallel resume: lane={lane} task={lane + 20} owner=2{lane} arrived=3 done={0 if lane == first else 1 << first} valid=1",
            f"kd_native ack: task={lane + 20} lock=b{lane} mutex=1 last_spin=0",
            f"kd_native complete: task={lane + 20} outer=a{lane} mutex=1",
            f"kd_native ack: task={lane + 20} lock=a{lane} mutex=1 last_spin=0",
            f"kd_parallel done: lane={lane} task={lane + 20} waiter=1{lane} owner=2{lane} record=c{lane} before=1 held=1 called=1 after=1 value={((lane * 8 + 3) * 3 + 17) ^ 0x5A5A:x} valid=1",
        ]
    digest = 0
    for sequence in range(1, 12005):
        digest = (digest * 33 + sequence) & ((1 << 64) - 1)
    for lane in (0, 1):
        lines.append(
            f"kd_parallel lane: lane={lane} sequence=12004 digest={digest:x} claimed=15 a=0 b=0"
        )
    lines += [
        f"kd_parallel stats: first={first} shared_cpu=0 pressure=0 pressure_done=0 arrived=3 done=3 failures=0",
        "kd_native stats: started=2 completed=2 unlocks=4",
        "kd_mutex stats: context_busy=0 multi_slot=0 node_overflow=0",
        "kd_mutex tasks: active_tasks=0 task_alloc_failure=0 task_reroutes=0",
        "kd_exec invariant_failures=0",
    ]
    return "\n".join(lines)


def shared_fixture():
    # Lane 1 executes its own original CS while lane 0 still borrows A/B.
    # There must be no second generated body, frame registration or owner ACK.
    lines = []
    for line in fixture(1).splitlines():
        if line.startswith("kd_native ") and "task=21" in line:
            continue
        if line.startswith("JIT body witness: entry=101"):
            continue
        if line.startswith("kd_parallel arrive: lane=1"):
            lines += [
                "mutex JIT context busy: task=31 waiter=21 entry=101 lock=a1 cpu=1",
                "kd_parallel contender: task=31 owner=31 cpu=1 valid=1",
            ]
        lines.append(line.replace("owner=21", "owner=11"))
    return (
        "\n".join(lines)
        .replace("shared_cpu=0", "shared_cpu=1")
        .replace("started=2 completed=2 unlocks=4", "started=1 completed=1 unlocks=2")
        .replace("context_busy=0 multi_slot=0", "context_busy=1 multi_slot=1")
    )


def after_publication(shared=False):
    return [
        dict(
            item,
            status=int(not shared or lane == 0),
            target=0xFF if not shared or lane == 0 else 0,
        )
        for lane, item in enumerate(PUBLISHED)
    ]


def pressure_fixture(early=False):
    # The no-node task may win A1 before or after the queued waiter. Both
    # orders are legal; its full-mask refusal and final own-owner unlock must
    # still be contained within the first waiter's retained native frame.
    text = shared_fixture().replace("cpu=6 valid=1", "cpu=1 valid=1")
    text = text.replace(
        "mutex JIT context busy:",
        "mutex node fallback: task=41 entry=101 lock=a1 cpu=1 slots=f\n"
        "mutex task fallback: task=42 entry=101 lock=a1 cpu=1\n"
        "mutex JIT context busy:",
        1,
    )
    before = "kd_parallel contender:" if early else "kd_parallel resume: lane=0"
    text = text.replace(
        before,
        "kd_parallel pressure done: role=5 task=41 waiter=41 owner=41 outer=a1 inner=b1 record=c5 before=1 held=1 called=1 after=1 value=5a61 cpu=1 valid=1\n"
        "kd_parallel pressure done: role=6 task=42 waiter=42 owner=42 outer=a1 inner=b1 record=c6 before=1 held=1 called=1 after=1 value=5a64 cpu=1 valid=1\n"
        + before,
        1,
    )
    digest = 0
    for sequence in range(1, 12007):
        digest = (digest * 33 + sequence) & ((1 << 64) - 1)
    old = next(line for line in text.splitlines() if "lane: lane=1" in line)
    return (
        text.replace(
            old,
            f"kd_parallel lane: lane=1 sequence=12006 digest={digest:x} claimed=111 a=0 b=0",
        )
        .replace("pressure=0 pressure_done=0", "pressure=1 pressure_done=3")
        .replace("node_overflow=0", "node_overflow=1")
        .replace("task_alloc_failure=0", "task_alloc_failure=1")
    )


def code_pool_fixture(first=0):
    # Synthetic evidence exercises the observer's rejection contract only.
    # Live tests must separately derive these CALL sites from the loaded ELF.
    sites = {
        str(i): {"function": 0x1000 + i * 32, "entry": 0x1010 + i * 32}
        for i in range(64)
    }
    before = [dict(p, pid=0, tgid=42, status=0) for p in PUBLISHED]
    before.append(
        {
            "entry": sites["0"]["entry"],
            "code": 0x5000,
            "pid": 0,
            "tgid": 43,
            "kind": 2,
            "status": -1,
        }
    )
    held = copy.deepcopy(before)
    for row in held[:2]:
        row["status"] = 1
    held.append(
        {"entry": 0x9000, "code": 0x6000, "pid": 0, "tgid": 44, "kind": 2, "status": -1}
    )
    full = held + [
        {
            "entry": sites[str(i)]["entry"],
            "code": 0x6000 + i * 4096,
            "pid": 0,
            "tgid": 45,
            "kind": 2,
            "status": -1,
        }
        for i in range(1, 61)
    ]
    evidence = {
        "sites": sites,
        "lock": 0xC00,
        "module_sha256": "a" * 64,
        "snapshots": {
            phase: {
                "source": {
                    "state": 0,
                    "modules": 1,
                    "frames": 0 if phase == "prepare" else 2,
                    "writers": 0,
                },
                "registry": copy.deepcopy(registry),
            }
            for phase, registry in (
                ("prepare", before),
                ("held", held),
                ("filled", full),
                ("drained", full),
            )
        },
    }
    lines = []
    for i in range(64):
        if i >= 61:
            lines.append(
                f"kd_exe_add: code block pool exhausted entry={sites[str(i)]['entry']:x} task=100 kind=2"
            )
        lines.append(
            f"kd_parallel code record: role=1 site={i} fn={sites[str(i)]['function']:x} task=100 waiter=ee00 owner=ee00 lock=c00 updates=1 value={(i + 7) * 33 + i + 1:x} valid=1"
        )
    lines.append("kd_parallel code queued: lock=c00 task=102 waiters=3")
    lines.append(
        f"mutex JIT not ready: task=103 waiter=104 entry={sites['63']['entry']:x} lock=c00 cpu=9"
    )
    for role in (3, 4, 5):
        lines.append(
            f"kd_parallel code record: role={role} site=63 fn={sites['63']['function']:x} task={100 + role} waiter=ee0{role} owner=ee0{role} lock=c00 updates=1 value={(role + 7) * 33 + 64:x} valid=1"
        )
    text = fixture(first)
    point = text.index("kd_parallel resume:")
    text = (
        "JIT code block pool ready: 64/64\n"
        + text[:point]
        + "\n".join(lines)
        + "\n"
        + text[point:]
    )
    text += (
        "\nkd_parallel code stats: warm=12000 filled=64 claimed=63 updates=12067 lock=0"
    )
    return text, evidence


def with_native_peers(text, first):
    """Compose renamed borrowers and peer cancellation around the frame contract.

    Synthetic log records test the oracle, not Linux waiting or live signals.
    """
    routed, arrived = [], 0
    controls = [
        f"kd_parallel routed native: lane={lane} task={20 + lane} waiter=1{lane} owner=2{lane} outer=a{lane} inner=b{lane} local=e{lane} local_owner=1{lane} after_owner=0 acquired=1 released=1 comm=kd_renamed valid=1"
        for lane in (0, 1)
    ]
    for line in text.splitlines():
        if line.startswith(
            ("kd_parallel arrive:", "kd_parallel resume:", "kd_parallel done:")
        ):
            lane = int(re.search(r"lane=(\d+)", line)[1])
            if line.startswith("kd_parallel arrive:"):
                routed.append(
                    f"kd_resume rename: task={20 + lane} old=klock_test new=kd_renamed cpu={4 * lane + 2} preempt_before=0 preempt_after=0 irq_before=0 irq_after=0 valid=1"
                )
            routed.append(line + " comm=kd_renamed")
            if line.startswith("kd_parallel arrive:"):
                arrived += 1
                if arrived == 2:
                    routed.extend(controls)
            if line.startswith("kd_parallel done:"):
                routed.append(
                    f"kd_resume rename: task={20 + lane} old=kd_renamed new=klock_test cpu={4 * lane + 2} preempt_before=0 preempt_after=0 irq_before=0 irq_after=0 valid=1"
                )
        else:
            routed.append(line)
    text = "\n".join(routed)
    queued = []
    for attempt in (1, 2):
        for lane in (0, 1):
            if attempt == 2:
                queued.append(
                    f"kd_parallel peer cancelled: lane={lane} task={100 + lane} waiter=d{lane} lock=b{lane} owner=2{lane} other_owner=2{1 - lane} error=4 pending=1 fatal=0 queued=0 matched=0 cancelled=1 acquired=0 released=0 valid=1"
                )
            queued += [
                f"kd_parallel peer try: lane={lane} attempt={attempt} task={100 + lane} waiter=d{lane} lock=b{lane} owner=2{lane} result=0 comm=kd_native valid=1",
                f"kd_parallel peer queued: lane={lane} attempt={attempt} task={100 + lane} waiter=d{lane} lock=b{lane} owner=2{lane} queued=1 matched=1 valid=1",
            ]
    marker = f"kd_parallel resume: lane={first} "
    text = text.replace(marker, "\n".join(queued) + "\n" + marker)
    for lane in (first, 1 - first):
        value = ((0x700 + lane) * 33 + 17) ^ 0x5A5A
        lines = [
            f"kd_parallel peer acquired: lane={lane} task={100 + lane} waiter=d{lane} lock=b{lane} owner=d{lane} other=b{1 - lane} other_owner=2{1 - lane} cross_try={0 if lane == first else 2} value={value:x} valid=1",
            f"kd_parallel peer released: lane={lane} task={100 + lane} acquired=1 released=1 value={value:x} valid=1",
        ]
        marker = f"kd_native ack: task={20 + lane} lock=b{lane} mutex=1 last_spin=0"
        text = text.replace(marker, marker + "\n" + "\n".join(lines))
    return (
        text
        + "\nkd_parallel peer stats: completed=3 acquired=2 released=2 cancelled=2 valid=1"
    )


def waiter_signal_fixture(first):
    """Compose task-exit evidence with the existing full two-frame oracle."""
    text = with_native_peers(fixture(first), first)
    text = "\n".join(
        line + f" pending=1 fatal={int(f'lane={first} ' in line)}"
        if line.startswith("kd_parallel resume:") else line
        for line in text.splitlines()
    )
    prefix = text[:text.index(f"kd_parallel resume: lane={1 - first} ")]
    evidence = {
        "first": first, "complete": True, "client_sha256": "a" * 64,
        "source": {
            "before": {"state": 0, "modules": 1, "frames": 2, "writers": 0},
            "after_exit": {"state": 1, "modules": 1, "frames": 1, "writers": 1},
        },
        "waiters": [
            {"lane": lane, "pid": 20 + lane, "pidfd": True,
             "signum": 9 if lane == first else 10, "before_ns": 100, "after_ns": 101}
            for lane in (0, 1)
        ],
        "after_exit": {
            "pidfd_exited": True, "survivor_alive": True, "observed_ns": 200,
            "log_bytes": len(prefix.encode()),
            "log_sha256": hashlib.sha256(prefix.encode()).hexdigest(),
        },
    }
    clients = [
        f"parallel waiter client enter: lane={lane} pid={20 + lane}\n"
        + ("" if lane == first else
           f"parallel waiter client return: lane={lane} pid={20 + lane} ret=0 errno=0 signals=1\n")
        for lane in (0, 1)
    ]
    statuses = "\n".join(f"{i}\t{137 if i == 4 + first else 0}" for i in range(8))
    return text, evidence, clients, statuses


def shadow_fixture(first=0):
    """Compose a real-capacity contract into the existing peer/pool fixture.

    This is an oracle fixture, not proof of kernel allocation or Linux waiting;
    the same complex live scripts must independently produce these observations.
    """
    text, code = code_pool_fixture(first)
    text = with_native_peers(text, first)
    base, stride, entry = 0x100000, 32, 0x8888
    evidence = {
        "base": base,
        "stride": stride,
        "entry": entry,
        "count": 1025,
        "module_sha256": "b" * 64,
        "snapshots": {
            phase: {
                "allocated": allocated,
                "source": {
                    "state": 0,
                    "modules": 1,
                    "frames": 0 if phase == "prepare" else 2,
                    "writers": 0,
                },
            }
            for phase, allocated in (
                ("prepare", 3),
                ("held", 5),
                ("filled", 1024),
                ("drained", 1024),
            )
        },
    }
    declarations = [
        f"kd_parallel shadow layout: base={base:x} stride={stride} count=1025"
    ]
    declarations += [
        f"kd_hotlock selftest promote: lock={base + i * stride:x}" for i in range(1025)
    ]
    lines = []
    value = 0
    for role, indexes in ((0, range(1025)), (1, [1024]), (2, [1024]), (3, [1024])):
        for i in indexes:
            lock = base + i * stride
            if (role == 0 and i >= 1019) or role >= 2:
                lines.append(
                    f"mutex shadow fallback: task={200 + role} entry={entry:x} lock={lock:x} cpu=9"
                )
            if role == 1:
                lines.append(
                    f"kd_parallel shadow queued: task=201 owner=ff201 lock={lock:x} count=2 matched=3"
                )
            value = (i + 7 if not role else value) * 33 + i + 1
            lines.append(
                f"kd_parallel shadow record: role={role} index={i} task={200 + role} waiter=ff{200 + role} owner=ff{200 + role} lock={lock:x} registered={int(not role and i < 1019)} updates={role + 1} value={value:x} valid=1"
            )
    marker = "kd_parallel peer try: lane=0 "
    text = text.replace(marker, "\n".join(lines) + "\n" + marker, 1)
    return "\n".join(declarations) + "\n" + text, code, evidence
