/* SPDX-License-Identifier: GPL-2.0 */
#ifndef LINUX_KD_MMAP_LOCK_H
#define LINUX_KD_MMAP_LOCK_H

#include <linux/kd_mmap_lock_types.h>
#include <asm/asm.h>

void kd_mmap_init(struct kd_mmap_lock *lock);
void kd_mmap_destroy(struct kd_mmap_lock *lock);
void kd_mmap_write_lock(struct kd_mmap_lock *lock);
void kd_mmap_write_lock_nested(struct kd_mmap_lock *lock, int subclass);
int kd_mmap_write_lock_killable(struct kd_mmap_lock *lock);
int kd_mmap_write_trylock(struct kd_mmap_lock *lock);
void kd_mmap_write_unlock(struct kd_mmap_lock *lock);
void kd_mmap_write_downgrade(struct kd_mmap_lock *lock);
void kd_mmap_read_lock(struct kd_mmap_lock *lock);
int kd_mmap_read_lock_killable(struct kd_mmap_lock *lock);
int kd_mmap_read_trylock(struct kd_mmap_lock *lock);
void kd_mmap_read_unlock(struct kd_mmap_lock *lock);
void kd_mmap_read_unlock_non_owner(struct kd_mmap_lock *lock);
bool kd_mmap_is_locked(struct kd_mmap_lock *lock);
bool kd_mmap_is_write_owner(struct kd_mmap_lock *lock);
bool kd_mmap_is_contended(struct kd_mmap_lock *lock);
void kd_mmap_assert_held(const struct kd_mmap_lock *lock);
void kd_mmap_assert_held_write(const struct kd_mmap_lock *lock);

void kd_mmap_write_lock_clobber_v1(struct kd_mmap_lock *lock,
	unsigned long sp, unsigned long ip, unsigned long bp);
int kd_mmap_write_lock_killable_clobber_v1(struct kd_mmap_lock *lock,
	unsigned long sp, unsigned long ip, unsigned long bp);
void kd_mmap_write_unlock_clobber_v1(struct kd_mmap_lock *lock,
	unsigned long sp, unsigned long ip, unsigned long bp);

/* Site records describe ordinary lock controls, independent of the function
 * or workload which contains them. Their entry is the caller's real frame. */
#define __KD_RWSEM_SITE_RECORD \
	".pushsection .kd_rwsem_sites,\"a\"\n\t.balign 8\n\t.quad 1b\n\t" \
	".long %c[kd_operation]\n\t.long 0\n\t.popsection\n\t"
#define __KD_MMAP_RWSEM_CALL(symbol, argument, operation, site_record) do { \
	__auto_type kd_argument = (argument); \
	struct kd_mmap_lock *kd_object = kd_argument; \
	unsigned long kd_sp, kd_ip, kd_bp; \
	asm volatile("movq %%rsp, %%rsi\n\t" \
		"leaq 1f(%%rip), %%rdx\n\t" \
		"movq %%rbp, %%rcx\n\tcall " #symbol "\n\t1:\n\t" site_record \
		: "+D"(kd_object), "=S"(kd_sp), "=d"(kd_ip), "=c"(kd_bp), \
		  ASM_CALL_CONSTRAINT : [kd_operation] "i"(operation) \
		: "rax", "rbx", "r8", "r9", "r10", "r11", \
		  "r12", "r13", "r14", "r15", "cc", "memory"); \
} while (0)
#define __KD_MMAP_RWSEM_RESULT_CALL(symbol, argument, operation) ({ \
	__auto_type kd_argument = (argument); \
	struct kd_mmap_lock *kd_object = kd_argument; \
	unsigned long kd_sp, kd_ip, kd_bp; \
	int kd_result; \
	asm volatile("movq %%rsp, %%rsi\n\t" \
		"leaq 1f(%%rip), %%rdx\n\t" \
		"movq %%rbp, %%rcx\n\tcall " #symbol "\n\t" \
		"jmp 2f\n\t1:\n\txorl %%eax, %%eax\n\t2:\n\t" __KD_RWSEM_SITE_RECORD \
		: "=a"(kd_result), "+D"(kd_object), "=S"(kd_sp), \
		  "=d"(kd_ip), "=c"(kd_bp), ASM_CALL_CONSTRAINT \
		: [kd_operation] "i"(operation) \
		: "rbx", "r8", "r9", "r10", "r11", \
		  "r12", "r13", "r14", "r15", "cc", "memory"); \
	kd_result; \
})

#ifndef KD_RWSEM_FACADE_IMPLEMENTATION
#define kd_mmap_write_lock(lock) \
	__KD_MMAP_RWSEM_CALL(kd_mmap_write_lock_clobber_v1, (lock), \
		KD_RWSEM_OP_DOWN_WRITE, __KD_RWSEM_SITE_RECORD)
/* Unsupported lockdep annotations confer no ownership and are not evaluated. */
#define kd_mmap_write_lock_nested(lock, subclass) kd_mmap_write_lock(lock)
#define kd_mmap_write_lock_killable(lock) \
	__KD_MMAP_RWSEM_RESULT_CALL(kd_mmap_write_lock_killable_clobber_v1, \
		(lock), KD_RWSEM_OP_DOWN_WRITE_KILLABLE)
#define kd_mmap_write_unlock(lock) \
	__KD_MMAP_RWSEM_CALL(kd_mmap_write_unlock_clobber_v1, (lock), \
		KD_RWSEM_OP_UP_WRITE, "")
#endif

#endif
