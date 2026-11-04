/* SPDX-License-Identifier: GPL-2.0 */
#define _GNU_SOURCE
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef int8_t s8;
typedef int16_t s16;
typedef int32_t s32;
typedef int64_t s64;
#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))
#define fallthrough __attribute__((fallthrough))
#define cpu_relax() asm volatile("pause" ::: "memory")
#define asm_goto_output asm goto
#define _ASM_EXTABLE(a, b) ""
#define KD_JIT_COMPONENT_FIXTURE
#include "reference.h"
#include "native.h"
#include "kd_reached_jit.c"

#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr,"FAIL line=%d %s\n",__LINE__,#x); exit(1); } } while (0)
struct fixture {
	struct kd_regs regs;
	struct kd_reached_state state;
	u64 memory[32];
	u8 source[16];
	unsigned int length;
	bool fail_read, fail_write;
};
static unsigned int checks;
static int fetch(void *ctx, unsigned long address, void *out, unsigned int size)
{
	struct fixture *f = ctx;
	if (address < 0x1000 || address - 0x1000 + size > f->length) return -ENODATA;
	memcpy(out, f->source + address - 0x1000, size); return 0;
}
static bool range(struct fixture *f, unsigned long address, unsigned int size)
{
	return address >= (unsigned long)f->memory && address - (unsigned long)f->memory <= sizeof(f->memory) &&
		size <= sizeof(f->memory) - (address - (unsigned long)f->memory);
}
static int read_memory(void *ctx, unsigned long address, void *out, unsigned int size)
{
	struct fixture *f = ctx;
	if (f->fail_read || !range(f,address,size)) return -EFAULT;
	memcpy(out,(void *)address,size); return 0;
}
static int write_memory(void *ctx, unsigned long address, const void *in, unsigned int size)
{
	struct fixture *f = ctx;
	if (f->fail_write || !range(f,address,size)) return -EFAULT;
	memcpy((void *)address,in,size); return 0;
}
static int atomic_memory(void *ctx, unsigned long address, unsigned int width,
	enum kd_reached_atomic_op op, u64 input, u64 accumulator, unsigned long flags,
	u64 *old, unsigned long *output)
{
	struct fixture *f = ctx;
	if (f->fail_write || !range(f,address,width)) return -EFAULT;
	return kd_reached_atomic_apply((void *)address,width,op,input,accumulator,flags,old,output);
}
static const struct kd_reached_ops ops = {
	.fetch=fetch,.read=read_memory,.write=write_memory,.atomic=atomic_memory,
};
__attribute__((naked)) static void return_entry(void) { asm volatile("ret"); }

int main(void)
{
	static const char *cases[] = {
		"90","f390","0faee8","0faef0","0faef8",
		"4889c2","89c2","6689c2","88e2","488b03","488903","488d4c8b08",
		"4801c8","01c8","6601c8","00c8","4829c8","4811c8","4819c8",
		"4831c8","4821c8","4809c8","4839c8","4885c8","48ffc0","48ffc8",
		"48f7d0","48f7d8","48d3e0","48d3e8","48d3f8","48d3c0","48d3d8",
		"480fafc1","486bc1ff","480fbec1","480fbfc1","4863c1","0fb6c1",
		"480f44c1","0f44c1","0f94c0","f8","f9","f5","9e","9f","4899","6699","99",
		"50","54","58","5c","c9","e801000000","eb01","7401","488b0424","c3","c20800",
		"48ff13","48ffe1","48ff1424","f3aa","f348ab","f3a4","f3a5",
		"480fbcc1","480fbdc1","f3480fbcc1","f3480fbdc1","480fa3cb",
		"f048010b","f0010b","f066010b","f0000b","f048210b","f048090b","f048310b",
		"48870b","f0480fc10b","f0480fb10b","f0480fba3301","480fba2301",
	};
	struct fixture f;
	unsigned int test, seed, mode;
	u8 *code = mmap(NULL, KD_REACHED_JIT_SLOT_BYTES, PROT_READ|PROT_WRITE|PROT_EXEC,
		MAP_PRIVATE|MAP_ANONYMOUS|MAP_32BIT, -1, 0);
	CHECK(code != MAP_FAILED);
	for (test=0;test<ARRAY_SIZE(cases);++test)
	for (seed=0;seed<8;++seed)
	for (mode=0;mode<3;++mode) {
		struct kd_regs before, expected;
		u64 old_memory[32], expected_memory[32];
		struct decoded decoded;
		enum kd_reached_result result;
		unsigned int i, value;
		int length;
		memset(&f,0,sizeof(f));
		for (i=0;cases[test][2*i];++i) { CHECK(sscanf(cases[test]+2*i,"%2x",&value)==1); f.source[i]=value; }
		f.length=i;
		for (i=0;i<ARRAY_SIZE(f.memory);++i) f.memory[i]=(seed+1)*17+i;
		f.regs=(struct kd_regs){.ip=0x1000,.sp=(unsigned long)&f.memory[20],.bp=(unsigned long)&f.memory[16],
			.ax=(unsigned long)&f.memory[8],.bx=(unsigned long)&f.memory[0],.cx=seed&3,
			.dx=~0UL,.si=(unsigned long)&f.memory[0],.di=(unsigned long)&f.memory[4],.flags=2|((seed&1)?0x8d5:0)};
		f.fail_read=mode==1;f.fail_write=mode==2;
		before=f.regs;memcpy(old_memory,f.memory,sizeof(old_memory));
		CHECK(!kd_reached_begin(&f.state,&f.regs,KD_PACKET_FULL,32));f.state.ops=&ops;f.state.context=&f;
		result=kd_reached_step(&f.state);expected=f.regs;memcpy(expected_memory,f.memory,sizeof(expected_memory));
		f.regs=before;memcpy(f.memory,old_memory,sizeof(old_memory));
		CHECK(!kd_reached_begin(&f.state,&f.regs,KD_PACKET_FULL,32));f.state.ops=&ops;f.state.context=&f;
		CHECK(!kd_reached_decode(&f.state,&decoded));
		length=kd_reached_jit_compile(&decoded,code,KD_REACHED_JIT_SLOT_BYTES,(unsigned long)return_entry);
		CHECK(length>0);
		fprintf(stderr,"case=%u seed=%u mode=%u bytes=%s generated=%d\n",test,seed,mode,cases[test],length);
		CHECK(((enum kd_reached_result (*)(struct kd_reached_state *))code)(&f.state)==result);
		/* Logical AF has no defined Native value. All remaining packet bits
		 * and every memory byte must match the qualified reference effects. */
		if (decoded.operation==OP_AND || decoded.operation==OP_OR || decoded.operation==OP_XOR || decoded.operation==OP_TEST)
			f.regs.flags=(f.regs.flags&~0x10UL)|(expected.flags&0x10);
		if (memcmp(&expected,&f.regs,sizeof(expected))) {
			const unsigned long *a=(const void *)&expected,*b=(const void *)&f.regs;
			for(i=0;i<sizeof(expected)/8;++i)if(a[i]!=b[i])fprintf(stderr,"word%u expected=%lx actual=%lx\n",i,a[i],b[i]);
		}
		CHECK(!memcmp(&expected,&f.regs,sizeof(expected)));
		CHECK(!memcmp(expected_memory,f.memory,sizeof(expected_memory)));
		CHECK(f.state.jit_entries==1 && f.state.interpreted_steps==0);
		CHECK(f.state.jit_retired==(result==KD_REACHED_NEXT || result==KD_REACHED_EDGE));
		CHECK(f.state.jit_code>=(unsigned long)code && f.state.jit_code<(unsigned long)code+length);
	}
	CHECK(!munmap(code,KD_REACHED_JIT_SLOT_BYTES));
	printf("Native reached JIT: %u checks, %zu instruction forms, zero interpreted steps\n",checks,ARRAY_SIZE(cases));
	return 0;
}
