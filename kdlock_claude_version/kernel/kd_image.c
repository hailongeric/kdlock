// SPDX-License-Identifier: GPL-2.0
/*
 * kdlock generated-code management.
 *
 * A "site" is the return address of a delegable lock call; the code that
 * follows it is the critical section. The userspace translator builds one
 * image per site: a relocated copy of the section, linked for the address
 * handed out by KD_IOC_IMAGE_ALLOC.
 *
 * Lifetime: a waiter looks its site up with preemption disabled and stays
 * that way until it resumes; the combiner runs images with preemption
 * disabled. So a site or image that has been unpublished is unreachable
 * after one RCU grace period, and publication needs no reference counts.
 *
 * Learning: generated code reports branch targets it does not know. The
 * reports go into a lossy ring that the translator drains; the current
 * invocation never waits for them, it is handed back to its origin.
 *
 * Text lifetime: an image is a copy of kernel or module text and may hold
 * that text's addresses (return addresses, compare chains, rip-relative
 * data). When module text goes away every site is dropped, since any image
 * may contain code copied from it, and kd_text_gen moves on so that an
 * image built from the old text cannot be loaded afterwards.
 */
#include <linux/kernel.h>
#include <linux/slab.h>
#include <linux/hash.h>
#include <linux/rculist.h>
#include <linux/mutex.h>
#include <linux/uaccess.h>
#include <linux/execmem.h>
#include <linux/set_memory.h>
#include <linux/smp.h>
#include <linux/mm.h>
#include <linux/random.h>
#include <asm/current.h>
#include <asm/processor.h>
#include <linux/stackprotector.h>
#include <linux/module.h>
#include <linux/extable.h>
#include <linux/notifier.h>
#include <asm/sections.h>
#include <asm/stackprotector.h>
#include "kd_internal.h"

#define KD_SITE_BITS		10
#define KD_IMAGE_MAX		(8UL << 20)
#define KD_MISS_BUDGET		64	/* learning reports per published image */
#define KD_SITE_WINDOW		256	/* executions between usefulness checks */
#define KD_REQ_BITS		10
#define KD_REQ_THRESHOLD	64	/* contended waits before a site is requested */
#define KD_REQ_REPEAT		4096	/* ... and again every this many (power of two) */
#define KD_RING_SIZE		4096	/* power of two */

struct kd_image {
	struct list_head link;
	void		*text;
	size_t		size;
	u32		id;
	bool		loaded;
};

static struct hlist_head kd_sites[1 << KD_SITE_BITS];
static LIST_HEAD(kd_images);		/* allocated, not yet attached to a site */
static DEFINE_MUTEX(kd_image_mutex);	/* serialises all publication */
static u32 kd_next_id = 1;
static u32 kd_text_gen = 1;		/* under kd_image_mutex */

extern struct exception_table_entry __start___ex_table[], __stop___ex_table[];

/* ---- site lookup (waiter side, any context, preemption off) ----------------- */

struct kd_site *kd_site_find(unsigned long rip)
{
	struct kd_site *s;

	hlist_for_each_entry_rcu(s, &kd_sites[hash_long(rip, KD_SITE_BITS)], hash,
				 true) {
		if (s->rip == rip)
			return s;
	}
	return NULL;
}

/*
 * Count contended waits at sites without an image and ask the translator
 * for the hot ones. Direct-mapped and unsynchronised on purpose: this runs
 * inside arbitrary lock slow paths, so it must not allocate or lock, and a
 * lost or duplicated request only delays or repeats a compile. The request
 * repeats while the site stays without an image, so a request lost in the
 * event ring (or sent while no translator ran) is not final.
 */
static struct {
	unsigned long	rip;
	u32		count;
} kd_req[1 << KD_REQ_BITS];

void kd_site_request(unsigned long rip)
{
	typeof(&kd_req[0]) e = &kd_req[hash_long(rip, KD_REQ_BITS)];
	u32 n;

	if (READ_ONCE(e->rip) != rip) {
		WRITE_ONCE(e->rip, rip);
		WRITE_ONCE(e->count, 0);
	}
	n = READ_ONCE(e->count) + 1;
	WRITE_ONCE(e->count, n);
	if ((n & (KD_REQ_REPEAT - 1)) == KD_REQ_THRESHOLD)
		kd_event_push(KD_EV_REQUEST, rip, rip, 0);
}

/*
 * Combiner-side accounting. A site whose sections are mostly handed back
 * costs more than it saves, so it is switched off until the translator
 * publishes a better image. Counters are approximate by design.
 */
void kd_site_account(struct kd_site *site, bool done)
{
	u32 ok, bad;

	if (done)
		WRITE_ONCE(site->ok, site->ok + 1);
	else
		WRITE_ONCE(site->bad, site->bad + 1);
	ok = READ_ONCE(site->ok);
	bad = READ_ONCE(site->bad);
	if (ok + bad < KD_SITE_WINDOW)
		return;
	WRITE_ONCE(site->ok, 0);
	WRITE_ONCE(site->bad, 0);
	if (bad > ok && READ_ONCE(site->entry)) {
		WRITE_ONCE(site->entry, NULL);
		kd_event_push(KD_EV_SITE_OFF, site->rip, site->rip, bad);
	}
}

/* ---- event ring ------------------------------------------------------------- */

struct kd_ring_slot {
	atomic_long_t	seq;		/* index + 1 once the slot is complete */
	struct kd_event	ev;
};

static struct kd_ring_slot kd_ring[KD_RING_SIZE];
static atomic_long_t kd_ring_head;
static unsigned long kd_ring_tail;	/* reader only, under kd_image_mutex */

/* Any context. Overwrites the oldest entries when the reader is slow. */
void kd_event_push(u32 type, unsigned long site, unsigned long ip, unsigned long target)
{
	unsigned long idx = atomic_long_fetch_inc(&kd_ring_head);
	struct kd_ring_slot *s = &kd_ring[idx & (KD_RING_SIZE - 1)];

	atomic_long_set(&s->seq, 0);
	s->ev.type = type;
	s->ev.cpu = raw_smp_processor_id();
	s->ev.site = site;
	s->ev.ip = ip;
	s->ev.target = target;
	atomic_long_set_release(&s->seq, idx + 1);
}

ssize_t kd_event_read(char __user *buf, size_t len)
{
	unsigned long head;
	ssize_t done = 0;

	mutex_lock(&kd_image_mutex);
	head = atomic_long_read(&kd_ring_head);
	if (head - kd_ring_tail > KD_RING_SIZE)
		kd_ring_tail = head - KD_RING_SIZE;

	while (kd_ring_tail != head && len - done >= sizeof(struct kd_event)) {
		struct kd_ring_slot *s = &kd_ring[kd_ring_tail & (KD_RING_SIZE - 1)];
		struct kd_event ev;

		/* Copy between two matching sequence reads, or skip the slot. */
		if (atomic_long_read_acquire(&s->seq) == kd_ring_tail + 1) {
			ev = s->ev;
			if (atomic_long_read(&s->seq) == kd_ring_tail + 1) {
				if (copy_to_user(buf + done, &ev, sizeof(ev))) {
					done = done ? done : -EFAULT;
					break;
				}
				done += sizeof(ev);
			}
		}
		kd_ring_tail++;
	}
	mutex_unlock(&kd_image_mutex);
	return done;
}

/* ---- images ----------------------------------------------------------------- */

static void kd_image_free(struct kd_image *img)
{
	if (!img)
		return;
	execmem_free(img->text);
	kfree(img);
}

/*
 * Reserve executable address space so the translator can link the image
 * for its final address. The memory stays writable until it is loaded.
 *
 * EXECMEM_BPF is used because, like a BPF program, an image is written
 * once while still RW and then switched to ROX; it also places the image
 * within rel32 range of kernel text, which the generated code relies on.
 */
static long kd_image_alloc(struct kd_image_alloc __user *uarg)
{
	struct kd_image_alloc a;
	struct kd_image *img;

	if (copy_from_user(&a, uarg, sizeof(a)))
		return -EFAULT;
	if (!a.size || a.size > KD_IMAGE_MAX)
		return -EINVAL;

	img = kzalloc(sizeof(*img), GFP_KERNEL);
	if (!img)
		return -ENOMEM;
	img->size = PAGE_ALIGN(a.size);
	img->text = execmem_alloc(EXECMEM_BPF, img->size);
	if (!img->text) {
		kfree(img);
		return -ENOMEM;
	}

	mutex_lock(&kd_image_mutex);
	img->id = kd_next_id++;
	list_add(&img->link, &kd_images);
	mutex_unlock(&kd_image_mutex);

	a.base = (unsigned long)img->text;
	a.id = img->id;
	if (copy_to_user(uarg, &a, sizeof(a)))
		return -EFAULT;	/* the image stays listed and is reaped on reuse */
	return 0;
}

/*
 * Text region holding addr: core kernel text, or the text (or init text)
 * of a module that is not going away. Called under kd_image_mutex: the
 * module notifier needs that mutex before the module's memory is freed,
 * so a module seen live here stays mapped until the mutex is released.
 */
static bool kd_text_region(unsigned long addr, unsigned long *start,
			   unsigned long *end, struct module **modp)
{
	static const enum mod_mem_type types[] = { MOD_TEXT, MOD_INIT_TEXT };
	struct module *mod;
	unsigned int i;

	lockdep_assert_held(&kd_image_mutex);
	*modp = NULL;
	if (__is_kernel_text(addr)) {
		*start = (unsigned long)_stext;
		*end = (unsigned long)_etext;
		return true;
	}
	guard(rcu)();
	mod = __module_text_address(addr);
	if (!mod || !module_is_live(mod))
		return false;
	for (i = 0; i < ARRAY_SIZE(types); i++) {
		struct module_memory *m = &mod->mem[types[i]];
		unsigned long b = (unsigned long)m->base;

		/* Init text is freed once the module is live. */
		if (types[i] == MOD_INIT_TEXT && mod->state != MODULE_STATE_COMING)
			continue;

		if (m->size && addr >= b && addr < b + m->size) {
			*start = b;
			*end = b + m->size;
			*modp = mod;
			return true;
		}
	}
	return false;
}

/*
 * Fill a reserved image and publish it for its site. The entry pointer is
 * the single publication point: waiters either see the old complete image
 * or the new complete image. The old one is freed after a grace period,
 * when no waiter that looked it up can still be queued or executing.
 *
 * The image is refused when text changed since the translator read it
 * (-ESTALE) or when the site is not in live text. A refused or failed
 * image is freed here; the translator allocates a new one to retry.
 */
static long kd_image_load(struct kd_image_load __user *uarg)
{
	struct kd_image_load l;
	struct kd_image *img = NULL, *it, *old = NULL;
	struct kd_site *site;
	unsigned long start, end;
	struct module *mod;
	long ret = 0;

	if (copy_from_user(&l, uarg, sizeof(l)))
		return -EFAULT;

	mutex_lock(&kd_image_mutex);
	list_for_each_entry(it, &kd_images, link) {
		if (it->id == l.id) {
			img = it;
			break;
		}
	}
	if (!img) {
		ret = -EINVAL;
		goto out;
	}
	/* From here on the image belongs to this call. */
	list_del(&img->link);
	if (l.len > img->size || l.entry_off >= l.len) {
		ret = -EINVAL;
		goto out;
	}
	if (l.gen != kd_text_gen) {
		ret = -ESTALE;
		goto out;
	}
	if (!kd_text_region(l.site, &start, &end, &mod)) {
		ret = -ENOENT;
		goto out;
	}
	if (copy_from_user(img->text, u64_to_user_ptr(l.buf), l.len)) {
		ret = -EFAULT;
		goto out;
	}
	/* Pad with int3 so a stray jump stops immediately. */
	memset(img->text + l.len, 0xcc, img->size - l.len);
	ret = set_memory_rox((unsigned long)img->text, img->size >> PAGE_SHIFT);
	if (ret)
		goto out;
	img->loaded = true;

	site = kd_site_find(l.site);
	if (!site) {
		site = kzalloc(sizeof(*site), GFP_KERNEL);
		if (!site) {
			ret = -ENOMEM;
			goto out;
		}
		site->rip = l.site;
		hlist_add_head_rcu(&site->hash,
				   &kd_sites[hash_long(l.site, KD_SITE_BITS)]);
	}
	old = site->img;
	site->img = img;
	img = NULL;
	WRITE_ONCE(site->ok, 0);
	WRITE_ONCE(site->bad, 0);
	atomic_set(&site->miss_budget, KD_MISS_BUDGET);
	atomic_set(&site->hb_budget, 256);
	smp_store_release(&site->entry, site->img->text + l.entry_off);
out:
	mutex_unlock(&kd_image_mutex);
	/* Never published: nobody can be running it. */
	kd_image_free(img);
	if (old) {
		synchronize_rcu();
		kd_image_free(old);
	}
	return ret;
}

/*
 * Text [start, end) is about to go away. Unpublish every image, wait until
 * no waiter can still be queued on or executing one, free them all, and
 * tell the translator. Requests restart from zero so busy sites ask again.
 */
static void kd_text_gone(unsigned long start, unsigned long end)
{
	struct kd_site *s;
	struct hlist_node *tmp;
	unsigned int b;
	u32 gen;

	mutex_lock(&kd_image_mutex);
	gen = ++kd_text_gen;
	for (b = 0; b < ARRAY_SIZE(kd_sites); b++)
		hlist_for_each_entry(s, &kd_sites[b], hash)
			WRITE_ONCE(s->entry, NULL);
	/* Waiters hold preemption off from lookup until they resume. */
	synchronize_rcu();
	for (b = 0; b < ARRAY_SIZE(kd_sites); b++) {
		hlist_for_each_entry_safe(s, tmp, &kd_sites[b], hash) {
			hlist_del_rcu(&s->hash);
			kd_image_free(s->img);
			kfree_rcu(s, rcu);
		}
	}
	memset(kd_req, 0, sizeof(kd_req));
	kd_event_push(KD_EV_TEXT_GONE, start, end, gen);
	mutex_unlock(&kd_image_mutex);
}

static int kd_module_notify(struct notifier_block *nb, unsigned long action,
			    void *data)
{
	struct module *mod = data;
	struct module_memory *m;

	switch (action) {
	case MODULE_STATE_COMING:
		/* New text and symbols: the translator must reread them. */
		mutex_lock(&kd_image_mutex);
		kd_text_gen++;
		mutex_unlock(&kd_image_mutex);
		break;
	case MODULE_STATE_LIVE:
		/* Init text is freed after this notification. */
		m = &mod->mem[MOD_INIT_TEXT];
		if (m->size)
			kd_text_gone((unsigned long)m->base,
				     (unsigned long)m->base + m->size);
		break;
	case MODULE_STATE_GOING:
		m = &mod->mem[MOD_TEXT];
		kd_text_gone((unsigned long)m->base, (unsigned long)m->base + m->size);
		break;
	}
	return NOTIFY_OK;
}

static struct notifier_block kd_module_nb = {
	.notifier_call = kd_module_notify,
};

static int __init kd_image_init(void)
{
	return register_module_notifier(&kd_module_nb);
}
device_initcall(kd_image_init);

static long kd_site_drop(struct kd_site_ctl __user *uarg)
{
	struct kd_site_ctl c;
	struct kd_site *site;
	struct kd_image *img = NULL;

	if (copy_from_user(&c, uarg, sizeof(c)))
		return -EFAULT;

	mutex_lock(&kd_image_mutex);
	site = kd_site_find(c.site);
	if (site) {
		WRITE_ONCE(site->entry, NULL);
		hlist_del_rcu(&site->hash);
		img = site->img;
	}
	mutex_unlock(&kd_image_mutex);
	if (!site)
		return -ENOENT;
	synchronize_rcu();
	kd_image_free(img);
	kfree(site);
	return 0;
}

/* ---- translator support ----------------------------------------------------- */

static long kd_read_kernel(struct kd_read_req __user *uarg)
{
	struct kd_read_req r;
	u8 chunk[256];
	u64 off = 0;

	if (copy_from_user(&r, uarg, sizeof(r)))
		return -EFAULT;
	if (r.len > (1 << 20))
		return -EINVAL;
	while (off < r.len) {
		size_t n = min_t(u64, sizeof(chunk), r.len - off);

		if (copy_from_kernel_nofault(chunk, (void *)(unsigned long)(r.addr + off), n))
			return -EFAULT;
		if (copy_to_user(u64_to_user_ptr(r.buf + off), chunk, n))
			return -EFAULT;
		off += n;
	}
	return 0;
}

/*
 * Report the text region holding q.addr and the instructions in it that
 * have exception-table entries (see struct kd_text_query).
 */
static long kd_text_query(struct kd_text_query __user *uarg)
{
	const struct exception_table_entry *ex = NULL;
	struct kd_text_query q;
	unsigned long start = 0, end = 0;
	struct module *mod;
	unsigned int i, num = 0;
	u64 __user *out;
	long ret = 0;

	if (copy_from_user(&q, uarg, sizeof(q)))
		return -EFAULT;
	out = u64_to_user_ptr(q.buf);
	q.count = 0;

	mutex_lock(&kd_image_mutex);
	q.gen = kd_text_gen;
	if (q.addr && kd_text_region(q.addr, &start, &end, &mod)) {
		if (mod) {
			ex = mod->extable;
			num = mod->num_exentries;
		} else {
			ex = __start___ex_table;
			num = __stop___ex_table - __start___ex_table;
		}
	}
	for (i = 0; i < num; i++) {
		unsigned long insn = (unsigned long)&ex[i].insn + ex[i].insn;

		if (insn < start || insn >= end)
			continue;
		if (q.count < q.max && put_user(insn, out + q.count)) {
			ret = -EFAULT;
			break;
		}
		q.count++;
	}
	mutex_unlock(&kd_image_mutex);
	q.start = start;
	q.end = end;
	if (!ret && copy_to_user(uarg, &q, sizeof(q)))
		ret = -EFAULT;
	return ret;
}

#define KD_PCPU(field)	((unsigned long)&kd_cpu + offsetof(struct kd_cpu, field))

#define KD_SYM(fn, c, o) \
	{ .addr = (unsigned long)(fn), .cls = (c), .op = (o) }
#define KD_SYM_NEST(fn, o) \
	{ .addr = (unsigned long)(fn), .alt = (unsigned long)(fn##_jit), \
	  .cls = KD_SYM_NESTED, .op = (o) }

/*
 * The kd_ functions generated code may meet, by class (kd_uapi.h).
 * Spin-class acquires are called through their _jit entry, which leaves
 * generated code only when contended. KD_SYM_LOCAL functions never sleep
 * and act for the origin through kd_logical_current(), so the copy calls
 * them natively. A kd_ function that is not listed here is a frontier.
 */
static const struct kd_sym kd_syms[] = {
	KD_SYM(kd_spin_unlock,			KD_SYM_UNLOCK,	KD_OP_UNLOCK),
	KD_SYM(kd_spin_unlock_irq,		KD_SYM_UNLOCK,	KD_OP_UNLOCK_IRQ),
	KD_SYM(kd_spin_unlock_irqrestore,	KD_SYM_UNLOCK,	KD_OP_UNLOCK_IRQRESTORE),
	KD_SYM(kd_spin_unlock_bh,		KD_SYM_UNLOCK,	KD_OP_UNLOCK_BH),
	KD_SYM(kd_write_unlock,			KD_SYM_UNLOCK,	KD_OP_UNLOCK),
	KD_SYM(kd_write_unlock_irq,		KD_SYM_UNLOCK,	KD_OP_UNLOCK_IRQ),
	KD_SYM(kd_write_unlock_irqrestore,	KD_SYM_UNLOCK,	KD_OP_UNLOCK_IRQRESTORE),
	KD_SYM(kd_write_unlock_bh,		KD_SYM_UNLOCK,	KD_OP_UNLOCK_BH),
	KD_SYM(kd_mutex_unlock,			KD_SYM_UNLOCK,	KD_OP_UNLOCK_SLEEPABLE),
	KD_SYM(kd_up_write,			KD_SYM_UNLOCK,	KD_OP_UNLOCK_SLEEPABLE),
	KD_SYM(kd_downgrade_write,		KD_SYM_UNLOCK,	KD_OP_DOWNGRADE),
	KD_SYM(kd_mutex_lock,			KD_SYM_ACQUIRE,	KD_OP_MUTEX_LOCK),
	KD_SYM(kd_mutex_lock_interruptible,	KD_SYM_ACQUIRE,	KD_OP_MUTEX_LOCK),
	KD_SYM(kd_mutex_lock_killable,		KD_SYM_ACQUIRE,	KD_OP_MUTEX_LOCK),
	KD_SYM(kd_mutex_lock_io,		KD_SYM_ACQUIRE,	KD_OP_MUTEX_LOCK),
	KD_SYM(kd_down_read,			KD_SYM_ACQUIRE,	KD_OP_DOWN_READ),
	KD_SYM(kd_down_read_interruptible,	KD_SYM_ACQUIRE,	KD_OP_DOWN_READ),
	KD_SYM(kd_down_read_killable,		KD_SYM_ACQUIRE,	KD_OP_DOWN_READ),
	KD_SYM(kd_down_write,			KD_SYM_ACQUIRE,	KD_OP_DOWN_WRITE),
	KD_SYM(kd_down_write_killable,		KD_SYM_ACQUIRE,	KD_OP_DOWN_WRITE),
	KD_SYM_NEST(kd_spin_lock,		KD_OP_NEST_SPIN),
	KD_SYM_NEST(kd_spin_lock_irq,		KD_OP_NEST_SPIN),
	KD_SYM_NEST(kd_spin_lock_irqsave,	KD_OP_NEST_SPIN),
	KD_SYM_NEST(kd_spin_lock_bh,		KD_OP_NEST_SPIN),
	KD_SYM_NEST(kd_write_lock,		KD_OP_NEST_WRITE),
	KD_SYM_NEST(kd_write_lock_irq,		KD_OP_NEST_WRITE),
	KD_SYM_NEST(kd_write_lock_irqsave,	KD_OP_NEST_WRITE),
	KD_SYM_NEST(kd_write_lock_bh,		KD_OP_NEST_WRITE),
	/* Spin without publishing, or do not wait at all. */
	KD_SYM(kd_raw_spin_lock,		KD_SYM_LOCAL,	0),
	KD_SYM(kd_raw_spin_lock_irq,		KD_SYM_LOCAL,	0),
	KD_SYM(kd_raw_spin_lock_irqsave,	KD_SYM_LOCAL,	0),
	KD_SYM(kd_raw_spin_lock_bh,		KD_SYM_LOCAL,	0),
	KD_SYM(kd_arch_spin_lock,		KD_SYM_LOCAL,	0),
	KD_SYM(kd_spin_trylock,			KD_SYM_LOCAL,	0),
	KD_SYM(kd_spin_trylock_bh,		KD_SYM_LOCAL,	0),
	KD_SYM(kd_spin_trylock_irq,		KD_SYM_LOCAL,	0),
	KD_SYM(kd_spin_trylock_irqsave,		KD_SYM_LOCAL,	0),
	KD_SYM(kd_write_trylock,		KD_SYM_LOCAL,	0),
	KD_SYM(kd_write_trylock_irqsave,	KD_SYM_LOCAL,	0),
	KD_SYM(kd_arch_write_lock,		KD_SYM_LOCAL,	0),
	KD_SYM(kd_read_lock,			KD_SYM_LOCAL,	0),
	KD_SYM(kd_read_lock_irq,		KD_SYM_LOCAL,	0),
	KD_SYM(kd_read_lock_irqsave,		KD_SYM_LOCAL,	0),
	KD_SYM(kd_read_lock_bh,			KD_SYM_LOCAL,	0),
	KD_SYM(kd_arch_read_lock,		KD_SYM_LOCAL,	0),
	KD_SYM(kd_read_trylock,			KD_SYM_LOCAL,	0),
	KD_SYM(kd_read_unlock,			KD_SYM_LOCAL,	0),
	KD_SYM(kd_read_unlock_irq,		KD_SYM_LOCAL,	0),
	KD_SYM(kd_read_unlock_irqrestore,	KD_SYM_LOCAL,	0),
	KD_SYM(kd_read_unlock_bh,		KD_SYM_LOCAL,	0),
	KD_SYM(kd_mutex_trylock,		KD_SYM_LOCAL,	0),
	KD_SYM(kd_mutex_get_owner,		KD_SYM_LOCAL,	0),
	KD_SYM(kd_ww_mutex_trylock,		KD_SYM_LOCAL,	0),
	KD_SYM(kd_ww_mutex_unlock,		KD_SYM_LOCAL,	0),
	KD_SYM(kd_down_read_trylock,		KD_SYM_LOCAL,	0),
	KD_SYM(kd_down_write_trylock,		KD_SYM_LOCAL,	0),
	KD_SYM(kd_up_read,			KD_SYM_LOCAL,	0),
};
static_assert(ARRAY_SIZE(kd_syms) <= KD_MAX_SYMS);

static long kd_get_info(struct kd_info __user *uarg)
{
	struct kd_info *info;
	long ret = 0;

	info = kzalloc(sizeof(*info), GFP_KERNEL);
	if (!info)
		return -ENOMEM;
	info->abi = KD_ABI_VERSION;
	info->jit_exit = (unsigned long)kd_jit_exit;
	info->pcpu_task = KD_PCPU(task);
	info->pcpu_canary = KD_PCPU(canary);
	info->pcpu_stack_top = KD_PCPU(stack_top);
	info->pcpu_root = KD_PCPU(root);
	info->pcpu_exit_ip = KD_PCPU(exit_ip);
	info->pcpu_resume = KD_PCPU(resume);
	info->pcpu_aux = KD_PCPU(aux);
	info->pcpu_exit_code = KD_PCPU(exit_code);
	info->pcpu_anc = KD_PCPU(anc);
	info->src_current_task = (unsigned long)&current_task;
#ifdef CONFIG_STACKPROTECTOR
	info->src_stack_canary = (unsigned long)&__stack_chk_guard;
#endif
	info->src_stack_top = (unsigned long)&cpu_current_top_of_stack;
	info->nr_syms = ARRAY_SIZE(kd_syms);
	memcpy(info->syms, kd_syms, sizeof(kd_syms));

	if (copy_to_user(uarg, info, sizeof(*info)))
		ret = -EFAULT;
	kfree(info);
	return ret;
}

static long kd_set_enable(u32 __user *uarg)
{
	u32 on;

	if (get_user(on, uarg))
		return -EFAULT;
	if (on)
		static_branch_enable(&kd_delegation);
	else
		static_branch_disable(&kd_delegation);
	return 0;
}

long kd_image_ioctl(unsigned int cmd, unsigned long arg)
{
	void __user *uarg = (void __user *)arg;

	switch (cmd) {
	case KD_IOC_INFO:
		return kd_get_info(uarg);
	case KD_IOC_READ:
		return kd_read_kernel(uarg);
	case KD_IOC_IMAGE_ALLOC:
		return kd_image_alloc(uarg);
	case KD_IOC_IMAGE_LOAD:
		return kd_image_load(uarg);
	case KD_IOC_SITE_DROP:
		return kd_site_drop(uarg);
	case KD_IOC_ENABLE:
		return kd_set_enable(uarg);
	case KD_IOC_TEXT:
		return kd_text_query(uarg);
	}
	return -ENOTTY;
}
