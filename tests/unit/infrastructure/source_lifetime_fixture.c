/* SPDX-License-Identifier: GPL-2.0 */
/* Execute source and device decisions unchanged. Address/module/IRQ/VFS
 * primitives below are substitutes, not an unloadable-kernel simulation. */
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "exe_info.h"
#include "kd_source_api.h"

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
		(flags) = preempt_depth++;        \
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
struct module {
	int state;
	struct {
		void *base;
		unsigned int size, text_size;
	} core_layout, init_layout;
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
static int spin_entries_busy, spin_gates_busy;
struct inode {
	int unused;
};
struct file {
	unsigned int f_mode;
	void *private_data;
};

static bool try_module_get(struct module *module)
{
	CHECK(preempt_depth > 0);
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
	unsigned long index;

	CHECK(preempt_depth > 0);
	if (address < SOURCE)
		return NULL;
	index = (address - SOURCE) / 0x10000;
	if (index > KD_SOURCE_MAX_MODULES || (address & 0xffff) >= 0x5000)
		return NULL;
	return &modules[index];
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
static void kd_code_block_gate_lock(void)
{
	CHECK(!pthread_mutex_lock(&registry_gate));
}
static void kd_code_block_gate_unlock(void)
{
	CHECK(!pthread_mutex_unlock(&registry_gate));
}
static bool capable(int cap)
{
	CHECK(cap == CAP_SYS_MODULE);
	return admin;
}
static int mutex_lock_interruptible(pthread_mutex_t *lock)
{
	return interrupted ? -EINTR : pthread_mutex_lock(lock);
}
static void mutex_unlock(pthread_mutex_t *lock)
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
static int kd_spin_gates_check_idle(void)
{
	return spin_gates_busy;
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
	CHECK(caps.features == (KD_JIT_CAP_MUTEX_STACK |
				(module_bytes ? KD_JIT_CAP_PERCPU_MODULE : 0)));
	CHECK(caps.mutex_stack_bytes == KD_JIT_MUTEX_STACK_BYTES);
	CHECK(caps.percpu_module_bytes == module_bytes);
	after = status();
	CHECK(!memcmp(&before, &after, sizeof(before)));
}
static void reset(void)
{
	CHECK(!provider.refs);
	provider.state = MODULE_STATE_LIVE;
	provider.fail_get = false;
	for (unsigned int i = 0; i <= KD_SOURCE_MAX_MODULES; i++) {
		CHECK(!modules[i].refs);
		modules[i].state = MODULE_STATE_LIVE;
		modules[i].fail_get = false;
		modules[i].core_layout.base = (void *)(SOURCE + i * 0x10000);
		modules[i].core_layout.size = 0x4000;
		modules[i].core_layout.text_size = 0x2000;
		modules[i].init_layout.base =
			(void *)(SOURCE + i * 0x10000 + 0x4000);
		modules[i].init_layout.size = 0x1000;
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
	for (int busy = 0; busy < 4; busy++) {
		mutex_idle = busy != 0;
		tasks_idle = busy != 1;
		spin_entries_busy = busy == 2;
		spin_gates_busy = busy == 3;
		CHECK(retire() == -EBUSY && status().modules == 1);
		CHECK(table[0].status_code == KD_EXE_NORMAL);
	}
	mutex_idle = tasks_idle = true;
	spin_entries_busy = spin_gates_busy = 0;
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

int main(void)
{
	_Static_assert(sizeof(struct kd_source_info) == 16, "info ABI");
	_Static_assert(sizeof(struct kd_source_range) == 16, "range ABI");
	_Static_assert(KD_SOURCE_PIN == 0x40104b70, "Python PIN ABI");
	_Static_assert(KD_SOURCE_INFO == 0x80104b71, "Python INFO ABI");
	_Static_assert(KD_SOURCE_RETIRE == 0x4b72, "Python RETIRE ABI");
	_Static_assert(sizeof(struct kd_jit_caps) == 16, "capability ABI");
	_Static_assert(KD_JIT_CAPS == 0x80104b73, "Python capability ioctl");
	_Static_assert(KD_JIT_CAPS_VERSION == 2 &&
			       KD_JIT_CAP_MUTEX_STACK == 1 &&
			       KD_JIT_CAP_PERCPU_MODULE == 2,
		       "Python capability semantics");
	_Static_assert(KD_JIT_PERCPU_MODULE_BYTES == 8192 &&
			       KD_JIT_PERCPU_ALIGNMENT == 4,
		       "Python module arena");
	_Static_assert(KD_JIT_MUTEX_STACK_BYTES == 256,
		       "Python checked window");
	_Static_assert(sizeof(struct kd_exe_info) == 64, "entry ABI");
	_Static_assert(sizeof(struct kd_recv_pkt) == 24, "upload ABI");
	residency();
	draining();
	concurrent_pins();
	printf("production source lifetime: %u checks, 0 failures; cap=%u\n",
	       atomic_load(&checks), KD_SOURCE_MAX_MODULES);
	return 0;
}
