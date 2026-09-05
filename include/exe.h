#ifndef EXE_H
#define EXE_H
#include "exe_info.h"
#include <asm/ptrace.h>
#include <linux/sched/task.h>

struct kd_exe_ret {
	int ret;
	int count;
	int number;
	int wake_num[16];
	unsigned long uaddr[16];
};

void kd_exe_add(int pid, unsigned long RIP);
bool kd_exe_is_ready(unsigned int pid, unsigned long RIP);
int kd_exe_init(void);
void kd_exe_exit(void);
void kd_exe_on_call(struct task_struct *task, struct pt_regs *regs,
		    struct kd_exe_ret *ret);

#define KD_EXE_NO_READY 1
#define KD_EXE_NO_RUN 2
#define KD_EXE_RUN_ERROR 3
#define KD_EXE_RUN_TO_UNLOCK 4
#define KD_EXE_KNOWN_OUTER_UNLOCK 5
#define KD_EXE_RUN_NATIVE 6
#define KD_EXE_NATIVE_DONE 7
#define KD_EXE_KNOWN_NATIVE 8

int kd_exe_on_call_hl_entry(struct pt_regs *regs, unsigned long entry_ip,
			    unsigned long outer_lock_addr);

/* Resume a waiter after its critical section has already run in the sandbox. */
void jump_to_saved_regs(struct pt_regs *regs);
void jump_to_saved_regs_in_cs(struct pt_regs *regs);

struct kd_exe_info *kd_get_exe(unsigned int pid, unsigned long ip);
const struct kd_exe_info *kd_exe_get_slot(unsigned int index);

static inline unsigned int zz_hash(unsigned int pid, unsigned long ip)
{
	return (pid + (ip & 0xFFFF)) * 1000003;
}

#endif
