#ifndef EXE_H
#define EXE_H
#include "exe_info.h"
#include <asm/ptrace.h>
#include <linux/sched/task.h>

#define KD_UADDR_INIT     -1
#define KD_UADDR_CHECKING  0
#define KD_UADDR_DELEGATE  1
#define KD_UADDR_IGNORE   -2

#define KD_MAX_EXE          511
#define KD_MAX_THREAD       256
#define KD_MAX_DELEGATE_UADDR 31
#define KD_MAX_RAN          511
#define KD_MAX_UADDR        131071
#define KD_MAX_CALL         31

static unsigned int kd_seed = 12345;
static const unsigned int KD_A = 1664525;
static const unsigned int KD_C = 1013904223;
static const unsigned int KD_M = 0xFFFFFFFF;

struct kd_exe_ret {
	int ret;
	int count;
	int number;
	int wake_num[16];
	unsigned long uaddr[16];
};

struct kd_thread {
	int pid;
	unsigned long fsbase;
}__attribute__((aligned(64)));

struct kd_numa_delegate_info {
	atomic_t is_delegating;
}__attribute__((aligned(64)));

struct kd_uaddr_state {
	unsigned long uaddr;
	unsigned long begin;
	unsigned long end;
	int state;
	int cnt;
	char padding_1[96];
	atomic_t is_delegating;
	char padding_2[124];
	struct kd_numa_delegate_info numa_info[2];
}__attribute__((aligned(64)));

struct kd_call_inst {
	unsigned long address;
	int offset;
	char padding[52];
}__attribute__((aligned(64)));

struct kd_delegate_queue {
	atomic_long_t q;
	char padding_2[248];
}__attribute__((aligned(64)));

struct kd_delegate_complete {
	atomic_t state;
	char padding_2[252];
	struct task_struct* task;
	struct pt_regs* regs;
	unsigned long rsp;
	struct futex_q* q;
	u32 val;
	char padding_3[28];
}__attribute__((aligned(64)));

struct kd_delegate_uaddrnode {
	unsigned long uaddr;
	char padding1[248];
	struct kd_delegate_queue queue;
	struct kd_delegate_queue wake_queue;
	struct kd_delegate_complete completes[64];
}__attribute__((aligned(64)));

struct kd_delegate_numanode {
	struct kd_delegate_uaddrnode uaddr_node[KD_MAX_DELEGATE_UADDR];
}__attribute__((aligned(64)));

struct kd_cycle_cnt {
	int cnt[30];
	unsigned long min;
	unsigned long total;
	unsigned long total_cnt;
	char padding[48];
}__attribute__((aligned(64)));

struct kd_random {
	int ran[KD_MAX_RAN];
	int cur_index;
}__attribute__((aligned(64)));

void kd_exe_add(int pid, unsigned long RIP);
void kd_exe_init(void);
void kd_exe_exit(void);
void kd_exe_on_call(struct task_struct* task, struct pt_regs* regs, struct kd_exe_ret* r);

#define KD_EXE_NO_READY    1
#define KD_EXE_NO_RUN      2
#define KD_EXE_RUN_ERROR   3
#define KD_EXE_RUN_TO_UNLOCK 4

int kd_exe_on_call_hl(struct pt_regs* regs, void* outgoing_rsp_ptr);

struct kd_exe_info* kd_get_exe(unsigned int pid, unsigned long ip);
struct kd_delegate_uaddrnode* kd_get_uaddrnode(unsigned long uaddr, struct kd_delegate_uaddrnode* u_list);
struct kd_uaddr_state* kd_get_uaddr_state(unsigned long uaddr);
struct kd_call_inst* kd_get_call_inst(unsigned long addr);

static inline unsigned int zz_hash(unsigned int pid, unsigned long ip) {
	return (pid + (ip & 0xFFFF)) * 1000003;
}

static inline unsigned int kd_random(void) {
	kd_seed = (KD_A * kd_seed + KD_C) % KD_M;
	return kd_seed;
}

static inline void kd_prefetchw(volatile void* v) {
	barrier();
	__asm__ __volatile__(
		"prefetchw (%0)"
		:
	: "r" (v)
		:
		);
	barrier();
}

static inline void kd_clwb(void* v) {
	__asm__ __volatile__(
		"clwb (%0)"
		:
	: "r" (v)
		: "memory"
		);
}

static inline void kd_cldemote(void* v) {
	__asm__ __volatile__(
		"cldemote (%0)"
		:
	: "r" (v)
		: "memory"
		);
}

#endif