/* SPDX-License-Identifier: GPL-2.0 */
/* Exercise production registration with bounded memory/copy substitutes.
 * No generated machine code, kernel locks or executable permissions run here.
 */
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <stdint.h>

/* Kernel-private fixed-width names are needed by the actual image header;
 * userspace linux/types.h intentionally exposes only its public names. */
typedef uint8_t u8;
typedef uint32_t u32;
typedef unsigned long long u64;

#include "exe_info.h"
#include "kd_image.h"
#include <assert.h>
#define BUG_ON(x) assert(!(x))
#define local_irq_save(f) ((f)=0)
#define local_irq_restore(f) ((void)(f))
#include "kd_call.h"
#include "kd_hostcall.h"
#include "kd_source_api.h"

#include "../../../include/kd_regs.h"
struct task_struct {
	int tgid, pid;
};
struct file { void *private_data; };
static int kd_publish_lock;
static int kd_mutex_lock_interruptible(int *lock) { assert(!*lock); *lock = 1; return 0; }
static void kd_mutex_local_unlock(int *lock) { assert(*lock); *lock = 0; }
#ifndef ERESTARTSYS
#define ERESTARTSYS 512
#endif
typedef struct {
	int counter;
} atomic_t;
typedef long long atomic64_t;
typedef long long s64;
#define S64_MAX LLONG_MAX
#define module_param_named(...)
#define MODULE_PARM_DESC(...)
struct kernel_param;
struct kernel_param_ops { int (*get)(char *, const struct kernel_param *); };
#define module_param_cb(name, ops, ...) \
 static const void *name##_parameter __attribute__((unused)) = (ops)
#define scnprintf snprintf
#define likely(x) (x)
#define unlikely(x) (x)

/* Type-check the production capacity diagnostic's real caller identity too. */
static struct task_struct task = { .tgid = 42, .pid = 43 };
static struct task_struct *current = &task;
static int checks, failures, errors, warnings, timing_rows;
static int gate_attempts, source_pin_calls;
static int service_pin_calls, service_pin_error;
static struct kd_exe_info *service_pin_entry;

/* Publish between lookup's UNUSED observation and the registration check's
 * acquire reload. This deterministic interleaving tests full-key validation;
 * it does not replace the separate real pthread registration contention. */
static struct kd_exe_info *publish_after_lookup;
static struct kd_exe_info pending_publication;

static int load_acquire_int(const int *pointer)
{
	int value = __atomic_load_n(pointer, __ATOMIC_ACQUIRE);
	struct kd_exe_info *slot = publish_after_lookup;

	if (slot && pointer == &slot->status_code && value == KD_EXE_UNUSED) {
		publish_after_lookup = NULL;
		slot->pid = pending_publication.pid;
		slot->RIP = pending_publication.RIP;
		slot->lock_kind = pending_publication.lock_kind;
		slot->code_block = pending_publication.code_block;
		__atomic_store_n(&slot->status_code, KD_EXE_UNINIT,
				 __ATOMIC_RELEASE);
	}
	return value;
}

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
static unsigned int get_unaligned_le32(const void *source)
{
	unsigned int value;
	memcpy(&value, source, sizeof(value));
	return value;
}
#define ATOMIC_INIT(value) { value }
#define READ_ONCE(x) __atomic_load_n(&(x), __ATOMIC_RELAXED)
#define smp_load_acquire(p) _Generic((p), int*:load_acquire_int((const int*)(p)), const int*:load_acquire_int((const int*)(p)), default:__atomic_load_n(p,__ATOMIC_ACQUIRE))
#define smp_store_release(p, v) __atomic_store_n(p, v, __ATOMIC_RELEASE)
#define atomic_set(p, v) __atomic_store_n(&(p)->counter, v, __ATOMIC_RELAXED)
#define atomic_read(p) __atomic_load_n(&(p)->counter, __ATOMIC_RELAXED)
#define atomic_set_release(p, v) smp_store_release(&(p)->counter, v)
#define atomic64_set(p, v) (*(p) = (v))
#define atomic64_read(p) (*(p))
#define try_cmpxchg(p, old, v)                                          \
	__atomic_compare_exchange_n(p, old, v, false, __ATOMIC_SEQ_CST, \
				    __ATOMIC_SEQ_CST)
#define atomic64_try_cmpxchg(p, old, v) try_cmpxchg(p, old, v)
#define cpu_relax() __asm__ volatile("pause" ::: "memory")
#define __user
#define KD_PR_INFO(format, ...)              \
	do {                                 \
		if (strstr(format, "kd_jit timing:")) \
			timing_rows++;              \
		if (0)                       \
			printf(format, ##__VA_ARGS__); \
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
	__atomic_add_fetch(&gate_attempts, 1, __ATOMIC_RELAXED);
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

static void kd_mutex_local_lock(void) {}

static unsigned long kallsyms_lookup_name(const char *name)
{
	return (unsigned long)name;
}

/* Registry init now links its direct API identities; this fixture never
 * executes a lock, only verifies allocation/publication/retirement. */
static void kd_spin_lock_legacy(void) { CHECK(!"unexpected lock call"); }
static void kd_spin_unlock_legacy(void) { CHECK(!"unexpected unlock call"); }
static void kd_spin_lock_clobber_v1(void) { CHECK(!"unexpected lock call"); }
static void kd_spin_lock_pinned_clobber_v1(void) { CHECK(!"unexpected lock call"); }
static void kd_spin_direct_native_unlock(void) { CHECK(!"unexpected unlock call"); }
static void kd_rwlock_fast_write_unlock(void) { CHECK(!"unexpected rwlock fast unlock"); }
static void kd_spin_unlock_clobber_v1(void) { CHECK(!"unexpected unlock call"); }
static void kd_mutex_direct_lock_clobber_v1(void) { CHECK(!"unexpected mutex lock call"); }
static void kd_mutex_direct_contended_clobber_v1(void) { CHECK(!"unexpected contended mutex lock call"); }
static void kd_mutex_outer_contended_clobber_v1(void) { CHECK(!"unexpected outer mutex lock call"); }
static void kd_mutex_direct_unlock_clobber_v1(void) { CHECK(!"unexpected mutex unlock call"); }


static unsigned long ktime_get(void)
{
	return 0;
}
static unsigned long ktime_get_ns(void)
{
	return 0;
}
/* Registration resolves the real manifest but does not execute services. Keep
 * the scalar primitive/argument shape present so that table drift compiles. */
static unsigned long int_sqrt(unsigned long argument)
{
	(void)argument;
	CHECK(!"registration unexpectedly invoked a service");
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
#define copy_from_kernel_nofault(to, from, size) copy_from_user(to, from, size)

/* Source admission is an external boundary in this allocation fixture; the
 * source-lifetime fixture executes its real locking and dependency decisions. */
static bool source_open = true;
static int source_root_error;
static bool kd_source_is_open(void)
{
	return READ_ONCE(source_open);
}
static int kd_source_pin_root(unsigned long address)
{
	(void)address;
	__atomic_add_fetch(&source_pin_calls, 1, __ATOMIC_RELAXED);
	return kd_source_is_open() ? source_root_error : -ESHUTDOWN;
}

/* Exact helper-source pinning is covered by the service registry fixture.
 * Here its result must still gate actual immutable image publication. */
static int kd_service_calls_pin(void)
{
	service_pin_calls++;
	if (service_pin_entry) {
		CHECK(service_pin_entry->status_code == KD_EXE_UNINIT);
		CHECK(service_pin_entry->generation == 0);
		CHECK(kd_image_current(service_pin_entry) == NULL);
	}
	return service_pin_error;
}

/* This registry fixture supplies no GS-memory image. The dedicated memory
 * fixture executes the real descriptor validation; accidental scope growth
 * here must fail rather than manufacture a successful memory validation. */
int kd_image_validate_memory_sites(const struct kd_jit_image *image)
{
	CHECK(!(image->requirements & KD_IMAGE_REQUIRE_ORIGIN_MEMORY));
	return image->requirements & KD_IMAGE_REQUIRE_ORIGIN_MEMORY ? -EPROTO : 0;
}

/* Match Kbuild's mixed-sign comparison policy only for unmodified production
 * functions; keep strict warnings on this fixture and its assertions. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wsign-compare"
struct kd_mutex { int unused; };
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
	gate_attempts = source_pin_calls = 0;
	service_pin_calls = service_pin_error = 0;
	service_pin_entry = NULL;
	publish_after_lookup = NULL;
	allocation_mode = mode;
	source_open = true;
	source_root_error = 0;
	kd_jit_timing = mode == PARTIAL;
	timing_rows = 0;
	/* Reinitialization must discard previous session measurements, including
	 * error markers, even if allocation fails before a code pool is usable. */
	for (int i = 0; i < KD_JIT_TIME_COUNT; i++) {
		kd_jit_times[i].samples = kd_jit_times[i].ns = 17;
		atomic_set(&kd_jit_times[i].invalid, 1);
	}
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
	for (int i = 0; i < KD_JIT_TIME_COUNT; i++) {
		CHECK(!kd_jit_times[i].samples && !kd_jit_times[i].ns);
		CHECK(!atomic_read(&kd_jit_times[i].invalid));
	}
	CHECK(!timing_rows);
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
		enum kd_exe_lock_kind kind = KD_EXE_LOCK_SPIN;
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
	kd_exe_add(0, key(available), KD_EXE_LOCK_SPIN);
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
	CHECK(timing_rows == (mode == PARTIAL ? KD_JIT_TIME_COUNT : 0));
}

/* Preparation registers a root before immutable publication has a code block.
 * Use the real registry and prepare helper, not a handwritten successful stub. */
static void check_mutex_preparation(void)
{
	struct kd_mutex lock = {0};
	struct kd_exe_info *exe;
	int blocks, pins;

	reset(NORMAL);
	CHECK(kd_exe_init() == 0);
	blocks = kd_code_block_free;
	CHECK(kd_mutex_prepare(NULL, key(0), 2) == -EINVAL);
	CHECK(kd_mutex_prepare(&lock, 0, 2) == -EINVAL);
	CHECK(kd_mutex_prepare(&lock, key(0), 1) == -EINVAL);
	CHECK(kd_mutex_prepare(&lock, key(0), 2) == 0);
	exe = kd_get_exe(0, key(0));
	CHECK(exe->status_code == KD_EXE_UNINIT && !exe->code_block);
	CHECK(!kd_exe_is_ready(0, key(0)) && !kd_image_current(exe));
	CHECK(kd_code_block_free == blocks);
	pins = source_pin_calls;
	CHECK(kd_mutex_prepare(&lock, key(0), 2) == 0);
	CHECK(source_pin_calls == pins && kd_code_block_free == blocks);
	CHECK(kd_exe_publish_status(exe, KD_EXE_NATIVE_ONLY));
	CHECK(kd_mutex_prepare(&lock, key(0), 2) == -EOPNOTSUPP);
	source_root_error = -ENOENT;
	CHECK(kd_mutex_prepare(&lock, key(1), 2) == -EINVAL);
	source_open = false;
	CHECK(kd_mutex_prepare(&lock, key(0), 2) == -ESHUTDOWN);
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

static struct kd_image_upload upload;

static void check_device(void)
{
	struct {
		struct kd_recv_pkt head;
		unsigned char data[64];
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
	packet = (__typeof__(packet)){ .head = { .status_code=KD_EXE_UNINIT, .RIP=key(0), .version=KD_IMAGE_PROTOCOL, .image_length=64, .upload_id=1 },
				       .data = { 0x5a } };
	CHECK(kd_dev_read(NULL, buffer, sizeof(buffer) - 1, NULL) == 0);
	CHECK(kd_dev_read(NULL, buffer, sizeof(buffer), NULL) ==
	      sizeof(buffer));
	memcpy(&snapshot, buffer, sizeof(snapshot));
	CHECK(snapshot.RIP == key(0) && snapshot.status_code == KD_EXE_UNINIT);
	CHECK(kd_dev_write_locked(&upload, (char *)&packet, header - 1) == -EINVAL);
	packet.head.RIP = key(1);
	CHECK(kd_dev_write_locked(&upload, (char *)&packet, header + 1) == -ENOENT);
	packet.head.RIP = key(0);
	for (int boundary = 0; boundary < 3; boundary++) {
		packet.head.offset = boundary == 0 ? KD_CODE_BLOCK_SIZE :
				     boundary == 1 ? KD_CODE_BLOCK_SIZE + 1 :
						     ~0UL;
		CHECK(kd_dev_write_locked(&upload, (char *)&packet, header + 1) ==
		      -EINVAL);
		CHECK(!kd_exe_is_ready(0, key(0)));
	}
	packet.head.offset = 0;
	packet.head.image_length=KD_CODE_BLOCK_SIZE+1;
	CHECK(kd_dev_write_locked(&upload,(char *)&packet,header+1)==-EINVAL);
	packet.head.image_length=64;
	copy_calls = 0;
	fail_copy = 2;
	CHECK(kd_dev_write_locked(&upload, (char *)&packet, header + 1) == -EFAULT);
	CHECK(!kd_exe_is_ready(0, key(0)));
	fail_copy = 0;
	memcpy(packet.data+9,"KDWB002",7);
	memcpy(packet.data+25,"KDWC002",7);
	memcpy(packet.data+41,"KDAB",4);
	packet.data[45]=0;packet.data[46]=KD_IMAGE_PROTOCOL;packet.data[47]=0;
	packet.head.status_code=KD_EXE_NORMAL;
	CHECK(kd_dev_write_locked(&upload,(char *)&packet,header+64)==(ssize_t)header+64);
	CHECK(!memcmp(exe->code_block,packet.data,64));
	CHECK(kd_exe_is_ready(0, key(0)));
	source_open = false;
	CHECK(!kd_exe_is_ready(0, key(0)));
	CHECK(kd_dev_write_locked(&upload, (char *)&packet, header + 1) == -ESHUTDOWN);
	source_open = true;
	packet.head = (struct kd_recv_pkt){ .status_code=KD_EXE_NATIVE_ONLY, .RIP=key(0), .version=KD_IMAGE_PROTOCOL, .base_generation=exe->generation };
	CHECK(kd_dev_write_locked(&upload, (char *)&packet, header) == (ssize_t)header);
	CHECK(!kd_exe_is_ready(0, key(0)));
	packet.head.status_code = KD_EXE_NORMAL;packet.head.image_length=48;packet.head.upload_id=2;
	CHECK(kd_dev_write_locked(&upload, (char *)&packet, header + 48) == -EPERM);
	kd_exe_exit();
}

/* Never publish old pt_regs-layout images, even through the ordinary FULL
 * bridge. Staging chunks is allowed; only the complete matching directory
 * grants NORMAL, and a rejected entry stays terminal. */
static void check_packet_directory(void)
{
    struct { struct kd_recv_pkt head; unsigned char data[48]; } packet;
    for (unsigned int abi = 0; abi <= 2; abi++) {
        for (unsigned int fault = 0; fault < 5; fault++) {
            reset(NORMAL);
            CHECK(kd_exe_init() == 0);
            kd_exe_add_abi(0, key(0), abi == 1 ? KD_EXE_LOCK_SPIN : KD_EXE_LOCK_MUTEX, abi);
            packet = (__typeof__(packet)){ .head = { .status_code=KD_EXE_UNINIT,.RIP=key(0),.version=KD_IMAGE_PROTOCOL,.entry_abi=abi,.image_length=48,.upload_id=1 } };
            memcpy(packet.data + 9, "KDWB002", 7);
            memcpy(packet.data + 25, "KDWC002", 7);
            memcpy(packet.data + 41, "KDAB", 4);
            packet.data[45] = abi;packet.data[46]=KD_IMAGE_PROTOCOL;
            if (fault == 1) packet.data[15] = '1';
            if (fault == 2) packet.data[31] = '1';
            if (fault == 3) memset(packet.data, 0, sizeof(packet.data));
            if (fault == 4) packet.data[45] = (abi + 1) % 3;
            size_t bytes = sizeof(packet.head) + sizeof(packet.data);
            CHECK(kd_dev_write_locked(&upload, (char *)&packet, bytes) == -EINVAL);
            CHECK(!kd_exe_is_ready(0, key(0)));
            packet.head.status_code = KD_EXE_NORMAL;
            CHECK(kd_dev_write_locked(&upload, (char *)&packet, bytes) ==
                  (fault ? -EPROTO : (ssize_t)bytes));
            CHECK(kd_exe_is_ready(0, key(0)) == !fault);
            if (fault) CHECK(kd_dev_write_locked(&upload, (char *)&packet, bytes) == -EPROTO);
            kd_image_discard(upload.image); upload.image = NULL;
            kd_exe_exit();
        }
    }
}

static void check_service_source_publication(void)
{
	struct {
		struct kd_recv_pkt head;
		unsigned char data[KD_IMAGE_SERVICE_HEADER_SIZE];
	} packet = {0};
	struct kd_exe_info *entry;
	unsigned int requirements = KD_IMAGE_REQUIRE_SERVICE_QUEUE |
		KD_IMAGE_REQUIRE_ORIGIN_CALL | KD_IMAGE_REQUIRE_BUDGET_RESUME |
		KD_IMAGE_REQUIRE_RETAINED_MISS;
	size_t bytes = sizeof(packet.head) + sizeof(packet.data);
	int blocks;

	reset(NORMAL);
	CHECK(kd_exe_init() == 0);
	kd_exe_add_abi(0, key(0), KD_EXE_LOCK_MUTEX, KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
	entry = kd_get_exe(0, key(0));
	service_pin_entry = entry;
	packet.head = (struct kd_recv_pkt){
		.status_code = KD_EXE_NORMAL, .RIP = key(0),
		.version = KD_IMAGE_PROTOCOL_SERVICE_QUEUE,
		.entry_abi = KD_ENTRY_ABI_MUTEX_CLOBBER_V1,
		.requirements = requirements, .image_length = sizeof(packet.data),
		.upload_id = 1,
	};
	memcpy(packet.data + 9, "KDWB002", 7);
	memcpy(packet.data + 25, "KDWC002", 7);
	memcpy(packet.data + 41, "KDAB", 4);
	packet.data[45] = KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
	packet.data[46] = KD_IMAGE_PROTOCOL_SERVICE_QUEUE;
	packet.data[47] = requirements & 0xffU;
	memcpy(packet.data + KD_IMAGE_FULL_REQUIREMENTS_OFFSET,
	       &requirements, sizeof(requirements));
	blocks = kd_code_block_free;
	service_pin_error = -ESTALE;
	CHECK(kd_dev_write_locked(&upload, (char *)&packet, bytes) == -ESTALE);
	CHECK(service_pin_calls == 1 && !kd_exe_is_ready(0, key(0)));
	CHECK(entry->status_code == KD_EXE_UNINIT && entry->generation == 0);
	CHECK(entry->code_block == NULL && kd_image_current(entry) == NULL);
	CHECK(upload.image && !upload.image->entry && upload.covered == sizeof(packet.data));
	CHECK(kd_code_block_free == blocks - 1);
	service_pin_error = 0;
	CHECK(kd_dev_write_locked(&upload, (char *)&packet, bytes) == (ssize_t)bytes);
	CHECK(service_pin_calls == 2 && kd_exe_is_ready(0, key(0)));
	CHECK(entry->generation == 1 && entry->requirements == requirements);
	CHECK(kd_image_current(entry)->entry == entry && upload.image == NULL);
	CHECK(kd_code_block_free == blocks - 1);
	/* Same-generation repeated reads cannot change the compilation receipt.
	 * Publication consumes only the frozen revision; later reports survive. */
	service_pin_entry = NULL;
	const struct kd_jit_image *old = kd_image_current(entry);
	struct file channel = { .private_data = &upload };
	struct kd_exe_info snapshots[KD_MAX_EXE];
	unsigned int slot = kd_exe_slot_index(entry);
	unsigned char original[sizeof(packet.data)];
	memcpy(original, packet.data, sizeof(original));
	kd_image_report(entry, old, KD_EXE_CALL_MISS, 0x2222, 0);
	CHECK(kd_dev_read(&channel, (char *)snapshots, sizeof(snapshots), NULL) > 0);
	unsigned long revision = upload.observed[slot].revision;
	kd_image_report(entry, old, KD_EXE_CALL_MISS, 0x2222, 0);
	CHECK(kd_image_learning[slot].revision == revision);
	packet.head.base_generation = 1; packet.head.upload_id = 2;
	packet.head.status_code = KD_EXE_UNINIT;
	CHECK(kd_dev_write_locked(&upload, (char *)&packet, sizeof(packet.head) + 32) > 0);
	kd_image_report(entry, old, KD_EXE_IJ_MISS, 0x3333, 0x4444);
	CHECK(kd_dev_read(&channel, (char *)snapshots, sizeof(snapshots), NULL) > 0);
	CHECK(upload.observed[slot].revision == revision && upload.acknowledgment.revision == revision);
	packet.head.offset = 32; packet.head.status_code = KD_EXE_NORMAL;
	memcpy(packet.data, original + 32, sizeof(original) - 32);
	CHECK(kd_dev_write_locked(&upload, (char *)&packet, bytes - 32) > 0);
	CHECK(entry->generation == 2 && entry->status_code == KD_EXE_IJ_MISS && entry->tgt_addr == 0x3333);
	kd_image_report(entry, old, KD_EXE_CALL_MISS, 0x5555, 0);
	CHECK(entry->tgt_addr == 0x3333);
	CHECK(kd_dev_read(&channel, (char *)snapshots, sizeof(snapshots), NULL) > 0);
	packet.head.offset = 0; packet.head.base_generation = 2; packet.head.upload_id = 3;
	memcpy(packet.data, original, sizeof(original));
	CHECK(kd_dev_write_locked(&upload, (char *)&packet, bytes) > 0);
	CHECK(entry->generation == 3 && entry->status_code == KD_EXE_NORMAL);
	/* A no-report read cannot acknowledge a subsequently reached frontier. */
	CHECK(kd_dev_read(&channel, (char *)snapshots, sizeof(snapshots), NULL) > 0);
	kd_image_report(entry, kd_image_current(entry), KD_EXE_CALL_MISS, 0x6666, 0);
	CHECK(kd_dev_read(&channel, (char *)snapshots, sizeof(snapshots), NULL) > 0);
	packet.head.base_generation = 3; packet.head.upload_id = 4;
	CHECK(kd_dev_write_locked(&upload, (char *)&packet, bytes) > 0);
	CHECK(entry->generation == 4 && entry->status_code == KD_EXE_CALL_MISS && entry->tgt_addr == 0x6666);
	/* A failed whole read may not retain its newly copied first-row receipt. */
	kd_exe_add_abi(0, key(1), KD_EXE_LOCK_MUTEX, KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
	memset(upload.observed, 0, sizeof(upload.observed));
	fail_copy = copy_calls + 2;
	CHECK(kd_dev_read(&channel, (char *)snapshots, sizeof(snapshots), NULL) == -EFAULT);
	for (unsigned int i = 0; i < KD_MAX_EXE; ++i) CHECK(!upload.observed[i].valid);
	fail_copy = 0;
	CHECK(kd_dev_read(&channel, (char *)snapshots, sizeof(snapshots), NULL) > 0);
	CHECK(upload.observed[slot].generation == 4);
	CHECK(upload.observed[kd_exe_slot_index(kd_get_exe(0, key(1)))].generation == 0);
	kd_exe_exit();
}

/* These tests exercise publication metadata, not generated-code execution. */
static struct kd_jit_image *learning_test_image(unsigned int requirements)
{
	struct kd_jit_image *image = kd_image_alloc();

	CHECK(image != NULL);
	if (!image)
		abort();
	image->length = KD_IMAGE_SERVICE_HEADER_SIZE;
	image->requirements = requirements;
	image->entry_abi = KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
	return image;
}

static void check_learning_batches(void)
{
	const unsigned int requirements = KD_IMAGE_REQUIRE_SERVICE_QUEUE |
		KD_IMAGE_REQUIRE_ORIGIN_CALL | KD_IMAGE_REQUIRE_BUDGET_RESUME |
		KD_IMAGE_REQUIRE_RETAINED_MISS;
	const unsigned long call_a = 0x2222, call_b = 0x3333, call_c = 0x7777;
	struct kd_learning_record records[KD_LEARNING_CAPACITY], frozen[KD_LEARNING_CAPACITY];
	struct kd_image_learning_receipt batch, legacy, next;
	struct kd_image_learning_state saved, *learning;
	struct kd_exe_info *entry, snapshot, before;
	struct kd_jit_image *replacement, *incompatible;
	const struct kd_jit_image *old, *current_image;
	unsigned long long overflow;
	unsigned int count;

	reset(NORMAL);
	CHECK(kd_exe_init() == 0);
	kd_exe_add_abi(0, key(0), KD_EXE_LOCK_MUTEX, KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
	entry = kd_get_exe(0, key(0));
	learning = &kd_image_learning[kd_exe_slot_index(entry)];
	replacement = learning_test_image(requirements);
	CHECK(kd_image_publish_learned(entry, replacement, 0, NULL) == 0);
	old = kd_image_current(entry);
	CHECK(entry->generation == 1 && entry->status_code == KD_EXE_NORMAL);

	/* Kind and indirect source are both part of distinct-miss identity. All
	 * four rows coexist; repeated pending CALL/IJ reports consume no slot. */
	kd_image_report(entry, old, KD_EXE_CALL_MISS, call_a, 0);
	kd_image_report(entry, old, KD_EXE_CALL_MISS, call_b, 0);
	kd_image_report(entry, old, KD_EXE_IJ_MISS, call_a, 0x4444);
	kd_image_report(entry, old, KD_EXE_IJ_MISS, call_a, 0x5555);
	CHECK(learning->count == 4 && learning->revision == 4);
	for (unsigned int i = 0; i < KD_LEARNING_CAPACITY; ++i) {
		kd_image_report(entry, old, KD_EXE_CALL_MISS, call_a, 0);
		kd_image_report(entry, old, KD_EXE_IJ_MISS, call_a, 0x4444);
	}
	kd_exe_snapshot_misses(entry, &snapshot, records, &count, &overflow, &batch);
	CHECK(count == 4 && !overflow && batch.valid && batch.batch);
	CHECK(batch.generation == 1 && batch.revision == 4);
	CHECK(snapshot.generation == 1 && snapshot.status_code == KD_EXE_IJ_MISS);
	for (unsigned int i = 0; i < count; ++i) {
		CHECK(records[i].sequence == i + 1 && records[i].admitted_generation == 1);
		CHECK(!records[i].reserved);
	}
	CHECK(records[0].kind == KD_EXE_CALL_MISS && records[0].target == call_a && !records[0].from);
	CHECK(records[1].kind == KD_EXE_CALL_MISS && records[1].target == call_b && !records[1].from);
	CHECK(records[2].kind == KD_EXE_IJ_MISS && records[2].target == call_a && records[2].from == 0x4444);
	CHECK(records[3].kind == KD_EXE_IJ_MISS && records[3].target == call_a && records[3].from == 0x5555);
	memcpy(frozen, records, count * sizeof(records[0]));

	/* A fifth row arrives after the frozen view. Neither stale/source-closed
	 * publication nor an incompatible replacement may consume any obligation. */
	kd_image_report(entry, old, KD_EXE_CALL_MISS, call_c, 0);
	CHECK(learning->count == 5 && learning->revision == 5);
	CHECK(!memcmp(frozen, records, 4 * sizeof(records[0])));
	saved = *learning;
	before = *entry;
	replacement = learning_test_image(requirements);
	CHECK(kd_image_publish_learned(entry, replacement, 0, &batch) == -ESTALE);
	CHECK(kd_image_current(entry) == old && !replacement->entry);
	CHECK(!memcmp(&saved, learning, sizeof(saved)) && !memcmp(&before, entry, sizeof(before)));
	source_open = false;
	CHECK(kd_image_publish_learned(entry, replacement, 1, &batch) == -ESHUTDOWN);
	CHECK(kd_image_current(entry) == old && !replacement->entry);
	CHECK(!memcmp(&saved, learning, sizeof(saved)) && !memcmp(&before, entry, sizeof(before)));
	source_open = true;
	incompatible = learning_test_image(requirements & ~KD_IMAGE_REQUIRE_RETAINED_MISS);
	CHECK(kd_image_publish_learned(entry, incompatible, 1, &batch) == -EPROTO);
	CHECK(kd_image_current(entry) == old && !incompatible->entry);
	CHECK(!memcmp(&saved, learning, sizeof(saved)) && !memcmp(&before, entry, sizeof(before)));
	kd_image_discard(incompatible);

	CHECK(kd_image_publish_learned(entry, replacement, 1, &batch) == 0);
	current_image = kd_image_current(entry);
	CHECK(current_image == replacement && entry->generation == 2);
	CHECK(entry->status_code == KD_EXE_CALL_MISS && entry->tgt_addr == call_c);
	CHECK(learning->count == 1 && learning->revision == 5);
	kd_exe_snapshot_misses(entry, &snapshot, records, &count, &overflow, &next);
	CHECK(count == 1 && records[0].sequence == 5 && records[0].target == call_c);
	CHECK(records[0].admitted_generation == 1 && next.generation == 2);
	CHECK(old->entry == entry && old->generation == 1 && old->code);
	saved = *learning;
	kd_image_report(entry, old, KD_EXE_CALL_MISS, 0x8888, 0);
	CHECK(!memcmp(&saved, learning, sizeof(saved)) && entry->tgt_addr == call_c);

	/* Reuse occurs only after ACK. The same CALL key from the new image is a
	 * new obligation, while the carried C row retains its original generation. */
	kd_image_report(entry, current_image, KD_EXE_CALL_MISS, call_a, 0);
	kd_image_report(entry, current_image, KD_EXE_CALL_MISS, call_c, 0);
	CHECK(learning->count == 2 && learning->revision == 6);
	CHECK(learning->records[0].sequence == 6 && learning->records[0].admitted_generation == 2);
	kd_exe_snapshot_misses(entry, &snapshot, records, &count, &overflow, &next);
	CHECK(count == 2 && records[0].sequence == 5 && records[1].sequence == 6);
	CHECK(records[0].target == call_c && records[0].admitted_generation == 1);
	CHECK(records[1].target == call_a && records[1].admitted_generation == 2);

	/* A legacy read observes A only. Its watermark must not acknowledge an
	 * older unseen C row or a B row admitted after that read. */
	kd_exe_snapshot_learning(entry, &snapshot, &legacy);
	CHECK(legacy.valid && !legacy.batch && legacy.kind == KD_EXE_CALL_MISS);
	CHECK(legacy.target == call_a && legacy.revision == 6 && legacy.generation == 2);
	kd_image_report(entry, current_image, KD_EXE_CALL_MISS, call_b, 0);
	replacement = learning_test_image(requirements);
	CHECK(kd_image_publish_learned(entry, replacement, 2, &legacy) == 0);
	CHECK(entry->generation == 3 && learning->count == 2 && learning->revision == 7);
	kd_exe_snapshot_misses(entry, &snapshot, records, &count, &overflow, &batch);
	CHECK(count == 2 && records[0].sequence == 5 && records[1].sequence == 7);
	CHECK(records[0].target == call_c && records[1].target == call_b);
	CHECK(entry->status_code == KD_EXE_CALL_MISS && entry->tgt_addr == call_b);
	kd_image_report(entry, replacement, KD_EXE_CALL_MISS, call_a, 0);
	CHECK(learning->count == 3 && learning->revision == 8);
	replacement = learning_test_image(requirements);
	CHECK(kd_image_publish_learned(entry, replacement, 3, &batch) == 0);
	kd_exe_snapshot_misses(entry, &snapshot, records, &count, &overflow, &batch);
	CHECK(count == 1 && records[0].target == call_a && records[0].sequence == 8);
	CHECK(records[0].admitted_generation == 3 && entry->generation == 4);
	replacement = learning_test_image(requirements);
	CHECK(kd_image_publish_learned(entry, replacement, 4, &batch) == 0);
	CHECK(!learning->count && learning->revision == 8 && entry->generation == 5);
	CHECK(entry->status_code == KD_EXE_NORMAL && !entry->tgt_addr && !entry->jump_from);
	kd_exe_exit();

	/* Filling all 32 rows never evicts one. Rejections count events, including
	 * repeated rejected keys; duplicates already pending remain free of charge. */
	reset(NORMAL);
	CHECK(kd_exe_init() == 0);
	kd_exe_add_abi(0, key(0), KD_EXE_LOCK_MUTEX, KD_ENTRY_ABI_MUTEX_CLOBBER_V1);
	entry = kd_get_exe(0, key(0));
	learning = &kd_image_learning[kd_exe_slot_index(entry)];
	replacement = learning_test_image(requirements);
	CHECK(kd_image_publish_learned(entry, replacement, 0, NULL) == 0);
	old = replacement;
	for (unsigned int i = 0; i < KD_LEARNING_CAPACITY; ++i)
		kd_image_report(entry, old, KD_EXE_CALL_MISS, 0x10000 + i * 16, 0);
	kd_exe_snapshot_misses(entry, &snapshot, records, &count, &overflow, &batch);
	CHECK(count == KD_LEARNING_CAPACITY && batch.revision == KD_LEARNING_CAPACITY && !overflow);
	memcpy(frozen, records, sizeof(frozen));
	for (unsigned int i = 0; i < KD_LEARNING_CAPACITY; ++i)
		kd_image_report(entry, old, KD_EXE_CALL_MISS, 0x10000 + i * 16, 0);
	CHECK(!learning->overflow_report_events);
	kd_image_report(entry, old, KD_EXE_CALL_MISS, 0x90000, 0);
	kd_image_report(entry, old, KD_EXE_CALL_MISS, 0x90000, 0);
	CHECK(learning->count == KD_LEARNING_CAPACITY && learning->revision == KD_LEARNING_CAPACITY);
	CHECK(learning->overflow_report_events == 2);
	kd_exe_snapshot_misses(entry, &snapshot, records, &count, &overflow, &next);
	CHECK(overflow == 2 && count == KD_LEARNING_CAPACITY && !memcmp(records, frozen, sizeof(frozen)));
	CHECK(entry->tgt_addr == 0x10000 + (KD_LEARNING_CAPACITY - 1) * 16);
	learning->overflow_report_events = ~0ULL - 1;
	kd_image_report(entry, old, KD_EXE_IJ_MISS, 0x90000, 0xa0000);
	kd_image_report(entry, old, KD_EXE_IJ_MISS, 0x90000, 0xa0000);
	CHECK(learning->overflow_report_events == ~0ULL && learning->count == KD_LEARNING_CAPACITY);
	CHECK(!memcmp(learning->records, frozen, sizeof(frozen)));

	replacement = learning_test_image(requirements);
	CHECK(kd_image_publish_learned(entry, replacement, 1, &batch) == 0);
	CHECK(!learning->count && entry->status_code == KD_EXE_NORMAL);
	CHECK(learning->overflow_report_events == ~0ULL && learning->revision == KD_LEARNING_CAPACITY);
	kd_image_report(entry, replacement, KD_EXE_CALL_MISS, 0x90000, 0);
	CHECK(learning->count == 1 && learning->revision == KD_LEARNING_CAPACITY + 1);
	CHECK(learning->records[0].sequence == KD_LEARNING_CAPACITY + 1);
	CHECK(learning->records[0].admitted_generation == 2 && learning->records[0].target == 0x90000);
	CHECK(learning->overflow_report_events == ~0ULL && old->entry == entry && old->generation == 1);
	kd_exe_snapshot_misses(entry, &snapshot, records, &count, &overflow, &batch);
	saved = *learning;
	current_image = kd_image_current(entry);
	kd_image_disable(entry);
	replacement = learning_test_image(requirements);
	CHECK(kd_image_publish_learned(entry, replacement, 2, &batch) == -ESHUTDOWN);
	CHECK(kd_image_current(entry) == current_image && !replacement->entry);
	CHECK(!memcmp(&saved, learning, sizeof(saved)) && entry->status_code == KD_EXE_NATIVE_ONLY);
	kd_image_discard(replacement);
	kd_exe_exit();
}

static void check_registration_reads(void)
{
	const int states[] = { KD_EXE_UNINIT, KD_EXE_NORMAL, KD_EXE_CALL_MISS,
		KD_EXE_IJ_MISS, KD_EXE_ERROR_INST, KD_EXE_INST_LIMIT,
		KD_EXE_NATIVE_ONLY };
	struct kd_exe_info *exe, snapshot;
	int gate_before, pins_before, free_before;

	reset(NORMAL);
	CHECK(kd_exe_init() == 0);
	for (int backend = KD_EXE_LOCK_SPIN; backend <= KD_EXE_LOCK_MUTEX;
	     backend++) {
		gate_before = gate_attempts;
		pins_before = source_pin_calls;
		kd_exe_add(0, key(backend), backend);
		exe = kd_get_exe(0, key(backend));
		CHECK(gate_attempts == gate_before + 1);
		CHECK(source_pin_calls == pins_before + 1);
		if (backend == KD_EXE_LOCK_MUTEX) {
			struct kd_jit_image *image;
			CHECK(!exe->code_block && !kd_image_current(exe));
			image = kd_image_alloc();
			CHECK(image != NULL);
			image->length = KD_IMAGE_HEADER_SIZE;
			image->requirements = 0;
			image->entry_abi = 0;
			CHECK(kd_image_publish(exe, image, 0) == 0);
		}
		free_before = kd_code_block_free;
		gate_before = gate_attempts;
		pins_before = source_pin_calls;
		for (unsigned int i = 0; i < ARRAY_SIZE(states); i++) {
			CHECK(kd_exe_publish_status(exe, states[i]));
			snapshot = *exe;
			for (int repeat = 0; repeat < 100; repeat++)
				kd_exe_add(0, key(backend), backend);
			CHECK(gate_attempts == gate_before);
			CHECK(source_pin_calls == pins_before);
			CHECK(kd_code_block_free == free_before);
			CHECK(memcmp(&snapshot, exe, sizeof(snapshot)) == 0);
			CHECK(kd_exe_is_ready(0, key(backend)) ==
			      (states[i] == KD_EXE_NORMAL));
		}
	}

	/* An incompatible backend must retain the old terminal conflict path,
	 * including when there are still free code blocks available. */
	kd_exe_add(0, key(3), KD_EXE_LOCK_SPIN);
	exe = kd_get_exe(0, key(3));
	CHECK(kd_exe_publish_status(exe, KD_EXE_NORMAL));
	gate_before = gate_attempts;
	pins_before = source_pin_calls;
	free_before = kd_code_block_free;
	kd_exe_add(0, key(3), KD_EXE_LOCK_MUTEX);
	CHECK(gate_attempts == gate_before + 1 && source_pin_calls == pins_before + 1);
	CHECK(exe->status_code == KD_EXE_NATIVE_ONLY && warnings == 1);
	CHECK(kd_code_block_free == free_before);

	/* DRAINING can precede registry invalidation. Neither a NORMAL hit nor
	 * a new root can bypass source admission or mutate the table after close. */
	kd_exe_add(0, key(4), KD_EXE_LOCK_SPIN);
	exe = kd_get_exe(0, key(4));
	CHECK(kd_exe_publish_status(exe, KD_EXE_NORMAL));
	source_open = false;
	snapshot = *exe;
	free_before = kd_code_block_free;
	CHECK(!kd_exe_registered(0, key(4), KD_EXE_LOCK_SPIN, KD_ENTRY_ABI_LEGACY));
	CHECK(!kd_exe_is_ready(0, key(4)));
	pins_before = source_pin_calls;
	kd_exe_add(0, key(4), KD_EXE_LOCK_SPIN);
	kd_exe_add(0, key(5), KD_EXE_LOCK_SPIN);
	CHECK(source_pin_calls == pins_before + 2);
	CHECK(memcmp(&snapshot, exe, sizeof(snapshot)) == 0);
	CHECK(kd_get_exe(0, key(5))->status_code == KD_EXE_UNUSED);
	CHECK(kd_code_block_free == free_before);
	kd_exe_retire_all();
	CHECK(exe->status_code == KD_EXE_NATIVE_ONLY);
	CHECK(!kd_exe_registered(0, key(4), KD_EXE_LOCK_SPIN, KD_ENTRY_ABI_LEGACY));
	CHECK(!kd_exe_publish_status(exe, KD_EXE_NORMAL));
	kd_exe_add(0, key(4), KD_EXE_LOCK_SPIN);
	CHECK(exe->status_code == KD_EXE_NATIVE_ONLY && kd_code_block_free == free_before);
	kd_exe_exit();
}

static void check_lookup_publication(void)
{
	struct kd_exe_info *slot;
	int gate_before, pins_before;

	reset(NORMAL);
	CHECK(kd_exe_init() == 0);
	gate_before = gate_attempts;
	pins_before = source_pin_calls;
	slot = kd_get_exe(0, key(0));
	pending_publication = (struct kd_exe_info) {
		.pid = 0, .RIP = key(0), .lock_kind = KD_EXE_LOCK_SPIN,
		.code_block = kd_code_block_pool[0], .status_code = KD_EXE_UNUSED,
	};
	*slot = pending_publication;
	CHECK(!kd_exe_registered(0, key(0), KD_EXE_LOCK_SPIN, KD_ENTRY_ABI_LEGACY));
	for (int identity = 0; identity < 3; identity++) {
		/* Only the matching winner may satisfy this registration. The slot
		 * was still UNUSED when the real lookup chose it in all three cases. */
		slot->status_code = KD_EXE_UNUSED;
		pending_publication.pid = identity == 1 ? 1 : 0;
		pending_publication.RIP = identity == 2 ? key(1) : key(0);
		publish_after_lookup = slot;
		CHECK(kd_exe_registered(0, key(0), KD_EXE_LOCK_SPIN, KD_ENTRY_ABI_LEGACY) == (identity == 0));
		CHECK(publish_after_lookup == NULL);
	}
	CHECK(gate_attempts == gate_before && source_pin_calls == pins_before);
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
	/* Fast readers race first publication and colliding registrations. Only
	 * inspect totals after join; this does not model Linux IRQ/preemption. */
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
	CHECK(occupied == 6 && kd_code_block_free == KD_CODE_BLOCK_POOL - 3);
	CHECK(!errors && !warnings);
	for (int i = 0; i < 6; i++) {
		struct kd_exe_info *exe = kd_get_exe(0, key(i));

		CHECK(exe->RIP == key(i) && exe->status_code == KD_EXE_UNINIT);
		CHECK((exe->code_block != NULL) == !(i % 2));
		CHECK(!kd_exe_is_ready(0, key(i)));
	}
	kd_exe_exit();
}

#include "learning_control_fixture.inc"

int main(void)
{
	check_init_failures();
	check_mutex_preparation();
	check_pool(NORMAL);
	check_pool(PARTIAL);
	check_full_table();
	check_device();
	check_packet_directory();
	check_service_source_publication();
	check_learning_batches();
	check_learning_control();
	check_registration_reads();
	check_lookup_publication();
	check_concurrent_registration();
	reset(NORMAL);
	printf("production exe registry: %d checks, %d failures; pool=%d table=%d\n",
	       checks, failures, KD_CODE_BLOCK_POOL, KD_MAX_EXE);
	return failures != 0;
}
