"""Directed guest tests: real payload/client, accounting and scan classification."""
import argparse
import copy
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import run
import summarize
import profile_summary
from provider.prepare import prepare, production_files, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests/unit/infrastructure"))
from source_text import read_source

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORKLOAD = ROOT / "workload_modules/spin_cacheline"


class CachelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="spin-cacheline-units-")
        cls.out = Path(cls.temp.name)
        cls.provider = cls.out / "provider"
        cls.provider_manifest = prepare(cls.provider)
        cls.binary = cls.out / "client-fixture"
        subprocess.run(["cc", "-O2", "-Wall", "-Wextra", "-Werror", "-std=gnu11",
                        "-pthread", str(HERE / "client_fixture.c"), "-o", str(cls.binary)],
                       check=True, timeout=30)
        cls.cpus = sorted(os.sched_getaffinity(0))[:2]
        if len(cls.cpus) != 2:
            raise RuntimeError("two available guest CPUs required")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def client(self, n=2, fault=None, cpus=None, iterations=1000, api_counts=False):
        env = dict(os.environ)
        env.pop("SC_FIXTURE_FAULT", None)
        env.pop("SC_FIXTURE_COUNTS", None)
        if fault:
            env["SC_FIXTURE_FAULT"] = fault
        if api_counts:
            env["SC_FIXTURE_COUNTS"] = "1"
        return subprocess.run([str(self.binary), "--cachelines", str(n), "--iterations", str(iterations),
                               "--cpus", ",".join(map(str, self.cpus if cpus is None else cpus))],
                              capture_output=True, text=True, env=env, timeout=10)

    def test_one_ioctl_batch_and_constant_clock_calls(self):
        # Count actual calls from the client in the substitute device. This is
        # an API budget check, not syscall tracing or a clock-overhead estimate.
        for threads in (1, 2):
            cpus = self.cpus[:threads]
            for iterations in (1, 10000, 100000):
                with self.subTest(threads=threads, iterations=iterations):
                    result = self.client(cpus=cpus, iterations=iterations, api_counts=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    run.validate_measurement(json.loads(result.stdout),
                                             dict(cachelines=2, threads=threads, cpus=cpus), iterations)
                    self.assertEqual(json.loads(result.stderr), dict(
                        layout=1, counts=2, run=threads,
                        submitted_iterations=threads * iterations,
                        monotonic=threads + 1, thread_cputime=2 * threads))

    def test_post_work_survives_unused_result_without_memory_or_calls(self):
        binary = self.out / "post-work-fixture"
        subprocess.run(["cc", "-O2", "-Wall", "-Wextra", "-Werror", "-std=gnu11",
                        str(HERE / "post_work_fixture.c"), "-o", str(binary)],
                       check=True, timeout=30)
        subprocess.run([str(binary)], check=True, timeout=10)
        assembly = subprocess.check_output(
            ["objdump", "-d", "--no-show-raw-insn", "--disassemble=fixture_discard", str(binary)],
            text=True, timeout=10)
        instructions = re.findall(r"^\s*[0-9a-f]+:\s+(.*)$", assembly, re.MULTILINE)
        alu = [line for line in instructions if line.startswith(("imul", "add"))]
        self.assertEqual(sum(line.startswith("imul") for line in alu), 4, assembly)
        self.assertEqual(sum(line.startswith("add") for line in alu), 4, assembly)
        self.assertTrue(all("(" not in line for line in alu), assembly)
        self.assertFalse(any(line.startswith(("call", "pause", "j")) for line in instructions), assembly)

    def test_selected_kernel_bundle_rejects_corrupt_identity(self):
        # Selecting an experimental bundle must still use the existing file
        # verifier; a CLI override must not turn a bad identity into a pass.
        parser = argparse.ArgumentParser()
        run.kernel_identity.arguments(parser)
        defaults = parser.parse_args([])
        self.assertEqual(defaults.kernel_source, Path('/root/linux-6.1.159'))
        self.assertEqual(defaults.kernel_baseline, ROOT / 'kernel_baseline')
        with tempfile.TemporaryDirectory(prefix='spin-kernel-identity-') as directory:
            bundle = Path(directory) / 'bundle'
            shutil.copytree(ROOT / 'kernel_baseline', bundle)
            with (bundle / 'guest.config').open('a') as stream:
                stream.write('\n# deliberately corrupt captured identity\n')
            with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
                run.kernel_identity.check(defaults.kernel_source, bundle)

    def test_profile_weights_bound_symbols_and_keep_unknown_ips(self):
        ranges = profile_summary.symbol_ranges(
            '1000 T alpha\n2000 t beta [kdlock_km]\n',
            '0000 0020 t beta\n', 'kdlock_km')
        self.assertEqual(ranges, [(0x2000, 0x2020, 'kdlock_km:beta')])
        duplicated = profile_summary.symbol_ranges(
            '2000 t beta [kdlock_km]\n2040 t beta [kdlock_km]\n',
            '0000 0020 t beta\n0040 0010 t beta\n', 'kdlock_km')
        self.assertEqual(duplicated, ranges + [(0x2040, 0x2050, 'kdlock_km:beta')])
        result = profile_summary.aggregate(
            'client 999 2001\nsc_worker 10 2001\nsc_worker 30 201f\n'
            'sc_worker 20 2020\nsc_worker 40 9000\n',
            ranges + [(0x2004, 0x2008, 'kdlock_km:inner_asm'),
                      (0x9000, 0x9010, 'generated:jit_image')])
        self.assertEqual(result['worker_samples'], 4)
        self.assertEqual(result['total_sampled_period'], 100)
        weights = {r['symbol']: r['sample_weight_percent'] for r in result['symbols']}
        self.assertEqual(weights, {'kdlock_km:beta': 40, 'unresolved': 20, 'generated:jit_image': 40})
        with self.assertRaisesRegex(ValueError, 'no worker samples'):
            profile_summary.aggregate('client 10 2000\n', ranges)

    def test_five_payloads_and_actual_client(self):
        for n in (1, 2, 4, 8, 16):
            with self.subTest(cachelines=n):
                result = self.client(n)
                self.assertEqual(result.returncode, 0, result.stderr)
                m = json.loads(result.stdout)
                run.validate_measurement(m, dict(cachelines=n, threads=2, cpus=self.cpus), 1000)
                self.assertEqual(m["before"], list(range(100, 116)))
                self.assertEqual(m["after"], [100 + i + (2000 if i < n else 0) for i in range(16)])

    def test_client_rejects_corruption(self):
        for fault in ("active", "inactive", "completed", "layout"):
            with self.subTest(fault=fault):
                result = self.client(fault=fault)
                self.assertEqual(result.returncode, 1, result.stdout)
                if fault != "layout":
                    self.assertFalse(json.loads(result.stdout)["complete"])

    def test_atomic_start_gate_and_setup_failures(self):
        available = sorted(os.sched_getaffinity(0))
        self.assertGreaterEqual(len(available), 24, "24 available guest CPUs required")
        for threads in (1, 24):
            cpus = available[:threads]
            result = self.client(fault="slow_ready", cpus=cpus)
            self.assertEqual(result.returncode, 0, result.stderr)
            run.validate_measurement(json.loads(result.stdout),
                                     dict(cachelines=2, threads=threads, cpus=cpus), 1000)
        for fault in ("create", "affinity"):
            with self.subTest(fault=fault):
                result = self.client(fault=fault)
                self.assertEqual(result.returncode, 1, result.stderr)
                m = json.loads(result.stdout)
                self.assertFalse(m["complete"])
                self.assertTrue(m["data_ok"])
                self.assertEqual(m["completed"], 0)
                self.assertEqual(m["worker_cpu_ns"], 0)
                self.assertEqual(m["before"], m["after"])

    def test_atomic_admission_excludes_snapshots(self):
        module = (WORKLOAD / "module.c").read_text()
        start = module.index("static atomic_t sc_control")
        end = module.index("static long sc_ioctl", start)
        (self.out / "control.inc").write_text(module[start:end])
        binary = self.out / "control-fixture"
        subprocess.run(["cc", "-O2", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                        "-pthread", "-I", str(self.out), str(HERE / "control_fixture.c"),
                        "-o", str(binary)], check=True, timeout=30)
        subprocess.run([str(binary)], check=True, timeout=10)

    def test_aggregator_rejects_wrong_totals_and_affinity(self):
        m = json.loads(self.client().stdout)
        spec = dict(cachelines=2, threads=2, cpus=self.cpus)
        for key in ("completed", "wall_ns", "worker_cpu_ns"):
            changed = copy.deepcopy(m)
            changed[key] += 1
            with self.assertRaises(run.Failure):
                run.validate_measurement(changed, spec, 1000)
        m["workers"][0]["observed_cpu"] = self.cpus[1]
        with self.assertRaises(run.Failure):
            run.validate_measurement(m, spec, 1000)

    def test_plan_order_and_arguments(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(run.main(["--dry-run"]), 0)
        plan, end = json.JSONDecoder().raw_decode(output.getvalue())
        self.assertEqual(output.getvalue()[end:].strip(), "35 configurations, 140 sessions")
        self.assertEqual(len(plan), 140)
        self.assertEqual(len({s["name"] for s in plan}), 140)
        self.assertEqual(list(dict.fromkeys(s["threads"] for s in plan)), [1, 4, 8, 12, 16, 20, 24])
        self.assertEqual([s["arm"] for s in plan], ["native", "kdlock", "kdlock", "native"] * 35)
        for s in plan:
            self.assertEqual(s["cpus"], list(range(s["threads"])))
        run.annotate_topology(plan, dict(role_cpus=list(range(24)), role_nodes=[0] * 20 + [1] * 4))
        for s in plan:
            expected = ([0] * s["threads"] if s["threads"] <= 20 else [0] * 20 + [1] * 4)
            self.assertEqual(s["cpu_nodes"], expected)
            self.assertEqual(summarize.placement(s)["numa_scope"],
                             "cross_node" if s["threads"] == 24 else "single_node")
        with self.assertRaises(run.Failure):
            run.make_plan([1], [24], 10000, 2, list(range(23)))
        for repeat in (0, 1, 3, -2):
            with self.assertRaises(run.Failure):
                run.make_plan([1], [2], 10000, repeat, [0, 1])
        for cpus in ("0,0", "0-2,2", "2-0", "1024", "0,x"):
            with self.assertRaises(argparse.ArgumentTypeError):
                run.cpu_list(cpus)
        self.assertEqual(run.cpu_list("4,0-2"), [4, 0, 1, 2])

    def test_no_jit_and_pair_ratios(self):
        self.assertEqual(run.classify_bodies(900, 900, 2000),
                         dict(jit_bodies=0, jit_share=0, jit_status="NO_JIT"))
        self.assertEqual(run.classify_bodies(900, 1100, 2000)["jit_share"], 0.1)
        for before, after in ((2, 1), (0, 2001)):
            with self.assertRaises(run.Failure):
                run.classify_bodies(before, after, 2000)
        n = dict(run.make_plan([2], [2], 1000, 2, self.cpus)[0],
                 execution_status="OK", drained=True, measurement=json.loads(self.client().stdout))
        k = copy.deepcopy(n)
        k.update(arm="kdlock", jit_status="NO_JIT", jit_bodies=0)
        k["measurement"]["wall_ns"] *= 2
        self.assertEqual(summarize.pair_ratio(n, k), 0.5)
        with self.assertRaisesRegex(ValueError, "NUMA nodes differ"):
            summarize.pair_ratio(dict(n, cpu_nodes=[0, 0]), dict(k, cpu_nodes=[0, 1]))
        for changes in (dict(drained=False), dict(execution_status="PREPARATION_FAILED")):
            self.assertIsNone(summarize.pair_ratio(n, dict(k, **changes)))
        k["measurement"]["data_ok"] = False
        self.assertIsNone(summarize.pair_ratio(n, k))

    def test_csv_medians_missing_pairs_and_jit_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            plan = run.make_plan([2], [2], 1000, 2, self.cpus)
            run.annotate_topology(plan, dict(role_cpus=self.cpus, role_nodes=[0, 1]))
            summarize.write_json(out / "plan.json", plan)
            measurement = json.loads(self.client().stdout)
            for spec in plan:
                path = out / spec["name"]
                path.mkdir()
                m = copy.deepcopy(measurement)
                if spec["arm"] == "kdlock":
                    m["wall_ns"] *= (2 if spec["repeat"] == 0 else 0.5)
                summarize.write_json(path / "session.json", dict(
                    spec, measurement=m, execution_status="OK", drained=True,
                    jit_status="NO_JIT" if spec["arm"] == "kdlock" else "NATIVE",
                    jit_bodies=0, jit_share=0))
            with contextlib.redirect_stdout(io.StringIO()):
                result = summarize.summarize(out)
            row = result["configurations"][0]
            self.assertEqual(row["median_kdlock_over_native"], 1.25)
            self.assertEqual(row["best_kdlock_over_median_native"], 2)
            self.assertEqual(row["best_kdlock_session"], plan[2]["name"])
            self.assertEqual(row["best_kdlock_jit_status"], "NO_JIT")
            self.assertEqual(row["no_jit_sessions"], 2)
            self.assertEqual(row["numa_nodes"], "0,1")
            self.assertEqual(row["numa_scope"], "cross_node")
            self.assertEqual(summarize.placement({})["numa_scope"], "unknown")
            self.assertFalse(result["all_sizes_jit_verified"])
            (out / plan[-1]["name"] / "session.json").unlink()
            with contextlib.redirect_stdout(io.StringIO()):
                result = summarize.summarize(out)
            self.assertEqual(result["completed"], 3)
            self.assertEqual(result["configurations"][0]["valid_pairs"], 1)
            self.assertEqual(result["configurations"][0]["median_kdlock_over_native"], 0.5)

    def test_best_comparison_uses_native_median_and_excludes_invalid_fast_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            plan = run.make_plan([2], [2], 1000, 2, self.cpus)
            summarize.write_json(out / "plan.json", plan)
            measurement = json.loads(self.client().stdout)
            for spec, wall in zip(plan, (400, 250, 200, 100)):
                path = out / spec["name"]
                path.mkdir()
                m = dict(measurement, wall_ns=wall)
                jit = spec["arm"] == "kdlock"
                bodies = (100 if spec["repeat"] == 0 else 40) if jit else 0
                summarize.write_json(path / "session.json", dict(
                    spec, measurement=m, execution_status="OK", drained=True,
                    jit_status="JIT" if jit else "NATIVE",
                    jit_bodies=bodies, jit_share=bodies / measurement["completed"]))

            def summary():
                with contextlib.redirect_stdout(io.StringIO()):
                    return summarize.summarize(out)

            result = summary()
            row = result["configurations"][0]
            self.assertEqual(result["comparison_policy"], "best_kdlock_over_median_native")
            self.assertAlmostEqual(row["best_kdlock_over_median_native"], 0.8)
            self.assertAlmostEqual(row["median_kdlock_over_native"], 1.05)
            self.assertEqual(row["best_kdlock_session"], plan[2]["name"])
            self.assertEqual(row["best_kdlock_jit_bodies"], 40)
            self.assertEqual(row["best_kdlock_jit_share"], 0.02)
            self.assertEqual(row["valid_native_sessions"], 2)
            self.assertEqual(row["valid_kdlock_sessions"], 2)
            fastest = out / plan[2]["name"] / "session.json"
            original = json.loads(fastest.read_text())
            for change in (dict(drained=False), dict(execution_status="KERNEL_FAULT"),
                           dict(measurement=dict(original["measurement"], data_ok=False)),
                           dict(measurement=dict(original["measurement"], complete=False))):
                summarize.write_json(fastest, dict(original, **change))
                row = summary()["configurations"][0]
                self.assertEqual(row["best_kdlock_session"], plan[1]["name"])
                self.assertEqual(row["valid_kdlock_sessions"], 1)
                self.assertAlmostEqual(row["best_kdlock_over_median_native"], 0.64)
            summarize.write_json(fastest, original)
            # A bad paired native does not invalidate another, independent
            # baseline sample, but its time cannot enter that median.
            for spec in (plan[0], plan[3]):
                (out / spec["name"] / "session.json").unlink()
            row = summary()["configurations"][0]
            self.assertIsNone(row["best_kdlock_over_median_native"])
            self.assertEqual(row["valid_native_sessions"], 0)
            self.assertEqual(row["best_kdlock_session"], plan[2]["name"])
            # Reject even an incomplete plan that combines differently sized
            # batches into one best/median comparison.
            plan[2]["iterations"] += 1
            summarize.write_json(out / "plan.json", plan)
            with self.assertRaisesRegex(ValueError, "different iterations"):
                summary()

    def test_provider_isolation_and_incompatible_source(self):
        manifest = self.provider_manifest
        self.assertTrue(manifest["complete"])
        base = {str(p): digest(ROOT / p) for p in production_files(ROOT)}
        self.assertEqual(manifest["production"], base)
        changed = {p for p, sha in base.items() if manifest["prepared"][p] != sha}
        self.assertEqual(changed, {
            'include/utils.h',
            'kernel_module/Makefile',
            'kernel_module/exe.c',
            'kernel_module/execution/native.inc',
            'kernel_module/execution/remote.inc',
            'kernel_module/kd_exec.c',
            'kernel_module/kd_mutex.c',
            'kernel_module/kd_spinlock.c',
            'kernel_module/mutex/combiner.inc',
            'kernel_module/spin/combiner.inc',
        })
        self.assertEqual(set(manifest["prepared"]) - set(base),
                         {"include/kd_bench.h", "kernel_module/kd_bench.c"})
        self.assertNotIn("kd_bench", (ROOT / "kernel_module/Makefile").read_text())
        self.assertNotIn("kd_bench", (ROOT / "include/utils.h").read_text())
        # A project update that no longer matches the observation context must
        # fail before a benchmark provider is built, without touching that base.
        incompatible = self.out / "incompatible-base"
        for relative in production_files(ROOT):
            target = incompatible / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        utils = incompatible / "include/utils.h"
        utils.write_text(utils.read_text().replace("pr_info(", "trace_info("))
        before = digest(utils)
        with self.assertRaisesRegex(RuntimeError, "overlay failed"):
            prepare(self.out / "incompatible-provider", incompatible)
        self.assertEqual(digest(utils), before)

    def test_default_quiet_and_returned_body_counter(self):
        def stripped(path):
            return re.sub(r'^#include[^\n]*\n', '', path.read_text(), flags=re.M)
        # Compile the real observation helper, sysfs getter, log macros and
        # dispatcher witness block; CPU/log primitives alone are substituted.
        exe = read_source(self.provider / "kernel_module/exe.c")
        start = exe.index("if (!body_reported && args[1] == 1) {")
        end = exe.index("\n\t\t\tif (resume_after_hostcall)", start)
        block = exe[start:end]
        self.assertLess(exe.index("translated(regs, args);", exe.index("bool body_reported")), start)
        source = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stddef.h>
typedef uint64_t u64;
static int cpu, logs;
struct kernel_param { int unused; };
struct kernel_param_ops { int (*get)(char *, const struct kernel_param *); };
#define module_param_named(name, var, type, mode) _Static_assert(mode == 0444, "read only")
#define MODULE_PARM_DESC(name, text)
#define module_param_cb(name, ops, arg, mode) _Static_assert(mode == 0444, "read only")
#define DECLARE_PER_CPU(type, name) extern type name[3]
#define DEFINE_PER_CPU(type, name) type name[3]
#define per_cpu(name, id) name[id]
#define this_cpu_inc(name) (++name[cpu])
#define for_each_possible_cpu(id) for (id = 0; id < 3; id++)
#define READ_ONCE(x) (x)
#define unlikely(x) (x)
#define PAGE_SIZE 4096
#define scnprintf snprintf
#define pr_info(...) do { logs++; if (0) printf(__VA_ARGS__); } while (0)
#define printk(...) pr_info(__VA_ARGS__)
#define KERN_INFO ""
#define smp_processor_id() cpu
'''
        source += stripped(self.provider / "include/kd_bench.h")
        source += stripped(self.provider / "kernel_module/kd_bench.c")
        source += stripped(self.provider / "include/utils.h")
        note_start = exe.index("static void kd_exe_note_body(")
        note_end = exe.index("\n}", note_start) + 2
        source += exe[note_start:note_end] + "\n"
        source += "\nstatic bool observe(unsigned long outer_lock_addr, unsigned long marker, bool body_reported) {\n"
        source += "unsigned long args[2] = {0, marker}; unsigned long entry_ip = 123;\n" + block
        source += "\nreturn body_reported; }\n"
        spin = read_source(self.provider / "kernel_module/kd_spinlock.c")
        start = spin.index("if (exe_flag == KD_EXE_NO_RUN) {")
        end = spin.index("if (exe_flag != KD_EXE_NATIVE_DONE)", start)
        source += "\n#define KD_EXE_NO_RUN -1\n#define KD_EXE_RUN_ERROR -2\n"
        source += "static struct { void *next; } fallback_state;\n"
        # The unified combiner returns directly after recording its successor.
        # Keep the real void-return blocks and reject accidental fallthrough.
        source += "static void fallback_step(int exe_flag) { void *lock = NULL; "
        source += "void *next_node = NULL, *curr_node = (void *)1; __typeof__(fallback_state) *batch = &fallback_state;\n"
        source += spin[start:end]
        source += "\nassert(0); }\nstatic void fallback(int code) { fallback_state.next = NULL; fallback_step(code); assert(fallback_state.next == (void *)1); }\n"
        source += r'''
int main(void) {
    char buffer[4096]; void *lock = NULL; bool reported;
    (void)lock;
    assert(!kd_bench_quiet && !kd_bench_lock_addr);
    assert(observe(0x123, 1, false));
    assert(kd_bench_bodies[0] == 0 && logs == 1);
    kd_bench_lock_addr = 0x123;
    kd_bench_quiet = true;
    assert(!observe(0x123, 0, false));
    reported = observe(0x123, 1, false);
    assert(observe(0x123, 1, reported));
    assert(observe(0x456, 1, false));
    assert(kd_bench_bodies[0] == 1 && logs == 1);
    cpu = 2; assert(observe(0x123, 1, false));
    assert(kd_bench_bodies_ops.get(buffer, NULL) > 0 && !strcmp(buffer, "2\n"));
    KD_PR_DEBUG("routine"); KD_PR_ROUTINE("routine"); print_debug("routine");
    assert(logs == 1);
    KD_PR_ERR("error"); KD_PR_DEBUG_ALWAYS("error"); print_debug_always("error");
    assert(logs == 4);
    kd_bench_quiet = false;
    KD_PR_DEBUG("routine"); KD_PR_ROUTINE("routine"); print_debug("routine");
    assert(logs == 7);
    kd_bench_quiet = true;
    fallback(KD_EXE_NO_RUN); assert(logs == 7);
    fallback(KD_EXE_RUN_ERROR); assert(logs == 8);
    kd_bench_quiet = false;
    fallback(KD_EXE_NO_RUN); assert(logs == 9);
    return 0;
}
'''
        path = self.out / "observation.c"
        path.write_text(source)
        binary = self.out / "observation"
        subprocess.run(["cc", "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                        str(path), "-o", str(binary)], check=True, timeout=30)
        subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
