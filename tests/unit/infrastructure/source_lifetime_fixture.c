/* SPDX-License-Identifier: GPL-2.0 */
/* Execute source and device decisions unchanged. Address/module/IRQ/VFS
 * primitives below are substitutes, not an unloadable-kernel simulation. */
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <sched.h>
#include <stdbool.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "exe_info.h"
#include "kd_image.h"
#define GFP_KERNEL 0
#define kzalloc(n,f) calloc(1,n)
#define kfree(p) free(p)
void kd_image_discard(struct kd_jit_image *image) { if (image) abort(); }
static bool direct_pool_available;
int kd_image_direct_available(void) { return direct_pool_available; }
#include "kd_source_api.h"
#include "kd_api_control.h"

typedef long long s64;
typedef unsigned long long u64;
#define U64_MAX ULLONG_MAX
typedef _Atomic long long atomic64_t;
#define ATOMIC64_INIT(v) ATOMIC_VAR_INIT(v)
#define atomic64_read(p) atomic_load(p)
#define atomic64_set(p, v) atomic_store(p, v)
#define atomic64_try_cmpxchg(p, old, v) atomic_compare_exchange_strong(p, old, v)
#define atomic64_dec_return(p) (atomic_fetch_sub(p, 1) - 1)
#define atomic64_fetch_or(v, p) atomic_fetch_or(p, v)
static atomic_bool pause_frame_get, frame_get_paused, release_frame_get;
static _Thread_local unsigned int source_lock_calls;

static atomic_uint checks;
#define CHECK(expr)                                                     \
	do {                                                            \
		atomic_fetch_add(&checks, 1);                           \
		if (!(expr)) {                                          \
			fprintf(stderr, "FAIL line %d: %s\n", __LINE__, \
				#expr);                                 \
			exit(1);                                        \
		}                                                       \
	} while (0)
#define BUG_ON(expr) CHECK(!(expr))
#define BUILD_BUG_ON(expr) _Static_assert(!(expr), "kernel build contract")
#define CONFIG_X86_64 1
#define CONFIG_SMP 1
#define PERCPU_MODULE_RESERVE (8 << 10)
#define PCPU_MIN_ALLOC_SIZE 4
#define READ_ONCE(value) __atomic_load_n(&(value), __ATOMIC_RELAXED)
#define WRITE_ONCE(value, new) __atomic_store_n(&(value), new, __ATOMIC_RELAXED)
#define smp_load_acquire(p) __atomic_load_n(p, __ATOMIC_ACQUIRE)
#define try_cmpxchg(p, old, value)                                          \
	__atomic_compare_exchange_n(p, old, value, false, __ATOMIC_SEQ_CST, \
				    __ATOMIC_SEQ_CST)
#define min(a, b) ((a) < (b) ? (a) : (b))
#define __user
#define ERESTARTSYS 512
#define FMODE_WRITE 2
#define CAP_SYS_MODULE 16
#define DEFINE_RAW_SPINLOCK(name) \
	pthread_mutex_t name = PTHREAD_MUTEX_INITIALIZER
static _Thread_local unsigned int preempt_depth;
#define raw_spin_lock_irqsave(lock, flags)        \
	do {                                      \
		(flags) = preempt_depth++; source_lock_calls++;        \
		CHECK(!pthread_mutex_lock(lock)); \
	} while (0)
#define raw_spin_unlock_irqrestore(lock, flags)     \
	do {                                        \
		CHECK(!pthread_mutex_unlock(lock)); \
		preempt_depth = (flags);            \
	} while (0)
#define pr_info(...)                         \
	do {                                 \
		if (0)                       \
			printf(__VA_ARGS__); \
	} while (0)

enum { MODULE_STATE_LIVE, MODULE_STATE_COMING, MODULE_STATE_GOING };
enum mod_mem_type {
	MOD_TEXT,
	MOD_DATA,
	MOD_RODATA,
	MOD_RO_AFTER_INIT,
	MOD_INIT_TEXT,
	MOD_INIT_DATA,
	MOD_INIT_RODATA,
	MOD_MEM_NUM_TYPES,
};
#define mod_mem_type_is_init(type) \
	((type) == MOD_INIT_TEXT || (type) == MOD_INIT_DATA || \
	 (type) == MOD_INIT_RODATA)
struct module {
	int state;
	struct {
		void *base;
		unsigned int size;
	} mem[MOD_MEM_NUM_TYPES];
	atomic_int refs;
	bool fail_get;
};
static struct module provider, modules[KD_SOURCE_MAX_MODULES + 1];
#define THIS_MODULE (&provider)
#define CORE 0x100000000UL
#define SOURCE 0x200000000UL
static struct kd_exe_info table[KD_MAX_EXE], *kd_exes = table;
static pthread_mutex_t registry_gate = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t kd_publish_lock = PTHREAD_MUTEX_INITIALIZER;
static bool admin = true, interrupted, copy_failed;
static bool percpu_symbol_available = true;
static unsigned long percpu_reserved_chunk = 0x300000000UL;
static bool mutex_idle = true, tasks_idle = true;
static int spin_entries_busy;
struct inode {
	int unused;
};
struct file {
	unsigned int f_mode;
	void *private_data;
};

/* API selection has its own production fixture. Here observe only exact
 * ioctl/release forwarding from the shared source-device implementation. */
static struct file *api_file, *api_released_file;
static unsigned int api_command, api_calls, api_releases;
static unsigned long api_argument;
static long kd_api_provider_ioctl(struct file *file, unsigned int command,
				  unsigned long argument)
{
	api_file = file; api_command = command; api_argument = argument; api_calls++;
	return -EINPROGRESS;
}
static void kd_api_provider_release(struct file *file)
{
	api_released_file = file; api_releases++;
}

static bool try_module_get(struct module *module)
{
	if (module != THIS_MODULE)
                CHECK(preempt_depth > 0);
        if (module == THIS_MODULE && atomic_load(&pause_frame_get)) {
                atomic_store(&frame_get_paused, true);
                while (!atomic_load(&release_frame_get))
                        sched_yield();
        }
	if (module->state == MODULE_STATE_GOING || module->fail_get)
		return false;
	atomic_fetch_add(&module->refs, 1);
	return true;
}

static void module_put(struct module *module)
{
	CHECK(!preempt_depth);
	if (module != THIS_MODULE) {
		/* The last source ref must never precede terminal registry publication. */
		for (unsigned int i = 0; i < KD_MAX_EXE; i++)
			CHECK(table[i].status_code == KD_EXE_UNUSED ||
			      table[i].status_code == KD_EXE_NATIVE_ONLY);
	}
	CHECK(atomic_fetch_sub(&module->refs, 1) > 0);
}

static struct module *module_address(unsigned long address)
{
	CHECK(preempt_depth > 0);
	for (unsigned int i = 0; i <= KD_SOURCE_MAX_MODULES; i++)
		for (enum mod_mem_type type = MOD_TEXT;
		     type < MOD_MEM_NUM_TYPES; type++) {
			unsigned long base = (unsigned long)modules[i].mem[type].base;
			unsigned long size = modules[i].mem[type].size;

			if (address >= base && address - base < size)
				return &modules[i];
		}
	return NULL;
}

static unsigned long kallsyms_lookup_name(const char *name)
{
	if (!strcmp(name, "pcpu_reserved_chunk"))
		return percpu_symbol_available ?
			       (unsigned long)&percpu_reserved_chunk :
			       0;
	if (!strcmp(name, "__module_address"))
		return (unsigned long)module_address;
	if (!strcmp(name, "_stext"))
		return CORE;
	if (!strcmp(name, "_etext"))
		return CORE + 0x2000;
	if (!strcmp(name, "__init_begin"))
		return CORE + 0x3000;
	if (!strcmp(name, "__init_end"))
		return CORE + 0x4000;
	if (!strcmp(name, "_end"))
		return CORE + 0x8000;
	return 0;
}
static unsigned long kd_code_block_gate_lock(void)
{
	CHECK(!pthread_mutex_lock(&registry_gate));
	return 0;
}
static void kd_code_block_gate_unlock(unsigned long flags)
{
	(void)flags; CHECK(!pthread_mutex_unlock(&registry_gate));
}
static bool capable(int cap)
{
	CHECK(cap == CAP_SYS_MODULE);
	return admin;
}
static int kd_mutex_lock_interruptible(pthread_mutex_t *lock)
{
	return interrupted ? -EINTR : pthread_mutex_lock(lock);
}
static void kd_mutex_local_unlock(pthread_mutex_t *lock)
{
	CHECK(!pthread_mutex_unlock(lock));
}
static bool kd_mutex_check_idle(void)
{
	return mutex_idle;
}
static bool kd_mutex_tasks_idle(void)
{
	return tasks_idle;
}
static int kd_spin_entries_check_idle(void)
{
	return spin_entries_busy;
}
static int nonseekable_open(struct inode *inode, struct file *file)
{
	(void)inode;
	(void)file;
	return 0;
}
static int copy_from_user(void *dest, const void *src, unsigned long size)
{
	if (copy_failed)
		return 1;
	memcpy(dest, src, size);
	return 0;
}
#define copy_to_user copy_from_user
#include "source_production.h"

static struct kd_source_info status(void)
{
	struct kd_source_info info;
	struct file control = { 0 };

	CHECK(!kd_dev_ioctl(&control, KD_SOURCE_INFO, (unsigned long)&info));
	return info;
}
static long retire(void)
{
	struct file control = { 0 };

	return kd_dev_ioctl(&control, KD_SOURCE_RETIRE, 0);
}

static void check_caps(struct file *file)
{
	struct kd_source_info before = status(), after;
	struct kd_jit_caps caps;
	unsigned int module_bytes = percpu_symbol_available &&
						    percpu_reserved_chunk ?
					    KD_JIT_PERCPU_MODULE_BYTES :
					    0;

	/* Query semantics are independent of writable leases and retirement.
	 * Reading the immutable contract must not pin resources or reopen entry. */
	memset(&caps, 0xff, sizeof(caps));
	CHECK(!kd_dev_ioctl(file, KD_JIT_CAPS, (unsigned long)&caps));
	CHECK(caps.version == KD_JIT_CAPS_VERSION);
	CHECK(caps.features == (KD_JIT_CAP_MUTEX_STACK | KD_JIT_CAP_MUTEX_IMAGES | KD_JIT_CAP_MUTEX_EXCLUSIVE | KD_JIT_CAP_NATIVE_ESCAPE | KD_JIT_CAP_ADDRESS_GUARD | KD_JIT_CAP_STRING_SERVICES | KD_JIT_CAP_STRING_WRITE | KD_JIT_CAP_AUDITED_STRINGS | KD_JIT_CAP_ROOT_NATIVE_ESCAPE | KD_JIT_CAP_INDIRECT_CALL | KD_JIT_CAP_ORIGIN_INSTRUCTION | KD_JIT_CAP_ORIGIN_CALL |
				(module_bytes ? KD_JIT_CAP_PERCPU_MODULE : 0) |
				(direct_pool_available ? KD_JIT_CAP_DIRECT_STRINGS : 0)));
	CHECK(caps.mutex_stack_bytes == KD_JIT_MUTEX_STACK_BYTES);
	CHECK(caps.percpu_module_bytes == module_bytes);
	after = status();
	CHECK(!memcmp(&before, &after, sizeof(before)));
}

static void check_api_forwarding(void)
{
	struct file control = {0};
	struct kd_source_info before = status(), after;
	const unsigned int commands[] = {KD_API_SELECT, KD_API_CANCEL, KD_API_QUERY};
	for (unsigned int i = 0; i < sizeof(commands) / sizeof(commands[0]); i++) {
		unsigned int calls_before = api_calls;
		unsigned long argument = 0x123400UL + i;
		CHECK(kd_dev_ioctl(&control, commands[i], argument) == -EINPROGRESS);
		CHECK(api_calls == calls_before + 1 && api_file == &control &&
		      api_command == commands[i] && api_argument == argument);
	}
	unsigned int releases_before = api_releases;
	CHECK(!kd_dev_release(NULL, &control));
	CHECK(api_releases == releases_before + 1 && api_released_file == &control);
	after = status();
	CHECK(!memcmp(&before, &after, sizeof(before)));
}
static void reset(void)
{
	/* Deliberately noncontiguous and not in enum order. Init sections remain
	 * visible to lookup so the production residency filter must reject them. */
	static const unsigned long offsets[MOD_MEM_NUM_TYPES] = {
		[MOD_TEXT] = 0, [MOD_DATA] = 0x8000,
		[MOD_RODATA] = 0x3000, [MOD_RO_AFTER_INIT] = 0x2000,
		[MOD_INIT_TEXT] = 0x4000, [MOD_INIT_DATA] = 0xa000,
		[MOD_INIT_RODATA] = 0xc000,
	};

	CHECK(!provider.refs);
	provider.state = MODULE_STATE_LIVE;
	provider.fail_get = false;
	for (unsigned int i = 0; i <= KD_SOURCE_MAX_MODULES; i++) {
		CHECK(!modules[i].refs);
		modules[i].state = MODULE_STATE_LIVE;
		modules[i].fail_get = false;
		for (enum mod_mem_type type = MOD_TEXT;
		     type < MOD_MEM_NUM_TYPES; type++) {
			modules[i].mem[type].base =
				(void *)(SOURCE + i * 0x10000 + offsets[type]);
			modules[i].mem[type].size = type == MOD_TEXT ? 0x2000 : 0x1000;
		}
	}
	CHECK(!kd_source_init());
	for (unsigned int i = 0; i < KD_MAX_EXE; i++)
		table[i].status_code = KD_EXE_UNUSED;
	table[0].status_code = KD_EXE_NORMAL;
	table[1].status_code = KD_EXE_CALL_MISS;
	table[2].status_code = KD_EXE_UNINIT;
}

static void residency(void)
{
	reset();
	CHECK(kd_source_pin_range(SOURCE, 4) == -ESHUTDOWN);
	CHECK(kd_source_pin_target(SOURCE) == -ESHUTDOWN);
	CHECK(kd_source_writer_get());
	CHECK(!kd_source_pin_root(CORE));
	CHECK(kd_source_pin_root(CORE + 0x2100) == -EPERM);
	CHECK(!kd_source_pin_range(CORE + 0x2100, 4));
	CHECK(kd_source_pin_range(CORE + 0x2fff, 2) == -EPERM);
	CHECK(kd_source_pin_range(CORE + 0x3000, 4) == -EPERM);
	CHECK(!kd_source_pin_range(CORE + 0x4000, 4));
	CHECK(kd_source_pin_range(CORE, 0) == -EINVAL);
	CHECK(kd_source_pin_range(CORE, KD_SOURCE_MAX_READ + 1) == -EINVAL);
	CHECK(kd_source_pin_range(ULONG_MAX, 2) == -EINVAL);
	CHECK(kd_source_pin_root(SOURCE + 0x4000) == -EPERM);
	CHECK(kd_source_pin_range(SOURCE + 0x6000, 4) == -ESTALE);
	for (int state = MODULE_STATE_COMING; state <= MODULE_STATE_GOING;
	     state++) {
		modules[0].state = state;
		CHECK(kd_source_pin_root(SOURCE) == -ESTALE &&
		      !modules[0].refs);
	}
	modules[0].state = MODULE_STATE_LIVE;
	modules[0].fail_get = true;
	CHECK(kd_source_pin_root(SOURCE) == -ESTALE);
	modules[0].fail_get = false;
	CHECK(!kd_source_pin_root(SOURCE));
	CHECK(!kd_source_pin_range(SOURCE + 0x3000, 4));
	CHECK(kd_source_pin_root(SOURCE + 0x3000) == -EPERM);
	CHECK(kd_source_pin_range(SOURCE + 0x3fff, 2) == -EPERM);
	CHECK(modules[0].refs == 1 && status().modules == 1);
	for (unsigned int i = 1; i < KD_SOURCE_MAX_MODULES; i++)
		CHECK(!kd_source_pin_root(SOURCE + i * 0x10000));
	CHECK(status().modules == KD_SOURCE_MAX_MODULES);
	CHECK(kd_source_pin_root(SOURCE + KD_SOURCE_MAX_MODULES * 0x10000) ==
	      -ENOSPC);
	CHECK(!kd_source_pin_root(SOURCE) && modules[0].refs == 1);
	kd_source_writer_put();
	CHECK(!retire() && status().state == KD_SOURCE_RETIRED);
	CHECK(!status().modules && !retire());
	CHECK(!kd_exe_publish_status(&table[0], KD_EXE_NORMAL));
	CHECK(kd_source_pin_root(SOURCE) == -ESHUTDOWN);
	CHECK(!kd_source_writer_get() && !kd_source_frame_get());
}

static void module_regions(void)
{
	reset();
	CHECK(kd_source_writer_get());
	CHECK(kd_source_frame_get());
	for (enum mod_mem_type type = MOD_TEXT; type < MOD_MEM_NUM_TYPES; type++) {
		unsigned long base = (unsigned long)modules[0].mem[type].base;
		int text_result = type == MOD_TEXT ? 0 : -EPERM;

		CHECK(kd_source_pin_root(base) == text_result);
		CHECK(kd_source_pin_target(base) == text_result);
		CHECK(kd_source_pin_range(base, 4) ==
		      (mod_mem_type_is_init(type) ? -EPERM : 0));
	}
	/* A single lease covers all resident regions, but each read window must
	 * prove residency again at every region boundary. Adjacent core regions
	 * are valid; init regions and gaps must not inherit the preceding lease. */
	CHECK(modules[0].refs == 1 && status().modules == 1);
	CHECK(!kd_source_pin_range(SOURCE + 0x1fff, 2));
	CHECK(!kd_source_pin_range(SOURCE + 0x2fff, 2));
	CHECK(kd_source_pin_range(SOURCE + 0x3fff, 2) == -EPERM);
	CHECK(kd_source_pin_range(SOURCE + 0x8fff, 2) == -ESTALE);
	CHECK(kd_source_pin_root(SOURCE + 0x6000) == -ESTALE);
	CHECK(modules[0].refs == 1 && status().modules == 1);

	/* Reject corrupt/wrapping module extents before taking a source reference. */
	modules[1].mem[MOD_TEXT].base = (void *)(ULONG_MAX - 1);
	modules[1].mem[MOD_TEXT].size = 4;
	CHECK(kd_source_pin_root(ULONG_MAX - 1) == -EOVERFLOW);
	CHECK(!modules[1].refs && status().modules == 1);
	kd_source_frame_put();
	kd_source_writer_put();
	CHECK(!retire() && !status().modules);
}

static void draining(void)
{
	struct file writer = { .f_mode = FMODE_WRITE }, control = { 0 };
	struct kd_source_range range = { SOURCE, 4 };

	reset();
	provider.state = MODULE_STATE_COMING;
	CHECK(kd_dev_open(NULL, &writer) == -ENODEV);
	provider.state = MODULE_STATE_LIVE;
	CHECK(!kd_dev_open(NULL, &writer));
	CHECK(!kd_dev_open(NULL, &control) && status().writers == 1);
	check_caps(&writer);
	check_caps(&control);
	/* Missing/empty boot metadata disables only the range contract, without
	 * changing source state or inventing an allocator fallback guarantee. */
	percpu_symbol_available = false;
	check_caps(&control);
	percpu_symbol_available = true;
	percpu_reserved_chunk = 0;
	check_caps(&writer);
	percpu_reserved_chunk = 0x300000000UL;
	CHECK(kd_dev_ioctl(&control, KD_SOURCE_PIN, (unsigned long)&range) ==
	      -EBADF);
	CHECK(!kd_dev_ioctl(&writer, KD_SOURCE_PIN, (unsigned long)&range));
	CHECK(kd_dev_ioctl(&control, 0, 0) == -ENOTTY);
	admin = false;
	CHECK(retire() == -EPERM && kd_source_is_open());
	admin = true;
	interrupted = true;
	CHECK(retire() == -ERESTARTSYS && kd_source_is_open());
	interrupted = false;
	copy_failed = true;
	CHECK(kd_dev_ioctl(&control, KD_JIT_CAPS, (unsigned long)&range) ==
	      -EFAULT);
	CHECK(kd_dev_ioctl(&writer, KD_SOURCE_PIN, (unsigned long)&range) ==
	      -EFAULT);
	copy_failed = false;
	provider.fail_get = true;
	CHECK(!kd_source_frame_get());
	provider.fail_get = false;
	CHECK(kd_source_frame_get() && provider.refs == 1);
	CHECK(retire() == -EBUSY && status().state == KD_SOURCE_DRAINING);
	check_caps(&writer);
	check_caps(&control);
	CHECK(!kd_source_writer_get() && !kd_source_frame_get());
	CHECK(!kd_source_pin_target(SOURCE + 0x10000));
	CHECK(!kd_source_pin_range(SOURCE + 0x20000, 4));
	CHECK(status().modules == 3 && table[0].status_code == KD_EXE_NORMAL);
	kd_source_frame_put();
	CHECK(!status().frames && !provider.refs && retire() == -EBUSY);
	CHECK(!kd_dev_release(NULL, &writer));
	CHECK(!kd_dev_release(NULL, &control));
	CHECK(!retire() && !status().modules);
	CHECK(kd_dev_open(NULL, &writer) == -ESHUTDOWN);
	CHECK(!kd_dev_open(NULL, &control));
	check_caps(&control);
	CHECK(kd_dev_ioctl(&control, _IOR('K', 0x73, __u32),
			   (unsigned long)&range) == -ENOTTY);
	CHECK(kd_dev_ioctl(&control, _IOW('K', 0x73, struct kd_jit_caps),
			   (unsigned long)&range) == -ENOTTY);
	CHECK(!kd_dev_release(NULL, &control));
	/* Isolate frame-busy from writer-busy, then each secondary idle predicate. */
	reset();
	CHECK(kd_source_frame_get() && !kd_source_pin_target(SOURCE));
	CHECK(retire() == -EBUSY && status().frames == 1);
	kd_source_frame_put();
	for (int busy = 0; busy < 3; busy++) {
		mutex_idle = busy != 0;
		tasks_idle = busy != 1;
		spin_entries_busy = busy == 2;
		CHECK(retire() == -EBUSY && status().modules == 1);
		CHECK(table[0].status_code == KD_EXE_NORMAL);
	}
	mutex_idle = tasks_idle = true;
	spin_entries_busy = 0;
	CHECK(!retire() && !status().modules);
}

static pthread_barrier_t start;
static void *pin_worker(void *unused)
{
	(void)unused;
	pthread_barrier_wait(&start);
	for (unsigned int i = 0; i < 200; i++)
		CHECK(!kd_source_pin_range(SOURCE + i, 4));
	return NULL;
}
static void concurrent_pins(void)
{
	pthread_t threads[8];

	reset();
	CHECK(kd_source_writer_get());
	CHECK(!pthread_barrier_init(&start, NULL, 8));
	for (unsigned int i = 0; i < 8; i++)
		CHECK(!pthread_create(&threads[i], NULL, pin_worker, NULL));
	for (unsigned int i = 0; i < 8; i++)
		CHECK(!pthread_join(threads[i], NULL));
	CHECK(!pthread_barrier_destroy(&start));
	CHECK(status().modules == 1 && modules[0].refs == 1);
	kd_source_writer_put();
	CHECK(!retire());
	kd_source_exit();
}

/* Hold acquisition between its count reservation and module reference. Close
 * must report busy and reject new frames until this exact holder drains. */
static void *closing_frame_worker(void *unused)
{
        unsigned int locks = source_lock_calls;
        (void)unused;
        CHECK(kd_source_frame_get());
        kd_source_frame_put();
        CHECK(source_lock_calls == locks);
        return NULL;
}

static void atomic_frame_admission(void)
{
        pthread_t thread;
        unsigned int locks;

        reset();
        locks = source_lock_calls;
        atomic64_set(&kd_source_frame_gate, UINT_MAX);
        CHECK(!kd_source_frame_get() && !provider.refs);
        CHECK(kd_source_frame_count() == UINT_MAX);
        atomic64_set(&kd_source_frame_gate, 0);
        provider.fail_get = true;
        CHECK(!kd_source_frame_get() && !kd_source_frame_count());
        provider.fail_get = false;
        CHECK(kd_source_frame_get() && kd_source_frame_count() == 1);
        kd_source_frame_put();
        CHECK(!kd_source_frame_count() && !provider.refs &&
              source_lock_calls == locks);

        atomic_store(&pause_frame_get, true);
        atomic_store(&frame_get_paused, false);
        atomic_store(&release_frame_get, false);
        CHECK(!pthread_create(&thread, NULL, closing_frame_worker, NULL));
        while (!atomic_load(&frame_get_paused))
                sched_yield();
        CHECK(kd_source_begin_retire() == -EBUSY);
        CHECK(status().frames == 1 && !provider.refs);
        CHECK(!kd_source_frame_get());
        atomic_store(&release_frame_get, true);
        CHECK(!pthread_join(thread, NULL));
        atomic_store(&pause_frame_get, false);
        CHECK(!status().frames && !provider.refs && !retire());
        CHECK(!kd_source_frame_get());
}

static void *frame_loop_worker(void *unused)
{
        unsigned int locks = source_lock_calls;
        (void)unused;
        pthread_barrier_wait(&start);
        for (unsigned int i = 0; i < 2000; i++) {
                if (!kd_source_frame_get())
                        break;
                kd_source_frame_put();
        }
        CHECK(source_lock_calls == locks);
        return NULL;
}

static void concurrent_frame_close(void)
{
        pthread_t threads[4];
        reset();
        CHECK(!pthread_barrier_init(&start, NULL, 5));
        for (unsigned int i = 0; i < 4; i++)
                CHECK(!pthread_create(&threads[i], NULL, frame_loop_worker, NULL));
        pthread_barrier_wait(&start);
        int result = kd_source_begin_retire();
        CHECK(result == 0 || result == -EBUSY);
        for (unsigned int i = 0; i < 4; i++)
                CHECK(!pthread_join(threads[i], NULL));
        CHECK(!pthread_barrier_destroy(&start));
        CHECK(!status().frames && !provider.refs && !kd_source_frame_get());
        CHECK(!retire());
}

static void immutable_bindings(void)
{
	reset();
	CHECK(!kd_source_binding_count());
	CHECK(kd_source_binding_get());
	CHECK(kd_source_binding_get());
	CHECK(kd_source_binding_count() == 2);
	CHECK(kd_source_begin_retire() == -EBUSY);
	CHECK(status().state == KD_SOURCE_OPEN);
	CHECK(kd_source_frame_get());
	kd_source_frame_put();
	kd_source_binding_put();
	CHECK(kd_source_binding_count() == 1);
	CHECK(kd_source_begin_retire() == -EBUSY);
	CHECK(status().state == KD_SOURCE_OPEN);
	kd_source_binding_put();
	CHECK(!kd_source_binding_count());
	CHECK(!kd_source_begin_retire());
	CHECK(status().state == KD_SOURCE_DRAINING);
	CHECK(!kd_source_binding_get());
	CHECK(!retire());
}

int main(void)
{
	_Static_assert(sizeof(struct kd_source_info) == 16, "info ABI");
	_Static_assert(sizeof(struct kd_source_range) == 16, "range ABI");
	_Static_assert(KD_SOURCE_PIN == 0x40104b70, "Python PIN ABI");
	_Static_assert(KD_SOURCE_INFO == 0x80104b71, "Python INFO ABI");
	_Static_assert(KD_SOURCE_RETIRE == 0x4b72, "Python RETIRE ABI");
	_Static_assert(sizeof(struct kd_jit_caps) == 16, "capability ABI");
	_Static_assert(KD_JIT_CAPS == 0x80104b73, "Python capability ioctl");
	_Static_assert(KD_JIT_CAPS_VERSION == 14 &&
			       KD_JIT_CAP_MUTEX_STACK == 1 &&
			       KD_JIT_CAP_PERCPU_MODULE == 2 &&
			       KD_JIT_CAP_NATIVE_ESCAPE == 32 && KD_JIT_CAP_ADDRESS_GUARD == 64 &&
			       KD_JIT_CAP_STRING_SERVICES == 128 && KD_JIT_CAP_STRING_WRITE == 256 &&
			       KD_JIT_CAP_AUDITED_STRINGS == 512 && KD_JIT_CAP_DIRECT_STRINGS == 1024 &&
			       KD_JIT_CAP_ROOT_NATIVE_ESCAPE == 2048 && KD_JIT_CAP_INDIRECT_CALL == 4096 &&
			       KD_JIT_CAP_ORIGIN_INSTRUCTION == 8192 && KD_JIT_CAP_ORIGIN_CALL == 16384,
		       "Python capability semantics");
	_Static_assert(KD_JIT_PERCPU_MODULE_BYTES == 8192 &&
			       KD_JIT_PERCPU_ALIGNMENT == 4,
		       "Python module arena");
	_Static_assert(KD_JIT_MUTEX_STACK_BYTES == 256,
		       "Python checked window");
	_Static_assert(sizeof(struct kd_exe_info) == 64, "entry ABI");
	_Static_assert(sizeof(struct kd_recv_pkt) == 64, "upload ABI");
	residency();
	module_regions();
	direct_pool_available = true;
	check_caps(&(struct file){ 0 });
	direct_pool_available = false;
	draining();
	concurrent_pins();
	atomic_frame_admission();
	concurrent_frame_close();
	immutable_bindings();
	check_api_forwarding();
	printf("production source lifetime: %u checks, 0 failures; cap=%u\n",
	       atomic_load(&checks), KD_SOURCE_MAX_MODULES);
	return 0;
}
