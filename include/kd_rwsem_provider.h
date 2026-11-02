/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_RWSEM_PROVIDER_H
#define KD_RWSEM_PROVIDER_H

#include <linux/types.h>
#include <linux/compiler_attributes.h>

struct module;
struct task_struct;

#define KD_RWSEM_PROVIDER_VERSION 1U
#define KD_RWSEM_PROVIDER_STORAGE_BYTES 320U
#define KD_RWSEM_PROVIDER_STORAGE_ALIGN 64U
#define KD_RWSEM_PROVIDER_PACKET_LAYOUT 2U
#define KD_RWSEM_CONTROL_CAPTURE (1U << 0)
#define KD_RWSEM_CONTROL_INTEGER (1U << 1)

enum kd_rwsem_provider_operation {
	KD_RWSEM_OP_DOWN_WRITE = 1,
	KD_RWSEM_OP_DOWN_WRITE_INTERRUPTIBLE,
	KD_RWSEM_OP_DOWN_WRITE_KILLABLE,
	KD_RWSEM_OP_DOWN_WRITE_TRYLOCK,
	KD_RWSEM_OP_UP_WRITE,
	KD_RWSEM_OP_DOWNGRADE_WRITE,
	KD_RWSEM_OP_DOWN_READ,
	KD_RWSEM_OP_DOWN_READ_INTERRUPTIBLE,
	KD_RWSEM_OP_DOWN_READ_KILLABLE,
	KD_RWSEM_OP_DOWN_READ_TRYLOCK,
	KD_RWSEM_OP_UP_READ,
	KD_RWSEM_OP_DOWN_READ_NON_OWNER,
	KD_RWSEM_OP_UP_READ_NON_OWNER,
};

/* An object chooses this entire protocol once, before publication. Opaque
 * storage is initialized by its provider; equal geometry is not permission
 * for another provider to manipulate its queue or ownership records. */
struct kd_rwsem_provider {
	u32 version;
	u32 storage_bytes;
	u32 storage_align;
	u32 packet_layout;
	struct module *owner;
	/* Bounded factory lease operations. get runs under the builtin registry
	 * mutex before a selected binding escapes to an object initializer. */
	bool (*binding_get)(void);
	void (*binding_put)(void);
	void (*init)(void *object);
	void (*destroy)(void *object);
	bool (*idle)(const void *object);
	void (*down_write)(void *object);
	int (*down_write_interruptible)(void *object);
	int (*down_write_killable)(void *object);
	int (*down_write_trylock)(void *object);
	void (*up_write)(void *object);
	void (*downgrade_write)(void *object);
	void (*down_read)(void *object);
	int (*down_read_interruptible)(void *object);
	int (*down_read_killable)(void *object);
	int (*down_read_trylock)(void *object);
	void (*up_read)(void *object);
	void (*down_read_non_owner)(void *object);
	void (*up_read_non_owner)(void *object);
	bool (*is_locked)(const void *object);
	bool (*is_contended)(const void *object);
	bool (*write_owned)(const void *object, const struct task_struct *task);
	void (*assert_held)(const void *object);
	void (*assert_held_write)(const void *object);
	/* The builtin caller transfers its transient callback module reference.
	 * Cancellation returns to that caller. Successful proxy completion uses
	 * kd_rwsem_provider_resume after all module-owned state has retired. */
	int (*capture)(void *object, unsigned int state, unsigned long sp,
		       unsigned long ip, unsigned long bp);
};

struct kd_rwsem_site {
	unsigned long entry;
	u32 operation;
	u32 reserved;
};

/* resolve validates this facade's immutable binding before returning storage.
 * A NULL result is another backend, not a module rwsem selected by layout. */
struct kd_rwsem_control_binding {
	unsigned long target;
	u32 operation;
	u32 flags;
	void *(*resolve)(void *source_argument,
			 const struct kd_rwsem_provider *expected);
};

/* Builtin registry: setup controls only future object initialization. */
int kd_rwsem_register_provider(const struct kd_rwsem_provider *provider);
void kd_rwsem_unregister_provider(const struct kd_rwsem_provider *provider);
const struct kd_rwsem_provider *kd_rwsem_bind_provider(void);
void kd_rwsem_unbind_provider(const struct kd_rwsem_provider *provider);
const struct kd_rwsem_control_binding *kd_rwsem_provider_controls(unsigned int *count);
const struct kd_rwsem_site *kd_rwsem_provider_sites(unsigned int *count);
void kd_rwsem_provider_resume(struct module *owner, const void *full_packet) __noreturn;

/* Loadable provider lifecycle and exact typed endpoint lookup. Activation is
 * explicit and requires ready immutable images; it is never automatic at load. */
int kd_rwsem_provider_init(void);
void kd_rwsem_provider_exit(void);
int kd_rwsem_provider_prepare_entries(void);
int kd_rwsem_provider_activate(void);
void kd_rwsem_provider_deactivate(void);
bool kd_rwsem_provider_active(void);
bool kd_rwsem_provider_lookup_control(unsigned long target, void *source_argument,
				     unsigned int *operation, unsigned int *flags,
				     void **object);

#endif /* KD_RWSEM_PROVIDER_H */
