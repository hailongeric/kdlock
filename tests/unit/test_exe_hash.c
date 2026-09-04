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

	for (int probes = 0; probes < KD_MAX_EXE; probes++) {
		struct kd_exe_info *exe = &kd_exes[pos];

		if (exe->status_code == KD_EXE_UNUSED ||
		    (exe->pid == (int)pid && exe->RIP == ip))
			return exe;
		pos = (pos + 1) % KD_MAX_EXE;
	}
	return NULL;
}

static int kd_exe_is_ready(unsigned int pid, unsigned long ip)
{
	struct kd_exe_info *exe = kd_get_exe(pid, ip);

	return exe && exe->status_code == KD_EXE_NORMAL &&
	       exe->pid == (int)pid &&
	       exe->RIP == ip && exe->code_block != NULL;
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

TEST(ready_requires_published_matching_code) {
	struct kd_exe_info *e;

	init_exes();
	e = kd_get_exe(0, 0x1234);
	e->pid = 0;
	e->RIP = 0x1234;
	e->code_block = (void *)0x1;
	e->status_code = KD_EXE_UNINIT;
	ASSERT_EQ(kd_exe_is_ready(0, 0x1234), 0);
	e->status_code = KD_EXE_NORMAL;
	ASSERT_EQ(kd_exe_is_ready(0, 0x1234), 1);
	e->code_block = NULL;
	ASSERT_EQ(kd_exe_is_ready(0, 0x1234), 0);
	ASSERT_EQ(kd_exe_is_ready(1, 0x1234), 0);
}

TEST(full_table_lookup_fails_closed) {
	init_exes();
	for (int i = 0; i < KD_MAX_EXE; i++) {
		kd_exes[i].status_code = KD_EXE_NORMAL;
		kd_exes[i].pid = i + 1;
		kd_exes[i].RIP = 0x100000 + i;
	}
	ASSERT_EQ(kd_get_exe(0, 0xdeadbeef), NULL);
}

int main(void) {
	printf("=== test_exe_hash ===\n");
	RUN_TEST(lookup_empty_returns_unused);
	RUN_TEST(insert_and_find);
	RUN_TEST(different_pid_same_rip);
	RUN_TEST(collision_resolution);
	RUN_TEST(no_duplicate_on_re_add);
	RUN_TEST(ready_requires_published_matching_code);
	RUN_TEST(full_table_lookup_fails_closed);
	REPORT();
}
