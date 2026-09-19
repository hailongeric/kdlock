"""Private TestCases collected by test_mutex_parallel_protocol."""
import copy
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mutex_parallel_protocol import (
    signal_native_peers,
    signal_original_waiters,
    validate,
    validate_peer_signals,
    validate_waiter_signals,
)

from parallel_fixtures import PUBLISHED, fixture, with_native_peers, waiter_signal_fixture

class PeerSignalTests(unittest.TestCase):
    def client_logs(self):
        return [
            "\n".join(
                (
                    f"parallel peer client enter: lane={lane} pid={100 + lane}",
                    f"parallel peer client cancelled: lane={lane} pid={100 + lane} ret=-1 errno=4 signals=1",
                    f"parallel peer client return: lane={lane} pid={100 + lane} ret=0 errno=0 signals=1",
                )
            )
            + "\n"
            for lane in (0, 1)
        ]

    def control(self, phase, out, *, corrupt=""):
        # Proc, pidfd, source and signal APIs are all substitutes here. Live
        # tests must independently verify real wait lists and the same clients.
        from source_retirement import source

        client = out.parent / "mutex-signal-client"
        original_text, original_bytes, original_resolve = (
            Path.read_text,
            Path.read_bytes,
            Path.resolve,
        )

        def read_text(path, *args, **kwargs):
            if str(path).startswith("/proc/"):
                if path.name == "comm":
                    return "wrong\n" if corrupt == "comm" else "kd_native\n"
                if path.name == "status":
                    pid = int(path.parent.name)
                    return (
                        f"Tgid:\t{pid}\nThreads:\t{2 if corrupt == 'threads' else 1}\n"
                    )
            return original_text(path, *args, **kwargs)

        def read_bytes(path, *args, **kwargs):
            if str(path).startswith("/proc/") and path.name == "cmdline":
                lane = int(path.parent.name) - 100
                values = [str(client), str(lane), "kd_native", "parallel-peer"]
                if corrupt == "argv":
                    values[-1] = "pending-int"
                return b"\0".join(os.fsencode(v) for v in values) + b"\0"
            return original_bytes(path, *args, **kwargs)

        def resolve(path, *args, **kwargs):
            if str(path).startswith("/proc/") and path.name == "exe":
                return out / "wrong" if corrupt == "exe" else client
            return original_resolve(path, *args, **kwargs)

        state = {
            "state": 0,
            "modules": 1,
            "frames": 1 if corrupt == "frames" else 2,
            "writers": 0,
        }
        text = with_native_peers(fixture(0), 0)
        if corrupt == "queue":
            text = text.replace(
                "queued: lane=1 attempt=1 task=101", "queued: lane=1 attempt=1 task=102"
            )
        with (
            patch("mutex_parallel_signals.os.open", return_value=90),
            patch("mutex_parallel_signals.os.close") as close,
            patch.object(source, "info", return_value=state),
            patch("mutex_parallel_signals.subprocess.check_output", return_value=text),
            patch(
                "mutex_parallel_signals.os.pidfd_open", side_effect=[77, 78]
            ) as opened,
            patch(
                "mutex_parallel_signals.select.select",
                return_value=([77] if corrupt == "exited" else [], [], []),
            ),
            patch("mutex_parallel_signals.signal.pidfd_send_signal") as send,
            patch.object(Path, "read_text", read_text),
            patch.object(Path, "read_bytes", read_bytes),
            patch.object(Path, "resolve", resolve),
        ):
            if corrupt:
                with self.assertRaises(AssertionError):
                    signal_native_peers(phase, out)
                send.assert_not_called()
            else:
                signal_native_peers(phase, out)
                self.assertEqual(send.call_count, 2 if phase == "signal" else 0)
                if phase == "signal":
                    self.assertEqual(
                        [c.args for c in send.call_args_list],
                        [(77, 10, None, 0), (78, 10, None, 0)],
                    )
            self.assertEqual(close.call_count, 1 + opened.call_count)

    def test_verified_pidfds_and_userspace_retry_are_required(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = root / "native-peers"
            out.mkdir()
            (root / "mutex-signal-client").write_bytes(b"fixture client")
            clients = self.client_logs()
            for lane, log in enumerate(clients):
                (out / f"role-{lane}.log").write_text(log)
            self.control("signal", out)
            self.control("requeued", out)
            evidence = json.loads((out / "signal.json").read_text())
            text = with_native_peers(fixture(0), 0)
            self.assertEqual(
                validate_peer_signals(text, evidence, clients),
                {
                    "pidfd_signals": 2,
                    "userspace_cancellations": 2,
                    "explicit_retries": 2,
                },
            )
            for key, value in (
                ("pid", 999),
                ("pidfd", False),
                ("signum", 9),
                ("before_ns", 0),
                ("lane", 1),
            ):
                bad = copy.deepcopy(evidence)
                bad["peers"][0][key] = value
                with self.subTest(key=key), self.assertRaises(AssertionError):
                    validate_peer_signals(text, bad, clients)
            bad = copy.deepcopy(evidence)
            bad["source"]["requeued"]["frames"] = 1
            with self.assertRaises(AssertionError):
                validate_peer_signals(text, bad, clients)
            for old, new in (
                ("errno=4", "errno=0"),
                ("ret=-1", "ret=0"),
                ("signals=1", "signals=2"),
            ):
                with self.subTest(field=old), self.assertRaises(AssertionError):
                    validate_peer_signals(
                        text, evidence, [clients[0].replace(old, new), clients[1]]
                    )

    def test_wrong_client_or_missing_retained_frames_is_never_signalled(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = root / "native-peers"
            out.mkdir()
            (root / "mutex-signal-client").write_bytes(b"fixture client")
            for lane, log in enumerate(self.client_logs()):
                (out / f"role-{lane}.log").write_text(log)
            for corrupt in (
                "comm",
                "threads",
                "argv",
                "exe",
                "frames",
                "queue",
                "exited",
            ):
                with self.subTest(corrupt=corrupt):
                    self.control("signal", out, corrupt=corrupt)

    def test_delivered_client_has_no_automatic_eintr_retry(self):
        source = Path(__file__).with_name("mutex_parallel_client_fixture.c")
        with tempfile.TemporaryDirectory() as temp:
            executable = Path(temp) / "client-fixture"
            subprocess.run(
                [
                    *shlex.split(os.environ.get("CC", "cc")),
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    str(source),
                    "-o",
                    str(executable),
                ],
                check=True,
                timeout=30,
            )
            result = subprocess.run(
                [str(executable)], check=True, text=True, capture_output=True, timeout=5
            )
            self.assertIn(
                "24 valid/error rounds and invalid target pass", result.stdout
            )


class OriginalWaiterSignalTests(unittest.TestCase):
    def test_both_orders_keep_a_live_frame_after_verified_fatal_exit(self):
        for first in (0, 1):
            text, evidence, clients, statuses = waiter_signal_fixture(first)
            result = validate(text, PUBLISHED, 0xFF, first, native_peers=True)
            self.assertEqual(result["owner_acks"], 4)
            self.assertEqual(result["jit_bodies"], 2)
            self.assertEqual(
                validate_waiter_signals(text, evidence, clients, statuses, first),
                {"pidfd_signals": 2, "fatal_exits": 1, "surviving_native_frames": 1,
                 "nonfatal_returns": 1},
            )

    def test_exit_status_cannot_replace_identity_ack_or_pending_signal(self):
        text, evidence, clients, statuses = waiter_signal_fixture(0)
        for path, value in (
            (("complete",), False),
            (("first",), 1),
            (("source", "after_exit", "frames"), 0),
            (("source", "after_exit", "writers"), 0),
            (("after_exit", "pidfd_exited"), False),
            (("after_exit", "survivor_alive"), False),
            (("after_exit", "observed_ns"), 99),
            (("after_exit", "log_sha256"), "a" * 64),
            (("waiters", 0, "pid"), 99),
            (("waiters", 0, "signum"), 10),
            (("waiters", 1, "pidfd"), False),
        ):
            bad = copy.deepcopy(evidence)
            item = bad
            for key in path[:-1]:
                item = item[key]
            item[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(AssertionError):
                validate_waiter_signals(text, bad, clients, statuses, 0)
        for old, new in (
            ("kd_native ack: task=20 lock=a0", "kd_native ack: task=21 lock=a0"),
            ("kd_parallel done: lane=0 task=20", "kd_parallel done: lane=1 task=20"),
            ("pending=1 fatal=1", "pending=0 fatal=1"),
            ("comm=kd_renamed pending=1 fatal=0", "comm=kd_renamed pending=1 fatal=1"),
        ):
            # Recompute the prefix identity so semantic checks, not merely
            # the archive hash mismatch, reject the altered history.
            bad_text = text.replace(old, new, 1)
            prefix = bad_text[:bad_text.index("kd_parallel resume: lane=1 ")]
            bad = copy.deepcopy(evidence)
            bad["after_exit"].update(log_bytes=len(prefix.encode()),
                                     log_sha256=hashlib.sha256(prefix.encode()).hexdigest())
            with self.subTest(old=old), self.assertRaises(AssertionError):
                validate_waiter_signals(bad_text, bad, clients, statuses, 0)
        for bad_clients, bad_status in (
            ([clients[0] + "parallel waiter client return\n", clients[1]], statuses),
            ([clients[0], clients[1].replace("signals=1", "signals=0")], statuses),
            (clients, statuses.replace("137", "0")),
            (clients, statuses.replace("137", "124")),
            (clients, statuses + "\n4\t137"),
        ):
            with self.subTest(clients=bad_clients, status=bad_status), self.assertRaises(AssertionError):
                validate_waiter_signals(text, evidence, bad_clients, bad_status, 0)

    def test_controller_checks_real_client_contract_before_sending(self):
        # Only proc/device/pidfd/signal primitives are substituted. Exercise
        # the delivered controller, including both handle lifetimes and gate
        # release on pre-send identity failure or missing post-send exit.
        from source_retirement import source

        for first, corrupt in [(0, ""), (1, "")] + [
            (0, name) for name in ("comm", "argv", "threads", "exe", "frames", "exited", "no-exit")
        ]:
            with self.subTest(first=first, corrupt=corrupt), tempfile.TemporaryDirectory() as temp:
                out = Path(temp)
                client = out / "mutex-signal-client"
                client.write_bytes(b"test client")
                text, expected, clients, statuses = waiter_signal_fixture(first)
                for lane, log in enumerate(clients):
                    (out / f"role-{lane}-2.log").write_text(log.splitlines()[0] + "\n")
                original_text, original_bytes, original_resolve, original_write = (
                    Path.read_text, Path.read_bytes, Path.resolve, Path.write_text
                )
                released = []

                def read_text(path, *args, **kwargs):
                    if str(path).startswith("/sys/"):
                        return "Y\n"
                    if str(path).startswith("/proc/"):
                        if path.name == "comm":
                            return "klock_test\n" if corrupt == "comm" else "kd_renamed\n"
                        if path.name == "status":
                            return f"Tgid:\t{path.parent.name}\nThreads:\t{2 if corrupt == 'threads' else 1}\n"
                    return original_text(path, *args, **kwargs)

                def read_bytes(path, *args, **kwargs):
                    if str(path).startswith("/proc/") and path.name == "cmdline":
                        lane = int(path.parent.name) - 20
                        args = [str(client), str(lane), "klock_test",
                                "parallel-peer" if corrupt == "argv" else "parallel-waiter"]
                        return b"\0".join(os.fsencode(a) for a in args) + b"\0"
                    return original_bytes(path, *args, **kwargs)

                def resolve(path, *args, **kwargs):
                    if str(path).startswith("/proc/") and path.name == "exe":
                        return out / "wrong" if corrupt == "exe" else client
                    return original_resolve(path, *args, **kwargs)

                def write_text(path, value, *args, **kwargs):
                    if str(path).startswith("/sys/"):
                        released.append((path.name, value))
                        return len(value)
                    return original_write(path, value, *args, **kwargs)

                def selected(handles, writes, errors, timeout):
                    ready = handles if (
                        corrupt == "exited" or (timeout == 10 and corrupt != "no-exit")
                    ) else []
                    return ready, [], []

                before = dict(expected["source"]["before"])
                if corrupt == "frames":
                    before["frames"] = 1
                initial = text[:text.index(f"kd_parallel resume: lane={first} ")]
                after = text.encode()[:expected["after_exit"]["log_bytes"]].decode()
                with (
                    patch("mutex_parallel_signals.os.open", return_value=90),
                    patch("mutex_parallel_signals.os.close") as close,
                    patch.object(source, "info", side_effect=[before, before, expected["source"]["after_exit"]]),
                    patch("mutex_parallel_signals.subprocess.check_output", side_effect=[initial, after]),
                    patch("mutex_parallel_signals.os.pidfd_open", side_effect=[77, 78]) as opened,
                    patch("mutex_parallel_signals.select.select", side_effect=selected),
                    patch("mutex_parallel_signals.signal.pidfd_send_signal") as send,
                    patch.object(Path, "read_text", read_text),
                    patch.object(Path, "read_bytes", read_bytes),
                    patch.object(Path, "resolve", resolve),
                    patch.object(Path, "write_text", write_text),
                    # Path.touch also uses os.open/close. Substitute this
                    # separate readiness file so it cannot alias the mocked
                    # source descriptor, and assert the handshake explicitly.
                    patch.object(Path, "touch", autospec=True) as ready,
                ):
                    if corrupt:
                        with self.assertRaises(AssertionError):
                            signal_original_waiters(out, first)
                        self.assertEqual(send.call_count, 2 if corrupt == "no-exit" else 0)
                    else:
                        signal_original_waiters(out, first)
                        self.assertEqual(
                            [c.args for c in send.call_args_list],
                            [(77, 9 if first == 0 else 10, None, 0),
                             (78, 9 if first == 1 else 10, None, 0)],
                        )
                        saved = json.loads((out / "waiter-signals.json").read_text())
                        validate_waiter_signals(text, saved, clients, statuses, first)
                    self.assertEqual(close.call_count, 1 + opened.call_count)
                    self.assertEqual(released, [("mutex_parallel_exit_hold", "0\n")])
                    if not corrupt or corrupt == "no-exit":
                        ready.assert_called_once_with(out / "waiter-signals.ready")
                    else:
                        ready.assert_not_called()
