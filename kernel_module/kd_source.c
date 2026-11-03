// SPDX-License-Identifier: GPL-2.0

/* Residency leases for original text/data, not executable-image versions.
 * OPEN accepts writers/frames; DRAINING lets retained holders finish; RETIRED
 * releases dependencies only after registry invalidation and complete drain.
 * No path pins arbitrary heap objects or supplies missing guest hook readers. */
#include <linux/bug.h>
#include <linux/atomic.h>
#include <linux/errno.h>
#include <linux/kallsyms.h>
#include <linux/kernel.h>
#include <linux/limits.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/spinlock.h>
#include <linux/string.h>

#include "kd_source.h"
#include "kd_generated_text.h"

/* Session-wide dependencies avoid per-image reclamation while C3 is deferred.
 * A reverse source/provider dependency is broken by explicit retirement before
 * either exit. No allocation or sleeping occurs in lock hooks. */
static DEFINE_RAW_SPINLOCK(kd_source_lock);
struct kd_source_info kd_sources;
/* Admission and live count share one atomic word: closing cannot observe zero
 * between an OPEN check and a later increment. The upper bit is irreversible
 * until module init; low 32 bits retain the source-info counter ABI. Writers
 * and dependency registration are cold paths protected by kd_source_lock. */
#define KD_SOURCE_FRAME_CLOSED (1ULL << 32)
static atomic64_t kd_source_frame_gate = ATOMIC64_INIT(0);
static u64 kd_source_bindings;

static unsigned int kd_source_frame_count(void)
{
	return (unsigned int)atomic64_read(&kd_source_frame_gate);
}

static void kd_source_frame_release(void)
{
	/* A zero-count release wraps the low word, even when admission is closed. */
	BUG_ON((unsigned int)atomic64_dec_return(&kd_source_frame_gate) == UINT_MAX);
}
static struct module *kd_source_modules[KD_SOURCE_MAX_MODULES];
static struct module *(*kd_module_address)(unsigned long address);
static int (*kd_generated_lookup)(unsigned long address,
				  struct kd_generated_text_extent *extent);
static unsigned long kd_core_start, kd_core_text_end, kd_core_end;
static unsigned long kd_init_start, kd_init_end;

enum kd_source_scope {
	KD_SOURCE_ROOT,
	KD_SOURCE_WRITER,
	KD_SOURCE_FRAME,
};

/* Register one writer pin for shared source mutation. */
bool kd_source_writer_get(void)
{
	unsigned long flags;
	bool ok;

	raw_spin_lock_irqsave(&kd_source_lock, flags);
	ok = kd_sources.state == KD_SOURCE_OPEN &&
	     kd_sources.writers != UINT_MAX;
	if (ok)
		kd_sources.writers++;
	raw_spin_unlock_irqrestore(&kd_source_lock, flags);
	return ok;
}

void kd_source_writer_put(void)
{
	unsigned long flags;

	raw_spin_lock_irqsave(&kd_source_lock, flags);
	BUG_ON(!kd_sources.writers);
	kd_sources.writers--;
	raw_spin_unlock_irqrestore(&kd_source_lock, flags);
}

bool kd_source_binding_get(void)
{
	unsigned long flags;
	bool acquired;

	raw_spin_lock_irqsave(&kd_source_lock, flags);
	acquired = kd_sources.state == KD_SOURCE_OPEN && kd_source_bindings != U64_MAX;
	if (acquired)
		++kd_source_bindings;
	raw_spin_unlock_irqrestore(&kd_source_lock, flags);
	return acquired;
}

void kd_source_binding_put(void)
{
	unsigned long flags;

	raw_spin_lock_irqsave(&kd_source_lock, flags);
	BUG_ON(!kd_source_bindings);
	--kd_source_bindings;
	raw_spin_unlock_irqrestore(&kd_source_lock, flags);
}

u64 kd_source_binding_count(void)
{
	unsigned long flags;
	u64 bindings;

	raw_spin_lock_irqsave(&kd_source_lock, flags);
	bindings = kd_source_bindings;
	raw_spin_unlock_irqrestore(&kd_source_lock, flags);
	return bindings;
}

/* Register one frame pin and hold a module ref for the translated frame lifetime. */
bool kd_source_frame_get(void)
{
	s64 old = atomic64_read(&kd_source_frame_gate);

	do {
		if ((old & KD_SOURCE_FRAME_CLOSED) || (unsigned int)old == UINT_MAX)
			return false;
	} while (!atomic64_try_cmpxchg(&kd_source_frame_gate, &old, old + 1));
	/* Count covers this in-progress acquisition as well as the retained frame.
	 * A close racing here must see it or follow the rollback decrement. */
	if (try_module_get(THIS_MODULE))
		return true;
	kd_source_frame_release();
	return false;
}

void kd_source_frame_put(void)
{
	kd_source_frame_release();
	/* Spans the retained frame, not earlier guest dispatch or code after pop.
	 * This is not the missing generic hook-reader lifetime protocol. */
	module_put(THIS_MODULE);
}

/* Only the producer can classify separately allocated instruction pages. Its
 * successful module reply already owns a reference, unlike __module_address.
 * Keep that reference once per source session and drop every temporary reply
 * reference on rejection or reuse of an existing retained owner. */
static int kd_source_generated_piece(unsigned long address, unsigned long *end)
{
	struct kd_generated_text_extent extent = { 0 };
	unsigned int owner_index;
	int ret;

	if (!kd_generated_lookup)
		return -ESTALE;
	ret = kd_generated_lookup(address, &extent);
	if (ret)
		return ret == -ENOENT ? -ESTALE : ret;
	ret = -EPROTO;
	if (extent.abi != KD_GENERATED_TEXT_ABI_VERSION ||
	    (extent.kind != KD_GENERATED_TEXT_CORE_ITS &&
	     extent.kind != KD_GENERATED_TEXT_MODULE_ITS) ||
	    !extent.start || (extent.start & (PAGE_SIZE - 1)) ||
	    extent.end <= extent.start ||
	    extent.end - extent.start != PAGE_SIZE ||
	    address < extent.start || address >= extent.end ||
	    (extent.kind == KD_GENERATED_TEXT_CORE_ITS && extent.owner) ||
	    (extent.kind == KD_GENERATED_TEXT_MODULE_ITS && !extent.owner))
		goto drop_reply;
	if (!extent.owner) {
		*end = extent.end;
		return 0;
	}
	ret = -ESTALE;
	if (READ_ONCE(extent.owner->state) != MODULE_STATE_LIVE)
		goto drop_reply;
	for (owner_index = 0; owner_index < kd_sources.modules; owner_index++) {
		if (kd_source_modules[owner_index] == extent.owner) {
			*end = extent.end;
			ret = 0;
			goto drop_reply;
		}
	}
	ret = -ENOSPC;
	if (kd_sources.modules >= KD_SOURCE_MAX_MODULES)
		goto drop_reply;
	kd_source_modules[kd_sources.modules++] = extent.owner;
	*end = extent.end;
	return 0;

drop_reply:
	if (extent.owner)
		module_put(extent.owner);
	return ret;
}

/* The raw lock keeps preemption disabled through lookup and try_module_get.
 * Read windows may include core rodata; roots/continuations require text. */
static int kd_source_piece(unsigned long address, bool text, unsigned long *end)
{
	struct module *module;
	unsigned long base, size;
	enum mod_mem_type type;
	unsigned int i;

	if (address >= kd_core_start && address < kd_core_end) {
		if ((address >= kd_init_start && address < kd_init_end) ||
		    (text && address >= kd_core_text_end))
			return -EPERM;
		*end = address < kd_init_start ? kd_init_start : kd_core_end;
		return 0;
	}
	module = kd_module_address(address);
	if (!module)
		return kd_source_generated_piece(address, end);
	if (READ_ONCE(module->state) != MODULE_STATE_LIVE)
		return -ESTALE;
	/* Module regions are separate allocations. Never bridge a hole or an init
	 * region by treating them as one interval; executable targets need MOD_TEXT.
	 * The live module reference below retains every accepted core region. */
	for (type = MOD_TEXT; type < MOD_MEM_NUM_TYPES; type++) {
		if (mod_mem_type_is_init(type) || (text && type != MOD_TEXT))
			continue;
		base = (unsigned long)module->mem[type].base;
		size = module->mem[type].size;
		if (address >= base && address - base < size)
			break;
	}
	if (type == MOD_MEM_NUM_TYPES)
		return -EPERM;
	*end = base + size;
	if (*end <= address)
		return -EOVERFLOW;
	for (i = 0; i < kd_sources.modules; i++)
		if (kd_source_modules[i] == module)
			return 0;
	if (kd_sources.modules == KD_SOURCE_MAX_MODULES)
		return -ENOSPC;
	if (!try_module_get(module))
		return -ESTALE;
	kd_source_modules[kd_sources.modules++] = module;
	return 0;
}

static int kd_source_pin(unsigned long address, unsigned long size, bool text,
			 enum kd_source_scope scope)
{
	/* All address range checks happen under the source lock to coordinate with
	 * retire transitions and pin state changes.
	 */
	unsigned long flags, cursor = address, limit;
	int ret = 0;

	if (!size || size > KD_SOURCE_MAX_READ || address + size < address)
		return -EINVAL;
	limit = address + size;
	raw_spin_lock_irqsave(&kd_source_lock, flags);
	if (kd_sources.state == KD_SOURCE_RETIRED ||
	    (scope == KD_SOURCE_ROOT && kd_sources.state != KD_SOURCE_OPEN) ||
	    (scope == KD_SOURCE_WRITER && !kd_sources.writers) ||
	    (scope == KD_SOURCE_FRAME && !kd_source_frame_count())) {
		ret = -ESHUTDOWN;
		goto out;
	}
	while (cursor < limit) {
		unsigned long end = cursor;

		ret = kd_source_piece(cursor, text, &end);
		if (ret)
			break;
		if (end <= cursor) {
			ret = -EPROTO;
			break;
		}
		cursor = min(end, limit);
	}
out:
	/* Partial failures retain pins used by older images. Existing writer/frame
	 * holders may finish while admission is draining; release needs zero users. */
	raw_spin_unlock_irqrestore(&kd_source_lock, flags);
	return ret;
}

int kd_source_pin_root(unsigned long address)
{
	return kd_source_pin(address, 1, true, KD_SOURCE_ROOT);
}

int kd_source_pin_range(unsigned long address, unsigned long size)
{
	return kd_source_pin(address, size, false, KD_SOURCE_WRITER);
}

int kd_source_pin_target(unsigned long address)
{
	return kd_source_pin(address, 1, true, KD_SOURCE_FRAME);
}

void kd_source_info(struct kd_source_info *info)
{
	unsigned long flags;

	raw_spin_lock_irqsave(&kd_source_lock, flags);
	*info = kd_sources;
	info->frames = kd_source_frame_count();
	raw_spin_unlock_irqrestore(&kd_source_lock, flags);
}

int kd_source_begin_retire(void)
{
	/* Live bound objects still need future frame admission. Their factory
	 * leases arbitrate with closure here; returning busy must leave them open.
	 * With no bindings, close before testing transient frame/writer drain. */
	unsigned long flags;
	int ret = 0;

	raw_spin_lock_irqsave(&kd_source_lock, flags);
	if (kd_source_bindings) {
		raw_spin_unlock_irqrestore(&kd_source_lock, flags);
		return -EBUSY;
	}
	atomic64_fetch_or(KD_SOURCE_FRAME_CLOSED, &kd_source_frame_gate);
	if (kd_sources.state != KD_SOURCE_RETIRED)
		WRITE_ONCE(kd_sources.state, KD_SOURCE_DRAINING);
	if (kd_source_frame_count() || kd_sources.writers)
		ret = -EBUSY;
	raw_spin_unlock_irqrestore(&kd_source_lock, flags);
	return ret;
}

void kd_source_finish_retire(void)
{
	struct module *modules[KD_SOURCE_MAX_MODULES];
	unsigned long flags;
	unsigned int count, i;

	/* The publisher first invalidates entries under the registry gate. Never
	 * hold this source lock while waiting for that gate or dropping modules. */
	raw_spin_lock_irqsave(&kd_source_lock, flags);
	BUG_ON(kd_sources.state == KD_SOURCE_OPEN || kd_source_frame_count() ||
	       kd_sources.writers || kd_source_bindings);
	count = kd_sources.modules;
	memcpy(modules, kd_source_modules, count * sizeof(modules[0]));
	memset(kd_source_modules, 0, sizeof(kd_source_modules));
	kd_sources.modules = 0;
	WRITE_ONCE(kd_sources.state, KD_SOURCE_RETIRED);
	raw_spin_unlock_irqrestore(&kd_source_lock, flags);
	for (i = 0; i < count; i++)
		module_put(modules[i]);
}

int kd_source_init(void)
{
	/* Cache core/module boundaries once so hot paths do not repeatedly query
	 * kallsyms while servicing lock events.
	 */
	kd_module_address = (void *)kallsyms_lookup_name("__module_address");
	kd_core_start = kallsyms_lookup_name("_stext");
	kd_core_text_end = kallsyms_lookup_name("_etext");
	kd_core_end = kallsyms_lookup_name("_end");
	kd_init_start = kallsyms_lookup_name("__init_begin");
	kd_init_end = kallsyms_lookup_name("__init_end");
	kd_generated_lookup = (void *)kallsyms_lookup_name("kd_generated_text_lookup");
	if (!kd_module_address || !kd_core_start ||
	    kd_core_start >= kd_core_text_end ||
	    kd_core_text_end > kd_init_start || kd_init_start >= kd_init_end ||
	    kd_init_end > kd_core_end)
		return -EOPNOTSUPP;
	/* This optional callback belongs to the built-in producer and cannot outlive
	 * its own code. Older kernels keep the existing explicit source refusal. */
	if (kd_generated_lookup &&
	    ((unsigned long)kd_generated_lookup < kd_core_start ||
	     (unsigned long)kd_generated_lookup >= kd_core_text_end))
		return -EOPNOTSUPP;
	memset(&kd_sources, 0, sizeof(kd_sources));
	atomic64_set(&kd_source_frame_gate, 0);
	kd_source_bindings = 0;
	memset(kd_source_modules, 0, sizeof(kd_source_modules));
	return 0;
}

void kd_source_exit(void)
{
	/* Normal unload cannot pass source/self pins. A used session retires
	 * explicitly; an unused or init-failed session has no dependencies. */
	BUG_ON(kd_source_begin_retire());
	kd_source_finish_retire();
}
