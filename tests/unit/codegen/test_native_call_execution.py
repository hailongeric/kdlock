"""Guest-only execution of actual direct-call stubs inside the actual wrapper.

This isolates lowering from admission/provider ownership: the C fixture supplies
an explicit pristine packet and relocates the generated E8 slots to hostile
userspace helpers. It is neither kernel JIT acceptance nor a performance test.
"""
import io
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'disassem'))

from miasm.arch.x86.arch import mn_x86
from miasm.core.bin_stream import bin_stream_str
import conflict
import hostcall
import native_calls
import special_inst
from translation_image import write_entry_dispatch


def generated_body():
    services = {
        0x3000: hostcall.HostcallSpec('STRCMP', 4, 'strcmp'),
        0x4000: hostcall.HostcallSpec('STRSCPY_PAD', 5, 'strscpy_pad'),
    }
    calls = native_calls.NativeCalls(services)
    stream = io.StringIO()
    # Use the production root-only dispatch as well as the production CALL
    # lowering. Dummy block values are unused by this dispatch-only API.
    write_entry_dispatch(stream, 0x1000, {0x1000: None, 0x1005: None, 0x2005: None},
                         {0x1005, 0x2005}, body_witness=True, root_only=True)
    stream.write('loc_1000:\n')
    # The fixture explicitly defines resident source GPRs after the genuine
    # minimal entry. Real translated source has its own capture/admission proof.
    for reg, field in (('RBX', 'BX'), ('R10', 'R10'), ('R9', 'R9'), ('R8', 'R8'),
                       ('RAX', 'AX'), ('RCX', 'CX'), ('RDX', 'DX'), ('RSI', 'SI'), ('RDI', 'DI')):
        stream.write(f'MOV {reg}, QWORD PTR[REG_BANK + KD_REG_{field}]\n')
    stream.write('CMP QWORD PTR[rip + fixture_kind], 0\nJNE fixture_pad_loop\n')
    for kind, source, target, continuation in (('cmp', 0x1000, 0x3000, 0x1005),
                                                ('pad', 0x2000, 0x4000, 0x2005)):
        stream.write(f'fixture_{kind}_loop:\nINC QWORD PTR[rip + fixture_attempted]\n')
        # Define all arithmetic flags before the actual bridge: OF/SF/AF set,
        # CF/PF/ZF clear. Later MOV definitions preserve this exact pattern.
        stream.write('MOV R14, 127\nADD R14b, 1\n'
                     'PUSHFQ\nPOP QWORD PTR[rip + fixture_precall_flags]\n')
        # Exercise dirty remapped logical R11/R12 immediately before CALL.
        # These definitions also make each loop iteration's mapping genuine.
        stream.write('MOVABS R14, 0x1111222233334444\n'
                     'MOVABS R15, 0x5555666677778888\n')
        mapping = conflict.block_init()
        mapping.update({'14': '11', '15': '12'})
        mapping.dirty.update({'11', '12'})
        line = mn_x86.dis(bin_stream_str(bytes.fromhex('e800000000')), 64, 0)
        line.offset = source
        emitted = calls.emit(line, continuation, target, mapping)
        assert emitted.count('JMP full_exit\n') == 2
        # Only reroute the two bridge exits through an observation trampoline.
        # The production common FULL export has its own flag clobbers; record
        # at the bridge boundary and then execute that unchanged export.
        stream.write(emitted.replace('JMP full_exit\n', 'JMP fixture_bridge_exit\n'))
        stream.write(f'loc_{continuation:x}:\n'
                     'PUSHFQ\nPOP QWORD PTR[rip + fixture_return_flags]\n'
                     'MOV QWORD PTR[rip + fixture_return_rcx], RCX\n'
                     'INC QWORD PTR[rip + fixture_completed]\n'
                     'MOV R14, QWORD PTR[rip + fixture_completed]\n'
                     'CMP R14, QWORD PTR[rip + fixture_requested]\n'
                     f'JB fixture_{kind}_loop\nJMP fixture_finished\n')
    stream.write('fixture_bridge_exit:\nPUSHFQ\nPOP QWORD PTR[rip + fixture_exit_flags]\n'
                 'MOV QWORD PTR[rip + fixture_exit_rcx], RCX\nJMP full_exit\n'
                 'fixture_finished:\nCMP QWORD PTR[rip + fixture_terminal], 0\n'
                 'JNE fixture_terminal_completion\nMOV R14, 0x4444\n'
                 'MOV Stack_IJ, 0x1234\nJMP full_exit\n'
                 'fixture_terminal_completion:\nMOV RSI, R13\nMOV RCX, R12\n'
                 'MOV RDI, 0x6000\nMOV RDX, 0x7777\nMOV RBX, 0x11111111\n')
    stream.write(special_inst.terminal_clobber_unlock(0x7000, 0x7777, conflict.block_init()))
    return '#ifndef KD_EMIT_NATIVE_DIRECTORY\n' + stream.getvalue() + \
           '#else\n' + calls.metadata() + '#endif\n'


def main():
    with tempfile.TemporaryDirectory(prefix='kd-native-call-execution-') as name:
        path = Path(name)
        (path / 'jit.S').write_text(generated_body())
        # Compile production bytes unchanged. The final symbol only identifies
        # the metadata footer for the fixture's executable-image relocation.
        (path / 'wrapper.S').write_text((ROOT / 'include/wrapper.S').read_text() +
            '\n.globl kd_native_wrapper, kd_native_image_end\nkd_native_image_end:\n'
            '.section .note.GNU-stack,"",@progbits\n')
        cc = shlex.split(os.environ.get('CC', 'gcc'))
        subprocess.run(cc + ['-c', '-Dmain=kd_native_wrapper', '-DKD_GENERATED_ENTRY_ABI=1',
            '-DKD_GENERATED_REQUIREMENTS=28', '-DKD_GENERATED_GS_INPUT=0', '-DKD_GENERATED_TASK_INPUT=0',
            '-I' + str(path), '-I' + str(ROOT / 'include'), str(path / 'wrapper.S'),
            '-o', str(path / 'wrapper.o')], check=True, timeout=30)
        here = Path(__file__).resolve().parent
        subprocess.run(cc + ['-O2', '-fno-omit-frame-pointer', '-mno-red-zone', '-fno-pie', '-no-pie',
            '-Wall', '-Wextra', '-Werror', '-I' + str(ROOT / 'include'),
            str(here / 'native_call_execution_fixture.c'), str(here / 'native_call_execution_helpers.S'),
            str(path / 'wrapper.o'), '-o', str(path / 'fixture')], check=True, timeout=30)
        subprocess.run([str(path / 'fixture')], check=True, timeout=30)
    print('[PASS] actual native-call wrapper execution; userspace lowering fixture only')


if __name__ == '__main__':
    main()
