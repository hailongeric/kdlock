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
MOVABS R15, 0xffffffffc09ea0f2
CMP R14, R15
JE .Lkd_enter_ffffffffc09ea0f2
MOVABS R15, 0xffffffffc09ea189
CMP R14, R15
JE .Lkd_enter_ffffffffc09ea189
MOVABS R15, 0xffffffffc09ea1f4
CMP R14, R15
JE .Lkd_enter_ffffffffc09ea1f4
MOVABS R15, 0xffffffffc09ea215
CMP R14, R15
JE .Lkd_enter_ffffffffc09ea215
MOVABS R15, 0xffffffffc09ea25f
CMP R14, R15
JE .Lkd_enter_ffffffffc09ea25f
MOVABS R15, 0xffffffffc09ea2c0
CMP R14, R15
JE .Lkd_enter_ffffffffc09ea2c0
POPFQ
JMP .Lkd_exit_0
.Lkd_enter_ffffffffc09ea0f2:
POPFQ
JMP .Lkd_src_ffffffffc09ea0f2
.Lkd_enter_ffffffffc09ea189:
POPFQ
JMP .Lkd_src_ffffffffc09ea189
.Lkd_enter_ffffffffc09ea1f4:
POPFQ
JMP .Lkd_src_ffffffffc09ea1f4
.Lkd_enter_ffffffffc09ea215:
POPFQ
JMP .Lkd_src_ffffffffc09ea215
.Lkd_enter_ffffffffc09ea25f:
POPFQ
JMP .Lkd_src_ffffffffc09ea25f
.Lkd_enter_ffffffffc09ea2c0:
POPFQ
JMP .Lkd_src_ffffffffc09ea2c0
.Lkd_src_ffffffffc09e8020:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e8020
DEC QWORD PTR[RBP - 120]
POPFQ
PUSH            RAX
MOV             RAX, RAX
MOV             QWORD PTR[RBP - 88], RAX
POP             RAX
MOV R14, QWORD PTR[RBP - 88]
JMP .Lkd_exit_2
.Lkd_runtime_ffffffffc09e8020:
POPFQ
JMP .Lkd_exit_1
.Lkd_src_ffffffffc09e8023:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e8023
DEC QWORD PTR[RBP - 120]
POPFQ
PUSH            RAX
MOV             RAX, RAX
MOV             QWORD PTR[RBP - 88], RAX
POP             RAX
MOV R14, QWORD PTR[RBP - 88]
JMP .Lkd_exit_4
.Lkd_runtime_ffffffffc09e8023:
POPFQ
JMP .Lkd_exit_3
.Lkd_src_ffffffffc09e8026:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09e8026
DEC QWORD PTR[RBP - 120]
POPFQ
PUSH            RAX
MOV             RAX, RAX
MOV             QWORD PTR[RBP - 88], RAX
POP             RAX
MOV R14, QWORD PTR[RBP - 88]
JMP .Lkd_exit_6
.Lkd_runtime_ffffffffc09e8026:
POPFQ
JMP .Lkd_exit_5
.Lkd_src_ffffffffc09ea0f2:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea0f2
DEC QWORD PTR[RBP - 120]
POPFQ
CMP             QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0], 0x41
JMP .Lkd_src_ffffffffc09ea0f7
.Lkd_runtime_ffffffffc09ea0f2:
POPFQ
JMP .Lkd_exit_7
.Lkd_src_ffffffffc09ea0f7:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea0f7
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc09ea0f7
JMP .Lkd_src_ffffffffc09ea0fd
.Lkd_taken_ffffffffc09ea0f7:
JMP .Lkd_src_ffffffffc09ea3d8
.Lkd_runtime_ffffffffc09ea0f7:
POPFQ
JMP .Lkd_exit_8
.Lkd_src_ffffffffc09ea0fd:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea0fd
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RAX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc09ea101
.Lkd_runtime_ffffffffc09ea0fd:
POPFQ
JMP .Lkd_exit_9
.Lkd_src_ffffffffc09ea101:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea101
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RBX, QWORD PTR [0xFFFFFFFFC0B9A920 + 0x8 * RAX]
JMP .Lkd_src_ffffffffc09ea109
.Lkd_runtime_ffffffffc09ea101:
POPFQ
JMP .Lkd_exit_10
.Lkd_src_ffffffffc09ea109:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea109
DEC QWORD PTR[RBP - 120]
POPFQ
CMP             RAX, 0x41
JMP .Lkd_src_ffffffffc09ea10d
.Lkd_runtime_ffffffffc09ea109:
POPFQ
JMP .Lkd_exit_11
.Lkd_src_ffffffffc09ea10d:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea10d
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc09ea10d
JMP .Lkd_src_ffffffffc09ea113
.Lkd_taken_ffffffffc09ea10d:
JMP .Lkd_src_ffffffffc09ea3c4
.Lkd_runtime_ffffffffc09ea10d:
POPFQ
JMP .Lkd_exit_12
.Lkd_src_ffffffffc09ea113:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea113
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RAX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc09ea117
.Lkd_runtime_ffffffffc09ea113:
POPFQ
JMP .Lkd_exit_13
.Lkd_src_ffffffffc09ea117:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea117
DEC QWORD PTR[RBP - 120]
POPFQ
ADD             RBX, 0x1
JMP .Lkd_src_ffffffffc09ea11b
.Lkd_runtime_ffffffffc09ea117:
POPFQ
JMP .Lkd_exit_14
.Lkd_src_ffffffffc09ea11b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea11b
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RSI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFC8]
JMP .Lkd_src_ffffffffc09ea11f
.Lkd_runtime_ffffffffc09ea11b:
POPFQ
JMP .Lkd_exit_15
.Lkd_src_ffffffffc09ea11f:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea11f
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             QWORD PTR [0xFFFFFFFFC0B9A920 + 0x8 * RAX], RBX
JMP .Lkd_src_ffffffffc09ea127
.Lkd_runtime_ffffffffc09ea11f:
POPFQ
JMP .Lkd_exit_16
.Lkd_src_ffffffffc09ea127:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea127
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR[RBP - 56]
MOV             RAX, R15
JMP .Lkd_src_ffffffffc09ea12f
.Lkd_runtime_ffffffffc09ea127:
POPFQ
JMP .Lkd_exit_17
.Lkd_src_ffffffffc09ea12f:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea12f
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             QWORD PTR [RSI + 0x10], RAX
JMP .Lkd_src_ffffffffc09ea133
.Lkd_runtime_ffffffffc09ea12f:
POPFQ
JMP .Lkd_exit_18
.Lkd_src_ffffffffc09ea133:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea133
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             EAX, 0x10000
JMP .Lkd_src_ffffffffc09ea138
.Lkd_runtime_ffffffffc09ea133:
POPFQ
JMP .Lkd_exit_19
.Lkd_src_ffffffffc09ea138:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea138
DEC QWORD PTR[RBP - 120]
POPFQ
SUB             EAX, 0x2
JMP .Lkd_src_ffffffffc09ea13b
.Lkd_runtime_ffffffffc09ea138:
POPFQ
JMP .Lkd_exit_20
.Lkd_src_ffffffffc09ea13b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea13b
DEC QWORD PTR[RBP - 120]
POPFQ
JNZ .Lkd_taken_ffffffffc09ea13b
JMP .Lkd_src_ffffffffc09ea13d
.Lkd_taken_ffffffffc09ea13b:
JMP .Lkd_src_ffffffffc09ea138
.Lkd_runtime_ffffffffc09ea13b:
POPFQ
JMP .Lkd_exit_21
.Lkd_src_ffffffffc09ea13d:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea13d
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RBX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFC8]
JMP .Lkd_src_ffffffffc09ea141
.Lkd_runtime_ffffffffc09ea13d:
POPFQ
JMP .Lkd_exit_22
.Lkd_src_ffffffffc09ea141:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea141
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RAX, QWORD PTR [0xFFFFFFFFC0B9BAF8]
JMP .Lkd_src_ffffffffc09ea148
.Lkd_runtime_ffffffffc09ea141:
POPFQ
JMP .Lkd_exit_23
.Lkd_src_ffffffffc09ea148:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea148
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RDI, RBX
JMP .Lkd_src_ffffffffc09ea14b
.Lkd_runtime_ffffffffc09ea148:
POPFQ
JMP .Lkd_exit_24
.Lkd_src_ffffffffc09ea14b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea14b
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS          R15, 0xFFFFFFFFC09EA150
MOV             R15, R15
LEA             R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV             QWORD PTR [R13], R15
MOVABS          R14, 0xffffffffc09e8020
JMP .Lkd_src_ffffffffc09e8020
.Lkd_runtime_ffffffffc09ea14b:
POPFQ
JMP .Lkd_exit_25
.Lkd_src_ffffffffc09ea189:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea189
DEC QWORD PTR[RBP - 120]
POPFQ
CMP             QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0], 0x41
JMP .Lkd_src_ffffffffc09ea18e
.Lkd_runtime_ffffffffc09ea189:
POPFQ
JMP .Lkd_exit_26
.Lkd_src_ffffffffc09ea18e:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea18e
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc09ea18e
JMP .Lkd_src_ffffffffc09ea194
.Lkd_taken_ffffffffc09ea18e:
JMP .Lkd_src_ffffffffc09ea386
.Lkd_runtime_ffffffffc09ea18e:
POPFQ
JMP .Lkd_exit_27
.Lkd_src_ffffffffc09ea194:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea194
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RAX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc09ea198
.Lkd_runtime_ffffffffc09ea194:
POPFQ
JMP .Lkd_exit_28
.Lkd_src_ffffffffc09ea198:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea198
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RBX, QWORD PTR [0xFFFFFFFFC0B9A720 + 0x8 * RAX]
JMP .Lkd_src_ffffffffc09ea1a0
.Lkd_runtime_ffffffffc09ea198:
POPFQ
JMP .Lkd_exit_29
.Lkd_src_ffffffffc09ea1a0:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea1a0
DEC QWORD PTR[RBP - 120]
POPFQ
CMP             RAX, 0x41
JMP .Lkd_src_ffffffffc09ea1a4
.Lkd_runtime_ffffffffc09ea1a0:
POPFQ
JMP .Lkd_exit_30
.Lkd_src_ffffffffc09ea1a4:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea1a4
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc09ea1a4
JMP .Lkd_src_ffffffffc09ea1aa
.Lkd_taken_ffffffffc09ea1a4:
JMP .Lkd_src_ffffffffc09ea3b0
.Lkd_runtime_ffffffffc09ea1a4:
POPFQ
JMP .Lkd_exit_31
.Lkd_src_ffffffffc09ea1aa:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea1aa
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RAX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc09ea1ae
.Lkd_runtime_ffffffffc09ea1aa:
POPFQ
JMP .Lkd_exit_32
.Lkd_src_ffffffffc09ea1ae:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea1ae
DEC QWORD PTR[RBP - 120]
POPFQ
ADD             RBX, 0x1
JMP .Lkd_src_ffffffffc09ea1b2
.Lkd_runtime_ffffffffc09ea1ae:
POPFQ
JMP .Lkd_exit_33
.Lkd_src_ffffffffc09ea1b2:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea1b2
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             QWORD PTR [0xFFFFFFFFC0B9A720 + 0x8 * RAX], RBX
JMP .Lkd_src_ffffffffc09ea1ba
.Lkd_runtime_ffffffffc09ea1b2:
POPFQ
JMP .Lkd_exit_34
.Lkd_src_ffffffffc09ea1ba:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea1ba
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RBX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFC8]
JMP .Lkd_src_ffffffffc09ea1be
.Lkd_runtime_ffffffffc09ea1ba:
POPFQ
JMP .Lkd_exit_35
.Lkd_src_ffffffffc09ea1be:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea1be
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RAX, QWORD PTR [0xFFFFFFFFC0B9BAF8]
JMP .Lkd_src_ffffffffc09ea1c5
.Lkd_runtime_ffffffffc09ea1be:
POPFQ
JMP .Lkd_exit_36
.Lkd_src_ffffffffc09ea1c5:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea1c5
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RDI, RBX
JMP .Lkd_src_ffffffffc09ea1c8
.Lkd_runtime_ffffffffc09ea1c5:
POPFQ
JMP .Lkd_exit_37
.Lkd_src_ffffffffc09ea1c8:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea1c8
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS          R15, 0xFFFFFFFFC09EA1CD
MOV             R15, R15
LEA             R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV             QWORD PTR [R13], R15
MOVABS          R14, 0xffffffffc09e8023
JMP .Lkd_src_ffffffffc09e8023
.Lkd_runtime_ffffffffc09ea1c8:
POPFQ
JMP .Lkd_exit_38
.Lkd_src_ffffffffc09ea1f4:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea1f4
DEC QWORD PTR[RBP - 120]
POPFQ
CMP             QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0], 0x41
JMP .Lkd_src_ffffffffc09ea1f9
.Lkd_runtime_ffffffffc09ea1f4:
POPFQ
JMP .Lkd_exit_39
.Lkd_src_ffffffffc09ea1f9:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea1f9
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc09ea1f9
JMP .Lkd_src_ffffffffc09ea1ff
.Lkd_taken_ffffffffc09ea1f9:
JMP .Lkd_src_ffffffffc09ea31e
.Lkd_runtime_ffffffffc09ea1f9:
POPFQ
JMP .Lkd_exit_40
.Lkd_src_ffffffffc09ea1ff:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea1ff
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RDI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFC0]
JMP .Lkd_src_ffffffffc09ea203
.Lkd_runtime_ffffffffc09ea1ff:
POPFQ
JMP .Lkd_exit_41
.Lkd_src_ffffffffc09ea203:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea203
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RSI, R13
JMP .Lkd_src_ffffffffc09ea206
.Lkd_runtime_ffffffffc09ea203:
POPFQ
JMP .Lkd_exit_42
.Lkd_src_ffffffffc09ea206:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea206
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS          RDX, 0xFFFFFFFFC09EA215
JMP .Lkd_src_ffffffffc09ea20d
.Lkd_runtime_ffffffffc09ea206:
POPFQ
JMP .Lkd_exit_43
.Lkd_src_ffffffffc09ea20d:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea20d
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RCX, R12
JMP .Lkd_src_ffffffffc09ea210
.Lkd_runtime_ffffffffc09ea20d:
POPFQ
JMP .Lkd_exit_44
.Lkd_src_ffffffffc09ea210:
JMP .Lkd_exit_45
.Lkd_src_ffffffffc09ea215:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea215
DEC QWORD PTR[RBP - 120]
POPFQ
ADD             R13, 0x20
JMP .Lkd_src_ffffffffc09ea219
.Lkd_runtime_ffffffffc09ea215:
POPFQ
JMP .Lkd_exit_46
.Lkd_src_ffffffffc09ea219:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea219
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             RBX, R15
JMP .Lkd_src_ffffffffc09ea21a
.Lkd_runtime_ffffffffc09ea219:
POPFQ
JMP .Lkd_exit_47
.Lkd_src_ffffffffc09ea21a:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea21a
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R14, QWORD PTR[R11 + 48]
MOV             R14, R15
MOV             QWORD PTR[R11 + 48], R14
JMP .Lkd_src_ffffffffc09ea21c
.Lkd_runtime_ffffffffc09ea21a:
POPFQ
JMP .Lkd_exit_48
.Lkd_src_ffffffffc09ea21c:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea21c
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R14, QWORD PTR[R11 + 40]
MOV             R14, R15
MOV             QWORD PTR[R11 + 40], R14
JMP .Lkd_src_ffffffffc09ea21e
.Lkd_runtime_ffffffffc09ea21c:
POPFQ
JMP .Lkd_exit_49
.Lkd_src_ffffffffc09ea21e:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea21e
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R14, QWORD PTR[R11 + 32]
MOV             R14, R15
MOV             QWORD PTR[R11 + 32], R14
JMP .Lkd_src_ffffffffc09ea220
.Lkd_runtime_ffffffffc09ea21e:
POPFQ
JMP .Lkd_exit_50
.Lkd_src_ffffffffc09ea220:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea220
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R14, QWORD PTR[R11 + 24]
MOV             R14, R15
MOV             QWORD PTR[R11 + 24], R14
JMP .Lkd_src_ffffffffc09ea222
.Lkd_runtime_ffffffffc09ea220:
POPFQ
JMP .Lkd_exit_51
.Lkd_src_ffffffffc09ea222:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea222
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R12, R15
JMP .Lkd_src_ffffffffc09ea223
.Lkd_runtime_ffffffffc09ea222:
POPFQ
JMP .Lkd_exit_52
.Lkd_src_ffffffffc09ea223:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea223
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             EAX, EAX
JMP .Lkd_src_ffffffffc09ea225
.Lkd_runtime_ffffffffc09ea223:
POPFQ
JMP .Lkd_exit_53
.Lkd_src_ffffffffc09ea225:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea225
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             EDX, EDX
JMP .Lkd_src_ffffffffc09ea227
.Lkd_runtime_ffffffffc09ea225:
POPFQ
JMP .Lkd_exit_54
.Lkd_src_ffffffffc09ea227:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea227
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             ECX, ECX
JMP .Lkd_src_ffffffffc09ea229
.Lkd_runtime_ffffffffc09ea227:
POPFQ
JMP .Lkd_exit_55
.Lkd_src_ffffffffc09ea229:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea229
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             ESI, ESI
JMP .Lkd_src_ffffffffc09ea22b
.Lkd_runtime_ffffffffc09ea229:
POPFQ
JMP .Lkd_exit_56
.Lkd_src_ffffffffc09ea22b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea22b
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             EDI, EDI
JMP .Lkd_src_ffffffffc09ea22d
.Lkd_runtime_ffffffffc09ea22b:
POPFQ
JMP .Lkd_exit_57
.Lkd_src_ffffffffc09ea22d:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea22d
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             R8D, R8D
JMP .Lkd_src_ffffffffc09ea230
.Lkd_runtime_ffffffffc09ea22d:
POPFQ
JMP .Lkd_exit_58
.Lkd_src_ffffffffc09ea230:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea230
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             R9D, R9D
JMP .Lkd_src_ffffffffc09ea233
.Lkd_runtime_ffffffffc09ea230:
POPFQ
JMP .Lkd_exit_59
.Lkd_src_ffffffffc09ea233:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea233
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             R10D, R10D
JMP .Lkd_src_ffffffffc09ea236
.Lkd_runtime_ffffffffc09ea233:
POPFQ
JMP .Lkd_exit_60
.Lkd_src_ffffffffc09ea236:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea236
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR[R11 + 56]
XOR             R15d, R15d
MOV             QWORD PTR[R11 + 56], R15
JMP .Lkd_src_ffffffffc09ea239
.Lkd_runtime_ffffffffc09ea236:
POPFQ
JMP .Lkd_exit_61
.Lkd_src_ffffffffc09ea239:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea239
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R15, R15
MOV             QWORD PTR[RBP - 88], R15
MOV             R14, QWORD PTR[RBP - 88]
PUSHFQ
POPFQ
JMP .Lkd_exit_63
.Lkd_runtime_ffffffffc09ea239:
POPFQ
JMP .Lkd_exit_62
.Lkd_src_ffffffffc09ea25f:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea25f
DEC QWORD PTR[RBP - 120]
POPFQ
CMP             QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0], 0x41
JMP .Lkd_src_ffffffffc09ea264
.Lkd_runtime_ffffffffc09ea25f:
POPFQ
JMP .Lkd_exit_64
.Lkd_src_ffffffffc09ea264:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea264
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc09ea264
JMP .Lkd_src_ffffffffc09ea26a
.Lkd_taken_ffffffffc09ea264:
JMP .Lkd_src_ffffffffc09ea348
.Lkd_runtime_ffffffffc09ea264:
POPFQ
JMP .Lkd_exit_65
.Lkd_src_ffffffffc09ea26a:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea26a
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RAX, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc09ea26e
.Lkd_runtime_ffffffffc09ea26a:
POPFQ
JMP .Lkd_exit_66
.Lkd_src_ffffffffc09ea26e:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea26e
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RBX, QWORD PTR [0xFFFFFFFFC0B9A720 + 0x8 * RAX]
JMP .Lkd_src_ffffffffc09ea276
.Lkd_runtime_ffffffffc09ea26e:
POPFQ
JMP .Lkd_exit_67
.Lkd_src_ffffffffc09ea276:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea276
DEC QWORD PTR[RBP - 120]
POPFQ
CMP             RAX, 0x41
JMP .Lkd_src_ffffffffc09ea27a
.Lkd_runtime_ffffffffc09ea276:
POPFQ
JMP .Lkd_exit_68
.Lkd_src_ffffffffc09ea27a:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea27a
DEC QWORD PTR[RBP - 120]
POPFQ
JAE .Lkd_taken_ffffffffc09ea27a
JMP .Lkd_src_ffffffffc09ea280
.Lkd_taken_ffffffffc09ea27a:
JMP .Lkd_src_ffffffffc09ea35d
.Lkd_runtime_ffffffffc09ea27a:
POPFQ
JMP .Lkd_exit_69
.Lkd_src_ffffffffc09ea280:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea280
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR[R11 + 32]
MOV             R15, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
MOV             QWORD PTR[R11 + 32], R15
JMP .Lkd_src_ffffffffc09ea284
.Lkd_runtime_ffffffffc09ea280:
POPFQ
JMP .Lkd_exit_70
.Lkd_src_ffffffffc09ea284:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea284
DEC QWORD PTR[RBP - 120]
POPFQ
ADD             RBX, 0x1
JMP .Lkd_src_ffffffffc09ea288
.Lkd_runtime_ffffffffc09ea284:
POPFQ
JMP .Lkd_exit_71
.Lkd_src_ffffffffc09ea288:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea288
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RDI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFC8]
JMP .Lkd_src_ffffffffc09ea28c
.Lkd_runtime_ffffffffc09ea288:
POPFQ
JMP .Lkd_exit_72
.Lkd_src_ffffffffc09ea28c:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea28c
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR[R11 + 32]
MOV             QWORD PTR [0xFFFFFFFFC0B9A720 + 0x8 * R15], RBX
JMP .Lkd_src_ffffffffc09ea294
.Lkd_runtime_ffffffffc09ea28c:
POPFQ
JMP .Lkd_exit_73
.Lkd_src_ffffffffc09ea294:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea294
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RAX, QWORD PTR [0xFFFFFFFFC0B9BAF8]
JMP .Lkd_src_ffffffffc09ea29b
.Lkd_runtime_ffffffffc09ea294:
POPFQ
JMP .Lkd_exit_74
.Lkd_src_ffffffffc09ea29b:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea29b
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS          R15, 0xFFFFFFFFC09EA2A0
MOV             R15, R15
LEA             R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV             QWORD PTR [R13], R15
MOVABS          R14, 0xffffffffc09e8026
JMP .Lkd_src_ffffffffc09e8026
.Lkd_runtime_ffffffffc09ea29b:
POPFQ
JMP .Lkd_exit_75
.Lkd_src_ffffffffc09ea2c0:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea2c0
DEC QWORD PTR[RBP - 120]
POPFQ
ADD             R13, 0x20
JMP .Lkd_src_ffffffffc09ea2c4
.Lkd_runtime_ffffffffc09ea2c0:
POPFQ
JMP .Lkd_exit_76
.Lkd_src_ffffffffc09ea2c4:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea2c4
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             RBX, R15
JMP .Lkd_src_ffffffffc09ea2c5
.Lkd_runtime_ffffffffc09ea2c4:
POPFQ
JMP .Lkd_exit_77
.Lkd_src_ffffffffc09ea2c5:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea2c5
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R14, QWORD PTR[R11 + 48]
MOV             R14, R15
MOV             QWORD PTR[R11 + 48], R14
JMP .Lkd_src_ffffffffc09ea2c7
.Lkd_runtime_ffffffffc09ea2c5:
POPFQ
JMP .Lkd_exit_78
.Lkd_src_ffffffffc09ea2c7:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea2c7
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R14, QWORD PTR[R11 + 40]
MOV             R14, R15
MOV             QWORD PTR[R11 + 40], R14
JMP .Lkd_src_ffffffffc09ea2c9
.Lkd_runtime_ffffffffc09ea2c7:
POPFQ
JMP .Lkd_exit_79
.Lkd_src_ffffffffc09ea2c9:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea2c9
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R14, QWORD PTR[R11 + 32]
MOV             R14, R15
MOV             QWORD PTR[R11 + 32], R14
JMP .Lkd_src_ffffffffc09ea2cb
.Lkd_runtime_ffffffffc09ea2c9:
POPFQ
JMP .Lkd_exit_80
.Lkd_src_ffffffffc09ea2cb:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea2cb
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R14, QWORD PTR[R11 + 24]
MOV             R14, R15
MOV             QWORD PTR[R11 + 24], R14
JMP .Lkd_src_ffffffffc09ea2cd
.Lkd_runtime_ffffffffc09ea2cb:
POPFQ
JMP .Lkd_exit_81
.Lkd_src_ffffffffc09ea2cd:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea2cd
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R12, R15
JMP .Lkd_src_ffffffffc09ea2ce
.Lkd_runtime_ffffffffc09ea2cd:
POPFQ
JMP .Lkd_exit_82
.Lkd_src_ffffffffc09ea2ce:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea2ce
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             EAX, EAX
JMP .Lkd_src_ffffffffc09ea2d0
.Lkd_runtime_ffffffffc09ea2ce:
POPFQ
JMP .Lkd_exit_83
.Lkd_src_ffffffffc09ea2d0:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea2d0
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             EDX, EDX
JMP .Lkd_src_ffffffffc09ea2d2
.Lkd_runtime_ffffffffc09ea2d0:
POPFQ
JMP .Lkd_exit_84
.Lkd_src_ffffffffc09ea2d2:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea2d2
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             ECX, ECX
JMP .Lkd_src_ffffffffc09ea2d4
.Lkd_runtime_ffffffffc09ea2d2:
POPFQ
JMP .Lkd_exit_85
.Lkd_src_ffffffffc09ea2d4:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea2d4
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             ESI, ESI
JMP .Lkd_src_ffffffffc09ea2d6
.Lkd_runtime_ffffffffc09ea2d4:
POPFQ
JMP .Lkd_exit_86
.Lkd_src_ffffffffc09ea2d6:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea2d6
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             EDI, EDI
JMP .Lkd_src_ffffffffc09ea2d8
.Lkd_runtime_ffffffffc09ea2d6:
POPFQ
JMP .Lkd_exit_87
.Lkd_src_ffffffffc09ea2d8:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea2d8
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             R8D, R8D
JMP .Lkd_src_ffffffffc09ea2db
.Lkd_runtime_ffffffffc09ea2d8:
POPFQ
JMP .Lkd_exit_88
.Lkd_src_ffffffffc09ea2db:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea2db
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             R9D, R9D
JMP .Lkd_src_ffffffffc09ea2de
.Lkd_runtime_ffffffffc09ea2db:
POPFQ
JMP .Lkd_exit_89
.Lkd_src_ffffffffc09ea2de:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea2de
DEC QWORD PTR[RBP - 120]
POPFQ
XOR             R10D, R10D
JMP .Lkd_src_ffffffffc09ea2e1
.Lkd_runtime_ffffffffc09ea2de:
POPFQ
JMP .Lkd_exit_90
.Lkd_src_ffffffffc09ea2e1:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea2e1
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR[R11 + 56]
XOR             R15d, R15d
MOV             QWORD PTR[R11 + 56], R15
JMP .Lkd_src_ffffffffc09ea2e4
.Lkd_runtime_ffffffffc09ea2e1:
POPFQ
JMP .Lkd_exit_91
.Lkd_src_ffffffffc09ea2e4:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea2e4
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             R15, QWORD PTR [R13]
LEA             R13, QWORD PTR [R13 + 0x8]
MOV             R15, R15
MOV             QWORD PTR[RBP - 88], R15
MOV             R14, QWORD PTR[RBP - 88]
PUSHFQ
POPFQ
JMP .Lkd_exit_93
.Lkd_runtime_ffffffffc09ea2e4:
POPFQ
JMP .Lkd_exit_92
.Lkd_src_ffffffffc09ea31e:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea31e
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RSI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc09ea322
.Lkd_runtime_ffffffffc09ea31e:
POPFQ
JMP .Lkd_exit_94
.Lkd_src_ffffffffc09ea322:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea322
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RDI, 0xFFFFFFFFC0B9B740
JMP .Lkd_src_ffffffffc09ea329
.Lkd_runtime_ffffffffc09ea322:
POPFQ
JMP .Lkd_exit_95
.Lkd_src_ffffffffc09ea329:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea329
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS          R15, 0xFFFFFFFFC09EA32E
MOV             R15, R15
LEA             R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV             QWORD PTR [R13], R15
MOVABS          R14, 0xffffffff81dd0010
JMP .Lkd_exit_97
.Lkd_runtime_ffffffffc09ea329:
POPFQ
JMP .Lkd_exit_96
.Lkd_src_ffffffffc09ea348:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea348
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RSI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc09ea34c
.Lkd_runtime_ffffffffc09ea348:
POPFQ
JMP .Lkd_exit_98
.Lkd_src_ffffffffc09ea34c:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea34c
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RDI, 0xFFFFFFFFC0B9B7C0
JMP .Lkd_src_ffffffffc09ea353
.Lkd_runtime_ffffffffc09ea34c:
POPFQ
JMP .Lkd_exit_99
.Lkd_src_ffffffffc09ea353:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea353
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS          R15, 0xFFFFFFFFC09EA358
MOV             R15, R15
LEA             R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV             QWORD PTR [R13], R15
MOVABS          R14, 0xffffffff81dd0010
JMP .Lkd_exit_101
.Lkd_runtime_ffffffffc09ea353:
POPFQ
JMP .Lkd_exit_100
.Lkd_src_ffffffffc09ea35d:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea35d
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RSI, RAX
JMP .Lkd_src_ffffffffc09ea360
.Lkd_runtime_ffffffffc09ea35d:
POPFQ
JMP .Lkd_exit_102
.Lkd_src_ffffffffc09ea360:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea360
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RDI, 0xFFFFFFFFC0B9B7A0
JMP .Lkd_src_ffffffffc09ea367
.Lkd_runtime_ffffffffc09ea360:
POPFQ
JMP .Lkd_exit_103
.Lkd_src_ffffffffc09ea367:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea367
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS          R15, 0xFFFFFFFFC09EA36C
MOV             R15, R15
LEA             R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV             QWORD PTR [R13], R15
MOVABS          R14, 0xffffffff81dd0010
JMP .Lkd_exit_105
.Lkd_runtime_ffffffffc09ea367:
POPFQ
JMP .Lkd_exit_104
.Lkd_src_ffffffffc09ea386:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea386
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RSI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc09ea38a
.Lkd_runtime_ffffffffc09ea386:
POPFQ
JMP .Lkd_exit_106
.Lkd_src_ffffffffc09ea38a:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea38a
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RDI, 0xFFFFFFFFC0B9B820
JMP .Lkd_src_ffffffffc09ea391
.Lkd_runtime_ffffffffc09ea38a:
POPFQ
JMP .Lkd_exit_107
.Lkd_src_ffffffffc09ea391:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea391
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS          R15, 0xFFFFFFFFC09EA396
MOV             R15, R15
LEA             R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV             QWORD PTR [R13], R15
MOVABS          R14, 0xffffffff81dd0010
JMP .Lkd_exit_109
.Lkd_runtime_ffffffffc09ea391:
POPFQ
JMP .Lkd_exit_108
.Lkd_src_ffffffffc09ea3b0:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea3b0
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RSI, RAX
JMP .Lkd_src_ffffffffc09ea3b3
.Lkd_runtime_ffffffffc09ea3b0:
POPFQ
JMP .Lkd_exit_110
.Lkd_src_ffffffffc09ea3b3:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea3b3
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RDI, 0xFFFFFFFFC0B9B800
JMP .Lkd_src_ffffffffc09ea3ba
.Lkd_runtime_ffffffffc09ea3b3:
POPFQ
JMP .Lkd_exit_111
.Lkd_src_ffffffffc09ea3ba:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea3ba
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS          R15, 0xFFFFFFFFC09EA3BF
MOV             R15, R15
LEA             R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV             QWORD PTR [R13], R15
MOVABS          R14, 0xffffffff81dd0010
JMP .Lkd_exit_113
.Lkd_runtime_ffffffffc09ea3ba:
POPFQ
JMP .Lkd_exit_112
.Lkd_src_ffffffffc09ea3c4:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea3c4
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RSI, RAX
JMP .Lkd_src_ffffffffc09ea3c7
.Lkd_runtime_ffffffffc09ea3c4:
POPFQ
JMP .Lkd_exit_114
.Lkd_src_ffffffffc09ea3c7:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea3c7
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RDI, 0xFFFFFFFFC0B9B880
JMP .Lkd_src_ffffffffc09ea3ce
.Lkd_runtime_ffffffffc09ea3c7:
POPFQ
JMP .Lkd_exit_115
.Lkd_src_ffffffffc09ea3ce:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea3ce
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS          R15, 0xFFFFFFFFC09EA3D3
MOV             R15, R15
LEA             R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV             QWORD PTR [R13], R15
MOVABS          R14, 0xffffffff81dd0010
JMP .Lkd_exit_117
.Lkd_runtime_ffffffffc09ea3ce:
POPFQ
JMP .Lkd_exit_116
.Lkd_src_ffffffffc09ea3d8:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea3d8
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RSI, QWORD PTR [R12 + 0xFFFFFFFFFFFFFFD0]
JMP .Lkd_src_ffffffffc09ea3dc
.Lkd_runtime_ffffffffc09ea3d8:
POPFQ
JMP .Lkd_exit_118
.Lkd_src_ffffffffc09ea3dc:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea3dc
DEC QWORD PTR[RBP - 120]
POPFQ
MOV             RDI, 0xFFFFFFFFC0B9B8A0
JMP .Lkd_src_ffffffffc09ea3e3
.Lkd_runtime_ffffffffc09ea3dc:
POPFQ
JMP .Lkd_exit_119
.Lkd_src_ffffffffc09ea3e3:
PUSHFQ
CMP QWORD PTR[RBP - 120], 0
JE .Lkd_runtime_ffffffffc09ea3e3
DEC QWORD PTR[RBP - 120]
POPFQ
MOVABS          R15, 0xFFFFFFFFC09EA3E8
MOV             R15, R15
LEA             R13, QWORD PTR [R13 + 0xFFFFFFFFFFFFFFF8]
MOV             QWORD PTR [R13], R15
MOVABS          R14, 0xffffffff81dd0010
JMP .Lkd_exit_121
.Lkd_runtime_ffffffffc09ea3e3:
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
MOVABS R15, 0xffffffffc09e8020
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e8020
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_2:
MOV QWORD PTR[RBP - 72], R14
MOVABS R15, 0xffffffffc09e8020
MOV QWORD PTR[RBP - 80], R15
MOV QWORD PTR[RBP - 88], R14
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 10
MOV QWORD PTR[RBP - 112], 4
JMP .Lkd_export
.Lkd_exit_3:
MOVABS R15, 0xffffffffc09e8023
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e8023
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_4:
MOV QWORD PTR[RBP - 72], R14
MOVABS R15, 0xffffffffc09e8023
MOV QWORD PTR[RBP - 80], R15
MOV QWORD PTR[RBP - 88], R14
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 10
MOV QWORD PTR[RBP - 112], 4
JMP .Lkd_export
.Lkd_exit_5:
MOVABS R15, 0xffffffffc09e8026
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09e8026
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_6:
MOV QWORD PTR[RBP - 72], R14
MOVABS R15, 0xffffffffc09e8026
MOV QWORD PTR[RBP - 80], R15
MOV QWORD PTR[RBP - 88], R14
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 10
MOV QWORD PTR[RBP - 112], 4
JMP .Lkd_export
.Lkd_exit_7:
MOVABS R15, 0xffffffffc09ea0f2
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea0f2
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_8:
MOVABS R15, 0xffffffffc09ea0f7
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea0f7
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_9:
MOVABS R15, 0xffffffffc09ea0fd
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea0fd
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_10:
MOVABS R15, 0xffffffffc09ea101
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea101
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_11:
MOVABS R15, 0xffffffffc09ea109
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea109
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_12:
MOVABS R15, 0xffffffffc09ea10d
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea10d
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_13:
MOVABS R15, 0xffffffffc09ea113
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea113
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_14:
MOVABS R15, 0xffffffffc09ea117
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea117
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_15:
MOVABS R15, 0xffffffffc09ea11b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea11b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_16:
MOVABS R15, 0xffffffffc09ea11f
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea11f
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_17:
MOVABS R15, 0xffffffffc09ea127
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea127
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_18:
MOVABS R15, 0xffffffffc09ea12f
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea12f
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_19:
MOVABS R15, 0xffffffffc09ea133
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea133
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_20:
MOVABS R15, 0xffffffffc09ea138
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea138
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_21:
MOVABS R15, 0xffffffffc09ea13b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea13b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_22:
MOVABS R15, 0xffffffffc09ea13d
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea13d
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_23:
MOVABS R15, 0xffffffffc09ea141
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea141
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_24:
MOVABS R15, 0xffffffffc09ea148
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea148
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_25:
MOVABS R15, 0xffffffffc09ea14b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea14b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_26:
MOVABS R15, 0xffffffffc09ea189
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea189
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_27:
MOVABS R15, 0xffffffffc09ea18e
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea18e
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_28:
MOVABS R15, 0xffffffffc09ea194
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea194
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_29:
MOVABS R15, 0xffffffffc09ea198
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea198
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_30:
MOVABS R15, 0xffffffffc09ea1a0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea1a0
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_31:
MOVABS R15, 0xffffffffc09ea1a4
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea1a4
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_32:
MOVABS R15, 0xffffffffc09ea1aa
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea1aa
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_33:
MOVABS R15, 0xffffffffc09ea1ae
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea1ae
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_34:
MOVABS R15, 0xffffffffc09ea1b2
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea1b2
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_35:
MOVABS R15, 0xffffffffc09ea1ba
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea1ba
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_36:
MOVABS R15, 0xffffffffc09ea1be
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea1be
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_37:
MOVABS R15, 0xffffffffc09ea1c5
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea1c5
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_38:
MOVABS R15, 0xffffffffc09ea1c8
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea1c8
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_39:
MOVABS R15, 0xffffffffc09ea1f4
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea1f4
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_40:
MOVABS R15, 0xffffffffc09ea1f9
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea1f9
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_41:
MOVABS R15, 0xffffffffc09ea1ff
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea1ff
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_42:
MOVABS R15, 0xffffffffc09ea203
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea203
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_43:
MOVABS R15, 0xffffffffc09ea206
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea206
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_44:
MOVABS R15, 0xffffffffc09ea20d
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea20d
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_45:
MOVABS R15, 0xffffffffc09ea210
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea210
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81510980
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 1
MOV QWORD PTR[RBP - 104], 2
MOV QWORD PTR[RBP - 112], 1
JMP .Lkd_export
.Lkd_exit_46:
MOVABS R15, 0xffffffffc09ea215
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea215
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_47:
MOVABS R15, 0xffffffffc09ea219
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea219
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_48:
MOVABS R15, 0xffffffffc09ea21a
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea21a
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_49:
MOVABS R15, 0xffffffffc09ea21c
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea21c
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_50:
MOVABS R15, 0xffffffffc09ea21e
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea21e
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_51:
MOVABS R15, 0xffffffffc09ea220
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea220
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_52:
MOVABS R15, 0xffffffffc09ea222
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea222
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_53:
MOVABS R15, 0xffffffffc09ea223
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea223
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_54:
MOVABS R15, 0xffffffffc09ea225
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea225
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_55:
MOVABS R15, 0xffffffffc09ea227
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea227
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_56:
MOVABS R15, 0xffffffffc09ea229
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea229
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_57:
MOVABS R15, 0xffffffffc09ea22b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea22b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_58:
MOVABS R15, 0xffffffffc09ea22d
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea22d
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_59:
MOVABS R15, 0xffffffffc09ea230
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea230
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_60:
MOVABS R15, 0xffffffffc09ea233
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea233
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_61:
MOVABS R15, 0xffffffffc09ea236
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea236
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_62:
MOVABS R15, 0xffffffffc09ea239
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea239
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_63:
MOV QWORD PTR[RBP - 72], R14
MOVABS R15, 0xffffffffc09ea239
MOV QWORD PTR[RBP - 80], R15
MOV QWORD PTR[RBP - 88], R14
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 11
MOV QWORD PTR[RBP - 112], 3
JMP .Lkd_export
.Lkd_exit_64:
MOVABS R15, 0xffffffffc09ea25f
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea25f
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_65:
MOVABS R15, 0xffffffffc09ea264
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea264
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_66:
MOVABS R15, 0xffffffffc09ea26a
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea26a
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_67:
MOVABS R15, 0xffffffffc09ea26e
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea26e
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_68:
MOVABS R15, 0xffffffffc09ea276
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea276
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_69:
MOVABS R15, 0xffffffffc09ea27a
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea27a
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_70:
MOVABS R15, 0xffffffffc09ea280
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea280
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_71:
MOVABS R15, 0xffffffffc09ea284
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea284
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_72:
MOVABS R15, 0xffffffffc09ea288
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea288
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_73:
MOVABS R15, 0xffffffffc09ea28c
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea28c
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_74:
MOVABS R15, 0xffffffffc09ea294
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea294
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_75:
MOVABS R15, 0xffffffffc09ea29b
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea29b
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_76:
MOVABS R15, 0xffffffffc09ea2c0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea2c0
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_77:
MOVABS R15, 0xffffffffc09ea2c4
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea2c4
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_78:
MOVABS R15, 0xffffffffc09ea2c5
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea2c5
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_79:
MOVABS R15, 0xffffffffc09ea2c7
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea2c7
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_80:
MOVABS R15, 0xffffffffc09ea2c9
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea2c9
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_81:
MOVABS R15, 0xffffffffc09ea2cb
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea2cb
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_82:
MOVABS R15, 0xffffffffc09ea2cd
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea2cd
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_83:
MOVABS R15, 0xffffffffc09ea2ce
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea2ce
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_84:
MOVABS R15, 0xffffffffc09ea2d0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea2d0
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_85:
MOVABS R15, 0xffffffffc09ea2d2
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea2d2
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_86:
MOVABS R15, 0xffffffffc09ea2d4
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea2d4
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_87:
MOVABS R15, 0xffffffffc09ea2d6
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea2d6
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_88:
MOVABS R15, 0xffffffffc09ea2d8
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea2d8
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_89:
MOVABS R15, 0xffffffffc09ea2db
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea2db
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_90:
MOVABS R15, 0xffffffffc09ea2de
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea2de
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_91:
MOVABS R15, 0xffffffffc09ea2e1
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea2e1
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_92:
MOVABS R15, 0xffffffffc09ea2e4
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea2e4
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_93:
MOV QWORD PTR[RBP - 72], R14
MOVABS R15, 0xffffffffc09ea2e4
MOV QWORD PTR[RBP - 80], R15
MOV QWORD PTR[RBP - 88], R14
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 11
MOV QWORD PTR[RBP - 112], 3
JMP .Lkd_export
.Lkd_exit_94:
MOVABS R15, 0xffffffffc09ea31e
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea31e
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_95:
MOVABS R15, 0xffffffffc09ea322
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea322
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_96:
MOVABS R15, 0xffffffffc09ea329
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea329
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_97:
MOVABS R15, 0xffffffff81dd0010
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea329
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd0010
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_98:
MOVABS R15, 0xffffffffc09ea348
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea348
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_99:
MOVABS R15, 0xffffffffc09ea34c
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea34c
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_100:
MOVABS R15, 0xffffffffc09ea353
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea353
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_101:
MOVABS R15, 0xffffffff81dd0010
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea353
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd0010
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_102:
MOVABS R15, 0xffffffffc09ea35d
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea35d
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_103:
MOVABS R15, 0xffffffffc09ea360
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea360
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_104:
MOVABS R15, 0xffffffffc09ea367
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea367
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_105:
MOVABS R15, 0xffffffff81dd0010
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea367
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd0010
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_106:
MOVABS R15, 0xffffffffc09ea386
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea386
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_107:
MOVABS R15, 0xffffffffc09ea38a
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea38a
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_108:
MOVABS R15, 0xffffffffc09ea391
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea391
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_109:
MOVABS R15, 0xffffffff81dd0010
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea391
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd0010
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_110:
MOVABS R15, 0xffffffffc09ea3b0
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea3b0
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_111:
MOVABS R15, 0xffffffffc09ea3b3
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea3b3
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_112:
MOVABS R15, 0xffffffffc09ea3ba
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea3ba
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_113:
MOVABS R15, 0xffffffff81dd0010
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea3ba
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd0010
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_114:
MOVABS R15, 0xffffffffc09ea3c4
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea3c4
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_115:
MOVABS R15, 0xffffffffc09ea3c7
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea3c7
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_116:
MOVABS R15, 0xffffffffc09ea3ce
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea3ce
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_117:
MOVABS R15, 0xffffffff81dd0010
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea3ce
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd0010
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
JMP .Lkd_export
.Lkd_exit_118:
MOVABS R15, 0xffffffffc09ea3d8
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea3d8
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_119:
MOVABS R15, 0xffffffffc09ea3dc
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea3dc
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_120:
MOVABS R15, 0xffffffffc09ea3e3
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea3e3
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0x0
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 5
MOV QWORD PTR[RBP - 104], 9
MOV QWORD PTR[RBP - 112], 0
JMP .Lkd_export
.Lkd_exit_121:
MOVABS R15, 0xffffffff81dd0010
MOV QWORD PTR[RBP - 72], R15
MOVABS R15, 0xffffffffc09ea3e3
MOV QWORD PTR[RBP - 80], R15
MOVABS R15, 0xffffffff81dd0010
MOV QWORD PTR[RBP - 88], R15
MOV QWORD PTR[RBP - 96], 3
MOV QWORD PTR[RBP - 104], 1
MOV QWORD PTR[RBP - 112], 2
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
