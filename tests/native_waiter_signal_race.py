"""Race a pidfd signal with the real B owner's test release gate in the guest."""

import argparse
import json
import os
import re
import time
from pathlib import Path

from mutex_signal_protocol import PARAMS, trigger_race


def run(client, signum, offset_us):
    # Keep both triggers off the seven workload CPUs. Offsets bias scheduling;
    # they do not fabricate a kernel return or prove simultaneous lock updates.
    cpus = (7, 8, 9)
    assert set(cpus) <= os.sched_getaffinity(0)
    assert signum in (9, 10) and -50000 <= offset_us <= 50000
    deadline = time.monotonic() + 12
    while int((PARAMS / "native_waiter_phase").read_text()) != 1:
        assert time.monotonic() < deadline, "original waiter did not reach B's queue"
        time.sleep(0.01)
    pid = int((PARAMS / "native_waiter_pid").read_text())
    entered = re.findall(
        r"pending client enter: pid=(\d+) signal=(\d+)", client.read_text()
    )
    assert entered == [(str(pid), str(signum))] and pid > 0
    # pidfd pins the PID identity, not an extra test-owned task_struct reference.
    # The client cannot normally exit until this signal; a failed client is not
    # permission to signal whatever later reuses its numeric PID.
    fd = os.pidfd_open(pid, 0)
    try:
        tasks = {int(path.name) for path in Path(f"/proc/{pid}/task").iterdir()}
        assert tasks == {pid}
        assert Path(f"/proc/{pid}/comm").read_text().strip() == "klock_test"
        trigger = trigger_race(
            pid,
            signum,
            cpus,
            offset_us,
            release_parameter="native_waiter_release",
            pidfd=fd,
        )
        return {
            "pid": pid,
            "signal": signum,
            "offset_us": offset_us,
            "trigger": trigger,
        }
    finally:
        os.close(fd)
        # Release an unfinished fixture wait on controller failure. This never
        # unlocks B remotely and does not authorize unloading a live caller.
        (PARAMS / "native_waiter_release").write_text("1\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--signal", type=int, choices=(9, 10), required=True)
    parser.add_argument("--offset-us", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.client, args.signal, args.offset_us)
    args.output.write_text(json.dumps(result, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
