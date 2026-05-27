#ifndef KD_INT3_H
#define KD_INT3_H

/*
 * kd_int3.h — int3 handler and runtime code patching declarations.
 *
 * When the disassembler encounters an untranslated call instruction, the
 * daemon marks it KD_EXE_CALL_MISS and the running kernel patches the call
 * site with int3 (0xCC) breakpoints.  When execution hits the breakpoint,
 * __kd_do_int3 redirects to the original call target via the saved offset.
 */

#include <asm/ptrace.h>

/* --- runtime code patching ------------------------------------------------ */

int add_int3_in_lock(unsigned long vaddr);
void modify_var_with_lock(char* ptr, char value);

/* --- int3 handler --------------------------------------------------------- */

int __kd_do_int3(struct pt_regs* regs);

/* --- uaddr hotness tracking ----------------------------------------------- */

int count_uaddr_cnt(unsigned long uaddr);
int check_uaddr_state(unsigned long uaddr);
int is_target_uaddr(unsigned long uaddr);

extern unsigned long TARGET_UADDR[];
extern int int3_changed;
extern unsigned long delegation_end_time;

#endif /* KD_INT3_H */
