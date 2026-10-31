/* Execute actual wrapper/lowering. This is not kernel ownership acceptance. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "kd_regs.h"
#include "kd_jit_batch.h"
extern unsigned char kd_alias_wrapper[];
extern void fixture_invoke_clobber(struct kd_jit_batch_call *);
unsigned long fixture_invoke_padding, fixture_wrapper_stack_residue;
unsigned long fixture_lock, fixture_return;
static unsigned int checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "FAIL %d %s\n", __LINE__, #x); exit(1); } } while (0)
int main(void)
{
	for (unsigned int fault = 0; fault < 4; fault++) {
		struct kd_regs regs = {0};
		unsigned long stack[64], before[64];
		unsigned int state = 1;
		struct kd_jit_batch_call call = {.regs = &regs, .code = kd_alias_wrapper + 32,
			.lock = 0x6000, .unlock = fault == 2 ? 0x7001 : 0x7000,
			.entry_abi = 1, .packet_state = &state, .complete = 1};
		for (unsigned int i = 0; i < 64; i++) stack[i] = 0x9000 + i;
		memcpy(before, stack, sizeof(stack));
		regs.ip = 0x1000;
		regs.sp = (unsigned long)&stack[32];
		regs.bp = (unsigned long)&stack[48];
		fixture_lock = fault == 1 ? 0x6001 : 0x6000;
		fixture_return = fault == 3 ? 0x7778 : 0x7777;
		fixture_invoke_clobber(&call);
		CHECK(state == (fault ? 0U : 2U));
		CHECK(call.args[0] == (fault ? 1UL : 7UL));
		CHECK(call.args[1] == 1);
		CHECK(regs.ip == (fault ? 0x8000UL : 0x7777UL));
		CHECK(regs.sp == (unsigned long)&stack[fault ? 31 : 32]);
		CHECK(regs.bp == (unsigned long)&stack[48]);
		for (unsigned int i = 0; i < 64; i++)
			CHECK(stack[i] == (fault && i == 31 ? 0x7777UL : before[i]));
		if (fault) CHECK(regs.di == fixture_lock && regs.dx == fixture_return);
	}
	printf("alias wrapper checks=%u\n", checks);
	return 0;
}
