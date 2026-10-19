#include "kd_regs.h"
/* x86-64 kd_regs offsets and physical wrapper-frame slots used by jit.S.
 * Keep this layout synchronized with wrapper.S and JIT_REGISTER_ABI.md.
 * GS/task inputs occupy two existing words; no hardware context is switched. */
#define PT_REG R14
#define ARG_REG R15
/* Physical R11 is reserved for the authoritative packet throughout the body.
 * Logical R11 is virtualized by conflict.py, just like logical R12--R15. */
#define REG_BANK R11

#define MEM_ARG QWORD PTR[ARG_REG]
#define MEM_ARG2 QWORD PTR[ARG_REG + 8]

#define PT_R15 QWORD PTR[PT_REG + KD_REG_R15]
#define PT_R14 QWORD PTR[PT_REG + KD_REG_R14]
#define PT_R13 QWORD PTR[PT_REG + KD_REG_R13]
#define PT_R12 QWORD PTR[PT_REG + KD_REG_R12]
#define PT_RBP QWORD PTR[PT_REG + KD_REG_BP]
#define PT_RBX QWORD PTR[PT_REG + KD_REG_BX]
#define PT_R11 QWORD PTR[PT_REG + KD_REG_R11]
#define PT_R10 QWORD PTR[PT_REG + KD_REG_R10]
#define PT_R9 QWORD PTR[PT_REG + KD_REG_R9]
#define PT_R8 QWORD PTR[PT_REG + KD_REG_R8]
#define PT_RAX QWORD PTR[PT_REG + KD_REG_AX]
#define PT_RCX QWORD PTR[PT_REG + KD_REG_CX]
#define PT_RDX QWORD PTR[PT_REG + KD_REG_DX]
#define PT_RSI QWORD PTR[PT_REG + KD_REG_SI]
#define PT_RDI QWORD PTR[PT_REG + KD_REG_DI]
#define PT_RIP QWORD PTR[PT_REG + KD_REG_IP]
#define PT_EFLAGS QWORD PTR[PT_REG + KD_REG_FLAGS]
#define PT_RSP QWORD PTR[PT_REG + KD_REG_SP]
#define Stack_PT_REG QWORD PTR[RBP - 8 * 6]
#define Stack_ARG_REG QWORD PTR[RBP - 8 * 7]

/* Historical Stack_* names now address the same storage as PT_*; they are
 * JIT backing slots, not a second entry snapshot on the combiner stack.
 * Physical R12/R13 still cache logical BP/SP and must be flushed on exit. */
#define Stack_RBP QWORD PTR[REG_BANK + KD_REG_BP]
#define Stack_RSP QWORD PTR[REG_BANK + KD_REG_SP]
#define Stack_R15 QWORD PTR[REG_BANK + KD_REG_R15]
#define Stack_R14 QWORD PTR[REG_BANK + KD_REG_R14]
#define Stack_R13 QWORD PTR[REG_BANK + KD_REG_R13]
#define Stack_R12 QWORD PTR[REG_BANK + KD_REG_R12]
#define Stack_R11 QWORD PTR[REG_BANK + KD_REG_R11]
/* Reuse one vacated slot for the per-invocation block budget. Other vacated
 * words stay reserved so independent control/context offsets do not move. */
#define Stack_BUDGET QWORD PTR[RBP - 8 * 8]
/* Direct string images reuse private reserved words; no packet/args growth.
 * Remaining quotas are exported only once after this wrapper invocation. */
#define Stack_STRCMP_LEFT QWORD PTR[RBP - 8 * 9]
#define Stack_PAD_LEFT QWORD PTR[RBP - 8 * 10]
/* Slots 11 and 12 remain reserved; direct calls align the wrapper once and
 * use flag-neutral register bookkeeping rather than per-call stack scratch. */

#define Stack_RGS QWORD PTR[RBP - 8 * 15]
#define Stack_TASK QWORD PTR[RBP - 8 * 16]
#define Stack_RCT Stack_TASK

#define Stack_RIP QWORD PTR[RBP - 8 * 17]
#define Stack_IJ QWORD PTR[RBP - 8 * 18]
#define Stack_BATCH QWORD PTR[RBP - 8 * 20]
#define Stack_CLOBBER QWORD PTR[RBP - 8 * 21]
#define Stack_JIT_WITNESS QWORD PTR[RBP - 8 * 19]

#define PT_GS QWORD PTR[ARG_REG]
#define PT_TASK QWORD PTR[ARG_REG + 8]

#define Stack_RIPL DWORD PTR[RBP - 8 * 17]
#define Stack_RIPH DWORD PTR[RBP - 8 * 17 + 4]

/* R11: packet base; R13: virtual RSP; R14: RIP/target; R15: IJ source. */
