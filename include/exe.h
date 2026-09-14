#ifndef EXE_H
#define EXE_H
/* Registry and frame-backed executor interface. KD_EXE_RUN_* below are C
 * dispatcher results, not the similarly named wrapper/wire status constants
 * in exe_info.h; backends must preserve that distinction when handing off. */
#include "exe_info.h"
#include <asm/ptrace.h>

void kd_exe_add(int pid, unsigned long RIP, enum kd_exe_lock_kind kind);
bool kd_exe_is_ready(unsigned int pid, unsigned long RIP);
bool kd_exe_publish_status(struct kd_exe_info *exe, int status);
int kd_exe_init(void);
void kd_exe_exit(void);
void kd_exe_retire_all(void);

/*
 * Optional inclusive physical-owner wait, not the complete waiter suffix or
 * queue latency. These helpers do not change the two-word wrapper ABI.
 */
u64 kd_exe_native_timing_start(void);
void kd_exe_native_timing_end(bool mutex, u64 start);

/*
 * Wider envelope: start before borrowing/remote publication and finish after
 * owner wait, before frame cleanup. Only executor-local state crosses ACK.
 */
void kd_exe_native_handoff_timing_end(bool mutex, u64 start);

/*
 * Queue clocks stay outside JIT. Consume the node's timestamp before wake/reuse;
 * a refused JIT attempt leaves it pending until actual service or acquisition.
 */
u64 kd_exe_queue_timing_start(void);
void kd_exe_queue_timing_end(bool mutex, u64 *queued_at, u64 end);

#define KD_EXE_NO_READY 1
#define KD_EXE_NO_RUN 2
#define KD_EXE_RUN_ERROR 3
#define KD_EXE_RUN_TO_UNLOCK 4
#define KD_EXE_KNOWN_OUTER_UNLOCK 5
#define KD_EXE_RUN_NATIVE 6
#define KD_EXE_NATIVE_DONE 7
#define KD_EXE_KNOWN_NATIVE 8

/* Kernel-only entry: requires the caller's validated spin/mutex execution frame. */
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
