 .intel_syntax noprefix
 .text
 .p2align 4
 .globl kd_fixture_entry
 .type kd_fixture_entry, @function
kd_fixture_entry:
 endbr64
 push rbp
 mov rbp, rsp
 push rbx
 push r12
 push r13
 push r14
 push r15
 lea rsp, [rsp - 80]
 mov QWORD PTR[RBP - 64], rsi
 mov R11, rdi
 mov r14, QWORD PTR[rsi + 0]
 mov QWORD PTR[RBP - 48], r14
 mov r14, QWORD PTR[rsi + 8]
 mov QWORD PTR[RBP - 56], r14
 mov rbx, QWORD PTR[R11 + 64]
 mov r10, QWORD PTR[R11 + 72]
 mov r9, QWORD PTR[R11 + 80]
 mov r8, QWORD PTR[R11 + 88]
 mov rax, QWORD PTR[R11 + 96]
 mov rcx, QWORD PTR[R11 + 104]
 mov rdx, QWORD PTR[R11 + 112]
 mov rsi, QWORD PTR[R11 + 120]
 mov rdi, QWORD PTR[R11 + 128]
 mov r12, QWORD PTR[R11 + 16]
 mov r13, QWORD PTR[R11 + 8]
 jmp .Lkd_dispatch
.Lkd_dispatch:
MOVABS R14, 1000000
MOV QWORD PTR[RBP - 120], R14
MOV R14, QWORD PTR[R11 + 0]
PUSHFQ
MOVABS R15, 0xffffffffc000b1c2
CMP R14, R15
JE .Lkd_enter_ffffffffc000b1c2
MOVABS R15, 0xffffffffc000b270
CMP R14, R15
JE .Lkd_enter_ffffffffc000b270
MOVABS R15, 0xffffffffc000b2db
CMP R14, R15
JE .Lkd_enter_ffffffffc000b2db
MOVABS R15, 0xffffffffc000b2fc
CMP R14, R15
JE .Lkd_enter_ffffffffc000b2fc
MOVABS R15, 0xffffffffc000b346
CMP R14, R15
JE .Lkd_enter_ffffffffc000b346
MOVABS R15, 0xffffffffc000b3a7
CMP R14, R15
JE .Lkd_enter_ffffffffc000b3a7
POPFQ
JMP .Lkd_exit_0
.Lkd_enter_ffffffffc000b1c2:
POPFQ
JMP .Lkd_src_ffffffffc000b1c2
.Lkd_enter_ffffffffc000b270:
POPFQ
JMP .Lkd_src_ffffffffc000b270
.Lkd_enter_ffffffffc000b2db:
POPFQ
JMP .Lkd_src_ffffffffc000b2db
.Lkd_enter_ffffffffc000b2fc:
POPFQ
JMP .Lkd_src_ffffffffc000b2fc
.Lkd_enter_ffffffffc000b346:
POPFQ
JMP .Lkd_src_ffffffffc000b346
.Lkd_enter_ffffffffc000b3a7:
POPFQ
JMP .Lkd_src_ffffffffc000b3a7
.Lkd_src_ffffffffc000b0b0:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0b0
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR[RBP - 56]
MOV RDX, R15
JMP .Lkd_src_ffffffffc000b0b8
.Lkd_runtime_ffffffffc000b0b0:
POPFQ
JMP .Lkd_exit_1
.Lkd_src_ffffffffc000b0b8:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0b8
DEC QWORD PTR[RBP - 120]
POPFQ
ADD QWORD PTR [RDI + 0x40], 0x1
JMP .Lkd_src_ffffffffc000b0bd
.Lkd_runtime_ffffffffc000b0b8:
POPFQ
JMP .Lkd_exit_2
.Lkd_src_ffffffffc000b0bd:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0bd
DEC QWORD PTR[RBP - 120]
POPFQ
MOV QWORD PTR [RDI + 0x18], RDX
JMP .Lkd_src_ffffffffc000b0c1
.Lkd_runtime_ffffffffc000b0bd:
POPFQ
JMP .Lkd_exit_3
.Lkd_src_ffffffffc000b0c1:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0c1
DEC QWORD PTR[RBP - 120]
POPFQ
MOV EDX, DWORD PTR [RDI + 0x68]
JMP .Lkd_src_ffffffffc000b0c4
.Lkd_runtime_ffffffffc000b0c1:
POPFQ
JMP .Lkd_exit_4
.Lkd_src_ffffffffc000b0c4:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0c4
DEC QWORD PTR[RBP - 120]
POPFQ
CMP RDX, 0x41
JMP .Lkd_src_ffffffffc000b0c8
.Lkd_runtime_ffffffffc000b0c4:
POPFQ
JMP .Lkd_exit_5
.Lkd_src_ffffffffc000b0c8:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0c8
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc000b0c8
JMP .Lkd_src_ffffffffc000b0ca
.Lkd_taken_ffffffffc000b0c8:
JMP .Lkd_src_ffffffffc000b0e3
.Lkd_runtime_ffffffffc000b0c8:
POPFQ
JMP .Lkd_exit_6
.Lkd_src_ffffffffc000b0ca:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0ca
DEC QWORD PTR[RBP - 120]
POPFQ
LEA RDX, QWORD PTR [0xFFFFFFFFC0606800 + 0x8 * RDX]
JMP .Lkd_src_ffffffffc000b0d2
.Lkd_runtime_ffffffffc000b0ca:
POPFQ
JMP .Lkd_exit_7
.Lkd_src_ffffffffc000b0d2:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0d2
DEC QWORD PTR[RBP - 120]
POPFQ
MOV QWORD PTR [RDI + 0x20], RDX
JMP .Lkd_src_ffffffffc000b0d6
.Lkd_runtime_ffffffffc000b0d2:
POPFQ
JMP .Lkd_exit_8
.Lkd_src_ffffffffc000b0d6:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0d6
DEC QWORD PTR[RBP - 120]
POPFQ
XOR EAX, EAX
JMP .Lkd_src_ffffffffc000b0d8
.Lkd_runtime_ffffffffc000b0d6:
POPFQ
JMP .Lkd_exit_9
.Lkd_src_ffffffffc000b0d8:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0d8
DEC QWORD PTR[RBP - 120]
POPFQ
XOR EDX, EDX
JMP .Lkd_src_ffffffffc000b0da
.Lkd_runtime_ffffffffc000b0d8:
POPFQ
JMP .Lkd_exit_10
.Lkd_src_ffffffffc000b0da:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0da
DEC QWORD PTR[RBP - 120]
POPFQ
XOR ESI, ESI
JMP .Lkd_src_ffffffffc000b0dc
.Lkd_runtime_ffffffffc000b0da:
POPFQ
JMP .Lkd_exit_11
.Lkd_src_ffffffffc000b0dc:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0dc
DEC QWORD PTR[RBP - 120]
POPFQ
XOR EDI, EDI
JMP .Lkd_src_ffffffffc000b0de
.Lkd_runtime_ffffffffc000b0dc:
POPFQ
JMP .Lkd_exit_12
.Lkd_src_ffffffffc000b0de:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0de
DEC QWORD PTR[RBP - 120]
POPFQ
JMP .Lkd_exit_14
.Lkd_runtime_ffffffffc000b0de:
POPFQ
JMP .Lkd_exit_13
.Lkd_src_ffffffffc000b0e3:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0e3
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, R12
LEA R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV QWORD PTR [R13], R15
JMP .Lkd_src_ffffffffc000b0e4
.Lkd_runtime_ffffffffc000b0e3:
POPFQ
JMP .Lkd_exit_15
.Lkd_src_ffffffffc000b0e4:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0e4
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RSI, RDX
JMP .Lkd_src_ffffffffc000b0e7
.Lkd_runtime_ffffffffc000b0e4:
POPFQ
JMP .Lkd_exit_16
.Lkd_src_ffffffffc000b0e7:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0e7
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R12, R13
JMP .Lkd_src_ffffffffc000b0ea
.Lkd_runtime_ffffffffc000b0e7:
POPFQ
JMP .Lkd_exit_17
.Lkd_src_ffffffffc000b0ea:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0ea
DEC QWORD PTR[RBP - 120]
POPFQ
SUB R13, 0x10
JMP .Lkd_src_ffffffffc000b0ee
.Lkd_runtime_ffffffffc000b0ea:
POPFQ
JMP .Lkd_exit_18
.Lkd_src_ffffffffc000b0ee:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0ee
DEC QWORD PTR[RBP - 120]
POPFQ
MOV QWORD PTR [R12 + 0xFFFFFFFFFFFFFFF0], RDI
JMP .Lkd_src_ffffffffc000b0f2
.Lkd_runtime_ffffffffc000b0ee:
POPFQ
JMP .Lkd_exit_19
.Lkd_src_ffffffffc000b0f2:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0f2
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, 0xFFFFFFFFC06080E0
JMP .Lkd_src_ffffffffc000b0f9
.Lkd_runtime_ffffffffc000b0f2:
POPFQ
JMP .Lkd_exit_20
.Lkd_src_ffffffffc000b0f9:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0f9
DEC QWORD PTR[RBP - 120]
POPFQ
MOV QWORD PTR [R12 + 0xFFFFFFFFFFFFFFF8], RDX
JMP .Lkd_src_ffffffffc000b0fd
.Lkd_runtime_ffffffffc000b0f9:
POPFQ
JMP .Lkd_exit_21
.Lkd_src_ffffffffc000b0fd:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0fd
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS R15, 0xFFFFFFFFC000B102
MOV R15, R15
LEA R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV QWORD PTR [R13], R15
MOVABS R14, 0xffffffff81dd3fd0
JMP .Lkd_exit_23
.Lkd_runtime_ffffffffc000b0fd:
POPFQ
JMP .Lkd_exit_22
.Lkd_src_ffffffffc000b1c2:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1c2
DEC QWORD PTR[RBP - 120]
POPFQ
CMP QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0], 0x41
JMP .Lkd_src_ffffffffc000b1c7
.Lkd_runtime_ffffffffc000b1c2:
POPFQ
JMP .Lkd_exit_24
.Lkd_src_ffffffffc000b1c7:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1c7
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc000b1c7
JMP .Lkd_src_ffffffffc000b1cd
.Lkd_taken_ffffffffc000b1c7:
JMP .Lkd_src_ffffffffc000b4cc
.Lkd_runtime_ffffffffc000b1c7:
POPFQ
JMP .Lkd_exit_25
.Lkd_src_ffffffffc000b1cd:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1cd
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RAX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc000b1d1
.Lkd_runtime_ffffffffc000b1cd:
POPFQ
JMP .Lkd_exit_26
.Lkd_src_ffffffffc000b1d1:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1d1
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RBX, QWORD PTR [0xFFFFFFFFC0606C00 + 0x8 * RAX]
JMP .Lkd_src_ffffffffc000b1d9
.Lkd_runtime_ffffffffc000b1d1:
POPFQ
JMP .Lkd_exit_27
.Lkd_src_ffffffffc000b1d9:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1d9
DEC QWORD PTR[RBP - 120]
POPFQ
CMP RAX, 0x41
JMP .Lkd_src_ffffffffc000b1dd
.Lkd_runtime_ffffffffc000b1d9:
POPFQ
JMP .Lkd_exit_28
.Lkd_src_ffffffffc000b1dd:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1dd
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc000b1dd
JMP .Lkd_src_ffffffffc000b1e3
.Lkd_taken_ffffffffc000b1dd:
JMP .Lkd_src_ffffffffc000b4b8
.Lkd_runtime_ffffffffc000b1dd:
POPFQ
JMP .Lkd_exit_29
.Lkd_src_ffffffffc000b1e3:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1e3
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RAX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc000b1e7
.Lkd_runtime_ffffffffc000b1e3:
POPFQ
JMP .Lkd_exit_30
.Lkd_src_ffffffffc000b1e7:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1e7
DEC QWORD PTR[RBP - 120]
POPFQ
ADD RBX, 0x1
JMP .Lkd_src_ffffffffc000b1eb
.Lkd_runtime_ffffffffc000b1e7:
POPFQ
JMP .Lkd_exit_31
.Lkd_src_ffffffffc000b1eb:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1eb
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RSI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFC8]
JMP .Lkd_src_ffffffffc000b1ef
.Lkd_runtime_ffffffffc000b1eb:
POPFQ
JMP .Lkd_exit_32
.Lkd_src_ffffffffc000b1ef:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1ef
DEC QWORD PTR[RBP - 120]
POPFQ
MOV QWORD PTR [0xFFFFFFFFC0606C00 + 0x8 * RAX], RBX
JMP .Lkd_src_ffffffffc000b1f7
.Lkd_runtime_ffffffffc000b1ef:
POPFQ
JMP .Lkd_exit_33
.Lkd_src_ffffffffc000b1f7:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1f7
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR[RBP - 56]
MOV RAX, R15
JMP .Lkd_src_ffffffffc000b1ff
.Lkd_runtime_ffffffffc000b1f7:
POPFQ
JMP .Lkd_exit_34
.Lkd_src_ffffffffc000b1ff:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1ff
DEC QWORD PTR[RBP - 120]
POPFQ
MOV QWORD PTR [RSI + 0x10], RAX
JMP .Lkd_src_ffffffffc000b203
.Lkd_runtime_ffffffffc000b1ff:
POPFQ
JMP .Lkd_exit_35
.Lkd_src_ffffffffc000b203:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b203
DEC QWORD PTR[RBP - 120]
POPFQ
MOV EAX, 0x10000
JMP .Lkd_src_ffffffffc000b208
.Lkd_runtime_ffffffffc000b203:
POPFQ
JMP .Lkd_exit_36
.Lkd_src_ffffffffc000b208:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b208
DEC QWORD PTR[RBP - 120]
POPFQ
SUB EAX, 0x2
JMP .Lkd_src_ffffffffc000b20b
.Lkd_runtime_ffffffffc000b208:
POPFQ
JMP .Lkd_exit_37
.Lkd_src_ffffffffc000b20b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b20b
DEC QWORD PTR[RBP - 120]
POPFQ
JNZ .Lkd_taken_ffffffffc000b20b
JMP .Lkd_src_ffffffffc000b20d
.Lkd_taken_ffffffffc000b20b:
JMP .Lkd_src_ffffffffc000b208
.Lkd_runtime_ffffffffc000b20b:
POPFQ
JMP .Lkd_exit_38
.Lkd_src_ffffffffc000b20d:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b20d
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RAX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFC8]
JMP .Lkd_src_ffffffffc000b211
.Lkd_runtime_ffffffffc000b20d:
POPFQ
JMP .Lkd_exit_39
.Lkd_src_ffffffffc000b211:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b211
DEC QWORD PTR[RBP - 120]
POPFQ
CMP DWORD PTR [RAX + 0x60], 0x3
JMP .Lkd_src_ffffffffc000b215
.Lkd_runtime_ffffffffc000b211:
POPFQ
JMP .Lkd_exit_40
.Lkd_src_ffffffffc000b215:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b215
DEC QWORD PTR[RBP - 120]
POPFQ
JZ .Lkd_taken_ffffffffc000b215
JMP .Lkd_src_ffffffffc000b21b
.Lkd_taken_ffffffffc000b215:
JMP .Lkd_src_ffffffffc000b3f0
.Lkd_runtime_ffffffffc000b215:
POPFQ
JMP .Lkd_exit_41
.Lkd_src_ffffffffc000b21b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b21b
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RBX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFC8]
JMP .Lkd_src_ffffffffc000b21f
.Lkd_runtime_ffffffffc000b21b:
POPFQ
JMP .Lkd_exit_42
.Lkd_src_ffffffffc000b21f:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b21f
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RAX, QWORD PTR [0xFFFFFFFFC0608468]
JMP .Lkd_src_ffffffffc000b226
.Lkd_runtime_ffffffffc000b21f:
POPFQ
JMP .Lkd_exit_43
.Lkd_src_ffffffffc000b226:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b226
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, RBX
JMP .Lkd_src_ffffffffc000b229
.Lkd_runtime_ffffffffc000b226:
POPFQ
JMP .Lkd_exit_44
.Lkd_src_ffffffffc000b229:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b229
DEC QWORD PTR[RBP - 120]
POPFQ
PUSH RAX
MOV RAX, RAX
MOV QWORD PTR[RBP - 88], RAX
POP RAX
MOV R14, QWORD PTR[RBP - 88]
PUSHFQ
MOVABS R15, 0xffffffffc000b0b0
CMP R14, R15
JE .Lkd_icall_stage_ffffffffc000b229
POPFQ
JMP .Lkd_exit_46
.Lkd_icall_stage_ffffffffc000b229:
POPFQ
MOVABS R15, 0xFFFFFFFFC000B22E
MOV R15, R15
LEA R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV QWORD PTR [R13], R15
MOV R14, QWORD PTR[RBP - 88]
PUSHFQ
MOVABS R15, 0xffffffffc000b0b0
CMP R14, R15
JE .Lkd_icall_ffffffffc000b229_ffffffffc000b0b0
POPFQ
JMP .Lkd_exit_47
.Lkd_icall_ffffffffc000b229_ffffffffc000b0b0:
POPFQ
JMP .Lkd_src_ffffffffc000b0b0
.Lkd_runtime_ffffffffc000b229:
POPFQ
JMP .Lkd_exit_45
.Lkd_src_ffffffffc000b270:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b270
DEC QWORD PTR[RBP - 120]
POPFQ
CMP QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0], 0x41
JMP .Lkd_src_ffffffffc000b275
.Lkd_runtime_ffffffffc000b270:
POPFQ
JMP .Lkd_exit_48
.Lkd_src_ffffffffc000b275:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b275
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc000b275
JMP .Lkd_src_ffffffffc000b27b
.Lkd_taken_ffffffffc000b275:
JMP .Lkd_src_ffffffffc000b48e
.Lkd_runtime_ffffffffc000b275:
POPFQ
JMP .Lkd_exit_49
.Lkd_src_ffffffffc000b27b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b27b
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RAX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc000b27f
.Lkd_runtime_ffffffffc000b27b:
POPFQ
JMP .Lkd_exit_50
.Lkd_src_ffffffffc000b27f:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b27f
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RBX, QWORD PTR [0xFFFFFFFFC0606A00 + 0x8 * RAX]
JMP .Lkd_src_ffffffffc000b287
.Lkd_runtime_ffffffffc000b27f:
POPFQ
JMP .Lkd_exit_51
.Lkd_src_ffffffffc000b287:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b287
DEC QWORD PTR[RBP - 120]
POPFQ
CMP RAX, 0x41
JMP .Lkd_src_ffffffffc000b28b
.Lkd_runtime_ffffffffc000b287:
POPFQ
JMP .Lkd_exit_52
.Lkd_src_ffffffffc000b28b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b28b
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc000b28b
JMP .Lkd_src_ffffffffc000b291
.Lkd_taken_ffffffffc000b28b:
JMP .Lkd_src_ffffffffc000b47a
.Lkd_runtime_ffffffffc000b28b:
POPFQ
JMP .Lkd_exit_53
.Lkd_src_ffffffffc000b291:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b291
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RAX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc000b295
.Lkd_runtime_ffffffffc000b291:
POPFQ
JMP .Lkd_exit_54
.Lkd_src_ffffffffc000b295:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b295
DEC QWORD PTR[RBP - 120]
POPFQ
ADD RBX, 0x1
JMP .Lkd_src_ffffffffc000b299
.Lkd_runtime_ffffffffc000b295:
POPFQ
JMP .Lkd_exit_55
.Lkd_src_ffffffffc000b299:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b299
DEC QWORD PTR[RBP - 120]
POPFQ
MOV QWORD PTR [0xFFFFFFFFC0606A00 + 0x8 * RAX], RBX
JMP .Lkd_src_ffffffffc000b2a1
.Lkd_runtime_ffffffffc000b299:
POPFQ
JMP .Lkd_exit_56
.Lkd_src_ffffffffc000b2a1:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2a1
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RBX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFC8]
JMP .Lkd_src_ffffffffc000b2a5
.Lkd_runtime_ffffffffc000b2a1:
POPFQ
JMP .Lkd_exit_57
.Lkd_src_ffffffffc000b2a5:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2a5
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RAX, QWORD PTR [0xFFFFFFFFC0608468]
JMP .Lkd_src_ffffffffc000b2ac
.Lkd_runtime_ffffffffc000b2a5:
POPFQ
JMP .Lkd_exit_58
.Lkd_src_ffffffffc000b2ac:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2ac
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, RBX
JMP .Lkd_src_ffffffffc000b2af
.Lkd_runtime_ffffffffc000b2ac:
POPFQ
JMP .Lkd_exit_59
.Lkd_src_ffffffffc000b2af:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2af
DEC QWORD PTR[RBP - 120]
POPFQ
PUSH RAX
MOV RAX, RAX
MOV QWORD PTR[RBP - 88], RAX
POP RAX
MOV R14, QWORD PTR[RBP - 88]
JMP .Lkd_exit_61
.Lkd_runtime_ffffffffc000b2af:
POPFQ
JMP .Lkd_exit_60
.Lkd_src_ffffffffc000b2db:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2db
DEC QWORD PTR[RBP - 120]
POPFQ
CMP QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0], 0x41
JMP .Lkd_src_ffffffffc000b2e0
.Lkd_runtime_ffffffffc000b2db:
POPFQ
JMP .Lkd_exit_62
.Lkd_src_ffffffffc000b2e0:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2e0
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc000b2e0
JMP .Lkd_src_ffffffffc000b2e6
.Lkd_taken_ffffffffc000b2e0:
JMP .Lkd_src_ffffffffc000b412
.Lkd_runtime_ffffffffc000b2e0:
POPFQ
JMP .Lkd_exit_63
.Lkd_src_ffffffffc000b2e6:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2e6
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFC0]
JMP .Lkd_src_ffffffffc000b2ea
.Lkd_runtime_ffffffffc000b2e6:
POPFQ
JMP .Lkd_exit_64
.Lkd_src_ffffffffc000b2ea:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2ea
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RSI, R13
JMP .Lkd_src_ffffffffc000b2ed
.Lkd_runtime_ffffffffc000b2ea:
POPFQ
JMP .Lkd_exit_65
.Lkd_src_ffffffffc000b2ed:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2ed
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS RDX, 0xFFFFFFFFC000B2FC
JMP .Lkd_src_ffffffffc000b2f4
.Lkd_runtime_ffffffffc000b2ed:
POPFQ
JMP .Lkd_exit_66
.Lkd_src_ffffffffc000b2f4:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2f4
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RCX, R12
JMP .Lkd_src_ffffffffc000b2f7
.Lkd_runtime_ffffffffc000b2f4:
POPFQ
JMP .Lkd_exit_67
.Lkd_src_ffffffffc000b2f7:
JMP .Lkd_exit_68
.Lkd_src_ffffffffc000b2fc:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2fc
DEC QWORD PTR[RBP - 120]
POPFQ
ADD R13, 0x20
JMP .Lkd_src_ffffffffc000b300
.Lkd_runtime_ffffffffc000b2fc:
POPFQ
JMP .Lkd_exit_69
.Lkd_src_ffffffffc000b300:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b300
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV RBX, R15
JMP .Lkd_src_ffffffffc000b301
.Lkd_runtime_ffffffffc000b300:
POPFQ
JMP .Lkd_exit_70
.Lkd_src_ffffffffc000b301:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b301
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R14, QWORD PTR[R11 + 48]
MOV R14, R15
MOV QWORD PTR[R11 + 48], R14
JMP .Lkd_src_ffffffffc000b303
.Lkd_runtime_ffffffffc000b301:
POPFQ
JMP .Lkd_exit_71
.Lkd_src_ffffffffc000b303:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b303
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R14, QWORD PTR[R11 + 40]
MOV R14, R15
MOV QWORD PTR[R11 + 40], R14
JMP .Lkd_src_ffffffffc000b305
.Lkd_runtime_ffffffffc000b303:
POPFQ
JMP .Lkd_exit_72
.Lkd_src_ffffffffc000b305:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b305
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R14, QWORD PTR[R11 + 32]
MOV R14, R15
MOV QWORD PTR[R11 + 32], R14
JMP .Lkd_src_ffffffffc000b307
.Lkd_runtime_ffffffffc000b305:
POPFQ
JMP .Lkd_exit_73
.Lkd_src_ffffffffc000b307:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b307
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R14, QWORD PTR[R11 + 24]
MOV R14, R15
MOV QWORD PTR[R11 + 24], R14
JMP .Lkd_src_ffffffffc000b309
.Lkd_runtime_ffffffffc000b307:
POPFQ
JMP .Lkd_exit_74
.Lkd_src_ffffffffc000b309:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b309
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R12, R15
JMP .Lkd_src_ffffffffc000b30a
.Lkd_runtime_ffffffffc000b309:
POPFQ
JMP .Lkd_exit_75
.Lkd_src_ffffffffc000b30a:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b30a
DEC QWORD PTR[RBP - 120]
POPFQ
XOR EAX, EAX
JMP .Lkd_src_ffffffffc000b30c
.Lkd_runtime_ffffffffc000b30a:
POPFQ
JMP .Lkd_exit_76
.Lkd_src_ffffffffc000b30c:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b30c
DEC QWORD PTR[RBP - 120]
POPFQ
XOR EDX, EDX
JMP .Lkd_src_ffffffffc000b30e
.Lkd_runtime_ffffffffc000b30c:
POPFQ
JMP .Lkd_exit_77
.Lkd_src_ffffffffc000b30e:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b30e
DEC QWORD PTR[RBP - 120]
POPFQ
XOR ECX, ECX
JMP .Lkd_src_ffffffffc000b310
.Lkd_runtime_ffffffffc000b30e:
POPFQ
JMP .Lkd_exit_78
.Lkd_src_ffffffffc000b310:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b310
DEC QWORD PTR[RBP - 120]
POPFQ
XOR ESI, ESI
JMP .Lkd_src_ffffffffc000b312
.Lkd_runtime_ffffffffc000b310:
POPFQ
JMP .Lkd_exit_79
.Lkd_src_ffffffffc000b312:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b312
DEC QWORD PTR[RBP - 120]
POPFQ
XOR EDI, EDI
JMP .Lkd_src_ffffffffc000b314
.Lkd_runtime_ffffffffc000b312:
POPFQ
JMP .Lkd_exit_80
.Lkd_src_ffffffffc000b314:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b314
DEC QWORD PTR[RBP - 120]
POPFQ
XOR R8D, R8D
JMP .Lkd_src_ffffffffc000b317
.Lkd_runtime_ffffffffc000b314:
POPFQ
JMP .Lkd_exit_81
.Lkd_src_ffffffffc000b317:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b317
DEC QWORD PTR[RBP - 120]
POPFQ
XOR R9D, R9D
JMP .Lkd_src_ffffffffc000b31a
.Lkd_runtime_ffffffffc000b317:
POPFQ
JMP .Lkd_exit_82
.Lkd_src_ffffffffc000b31a:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b31a
DEC QWORD PTR[RBP - 120]
POPFQ
XOR R10D, R10D
JMP .Lkd_src_ffffffffc000b31d
.Lkd_runtime_ffffffffc000b31a:
POPFQ
JMP .Lkd_exit_83
.Lkd_src_ffffffffc000b31d:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b31d
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR[R11 + 56]
XOR R15d, R15d
MOV QWORD PTR[R11 + 56], R15
JMP .Lkd_src_ffffffffc000b320
.Lkd_runtime_ffffffffc000b31d:
POPFQ
JMP .Lkd_exit_84
.Lkd_src_ffffffffc000b320:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b320
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R15, R15
MOV QWORD PTR[RBP - 88], R15
MOV R14, QWORD PTR[RBP - 88]
PUSHFQ
POPFQ
JMP .Lkd_exit_86
.Lkd_runtime_ffffffffc000b320:
POPFQ
JMP .Lkd_exit_85
.Lkd_src_ffffffffc000b346:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b346
DEC QWORD PTR[RBP - 120]
POPFQ
CMP QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0], 0x41
JMP .Lkd_src_ffffffffc000b34b
.Lkd_runtime_ffffffffc000b346:
POPFQ
JMP .Lkd_exit_87
.Lkd_src_ffffffffc000b34b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b34b
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc000b34b
JMP .Lkd_src_ffffffffc000b351
.Lkd_taken_ffffffffc000b34b:
JMP .Lkd_src_ffffffffc000b43c
.Lkd_runtime_ffffffffc000b34b:
POPFQ
JMP .Lkd_exit_88
.Lkd_src_ffffffffc000b351:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b351
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RAX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc000b355
.Lkd_runtime_ffffffffc000b351:
POPFQ
JMP .Lkd_exit_89
.Lkd_src_ffffffffc000b355:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b355
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RBX, QWORD PTR [0xFFFFFFFFC0606A00 + 0x8 * RAX]
JMP .Lkd_src_ffffffffc000b35d
.Lkd_runtime_ffffffffc000b355:
POPFQ
JMP .Lkd_exit_90
.Lkd_src_ffffffffc000b35d:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b35d
DEC QWORD PTR[RBP - 120]
POPFQ
CMP RAX, 0x41
JMP .Lkd_src_ffffffffc000b361
.Lkd_runtime_ffffffffc000b35d:
POPFQ
JMP .Lkd_exit_91
.Lkd_src_ffffffffc000b361:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b361
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc000b361
JMP .Lkd_src_ffffffffc000b367
.Lkd_taken_ffffffffc000b361:
JMP .Lkd_src_ffffffffc000b451
.Lkd_runtime_ffffffffc000b361:
POPFQ
JMP .Lkd_exit_92
.Lkd_src_ffffffffc000b367:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b367
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR[R11 + 32]
MOV R15, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
MOV QWORD PTR[R11 + 32], R15
JMP .Lkd_src_ffffffffc000b36b
.Lkd_runtime_ffffffffc000b367:
POPFQ
JMP .Lkd_exit_93
.Lkd_src_ffffffffc000b36b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b36b
DEC QWORD PTR[RBP - 120]
POPFQ
ADD RBX, 0x1
JMP .Lkd_src_ffffffffc000b36f
.Lkd_runtime_ffffffffc000b36b:
POPFQ
JMP .Lkd_exit_94
.Lkd_src_ffffffffc000b36f:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b36f
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFC8]
JMP .Lkd_src_ffffffffc000b373
.Lkd_runtime_ffffffffc000b36f:
POPFQ
JMP .Lkd_exit_95
.Lkd_src_ffffffffc000b373:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b373
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR[R11 + 32]
MOV QWORD PTR [0xFFFFFFFFC0606A00 + 0x8 * R15], RBX
JMP .Lkd_src_ffffffffc000b37b
.Lkd_runtime_ffffffffc000b373:
POPFQ
JMP .Lkd_exit_96
.Lkd_src_ffffffffc000b37b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b37b
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RAX, QWORD PTR [0xFFFFFFFFC0608468]
JMP .Lkd_src_ffffffffc000b382
.Lkd_runtime_ffffffffc000b37b:
POPFQ
JMP .Lkd_exit_97
.Lkd_src_ffffffffc000b382:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b382
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS R15, 0xFFFFFFFFC000B387
MOV R15, R15
LEA R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV QWORD PTR [R13], R15
MOVABS R14, 0xffffffffc0010020
JMP .Lkd_src_ffffffffc0010020
.Lkd_runtime_ffffffffc000b382:
POPFQ
JMP .Lkd_exit_98
.Lkd_src_ffffffffc000b3a7:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3a7
DEC QWORD PTR[RBP - 120]
POPFQ
ADD R13, 0x20
JMP .Lkd_src_ffffffffc000b3ab
.Lkd_runtime_ffffffffc000b3a7:
POPFQ
JMP .Lkd_exit_99
.Lkd_src_ffffffffc000b3ab:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3ab
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV RBX, R15
JMP .Lkd_src_ffffffffc000b3ac
.Lkd_runtime_ffffffffc000b3ab:
POPFQ
JMP .Lkd_exit_100
.Lkd_src_ffffffffc000b3ac:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3ac
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R14, QWORD PTR[R11 + 48]
MOV R14, R15
MOV QWORD PTR[R11 + 48], R14
JMP .Lkd_src_ffffffffc000b3ae
.Lkd_runtime_ffffffffc000b3ac:
POPFQ
JMP .Lkd_exit_101
.Lkd_src_ffffffffc000b3ae:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3ae
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R14, QWORD PTR[R11 + 40]
MOV R14, R15
MOV QWORD PTR[R11 + 40], R14
JMP .Lkd_src_ffffffffc000b3b0
.Lkd_runtime_ffffffffc000b3ae:
POPFQ
JMP .Lkd_exit_102
.Lkd_src_ffffffffc000b3b0:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3b0
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R14, QWORD PTR[R11 + 32]
MOV R14, R15
MOV QWORD PTR[R11 + 32], R14
JMP .Lkd_src_ffffffffc000b3b2
.Lkd_runtime_ffffffffc000b3b0:
POPFQ
JMP .Lkd_exit_103
.Lkd_src_ffffffffc000b3b2:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3b2
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R14, QWORD PTR[R11 + 24]
MOV R14, R15
MOV QWORD PTR[R11 + 24], R14
JMP .Lkd_src_ffffffffc000b3b4
.Lkd_runtime_ffffffffc000b3b2:
POPFQ
JMP .Lkd_exit_104
.Lkd_src_ffffffffc000b3b4:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3b4
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R12, R15
JMP .Lkd_src_ffffffffc000b3b5
.Lkd_runtime_ffffffffc000b3b4:
POPFQ
JMP .Lkd_exit_105
.Lkd_src_ffffffffc000b3b5:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3b5
DEC QWORD PTR[RBP - 120]
POPFQ
XOR EAX, EAX
JMP .Lkd_src_ffffffffc000b3b7
.Lkd_runtime_ffffffffc000b3b5:
POPFQ
JMP .Lkd_exit_106
.Lkd_src_ffffffffc000b3b7:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3b7
DEC QWORD PTR[RBP - 120]
POPFQ
XOR EDX, EDX
JMP .Lkd_src_ffffffffc000b3b9
.Lkd_runtime_ffffffffc000b3b7:
POPFQ
JMP .Lkd_exit_107
.Lkd_src_ffffffffc000b3b9:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3b9
DEC QWORD PTR[RBP - 120]
POPFQ
XOR ECX, ECX
JMP .Lkd_src_ffffffffc000b3bb
.Lkd_runtime_ffffffffc000b3b9:
POPFQ
JMP .Lkd_exit_108
.Lkd_src_ffffffffc000b3bb:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3bb
DEC QWORD PTR[RBP - 120]
POPFQ
XOR ESI, ESI
JMP .Lkd_src_ffffffffc000b3bd
.Lkd_runtime_ffffffffc000b3bb:
POPFQ
JMP .Lkd_exit_109
.Lkd_src_ffffffffc000b3bd:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3bd
DEC QWORD PTR[RBP - 120]
POPFQ
XOR EDI, EDI
JMP .Lkd_src_ffffffffc000b3bf
.Lkd_runtime_ffffffffc000b3bd:
POPFQ
JMP .Lkd_exit_110
.Lkd_src_ffffffffc000b3bf:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3bf
DEC QWORD PTR[RBP - 120]
POPFQ
XOR R8D, R8D
JMP .Lkd_src_ffffffffc000b3c2
.Lkd_runtime_ffffffffc000b3bf:
POPFQ
JMP .Lkd_exit_111
.Lkd_src_ffffffffc000b3c2:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3c2
DEC QWORD PTR[RBP - 120]
POPFQ
XOR R9D, R9D
JMP .Lkd_src_ffffffffc000b3c5
.Lkd_runtime_ffffffffc000b3c2:
POPFQ
JMP .Lkd_exit_112
.Lkd_src_ffffffffc000b3c5:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3c5
DEC QWORD PTR[RBP - 120]
POPFQ
XOR R10D, R10D
JMP .Lkd_src_ffffffffc000b3c8
.Lkd_runtime_ffffffffc000b3c5:
POPFQ
JMP .Lkd_exit_113
.Lkd_src_ffffffffc000b3c8:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3c8
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR[R11 + 56]
XOR R15d, R15d
MOV QWORD PTR[R11 + 56], R15
JMP .Lkd_src_ffffffffc000b3cb
.Lkd_runtime_ffffffffc000b3c8:
POPFQ
JMP .Lkd_exit_114
.Lkd_src_ffffffffc000b3cb:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3cb
DEC QWORD PTR[RBP - 120]
POPFQ
JMP .Lkd_exit_116
.Lkd_runtime_ffffffffc000b3cb:
POPFQ
JMP .Lkd_exit_115
.Lkd_src_ffffffffc000b3f0:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3f0
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, RAX
JMP .Lkd_src_ffffffffc000b3f3
.Lkd_runtime_ffffffffc000b3f0:
POPFQ
JMP .Lkd_exit_117
.Lkd_src_ffffffffc000b3f3:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3f3
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS R15, 0xFFFFFFFFC000B3F8
MOV R15, R15
LEA R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV QWORD PTR [R13], R15
MOVABS R14, 0xffffffffc000b140
JMP .Lkd_exit_119
.Lkd_runtime_ffffffffc000b3f3:
POPFQ
JMP .Lkd_exit_118
.Lkd_src_ffffffffc000b412:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b412
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RSI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc000b416
.Lkd_runtime_ffffffffc000b412:
POPFQ
JMP .Lkd_exit_120
.Lkd_src_ffffffffc000b416:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b416
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, 0xFFFFFFFFC0607F20
JMP .Lkd_src_ffffffffc000b41d
.Lkd_runtime_ffffffffc000b416:
POPFQ
JMP .Lkd_exit_121
.Lkd_src_ffffffffc000b41d:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b41d
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS R15, 0xFFFFFFFFC000B422
MOV R15, R15
LEA R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV QWORD PTR [R13], R15
MOVABS R14, 0xffffffff81dd3fd0
JMP .Lkd_exit_123
.Lkd_runtime_ffffffffc000b41d:
POPFQ
JMP .Lkd_exit_122
.Lkd_src_ffffffffc000b43c:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b43c
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RSI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc000b440
.Lkd_runtime_ffffffffc000b43c:
POPFQ
JMP .Lkd_exit_124
.Lkd_src_ffffffffc000b440:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b440
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, 0xFFFFFFFFC0607FA0
JMP .Lkd_src_ffffffffc000b447
.Lkd_runtime_ffffffffc000b440:
POPFQ
JMP .Lkd_exit_125
.Lkd_src_ffffffffc000b447:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b447
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS R15, 0xFFFFFFFFC000B44C
MOV R15, R15
LEA R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV QWORD PTR [R13], R15
MOVABS R14, 0xffffffff81dd3fd0
JMP .Lkd_exit_127
.Lkd_runtime_ffffffffc000b447:
POPFQ
JMP .Lkd_exit_126
.Lkd_src_ffffffffc000b451:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b451
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RSI, RAX
JMP .Lkd_src_ffffffffc000b454
.Lkd_runtime_ffffffffc000b451:
POPFQ
JMP .Lkd_exit_128
.Lkd_src_ffffffffc000b454:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b454
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, 0xFFFFFFFFC0607F80
JMP .Lkd_src_ffffffffc000b45b
.Lkd_runtime_ffffffffc000b454:
POPFQ
JMP .Lkd_exit_129
.Lkd_src_ffffffffc000b45b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b45b
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS R15, 0xFFFFFFFFC000B460
MOV R15, R15
LEA R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV QWORD PTR [R13], R15
MOVABS R14, 0xffffffff81dd3fd0
JMP .Lkd_exit_131
.Lkd_runtime_ffffffffc000b45b:
POPFQ
JMP .Lkd_exit_130
.Lkd_src_ffffffffc000b47a:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b47a
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RSI, RAX
JMP .Lkd_src_ffffffffc000b47d
.Lkd_runtime_ffffffffc000b47a:
POPFQ
JMP .Lkd_exit_132
.Lkd_src_ffffffffc000b47d:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b47d
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, 0xFFFFFFFFC0607FE0
JMP .Lkd_src_ffffffffc000b484
.Lkd_runtime_ffffffffc000b47d:
POPFQ
JMP .Lkd_exit_133
.Lkd_src_ffffffffc000b484:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b484
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS R15, 0xFFFFFFFFC000B489
MOV R15, R15
LEA R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV QWORD PTR [R13], R15
MOVABS R14, 0xffffffff81dd3fd0
JMP .Lkd_exit_135
.Lkd_runtime_ffffffffc000b484:
POPFQ
JMP .Lkd_exit_134
.Lkd_src_ffffffffc000b48e:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b48e
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RSI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc000b492
.Lkd_runtime_ffffffffc000b48e:
POPFQ
JMP .Lkd_exit_136
.Lkd_src_ffffffffc000b492:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b492
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, 0xFFFFFFFFC0608000
JMP .Lkd_src_ffffffffc000b499
.Lkd_runtime_ffffffffc000b492:
POPFQ
JMP .Lkd_exit_137
.Lkd_src_ffffffffc000b499:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b499
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS R15, 0xFFFFFFFFC000B49E
MOV R15, R15
LEA R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV QWORD PTR [R13], R15
MOVABS R14, 0xffffffff81dd3fd0
JMP .Lkd_exit_139
.Lkd_runtime_ffffffffc000b499:
POPFQ
JMP .Lkd_exit_138
.Lkd_src_ffffffffc000b4b8:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b4b8
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RSI, RAX
JMP .Lkd_src_ffffffffc000b4bb
.Lkd_runtime_ffffffffc000b4b8:
POPFQ
JMP .Lkd_exit_140
.Lkd_src_ffffffffc000b4bb:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b4bb
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, 0xFFFFFFFFC0608060
JMP .Lkd_src_ffffffffc000b4c2
.Lkd_runtime_ffffffffc000b4bb:
POPFQ
JMP .Lkd_exit_141
.Lkd_src_ffffffffc000b4c2:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b4c2
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS R15, 0xFFFFFFFFC000B4C7
MOV R15, R15
LEA R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV QWORD PTR [R13], R15
MOVABS R14, 0xffffffff81dd3fd0
JMP .Lkd_exit_143
.Lkd_runtime_ffffffffc000b4c2:
POPFQ
JMP .Lkd_exit_142
.Lkd_src_ffffffffc000b4cc:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b4cc
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RSI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc000b4d0
.Lkd_runtime_ffffffffc000b4cc:
POPFQ
JMP .Lkd_exit_144
.Lkd_src_ffffffffc000b4d0:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b4d0
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, 0xFFFFFFFFC0608080
JMP .Lkd_src_ffffffffc000b4d7
.Lkd_runtime_ffffffffc000b4d0:
POPFQ
JMP .Lkd_exit_145
.Lkd_src_ffffffffc000b4d7:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b4d7
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS R15, 0xFFFFFFFFC000B4DC
MOV R15, R15
LEA R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV QWORD PTR [R13], R15
MOVABS R14, 0xffffffff81dd3fd0
JMP .Lkd_exit_147
.Lkd_runtime_ffffffffc000b4d7:
POPFQ
JMP .Lkd_exit_146
.Lkd_src_ffffffffc0010020:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc0010020
DEC QWORD PTR[RBP - 120]
POPFQ
PUSH RAX
MOV RAX, RAX
MOV QWORD PTR[RBP - 88], RAX
POP RAX
MOV R14, QWORD PTR[RBP - 88]
JMP .Lkd_exit_149
.Lkd_runtime_ffffffffc0010020:
POPFQ
JMP .Lkd_exit_148
.Lkd_exit_0:
MOV QWORD PTR[RBP - 72], R14
MOV QWORD PTR[RBP - 80], R14
MOV QWORD PTR[RBP - 88], R14
MOV QWORD PTR[RBP - 96], 6
MOV QWORD PTR[RBP - 104], 0
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_1:
MOVABS R15, 0xffffffffc000b0b0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0b0
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_2:
MOVABS R15, 0xffffffffc000b0b8
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0b8
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_3:
MOVABS R15, 0xffffffffc000b0bd
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0bd
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_4:
MOVABS R15, 0xffffffffc000b0c1
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0c1
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_5:
MOVABS R15, 0xffffffffc000b0c4
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0c4
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_6:
MOVABS R15, 0xffffffffc000b0c8
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0c8
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_7:
MOVABS R15, 0xffffffffc000b0ca
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0ca
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_8:
MOVABS R15, 0xffffffffc000b0d2
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0d2
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_9:
MOVABS R15, 0xffffffffc000b0d6
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0d6
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_10:
MOVABS R15, 0xffffffffc000b0d8
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0d8
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_11:
MOVABS R15, 0xffffffffc000b0da
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0da
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_12:
MOVABS R15, 0xffffffffc000b0dc
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0dc
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_13:
MOVABS R15, 0xffffffffc000b0de
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0de
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_14:
MOVABS R15, 0xffffffff8271be20
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0de
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff8271be20
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 4
JMP .Lkd_export
.Lkd_exit_15:
MOVABS R15, 0xffffffffc000b0e3
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0e3
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_16:
MOVABS R15, 0xffffffffc000b0e4
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0e4
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_17:
MOVABS R15, 0xffffffffc000b0e7
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0e7
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_18:
MOVABS R15, 0xffffffffc000b0ea
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0ea
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_19:
MOVABS R15, 0xffffffffc000b0ee
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0ee
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_20:
MOVABS R15, 0xffffffffc000b0f2
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0f2
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_21:
MOVABS R15, 0xffffffffc000b0f9
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0f9
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_22:
MOVABS R15, 0xffffffffc000b0fd
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0fd
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_23:
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0fd
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_24:
MOVABS R15, 0xffffffffc000b1c2
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1c2
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_25:
MOVABS R15, 0xffffffffc000b1c7
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1c7
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_26:
MOVABS R15, 0xffffffffc000b1cd
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1cd
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_27:
MOVABS R15, 0xffffffffc000b1d1
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1d1
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_28:
MOVABS R15, 0xffffffffc000b1d9
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1d9
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_29:
MOVABS R15, 0xffffffffc000b1dd
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1dd
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_30:
MOVABS R15, 0xffffffffc000b1e3
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1e3
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_31:
MOVABS R15, 0xffffffffc000b1e7
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1e7
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_32:
MOVABS R15, 0xffffffffc000b1eb
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1eb
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_33:
MOVABS R15, 0xffffffffc000b1ef
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1ef
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_34:
MOVABS R15, 0xffffffffc000b1f7
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1f7
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_35:
MOVABS R15, 0xffffffffc000b1ff
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1ff
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_36:
MOVABS R15, 0xffffffffc000b203
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b203
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_37:
MOVABS R15, 0xffffffffc000b208
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b208
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_38:
MOVABS R15, 0xffffffffc000b20b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b20b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_39:
MOVABS R15, 0xffffffffc000b20d
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b20d
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_40:
MOVABS R15, 0xffffffffc000b211
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b211
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_41:
MOVABS R15, 0xffffffffc000b215
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b215
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_42:
MOVABS R15, 0xffffffffc000b21b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b21b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_43:
MOVABS R15, 0xffffffffc000b21f
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b21f
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_44:
MOVABS R15, 0xffffffffc000b226
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b226
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_45:
MOVABS R15, 0xffffffffc000b229
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b229
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_46:
MOVABS R15, 0xffffffffc000b229
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b229
MOV QWORD PTR[RBP - 80], R15
MOV QWORD PTR[RBP - 88], R14
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 10
MOV QWORD PTR[RBP - 112], 1
JMP .Lkd_export
.Lkd_exit_47:
MOV QWORD PTR[RBP - 72], R14
MOVABS R15, 0xffffffffc000b229
MOV QWORD PTR[RBP - 80], R15
MOV QWORD PTR[RBP - 88], R14
MOV QWORD PTR[RBP - 96], 7
MOV QWORD PTR[RBP - 104], 10
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_48:
MOVABS R15, 0xffffffffc000b270
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b270
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_49:
MOVABS R15, 0xffffffffc000b275
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b275
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_50:
MOVABS R15, 0xffffffffc000b27b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b27b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_51:
MOVABS R15, 0xffffffffc000b27f
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b27f
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_52:
MOVABS R15, 0xffffffffc000b287
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b287
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_53:
MOVABS R15, 0xffffffffc000b28b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b28b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_54:
MOVABS R15, 0xffffffffc000b291
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b291
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_55:
MOVABS R15, 0xffffffffc000b295
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b295
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_56:
MOVABS R15, 0xffffffffc000b299
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b299
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_57:
MOVABS R15, 0xffffffffc000b2a1
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2a1
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_58:
MOVABS R15, 0xffffffffc000b2a5
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2a5
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_59:
MOVABS R15, 0xffffffffc000b2ac
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2ac
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_60:
MOVABS R15, 0xffffffffc000b2af
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2af
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_61:
MOVABS R15, 0xffffffffc000b2af
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2af
MOV QWORD PTR[RBP - 80], R15
MOV QWORD PTR[RBP - 88], R14
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 10
MOV QWORD PTR[RBP - 112], 1
JMP .Lkd_export
.Lkd_exit_62:
MOVABS R15, 0xffffffffc000b2db
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2db
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_63:
MOVABS R15, 0xffffffffc000b2e0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2e0
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_64:
MOVABS R15, 0xffffffffc000b2e6
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2e6
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_65:
MOVABS R15, 0xffffffffc000b2ea
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2ea
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_66:
MOVABS R15, 0xffffffffc000b2ed
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2ed
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_67:
MOVABS R15, 0xffffffffc000b2f4
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2f4
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_68:
MOVABS R15, 0xffffffffc000b2f7
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2f7
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff815148e0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 1
MOV QWORD PTR[RBP - 104], 2
MOV QWORD PTR[RBP - 112], 1
JMP .Lkd_export
.Lkd_exit_69:
MOVABS R15, 0xffffffffc000b2fc
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2fc
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_70:
MOVABS R15, 0xffffffffc000b300
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b300
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_71:
MOVABS R15, 0xffffffffc000b301
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b301
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_72:
MOVABS R15, 0xffffffffc000b303
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b303
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_73:
MOVABS R15, 0xffffffffc000b305
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b305
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_74:
MOVABS R15, 0xffffffffc000b307
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b307
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_75:
MOVABS R15, 0xffffffffc000b309
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b309
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_76:
MOVABS R15, 0xffffffffc000b30a
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b30a
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_77:
MOVABS R15, 0xffffffffc000b30c
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b30c
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_78:
MOVABS R15, 0xffffffffc000b30e
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b30e
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_79:
MOVABS R15, 0xffffffffc000b310
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b310
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_80:
MOVABS R15, 0xffffffffc000b312
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b312
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_81:
MOVABS R15, 0xffffffffc000b314
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b314
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_82:
MOVABS R15, 0xffffffffc000b317
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b317
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_83:
MOVABS R15, 0xffffffffc000b31a
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b31a
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_84:
MOVABS R15, 0xffffffffc000b31d
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b31d
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_85:
MOVABS R15, 0xffffffffc000b320
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b320
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_86:
MOV QWORD PTR[RBP - 72], R14
MOVABS R15, 0xffffffffc000b320
MOV QWORD PTR[RBP - 80], R15
MOV QWORD PTR[RBP - 88], R14
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 11
MOV QWORD PTR[RBP - 112], 3
JMP .Lkd_export
.Lkd_exit_87:
MOVABS R15, 0xffffffffc000b346
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b346
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_88:
MOVABS R15, 0xffffffffc000b34b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b34b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_89:
MOVABS R15, 0xffffffffc000b351
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b351
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_90:
MOVABS R15, 0xffffffffc000b355
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b355
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_91:
MOVABS R15, 0xffffffffc000b35d
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b35d
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_92:
MOVABS R15, 0xffffffffc000b361
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b361
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_93:
MOVABS R15, 0xffffffffc000b367
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b367
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_94:
MOVABS R15, 0xffffffffc000b36b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b36b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_95:
MOVABS R15, 0xffffffffc000b36f
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b36f
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_96:
MOVABS R15, 0xffffffffc000b373
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b373
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_97:
MOVABS R15, 0xffffffffc000b37b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b37b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_98:
MOVABS R15, 0xffffffffc000b382
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b382
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_99:
MOVABS R15, 0xffffffffc000b3a7
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3a7
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_100:
MOVABS R15, 0xffffffffc000b3ab
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3ab
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_101:
MOVABS R15, 0xffffffffc000b3ac
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3ac
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_102:
MOVABS R15, 0xffffffffc000b3ae
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3ae
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_103:
MOVABS R15, 0xffffffffc000b3b0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3b0
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_104:
MOVABS R15, 0xffffffffc000b3b2
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3b2
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_105:
MOVABS R15, 0xffffffffc000b3b4
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3b4
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_106:
MOVABS R15, 0xffffffffc000b3b5
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3b5
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_107:
MOVABS R15, 0xffffffffc000b3b7
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3b7
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_108:
MOVABS R15, 0xffffffffc000b3b9
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3b9
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_109:
MOVABS R15, 0xffffffffc000b3bb
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3bb
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_110:
MOVABS R15, 0xffffffffc000b3bd
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3bd
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_111:
MOVABS R15, 0xffffffffc000b3bf
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3bf
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_112:
MOVABS R15, 0xffffffffc000b3c2
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3c2
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_113:
MOVABS R15, 0xffffffffc000b3c5
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3c5
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_114:
MOVABS R15, 0xffffffffc000b3c8
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3c8
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_115:
MOVABS R15, 0xffffffffc000b3cb
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3cb
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_116:
MOVABS R15, 0xffffffff8271be20
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3cb
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff8271be20
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 4
JMP .Lkd_export
.Lkd_exit_117:
MOVABS R15, 0xffffffffc000b3f0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3f0
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_118:
MOVABS R15, 0xffffffffc000b3f3
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3f3
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_119:
MOVABS R15, 0xffffffffc000b140
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3f3
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffffc000b140
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_120:
MOVABS R15, 0xffffffffc000b412
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b412
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_121:
MOVABS R15, 0xffffffffc000b416
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b416
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_122:
MOVABS R15, 0xffffffffc000b41d
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b41d
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_123:
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b41d
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_124:
MOVABS R15, 0xffffffffc000b43c
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b43c
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_125:
MOVABS R15, 0xffffffffc000b440
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b440
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_126:
MOVABS R15, 0xffffffffc000b447
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b447
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_127:
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b447
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_128:
MOVABS R15, 0xffffffffc000b451
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b451
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_129:
MOVABS R15, 0xffffffffc000b454
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b454
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_130:
MOVABS R15, 0xffffffffc000b45b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b45b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_131:
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b45b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_132:
MOVABS R15, 0xffffffffc000b47a
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b47a
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_133:
MOVABS R15, 0xffffffffc000b47d
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b47d
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_134:
MOVABS R15, 0xffffffffc000b484
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b484
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_135:
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b484
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_136:
MOVABS R15, 0xffffffffc000b48e
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b48e
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_137:
MOVABS R15, 0xffffffffc000b492
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b492
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_138:
MOVABS R15, 0xffffffffc000b499
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b499
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_139:
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b499
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_140:
MOVABS R15, 0xffffffffc000b4b8
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b4b8
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_141:
MOVABS R15, 0xffffffffc000b4bb
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b4bb
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_142:
MOVABS R15, 0xffffffffc000b4c2
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b4c2
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_143:
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b4c2
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_144:
MOVABS R15, 0xffffffffc000b4cc
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b4cc
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_145:
MOVABS R15, 0xffffffffc000b4d0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b4d0
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_146:
MOVABS R15, 0xffffffffc000b4d7
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b4d7
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_147:
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b4d7
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_148:
MOVABS R15, 0xffffffffc0010020
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc0010020
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_149:
MOV QWORD PTR[RBP - 72], R14
MOVABS R15, 0xffffffffc0010020
MOV QWORD PTR[RBP - 80], R15
MOV QWORD PTR[RBP - 88], R14
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 10
MOV QWORD PTR[RBP - 112], 4
JMP .Lkd_export
.Lkd_export:
 mov QWORD PTR[R11 + 16], r12
 mov QWORD PTR[R11 + 8], r13
 mov QWORD PTR[R11 + 64], rbx
 mov QWORD PTR[R11 + 72], r10
 mov QWORD PTR[R11 + 80], r9
 mov QWORD PTR[R11 + 88], r8
 mov QWORD PTR[R11 + 96], rax
 mov QWORD PTR[R11 + 104], rcx
 mov QWORD PTR[R11 + 112], rdx
 mov QWORD PTR[R11 + 120], rsi
 mov QWORD PTR[R11 + 128], rdi
 mov rax, QWORD PTR[RBP - 72]
 mov QWORD PTR[R11 + 0], rax
 mov r14, QWORD PTR[RBP - 64]
 mov rax, QWORD PTR[RBP - 96]
 mov QWORD PTR[r14 + 16], rax
 mov rax, QWORD PTR[RBP - 104]
 mov QWORD PTR[r14 + 24], rax
 mov rax, QWORD PTR[RBP - 80]
 mov QWORD PTR[r14 + 32], rax
 mov rax, QWORD PTR[RBP - 88]
 mov QWORD PTR[r14 + 40], rax
 mov rax, QWORD PTR[RBP - 112]
 mov QWORD PTR[r14 + 48], rax
 lea rsp, [rbp - 40]
 pop r15
 pop r14
 pop r13
 pop r12
 pop rbx
 pop rbp
 ret
 .size kd_fixture_entry, .-kd_fixture_entry
 .section .note.GNU-stack, "", @progbits
