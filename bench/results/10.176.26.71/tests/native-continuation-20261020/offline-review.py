#!/usr/bin/env python3
"""Inspect inert continuation archives and committed Git objects on 380G10."""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True


def review(repo, raw):
    helper = repo / "bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/offline-review.py"
    spec = importlib.util.spec_from_file_location("archive_reader", helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    audit = module.Audit(SimpleNamespace(repo=repo, raw=raw, report=Path("/tmp/unused-report")))
    groups, links = audit.load_archives()
    audit.manifests()
    manifest = audit.jread("committed-source.json")
    revision = audit.revision(manifest["commit"])
    paths = audit.names(revision)
    for path, expected in manifest["files"].items():
        audit.check(path in paths and module.sha(audit.git_bytes(revision, path)) == expected,
                    "committed_source_git_hash", path)
    tasks = audit.jread("tasks.json")
    audit.check(tasks["source_commit"] == revision and
                module.sha(audit.contents["run-tasks.py"]) == tasks["script_sha256"],
                "task_runner_binding")
    cases = []
    for task in tasks["tasks"]:
        name = task["name"]
        original = name + "/source/"
        source = audit.jread(name + "/source-sha256.json")
        for path, expected in source.items():
            audit.check(manifest["files"].get(path) == expected, "source_manifest_binding", path)
        prepared = audit.jread(name + "/prepared-source-sha256.json")
        changes = audit.reconstruct(
            original, audit.contents[original + "bench/spin_cacheline/provider/observation.patch"])
        classes = Counter()
        for path, expected in prepared.items():
            if path in ("include/kd_bench.h", "kernel_module/kd_bench.c"):
                data = audit.contents[original + "bench/spin_cacheline/provider/" + Path(path).name]
                category = "overlay"
            elif path in changes:
                data, category = changes[path], "patched"
            else:
                data, category = audit.contents[original + path], "unchanged"
            audit.check(module.sha(data) == expected, "prepared_reconstructed_hash", name + "/" + path)
            classes[category] += 1
        audit.check(set(changes) <= set(prepared), "patch_targets_retained", name)
        session = audit.jread(name + "/session/session.json")
        audit.check(session["drained"] and session["retired"] ==
                    dict(state=2, modules=0, writers=0, frames=0), "exact_retirement", name)
        accepted = task["exit_code"] == 0
        if accepted:
            result = audit.jread(name + "/result.json")
            audit.check(result["passed"] and result["drained"] and
                        session["execution_status"] == "OK" and
                        result["phases"] == session["phases"], "accepted_result", name)
            audit.check([p["name"] for p in session["phases"]] ==
                        ["cold-warmup", "cold-delegated", "hot-escape", "post-ban"],
                        "complete_phase_order", name)
        else:
            failure = audit.jread(name + "/failure.json")
            audit.check(not failure["unsafe"] and
                        failure["status"] == session["execution_status"] and
                        name + "/result.json" not in audit.files, "failed_case_not_pass", name)
        phase_rows = []
        for phase in session.get("phases", []):
            tag = name + "/" + phase["name"]
            prefix = name + "/session/" + phase["name"]
            workers = phase["workers"]
            audit.check(phase["complete"] and not any(phase["returncodes"]) and
                        len(workers) == len(phase["returncodes"]) ==
                        len(phase["ready"]) == len(phase["callers"]), "phase_complete", tag)
            audit.check(phase["callers"] == audit.jread(prefix + "-callers.json"),
                        "caller_receipt", tag)
            for index, worker in enumerate(workers):
                expected = session["reader_iterations"] if worker["role"] == "reader" else phase["iterations"]
                audit.check(worker == audit.jread(prefix + "-worker-" + str(index) + ".json") and
                            worker["worker"] == index and worker["cpu"] == session["cpus"][index] and
                            worker["comm"] == "ke_worker" and worker["errors"] == 0 and
                            worker["reserved"] == [0, 0] and
                            worker["completed"] == worker["iterations"] == expected,
                            "worker_progress_receipt", tag + "/" + str(index))
                ready, caller = phase["ready"][index], phase["callers"][index]
                audit.check(ready == audit.jread(prefix + "-barrier/ready-" + str(index) + ".json") and
                            ready["pid"] == caller["pid"] and ready["cpu"] == caller["cpu"] ==
                            worker["cpu"] and ready["role"] == caller["role"] == worker["role"],
                            "worker_ready_identity", tag + "/" + str(index))
            before, after, delta = phase["before"], phase["after"], phase["jit_delta"]
            audit.check(before == audit.jread(prefix + "-before.counts.json") and
                        after == audit.jread(prefix + "-after.counts.json"), "phase_counts", tag)
            writes = sum(w["completed"] for w in workers if w["role"] == "writer")
            reads = sum(w["completed"] for w in workers if w["role"] == "reader")
            audit.check(writes == phase["write_operations"] == after["prefix"] - before["prefix"] ==
                        after["suffix"] - before["suffix"] and reads == phase["read_operations"] and
                        all(v["active"] == v["failures"] == 0 and v["idle"] == 1 for v in (before, after)),
                        "exact_business_effects", tag)
            audit.check(after["hot_taken"] - before["hot_taken"] == (writes if phase["hot"] else 0),
                        "exact_hot_effects", tag)
            audit.check(delta == {k: phase["counters_after"][k] - v
                                 for k, v in phase["counters_before"].items()}, "counter_arithmetic", tag)
            if accepted:
                if phase["name"] == "cold-delegated":
                    audit.check(delta["bench_jit_bodies"] == delta["bench_jit_completions"] > 0 and
                                delta["native_escape_count"] == 0, "cold_returned_bodies", tag)
                elif phase["name"] == "cold-warmup":
                    audit.check(delta["bench_jit_bodies"] == delta["bench_jit_completions"] and
                                delta["native_escape_count"] == 0, "warmup_complete_bodies", tag)
                elif phase["name"] == "hot-escape":
                    audit.check(delta == dict(bench_jit_bodies=1, bench_jit_completions=0,
                                              native_escape_count=1), "single_native_exit", tag)
                else:
                    audit.check(not any(delta.values()), "sticky_ban", tag)
            audit.check(phase["source_after"]["frames"] == 0, "phase_frames_drained", tag)
            phase_rows.append(dict(name=phase["name"], writes=writes, reads=reads, counters=delta))
        for filename, expected in session.get("publication", {}).get("images", {}).items():
            matches = [p for p in audit.files if p.startswith(name + "/session/workspace/") and
                       p.endswith("/" + filename)]
            audit.check(len(matches) == 1 and audit.files[matches[0]] == expected,
                        "publication_hash", name + "/" + filename)
        cases.append(dict(name=name, execution_status=session["execution_status"],
                          source_files=len(source), private_inc_files=sum(p.endswith(".inc") for p in source),
                          prepared_classes=dict(classes), phases=phase_rows))
    health = audit.jread("health.json")
    audit.check(health["idle"] and health["boot_id"] == tasks["boot_id"] == audit.archive["boot_id"] and
                not health["per_session_kernel_faults"], "later_health_identity")
    return dict(scope="Archive consistency only; live outcomes remain separate. No archived code executed.",
                run=raw.name, source_commit=revision, consistent=not audit.issues, issues=audit.issues,
                total_checks=sum(audit.counts.values()), check_counts=dict(audit.counts),
                groups=groups, members=len(audit.members), files=len(audit.files), symlinks=len(links),
                archives_manifest_sha256=module.hashfile(raw / "archives.json"),
                regular_file_hash_map_sha256=module.canonical(audit.files),
                helper_sha256=module.hashfile(helper), cases=cases)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    arguments = parser.parse_args()
    receipt = review(arguments.repo, arguments.raw)
    print(json.dumps(receipt, indent=2))
    raise SystemExit(0 if receipt["consistent"] else 1)
