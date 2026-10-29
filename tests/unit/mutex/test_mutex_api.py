"""Guest-only public mutex facade, conventional symbols and compiled JIT calls.

Compile the actual headers with narrow userspace physical primitives. Translate
the compiler-produced anonymous continuation using unchanged production
admission, then execute the real wrapper. Native control services are replaced;
this fixture does not claim real scheduler or owner/ACK concurrency coverage.
"""
import re
import subprocess
import tempfile
from pathlib import Path

from test_jit_diagnostics import ROOT, render
import context_policy


def without_includes(path):
    return re.sub(r"^#include .*$", "", path.read_text(), flags=re.M)


def read_symbols(binary):
    symbols, sizes = {}, {}
    output = subprocess.check_output(
        ["nm", "-S", "--defined-only", binary], text=True, timeout=10)
    for line in output.splitlines():
        words = line.split()
        if len(words) in (3, 4):
            symbols[words[-1]] = int(words[0], 16)
            if len(words) == 4:
                sizes[words[-1]] = int(words[1], 16)
    return symbols, sizes


def main():
    base_header = (ROOT / "include/kd_mutex.h").read_text()
    gate = "\n".join(line for line in base_header.splitlines()
                if line.startswith("#define KD_MUTEX_GATE_"))
    # Preserve the production public-to-linker-name declarations. Repeating
    # an alias in this fixture would not detect an accidental return to the
    # captured kernel's conflicting legacy kd_mutex_lock/unlock exports.
    declarations = re.findall(
        r"^void kd_mutex_(?:un)?lock\([^;]+;", base_header, flags=re.M)
    assert len(declarations) == 2 and all("__asm__" in line for line in declarations)
    stack_bytes = int(next(line.split()[-1] for line in
                          (ROOT / "include/kd_source_api.h").read_text().splitlines()
                          if line.startswith("#define KD_JIT_MUTEX_STACK_BYTES ")))
    header = gate + "\n" + "\n".join(declarations) + "\n"
    header += without_includes(ROOT / "include/kd_mutex_direct.h")
    header += "\n" + without_includes(ROOT / "include/kd_mutex_api.h")
    for nested in (0, 1, 2):
        with tempfile.TemporaryDirectory(prefix=f"kd-mutex-api-{nested}-") as directory:
            path = Path(directory)
            (path / "mutex_api.h").write_text(header)
            (path / "mutex_compat.h").write_text(
                without_includes(ROOT / "include/kd_mutex_compat.h"))
            (path / "asm").mkdir()
            (path / "linux").mkdir()
            (path / "linux/objtool.h").write_text('#define UNWIND_HINT(...) ""\n')
            (path / "asm/asm.h").write_text(
                "/* ASM_CALL_CONSTRAINT is provided by the fixture. */\n")
            (path / "asm/nospec-branch.h").write_text(
                '#define CALL_NOSPEC "call *%[thunk_target]\\n"\n')
            flags = [
                "-O2", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                "-fno-omit-frame-pointer", "-fno-optimize-sibling-calls",
                "-fno-reorder-blocks-and-partition", "-fno-toplevel-reorder",
                "-mno-red-zone", "-mpreferred-stack-boundary=4", "-fno-pie",
                f"-DCASE_NESTED={nested}", "-I" + directory, "-I" + str(ROOT / "include"),
            ]
            subprocess.run(
                ["cc", *flags, "-c", str(ROOT / "tests/unit/mutex/mutex_api_fixture.c"),
                 "-o", str(path / "fixture.o")], check=True, timeout=30)
            link = [
                "cc", "-no-pie", "-Wl,--section-start=.text=0x1000000",
                "-Wl,--section-start=.api_lock=0x60000000", str(path / "fixture.o"),
            ]
            binary = path / "fixture"
            subprocess.run([*link, "-o", str(binary)], check=True, timeout=30)
            result = subprocess.run(
                [binary], capture_output=True, text=True, check=True, timeout=10)
            entry = int(re.search(r"^ENTRY ([0-9a-f]+)$", result.stdout, re.M)[1], 16)
            print(result.stdout, end="")
            symbols, sizes = read_symbols(binary)
            assert "kd_mutex_lock" not in symbols and "kd_mutex_unlock" not in symbols
            sections = subprocess.check_output(
                ["objdump", "-h", binary], text=True, timeout=10)
            text_base = int(next(line.split()[3] for line in sections.splitlines()
                                 if line.split()[1:2] == [".text"]), 16)
            subprocess.run(
                ["objcopy", "--dump-section", f".text={path}/text.bin", binary],
                check=True, timeout=10)
            text = (path / "text.bin").read_bytes()
            start = symbols["api_jit_case"]
            assert start < entry < start + sizes["api_jit_case"]
            raw = text[start - text_base:start - text_base + sizes["api_jit_case"]]
            controls = {
                name: address for name, address in symbols.items()
                if name in {
                    "kd_mutex_api_lock", "kd_mutex_api_unlock",
                    "kd_mutex_local_lock", "kd_mutex_local_unlock",
                    "kd_mutex_direct_lock_clobber_v1",
                    "kd_mutex_direct_unlock_clobber_v1",
                }
            }
            # Real conventional symbols must not become remote ordinary
            # helpers: their native implementation does not publish a nested
            # JIT ledger record. Check direct and register-derived references.
            for name in ("kd_mutex_lock", "kd_mutex_unlock"):
                assert context_policy.is_context_symbol(name), name
            for name in ("kd_mutex_api_lock", "kd_mutex_api_unlock"):
                assert context_policy.is_context_symbol(name), name
                target, base = symbols[name], 0x2000000
                direct = b"\xe8" + (target - base - 5).to_bytes(4, "little", signed=True)
                indirect = b"\x48\xb8" + target.to_bytes(8, "little") + b"\xff\xd0"
                for code in (direct, indirect):
                    refused, rejection, rejected = render(
                        (code + b"\xc3").hex(), entry=base, kernel_symbols=controls,
                        symbols={target: name}, abi=2, lock_kind="mutex",
                        return_status=True)
                    assert rejected == context_policy.NATIVE_ONLY_EXIT, rejection
                    assert not refused and name in rejection, rejection
            assembly, log, status = render(
                "", regions=[(raw, start, [entry])], entry=entry,
                kernel_symbols=controls, abi=2, lock_kind="mutex",
                mutex_stack_bytes=stack_bytes, body_witness=True, return_status=True)
            assert status == 0, log
            if not nested:
                assert b"clobber_complete" in assembly, assembly
            print(subprocess.check_output(
                ["objdump", "-d", "--disassemble=api_jit_case", binary],
                text=True, timeout=10))
            (path / "asm/jit.S").write_bytes(assembly)
            (path / "wrapper.S").write_text(
                (ROOT / "include/wrapper.S").read_text()
                + '\n.globl main\n.section .note.GNU-stack,"",@progbits\n')
            subprocess.run(
                ["cc", "-c", "-DKD_GENERATED_ENTRY_ABI=2", "-Dmain=main_wrapper",
                 "-I" + directory, "-I" + str(path / "asm"), "-I" + str(ROOT / "include"),
                 str(path / "wrapper.S"), "-o", str(path / "wrapper.o")],
                check=True, timeout=30)
            generated = path / "generated"
            subprocess.run(
                [*link, str(path / "wrapper.o"), "-o", str(generated)],
                check=True, timeout=30)
            final_symbols, _ = read_symbols(generated)
            for name in ("api_jit_case", "test_lock", "inner_lock", *controls):
                assert final_symbols[name] == symbols[name], (
                    name, symbols[name], final_symbols[name])
            assert "main_wrapper" in final_symbols
            result = subprocess.run(
                [generated], capture_output=True, text=True, check=True, timeout=10)
            assert f"ENTRY {entry:x}\n" in result.stdout, result.stdout
            assert "PASS compiled unified " in result.stdout, result.stdout
            print(result.stdout, end="")
    print("PASS unified facade: actual root/nested/early-unlock compiler output, strict ABI2 admission and generated execution")


if __name__ == "__main__":
    main()
