/*
 * test_exe_hash.c — verify kd_get_exe hash table open-addressing logic.
 */
#include "mock_kernel.h"
#include "test_harness.h"

/* Replicate from exe.h / exe_info.h */
#define KD_EXE_UNUSED   -2
#define KD_EXE_UNINIT   -1
#define KD_EXE_NORMAL    0
#define KD_MAX_EXE       511

struct kd_exe_info {
	int status_code;
	int pid;
	int tgid;
	unsigned long RIP;
	void *code_block;
	unsigned long jump_from;
	unsigned long tgt_addr;
	unsigned long gsbase;
	int success_cnt;
	int fail_cnt;
} __attribute__((aligned(64)));

static struct kd_exe_info kd_exes[KD_MAX_EXE];

static inline unsigned int zz_hash(unsigned int pid, unsigned long ip) {
	return (pid + (ip & 0xFFFF)) * 1000003;
}

static struct kd_exe_info *kd_get_exe(unsigned int pid, unsigned long ip) {
	int pos = zz_hash(pid, ip) % KD_MAX_EXE;
	while (kd_exes[pos].status_code != KD_EXE_UNUSED &&
	       (kd_exes[pos].pid != pid || kd_exes[pos].RIP != ip))
		pos = (pos + 1) % KD_MAX_EXE;
	return &kd_exes[pos];
}

static void init_exes(void) {
	for (int i = 0; i < KD_MAX_EXE; i++)
		kd_exes[i].status_code = KD_EXE_UNUSED;
}

TEST(lookup_empty_returns_unused) {
	init_exes();
	struct kd_exe_info *e = kd_get_exe(100, 0xffffffff81001234);
	ASSERT_EQ(e->status_code, KD_EXE_UNUSED);
}

TEST(insert_and_find) {
	init_exes();
	struct kd_exe_info *e = kd_get_exe(100, 0xffffffff81001234);
	e->status_code = KD_EXE_UNINIT;
	e->pid = 100;
	e->RIP = 0xffffffff81001234;

	struct kd_exe_info *f = kd_get_exe(100, 0xffffffff81001234);
	ASSERT_EQ(f, e);
	ASSERT_EQ(f->status_code, KD_EXE_UNINIT);
}

TEST(different_pid_same_rip) {
	init_exes();
	struct kd_exe_info *e1 = kd_get_exe(100, 0xdead);
	e1->status_code = KD_EXE_NORMAL;
	e1->pid = 100;
	e1->RIP = 0xdead;

	struct kd_exe_info *e2 = kd_get_exe(200, 0xdead);
	ASSERT_NE(e1, e2);
	ASSERT_EQ(e2->status_code, KD_EXE_UNUSED);
}

TEST(collision_resolution) {
	init_exes();
	/* Fill several entries with sequential PIDs to force collisions */
	for (int i = 0; i < 20; i++) {
		struct kd_exe_info *e = kd_get_exe(i, 0xbeef);
		e->status_code = KD_EXE_NORMAL;
		e->pid = i;
		e->RIP = 0xbeef;
	}
	/* Verify all 20 can be found */
	for (int i = 0; i < 20; i++) {
		struct kd_exe_info *e = kd_get_exe(i, 0xbeef);
		ASSERT_EQ(e->pid, i);
		ASSERT_EQ(e->RIP, (unsigned long)0xbeef);
		ASSERT_EQ(e->status_code, KD_EXE_NORMAL);
	}
}

TEST(no_duplicate_on_re_add) {
	init_exes();
	struct kd_exe_info *e1 = kd_get_exe(42, 0xcafe);
	e1->status_code = KD_EXE_UNINIT;
	e1->pid = 42;
	e1->RIP = 0xcafe;

	/* Look up again — should return same entry */
	struct kd_exe_info *e2 = kd_get_exe(42, 0xcafe);
	ASSERT_EQ(e1, e2);
}

int main(void) {
	printf("=== test_exe_hash ===\n");
	RUN_TEST(lookup_empty_returns_unused);
	RUN_TEST(insert_and_find);
	RUN_TEST(different_pid_same_rip);
	RUN_TEST(collision_resolution);
	RUN_TEST(no_duplicate_on_re_add);
	REPORT();
}
