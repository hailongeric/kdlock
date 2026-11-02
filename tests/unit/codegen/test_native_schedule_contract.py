"""VM-only production descriptor and scheduling-context policy execution.

This checks admission and executor pin policy. Actual Native scheduling,
Native task-stack returns and MM performance need separate live evidence.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]


def definition(source, name):
    marker = source.index(name + "(")
    start = source.rfind("\n", 0, marker) + 1
    opening = source.index("{", marker)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


def production_code():
    header = (ROOT / "include/kd_service_calls.h").read_text()
    enums = header[header.index("enum kd_service_call_result {"):
                   header.index("enum kd_native_owner_kind {")]
    desc = header[header.index("struct kd_service_call_desc {"):
                  header.index("enum kd_origin_call_phase {")]
    registry = (ROOT / "kernel_module/kd_service_calls.c").read_text()
    native = (ROOT / "kernel_module/service_native.inc").read_text()
    return enums + desc + "\n".join((
        definition(registry, "kd_service_call_requires_preempt_rcu"),
        definition(registry, "kd_service_call_context_valid"),
        definition(native, "kd_service_schedule_origin_allowed"),
        definition(native, "kd_service_native_executor_pinned"),
    ))


def main():
    code = production_code()
    variants = (
        ("production", None, (0, 1)),
        ("schedule-with-native-pin", ("return !pins &&", "return (!pins || pins) &&"), (1,)),
        ("schedule-in-nonpreempt-rcu", (
            "(!rcu || IS_ENABLED(CONFIG_PREEMPT_RCU))", "(!rcu || rcu)"), (0,)),
        ("schedule-nonzero-arity", (
            "return !desc->nargs && desc->result_kind == KD_SERVICE_CALL_VOID;",
            "return desc->nargs <= 6 && desc->result_kind == KD_SERVICE_CALL_VOID;"), (1,)),
        ("schedule-executor-pinned", (
            "return pins || (context >= KD_SERVICE_CALL_PTE_LOCK &&\n"
            "\t\tcontext <= KD_SERVICE_CALL_PTE_RCU);",
            "return pins || context >= KD_SERVICE_CALL_PTE_LOCK;"), (1,)),
        ("schedule-requires-preempt-rcu", (
            "return context >= KD_SERVICE_CALL_PTE_LOCK &&\n"
            "\t\tcontext <= KD_SERVICE_CALL_PTE_RCU;",
            "return context >= KD_SERVICE_CALL_PTE_LOCK;"), (0,)),
    )
    with tempfile.TemporaryDirectory(prefix="kd-native-schedule-contract-") as name:
        directory = Path(name)
        for label, mutation, configurations in variants:
            transformed = code
            if mutation:
                before, after = mutation
                assert transformed.count(before) == 1, label
                transformed = transformed.replace(before, after)
            (directory / "production.h").write_text(transformed)
            for preempt_rcu in configurations:
                binary = directory / f"{label}-{preempt_rcu}"
                subprocess.run(shlex.split(os.environ.get("CC", "cc")) + [
                    "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                    f"-DCONFIG_PREEMPT_RCU={preempt_rcu}",
                    "-I", str(ROOT / "include"), "-I", str(directory),
                    str(ROOT / "tests/unit/codegen/native_schedule_contract_fixture.c"),
                    "-o", str(binary)], check=True, timeout=30)
                result = subprocess.run([str(binary)], text=True,
                                        capture_output=True, timeout=15)
                if mutation:
                    assert result.returncode == 1 and "FAIL line=" in result.stderr, (
                        label, preempt_rcu, result.returncode, result.stdout, result.stderr)
                    print("Native schedule policy mutation detected:", label)
                else:
                    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
                    print(result.stdout, end="")


if __name__ == "__main__":
    main()
