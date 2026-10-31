/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LINUX_KD_API_LOCK_H
#define _LINUX_KD_API_LOCK_H
#include <linux/kd_api_lock_types.h>
#include <linux/kd_api_control.h>
struct files_struct;
struct pipe_inode_info;

#ifdef CONFIG_KD_API_LOCKS
int kd_api_files_init(struct files_struct *files);
void kd_api_files_destroy(struct files_struct *files);
int kd_api_pipe_init(struct pipe_inode_info *pipe);
void kd_api_pipe_destroy(struct pipe_inode_info *pipe);
void kd_api_files_lock(kd_api_spinlock_t *lock);
void kd_api_files_unlock(kd_api_spinlock_t *lock);
void kd_api_pipe_lock(kd_api_mutex_t *lock);
void kd_api_pipe_unlock(kd_api_mutex_t *lock);

#include <asm/asm.h>
/* R8 is the immutable per-object binding; R9 admits GETPIPE_SZ only. No C
 * helper may create a frame between this capture and the provider entry. */
#define __KD_API_CALL(symbol, word, binding, eligible, site_record) do { \
	__auto_type kd_api_word = (word); \
	register const struct kd_api_provider *kd_api_ops asm("r8") = (binding); \
	register unsigned long kd_api_eligible asm("r9") = (eligible); \
	unsigned long kd_api_sp, kd_api_ip, kd_api_bp; \
	asm volatile("movq %%rsp, %%rsi\n\t" \
		"leaq 1f(%%rip), %%rdx\n\t" \
		"movq %%rbp, %%rcx\n\tcall " #symbol "\n\t1:\n\t" site_record \
		: "+D"(kd_api_word), "=S"(kd_api_sp), "=d"(kd_api_ip), \
		  "=c"(kd_api_bp), "+r"(kd_api_ops), "+r"(kd_api_eligible), \
		  ASM_CALL_CONSTRAINT \
		: : "rax", "rbx", "r10", "r11", "r12", "r13", "r14", "r15", \
		    "cc", "memory"); \
} while (0)
#define __KD_API_SITE(number) \
	".pushsection .kd_api_sites,\"a\"\n\t.balign 8\n\t.quad 1b\n\t" \
	".long " #number "\n\t.long 0\n\t.popsection\n\t"
#define KD_API_FILES_LOCK(files) do { \
	struct files_struct *kd_api_files = (files); \
	__KD_API_CALL(kd_api_files_lock_clobber, &kd_api_files->file_lock, \
		kd_api_files->kd_lock_provider, 1, __KD_API_SITE(1)); \
} while (0)
#define KD_API_FILES_UNLOCK(files) do { \
	struct files_struct *kd_api_files = (files); \
	__KD_API_CALL(kd_api_files_unlock_clobber, &kd_api_files->file_lock, \
		kd_api_files->kd_lock_provider, 1, ""); \
} while (0)
#define KD_API_PIPE_LOCK(pipe, eligible, site) do { \
	struct pipe_inode_info *kd_api_pipe = (pipe); \
	__KD_API_CALL(kd_api_pipe_lock_clobber, &kd_api_pipe->mutex, \
		kd_api_pipe->kd_lock_provider, eligible, __KD_API_SITE(site)); \
} while (0)
#define KD_API_PIPE_UNLOCK(pipe) do { \
	struct pipe_inode_info *kd_api_pipe = (pipe); \
	__KD_API_CALL(kd_api_pipe_unlock_clobber, &kd_api_pipe->mutex, \
		kd_api_pipe->kd_lock_provider, 1, ""); \
} while (0)
#else
/* Disabled configuration keeps Native locking; typed storage still prevents
 * accidentally adding an unreviewed direct lock call to these object classes. */
#define kd_api_files_init(files) \
	({ (files)->kd_lock_provider = NULL; spin_lock_init(&(files)->file_lock.native); 0; })
#define kd_api_pipe_init(pipe) \
	({ (pipe)->kd_lock_provider = NULL; mutex_init(&(pipe)->mutex.native); 0; })
#define kd_api_files_destroy(files) do { } while (0)
#define kd_api_pipe_destroy(pipe) do { } while (0)
static inline void kd_api_files_lock(kd_api_spinlock_t *lock) { spin_lock(&lock->native); }
static inline void kd_api_files_unlock(kd_api_spinlock_t *lock) { spin_unlock(&lock->native); }
static inline void kd_api_pipe_lock(kd_api_mutex_t *lock) { mutex_lock(&lock->native); }
static inline void kd_api_pipe_unlock(kd_api_mutex_t *lock) { mutex_unlock(&lock->native); }
#define KD_API_FILES_LOCK(files) kd_api_files_lock(&(files)->file_lock)
#define KD_API_FILES_UNLOCK(files) kd_api_files_unlock(&(files)->file_lock)
#define KD_API_PIPE_LOCK(pipe, eligible, site) kd_api_pipe_lock(&(pipe)->mutex)
#define KD_API_PIPE_UNLOCK(pipe) kd_api_pipe_unlock(&(pipe)->mutex)
#endif

/* The enabled target refuses LOCKDEP/debug layouts. These retain the Native
 * annotation vocabulary for disabled builds; they confer no KD ownership. */
#define kd_api_files_is_held(lock) lockdep_is_held(&(lock)->native)
#define kd_api_files_assert_held(lock) lockdep_assert_held(&(lock)->native)
#define kd_api_pipe_assert_held(lock) lockdep_assert_held(&(lock)->native)
#define kd_api_pipe_is_held(lock) lockdep_is_held(&(lock)->native)
#define kd_api_pipe_set_cmp_fn(lock, fn, priv) lock_set_cmp_fn(&(lock)->native, fn, priv)
#endif
