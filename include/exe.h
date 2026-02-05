#ifndef EXE_H
#define EXE_H

#include <asm/ptrace.h>
#include <linux/spinlock.h>
#include <linux/kfifo.h>
#include <linux/sched/task.h>

#define F_UN_USED -2
#define F_UN_INIT -1
#define F_NORMAL 0
#define F_CALL_MISS 1
#define F_IJ_MISS 2
#define F_ERROR_INST 3
#define F_INST_LIMIT 4

#define F_UADDR_INIT -1
#define F_UADDR_CHECKING 0
#define F_UADDR_DELGEGATE 1
#define F_UADDR_IGNORE -2

static const int MAX_EXE = 511;
static const int MAX_THREAD = 256;

static unsigned int nf_seed = 12345;
static const unsigned int NF_A = 1664525;
static const unsigned int NF_C = 1013904223;
static const unsigned int NF_M = 0xFFFFFFFF;

#define MAX_DELGEGATE_UADDR 31
#define MAX_RAN 511
#define MAX_UADDR 131071
#define MAX_CALL 31

struct exe_info {
	int status_code;
	int pid;
	int tgid;
	unsigned long RIP;
	void* code_block;
	unsigned long jump_from;
	unsigned long tgt_addr;
	// unsigned long fsbase;
	unsigned long gsbase;
	int success_cnt;
	int fail_cnt;
}__attribute__((aligned(64)));


struct recv_pkt {
	int status_code;
	int pid;
	unsigned long RIP;
	unsigned long offset;
};


struct exe_ret {
	int ret;
	int count;
	int number;
	int wake_num[16];
	unsigned long uaddr[16];
};

struct nf_thread {
	int pid;
	unsigned long fsbase;
}__attribute__((aligned(64)));

struct numa_delegate_info {
	atomic_t is_delegating;
}__attribute__((aligned(64)));

struct nf_uaddr_state {
	unsigned long uaddr;
	unsigned long begin;
	unsigned long end;
	int state;
	int cnt;
	char padding_1[96];
	atomic_t is_delegating;
	char padding_2[124];
	struct numa_delegate_info numa_info[2];
}__attribute__((aligned(64)));

struct nf_call_inst {
	unsigned long address;
	int offset;
	char padding[52];
}__attribute__((aligned(64)));

struct nf_delegate_queue {
	atomic_long_t q;
	char padding_2[248];
}__attribute__((aligned(64)));

struct nf_delegate_complete {
	atomic_t state;
	char padding_2[252];
	struct task_struct* task;
	struct pt_regs* regs;
	unsigned long rsp;
	struct futex_q* q;
	u32 val;
	char padding_3[28];
}__attribute__((aligned(64)));

struct nf_delegate_uaddrnode {
	unsigned long uaddr;
	char padding1[248];
	struct nf_delegate_queue queue;
	struct nf_delegate_queue wake_queue;
	struct nf_delegate_complete completes[64];
}__attribute__((aligned(64)));

struct nf_delegate_numanode {
	struct nf_delegate_uaddrnode uaddr_node[MAX_DELGEGATE_UADDR];
}__attribute__((aligned(64)));

struct nf_cycle_cnt {
	int cnt[30];
	unsigned long min;
	unsigned long total;
	unsigned long total_cnt;
	char padding[48];
}__attribute__((aligned(64)));

struct nf_random {
	int ran[MAX_RAN];
	int cur_index;
}__attribute__((aligned(64)));

void exe_add(int pid, unsigned long RIP);
void exe_init(void);
void exe_exit(void);
void exe_on_call(struct task_struct* task, struct pt_regs* regs, struct exe_ret* r);
#define EXE_NO_READY 1
#define EXE_NO_RUN 2
#define EXE_RUN_ERROR 3
#define EXE_RUN_TO_UNLOCK 4

int exe_on_call_hl(struct pt_regs* regs, void* outgoing_rsp_ptr);

struct exe_info* get_exe(unsigned int pid, unsigned long ip);
struct nf_delegate_uaddrnode* get_uaddrnode(unsigned long uaddr, struct nf_delegate_uaddrnode* u_list);
struct nf_uaddr_state* get_uaddr_state(unsigned long uaddr);
struct nf_call_inst* get_call_inst(unsigned long addr);

static inline unsigned int zz_hash(unsigned int pid, unsigned long ip) {
	return (pid + (ip & 0xFFFF)) * 1000003;
}

static inline unsigned int nf_random(void) {
	nf_seed = (NF_A * nf_seed + NF_C) % NF_M;
	return nf_seed;
}

static inline void nf_prefetchw(volatile void* v) {
	barrier();
	__asm__ __volatile__(
		"prefetchw (%0)"
		:
	: "r" (v)
		:
		);
	barrier();
	// *((volatile long*)v) = *((volatile long*)v);
}

static inline void nf_clwb(void* v) {
	__asm__ __volatile__(
		"clwb (%0)"
		:
	: "r" (v)
		: "memory"
		);
}

static inline void nf_cldemote(void* v) {
	__asm__ __volatile__(
		"cldemote (%0)"
		:
	: "r" (v)
		: "memory"
		);
}

#endif
