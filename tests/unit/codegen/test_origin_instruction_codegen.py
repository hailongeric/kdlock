"""Guest-only generated instruction reentry, with an explicit service double.

The actual wrapper and emitted continuation execute here. Fixed instruction
results substitute for the original-task rendezvous; live kernel probes must
separately prove the waiter CPU/task, owner and queue lifetime.
"""
import ctypes
import os
from pathlib import Path
import struct
import tempfile
import unittest

from test_jit_diagnostics import render, translator, decode
from test_jit_body_witness import run_image
from test_rip_relative_codegen import machine_code
from test_instruction_policy import SYMBOLS
import origin_instructions

TAG = 0x4b444f524947494e


def compile_source(source, **options):
    raw = machine_code(source)
    build = {}
    assembly, log, status = render(raw.hex(), lock_kind="mutex", abi=2,
        kernel_symbols=SYMBOLS, native_escape_capable=True,
        origin_instruction_capable=True,
        body_witness=options.pop('body_witness', True),
        trusted_source=options.pop('trusted_source', True),
        return_status=True, build_options=build, **options)
    if status:
        raise AssertionError(log)
    return raw, assembly, build


def image_bytes(assembly, requirements):
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="kd-origin-directory-") as directory:
        directory = Path(directory)
        (directory/'asm').mkdir()
        (directory/'asm/jit.S').write_bytes(assembly)
        try:
            os.chdir(directory)
            translator.build_jit_binary(2, context_inputs=translator.wrapper_context_inputs(assembly.decode()),
                                        requirements=requirements)
            return (directory/'asm/jit.bin').read_bytes()
        finally:
            os.chdir(previous)


class OriginInstructionCodegenTests(unittest.TestCase):
    def test_exact_directory_records_and_nonservice_encodings(self):
        raw, assembly, build = compile_source("rdtsc\nrdtscp\ncpuid\nret")
        self.assertEqual(build['requirements'], 65)
        binary = image_bytes(assembly, 65)
        magic, offset, count = struct.unpack_from('<8sII', binary, len(binary)-16)
        self.assertEqual((magic, count), (b'KDOS0001', 3))
        self.assertEqual(offset + count*32, len(binary)-16)
        for index, (opcode, kind) in enumerate(((b'\x0f\x31',1), (b'\x0f\x01\xf9',2), (b'\x0f\xa2',3))):
            ip, next_ip, target, actual_kind, length, reserved, encoded = struct.unpack_from('<QQIBB2s8s', binary, offset+index*32)
            self.assertEqual((ip,next_ip), (0x1000+raw.index(opcode),0x1000+raw.index(opcode)+len(opcode)))
            self.assertEqual((actual_kind,length,reserved,encoded), (kind,len(opcode),b'\0\0',opcode.ljust(8,b'\0')))
            self.assertTrue(48 <= target < offset)
        for raw_hex in ('fa', 'fb', 'fc', 'fd', '0f32', '0f30', '0f33', '9f', '9e', 'f30f31'):
            line = decode(raw_hex)
            self.assertFalse(line.name.upper() in origin_instructions.KINDS and
                             origin_instructions.native_escape.descriptor(line), raw_hex)

    def test_same_image_reentry_preserves_flags_sp_bp_and_virtual_registers(self):
        for instruction, outputs in (
                ('rdtsc', {12:0x12345678,14:0x87654321}),
                ('rdtscp', {12:0x12345678,14:0x87654321,13:0x1357}),
                ('cpuid', {12:0x12345678,8:0xAABBCCDD,13:0x1357,14:0x87654321})):
            with self.subTest(instruction=instruction):
                raw, assembly, _ = compile_source(f"""
                    add QWORD PTR[rbp], 1
                    mov r11, 0x1111
                    mov r12, 0x1212
                    mov r14, 0x1414
                    mov r15, 0x1515
                    mov eax, 1
                    mov ecx, 7
                    cmp eax, 2
                    {instruction}
                    setc BYTE PTR[rbp + 8]
                    mov QWORD PTR[rbp + 16], rax
                    mov QWORD PTR[rbp + 24], r11
                    mov QWORD PTR[rbp + 32], r12
                    mov QWORD PTR[rbp + 40], r14
                    mov QWORD PTR[rbp + 48], r15
                    ret
                """)
                data = (ctypes.c_ulong*7)()
                entered = []
                def initialize(regs, stack):
                    regs[2] = ctypes.addressof(data)
                    entered.append((regs[1],regs[2]))
                calls = []
                def service(regs, args, stack):
                    if args[0] != 12:
                        return False
                    calls.append(regs[0])
                    self.assertEqual((regs[1],regs[2]), entered[0])
                    self.assertEqual((regs[12],regs[13]), (1,7))
                    self.assertEqual(regs[19]&0x8d5, 0x95)
                    self.assertEqual(regs[20], 0x1000000)
                    for slot,value in outputs.items(): regs[slot] = value
                    regs[0] += 3 if instruction == 'rdtscp' else 2
                    regs[17] = TAG
                    return True
                regs,args = run_image(assembly,[0x1000],initialize=initialize,resume=service,
                                      abi=2,requirements=65)[0]
                self.assertEqual(len(calls),1)
                self.assertEqual(list(data),[1,1,0x12345678,0x1111,0x1212,0x1414,0x1515])
                self.assertEqual((regs[0],regs[1],regs[2],regs[17]),(0x4444,entered[0][0]+8,entered[0][1],0))
                for slot,value in outputs.items():
                    self.assertEqual(regs[slot],value)
                self.assertEqual(args[1],1)

    def test_resumed_body_has_a_receipt_when_general_observation_is_off(self):
        _,assembly,_=compile_source('rdtsc\nmov eax,42\nret',body_witness=False)
        witnesses=[]
        def service(regs,args,stack):
            if args[0]!=12:return False
            witnesses.append(args[1]);regs[0]+=2;regs[17]=TAG;return True
        regs,args=run_image(assembly,[0x1000],resume=service,abi=2,requirements=65)[0]
        self.assertEqual(witnesses,[0])
        self.assertEqual(regs[12],42)
        self.assertEqual(args[1],1)

    def test_all_arithmetic_flags_survive_the_generated_successor(self):
        # LAHF is an exact ordinary native marker here. Its pre-instruction
        # PUSHFQ captures real post-reentry hardware flags, including AF/OF;
        # no source arithmetic operation occurs between service and capture.
        patterns = (
            ('mov eax,1\ncmp eax,2', 0x95),
            ('mov eax,0x7fffffff\nadd eax,1', 0x894),
            ('mov eax,0xffffffff\nadd eax,1', 0x55),
            ('mov eax,0\ncmp eax,0', 0x44),
        )
        for setup,expected in patterns:
            with self.subTest(flags=hex(expected)):
                _,assembly,_=compile_source(f'''
                    add QWORD PTR[rbp],1
                    {setup}
                    rdtsc
                    mov QWORD PTR[rbp+8],1
                    lahf
                    ret
                ''')
                data=(ctypes.c_ulong*2)();captured=[]
                def initialize(regs,stack):regs[2]=ctypes.addressof(data)
                def service(regs,args,stack):
                    if args[0]!=12:return False
                    captured.append(regs[19]&0x8d5)
                    regs[12],regs[14],regs[0],regs[17]=100,0,regs[0]+2,TAG
                    return True
                regs,args=run_image(assembly,[0x1000],initialize=initialize,resume=service,
                                    abi=2,requirements=65)[0]
                self.assertEqual(captured,[expected])
                self.assertEqual(regs[19]&0x8d5,expected)
                self.assertEqual(args,[8,1])
                self.assertEqual(list(data),[1,1])

    def test_two_services_use_one_prefix_and_one_suffix(self):
        _,assembly,_ = compile_source("""
            add QWORD PTR[rbp], 1
            rdtsc
            add QWORD PTR[rbp + 8], 1
            rdtscp
            add QWORD PTR[rbp + 16], 1
            ret
        """)
        data=(ctypes.c_ulong*3)();calls=[]
        def initialize(regs,stack):regs[2]=ctypes.addressof(data)
        def service(regs,args,stack):
            if args[0]!=12:return False
            calls.append((regs[0],regs[20]))
            regs[0]+=2 if len(calls)==1 else 3
            regs[12],regs[14],regs[17]=100,0,TAG
            return True
        regs,args=run_image(assembly,[0x1000],initialize=initialize,resume=service,abi=2,requirements=65)[0]
        self.assertEqual(list(data),[1,1,1]);self.assertEqual(len(calls),2)
        self.assertEqual([budget for _,budget in calls],[0x1000000]*2)
        self.assertEqual(regs[17],0);self.assertEqual(args[1],1)

    def test_budget_is_not_replenished_by_reentry(self):
        raw,assembly,_=compile_source("mov ecx, 9\nagain: rdtsc\ndec ecx\njne again\nret")
        assembly=assembly.replace(b'MOV     Stack_BUDGET, 0x1000000\n',b'MOV     Stack_BUDGET, 3\n')
        budgets=[]
        def service(regs,args,stack):
            if args[0]!=12:return False
            budgets.append(regs[20]);regs[0]+=2;regs[17]=TAG;return True
        regs,args=run_image(assembly,[0x1000],resume=service,abi=2,requirements=65)[0]
        self.assertEqual(budgets,[2,1]);self.assertEqual(args,[4,1])
        self.assertEqual(regs[0],0x1000+raw.index(b'\x0f\x31'))
        self.assertEqual(regs[13],7)

    def test_invalid_reentry_never_runs_a_successor_and_clears_tag(self):
        raw,assembly,_=compile_source('rdtsc\nmov eax, 42\nret')
        for budget,target in ((0,0x1002),(0x1000001,0x1002),(1,0x1000),(1,0x7777)):
            def initialize(regs,stack):
                regs[17],regs[20],regs[12]=TAG,budget,99
            regs,args=run_image(assembly,[target],initialize=initialize,abi=2,requirements=65)[0]
            self.assertEqual(args[1],0);self.assertEqual(regs[12],99);self.assertEqual(regs[17],0)

    def test_nonservice_marker_keeps_its_waiter_suffix(self):
        _,assembly,build=compile_source('rdtsc\ncli\nmov eax,42\nret')
        self.assertEqual(build['requirements'],65)
        calls=[]
        def service(regs,args,stack):
            if args[0]!=12:return False
            calls.append(regs[0]);regs[0]+=2;regs[17]=TAG;return True
        regs,args=run_image(assembly,[0x1000],resume=service,abi=2,requirements=65)[0]
        self.assertEqual(calls,[0x1000]);self.assertEqual(args,[8,1]);self.assertEqual(regs[0],0x1002)
        self.assertNotIn(b'0x2a',assembly.lower())

    def test_service_capability_does_not_change_ordinary_images(self):
        raw='48c7c02a000000c3'
        # Compare production translations with and without the new capability.
        # The explicit checked-source analyzer has a separate rejection policy.
        common=dict(lock_kind='mutex',abi=2,kernel_symbols=SYMBOLS,
                    native_escape_capable=True,trusted_source=True)
        original,_=render(raw,**common)
        capable,_=render(raw,origin_instruction_capable=True,**common)
        self.assertEqual(original,capable)
        _,assembly,build=compile_source('cli\nret')
        self.assertEqual(build['requirements'],1);self.assertNotIn(b'KDOS0001',assembly)
        old,log,status=render('0f31c3',return_status=True,**common)
        self.assertEqual(status,0,log);self.assertNotIn(b'KDOS0001',old)


if __name__ == '__main__':
    unittest.main(verbosity=2)
