/*
 * test_tail_encoding.c — verify encode_tail / decode_tail are inverses.
 */
#include "mock_kernel.h"
#include "test_harness.h"

/* Replicate the encoding logic from kd_mutex.c */
#define _Q_TAIL_IDX_OFFSET 2
#define _Q_TAIL_IDX_BITS 2
#define _Q_TAIL_IDX_MASK ((1U << _Q_TAIL_IDX_BITS) - 1)
#define _Q_TAIL_CPU_OFFSET (_Q_TAIL_IDX_OFFSET + _Q_TAIL_IDX_BITS)

static inline u32 encode_tail(int cpu, int idx)
{
	return (cpu + 1) << _Q_TAIL_CPU_OFFSET | idx << _Q_TAIL_IDX_OFFSET;
}

static inline void decode_tail_fields(u32 tail, int *cpu, int *idx)
{
	*cpu = (tail >> _Q_TAIL_CPU_OFFSET) - 1;
	*idx = (tail >> _Q_TAIL_IDX_OFFSET) & _Q_TAIL_IDX_MASK;
}

TEST(encode_decode_cpu0_idx0)
{
	u32 t = encode_tail(0, 0);
	int cpu, idx;
	decode_tail_fields(t, &cpu, &idx);
	ASSERT_EQ(cpu, 0);
	ASSERT_EQ(idx, 0);
}

TEST(encode_decode_cpu7_idx3)
{
	u32 t = encode_tail(7, 3);
	int cpu, idx;
	decode_tail_fields(t, &cpu, &idx);
	ASSERT_EQ(cpu, 7);
	ASSERT_EQ(idx, 3);
}

TEST(encode_decode_cpu39_idx2)
{
	u32 t = encode_tail(39, 2);
	int cpu, idx;
	decode_tail_fields(t, &cpu, &idx);
	ASSERT_EQ(cpu, 39);
	ASSERT_EQ(idx, 2);
}

TEST(encode_nonzero)
{
	/* encode_tail should never return 0 for valid cpu/idx */
	ASSERT_NE(encode_tail(0, 0), (u32)0);
}

TEST(different_cpus_different_tails)
{
	u32 t1 = encode_tail(0, 0);
	u32 t2 = encode_tail(1, 0);
	ASSERT_NE(t1, t2);
}

int main(void)
{
	printf("=== test_tail_encoding ===\n");
	RUN_TEST(encode_decode_cpu0_idx0);
	RUN_TEST(encode_decode_cpu7_idx3);
	RUN_TEST(encode_decode_cpu39_idx2);
	RUN_TEST(encode_nonzero);
	RUN_TEST(different_cpus_different_tails);
	REPORT();
}
