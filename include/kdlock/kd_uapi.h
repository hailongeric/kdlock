/* SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note */
/*
 * Interface between the kdlock core and the userspace translator
 * (/dev/kdlock). jit/kdjit/kernel.py mirrors these layouts; change both.
 */
#ifndef _KDLOCK_KD_UAPI_H
#define _KDLOCK_KD_UAPI_H

#include <linux/types.h>
#include <linux/ioctl.h>

#define KD_ABI_VERSION		4

/* ---- exit codes written by generated code ----------------------------- */

/* kind: bits 0-7 */
#define KD_X_UNLOCK		1	/* call to a release API with rdi == session root */
#define KD_X_ACQUIRE		2	/* call to a sleeping-family acquire API */
#define KD_X_MISS_CODE		3	/* direct target not in this image (learnable) */
#define KD_X_MISS_IND		4	/* indirect call/jmp target unknown (learnable) */
#define KD_X_MISS_RET		5	/* return target unknown (learnable) */
#define KD_X_FRONTIER		6	/* instruction or callee that only the origin may run */
#define KD_X_BUDGET		7	/* translator budget; not learnable */
#define KD_X_UNLOCK_ANC		8	/* release call, rdi != root, while outer sessions exist */
#define KD_X_NESTED		9	/* contended spin-class acquire inside a section */
#define KD_X_KIND(code)		((code) & 0xff)
/* op: bits 8-15, enum kd_op */
#define KD_X_OP(code)		(((code) >> 8) & 0xff)
/* The API was reached by a jmp (sibling call), not a call. */
#define KD_X_TAIL		0x10000
/*
 * The exit lies inside a per-CPU region the translator walked (an exit it
 * found only on a slow path of the region). kd_exec_one() counts it as
 * hb_region when it is taken with the region actually open.
 */
#define KD_X_REGION		0x20000

enum kd_op {
	KD_OP_NONE = 0,
	/* release operations (KD_SYM_UNLOCK) */
	KD_OP_UNLOCK,			/* spin/write unlock */
	KD_OP_UNLOCK_IRQ,
	KD_OP_UNLOCK_IRQRESTORE,
	KD_OP_UNLOCK_BH,
	KD_OP_UNLOCK_SLEEPABLE,		/* mutex_unlock, up_write */
	KD_OP_DOWNGRADE,		/* always handed back to the origin */
	/* acquire operations (KD_SYM_ACQUIRE) */
	KD_OP_MUTEX_LOCK,
	KD_OP_DOWN_READ,
	KD_OP_DOWN_WRITE,
	/* contended nested spin-class acquires (KD_SYM_NESTED) */
	KD_OP_NEST_SPIN,
	KD_OP_NEST_WRITE,
	/* release of the read side kept after a downgrade (KD_SYM_UNLOCK) */
	KD_OP_UP_READ,
};

/* ---- KD_IOC_INFO ------------------------------------------------------- */

/*
 * Every kd_ function generated code may meet is listed with its class. A
 * kd_ function that is not listed is a frontier: only the origin runs it.
 */
#define KD_SYM_UNLOCK		1	/* compare rdi with the session root before calling */
#define KD_SYM_ACQUIRE		2	/* always leave generated code */
#define KD_SYM_NESTED		3	/* call ->alt instead: same fast path, exits when contended */
#define KD_SYM_LOCAL		4	/* never sleeps and acts for the origin: call natively */
/*
 * As KD_SYM_UNLOCK, for a clobber release (kd_api.h): its callers keep only
 * rsp and rbp in registers across it, so when it ends the section the exit
 * may record just those (jit_exit_cl). As a sibling call it is a plain
 * KD_SYM_UNLOCK.
 */
#define KD_SYM_UNLOCK_CL	5

struct kd_sym {
	__u64 addr;
	__u64 alt;			/* KD_SYM_NESTED: entry to call from generated code */
	__u32 cls;
	__u32 op;
};

#define KD_MAX_SYMS		96

struct kd_info {
	__u32 abi;
	__u32 nr_syms;
	__u64 jit_exit;			/* kd_jit_exit: generated code jumps here to leave */
	/* GS-relative (per-CPU symbol) addresses generated code may use. */
	__u64 pcpu_task;		/* origin task, replaces current_task */
	__u64 pcpu_canary;		/* origin stack canary, replaces __stack_chk_guard */
	__u64 pcpu_stack_top;		/* origin stack top, replaces cpu_current_top_of_stack */
	__u64 pcpu_root;		/* lock whose release ends the delegated section */
	__u64 pcpu_exit_ip;
	__u64 pcpu_resume;
	__u64 pcpu_aux;
	__u64 pcpu_exit_code;
	/* Per-CPU symbols whose accesses are redirected to the fields above. */
	__u64 src_current_task;
	__u64 src_stack_canary;
	__u64 src_stack_top;
	__u64 pcpu_anc;			/* u32: number of outer session roots of the running section */
	__u64 jit_exit_cl;		/* kd_jit_exit_cl: exit at a clobber release ending the section */
	__u64 reserved[3];
	struct kd_sym syms[KD_MAX_SYMS];
};

/* ---- other ioctls ------------------------------------------------------ */

struct kd_read_req {
	__u64 addr;			/* kernel virtual address */
	__u64 len;
	__u64 buf;			/* user pointer */
};

struct kd_image_alloc {
	__u64 size;			/* in */
	__u64 base;			/* out: address the image will run at */
	__u32 id;			/* out */
	__u32 pad;
};

struct kd_image_load {
	__u32 id;
	__u32 gen;			/* KD_IOC_TEXT generation the image was built from */
	__u64 site;			/* return address of the root lock call */
	__u64 entry_off;		/* offset of the site's entry in the image */
	__u64 len;
	__u64 buf;			/* user pointer to image bytes */
};

struct kd_site_ctl {
	__u64 site;
};

/*
 * Text the translator may copy. Module load and unload change the set of
 * text regions and bump `gen`; an image built from older text is refused
 * (-ESTALE), because its copied instructions or symbols may be gone.
 *
 * For `addr`, returns the text region that holds it (core kernel text or
 * one module's text; start == end == 0 if none) and the addresses of every
 * instruction in that region that has an exception-table entry. Those
 * instructions rely on their own address and must never be copied.
 * `count` is the total; only min(count, max) are stored. addr == 0 only
 * reads `gen`.
 */
struct kd_text_query {
	__u64 addr;			/* in */
	__u64 buf;			/* in: user pointer to __u64[max] */
	__u32 max;			/* in */
	__u32 count;			/* out */
	__u64 start;			/* out */
	__u64 end;			/* out */
	__u32 gen;			/* out */
	__u32 pad;
};

#define KD_IOC_MAGIC		'K'
#define KD_IOC_INFO		_IOR(KD_IOC_MAGIC, 1, struct kd_info)
#define KD_IOC_READ		_IOW(KD_IOC_MAGIC, 2, struct kd_read_req)
#define KD_IOC_IMAGE_ALLOC	_IOWR(KD_IOC_MAGIC, 3, struct kd_image_alloc)
#define KD_IOC_IMAGE_LOAD	_IOW(KD_IOC_MAGIC, 4, struct kd_image_load)
#define KD_IOC_SITE_DROP	_IOW(KD_IOC_MAGIC, 5, struct kd_site_ctl)
#define KD_IOC_ENABLE		_IOW(KD_IOC_MAGIC, 6, __u32)
#define KD_IOC_TEXT		_IOWR(KD_IOC_MAGIC, 7, struct kd_text_query)

/* ---- events returned by read() ----------------------------------------- */

#define KD_EV_REQUEST		1	/* contended site without an image: ip = site */
#define KD_EV_MISS_CODE		2	/* ip = missing code address */
#define KD_EV_MISS_IND		3	/* ip = branch instruction, target = destination */
#define KD_EV_MISS_RET		4	/* ip = ret instruction, target = return address */
#define KD_EV_SITE_OFF		5	/* site disabled: handbacks dominate */
/*
 * Text [site, ip) went away (module unload, or module init text freed).
 * Every site was dropped, because any image may hold code copied from that
 * range; target = new text generation. Knowledge about the range is stale.
 */
#define KD_EV_TEXT_GONE		6
/*
 * A section was handed back for a reason the translator cannot learn
 * (frontier, sleeping acquire, downgrade): ip = first instruction not
 * executed, target = exit code. Diagnostic; 256 per image.
 */
#define KD_EV_HANDBACK		7

struct kd_event {
	__u32 type;
	__u32 cpu;
	__u64 site;
	__u64 ip;
	__u64 target;
};

#endif /* _KDLOCK_KD_UAPI_H */
