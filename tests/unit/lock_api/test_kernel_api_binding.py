"""Guest-only composition of the real scoped binding/route implementation."""
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests/unit/spin"))
sys.path.insert(0, str(ROOT / "tests/unit/infrastructure"))
from test_spin_shadow import definition


def production():
    source = (ROOT / "kernel_integration/real_api/overlay/kernel/locking/kd_api/bridge.c").read_text()
    start = source.index("#define KD_API_SELECTORS")
    head = source[start:source.index("extern const struct kd_api_site", start)]
    functions = [
        "int kd_api_register_provider(", "void kd_api_unregister_provider(",
        "static void kd_api_selector_put(", "int kd_api_select_current(",
        "void kd_api_cancel_selector(", "static const struct kd_api_provider *kd_api_bind(",
        "int kd_api_files_init(", "void kd_api_files_destroy(",
        "int kd_api_pipe_init(", "void kd_api_pipe_destroy(",
        "void kd_api_files_lock(", "void kd_api_files_unlock(",
        "void kd_api_pipe_lock(", "void kd_api_pipe_unlock(",
    ]
    bodies = []
    for marker in functions:
        lines = [line for line in source.splitlines() if line.startswith(marker)]
        assert len(lines) == 1, marker
        bodies.append(definition(source, lines[0]))
    return head + "\n" + "\n".join(bodies)


def types():
    path = ROOT / "kernel_integration/real_api/overlay/include/linux"
    control = (ROOT / "include/kd_api_control.h").read_text()
    control = re.sub(r"^#include.*\n", "", control, flags=re.M)
    locks = (path / "kd_api_lock_types.h").read_text()
    locks = locks[locks.index("typedef union kd_api_spinlock"):locks.rindex("#endif")]
    provider = (path / "kd_api_provider.h").read_text()
    offsets = "\n".join(line for line in provider.splitlines() if line.startswith("#define KD_API_OP_"))
    begin = provider.index("struct kd_api_provider {")
    provider = provider[begin:provider.index("struct kd_api_site", begin)]
    return "#define CONFIG_KD_API_LOCKS 1\n" + control + locks + offsets + "\n" + provider


def main():
    here = Path(__file__).resolve().parent
    source = production()
    mutations = [
        ("missing-object-ref", "if (!try_module_get(ops->owner)) {\n\t\t\tops = ERR_PTR(-ENODEV);", "if (false) {\n\t\t\tops = ERR_PTR(-ENODEV);", (), 1),
        ("skip-task-binding", "slot->task != current || !*left", "!*left", (), 1),
        ("leak-selector-ref", "put_task_struct(task);\n\tmodule_put(ops->owner);", "put_task_struct(task);\n\t(void)ops;", (), 1),
        ("native-backing-spin", "if (ops) ops->spin_local_lock(&lock->kd);", "if (ops) spin_lock(&lock->native);", (), 1),
        ("missing-idle-check", "BUG_ON(!ops->spin_idle(&files->file_lock.kd));", "/* removed idle probe */", ("destroy-held",), 0),
    ]
    with tempfile.TemporaryDirectory(prefix="kd-api-binding-") as name:
        path = Path(name)
        (path / "api_types.h").write_text(types())
        cc = shlex.split(os.environ.get("CC", "gcc"))
        def build_run(body, args=()):
            (path / "api_binding_production.h").write_text(body)
            command = cc + ["-O2", "-Wall", "-Wextra", "-Werror", "-I" + str(path),
                            str(here / "api_binding_fixture.c"), "-o", str(path / "fixture")]
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
            return subprocess.run([str(path / "fixture"), *args], capture_output=True, text=True, timeout=10)
        result = build_run(source)
        assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
        print(result.stdout.strip())
        for case, expected in (("destroy-held", "!ops->spin_idle"), ("unregister-live", "kd_api_objects")):
            result = build_run(source, (case,))
            assert result.returncode == 86 and expected in result.stderr, (case, result.returncode, result.stderr)
        for name, old, new, args, expected in mutations:
            assert source.count(old) == 1, name
            result = build_run(source.replace(old, new), args)
            if expected is None:
                assert result.returncode != 0, (name, result.stdout, result.stderr)
            else:
                assert result.returncode == expected, (name, result.returncode, result.stdout, result.stderr)
    print("[PASS] actual binding lifetime/routes; 2 fail-stop cases and 5 mutants")


if __name__ == "__main__":
    main()
