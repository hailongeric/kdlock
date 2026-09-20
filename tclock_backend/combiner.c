// SPDX-License-Identifier: GPL-2.0
// Copyright (c) 2022 Vishal Gupta, Kumar Kartikeya Dwivedi
/* Upstream C inline-assembly context switch. The provider owns batch size;
 * this external module omits the upstream in-kernel statistics syscalls.
 */
#include "compat.h"

#pragma GCC push_options
#pragma GCC optimize("O3")
__attribute__((noipa)) noinline notrace void
komb_context_switch(void *incoming_rsp_ptr, void *outgoing_rsp_ptr)
{
	asm volatile("pushq %%rbp\n"
		     "pushq %%rbx\n"
		     "pushq %%r12\n"
		     "pushq %%r13\n"
		     "pushq %%r14\n"
		     "pushq %%r15\n"
		     "movq %%rsp, (%%rsi)\n"
		     "movq (%%rdi), %%rsp\n"
		     "popq %%r15\n"
		     "popq %%r14\n"
		     "popq %%r13\n"
		     "popq %%r12\n"
		     "popq %%rbx\n"
		     "popq %%rbp\n"
		     :
		     :
		     : "memory");
}
#pragma GCC pop_options
