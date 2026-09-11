/* SPDX-License-Identifier: GPL-2.0 */
/* Exercise production registration with bounded memory/copy substitutes.
 * No generated machine code, kernel locks or executable permissions run here.
 */
#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>

#include "exe_info.h"
#include "kd_call.h"
#include "kd_hostcall.h"
#include "kd_source_api.h"

struct pt_regs {
	unsigned long ax;
};
struct task_struct {
	int tgid, pid;
};
struct file;
typedef struct {
	int counter;
} atomic_t;
typedef long long atomic64_t;

/* Type-check the production capacity diagnostic's real caller identity too. */
static struct task_struct task = { .tgid = 42, .pid = 43 };
static struct task_struct *current = &task;
static int checks, failures, errors, warnings;

#define CHECK(expr)                                                     \
	do {                                                            \
		checks++;                                               \
		if (!(expr)) {                                          \
			fprintf(stderr, "FAIL line %d: %s\n", __LINE__, \
				#expr);                                 \
			failures++;                                     \
		}                                                       \
	} while (0)
#define PAGE_SIZE 4096
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define ATOMIC_INIT(value) { value }
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_RELAXED)
#define smp_load_acquire(p) __atomic_load_n(p, __ATOMIC_ACQUIRE)
#define smp_store_release(p, v) __atomic_store_n(p, v, __ATOMIC_RELEASE)
#define atomic_set(p, v) __atomic_store_n(&(p)->counter, v, __ATOMIC_RELAXED)
#define atomic_set_release(p, v) smp_store_release(&(p)->counter, v)
#define atomic64_set(p, v) (*(p) = (v))
#define atomic64_read(p) (*(p))
#define try_cmpxchg(p, old, v)                                          \
	__atomic_compare_exchange_n(p, old, v, false, __ATOMIC_SEQ_CST, \
				    __ATOMIC_SEQ_CST)
#define cpu_relax() __asm__ volatile("pause" ::: "memory")
#define __user
#define KD_PR_INFO(...)                      \
	do {                                 \
		if (0)                       \
			printf(__VA_ARGS__); \
	} while (0)
#define KD_PR_ERR(...)                                            \
	do {                                                      \
		__atomic_add_fetch(&errors, 1, __ATOMIC_RELAXED); \
		KD_PR_INFO(__VA_ARGS__);                          \
	} while (0)
#define pr_warn_ratelimited(...)                                    \
	do {                                                        \
		__atomic_add_fetch(&warnings, 1, __ATOMIC_RELAXED); \
		KD_PR_INFO(__VA_ARGS__);                            \
	} while (0)

static int atomic_cmpxchg_acquire(atomic_t *p, int old, int value)
{
	__atomic_compare_exchange_n(&p->counter, &old, value, false,
				    __ATOMIC_ACQUIRE, __ATOMIC_RELAXED);
	return old;
}

/* Allocation/copy failures are injected only at external APIs. The tested
 * registration and teardown code must make every resource/state decision. */
enum allocation_mode { NORMAL, FAIL_TABLE, FAIL_BLOCKS, FAIL_EXEC, PARTIAL };
static enum allocation_mode allocation_mode;
static struct allocation {
	void *ptr;
	size_t size;
	bool live;
} allocations[1024];
static unsigned int allocation_count, block_attempts, exec_attempts;
static int copy_calls, fail_copy;

static void *allocate(size_t size)
{
	void *ptr = NULL;

	if (allocation_count == ARRAY_SIZE(allocations) ||
	    posix_memalign(&ptr, PAGE_SIZE, size + 16))
		abort();
	memset(ptr, 0, size + 16);
	allocations[allocation_count++] =
		(struct allocation){ ptr, size, true };
	return ptr;
}

static void *vzalloc(size_t size)
{
	return allocation_mode == FAIL_TABLE ? NULL : allocate(size);
}

static void *vmalloc(size_t size)
{
	block_attempts++;
	if (allocation_mode == FAIL_BLOCKS ||
	    (allocation_mode == PARTIAL && block_attempts % 2 == 0))
		return NULL;
	return allocate(size);
}

static void vfree(void *ptr)
{
	if (!ptr)
		return;
	for (unsigned int i = allocation_count; i > 0; i--) {
		struct allocation *a = &allocations[i - 1];

		if (a->ptr != ptr || !a->live)
			continue;
		/* Red zones keep bounds mutants non-dangerous while detecting writes. */
		for (size_t j = 0; j < 16; j++)
			CHECK(((unsigned char *)ptr)[a->size + j] == 0);
		a->live = false;
		free(ptr);
		return;
	}
	CHECK(!"double free or unknown allocation");
}

static int set_memory_x(unsigned long addr, int pages)
{
	CHECK(addr != 0 && pages == KD_CODE_BLOCK_SIZE / PAGE_SIZE);
	exec_attempts++;
	return allocation_mode == FAIL_EXEC || (allocation_mode == PARTIAL &&
						exec_attempts % 3 == 0) ?
		       -ENOMEM :
		       0;
}

static unsigned long kallsyms_lookup_name(const char *name)
{
	return (unsigned long)name;
}

static unsigned long ktime_get(void)
{
	return 0;
}
static unsigned long ktime_get_ns(void)
{
	return 0;
}
#define ktime_to_ns(value) (value)

static size_t copy_from_user(void *to, const void *from, size_t size)
{
	if (++copy_calls == fail_copy)
		return size;
	memcpy(to, from, size);
	return 0;
}
#define copy_to_user(to, from, size) copy_from_user(to, from, size)

/* Source admission is an external boundary in this allocation fixture; the
 * source-lifetime fixture executes its real locking and dependency decisions. */
static bool source_open = true;
static int source_root_error;
static bool kd_source_is_open(void)
{
	return source_open;
}
static int kd_source_pin_root(unsigned long address)
{
	(void)address;
	return source_root_error;
}

/* Match Kbuild's mixed-sign comparison policy only for unmodified production
 * functions; keep strict warnings on this fixture and its assertions. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wsign-compare"
#include "registry_code.h"
#pragma GCC diagnostic pop

static void reset(enum allocation_mode mode)
{
	for (unsigned int i = 0; i < allocation_count; i++)
		CHECK(!allocations[i].live);
	CHECK(kd_exes == NULL && kd_code_block_free == 0);
	for (unsigned int i = 0; i < KD_CODE_BLOCK_POOL; i++)
		CHECK(kd_code_block_pool[i] == NULL);
	allocation_count = block_attempts = exec_attempts = 0;
	errors = warnings = copy_calls = fail_copy = 0;
	allocation_mode = mode;
	source_open = true;
	source_root_error = 0;
}

static unsigned long key(unsigned int i)
{
	/* Same PID/low RIP bits force a real probe chain, not an assumed collision. */
	return 0x81000000UL + ((unsigned long)i << 16) + 0x1234;
}

static void check_init_failures(void)
{
	for (int mode = FAIL_TABLE; mode <= FAIL_EXEC; mode++) {
		reset(mode);
		CHECK(kd_exe_init() == -ENOMEM);
		CHECK(kd_get_exe(0, key(0)) == NULL);
		CHECK(!kd_exe_is_ready(0, key(0)));
		CHECK(kd_exe_get_slot(0) == NULL);
		CHECK(kd_dev_read(NULL, NULL, sizeof(struct kd_exe_info),
				  NULL) == -ENODEV);
	}
}

static void check_pool(enum allocation_mode mode)
{
	struct kd_exe_info snapshot[KD_MAX_EXE], device[KD_MAX_EXE];
	void *blocks[KD_CODE_BLOCK_POOL];
	int available;

	reset(mode);
	CHECK(kd_exe_init() == 0);
	available = kd_code_block_free;
	CHECK(available == (mode == PARTIAL ?
				    (KD_CODE_BLOCK_POOL + 1) / 2 -
					    (KD_CODE_BLOCK_POOL + 1) / 2 / 3 :
				    KD_CODE_BLOCK_POOL));
	memcpy(blocks, kd_code_block_pool, sizeof(blocks));
	CHECK(kd_get_exe(0, key(0))->status_code == KD_EXE_UNUSED);
	CHECK(kd_exe_get_slot(KD_MAX_EXE - 1) == &kd_exes[KD_MAX_EXE - 1]);
	CHECK(kd_exe_get_slot(KD_MAX_EXE) == NULL);
	kd_exe_add(0, key(0), KD_EXE_LOCK_UNKNOWN);
	CHECK(kd_code_block_free == available);
	for (int i = 0; i < available; i++) {
		enum kd_exe_lock_kind kind = i % 2 ? KD_EXE_LOCK_MUTEX :
						     KD_EXE_LOCK_SPIN;
		struct kd_exe_info *exe;

		kd_exe_add(0, key(i), kind);
		exe = kd_get_exe(0, key(i));
		CHECK(exe->status_code == KD_EXE_UNINIT);
		CHECK(exe->pid == 0 && exe->RIP == key(i) &&
		      exe->tgid == current->tgid);
		CHECK(exe->lock_kind == (int)kind &&
		      exe->code_block == blocks[available - i - 1]);
		CHECK(!kd_exe_is_ready(0, key(i)) &&
		      !kd_exe_is_ready(1, key(i)));
		CHECK(kd_code_block_free == available - i - 1);
		kd_exe_add(0, key(i), kind);
		CHECK(kd_code_block_free == available - i - 1);
		CHECK(kd_exe_publish_status(exe, KD_EXE_NORMAL));
		CHECK(kd_exe_is_ready(0, key(i)));
	}
	/* Exhaustion must leave the entire table unchanged, not publish a partial
	 * key that the daemon might later treat as a translation request. */
	memcpy(snapshot, kd_exes, sizeof(snapshot));
	kd_exe_add(0, key(available), KD_EXE_LOCK_MUTEX);
	CHECK(kd_code_block_free == 0 && errors == 1);
	CHECK(memcmp(snapshot, kd_exes, sizeof(snapshot)) == 0);
	CHECK(!kd_exe_is_ready(0, key(available)));
	CHECK(kd_dev_read(NULL, (char *)device, sizeof(device), NULL) ==
	      (ssize_t)(available * sizeof(device[0])));
	for (int i = 0; i < available; i++)
		CHECK(kd_exe_is_ready(0, key(i)));

	/* Backend conflict is terminal, but not code-pool reclamation. */
	kd_exe_add(0, key(0), KD_EXE_LOCK_MUTEX);
	CHECK(warnings == 1 && kd_code_block_free == 0);
	CHECK(kd_get_exe(0, key(0))->status_code == KD_EXE_NATIVE_ONLY);
	CHECK(!kd_exe_is_ready(0, key(0)));
	CHECK(!kd_exe_publish_status(kd_get_exe(0, key(0)), KD_EXE_NORMAL));
	kd_exe_exit();
}

static void check_full_table(void)
{
	struct kd_exe_info snapshot[KD_MAX_EXE];
	int free_blocks;

	reset(NORMAL);
	CHECK(kd_exe_init() == 0);
	/* The default code pool fills first. Seed synthetic occupied metadata only
	 * for this bounded-probe guard; do not label it live table exhaustion. */
	for (int i = 0; i < KD_MAX_EXE; i++) {
		struct kd_exe_info *exe = kd_get_exe(0, key(i));

		exe->pid = 0;
		exe->RIP = key(i);
		exe->status_code = KD_EXE_UNINIT;
	}
	for (int i = 0; i < KD_MAX_EXE; i++)
		CHECK(kd_get_exe(0, key(i))->RIP == key(i));
	CHECK(kd_get_exe(1, key(0)) == NULL);
	CHECK(kd_get_exe(0, key(KD_MAX_EXE)) == NULL);
	free_blocks = kd_code_block_free;
	memcpy(snapshot, kd_exes, sizeof(snapshot));
	kd_exe_add(0, key(KD_MAX_EXE), KD_EXE_LOCK_SPIN);
	CHECK(errors == 1 && kd_code_block_free == free_blocks);
	CHECK(memcmp(snapshot, kd_exes, sizeof(snapshot)) == 0);
	CHECK(!kd_exe_is_ready(0, key(KD_MAX_EXE)));
	kd_exe_exit();
}

static void check_device(void)
{
	struct {
		struct kd_recv_pkt head;
		unsigned char data[16];
	} packet;
	struct kd_exe_info *exe, snapshot;
	const size_t header = sizeof(packet.head);
	char buffer[sizeof(snapshot)];

	reset(NORMAL);
	CHECK(kd_exe_init() == 0);
	source_root_error = -ESTALE;
	kd_exe_add(0, key(0), KD_EXE_LOCK_MUTEX);
	CHECK(kd_get_exe(0, key(0))->status_code == KD_EXE_UNUSED);
	CHECK(kd_code_block_free == KD_CODE_BLOCK_POOL && warnings == 1);
	source_root_error = 0;
	kd_exe_add(0, key(0), KD_EXE_LOCK_MUTEX);
	exe = kd_get_exe(0, key(0));
	packet = (__typeof__(packet)){ .head = { KD_EXE_NORMAL, 0, key(0), 0 },
				       .data = { 0x5a } };
	CHECK(kd_dev_read(NULL, buffer, sizeof(buffer) - 1, NULL) == 0);
	CHECK(kd_dev_read(NULL, buffer, sizeof(buffer), NULL) ==
	      sizeof(buffer));
	memcpy(&snapshot, buffer, sizeof(snapshot));
	CHECK(snapshot.RIP == key(0) && snapshot.status_code == KD_EXE_UNINIT);
	CHECK(kd_dev_write_locked((char *)&packet, header - 1) == -EINVAL);
	packet.head.RIP = key(1);
	CHECK(kd_dev_write_locked((char *)&packet, header + 1) == -ENOENT);
	packet.head.RIP = key(0);
	for (int boundary = 0; boundary < 3; boundary++) {
		packet.head.offset = boundary == 0 ? KD_CODE_BLOCK_SIZE :
				     boundary == 1 ? KD_CODE_BLOCK_SIZE + 1 :
						     ~0UL;
		CHECK(kd_dev_write_locked((char *)&packet, header + 1) ==
		      -EINVAL);
		CHECK(!kd_exe_is_ready(0, key(0)));
	}
	packet.head.offset = 0;
	copy_calls = 0;
	fail_copy = 2;
	CHECK(kd_dev_write_locked((char *)&packet, header + 1) == -EFAULT);
	CHECK(!kd_exe_is_ready(0, key(0)));
	fail_copy = 0;
	packet.head.offset = KD_CODE_BLOCK_SIZE - 1;
	CHECK(kd_dev_write_locked((char *)&packet, header + 1) ==
	      (ssize_t)header + 1);
	CHECK(((unsigned char *)exe->code_block)[KD_CODE_BLOCK_SIZE - 1] ==
	      0x5a);
	CHECK(kd_exe_is_ready(0, key(0)));
	source_open = false;
	CHECK(!kd_exe_is_ready(0, key(0)));
	CHECK(kd_dev_write_locked((char *)&packet, header + 1) == -ESHUTDOWN);
	source_open = true;
	packet.head = (struct kd_recv_pkt){ KD_EXE_NATIVE_ONLY, 0, key(0), 0 };
	CHECK(kd_dev_write_locked((char *)&packet, header) == (ssize_t)header);
	CHECK(!kd_exe_is_ready(0, key(0)));
	packet.head.status_code = KD_EXE_NORMAL;
	CHECK(kd_dev_write_locked((char *)&packet, header + 1) == -EPERM);
	kd_exe_exit();
}

static pthread_barrier_t start;

static void *register_worker(void *arg)
{
	unsigned long id = (unsigned long)arg;

	pthread_barrier_wait(&start);
	for (int i = 0; i < 100; i++)
		kd_exe_add(0, key(id % 6),
			   id % 2 ? KD_EXE_LOCK_MUTEX : KD_EXE_LOCK_SPIN);
	return NULL;
}

static void check_concurrent_registration(void)
{
	pthread_t threads[24];
	int occupied = 0;

	reset(NORMAL);
	CHECK(kd_exe_init() == 0);
	/* Run real gate contention, with all table readers after join. This tests
	 * registration serialization, not Linux IRQ/preemption or lock ownership. */
	if (pthread_barrier_init(&start, NULL, ARRAY_SIZE(threads)))
		abort();
	for (unsigned long i = 0; i < ARRAY_SIZE(threads); i++)
		if (pthread_create(&threads[i], NULL, register_worker,
				   (void *)i))
			abort();
	for (unsigned int i = 0; i < ARRAY_SIZE(threads); i++)
		CHECK(pthread_join(threads[i], NULL) == 0);
	pthread_barrier_destroy(&start);
	for (int i = 0; i < KD_MAX_EXE; i++)
		occupied += kd_exes[i].status_code != KD_EXE_UNUSED;
	CHECK(occupied == 6 && kd_code_block_free == KD_CODE_BLOCK_POOL - 6);
	CHECK(!errors && !warnings);
	for (int i = 0; i < 6; i++) {
		struct kd_exe_info *exe = kd_get_exe(0, key(i));

		CHECK(exe->RIP == key(i) && exe->status_code == KD_EXE_UNINIT);
		CHECK(exe->code_block != NULL && !kd_exe_is_ready(0, key(i)));
	}
	kd_exe_exit();
}

int main(void)
{
	check_init_failures();
	check_pool(NORMAL);
	check_pool(PARTIAL);
	check_full_table();
	check_device();
	check_concurrent_registration();
	reset(NORMAL);
	printf("production exe registry: %d checks, %d failures; pool=%d table=%d\n",
	       checks, failures, KD_CODE_BLOCK_POOL, KD_MAX_EXE);
	return failures != 0;
}
