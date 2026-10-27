"""Guest-only ordinary byte loops executed through the actual generated wrapper.

The source is assembled independently, then decoded with the normal coordinator.
No symbol summary, hostcall, native helper implementation, or runtime memory
oracle substitutes for a callee. The ctypes objects only supply ordinary input
bytes and compare output bytes after execution. This is not a kernel live test.
"""
import ctypes
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_jit_diagnostics import render
from test_jit_body_witness import run_image

SYMBOLS = {"kd_raw_spin_lock_clobber_v1": 0x6000,
           "kd_raw_spin_unlock_clobber_v1": 0x7000}


def source_bytes(body):
    """Assemble ordinary source functions at fixed virtual source addresses."""
    with tempfile.TemporaryDirectory(prefix="kd-ordinary-source-") as name:
        path = Path(name)
        (path / "source.S").write_text(
            ".intel_syntax noprefix\n.text\n.global source_entry\n"
            "source_entry:\n" + body + "\n.section .note.GNU-stack,\"\",@progbits\n")
        for command in (
            ["as", "--64", "-o", "source.o", "source.S"],
            ["ld", "-Ttext=0x1000", "-e", "source_entry", "-o", "source.elf", "source.o"],
            ["objcopy", "-O", "binary", "-j", ".text", "source.elf", "source.bin"],
        ):
            subprocess.run(command, cwd=path, check=True, capture_output=True, timeout=15)
        symbols = subprocess.run(["nm", "-n", "source.elf"], cwd=path,
                                 check=True, capture_output=True, text=True,
                                 timeout=15).stdout
        addresses = {fields[2]: int(fields[0], 16)
                     for line in symbols.splitlines()
                     if len(fields := line.split()) == 3 and fields[1] in {"t", "T"}}
        raw = (path / "source.bin").read_bytes()
    roots = [addresses[name] for name in ("source_entry", "helper", "helper_pad")
             if name in addresses]
    return [(raw, 0x1000, roots)], addresses


SCAN = """
    call helper
    ret
    .balign 4096
helper:
    mov rax, rdi
    lea rdx, [rdi+rsi]
    test rsi, rsi
    je scan_done
scan_loop:
    cmp BYTE PTR [rax], 0
    je scan_done
    add rax, 1
    cmp rax, rdx
    jne scan_loop
scan_done:
    sub rax, rdi
    ret
"""

COPY_PAD = """
    call helper
    ret
    .balign 4096
helper:
    test rdx, rdx
    je copy_empty
    dec rdx
    xor ecx, ecx
copy_loop:
    mov al, BYTE PTR [rsi+rcx]
    test al, al
    je copy_end
    cmp rcx, rdx
    je copy_truncated
    mov BYTE PTR [rdi+rcx], al
    inc rcx
    jmp copy_loop
copy_end:
    mov rax, rcx
    add rdi, rcx
    sub rdx, rcx
    inc rdx
    call helper_pad
    ret
copy_truncated:
    mov BYTE PTR [rdi+rcx], 0
copy_empty:
    mov rax, -7
    ret
    .balign 4096
helper_pad:
    mov BYTE PTR [rdi], 0
    inc rdi
    dec rdx
    jne helper_pad
    ret
"""


class OrdinaryCalleeBytesTests(unittest.TestCase):
    def generate(self, body, **kwargs):
        regions, addresses = source_bytes(body)
        options = {}
        assembly, log, status = render(
            "", regions=regions, abi=1, body_witness=True,
            kernel_symbols=SYMBOLS, trusted_source=True,
            build_options=options, return_status=True, **kwargs)
        self.assertEqual(status, 0, log)
        self.assertEqual(options["requirements"], 0)
        for name in ("helper", "helper_pad"):
            if name in addresses:
                self.assertIn(f"loc_{addresses[name]:x}:".encode(), assembly)
        for marker in (b"KD_HOSTCALL", b"KD_DIRECT_STRING", b"KDNC0001"):
            self.assertNotIn(marker, assembly)
        self.assertIn("TRANSLATION_FLAGS_PRESERVED", log)
        self.assertIn("TRUSTED_SOURCE_EMISSION", log)
        return assembly, addresses

    def execute(self, assembly):
        regs, args = run_image(assembly, [0x1000], abi=1)[0]
        self.assertEqual(regs[0], 0x4444)
        self.assertEqual(args[1], 1)
        return regs

    def test_finite_scan_decodes_every_load_and_return(self):
        # Include a complete 64-byte scan. The current trusted policy emits
        # the real source loop without applying a value-analysis proof budget.
        for size, data, expected in ((0, b"x", 0), (1, b"x", 1),
                                     (16, b"abc\0suffix", 3),
                                     (64, b"x" * 64, 64)):
            with self.subTest(size=size, expected=expected):
                source = ctypes.create_string_buffer(data, max(len(data), size) + 1)
                prefix = f"movabs rdi, {ctypes.addressof(source)}\nmov esi, {size}\n"
                assembly, _ = self.generate(prefix + SCAN)
                self.assertEqual(self.execute(assembly)[12], expected)
                self.assertEqual(bytes(source)[:len(data)], data)

    def test_nested_copy_and_padding_have_exact_memory_effects(self):
        for size, data in ((0, b"abc"), (1, b"abc"), (16, b"abc"),
                           (16, b"x" * 16), (64, b"short")):
            with self.subTest(size=size, source=data):
                source = ctypes.create_string_buffer(data)
                destination = ctypes.create_string_buffer(b"\xa5" * (size + 16), size + 16)
                before_source = bytes(source)
                prefix = (f"movabs rdi, {ctypes.addressof(destination) + 8}\n"
                          f"movabs rsi, {ctypes.addressof(source)}\nmov edx, {size}\n")
                assembly, _ = self.generate(prefix + COPY_PAD)
                returned = ctypes.c_long(self.execute(assembly)[12]).value
                expected_result = len(data) if size > len(data) else -7
                self.assertEqual(returned, expected_result)
                if not size:
                    expected = b""
                elif len(data) >= size:
                    expected = data[:size - 1] + b"\0"
                else:
                    expected = data + b"\0" * (size - len(data))
                self.assertEqual(bytes(destination), b"\xa5" * 8 + expected + b"\xa5" * 8)
                self.assertEqual(bytes(source), before_source)

    def test_flags_cross_block_budget_lea_call_and_return(self):
        # ADD defines OF=SF=AF=1, CF=ZF=PF=0. A source JMP, special LEA
        # lowering, ordinary CALL/RET and return-target checks must preserve it.
        assembly, _ = self.generate("""
            mov eax, 127
            mov r12d, 1
            mov r14d, 2
            add al, 1
            jmp flags_block
        flags_block:
            lea r13, [r12+r14]
            call helper
            seto al
            sets bl
            sete cl
            setb dl
            movzx eax, al
            movzx ebx, bl
            movzx ecx, cl
            movzx edx, dl
            shl ebx, 1
            shl ecx, 2
            shl edx, 3
            or eax, ebx
            or eax, ecx
            or eax, edx
            ret
            .balign 4096
        helper:
            jmp helper_return
        helper_return:
            mov esi, 17
            ret
        """)
        self.assertEqual(self.execute(assembly)[12], 3)

    def test_source_branch_after_call_observes_callee_flags(self):
        assembly, _ = self.generate("""
            call helper
            jne failed
            mov eax, 42
            ret
        failed:
            mov eax, 99
            ret
            .balign 4096
        helper:
            mov eax, 5
            cmp eax, 5
            ret
        """)
        self.assertEqual(self.execute(assembly)[12], 42)

    def test_entry_dispatch_preserves_its_input_flags(self):
        assembly, _ = self.generate("mov eax, 0\nsetb al\nret")
        boundary = b"MOV     R14, PT_RIP\nPUSHFQ\n"
        self.assertEqual(assembly.count(boundary), 1)
        # This fixture defines CF immediately at the dispatch boundary. It
        # does not assert that wrapper entry imports arbitrary caller flags.
        # The following matching dispatch CMP would clear CF without its save.
        seeded = assembly.replace(boundary,
                                  b"MOV     R14, PT_RIP\nCMP R14, 0x2000\nPUSHFQ\n")
        self.assertEqual(self.execute(seeded)[12], 1)

    def test_trusted_source_bypasses_semantic_admission_without_shortcuts(self):
        regions, _ = source_bytes("call helper\nret\n.balign 4096\n"
                                  "helper:\nud2\nret")
        # UD2 deliberately cannot be executed by this userspace test. Its
        # ordinary emitted instruction proves trusted source is not silently
        # pruned, replaced by a service, or subjected to the old safety check.
        assembly, log, status = render(
            "", regions=regions, abi=1, kernel_symbols=SYMBOLS,
            trusted_source=True, return_status=True)
        self.assertEqual(status, 0, log)
        self.assertRegex(assembly, rb"\bUD2\b")
        self.assertIn(b"loc_2000:", assembly)
        self.assertNotIn(b"KD_HOSTCALL", assembly)
        self.assertNotIn(b"KD_DIRECT_STRING", assembly)
        self.assertIn("TRUSTED_SOURCE_EMISSION", log)
        # The standalone checked mode remains useful for the legacy policy
        # corpus; it is no longer the current coordinator's default contract.
        assembly, log, status = render("", regions=regions, abi=1,
                                      kernel_symbols=SYMBOLS, trusted_source=False,
                                      return_status=True)
        self.assertEqual((assembly, status), (b"", 2), log)
        self.assertIn("UD2", log)


if __name__ == "__main__":
    unittest.main(verbosity=2)
