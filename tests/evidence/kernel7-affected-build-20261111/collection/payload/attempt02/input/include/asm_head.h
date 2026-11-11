/* SPDX-License-Identifier: GPL-2.0-only */
#include "kd_regs.h"

/* Selected KD mapping: source R11--R15 spill into the one canonical packet.
 * Physical R11 is never allocator scratch. Physical R12/R13 cache BP/SP;
 * mapping recovery must restore them before reaching the common export path.
 */
#define REG_BANK R11
#define Stack_RBP QWORD PTR[REG_BANK + KD_REG_BP]
#define Stack_RSP QWORD PTR[REG_BANK + KD_REG_SP]
#define Stack_R15 QWORD PTR[REG_BANK + KD_REG_R15]
#define Stack_R14 QWORD PTR[REG_BANK + KD_REG_R14]
#define Stack_R13 QWORD PTR[REG_BANK + KD_REG_R13]
#define Stack_R12 QWORD PTR[REG_BANK + KD_REG_R12]
#define Stack_R11 QWORD PTR[REG_BANK + KD_REG_R11]

/* Five native callee-saved registers occupy RBP slots 1--5. The ten allocated
 * local words below contain context/control only, never another source packet.
 */
#define KD_WRAPPER_LOCAL_BYTES 80
#define Stack_RGS QWORD PTR[RBP - 48]
#define Stack_TASK QWORD PTR[RBP - 56]
#define Stack_RCT Stack_TASK
#define Stack_IO QWORD PTR[RBP - 64]
#define Stack_RESUME QWORD PTR[RBP - 72]
#define Stack_RIP Stack_RESUME
#define Stack_RIPL DWORD PTR[RBP - 72]
#define Stack_RIPH DWORD PTR[RBP - 68]
#define Stack_SOURCE QWORD PTR[RBP - 80]
#define Stack_TARGET QWORD PTR[RBP - 88]
#define Stack_IJ Stack_TARGET
#define Stack_KIND QWORD PTR[RBP - 96]
#define Stack_DETAIL QWORD PTR[RBP - 104]
#define Stack_PHASE QWORD PTR[RBP - 112]
#define Stack_BUDGET QWORD PTR[RBP - 120]
