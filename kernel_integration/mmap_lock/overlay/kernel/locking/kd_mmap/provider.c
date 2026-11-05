// SPDX-License-Identifier: GPL-2.0
/* Binding setup and the builtin end of a transferred callback reference. */
#include <linux/export.h>
#include <linux/kd_mmap_lock_types.h>
#include <linux/kd_rwsem_provider.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include "kd_mmap_regs.h"

static DEFINE_MUTEX(kd_rwsem_registry_lock);
static const struct kd_rwsem_provider *kd_rwsem_registered;
extern const struct kd_rwsem_site __kd_rwsem_sites_start[], __kd_rwsem_sites_end[];

int kd_rwsem_register_provider(const struct kd_rwsem_provider *ops)
{
	int result = 0;

	static_assert(sizeof(struct kd_mmap_rwsem) == KD_RWSEM_PROVIDER_STORAGE_BYTES);
	static_assert(__alignof__(struct kd_mmap_rwsem) == KD_RWSEM_PROVIDER_STORAGE_ALIGN);
	static_assert(offsetof(struct kd_mmap_lock, use_kd) == 320);
	static_assert(offsetof(struct kd_mmap_lock, initialized) == 321);
	static_assert(offsetof(struct kd_mmap_lock, provider) == 328);
	static_assert(sizeof(struct kd_mmap_lock) == 384);
	if (!ops || ops->version != KD_RWSEM_PROVIDER_VERSION ||
	    ops->storage_bytes != KD_RWSEM_PROVIDER_STORAGE_BYTES ||
	    ops->storage_align != KD_RWSEM_PROVIDER_STORAGE_ALIGN ||
	    ops->packet_layout != KD_RWSEM_PROVIDER_PACKET_LAYOUT || !ops->owner ||
	    !ops->binding_get || !ops->binding_put ||
	    !ops->init || !ops->destroy || !ops->idle || !ops->down_write ||
	    !ops->down_write_interruptible || !ops->down_write_killable ||
	    !ops->down_write_trylock || !ops->up_write || !ops->downgrade_write ||
	    !ops->down_read || !ops->down_read_interruptible || !ops->down_read_killable ||
	    !ops->down_read_trylock || !ops->up_read || !ops->down_read_non_owner ||
	    !ops->up_read_non_owner || !ops->is_locked || !ops->is_contended ||
	    !ops->write_owned || !ops->assert_held || !ops->assert_held_write || !ops->capture)
		return -EINVAL;
	mutex_lock(&kd_rwsem_registry_lock);
	if (kd_rwsem_registered)
		result = -EBUSY;
	else
		kd_rwsem_registered = ops;
	mutex_unlock(&kd_rwsem_registry_lock);
	return result;
}
EXPORT_SYMBOL_GPL(kd_rwsem_register_provider);

void kd_rwsem_unregister_provider(const struct kd_rwsem_provider *ops)
{
	mutex_lock(&kd_rwsem_registry_lock);
	BUG_ON(!ops || kd_rwsem_registered != ops);
	/* Existing objects keep their exact protocol and their own references. */
	kd_rwsem_registered = NULL;
	mutex_unlock(&kd_rwsem_registry_lock);
}
EXPORT_SYMBOL_GPL(kd_rwsem_unregister_provider);

const struct kd_rwsem_provider *kd_rwsem_bind_provider(void)
{
	const struct kd_rwsem_provider *ops;

	mutex_lock(&kd_rwsem_registry_lock);
	ops = kd_rwsem_registered;
	if (ops) {
		if (!try_module_get(ops->owner)) {
			ops = NULL;
		} else if (!ops->binding_get()) {
			module_put(ops->owner);
			ops = NULL;
		}
	}
	mutex_unlock(&kd_rwsem_registry_lock);
	return ops;
}

void kd_rwsem_unbind_provider(const struct kd_rwsem_provider *ops)
{
	BUG_ON(!ops || !ops->owner);
	ops->binding_put();
	module_put(ops->owner);
}

const struct kd_rwsem_site *kd_rwsem_provider_sites(unsigned int *count)
{
	*count = __kd_rwsem_sites_end - __kd_rwsem_sites_start;
	return __kd_rwsem_sites_start;
}
EXPORT_SYMBOL_GPL(kd_rwsem_provider_sites);

/* A completed instruction has no source CALL word. Its exact post-state
 * supplies IP/SP and arithmetic flags after all cleanup, including module_put.
 * Only builtin text executes after the callback's final module reference. */
static __attribute__((noipa, noreturn)) noinline notrace void
kd_rwsem_provider_resume_instruction(const struct kd_mmap_regs *packet)
{
	asm volatile("pushfq\n\t"
		     "popq %%rax\n\t"
		     "andq $%c[keep_flags], %%rax\n\t"
		     "movq %c[flags](%%rdi), %%rcx\n\t"
		     "andq $%c[arithmetic_flags], %%rcx\n\t"
		     "orq %%rcx, %%rax\n\t"
		     "movq %c[sp](%%rdi), %%rsp\n\t"
		     "pushq %c[ip](%%rdi)\n\t"
		     "pushq %%rax\n\t"
		     "movq %c[r15](%%rdi), %%r15\n\t"
		     "movq %c[r14](%%rdi), %%r14\n\t"
		     "movq %c[r13](%%rdi), %%r13\n\t"
		     "movq %c[r12](%%rdi), %%r12\n\t"
		     "movq %c[bp](%%rdi), %%rbp\n\t"
		     "movq %c[bx](%%rdi), %%rbx\n\t"
		     "movq %c[r11](%%rdi), %%r11\n\t"
		     "movq %c[r10](%%rdi), %%r10\n\t"
		     "movq %c[r9](%%rdi), %%r9\n\t"
		     "movq %c[r8](%%rdi), %%r8\n\t"
		     "movq %c[ax](%%rdi), %%rax\n\t"
		     "movq %c[cx](%%rdi), %%rcx\n\t"
		     "movq %c[dx](%%rdi), %%rdx\n\t"
		     "movq %c[si](%%rdi), %%rsi\n\t"
		     "movq %c[di](%%rdi), %%rdi\n\t"
		     "popfq\n\t"
#if defined(CONFIG_MITIGATION_RETHUNK) || defined(CONFIG_RETHUNK)
		     "jmp __x86_return_thunk\n\t"
#else
		     "retq\n\t"
#endif
		     : : "D"(packet), [ip] "i"(KD_MMAP_REG_IP),
		       [sp] "i"(KD_MMAP_REG_SP), [flags] "i"(KD_MMAP_REG_FLAGS),
		       [arithmetic_flags] "i"(KD_MMAP_REG_ARITHMETIC_FLAGS),
		       [keep_flags] "i"(~KD_MMAP_REG_ARITHMETIC_FLAGS),
		       [r15] "i"(KD_MMAP_REG_R15), [r14] "i"(KD_MMAP_REG_R14),
		       [r13] "i"(KD_MMAP_REG_R13), [r12] "i"(KD_MMAP_REG_R12),
		       [bp] "i"(KD_MMAP_REG_BP), [bx] "i"(KD_MMAP_REG_BX),
		       [r11] "i"(KD_MMAP_REG_R11), [r10] "i"(KD_MMAP_REG_R10),
		       [r9] "i"(KD_MMAP_REG_R9), [r8] "i"(KD_MMAP_REG_R8),
		       [ax] "i"(KD_MMAP_REG_AX), [cx] "i"(KD_MMAP_REG_CX),
		       [dx] "i"(KD_MMAP_REG_DX), [si] "i"(KD_MMAP_REG_SI),
		       [di] "i"(KD_MMAP_REG_DI) : "memory", "cc");
	__builtin_unreachable();
}

/* FULL packet storage belongs to the Native caller's stack. Normal completion
 * has retired module-owned state. Native handback supplies an independent
 * restore reference; E retains its own references through its final accesses.
 * After module_put no module text or object/provider field is accessed. */
__attribute__((noipa)) noinline notrace void __noreturn
kd_rwsem_provider_resume(struct module *owner, const void *full_packet)
{
	const struct kd_mmap_regs *packet = full_packet;

	module_put(owner);
	if (packet->orig_ax == KD_MMAP_REG_ORIGIN_SUFFIX_TAG)
		kd_rwsem_provider_resume_instruction(packet);
	asm volatile("movq %c[r15](%%rdi), %%r15\n\t"
		     "movq %c[r14](%%rdi), %%r14\n\t"
		     "movq %c[r13](%%rdi), %%r13\n\t"
		     "movq %c[r12](%%rdi), %%r12\n\t"
		     "movq %c[bp](%%rdi), %%rbp\n\t"
		     "movq %c[bx](%%rdi), %%rbx\n\t"
		     "movq %c[r11](%%rdi), %%r11\n\t"
		     "movq %c[r10](%%rdi), %%r10\n\t"
		     "movq %c[r9](%%rdi), %%r9\n\t"
		     "movq %c[r8](%%rdi), %%r8\n\t"
		     "movq %c[ax](%%rdi), %%rax\n\t"
		     "movq %c[cx](%%rdi), %%rcx\n\t"
		     "movq %c[dx](%%rdi), %%rdx\n\t"
		     "movq %c[si](%%rdi), %%rsi\n\t"
		     "movq %c[sp](%%rdi), %%rsp\n\t"
		     "movq %c[di](%%rdi), %%rdi\n\t"
#if defined(CONFIG_MITIGATION_RETHUNK) || defined(CONFIG_RETHUNK)
		     "jmp __x86_return_thunk\n\t"
#else
		     "retq\n\t"
#endif
		     : : "D"(full_packet), [r15] "i"(KD_MMAP_REG_R15),
		       [r14] "i"(KD_MMAP_REG_R14), [r13] "i"(KD_MMAP_REG_R13),
		       [r12] "i"(KD_MMAP_REG_R12), [bp] "i"(KD_MMAP_REG_BP),
		       [bx] "i"(KD_MMAP_REG_BX), [r11] "i"(KD_MMAP_REG_R11),
		       [r10] "i"(KD_MMAP_REG_R10), [r9] "i"(KD_MMAP_REG_R9),
		       [r8] "i"(KD_MMAP_REG_R8), [ax] "i"(KD_MMAP_REG_AX),
		       [cx] "i"(KD_MMAP_REG_CX), [dx] "i"(KD_MMAP_REG_DX),
		       [si] "i"(KD_MMAP_REG_SI), [sp] "i"(KD_MMAP_REG_SP),
		       [di] "i"(KD_MMAP_REG_DI) : "memory");
	__builtin_unreachable();
}
EXPORT_SYMBOL_GPL(kd_rwsem_provider_resume);
