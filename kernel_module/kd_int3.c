/*
 * kd_int3.c — int3 handler and runtime code patching.
 *
 * When the disassembler encounters an untranslated call, the daemon adds
 * the callee to the translation table and the kernel patches the original
 * call instruction with int3 (0xCC).  When execution hits the breakpoint,
 * __kd_do_int3 redirects to the original call target via the offset saved
 * in kd_call_insts.
 *
 * Also contains the uaddr hotness tracking logic that promotes frequently
 * contended lock addresses to full delegation.
 */
#include <linux/sched.h>
#include <linux/spinlock.h>
#include <linux/mm.h>
#include <linux/highmem.h>
#include <asm/cacheflush.h>
#include <asm/barrier.h>
#include <asm/uaccess.h>
#include <linux/atomic.h>

#include "kd_lock.h"
#include "kd_int3.h"
#include "exe.h"
#include "utils.h"

/* --- target uaddr filtering ----------------------------------------------- */

unsigned long TARGET_UADDR[] = {};

int is_target_uaddr(unsigned long uaddr)
{
	int length = sizeof(TARGET_UADDR) / sizeof(unsigned long);
	if (length == 0)
		return 1;
	for (int i = 0; i < length; i++)
		if (TARGET_UADDR[i] == uaddr)
			return 1;
	return 0;
}

/* --- runtime code patching: replace call inst with int3 ------------------- */

void modify_var_with_lock(char* ptr, char value)
{
	__asm__ volatile(
		"movq %0, %%rbx\n"
		"mov %1, %%al\n"
		"xchg %%al, (%%rbx)"
		:
	: "r" (ptr), "r" (value)
		: "%rax", "%rbx", "memory"
	);
}

int add_int3_in_lock(unsigned long vaddr)
{
	struct page* pages[1];
	struct kd_call_inst* call_inst = kd_get_call_inst(vaddr);
	int ret;

	ret = get_user_pages_fast(vaddr & PAGE_MASK, 1, FOLL_WRITE | FOLL_FORCE,
				  pages);
	if (ret < 0) {
		pr_err("get user pages failed: %d\n", ret);
		return ret;
	}

	char* buffer = kmap(pages[0]);
	KD_PR_INFO("get userspace data: %hhx %hhx %hhx %hhx %hhx",
		   buffer[vaddr & (~PAGE_MASK)],
		   buffer[(vaddr & (~PAGE_MASK)) + 1],
		   buffer[(vaddr & (~PAGE_MASK)) + 2],
		   buffer[(vaddr & (~PAGE_MASK)) + 3],
		   buffer[(vaddr & (~PAGE_MASK)) + 4]);
	KD_PR_INFO("get userspace data: %lx",
		   *((long*)(buffer + (vaddr & (~PAGE_MASK)))));

	int* offset = (int*)(buffer + (vaddr & (~PAGE_MASK)) + 1);
	call_inst->offset = *offset;

	char* ptr = buffer + (vaddr & (~PAGE_MASK));
	for (int i = 0; i < 5; i++)
		modify_var_with_lock(ptr + i, 0xcc);

	KD_PR_INFO("get userspace data (after patch): %hhx %hhx %hhx %hhx %hhx",
		   buffer[vaddr & (~PAGE_MASK)],
		   buffer[(vaddr & (~PAGE_MASK)) + 1],
		   buffer[(vaddr & (~PAGE_MASK)) + 2],
		   buffer[(vaddr & (~PAGE_MASK)) + 3],
		   buffer[(vaddr & (~PAGE_MASK)) + 4]);
	KD_PR_INFO("get userspace data: %lx",
		   *((long*)(buffer + (vaddr & (~PAGE_MASK)))));

	kunmap(pages[0]);
	put_page(pages[0]);
	stac();
	clflush_cache_range((void *)vaddr, 64);
	return 0;
}

/* --- uaddr hotness tracking: promote contended locks to delegation ------- */

extern atomic_long_t start_work_cycle;
extern atomic_long_t count_uaddr_time;

int count_uaddr_cnt(unsigned long uaddr)
{
	if (atomic_long_read(&start_work_cycle) == 0) {
		atomic_long_cmpxchg(&start_work_cycle, 0, rdtsc_ordered());
		return 0;
	} else if (rdtsc_ordered() - atomic_long_read(&start_work_cycle)
		   < 1000000000)
		return 0;

	struct kd_uaddr_state* u_state = kd_get_uaddr_state(uaddr);

	if (u_state->state == KD_UADDR_DELEGATE)
		return 1;
	if (u_state->state == KD_UADDR_IGNORE) {
		u_state->cnt++;
		if (u_state->cnt == 10000)
			u_state->end = rdtsc_ordered();
		return 0;
	}
	u_state->cnt++;
	if (u_state->state == KD_UADDR_INIT) {
		u_state->state = KD_UADDR_CHECKING;
		u_state->begin = rdtsc_ordered();
		return 0;
	}
	if (u_state->state == KD_UADDR_CHECKING) {
		u_state->end = rdtsc_ordered();
		if (u_state->end - u_state->begin
		    >= atomic_long_read(&count_uaddr_time)) {
			u_state->state = KD_UADDR_IGNORE;
			return 0;
		} else if (u_state->cnt == 10000) {
			KD_PR_INFO("uaddr %lx begin delegate", uaddr);
			atomic_set_release(&u_state->is_delegating, 0);
			atomic_set_release(
				&u_state->numa_info[0].is_delegating, 0);
			atomic_set_release(
				&u_state->numa_info[1].is_delegating, 0);
			u_state->state = KD_UADDR_DELEGATE;
			unsigned long old =
				atomic_long_read(&count_uaddr_time);
			unsigned long new = old;
			while (new / (u_state->end - u_state->begin) >= 10)
				new = new / 10;
			if (new != old)
				atomic_long_cmpxchg(&count_uaddr_time, old,
						    new);
			return 1;
		}
	}
	return 0;
}

int check_uaddr_state(unsigned long uaddr)
{
	struct kd_uaddr_state* u_state = kd_get_uaddr_state(uaddr);
	if (u_state->state == KD_UADDR_DELEGATE)
		return 1;
	return 0;
}

/* --- int3 handler: runtime call redirection ------------------------------- */

int int3_changed = 0;
unsigned long delegation_end_time = 0;

int __kd_do_int3(struct pt_regs* regs)
{
	struct kd_uaddr_state* u_state =
		kd_get_uaddr_state((unsigned long)(regs->di));
	int cpu_id = smp_processor_id();

	if (u_state->state == KD_UADDR_DELEGATE) {
		preempt_disable();

		while (atomic_read_acquire(&u_state->is_delegating) == 1)
			cpu_relax();

		preempt_enable();
	}

	/* Redirect: push return address, jump to original call target */
	struct kd_call_inst* call_inst = kd_get_call_inst(regs->ip - 1);
	regs->sp -= 8;
	stac();
	*((unsigned long*)(regs->sp)) = regs->ip + 4;
	regs->ip += call_inst->offset + 4;

	return 1;
}
