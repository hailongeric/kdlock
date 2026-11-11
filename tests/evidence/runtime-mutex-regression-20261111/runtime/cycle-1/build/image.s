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
MOVABS R15, 0xffffffffc000b0f2
CMP R14, R15
JE .Lkd_enter_ffffffffc000b0f2
MOVABS R15, 0xffffffffc000b189
CMP R14, R15
JE .Lkd_enter_ffffffffc000b189
MOVABS R15, 0xffffffffc000b1f4
CMP R14, R15
JE .Lkd_enter_ffffffffc000b1f4
MOVABS R15, 0xffffffffc000b215
CMP R14, R15
JE .Lkd_enter_ffffffffc000b215
MOVABS R15, 0xffffffffc000b25f
CMP R14, R15
JE .Lkd_enter_ffffffffc000b25f
MOVABS R15, 0xffffffffc000b2c0
CMP R14, R15
JE .Lkd_enter_ffffffffc000b2c0
POPFQ
JMP .Lkd_exit_0
.Lkd_enter_ffffffffc000b0f2:
POPFQ
JMP .Lkd_src_ffffffffc000b0f2
.Lkd_enter_ffffffffc000b189:
POPFQ
JMP .Lkd_src_ffffffffc000b189
.Lkd_enter_ffffffffc000b1f4:
POPFQ
JMP .Lkd_src_ffffffffc000b1f4
.Lkd_enter_ffffffffc000b215:
POPFQ
JMP .Lkd_src_ffffffffc000b215
.Lkd_enter_ffffffffc000b25f:
POPFQ
JMP .Lkd_src_ffffffffc000b25f
.Lkd_enter_ffffffffc000b2c0:
POPFQ
JMP .Lkd_src_ffffffffc000b2c0
.Lkd_src_ffffffffc000b0f2:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0f2
DEC QWORD PTR[RBP - 120]
POPFQ
CMP QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0], 0x41
JMP .Lkd_src_ffffffffc000b0f7
.Lkd_runtime_ffffffffc000b0f2:
POPFQ
JMP .Lkd_exit_1
.Lkd_src_ffffffffc000b0f7:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0f7
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc000b0f7
JMP .Lkd_src_ffffffffc000b0fd
.Lkd_taken_ffffffffc000b0f7:
JMP .Lkd_src_ffffffffc000b3d8
.Lkd_runtime_ffffffffc000b0f7:
POPFQ
JMP .Lkd_exit_2
.Lkd_src_ffffffffc000b0fd:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b0fd
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RAX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc000b101
.Lkd_runtime_ffffffffc000b0fd:
POPFQ
JMP .Lkd_exit_3
.Lkd_src_ffffffffc000b101:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b101
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RBX, QWORD PTR [0xFFFFFFFFC0606B80 + 0x8 * RAX]
JMP .Lkd_src_ffffffffc000b109
.Lkd_runtime_ffffffffc000b101:
POPFQ
JMP .Lkd_exit_4
.Lkd_src_ffffffffc000b109:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b109
DEC QWORD PTR[RBP - 120]
POPFQ
CMP RAX, 0x41
JMP .Lkd_src_ffffffffc000b10d
.Lkd_runtime_ffffffffc000b109:
POPFQ
JMP .Lkd_exit_5
.Lkd_src_ffffffffc000b10d:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b10d
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc000b10d
JMP .Lkd_src_ffffffffc000b113
.Lkd_taken_ffffffffc000b10d:
JMP .Lkd_src_ffffffffc000b3c4
.Lkd_runtime_ffffffffc000b10d:
POPFQ
JMP .Lkd_exit_6
.Lkd_src_ffffffffc000b113:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b113
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RAX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc000b117
.Lkd_runtime_ffffffffc000b113:
POPFQ
JMP .Lkd_exit_7
.Lkd_src_ffffffffc000b117:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b117
DEC QWORD PTR[RBP - 120]
POPFQ
ADD RBX, 0x1
JMP .Lkd_src_ffffffffc000b11b
.Lkd_runtime_ffffffffc000b117:
POPFQ
JMP .Lkd_exit_8
.Lkd_src_ffffffffc000b11b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b11b
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RSI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFC8]
JMP .Lkd_src_ffffffffc000b11f
.Lkd_runtime_ffffffffc000b11b:
POPFQ
JMP .Lkd_exit_9
.Lkd_src_ffffffffc000b11f:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b11f
DEC QWORD PTR[RBP - 120]
POPFQ
MOV QWORD PTR [0xFFFFFFFFC0606B80 + 0x8 * RAX], RBX
JMP .Lkd_src_ffffffffc000b127
.Lkd_runtime_ffffffffc000b11f:
POPFQ
JMP .Lkd_exit_10
.Lkd_src_ffffffffc000b127:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b127
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR[RBP - 56]
MOV RAX, R15
JMP .Lkd_src_ffffffffc000b12f
.Lkd_runtime_ffffffffc000b127:
POPFQ
JMP .Lkd_exit_11
.Lkd_src_ffffffffc000b12f:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b12f
DEC QWORD PTR[RBP - 120]
POPFQ
MOV QWORD PTR [RSI + 0x10], RAX
JMP .Lkd_src_ffffffffc000b133
.Lkd_runtime_ffffffffc000b12f:
POPFQ
JMP .Lkd_exit_12
.Lkd_src_ffffffffc000b133:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b133
DEC QWORD PTR[RBP - 120]
POPFQ
MOV EAX, 0x10000
JMP .Lkd_src_ffffffffc000b138
.Lkd_runtime_ffffffffc000b133:
POPFQ
JMP .Lkd_exit_13
.Lkd_src_ffffffffc000b138:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b138
DEC QWORD PTR[RBP - 120]
POPFQ
SUB EAX, 0x2
JMP .Lkd_src_ffffffffc000b13b
.Lkd_runtime_ffffffffc000b138:
POPFQ
JMP .Lkd_exit_14
.Lkd_src_ffffffffc000b13b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b13b
DEC QWORD PTR[RBP - 120]
POPFQ
JNZ .Lkd_taken_ffffffffc000b13b
JMP .Lkd_src_ffffffffc000b13d
.Lkd_taken_ffffffffc000b13b:
JMP .Lkd_src_ffffffffc000b138
.Lkd_runtime_ffffffffc000b13b:
POPFQ
JMP .Lkd_exit_15
.Lkd_src_ffffffffc000b13d:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b13d
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RBX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFC8]
JMP .Lkd_src_ffffffffc000b141
.Lkd_runtime_ffffffffc000b13d:
POPFQ
JMP .Lkd_exit_16
.Lkd_src_ffffffffc000b141:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b141
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RAX, QWORD PTR [0xFFFFFFFFC0608188]
JMP .Lkd_src_ffffffffc000b148
.Lkd_runtime_ffffffffc000b141:
POPFQ
JMP .Lkd_exit_17
.Lkd_src_ffffffffc000b148:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b148
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, RBX
JMP .Lkd_src_ffffffffc000b14b
.Lkd_runtime_ffffffffc000b148:
POPFQ
JMP .Lkd_exit_18
.Lkd_src_ffffffffc000b14b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b14b
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS R15, 0xFFFFFFFFC000B150
MOV R15, R15
LEA R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV QWORD PTR [R13], R15
MOVABS R14, 0xffffffffc000f020
JMP .Lkd_src_ffffffffc000f020
.Lkd_runtime_ffffffffc000b14b:
POPFQ
JMP .Lkd_exit_19
.Lkd_src_ffffffffc000b189:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b189
DEC QWORD PTR[RBP - 120]
POPFQ
CMP QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0], 0x41
JMP .Lkd_src_ffffffffc000b18e
.Lkd_runtime_ffffffffc000b189:
POPFQ
JMP .Lkd_exit_20
.Lkd_src_ffffffffc000b18e:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b18e
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc000b18e
JMP .Lkd_src_ffffffffc000b194
.Lkd_taken_ffffffffc000b18e:
JMP .Lkd_src_ffffffffc000b386
.Lkd_runtime_ffffffffc000b18e:
POPFQ
JMP .Lkd_exit_21
.Lkd_src_ffffffffc000b194:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b194
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RAX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc000b198
.Lkd_runtime_ffffffffc000b194:
POPFQ
JMP .Lkd_exit_22
.Lkd_src_ffffffffc000b198:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b198
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RBX, QWORD PTR [0xFFFFFFFFC0606980 + 0x8 * RAX]
JMP .Lkd_src_ffffffffc000b1a0
.Lkd_runtime_ffffffffc000b198:
POPFQ
JMP .Lkd_exit_23
.Lkd_src_ffffffffc000b1a0:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1a0
DEC QWORD PTR[RBP - 120]
POPFQ
CMP RAX, 0x41
JMP .Lkd_src_ffffffffc000b1a4
.Lkd_runtime_ffffffffc000b1a0:
POPFQ
JMP .Lkd_exit_24
.Lkd_src_ffffffffc000b1a4:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1a4
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc000b1a4
JMP .Lkd_src_ffffffffc000b1aa
.Lkd_taken_ffffffffc000b1a4:
JMP .Lkd_src_ffffffffc000b3b0
.Lkd_runtime_ffffffffc000b1a4:
POPFQ
JMP .Lkd_exit_25
.Lkd_src_ffffffffc000b1aa:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1aa
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RAX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc000b1ae
.Lkd_runtime_ffffffffc000b1aa:
POPFQ
JMP .Lkd_exit_26
.Lkd_src_ffffffffc000b1ae:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1ae
DEC QWORD PTR[RBP - 120]
POPFQ
ADD RBX, 0x1
JMP .Lkd_src_ffffffffc000b1b2
.Lkd_runtime_ffffffffc000b1ae:
POPFQ
JMP .Lkd_exit_27
.Lkd_src_ffffffffc000b1b2:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1b2
DEC QWORD PTR[RBP - 120]
POPFQ
MOV QWORD PTR [0xFFFFFFFFC0606980 + 0x8 * RAX], RBX
JMP .Lkd_src_ffffffffc000b1ba
.Lkd_runtime_ffffffffc000b1b2:
POPFQ
JMP .Lkd_exit_28
.Lkd_src_ffffffffc000b1ba:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1ba
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RBX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFC8]
JMP .Lkd_src_ffffffffc000b1be
.Lkd_runtime_ffffffffc000b1ba:
POPFQ
JMP .Lkd_exit_29
.Lkd_src_ffffffffc000b1be:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1be
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RAX, QWORD PTR [0xFFFFFFFFC0608188]
JMP .Lkd_src_ffffffffc000b1c5
.Lkd_runtime_ffffffffc000b1be:
POPFQ
JMP .Lkd_exit_30
.Lkd_src_ffffffffc000b1c5:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1c5
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, RBX
JMP .Lkd_src_ffffffffc000b1c8
.Lkd_runtime_ffffffffc000b1c5:
POPFQ
JMP .Lkd_exit_31
.Lkd_src_ffffffffc000b1c8:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1c8
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS R15, 0xFFFFFFFFC000B1CD
MOV R15, R15
LEA R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV QWORD PTR [R13], R15
MOVABS R14, 0xffffffffc000f023
JMP .Lkd_src_ffffffffc000f023
.Lkd_runtime_ffffffffc000b1c8:
POPFQ
JMP .Lkd_exit_32
.Lkd_src_ffffffffc000b1f4:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1f4
DEC QWORD PTR[RBP - 120]
POPFQ
CMP QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0], 0x41
JMP .Lkd_src_ffffffffc000b1f9
.Lkd_runtime_ffffffffc000b1f4:
POPFQ
JMP .Lkd_exit_33
.Lkd_src_ffffffffc000b1f9:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1f9
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc000b1f9
JMP .Lkd_src_ffffffffc000b1ff
.Lkd_taken_ffffffffc000b1f9:
JMP .Lkd_src_ffffffffc000b31e
.Lkd_runtime_ffffffffc000b1f9:
POPFQ
JMP .Lkd_exit_34
.Lkd_src_ffffffffc000b1ff:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b1ff
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFC0]
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
MOV RSI, R13
JMP .Lkd_src_ffffffffc000b206
.Lkd_runtime_ffffffffc000b203:
POPFQ
JMP .Lkd_exit_36
.Lkd_src_ffffffffc000b206:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b206
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS RDX, 0xFFFFFFFFC000B215
JMP .Lkd_src_ffffffffc000b20d
.Lkd_runtime_ffffffffc000b206:
POPFQ
JMP .Lkd_exit_37
.Lkd_src_ffffffffc000b20d:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b20d
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RCX, R12
JMP .Lkd_src_ffffffffc000b210
.Lkd_runtime_ffffffffc000b20d:
POPFQ
JMP .Lkd_exit_38
.Lkd_src_ffffffffc000b210:
JMP .Lkd_exit_39
.Lkd_src_ffffffffc000b215:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b215
DEC QWORD PTR[RBP - 120]
POPFQ
ADD R13, 0x20
JMP .Lkd_src_ffffffffc000b219
.Lkd_runtime_ffffffffc000b215:
POPFQ
JMP .Lkd_exit_40
.Lkd_src_ffffffffc000b219:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b219
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV RBX, R15
JMP .Lkd_src_ffffffffc000b21a
.Lkd_runtime_ffffffffc000b219:
POPFQ
JMP .Lkd_exit_41
.Lkd_src_ffffffffc000b21a:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b21a
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R14, QWORD PTR[R11 + 48]
MOV R14, R15
MOV QWORD PTR[R11 + 48], R14
JMP .Lkd_src_ffffffffc000b21c
.Lkd_runtime_ffffffffc000b21a:
POPFQ
JMP .Lkd_exit_42
.Lkd_src_ffffffffc000b21c:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b21c
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R14, QWORD PTR[R11 + 40]
MOV R14, R15
MOV QWORD PTR[R11 + 40], R14
JMP .Lkd_src_ffffffffc000b21e
.Lkd_runtime_ffffffffc000b21c:
POPFQ
JMP .Lkd_exit_43
.Lkd_src_ffffffffc000b21e:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b21e
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R14, QWORD PTR[R11 + 32]
MOV R14, R15
MOV QWORD PTR[R11 + 32], R14
JMP .Lkd_src_ffffffffc000b220
.Lkd_runtime_ffffffffc000b21e:
POPFQ
JMP .Lkd_exit_44
.Lkd_src_ffffffffc000b220:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b220
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R14, QWORD PTR[R11 + 24]
MOV R14, R15
MOV QWORD PTR[R11 + 24], R14
JMP .Lkd_src_ffffffffc000b222
.Lkd_runtime_ffffffffc000b220:
POPFQ
JMP .Lkd_exit_45
.Lkd_src_ffffffffc000b222:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b222
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R12, R15
JMP .Lkd_src_ffffffffc000b223
.Lkd_runtime_ffffffffc000b222:
POPFQ
JMP .Lkd_exit_46
.Lkd_src_ffffffffc000b223:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b223
DEC QWORD PTR[RBP - 120]
POPFQ
XOR EAX, EAX
JMP .Lkd_src_ffffffffc000b225
.Lkd_runtime_ffffffffc000b223:
POPFQ
JMP .Lkd_exit_47
.Lkd_src_ffffffffc000b225:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b225
DEC QWORD PTR[RBP - 120]
POPFQ
XOR EDX, EDX
JMP .Lkd_src_ffffffffc000b227
.Lkd_runtime_ffffffffc000b225:
POPFQ
JMP .Lkd_exit_48
.Lkd_src_ffffffffc000b227:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b227
DEC QWORD PTR[RBP - 120]
POPFQ
XOR ECX, ECX
JMP .Lkd_src_ffffffffc000b229
.Lkd_runtime_ffffffffc000b227:
POPFQ
JMP .Lkd_exit_49
.Lkd_src_ffffffffc000b229:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b229
DEC QWORD PTR[RBP - 120]
POPFQ
XOR ESI, ESI
JMP .Lkd_src_ffffffffc000b22b
.Lkd_runtime_ffffffffc000b229:
POPFQ
JMP .Lkd_exit_50
.Lkd_src_ffffffffc000b22b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b22b
DEC QWORD PTR[RBP - 120]
POPFQ
XOR EDI, EDI
JMP .Lkd_src_ffffffffc000b22d
.Lkd_runtime_ffffffffc000b22b:
POPFQ
JMP .Lkd_exit_51
.Lkd_src_ffffffffc000b22d:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b22d
DEC QWORD PTR[RBP - 120]
POPFQ
XOR R8D, R8D
JMP .Lkd_src_ffffffffc000b230
.Lkd_runtime_ffffffffc000b22d:
POPFQ
JMP .Lkd_exit_52
.Lkd_src_ffffffffc000b230:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b230
DEC QWORD PTR[RBP - 120]
POPFQ
XOR R9D, R9D
JMP .Lkd_src_ffffffffc000b233
.Lkd_runtime_ffffffffc000b230:
POPFQ
JMP .Lkd_exit_53
.Lkd_src_ffffffffc000b233:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b233
DEC QWORD PTR[RBP - 120]
POPFQ
XOR R10D, R10D
JMP .Lkd_src_ffffffffc000b236
.Lkd_runtime_ffffffffc000b233:
POPFQ
JMP .Lkd_exit_54
.Lkd_src_ffffffffc000b236:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b236
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR[R11 + 56]
XOR R15d, R15d
MOV QWORD PTR[R11 + 56], R15
JMP .Lkd_src_ffffffffc000b239
.Lkd_runtime_ffffffffc000b236:
POPFQ
JMP .Lkd_exit_55
.Lkd_src_ffffffffc000b239:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b239
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R15, R15
MOV QWORD PTR[RBP - 88], R15
MOV R14, QWORD PTR[RBP - 88]
PUSHFQ
POPFQ
JMP .Lkd_exit_57
.Lkd_runtime_ffffffffc000b239:
POPFQ
JMP .Lkd_exit_56
.Lkd_src_ffffffffc000b25f:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b25f
DEC QWORD PTR[RBP - 120]
POPFQ
CMP QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0], 0x41
JMP .Lkd_src_ffffffffc000b264
.Lkd_runtime_ffffffffc000b25f:
POPFQ
JMP .Lkd_exit_58
.Lkd_src_ffffffffc000b264:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b264
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc000b264
JMP .Lkd_src_ffffffffc000b26a
.Lkd_taken_ffffffffc000b264:
JMP .Lkd_src_ffffffffc000b348
.Lkd_runtime_ffffffffc000b264:
POPFQ
JMP .Lkd_exit_59
.Lkd_src_ffffffffc000b26a:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b26a
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RAX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc000b26e
.Lkd_runtime_ffffffffc000b26a:
POPFQ
JMP .Lkd_exit_60
.Lkd_src_ffffffffc000b26e:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b26e
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RBX, QWORD PTR [0xFFFFFFFFC0606980 + 0x8 * RAX]
JMP .Lkd_src_ffffffffc000b276
.Lkd_runtime_ffffffffc000b26e:
POPFQ
JMP .Lkd_exit_61
.Lkd_src_ffffffffc000b276:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b276
DEC QWORD PTR[RBP - 120]
POPFQ
CMP RAX, 0x41
JMP .Lkd_src_ffffffffc000b27a
.Lkd_runtime_ffffffffc000b276:
POPFQ
JMP .Lkd_exit_62
.Lkd_src_ffffffffc000b27a:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b27a
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc000b27a
JMP .Lkd_src_ffffffffc000b280
.Lkd_taken_ffffffffc000b27a:
JMP .Lkd_src_ffffffffc000b35d
.Lkd_runtime_ffffffffc000b27a:
POPFQ
JMP .Lkd_exit_63
.Lkd_src_ffffffffc000b280:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b280
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR[R11 + 32]
MOV R15, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
MOV QWORD PTR[R11 + 32], R15
JMP .Lkd_src_ffffffffc000b284
.Lkd_runtime_ffffffffc000b280:
POPFQ
JMP .Lkd_exit_64
.Lkd_src_ffffffffc000b284:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b284
DEC QWORD PTR[RBP - 120]
POPFQ
ADD RBX, 0x1
JMP .Lkd_src_ffffffffc000b288
.Lkd_runtime_ffffffffc000b284:
POPFQ
JMP .Lkd_exit_65
.Lkd_src_ffffffffc000b288:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b288
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFC8]
JMP .Lkd_src_ffffffffc000b28c
.Lkd_runtime_ffffffffc000b288:
POPFQ
JMP .Lkd_exit_66
.Lkd_src_ffffffffc000b28c:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b28c
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR[R11 + 32]
MOV QWORD PTR [0xFFFFFFFFC0606980 + 0x8 * R15], RBX
JMP .Lkd_src_ffffffffc000b294
.Lkd_runtime_ffffffffc000b28c:
POPFQ
JMP .Lkd_exit_67
.Lkd_src_ffffffffc000b294:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b294
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RAX, QWORD PTR [0xFFFFFFFFC0608188]
JMP .Lkd_src_ffffffffc000b29b
.Lkd_runtime_ffffffffc000b294:
POPFQ
JMP .Lkd_exit_68
.Lkd_src_ffffffffc000b29b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b29b
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS R15, 0xFFFFFFFFC000B2A0
MOV R15, R15
LEA R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV QWORD PTR [R13], R15
MOVABS R14, 0xffffffffc000f026
JMP .Lkd_src_ffffffffc000f026
.Lkd_runtime_ffffffffc000b29b:
POPFQ
JMP .Lkd_exit_69
.Lkd_src_ffffffffc000b2c0:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2c0
DEC QWORD PTR[RBP - 120]
POPFQ
ADD R13, 0x20
JMP .Lkd_src_ffffffffc000b2c4
.Lkd_runtime_ffffffffc000b2c0:
POPFQ
JMP .Lkd_exit_70
.Lkd_src_ffffffffc000b2c4:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2c4
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV RBX, R15
JMP .Lkd_src_ffffffffc000b2c5
.Lkd_runtime_ffffffffc000b2c4:
POPFQ
JMP .Lkd_exit_71
.Lkd_src_ffffffffc000b2c5:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2c5
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R14, QWORD PTR[R11 + 48]
MOV R14, R15
MOV QWORD PTR[R11 + 48], R14
JMP .Lkd_src_ffffffffc000b2c7
.Lkd_runtime_ffffffffc000b2c5:
POPFQ
JMP .Lkd_exit_72
.Lkd_src_ffffffffc000b2c7:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2c7
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R14, QWORD PTR[R11 + 40]
MOV R14, R15
MOV QWORD PTR[R11 + 40], R14
JMP .Lkd_src_ffffffffc000b2c9
.Lkd_runtime_ffffffffc000b2c7:
POPFQ
JMP .Lkd_exit_73
.Lkd_src_ffffffffc000b2c9:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2c9
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R14, QWORD PTR[R11 + 32]
MOV R14, R15
MOV QWORD PTR[R11 + 32], R14
JMP .Lkd_src_ffffffffc000b2cb
.Lkd_runtime_ffffffffc000b2c9:
POPFQ
JMP .Lkd_exit_74
.Lkd_src_ffffffffc000b2cb:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2cb
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R14, QWORD PTR[R11 + 24]
MOV R14, R15
MOV QWORD PTR[R11 + 24], R14
JMP .Lkd_src_ffffffffc000b2cd
.Lkd_runtime_ffffffffc000b2cb:
POPFQ
JMP .Lkd_exit_75
.Lkd_src_ffffffffc000b2cd:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2cd
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R12, R15
JMP .Lkd_src_ffffffffc000b2ce
.Lkd_runtime_ffffffffc000b2cd:
POPFQ
JMP .Lkd_exit_76
.Lkd_src_ffffffffc000b2ce:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2ce
DEC QWORD PTR[RBP - 120]
POPFQ
XOR EAX, EAX
JMP .Lkd_src_ffffffffc000b2d0
.Lkd_runtime_ffffffffc000b2ce:
POPFQ
JMP .Lkd_exit_77
.Lkd_src_ffffffffc000b2d0:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2d0
DEC QWORD PTR[RBP - 120]
POPFQ
XOR EDX, EDX
JMP .Lkd_src_ffffffffc000b2d2
.Lkd_runtime_ffffffffc000b2d0:
POPFQ
JMP .Lkd_exit_78
.Lkd_src_ffffffffc000b2d2:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2d2
DEC QWORD PTR[RBP - 120]
POPFQ
XOR ECX, ECX
JMP .Lkd_src_ffffffffc000b2d4
.Lkd_runtime_ffffffffc000b2d2:
POPFQ
JMP .Lkd_exit_79
.Lkd_src_ffffffffc000b2d4:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2d4
DEC QWORD PTR[RBP - 120]
POPFQ
XOR ESI, ESI
JMP .Lkd_src_ffffffffc000b2d6
.Lkd_runtime_ffffffffc000b2d4:
POPFQ
JMP .Lkd_exit_80
.Lkd_src_ffffffffc000b2d6:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2d6
DEC QWORD PTR[RBP - 120]
POPFQ
XOR EDI, EDI
JMP .Lkd_src_ffffffffc000b2d8
.Lkd_runtime_ffffffffc000b2d6:
POPFQ
JMP .Lkd_exit_81
.Lkd_src_ffffffffc000b2d8:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2d8
DEC QWORD PTR[RBP - 120]
POPFQ
XOR R8D, R8D
JMP .Lkd_src_ffffffffc000b2db
.Lkd_runtime_ffffffffc000b2d8:
POPFQ
JMP .Lkd_exit_82
.Lkd_src_ffffffffc000b2db:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2db
DEC QWORD PTR[RBP - 120]
POPFQ
XOR R9D, R9D
JMP .Lkd_src_ffffffffc000b2de
.Lkd_runtime_ffffffffc000b2db:
POPFQ
JMP .Lkd_exit_83
.Lkd_src_ffffffffc000b2de:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2de
DEC QWORD PTR[RBP - 120]
POPFQ
XOR R10D, R10D
JMP .Lkd_src_ffffffffc000b2e1
.Lkd_runtime_ffffffffc000b2de:
POPFQ
JMP .Lkd_exit_84
.Lkd_src_ffffffffc000b2e1:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2e1
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR[R11 + 56]
XOR R15d, R15d
MOV QWORD PTR[R11 + 56], R15
JMP .Lkd_src_ffffffffc000b2e4
.Lkd_runtime_ffffffffc000b2e1:
POPFQ
JMP .Lkd_exit_85
.Lkd_src_ffffffffc000b2e4:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b2e4
DEC QWORD PTR[RBP - 120]
POPFQ
MOV R15, QWORD PTR [R13]
LEA R13, QWORD PTR [R13 + 0x8]
MOV R15, R15
MOV QWORD PTR[RBP - 88], R15
MOV R14, QWORD PTR[RBP - 88]
PUSHFQ
POPFQ
JMP .Lkd_exit_87
.Lkd_runtime_ffffffffc000b2e4:
POPFQ
JMP .Lkd_exit_86
.Lkd_src_ffffffffc000b31e:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b31e
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RSI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc000b322
.Lkd_runtime_ffffffffc000b31e:
POPFQ
JMP .Lkd_exit_88
.Lkd_src_ffffffffc000b322:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b322
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, 0xFFFFFFFFC0607C60
JMP .Lkd_src_ffffffffc000b329
.Lkd_runtime_ffffffffc000b322:
POPFQ
JMP .Lkd_exit_89
.Lkd_src_ffffffffc000b329:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b329
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS R15, 0xFFFFFFFFC000B32E
MOV R15, R15
LEA R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV QWORD PTR [R13], R15
MOVABS R14, 0xffffffff81dd3fd0
JMP .Lkd_exit_91
.Lkd_runtime_ffffffffc000b329:
POPFQ
JMP .Lkd_exit_90
.Lkd_src_ffffffffc000b348:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b348
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RSI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc000b34c
.Lkd_runtime_ffffffffc000b348:
POPFQ
JMP .Lkd_exit_92
.Lkd_src_ffffffffc000b34c:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b34c
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, 0xFFFFFFFFC0607CE0
JMP .Lkd_src_ffffffffc000b353
.Lkd_runtime_ffffffffc000b34c:
POPFQ
JMP .Lkd_exit_93
.Lkd_src_ffffffffc000b353:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b353
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS R15, 0xFFFFFFFFC000B358
MOV R15, R15
LEA R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV QWORD PTR [R13], R15
MOVABS R14, 0xffffffff81dd3fd0
JMP .Lkd_exit_95
.Lkd_runtime_ffffffffc000b353:
POPFQ
JMP .Lkd_exit_94
.Lkd_src_ffffffffc000b35d:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b35d
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RSI, RAX
JMP .Lkd_src_ffffffffc000b360
.Lkd_runtime_ffffffffc000b35d:
POPFQ
JMP .Lkd_exit_96
.Lkd_src_ffffffffc000b360:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b360
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, 0xFFFFFFFFC0607CC0
JMP .Lkd_src_ffffffffc000b367
.Lkd_runtime_ffffffffc000b360:
POPFQ
JMP .Lkd_exit_97
.Lkd_src_ffffffffc000b367:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b367
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS R15, 0xFFFFFFFFC000B36C
MOV R15, R15
LEA R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV QWORD PTR [R13], R15
MOVABS R14, 0xffffffff81dd3fd0
JMP .Lkd_exit_99
.Lkd_runtime_ffffffffc000b367:
POPFQ
JMP .Lkd_exit_98
.Lkd_src_ffffffffc000b386:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b386
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RSI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc000b38a
.Lkd_runtime_ffffffffc000b386:
POPFQ
JMP .Lkd_exit_100
.Lkd_src_ffffffffc000b38a:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b38a
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, 0xFFFFFFFFC0607D40
JMP .Lkd_src_ffffffffc000b391
.Lkd_runtime_ffffffffc000b38a:
POPFQ
JMP .Lkd_exit_101
.Lkd_src_ffffffffc000b391:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b391
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS R15, 0xFFFFFFFFC000B396
MOV R15, R15
LEA R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV QWORD PTR [R13], R15
MOVABS R14, 0xffffffff81dd3fd0
JMP .Lkd_exit_103
.Lkd_runtime_ffffffffc000b391:
POPFQ
JMP .Lkd_exit_102
.Lkd_src_ffffffffc000b3b0:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3b0
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RSI, RAX
JMP .Lkd_src_ffffffffc000b3b3
.Lkd_runtime_ffffffffc000b3b0:
POPFQ
JMP .Lkd_exit_104
.Lkd_src_ffffffffc000b3b3:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3b3
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, 0xFFFFFFFFC0607D20
JMP .Lkd_src_ffffffffc000b3ba
.Lkd_runtime_ffffffffc000b3b3:
POPFQ
JMP .Lkd_exit_105
.Lkd_src_ffffffffc000b3ba:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3ba
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS R15, 0xFFFFFFFFC000B3BF
MOV R15, R15
LEA R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV QWORD PTR [R13], R15
MOVABS R14, 0xffffffff81dd3fd0
JMP .Lkd_exit_107
.Lkd_runtime_ffffffffc000b3ba:
POPFQ
JMP .Lkd_exit_106
.Lkd_src_ffffffffc000b3c4:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3c4
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RSI, RAX
JMP .Lkd_src_ffffffffc000b3c7
.Lkd_runtime_ffffffffc000b3c4:
POPFQ
JMP .Lkd_exit_108
.Lkd_src_ffffffffc000b3c7:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3c7
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, 0xFFFFFFFFC0607DA0
JMP .Lkd_src_ffffffffc000b3ce
.Lkd_runtime_ffffffffc000b3c7:
POPFQ
JMP .Lkd_exit_109
.Lkd_src_ffffffffc000b3ce:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3ce
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS R15, 0xFFFFFFFFC000B3D3
MOV R15, R15
LEA R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV QWORD PTR [R13], R15
MOVABS R14, 0xffffffff81dd3fd0
JMP .Lkd_exit_111
.Lkd_runtime_ffffffffc000b3ce:
POPFQ
JMP .Lkd_exit_110
.Lkd_src_ffffffffc000b3d8:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3d8
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RSI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc000b3dc
.Lkd_runtime_ffffffffc000b3d8:
POPFQ
JMP .Lkd_exit_112
.Lkd_src_ffffffffc000b3dc:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3dc
DEC QWORD PTR[RBP - 120]
POPFQ
MOV RDI, 0xFFFFFFFFC0607DC0
JMP .Lkd_src_ffffffffc000b3e3
.Lkd_runtime_ffffffffc000b3dc:
POPFQ
JMP .Lkd_exit_113
.Lkd_src_ffffffffc000b3e3:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000b3e3
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS R15, 0xFFFFFFFFC000B3E8
MOV R15, R15
LEA R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV QWORD PTR [R13], R15
MOVABS R14, 0xffffffff81dd3fd0
JMP .Lkd_exit_115
.Lkd_runtime_ffffffffc000b3e3:
POPFQ
JMP .Lkd_exit_114
.Lkd_src_ffffffffc000f020:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000f020
DEC QWORD PTR[RBP - 120]
POPFQ
PUSH RAX
MOV RAX, RAX
MOV QWORD PTR[RBP - 88], RAX
POP RAX
MOV R14, QWORD PTR[RBP - 88]
JMP .Lkd_exit_117
.Lkd_runtime_ffffffffc000f020:
POPFQ
JMP .Lkd_exit_116
.Lkd_src_ffffffffc000f023:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000f023
DEC QWORD PTR[RBP - 120]
POPFQ
PUSH RAX
MOV RAX, RAX
MOV QWORD PTR[RBP - 88], RAX
POP RAX
MOV R14, QWORD PTR[RBP - 88]
JMP .Lkd_exit_119
.Lkd_runtime_ffffffffc000f023:
POPFQ
JMP .Lkd_exit_118
.Lkd_src_ffffffffc000f026:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc000f026
DEC QWORD PTR[RBP - 120]
POPFQ
PUSH RAX
MOV RAX, RAX
MOV QWORD PTR[RBP - 88], RAX
POP RAX
MOV R14, QWORD PTR[RBP - 88]
JMP .Lkd_exit_121
.Lkd_runtime_ffffffffc000f026:
POPFQ
JMP .Lkd_exit_120
.Lkd_exit_0:
MOV QWORD PTR[RBP - 72], R14
MOV QWORD PTR[RBP - 80], R14
MOV QWORD PTR[RBP - 88], R14
MOV QWORD PTR[RBP - 96], 6
MOV QWORD PTR[RBP - 104], 0
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_1:
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
.Lkd_exit_2:
MOVABS R15, 0xffffffffc000b0f7
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b0f7
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_3:
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
.Lkd_exit_4:
MOVABS R15, 0xffffffffc000b101
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b101
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_5:
MOVABS R15, 0xffffffffc000b109
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b109
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_6:
MOVABS R15, 0xffffffffc000b10d
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b10d
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_7:
MOVABS R15, 0xffffffffc000b113
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b113
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_8:
MOVABS R15, 0xffffffffc000b117
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b117
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_9:
MOVABS R15, 0xffffffffc000b11b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b11b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_10:
MOVABS R15, 0xffffffffc000b11f
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b11f
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_11:
MOVABS R15, 0xffffffffc000b127
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b127
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_12:
MOVABS R15, 0xffffffffc000b12f
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b12f
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_13:
MOVABS R15, 0xffffffffc000b133
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b133
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_14:
MOVABS R15, 0xffffffffc000b138
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b138
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_15:
MOVABS R15, 0xffffffffc000b13b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b13b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_16:
MOVABS R15, 0xffffffffc000b13d
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b13d
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_17:
MOVABS R15, 0xffffffffc000b141
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b141
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_18:
MOVABS R15, 0xffffffffc000b148
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b148
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_19:
MOVABS R15, 0xffffffffc000b14b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b14b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_20:
MOVABS R15, 0xffffffffc000b189
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b189
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_21:
MOVABS R15, 0xffffffffc000b18e
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b18e
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_22:
MOVABS R15, 0xffffffffc000b194
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b194
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_23:
MOVABS R15, 0xffffffffc000b198
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b198
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_24:
MOVABS R15, 0xffffffffc000b1a0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1a0
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_25:
MOVABS R15, 0xffffffffc000b1a4
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1a4
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_26:
MOVABS R15, 0xffffffffc000b1aa
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1aa
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_27:
MOVABS R15, 0xffffffffc000b1ae
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1ae
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_28:
MOVABS R15, 0xffffffffc000b1b2
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1b2
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_29:
MOVABS R15, 0xffffffffc000b1ba
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1ba
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_30:
MOVABS R15, 0xffffffffc000b1be
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1be
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_31:
MOVABS R15, 0xffffffffc000b1c5
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1c5
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_32:
MOVABS R15, 0xffffffffc000b1c8
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1c8
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_33:
MOVABS R15, 0xffffffffc000b1f4
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1f4
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_34:
MOVABS R15, 0xffffffffc000b1f9
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b1f9
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
MOVABS R15, 0xffffffffc000b206
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b206
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_38:
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
.Lkd_exit_39:
MOVABS R15, 0xffffffffc000b210
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b210
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81514860
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 1
MOV QWORD PTR[RBP - 104], 2
MOV QWORD PTR[RBP - 112], 1
JMP .Lkd_export
.Lkd_exit_40:
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
.Lkd_exit_41:
MOVABS R15, 0xffffffffc000b219
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b219
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_42:
MOVABS R15, 0xffffffffc000b21a
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b21a
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_43:
MOVABS R15, 0xffffffffc000b21c
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b21c
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_44:
MOVABS R15, 0xffffffffc000b21e
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b21e
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_45:
MOVABS R15, 0xffffffffc000b220
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b220
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_46:
MOVABS R15, 0xffffffffc000b222
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b222
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_47:
MOVABS R15, 0xffffffffc000b223
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b223
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_48:
MOVABS R15, 0xffffffffc000b225
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b225
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_49:
MOVABS R15, 0xffffffffc000b227
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b227
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_50:
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
.Lkd_exit_51:
MOVABS R15, 0xffffffffc000b22b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b22b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_52:
MOVABS R15, 0xffffffffc000b22d
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b22d
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_53:
MOVABS R15, 0xffffffffc000b230
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b230
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_54:
MOVABS R15, 0xffffffffc000b233
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b233
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_55:
MOVABS R15, 0xffffffffc000b236
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b236
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_56:
MOVABS R15, 0xffffffffc000b239
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b239
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_57:
MOV QWORD PTR[RBP - 72], R14
MOVABS R15, 0xffffffffc000b239
MOV QWORD PTR[RBP - 80], R15
MOV QWORD PTR[RBP - 88], R14
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 11
MOV QWORD PTR[RBP - 112], 3
JMP .Lkd_export
.Lkd_exit_58:
MOVABS R15, 0xffffffffc000b25f
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b25f
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_59:
MOVABS R15, 0xffffffffc000b264
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b264
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_60:
MOVABS R15, 0xffffffffc000b26a
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b26a
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_61:
MOVABS R15, 0xffffffffc000b26e
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b26e
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_62:
MOVABS R15, 0xffffffffc000b276
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b276
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_63:
MOVABS R15, 0xffffffffc000b27a
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b27a
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_64:
MOVABS R15, 0xffffffffc000b280
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b280
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_65:
MOVABS R15, 0xffffffffc000b284
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b284
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_66:
MOVABS R15, 0xffffffffc000b288
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b288
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_67:
MOVABS R15, 0xffffffffc000b28c
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b28c
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_68:
MOVABS R15, 0xffffffffc000b294
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b294
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_69:
MOVABS R15, 0xffffffffc000b29b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b29b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_70:
MOVABS R15, 0xffffffffc000b2c0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2c0
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_71:
MOVABS R15, 0xffffffffc000b2c4
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2c4
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_72:
MOVABS R15, 0xffffffffc000b2c5
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2c5
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_73:
MOVABS R15, 0xffffffffc000b2c7
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2c7
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_74:
MOVABS R15, 0xffffffffc000b2c9
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2c9
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_75:
MOVABS R15, 0xffffffffc000b2cb
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2cb
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_76:
MOVABS R15, 0xffffffffc000b2cd
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2cd
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_77:
MOVABS R15, 0xffffffffc000b2ce
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2ce
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_78:
MOVABS R15, 0xffffffffc000b2d0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2d0
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_79:
MOVABS R15, 0xffffffffc000b2d2
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2d2
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_80:
MOVABS R15, 0xffffffffc000b2d4
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2d4
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_81:
MOVABS R15, 0xffffffffc000b2d6
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2d6
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_82:
MOVABS R15, 0xffffffffc000b2d8
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2d8
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_83:
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
.Lkd_exit_84:
MOVABS R15, 0xffffffffc000b2de
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2de
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_85:
MOVABS R15, 0xffffffffc000b2e1
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2e1
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_86:
MOVABS R15, 0xffffffffc000b2e4
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b2e4
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_87:
MOV QWORD PTR[RBP - 72], R14
MOVABS R15, 0xffffffffc000b2e4
MOV QWORD PTR[RBP - 80], R15
MOV QWORD PTR[RBP - 88], R14
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 11
MOV QWORD PTR[RBP - 112], 3
JMP .Lkd_export
.Lkd_exit_88:
MOVABS R15, 0xffffffffc000b31e
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b31e
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_89:
MOVABS R15, 0xffffffffc000b322
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b322
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_90:
MOVABS R15, 0xffffffffc000b329
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b329
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_91:
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b329
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_92:
MOVABS R15, 0xffffffffc000b348
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b348
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_93:
MOVABS R15, 0xffffffffc000b34c
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b34c
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_94:
MOVABS R15, 0xffffffffc000b353
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b353
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_95:
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b353
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_96:
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
.Lkd_exit_97:
MOVABS R15, 0xffffffffc000b360
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b360
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_98:
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
.Lkd_exit_99:
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b367
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_100:
MOVABS R15, 0xffffffffc000b386
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b386
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_101:
MOVABS R15, 0xffffffffc000b38a
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b38a
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_102:
MOVABS R15, 0xffffffffc000b391
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b391
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_103:
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b391
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_104:
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
.Lkd_exit_105:
MOVABS R15, 0xffffffffc000b3b3
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3b3
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_106:
MOVABS R15, 0xffffffffc000b3ba
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3ba
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_107:
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3ba
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_108:
MOVABS R15, 0xffffffffc000b3c4
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3c4
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_109:
MOVABS R15, 0xffffffffc000b3c7
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3c7
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_110:
MOVABS R15, 0xffffffffc000b3ce
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3ce
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_111:
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3ce
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_112:
MOVABS R15, 0xffffffffc000b3d8
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3d8
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_113:
MOVABS R15, 0xffffffffc000b3dc
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3dc
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_114:
MOVABS R15, 0xffffffffc000b3e3
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3e3
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_115:
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000b3e3
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd3fd0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_116:
MOVABS R15, 0xffffffffc000f020
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000f020
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_117:
MOV QWORD PTR[RBP - 72], R14
MOVABS R15, 0xffffffffc000f020
MOV QWORD PTR[RBP - 80], R15
MOV QWORD PTR[RBP - 88], R14
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 10
MOV QWORD PTR[RBP - 112], 4
JMP .Lkd_export
.Lkd_exit_118:
MOVABS R15, 0xffffffffc000f023
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000f023
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_119:
MOV QWORD PTR[RBP - 72], R14
MOVABS R15, 0xffffffffc000f023
MOV QWORD PTR[RBP - 80], R15
MOV QWORD PTR[RBP - 88], R14
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 10
MOV QWORD PTR[RBP - 112], 4
JMP .Lkd_export
.Lkd_exit_120:
MOVABS R15, 0xffffffffc000f026
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc000f026
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_121:
MOV QWORD PTR[RBP - 72], R14
MOVABS R15, 0xffffffffc000f026
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
