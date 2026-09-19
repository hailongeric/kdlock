"""One native/kdlock session: prepare, measure, validate and drain.

Keep promotion and publication outside measurement. Only successful caller
exit plus explicit drain permits retirement/unload; unsafe failures stop here.
"""
import fcntl
import json
import os
import re
import subprocess
import time
from pathlib import Path

from summarize import write_json
from bench_runtime import (
    ROOT, HERE, WORKLOAD, PROVIDER, Failure, require, command, digest,
    status, parameters, registry, children, validate_measurement, classify_bodies,
    info, RETIRE, FAULT,
)


class Session:
    def __init__(self, out, spec, *, workload_module=None):
        self.workload_module = workload_module or WORKLOAD / "spin_cacheline.ko"
        self.path = out / spec["name"]
        self.path.mkdir()
        self.record = dict(spec, schema=1, execution_status="PREPARING", drained=False)
        self.daemon = None
        self.daemon_log = None
        self.loaded_source = self.loaded_kd = False
        self.kmsg = os.open("/dev/kmsg", os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        os.lseek(self.kmsg, 0, os.SEEK_END)
        self.messages = ""
        self.save()

    def save(self):
        write_json(self.path / "session.json", self.record)

    def faults(self):
        try:
            while True:
                raw = os.read(self.kmsg, 1 << 20)
                self.messages += raw.decode(errors="replace") + "\n"
        except BlockingIOError:
            pass
        except OSError as error:
            raise Failure("KERNEL_LOG_LOST", str(error), unsafe=True) from error
        (self.path / "kernel.log").write_text(self.messages)
        if FAULT.search(self.messages):
            raise Failure("KERNEL_FAULT", "kernel fault/error; retain modules and stop",
                          unsafe=True)

    def run(self, args, log, **kwargs):
        return command(args, self.path / log, **kwargs)

    def counts(self, label):
        return json.loads(self.run([HERE / "client", "--counts"], f"{label}.counts.json"))

    def phase(self, label, iterations, *, spec=None):
        # A comparator may prepare an entry with one CPU before measuring
        # contention. Validate against that phase's explicit worker geometry.
        spec = self.record if spec is None else spec
        args = [HERE / "client", "--cachelines", self.record["cachelines"],
                "--iterations", iterations, "--cpus", ",".join(map(str, spec["cpus"]))]
        try:
            raw = self.run(args, f"{label}.json", timeout=120)
        except Failure as error:
            if not error.unsafe:
                error.status = "DATA_ERROR"
            raise
        self.faults()
        m = json.loads(raw)
        validate_measurement(m, spec, iterations)
        require(self.counts(label)["active"] == 0, "workers did not drain", "UNDRAINED")
        return m

    def start_daemon(self):
        # The daemon and hostcall manifest use fixed relative sibling paths.
        # Both point at frozen inputs, without touching existing workspaces.
        workspace = self.path / "workspace"
        (workspace / "daemon").mkdir(parents=True)
        for directory in ("disassem", "include"):
            (workspace / directory).symlink_to(self.path.parent / "source" / directory,
                                               target_is_directory=True)
        self.daemon_log = (self.path / "daemon.log").open("w")
        env = dict(os.environ, KD_JIT_BODY_WITNESS="1")
        env.pop("KD_DEVICE_FD", None)
        self.daemon = subprocess.Popen([ROOT / "daemon/daemon", "--quiet", "--metrics",
                                        "--mode", "per-tgid"], cwd=workspace / "daemon",
                                       env=env, stdout=self.daemon_log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
        self.record["daemon_pid"] = self.daemon.pid
        self.save()

    def stop_daemon(self):
        if self.daemon is None:
            return
        require(not children(self.daemon.pid), "translator has not exited", "UNDRAINED")
        if self.daemon.poll() is None:
            self.daemon.terminate()
            try:
                self.daemon.wait(timeout=10)
            except subprocess.TimeoutExpired as error:
                raise Failure("UNDRAINED", "daemon did not exit", unsafe=True) from error
        self.daemon_log.close()
        self.daemon = None

    def publication(self):
        """Check a stable NORMAL entry and its image; actual execution is separate."""
        r = registry()
        require(len(r) == 1 and r[0]["status"] == 0 and r[0]["pid"] == 0 and
                r[0]["lock_kind"] == 1 and r[0]["code"] != 0, "entry is not NORMAL")
        entry = r[0]
        if "caller_abi" in self.record:
            require(entry["entry_abi"] == (self.record["caller_abi"] == "clobber"),
                    "published entry has the wrong caller ABI")
        begin, end = self.record["entry_range"]
        require(begin <= entry["entry"] < end, "published entry belongs to another CS")
        folder = (self.path / "workspace/daemon" / hex(entry["entry"]) /
                  str(entry["tgid"]) / "asm")
        image, assembly, disassembly = folder / "jit.bin", folder / "jit.S", folder / "bin.txt"
        require(image.exists() and 0 < image.stat().st_size <= 640 * 1024 and
                assembly.exists() and disassembly.is_file() and disassembly.stat().st_size > 0,
                "invalid/missing generated image or disassembly")
        text = assembly.read_text()
        require("MOV             Stack_JIT_WITNESS, 1" in text and
                f"loc_{entry['entry']:x}:" in text, "image lacks entry/body marker")
        state = status()
        require(state["state"] == 0 and state["frames"] == 0,
                "source is not OPEN/drained", "UNDRAINED")
        return dict(entry=entry, source=state,
                    # Hash the inspection disassembly at the same boundaries;
                    # exporting it later never adds I/O to the measured batch.
                    images={p.name: digest(p) for p in (image, assembly, disassembly)})

    def prepare(self):
        """Load fresh state, promote naturally and wait for translator exit."""
        self.run(["insmod", self.workload_module], "load-source.log")
        self.loaded_source = True
        layout = json.loads(self.run([HERE / "client", "--layout"], "layout.json"))
        self.record["layout"] = layout
        require(self.counts("initial")["values"] == [0] * 16, "source was not reset")
        if self.record["arm"] == "kdlock":
            self.run(["insmod", PROVIDER,
                      "target_process=sc_worker", "bench_quiet=1", "jit_timing=0",
                      f"bench_lock_addr={layout['lock_addr']}"], "load-kdlock.log")
            self.loaded_kd = True
            params = parameters()
            self.record["parameters"] = params
            require(params["bench_quiet"] == "Y" and params["jit_timing"] == "N" and
                    int(params["bench_lock_addr"]) == layout["lock_addr"],
                    "loaded observation parameters differ")
            require("spin_selftest_promote" not in params, "SELFTEST provider is forbidden")
            symbol = f"sc_body_{self.record['cachelines']}"
            symbols = [line.split() for line in Path("/proc/kallsyms").read_text().splitlines()]
            found = [int(s[0], 16) for s in symbols if len(s) == 4 and
                     s[2:] == [symbol, "[spin_cacheline]"]]
            nm = self.run(["nm", "-S", self.workload_module], "symbols.txt")
            sizes = [int(s[1], 16) for line in nm.splitlines()
                     if len(s := line.split()) == 4 and s[3] == symbol]
            require(len(found) == len(sizes) == 1 and found[0] != 0, "unknown CS symbol")
            self.record["entry_range"] = [found[0], found[0] + sizes[0]]
            self.start_daemon()
        else:
            require(not Path("/sys/module/kdlock_km").exists(), "native arm has kdlock loaded")
        self.phase("warmup", 1)
        # CPU admission is frequency-based; keep lock samples consecutive.
        self.phase("promotion", 48000)
        if self.loaded_kd:
            deadline = time.monotonic() + 90
            while True:
                self.faults()
                require(self.daemon.poll() is None, "daemon exited during preparation")
                log = (self.path / "daemon.log").read_text()
                require(not re.search(r"\[KD_JIT\]\[ERROR\]|Traceback|command failed", log),
                        "translator failed; see daemon.log")
                metrics = [json.loads(line.split(" ", 1)[1]) for line in log.splitlines()
                           if line.startswith("KD_TRANSLATION_METRICS ")]
                require(all(m["result"] == 0 and m["status"] == 0 for m in metrics),
                        "translation failed or refused")
                r = registry()
                require(all(e["status"] in (-1, 0) for e in r), "unexpected entry state")
                if len(r) == 1 and r[0]["status"] == 0 and metrics and not children(self.daemon.pid):
                    self.record["translation"] = metrics
                    self.publication()
                    break
                if time.monotonic() >= deadline:
                    raise Failure("TIMEOUT", "natural promotion/publication timed out",
                                  unsafe=True)
                time.sleep(0.1)
            self.stop_daemon()
            require(status()["writers"] == 0, "translator writer still open", "UNDRAINED")
        time.sleep(2)  # Same fixed post-preparation settling in each arm.
        self.record["prepared_ns"] = time.monotonic_ns()
        self.save()

    def measure(self):
        """Count returned JIT bodies only across the joined measurement batch."""
        if self.loaded_kd:
            before = self.publication()
            require(before["source"]["writers"] == 0, "writers before measurement", "UNDRAINED")
            count_path = Path("/sys/module/kdlock_km/parameters/bench_jit_bodies")
            self.record["jit_before"] = int(count_path.read_text())
            self.record["published_before"] = before
        self.record["execution_status"] = "MEASURING"
        self.save()
        self.record["measurement"] = self.phase("measure", self.record["iterations"])
        if self.loaded_kd:
            self.record["jit_after"] = int(count_path.read_text())
            after = self.publication()
            self.record["published_after"] = after
            require(before == after, "publication changed during measurement")
            self.record.update(classify_bodies(self.record["jit_before"], self.record["jit_after"],
                                              self.record["measurement"]["completed"]))
        else:
            require(not Path("/sys/module/kdlock_km").exists(), "kdlock appeared in native arm")
            self.record.update(jit_bodies=0, jit_share=0, jit_status="NATIVE")
        self.save()

    def cleanup(self):
        """Retire only after caller/frame drain, then unload without forcing."""
        # Caller processes have joined/exited before this boundary. No cleanup
        # is attempted on timeouts or kernel faults, even if the PID disappeared.
        self.faults()
        if self.loaded_source:
            require(self.counts("drain")["active"] == 0, "active workers", "UNDRAINED")
        if self.loaded_kd:
            require(status()["frames"] == 0, "active frames", "UNDRAINED")
            self.stop_daemon()
            state = status()
            require(state["frames"] == state["writers"] == 0, "active frames/writers", "UNDRAINED")
            fd = os.open("/dev/kd_dev", os.O_RDONLY | os.O_CLOEXEC)
            try:
                # Retirement checks the existing queue/task/origin ledgers too.
                fcntl.ioctl(fd, RETIRE)
                self.record["retired"] = info(fd)
            except OSError as error:
                raise Failure("UNDRAINED", f"retirement refused: {error}", unsafe=True) from error
            finally:
                os.close(fd)
            require(self.record["retired"] == dict(state=2, modules=0, frames=0, writers=0),
                    "retirement incomplete", "UNDRAINED")
        if self.loaded_source:
            self.run(["rmmod", "spin_cacheline"], "unload-source.log")
            self.loaded_source = False
        if self.loaded_kd:
            self.run(["rmmod", "kdlock_km"], "unload-kdlock.log")
            self.loaded_kd = False
        self.faults()
        self.record["drained"] = True

    def execute(self):
        try:
            self.prepare()
            self.measure()
            self.cleanup()
            self.record["execution_status"] = "OK"
        except (Failure, OSError, ValueError, KeyError) as error:
            failure = error if isinstance(error, Failure) else Failure("PREPARATION_FAILED", str(error))
            self.record.update(execution_status=failure.status, error=str(failure))
            self.save()
            if not failure.unsafe and failure.status != "UNDRAINED":
                try:
                    self.cleanup()
                except (Failure, OSError) as cleanup_error:
                    self.record["cleanup_error"] = str(cleanup_error)
            raise failure
        finally:
            self.record["finished_ns"] = time.monotonic_ns()
            self.save()
            os.close(self.kmsg)
