/* SPDX-License-Identifier: GPL-2.0-only */
/* Per-image entry template for the original UB-derived KD mapping. Lowering
 * substitutes kd_fixture_entry and KD_GENERATED_BODY for one image's own code.
 * All source state remains in its original thread's one canonical packet.
 * The caller supplies fresh origin GS/task inputs, exclusive source execution,
 * valid source/code bindings and the declared sleepable physical context.
 * The distinct executor's native stack and all origin waiting/control stacks
 * must be admitted disjoint from the stopped source stack; this template does
 * not establish or allocate that context and cannot execute an origin's own
 * source on overlapping native frames.
 * General flags/SIMD use AS01; this unrun wrapper is no equivalence evidence.
 */


	.intel_syntax noprefix
	.text
	.p2align 4
	.globl kd_fixture_entry
	.type kd_fixture_entry, @function
kd_fixture_entry:
	endbr64
	/* Preserve the executor's native callee-saved state. Logical source
	 * BP/SP are separate and never replace physical RBP/RSP here. */
	push rbp
	mov rbp, rsp
	push rbx
	push r12
	push r13
	push r14
	push r15
	/* Allocate every private slot before stores, without using a red zone
	 * or changing the assumed source flags during packet import. */
	lea rsp, [rsp - 80]
	mov QWORD PTR[RBP - 64], rsi
	mov R11, rdi
	mov r14, QWORD PTR[rsi + 0]
	mov QWORD PTR[RBP - 48], r14
	mov r14, QWORD PTR[rsi + 8]
	mov QWORD PTR[RBP - 56], r14
	/* Source R11--R15 already have canonical backing. Only the resident
	 * source GPRs and stable BP/SP caches need importing. */
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
MOVABS R15, 0xffffffffc09e90f2
CMP R14, R15
JE .Lkd_enter_ffffffffc09e90f2
MOVABS R15, 0xffffffffc09e9189
CMP R14, R15
JE .Lkd_enter_ffffffffc09e9189
MOVABS R15, 0xffffffffc09e91f4
CMP R14, R15
JE .Lkd_enter_ffffffffc09e91f4
MOVABS R15, 0xffffffffc09e9215
CMP R14, R15
JE .Lkd_enter_ffffffffc09e9215
MOVABS R15, 0xffffffffc09e925f
CMP R14, R15
JE .Lkd_enter_ffffffffc09e925f
MOVABS R15, 0xffffffffc09e92c0
CMP R14, R15
JE .Lkd_enter_ffffffffc09e92c0
POPFQ
JMP .Lkd_exit_0
.Lkd_enter_ffffffffc09e90f2:
POPFQ
JMP .Lkd_src_ffffffffc09e90f2
.Lkd_enter_ffffffffc09e9189:
POPFQ
JMP .Lkd_src_ffffffffc09e9189
.Lkd_enter_ffffffffc09e91f4:
POPFQ
JMP .Lkd_src_ffffffffc09e91f4
.Lkd_enter_ffffffffc09e9215:
POPFQ
JMP .Lkd_src_ffffffffc09e9215
.Lkd_enter_ffffffffc09e925f:
POPFQ
JMP .Lkd_src_ffffffffc09e925f
.Lkd_enter_ffffffffc09e92c0:
POPFQ
JMP .Lkd_src_ffffffffc09e92c0
.Lkd_src_ffffffffc09e90f2:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e90f2
DEC QWORD PTR[RBP - 120]
POPFQ
CMP             QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0], 0x41
JMP .Lkd_src_ffffffffc09e90f7
.Lkd_runtime_ffffffffc09e90f2:
POPFQ
JMP .Lkd_exit_1
.Lkd_src_ffffffffc09e90f7:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e90f7
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc09e90f7
JMP .Lkd_src_ffffffffc09e90fd
.Lkd_taken_ffffffffc09e90f7:
JMP .Lkd_src_ffffffffc09e93d8
.Lkd_runtime_ffffffffc09e90f7:
POPFQ
JMP .Lkd_exit_2
.Lkd_src_ffffffffc09e90fd:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e90fd
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RAX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc09e9101
.Lkd_runtime_ffffffffc09e90fd:
POPFQ
JMP .Lkd_exit_3
.Lkd_src_ffffffffc09e9101:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9101
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RBX, QWORD PTR [0xFFFFFFFFC0B9BB60 + 0x8 * RAX]
JMP .Lkd_src_ffffffffc09e9109
.Lkd_runtime_ffffffffc09e9101:
POPFQ
JMP .Lkd_exit_4
.Lkd_src_ffffffffc09e9109:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9109
DEC QWORD PTR[RBP - 120]
POPFQ
CMP             RAX, 0x41
JMP .Lkd_src_ffffffffc09e910d
.Lkd_runtime_ffffffffc09e9109:
POPFQ
JMP .Lkd_exit_5
.Lkd_src_ffffffffc09e910d:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e910d
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc09e910d
JMP .Lkd_src_ffffffffc09e9113
.Lkd_taken_ffffffffc09e910d:
JMP .Lkd_src_ffffffffc09e93c4
.Lkd_runtime_ffffffffc09e910d:
POPFQ
JMP .Lkd_exit_6
.Lkd_src_ffffffffc09e9113:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9113
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RAX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc09e9117
.Lkd_runtime_ffffffffc09e9113:
POPFQ
JMP .Lkd_exit_7
.Lkd_src_ffffffffc09e9117:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9117
DEC QWORD PTR[RBP - 120]
POPFQ
ADD             RBX, 0x1
JMP .Lkd_src_ffffffffc09e911b
.Lkd_runtime_ffffffffc09e9117:
POPFQ
JMP .Lkd_exit_8
.Lkd_src_ffffffffc09e911b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e911b
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RSI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFC8]
JMP .Lkd_src_ffffffffc09e911f
.Lkd_runtime_ffffffffc09e911b:
POPFQ
JMP .Lkd_exit_9
.Lkd_src_ffffffffc09e911f:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e911f
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             QWORD PTR [0xFFFFFFFFC0B9BB60 + 0x8 * RAX], RBX
JMP .Lkd_src_ffffffffc09e9127
.Lkd_runtime_ffffffffc09e911f:
POPFQ
JMP .Lkd_exit_10
.Lkd_src_ffffffffc09e9127:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9127
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR[RBP - 56]
MOV             RAX, R15
JMP .Lkd_src_ffffffffc09e912f
.Lkd_runtime_ffffffffc09e9127:
POPFQ
JMP .Lkd_exit_11
.Lkd_src_ffffffffc09e912f:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e912f
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             QWORD PTR [RSI + 0x10], RAX
JMP .Lkd_src_ffffffffc09e9133
.Lkd_runtime_ffffffffc09e912f:
POPFQ
JMP .Lkd_exit_12
.Lkd_src_ffffffffc09e9133:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9133
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             EAX, 0x10000
JMP .Lkd_src_ffffffffc09e9138
.Lkd_runtime_ffffffffc09e9133:
POPFQ
JMP .Lkd_exit_13
.Lkd_src_ffffffffc09e9138:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9138
DEC QWORD PTR[RBP - 120]
POPFQ
SUB             EAX, 0x2
JMP .Lkd_src_ffffffffc09e913b
.Lkd_runtime_ffffffffc09e9138:
POPFQ
JMP .Lkd_exit_14
.Lkd_src_ffffffffc09e913b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e913b
DEC QWORD PTR[RBP - 120]
POPFQ
JNZ .Lkd_taken_ffffffffc09e913b
JMP .Lkd_src_ffffffffc09e913d
.Lkd_taken_ffffffffc09e913b:
JMP .Lkd_src_ffffffffc09e9138
.Lkd_runtime_ffffffffc09e913b:
POPFQ
JMP .Lkd_exit_15
.Lkd_src_ffffffffc09e913d:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e913d
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RBX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFC8]
JMP .Lkd_src_ffffffffc09e9141
.Lkd_runtime_ffffffffc09e913d:
POPFQ
JMP .Lkd_exit_16
.Lkd_src_ffffffffc09e9141:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9141
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RAX, QWORD PTR [0xFFFFFFFFC0B9D168]
JMP .Lkd_src_ffffffffc09e9148
.Lkd_runtime_ffffffffc09e9141:
POPFQ
JMP .Lkd_exit_17
.Lkd_src_ffffffffc09e9148:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9148
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RDI, RBX
JMP .Lkd_src_ffffffffc09e914b
.Lkd_runtime_ffffffffc09e9148:
POPFQ
JMP .Lkd_exit_18
.Lkd_src_ffffffffc09e914b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e914b
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS          R15, 0xFFFFFFFFC09E9150
MOV             R15, R15
LEA             R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV             QWORD PTR [R13], R15
MOVABS          R14, 0xffffffffc09ec020
JMP .Lkd_src_ffffffffc09ec020
.Lkd_runtime_ffffffffc09e914b:
POPFQ
JMP .Lkd_exit_19
.Lkd_src_ffffffffc09e9189:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9189
DEC QWORD PTR[RBP - 120]
POPFQ
CMP             QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0], 0x41
JMP .Lkd_src_ffffffffc09e918e
.Lkd_runtime_ffffffffc09e9189:
POPFQ
JMP .Lkd_exit_20
.Lkd_src_ffffffffc09e918e:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e918e
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc09e918e
JMP .Lkd_src_ffffffffc09e9194
.Lkd_taken_ffffffffc09e918e:
JMP .Lkd_src_ffffffffc09e9386
.Lkd_runtime_ffffffffc09e918e:
POPFQ
JMP .Lkd_exit_21
.Lkd_src_ffffffffc09e9194:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9194
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RAX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc09e9198
.Lkd_runtime_ffffffffc09e9194:
POPFQ
JMP .Lkd_exit_22
.Lkd_src_ffffffffc09e9198:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9198
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RBX, QWORD PTR [0xFFFFFFFFC0B9B960 + 0x8 * RAX]
JMP .Lkd_src_ffffffffc09e91a0
.Lkd_runtime_ffffffffc09e9198:
POPFQ
JMP .Lkd_exit_23
.Lkd_src_ffffffffc09e91a0:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e91a0
DEC QWORD PTR[RBP - 120]
POPFQ
CMP             RAX, 0x41
JMP .Lkd_src_ffffffffc09e91a4
.Lkd_runtime_ffffffffc09e91a0:
POPFQ
JMP .Lkd_exit_24
.Lkd_src_ffffffffc09e91a4:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e91a4
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc09e91a4
JMP .Lkd_src_ffffffffc09e91aa
.Lkd_taken_ffffffffc09e91a4:
JMP .Lkd_src_ffffffffc09e93b0
.Lkd_runtime_ffffffffc09e91a4:
POPFQ
JMP .Lkd_exit_25
.Lkd_src_ffffffffc09e91aa:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e91aa
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RAX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc09e91ae
.Lkd_runtime_ffffffffc09e91aa:
POPFQ
JMP .Lkd_exit_26
.Lkd_src_ffffffffc09e91ae:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e91ae
DEC QWORD PTR[RBP - 120]
POPFQ
ADD             RBX, 0x1
JMP .Lkd_src_ffffffffc09e91b2
.Lkd_runtime_ffffffffc09e91ae:
POPFQ
JMP .Lkd_exit_27
.Lkd_src_ffffffffc09e91b2:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e91b2
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             QWORD PTR [0xFFFFFFFFC0B9B960 + 0x8 * RAX], RBX
JMP .Lkd_src_ffffffffc09e91ba
.Lkd_runtime_ffffffffc09e91b2:
POPFQ
JMP .Lkd_exit_28
.Lkd_src_ffffffffc09e91ba:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e91ba
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RBX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFC8]
JMP .Lkd_src_ffffffffc09e91be
.Lkd_runtime_ffffffffc09e91ba:
POPFQ
JMP .Lkd_exit_29
.Lkd_src_ffffffffc09e91be:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e91be
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RAX, QWORD PTR [0xFFFFFFFFC0B9D168]
JMP .Lkd_src_ffffffffc09e91c5
.Lkd_runtime_ffffffffc09e91be:
POPFQ
JMP .Lkd_exit_30
.Lkd_src_ffffffffc09e91c5:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e91c5
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RDI, RBX
JMP .Lkd_src_ffffffffc09e91c8
.Lkd_runtime_ffffffffc09e91c5:
POPFQ
JMP .Lkd_exit_31
.Lkd_src_ffffffffc09e91c8:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e91c8
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS          R15, 0xFFFFFFFFC09E91CD
MOV             R15, R15
LEA             R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV             QWORD PTR [R13], R15
MOVABS          R14, 0xffffffffc09ec023
JMP .Lkd_src_ffffffffc09ec023
.Lkd_runtime_ffffffffc09e91c8:
POPFQ
JMP .Lkd_exit_32
.Lkd_src_ffffffffc09e91f4:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e91f4
DEC QWORD PTR[RBP - 120]
POPFQ
CMP             QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0], 0x41
JMP .Lkd_src_ffffffffc09e91f9
.Lkd_runtime_ffffffffc09e91f4:
POPFQ
JMP .Lkd_exit_33
.Lkd_src_ffffffffc09e91f9:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e91f9
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc09e91f9
JMP .Lkd_src_ffffffffc09e91ff
.Lkd_taken_ffffffffc09e91f9:
JMP .Lkd_src_ffffffffc09e931e
.Lkd_runtime_ffffffffc09e91f9:
POPFQ
JMP .Lkd_exit_34
.Lkd_src_ffffffffc09e91ff:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e91ff
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RDI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFC0]
JMP .Lkd_src_ffffffffc09e9203
.Lkd_runtime_ffffffffc09e91ff:
POPFQ
JMP .Lkd_exit_35
.Lkd_src_ffffffffc09e9203:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9203
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RSI, R13
JMP .Lkd_src_ffffffffc09e9206
.Lkd_runtime_ffffffffc09e9203:
POPFQ
JMP .Lkd_exit_36
.Lkd_src_ffffffffc09e9206:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9206
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS          RDX, 0xFFFFFFFFC09E9215
JMP .Lkd_src_ffffffffc09e920d
.Lkd_runtime_ffffffffc09e9206:
POPFQ
JMP .Lkd_exit_37
.Lkd_src_ffffffffc09e920d:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e920d
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RCX, R12
JMP .Lkd_src_ffffffffc09e9210
.Lkd_runtime_ffffffffc09e920d:
POPFQ
JMP .Lkd_exit_38
.Lkd_src_ffffffffc09e9210:
JMP .Lkd_exit_39
.Lkd_src_ffffffffc09e9215:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9215
DEC QWORD PTR[RBP - 120]
POPFQ
ADD             R13, 0x20
JMP .Lkd_src_ffffffffc09e9219
.Lkd_runtime_ffffffffc09e9215:
POPFQ
JMP .Lkd_exit_40
.Lkd_src_ffffffffc09e9219:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9219
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             RBX, R15
JMP .Lkd_src_ffffffffc09e921a
.Lkd_runtime_ffffffffc09e9219:
POPFQ
JMP .Lkd_exit_41
.Lkd_src_ffffffffc09e921a:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e921a
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R14, QWORD PTR[R11 + 48]
MOV             R14, R15
MOV             QWORD PTR[R11 + 48], R14
JMP .Lkd_src_ffffffffc09e921c
.Lkd_runtime_ffffffffc09e921a:
POPFQ
JMP .Lkd_exit_42
.Lkd_src_ffffffffc09e921c:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e921c
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R14, QWORD PTR[R11 + 40]
MOV             R14, R15
MOV             QWORD PTR[R11 + 40], R14
JMP .Lkd_src_ffffffffc09e921e
.Lkd_runtime_ffffffffc09e921c:
POPFQ
JMP .Lkd_exit_43
.Lkd_src_ffffffffc09e921e:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e921e
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R14, QWORD PTR[R11 + 32]
MOV             R14, R15
MOV             QWORD PTR[R11 + 32], R14
JMP .Lkd_src_ffffffffc09e9220
.Lkd_runtime_ffffffffc09e921e:
POPFQ
JMP .Lkd_exit_44
.Lkd_src_ffffffffc09e9220:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9220
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R14, QWORD PTR[R11 + 24]
MOV             R14, R15
MOV             QWORD PTR[R11 + 24], R14
JMP .Lkd_src_ffffffffc09e9222
.Lkd_runtime_ffffffffc09e9220:
POPFQ
JMP .Lkd_exit_45
.Lkd_src_ffffffffc09e9222:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9222
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R12, R15
JMP .Lkd_src_ffffffffc09e9223
.Lkd_runtime_ffffffffc09e9222:
POPFQ
JMP .Lkd_exit_46
.Lkd_src_ffffffffc09e9223:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9223
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             EAX, EAX
JMP .Lkd_src_ffffffffc09e9225
.Lkd_runtime_ffffffffc09e9223:
POPFQ
JMP .Lkd_exit_47
.Lkd_src_ffffffffc09e9225:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9225
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             EDX, EDX
JMP .Lkd_src_ffffffffc09e9227
.Lkd_runtime_ffffffffc09e9225:
POPFQ
JMP .Lkd_exit_48
.Lkd_src_ffffffffc09e9227:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9227
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             ECX, ECX
JMP .Lkd_src_ffffffffc09e9229
.Lkd_runtime_ffffffffc09e9227:
POPFQ
JMP .Lkd_exit_49
.Lkd_src_ffffffffc09e9229:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9229
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             ESI, ESI
JMP .Lkd_src_ffffffffc09e922b
.Lkd_runtime_ffffffffc09e9229:
POPFQ
JMP .Lkd_exit_50
.Lkd_src_ffffffffc09e922b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e922b
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             EDI, EDI
JMP .Lkd_src_ffffffffc09e922d
.Lkd_runtime_ffffffffc09e922b:
POPFQ
JMP .Lkd_exit_51
.Lkd_src_ffffffffc09e922d:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e922d
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             R8D, R8D
JMP .Lkd_src_ffffffffc09e9230
.Lkd_runtime_ffffffffc09e922d:
POPFQ
JMP .Lkd_exit_52
.Lkd_src_ffffffffc09e9230:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9230
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             R9D, R9D
JMP .Lkd_src_ffffffffc09e9233
.Lkd_runtime_ffffffffc09e9230:
POPFQ
JMP .Lkd_exit_53
.Lkd_src_ffffffffc09e9233:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9233
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             R10D, R10D
JMP .Lkd_src_ffffffffc09e9236
.Lkd_runtime_ffffffffc09e9233:
POPFQ
JMP .Lkd_exit_54
.Lkd_src_ffffffffc09e9236:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9236
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR[R11 + 56]
XOR             R15d, R15d
MOV             QWORD PTR[R11 + 56], R15
JMP .Lkd_src_ffffffffc09e9239
.Lkd_runtime_ffffffffc09e9236:
POPFQ
JMP .Lkd_exit_55
.Lkd_src_ffffffffc09e9239:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9239
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R15, R15
MOV             QWORD PTR[RBP - 88], R15
MOV             R14, QWORD PTR[RBP - 88]
PUSHFQ
POPFQ
JMP .Lkd_exit_57
.Lkd_runtime_ffffffffc09e9239:
POPFQ
JMP .Lkd_exit_56
.Lkd_src_ffffffffc09e925f:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e925f
DEC QWORD PTR[RBP - 120]
POPFQ
CMP             QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0], 0x41
JMP .Lkd_src_ffffffffc09e9264
.Lkd_runtime_ffffffffc09e925f:
POPFQ
JMP .Lkd_exit_58
.Lkd_src_ffffffffc09e9264:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9264
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc09e9264
JMP .Lkd_src_ffffffffc09e926a
.Lkd_taken_ffffffffc09e9264:
JMP .Lkd_src_ffffffffc09e9348
.Lkd_runtime_ffffffffc09e9264:
POPFQ
JMP .Lkd_exit_59
.Lkd_src_ffffffffc09e926a:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e926a
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RAX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc09e926e
.Lkd_runtime_ffffffffc09e926a:
POPFQ
JMP .Lkd_exit_60
.Lkd_src_ffffffffc09e926e:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e926e
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RBX, QWORD PTR [0xFFFFFFFFC0B9B960 + 0x8 * RAX]
JMP .Lkd_src_ffffffffc09e9276
.Lkd_runtime_ffffffffc09e926e:
POPFQ
JMP .Lkd_exit_61
.Lkd_src_ffffffffc09e9276:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9276
DEC QWORD PTR[RBP - 120]
POPFQ
CMP             RAX, 0x41
JMP .Lkd_src_ffffffffc09e927a
.Lkd_runtime_ffffffffc09e9276:
POPFQ
JMP .Lkd_exit_62
.Lkd_src_ffffffffc09e927a:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e927a
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc09e927a
JMP .Lkd_src_ffffffffc09e9280
.Lkd_taken_ffffffffc09e927a:
JMP .Lkd_src_ffffffffc09e935d
.Lkd_runtime_ffffffffc09e927a:
POPFQ
JMP .Lkd_exit_63
.Lkd_src_ffffffffc09e9280:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9280
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR[R11 + 32]
MOV             R15, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
MOV             QWORD PTR[R11 + 32], R15
JMP .Lkd_src_ffffffffc09e9284
.Lkd_runtime_ffffffffc09e9280:
POPFQ
JMP .Lkd_exit_64
.Lkd_src_ffffffffc09e9284:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9284
DEC QWORD PTR[RBP - 120]
POPFQ
ADD             RBX, 0x1
JMP .Lkd_src_ffffffffc09e9288
.Lkd_runtime_ffffffffc09e9284:
POPFQ
JMP .Lkd_exit_65
.Lkd_src_ffffffffc09e9288:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9288
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RDI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFC8]
JMP .Lkd_src_ffffffffc09e928c
.Lkd_runtime_ffffffffc09e9288:
POPFQ
JMP .Lkd_exit_66
.Lkd_src_ffffffffc09e928c:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e928c
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR[R11 + 32]
MOV             QWORD PTR [0xFFFFFFFFC0B9B960 + 0x8 * R15], RBX
JMP .Lkd_src_ffffffffc09e9294
.Lkd_runtime_ffffffffc09e928c:
POPFQ
JMP .Lkd_exit_67
.Lkd_src_ffffffffc09e9294:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9294
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RAX, QWORD PTR [0xFFFFFFFFC0B9D168]
JMP .Lkd_src_ffffffffc09e929b
.Lkd_runtime_ffffffffc09e9294:
POPFQ
JMP .Lkd_exit_68
.Lkd_src_ffffffffc09e929b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e929b
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS          R15, 0xFFFFFFFFC09E92A0
MOV             R15, R15
LEA             R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV             QWORD PTR [R13], R15
MOVABS          R14, 0xffffffffc09ec026
JMP .Lkd_src_ffffffffc09ec026
.Lkd_runtime_ffffffffc09e929b:
POPFQ
JMP .Lkd_exit_69
.Lkd_src_ffffffffc09e92c0:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e92c0
DEC QWORD PTR[RBP - 120]
POPFQ
ADD             R13, 0x20
JMP .Lkd_src_ffffffffc09e92c4
.Lkd_runtime_ffffffffc09e92c0:
POPFQ
JMP .Lkd_exit_70
.Lkd_src_ffffffffc09e92c4:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e92c4
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             RBX, R15
JMP .Lkd_src_ffffffffc09e92c5
.Lkd_runtime_ffffffffc09e92c4:
POPFQ
JMP .Lkd_exit_71
.Lkd_src_ffffffffc09e92c5:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e92c5
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R14, QWORD PTR[R11 + 48]
MOV             R14, R15
MOV             QWORD PTR[R11 + 48], R14
JMP .Lkd_src_ffffffffc09e92c7
.Lkd_runtime_ffffffffc09e92c5:
POPFQ
JMP .Lkd_exit_72
.Lkd_src_ffffffffc09e92c7:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e92c7
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R14, QWORD PTR[R11 + 40]
MOV             R14, R15
MOV             QWORD PTR[R11 + 40], R14
JMP .Lkd_src_ffffffffc09e92c9
.Lkd_runtime_ffffffffc09e92c7:
POPFQ
JMP .Lkd_exit_73
.Lkd_src_ffffffffc09e92c9:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e92c9
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R14, QWORD PTR[R11 + 32]
MOV             R14, R15
MOV             QWORD PTR[R11 + 32], R14
JMP .Lkd_src_ffffffffc09e92cb
.Lkd_runtime_ffffffffc09e92c9:
POPFQ
JMP .Lkd_exit_74
.Lkd_src_ffffffffc09e92cb:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e92cb
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R14, QWORD PTR[R11 + 24]
MOV             R14, R15
MOV             QWORD PTR[R11 + 24], R14
JMP .Lkd_src_ffffffffc09e92cd
.Lkd_runtime_ffffffffc09e92cb:
POPFQ
JMP .Lkd_exit_75
.Lkd_src_ffffffffc09e92cd:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e92cd
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R12, R15
JMP .Lkd_src_ffffffffc09e92ce
.Lkd_runtime_ffffffffc09e92cd:
POPFQ
JMP .Lkd_exit_76
.Lkd_src_ffffffffc09e92ce:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e92ce
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             EAX, EAX
JMP .Lkd_src_ffffffffc09e92d0
.Lkd_runtime_ffffffffc09e92ce:
POPFQ
JMP .Lkd_exit_77
.Lkd_src_ffffffffc09e92d0:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e92d0
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             EDX, EDX
JMP .Lkd_src_ffffffffc09e92d2
.Lkd_runtime_ffffffffc09e92d0:
POPFQ
JMP .Lkd_exit_78
.Lkd_src_ffffffffc09e92d2:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e92d2
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             ECX, ECX
JMP .Lkd_src_ffffffffc09e92d4
.Lkd_runtime_ffffffffc09e92d2:
POPFQ
JMP .Lkd_exit_79
.Lkd_src_ffffffffc09e92d4:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e92d4
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             ESI, ESI
JMP .Lkd_src_ffffffffc09e92d6
.Lkd_runtime_ffffffffc09e92d4:
POPFQ
JMP .Lkd_exit_80
.Lkd_src_ffffffffc09e92d6:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e92d6
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             EDI, EDI
JMP .Lkd_src_ffffffffc09e92d8
.Lkd_runtime_ffffffffc09e92d6:
POPFQ
JMP .Lkd_exit_81
.Lkd_src_ffffffffc09e92d8:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e92d8
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             R8D, R8D
JMP .Lkd_src_ffffffffc09e92db
.Lkd_runtime_ffffffffc09e92d8:
POPFQ
JMP .Lkd_exit_82
.Lkd_src_ffffffffc09e92db:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e92db
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             R9D, R9D
JMP .Lkd_src_ffffffffc09e92de
.Lkd_runtime_ffffffffc09e92db:
POPFQ
JMP .Lkd_exit_83
.Lkd_src_ffffffffc09e92de:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e92de
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             R10D, R10D
JMP .Lkd_src_ffffffffc09e92e1
.Lkd_runtime_ffffffffc09e92de:
POPFQ
JMP .Lkd_exit_84
.Lkd_src_ffffffffc09e92e1:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e92e1
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR[R11 + 56]
XOR             R15d, R15d
MOV             QWORD PTR[R11 + 56], R15
JMP .Lkd_src_ffffffffc09e92e4
.Lkd_runtime_ffffffffc09e92e1:
POPFQ
JMP .Lkd_exit_85
.Lkd_src_ffffffffc09e92e4:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e92e4
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R15, R15
MOV             QWORD PTR[RBP - 88], R15
MOV             R14, QWORD PTR[RBP - 88]
PUSHFQ
POPFQ
JMP .Lkd_exit_87
.Lkd_runtime_ffffffffc09e92e4:
POPFQ
JMP .Lkd_exit_86
.Lkd_src_ffffffffc09e931e:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e931e
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RSI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc09e9322
.Lkd_runtime_ffffffffc09e931e:
POPFQ
JMP .Lkd_exit_88
.Lkd_src_ffffffffc09e9322:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9322
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RDI, 0xFFFFFFFFC0B9CC40
JMP .Lkd_src_ffffffffc09e9329
.Lkd_runtime_ffffffffc09e9322:
POPFQ
JMP .Lkd_exit_89
.Lkd_src_ffffffffc09e9329:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9329
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS          R15, 0xFFFFFFFFC09E932E
MOV             R15, R15
LEA             R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV             QWORD PTR [R13], R15
MOVABS          R14, 0xffffffff81dd1d90
JMP .Lkd_exit_91
.Lkd_runtime_ffffffffc09e9329:
POPFQ
JMP .Lkd_exit_90
.Lkd_src_ffffffffc09e9348:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9348
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RSI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc09e934c
.Lkd_runtime_ffffffffc09e9348:
POPFQ
JMP .Lkd_exit_92
.Lkd_src_ffffffffc09e934c:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e934c
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RDI, 0xFFFFFFFFC0B9CCC0
JMP .Lkd_src_ffffffffc09e9353
.Lkd_runtime_ffffffffc09e934c:
POPFQ
JMP .Lkd_exit_93
.Lkd_src_ffffffffc09e9353:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9353
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS          R15, 0xFFFFFFFFC09E9358
MOV             R15, R15
LEA             R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV             QWORD PTR [R13], R15
MOVABS          R14, 0xffffffff81dd1d90
JMP .Lkd_exit_95
.Lkd_runtime_ffffffffc09e9353:
POPFQ
JMP .Lkd_exit_94
.Lkd_src_ffffffffc09e935d:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e935d
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RSI, RAX
JMP .Lkd_src_ffffffffc09e9360
.Lkd_runtime_ffffffffc09e935d:
POPFQ
JMP .Lkd_exit_96
.Lkd_src_ffffffffc09e9360:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9360
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RDI, 0xFFFFFFFFC0B9CCA0
JMP .Lkd_src_ffffffffc09e9367
.Lkd_runtime_ffffffffc09e9360:
POPFQ
JMP .Lkd_exit_97
.Lkd_src_ffffffffc09e9367:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9367
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS          R15, 0xFFFFFFFFC09E936C
MOV             R15, R15
LEA             R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV             QWORD PTR [R13], R15
MOVABS          R14, 0xffffffff81dd1d90
JMP .Lkd_exit_99
.Lkd_runtime_ffffffffc09e9367:
POPFQ
JMP .Lkd_exit_98
.Lkd_src_ffffffffc09e9386:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9386
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RSI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc09e938a
.Lkd_runtime_ffffffffc09e9386:
POPFQ
JMP .Lkd_exit_100
.Lkd_src_ffffffffc09e938a:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e938a
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RDI, 0xFFFFFFFFC0B9CD20
JMP .Lkd_src_ffffffffc09e9391
.Lkd_runtime_ffffffffc09e938a:
POPFQ
JMP .Lkd_exit_101
.Lkd_src_ffffffffc09e9391:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e9391
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS          R15, 0xFFFFFFFFC09E9396
MOV             R15, R15
LEA             R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV             QWORD PTR [R13], R15
MOVABS          R14, 0xffffffff81dd1d90
JMP .Lkd_exit_103
.Lkd_runtime_ffffffffc09e9391:
POPFQ
JMP .Lkd_exit_102
.Lkd_src_ffffffffc09e93b0:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e93b0
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RSI, RAX
JMP .Lkd_src_ffffffffc09e93b3
.Lkd_runtime_ffffffffc09e93b0:
POPFQ
JMP .Lkd_exit_104
.Lkd_src_ffffffffc09e93b3:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e93b3
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RDI, 0xFFFFFFFFC0B9CD00
JMP .Lkd_src_ffffffffc09e93ba
.Lkd_runtime_ffffffffc09e93b3:
POPFQ
JMP .Lkd_exit_105
.Lkd_src_ffffffffc09e93ba:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e93ba
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS          R15, 0xFFFFFFFFC09E93BF
MOV             R15, R15
LEA             R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV             QWORD PTR [R13], R15
MOVABS          R14, 0xffffffff81dd1d90
JMP .Lkd_exit_107
.Lkd_runtime_ffffffffc09e93ba:
POPFQ
JMP .Lkd_exit_106
.Lkd_src_ffffffffc09e93c4:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e93c4
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RSI, RAX
JMP .Lkd_src_ffffffffc09e93c7
.Lkd_runtime_ffffffffc09e93c4:
POPFQ
JMP .Lkd_exit_108
.Lkd_src_ffffffffc09e93c7:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e93c7
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RDI, 0xFFFFFFFFC0B9CD80
JMP .Lkd_src_ffffffffc09e93ce
.Lkd_runtime_ffffffffc09e93c7:
POPFQ
JMP .Lkd_exit_109
.Lkd_src_ffffffffc09e93ce:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e93ce
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS          R15, 0xFFFFFFFFC09E93D3
MOV             R15, R15
LEA             R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV             QWORD PTR [R13], R15
MOVABS          R14, 0xffffffff81dd1d90
JMP .Lkd_exit_111
.Lkd_runtime_ffffffffc09e93ce:
POPFQ
JMP .Lkd_exit_110
.Lkd_src_ffffffffc09e93d8:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e93d8
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RSI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc09e93dc
.Lkd_runtime_ffffffffc09e93d8:
POPFQ
JMP .Lkd_exit_112
.Lkd_src_ffffffffc09e93dc:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e93dc
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RDI, 0xFFFFFFFFC0B9CDA0
JMP .Lkd_src_ffffffffc09e93e3
.Lkd_runtime_ffffffffc09e93dc:
POPFQ
JMP .Lkd_exit_113
.Lkd_src_ffffffffc09e93e3:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e93e3
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS          R15, 0xFFFFFFFFC09E93E8
MOV             R15, R15
LEA             R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV             QWORD PTR [R13], R15
MOVABS          R14, 0xffffffff81dd1d90
JMP .Lkd_exit_115
.Lkd_runtime_ffffffffc09e93e3:
POPFQ
JMP .Lkd_exit_114
.Lkd_src_ffffffffc09ec020:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ec020
DEC QWORD PTR[RBP - 120]
POPFQ
PUSH            RAX
MOV             RAX, RAX
MOV             QWORD PTR[RBP - 88], RAX
POP             RAX
MOV R14, QWORD PTR[RBP - 88]
JMP .Lkd_exit_117
.Lkd_runtime_ffffffffc09ec020:
POPFQ
JMP .Lkd_exit_116
.Lkd_src_ffffffffc09ec023:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ec023
DEC QWORD PTR[RBP - 120]
POPFQ
PUSH            RAX
MOV             RAX, RAX
MOV             QWORD PTR[RBP - 88], RAX
POP             RAX
MOV R14, QWORD PTR[RBP - 88]
JMP .Lkd_exit_119
.Lkd_runtime_ffffffffc09ec023:
POPFQ
JMP .Lkd_exit_118
.Lkd_src_ffffffffc09ec026:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ec026
DEC QWORD PTR[RBP - 120]
POPFQ
PUSH            RAX
MOV             RAX, RAX
MOV             QWORD PTR[RBP - 88], RAX
POP             RAX
MOV R14, QWORD PTR[RBP - 88]
JMP .Lkd_exit_121
.Lkd_runtime_ffffffffc09ec026:
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
MOVABS R15, 0xffffffffc09e90f2
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e90f2
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_2:
MOVABS R15, 0xffffffffc09e90f7
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e90f7
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_3:
MOVABS R15, 0xffffffffc09e90fd
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e90fd
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_4:
MOVABS R15, 0xffffffffc09e9101
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9101
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_5:
MOVABS R15, 0xffffffffc09e9109
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9109
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_6:
MOVABS R15, 0xffffffffc09e910d
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e910d
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_7:
MOVABS R15, 0xffffffffc09e9113
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9113
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_8:
MOVABS R15, 0xffffffffc09e9117
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9117
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_9:
MOVABS R15, 0xffffffffc09e911b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e911b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_10:
MOVABS R15, 0xffffffffc09e911f
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e911f
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_11:
MOVABS R15, 0xffffffffc09e9127
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9127
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_12:
MOVABS R15, 0xffffffffc09e912f
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e912f
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_13:
MOVABS R15, 0xffffffffc09e9133
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9133
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_14:
MOVABS R15, 0xffffffffc09e9138
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9138
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_15:
MOVABS R15, 0xffffffffc09e913b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e913b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_16:
MOVABS R15, 0xffffffffc09e913d
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e913d
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_17:
MOVABS R15, 0xffffffffc09e9141
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9141
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_18:
MOVABS R15, 0xffffffffc09e9148
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9148
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_19:
MOVABS R15, 0xffffffffc09e914b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e914b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_20:
MOVABS R15, 0xffffffffc09e9189
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9189
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_21:
MOVABS R15, 0xffffffffc09e918e
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e918e
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_22:
MOVABS R15, 0xffffffffc09e9194
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9194
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_23:
MOVABS R15, 0xffffffffc09e9198
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9198
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_24:
MOVABS R15, 0xffffffffc09e91a0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e91a0
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_25:
MOVABS R15, 0xffffffffc09e91a4
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e91a4
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_26:
MOVABS R15, 0xffffffffc09e91aa
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e91aa
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_27:
MOVABS R15, 0xffffffffc09e91ae
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e91ae
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_28:
MOVABS R15, 0xffffffffc09e91b2
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e91b2
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_29:
MOVABS R15, 0xffffffffc09e91ba
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e91ba
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_30:
MOVABS R15, 0xffffffffc09e91be
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e91be
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_31:
MOVABS R15, 0xffffffffc09e91c5
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e91c5
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_32:
MOVABS R15, 0xffffffffc09e91c8
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e91c8
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_33:
MOVABS R15, 0xffffffffc09e91f4
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e91f4
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_34:
MOVABS R15, 0xffffffffc09e91f9
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e91f9
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_35:
MOVABS R15, 0xffffffffc09e91ff
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e91ff
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_36:
MOVABS R15, 0xffffffffc09e9203
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9203
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_37:
MOVABS R15, 0xffffffffc09e9206
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9206
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_38:
MOVABS R15, 0xffffffffc09e920d
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e920d
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_39:
MOVABS R15, 0xffffffffc09e9210
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9210
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81512700
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 1
MOV QWORD PTR[RBP - 104], 2
MOV QWORD PTR[RBP - 112], 1
JMP .Lkd_export
.Lkd_exit_40:
MOVABS R15, 0xffffffffc09e9215
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9215
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_41:
MOVABS R15, 0xffffffffc09e9219
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9219
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_42:
MOVABS R15, 0xffffffffc09e921a
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e921a
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_43:
MOVABS R15, 0xffffffffc09e921c
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e921c
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_44:
MOVABS R15, 0xffffffffc09e921e
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e921e
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_45:
MOVABS R15, 0xffffffffc09e9220
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9220
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_46:
MOVABS R15, 0xffffffffc09e9222
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9222
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_47:
MOVABS R15, 0xffffffffc09e9223
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9223
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_48:
MOVABS R15, 0xffffffffc09e9225
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9225
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_49:
MOVABS R15, 0xffffffffc09e9227
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9227
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_50:
MOVABS R15, 0xffffffffc09e9229
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9229
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_51:
MOVABS R15, 0xffffffffc09e922b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e922b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_52:
MOVABS R15, 0xffffffffc09e922d
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e922d
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_53:
MOVABS R15, 0xffffffffc09e9230
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9230
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_54:
MOVABS R15, 0xffffffffc09e9233
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9233
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_55:
MOVABS R15, 0xffffffffc09e9236
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9236
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_56:
MOVABS R15, 0xffffffffc09e9239
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9239
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_57:
MOV QWORD PTR[RBP - 72], R14
MOVABS R15, 0xffffffffc09e9239
MOV QWORD PTR[RBP - 80], R15
MOV QWORD PTR[RBP - 88], R14
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 11
MOV QWORD PTR[RBP - 112], 3
JMP .Lkd_export
.Lkd_exit_58:
MOVABS R15, 0xffffffffc09e925f
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e925f
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_59:
MOVABS R15, 0xffffffffc09e9264
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9264
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_60:
MOVABS R15, 0xffffffffc09e926a
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e926a
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_61:
MOVABS R15, 0xffffffffc09e926e
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e926e
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_62:
MOVABS R15, 0xffffffffc09e9276
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9276
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_63:
MOVABS R15, 0xffffffffc09e927a
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e927a
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_64:
MOVABS R15, 0xffffffffc09e9280
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9280
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_65:
MOVABS R15, 0xffffffffc09e9284
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9284
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_66:
MOVABS R15, 0xffffffffc09e9288
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9288
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_67:
MOVABS R15, 0xffffffffc09e928c
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e928c
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_68:
MOVABS R15, 0xffffffffc09e9294
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9294
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_69:
MOVABS R15, 0xffffffffc09e929b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e929b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_70:
MOVABS R15, 0xffffffffc09e92c0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e92c0
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_71:
MOVABS R15, 0xffffffffc09e92c4
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e92c4
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_72:
MOVABS R15, 0xffffffffc09e92c5
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e92c5
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_73:
MOVABS R15, 0xffffffffc09e92c7
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e92c7
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_74:
MOVABS R15, 0xffffffffc09e92c9
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e92c9
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_75:
MOVABS R15, 0xffffffffc09e92cb
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e92cb
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_76:
MOVABS R15, 0xffffffffc09e92cd
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e92cd
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_77:
MOVABS R15, 0xffffffffc09e92ce
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e92ce
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_78:
MOVABS R15, 0xffffffffc09e92d0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e92d0
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_79:
MOVABS R15, 0xffffffffc09e92d2
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e92d2
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_80:
MOVABS R15, 0xffffffffc09e92d4
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e92d4
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_81:
MOVABS R15, 0xffffffffc09e92d6
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e92d6
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_82:
MOVABS R15, 0xffffffffc09e92d8
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e92d8
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_83:
MOVABS R15, 0xffffffffc09e92db
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e92db
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_84:
MOVABS R15, 0xffffffffc09e92de
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e92de
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_85:
MOVABS R15, 0xffffffffc09e92e1
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e92e1
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_86:
MOVABS R15, 0xffffffffc09e92e4
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e92e4
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_87:
MOV QWORD PTR[RBP - 72], R14
MOVABS R15, 0xffffffffc09e92e4
MOV QWORD PTR[RBP - 80], R15
MOV QWORD PTR[RBP - 88], R14
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 11
MOV QWORD PTR[RBP - 112], 3
JMP .Lkd_export
.Lkd_exit_88:
MOVABS R15, 0xffffffffc09e931e
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e931e
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_89:
MOVABS R15, 0xffffffffc09e9322
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9322
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_90:
MOVABS R15, 0xffffffffc09e9329
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9329
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_91:
MOVABS R15, 0xffffffff81dd1d90
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9329
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd1d90
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_92:
MOVABS R15, 0xffffffffc09e9348
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9348
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_93:
MOVABS R15, 0xffffffffc09e934c
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e934c
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_94:
MOVABS R15, 0xffffffffc09e9353
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9353
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_95:
MOVABS R15, 0xffffffff81dd1d90
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9353
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd1d90
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_96:
MOVABS R15, 0xffffffffc09e935d
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e935d
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_97:
MOVABS R15, 0xffffffffc09e9360
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9360
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_98:
MOVABS R15, 0xffffffffc09e9367
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9367
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_99:
MOVABS R15, 0xffffffff81dd1d90
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9367
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd1d90
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_100:
MOVABS R15, 0xffffffffc09e9386
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9386
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_101:
MOVABS R15, 0xffffffffc09e938a
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e938a
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_102:
MOVABS R15, 0xffffffffc09e9391
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9391
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_103:
MOVABS R15, 0xffffffff81dd1d90
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e9391
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd1d90
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_104:
MOVABS R15, 0xffffffffc09e93b0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e93b0
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_105:
MOVABS R15, 0xffffffffc09e93b3
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e93b3
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_106:
MOVABS R15, 0xffffffffc09e93ba
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e93ba
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_107:
MOVABS R15, 0xffffffff81dd1d90
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e93ba
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd1d90
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_108:
MOVABS R15, 0xffffffffc09e93c4
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e93c4
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_109:
MOVABS R15, 0xffffffffc09e93c7
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e93c7
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_110:
MOVABS R15, 0xffffffffc09e93ce
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e93ce
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_111:
MOVABS R15, 0xffffffff81dd1d90
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e93ce
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd1d90
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_112:
MOVABS R15, 0xffffffffc09e93d8
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e93d8
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_113:
MOVABS R15, 0xffffffffc09e93dc
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e93dc
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_114:
MOVABS R15, 0xffffffffc09e93e3
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e93e3
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_115:
MOVABS R15, 0xffffffff81dd1d90
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e93e3
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd1d90
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_116:
MOVABS R15, 0xffffffffc09ec020
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ec020
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_117:
MOV QWORD PTR[RBP - 72], R14
MOVABS R15, 0xffffffffc09ec020
MOV QWORD PTR[RBP - 80], R15
MOV QWORD PTR[RBP - 88], R14
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 10
MOV QWORD PTR[RBP - 112], 4
JMP .Lkd_export
.Lkd_exit_118:
MOVABS R15, 0xffffffffc09ec023
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ec023
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_119:
MOV QWORD PTR[RBP - 72], R14
MOVABS R15, 0xffffffffc09ec023
MOV QWORD PTR[RBP - 80], R15
MOV QWORD PTR[RBP - 88], R14
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 10
MOV QWORD PTR[RBP - 112], 4
JMP .Lkd_export
.Lkd_exit_120:
MOVABS R15, 0xffffffffc09ec026
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ec026
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_121:
MOV QWORD PTR[RBP - 72], R14
MOVABS R15, 0xffffffffc09ec026
MOV QWORD PTR[RBP - 80], R15
MOV QWORD PTR[RBP - 88], R14
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 10
MOV QWORD PTR[RBP - 112], 4
JMP .Lkd_export


.Lkd_export:
	/* The generated exit has already flushed mapped source GPRs, recovered
	 * physical R12/R13 as BP/SP and written the exact control result slots.
	 * Save all resident source values before reusing RAX/R14 for control. */
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
	/* Keep all private slots allocated through their final read. Returning
	 * publishes no ownership transfer by itself; lock code owns that order. */
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
