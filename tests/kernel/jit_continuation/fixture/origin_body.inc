/* Four committed effects bracket distinct services in the same source body.
 * The first RDTSC and its complete flag observations precede this include. */
WRITE_ONCE(origin_effects[0], READ_ONCE(origin_effects[0]) + 1);
asm volatile("movl $1, %%eax\n\tcmpl $2, %%eax\n\t"
	     ".globl jit_origin_rdtscp_first\njit_origin_rdtscp_first:\n\t"
	     "rdtscp\n\t"
	     "movl %%eax, %[low]\n\tmovl %%edx, %[high]\n\tmovl %%ecx, %[aux]\n\t"
	     "jc 1f\n\tmovb $0, %[branch]\n\tjmp 2f\n1:\n\tmovb $1, %[branch]\n2:\n\t"
	     "setc %[carry]\n\tsetp %[parity]\n\tsetz %[zero]\n\tsets %[sign]\n\tseto %[overflow]\n\t"
	     : [low] "=m"(observed.timestamp_low[0]), [high] "=m"(observed.timestamp_high[0]),
	       [aux] "=m"(observed.auxiliary[0]), [carry] "=m"(observed.stage_carry[0]), [parity] "=m"(observed.stage_parity[0]),
	       [zero] "=m"(observed.stage_zero[0]), [sign] "=m"(observed.stage_sign[0]),
	       [overflow] "=m"(observed.stage_overflow[0]), [branch] "=m"(observed.stage_branch[0])
	     : : "rax", "rcx", "rdx", "cc", "memory");
WRITE_ONCE(origin_effects[1], READ_ONCE(origin_effects[1]) + 1);
/* Leaf 1 includes the logical processor's APIC identity in EBX. The expected
 * native value is sampled by this singleton-affinity worker before locking. */
asm volatile("movl $1, %%eax\n\tmovl $0, %%ecx\n\tcmpl $2, %%eax\n\t"
	     ".globl jit_origin_cpuid\njit_origin_cpuid:\n\t"
	     "cpuid\n\t"
	     "movl %%eax, %[a]\n\tmovl %%ebx, %[b]\n\tmovl %%ecx, %[c]\n\tmovl %%edx, %[d]\n\t"
	     "jc 1f\n\tmovb $0, %[branch]\n\tjmp 2f\n1:\n\tmovb $1, %[branch]\n2:\n\t"
	     "setc %[carry]\n\tsetp %[parity]\n\tsetz %[zero]\n\tsets %[sign]\n\tseto %[overflow]\n\t"
	     : [a] "=m"(observed.cpuid[0]), [b] "=m"(observed.cpuid[1]),
	       [c] "=m"(observed.cpuid[2]), [d] "=m"(observed.cpuid[3]),
	       [carry] "=m"(observed.stage_carry[1]), [parity] "=m"(observed.stage_parity[1]),
	       [zero] "=m"(observed.stage_zero[1]), [sign] "=m"(observed.stage_sign[1]), [overflow] "=m"(observed.stage_overflow[1]),
	       [branch] "=m"(observed.stage_branch[1])
	     : : "rax", "rbx", "rcx", "rdx", "cc", "memory");
WRITE_ONCE(origin_effects[2], READ_ONCE(origin_effects[2]) + 1);
asm volatile("movl $1, %%eax\n\tcmpl $2, %%eax\n\t"
	     ".globl jit_origin_rdtscp_second\njit_origin_rdtscp_second:\n\t"
	     "rdtscp\n\t"
	     "movl %%eax, %[low]\n\tmovl %%edx, %[high]\n\tmovl %%ecx, %[aux]\n\t"
	     "jc 1f\n\tmovb $0, %[branch]\n\tjmp 2f\n1:\n\tmovb $1, %[branch]\n2:\n\t"
	     "setc %[carry]\n\tsetp %[parity]\n\tsetz %[zero]\n\tsets %[sign]\n\tseto %[overflow]\n\t"
	     : [low] "=m"(observed.timestamp_low[1]), [high] "=m"(observed.timestamp_high[1]),
	       [aux] "=m"(observed.auxiliary[1]), [carry] "=m"(observed.stage_carry[2]), [parity] "=m"(observed.stage_parity[2]),
	       [zero] "=m"(observed.stage_zero[2]), [sign] "=m"(observed.stage_sign[2]),
	       [overflow] "=m"(observed.stage_overflow[2]), [branch] "=m"(observed.stage_branch[2])
	     : : "rax", "rcx", "rdx", "cc", "memory");
WRITE_ONCE(origin_effects[3], READ_ONCE(origin_effects[3]) + 1);
