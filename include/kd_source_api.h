#ifndef KD_SOURCE_API_H
#define KD_SOURCE_API_H

#include <linux/ioctl.h>
#include <linux/types.h>

/* Separate device control ABI; entry packets and wrapper words stay unchanged.
 * Retirement is terminal, not a concurrent code-version switch. */
#define KD_SOURCE_OPEN 0
#define KD_SOURCE_DRAINING 1
#define KD_SOURCE_RETIRED 2
#define KD_SOURCE_MAX_MODULES 64
#define KD_SOURCE_MAX_READ (256 * 1024)

struct kd_source_range {
	__u64 address;
	__u64 size;
};

struct kd_source_info {
	__u32 state;
	__u32 modules;
	__u32 frames;
	__u32 writers;
};

/* Capabilities describe implementation guarantees, not mutable admission or
 * an executable generation. Only local mutex controls returning to JIT have
 * compared this many bytes above the virtual CALL word. The CALL token is
 * validated separately; other memory, spin controls and hostcalls are excluded.
 * The runtime array and advertised bound must share this constant.
 *
 * Version 2 uses the former reserved word for the x86-64 boot-reserved module
 * per-CPU arena. It starts after ALIGN(core_static_size, 4) on each possible
 * CPU. Its address extent survives module unload; object validity does not.
 * This excludes dynamic chunks and the first unit's possibly freed tail. */
#define KD_JIT_CAPS_VERSION 20
#define KD_JIT_CAP_MUTEX_STACK (1U << 0)
#define KD_JIT_CAP_PERCPU_MODULE (1U << 1)
#define KD_JIT_CAP_MUTEX_IMAGES (1U << 3)
#define KD_JIT_CAP_MUTEX_EXCLUSIVE (1U << 4)
#define KD_JIT_CAP_NATIVE_ESCAPE (1U << 5)
#define KD_JIT_CAP_ADDRESS_GUARD (1U << 6)
#define KD_JIT_CAP_STRING_SERVICES (1U << 7)
#define KD_JIT_CAP_STRING_WRITE (1U << 8)
/* Original C helper semantics without helper-specific instruction/argument
 * checks; the caller supplies valid memory and lifetime. KD frame/return
 * bookkeeping and the existing string service image requirements remain. */
#define KD_JIT_CAP_AUDITED_STRINGS (1U << 9)
/* Relocated native CALLs inside a pristine immutable ABI1 invocation. */
#define KD_JIT_CAP_DIRECT_STRINGS (1U << 10)
/* Immutable ABI1/3 instruction markers, only from a single physical root. */
#define KD_JIT_CAP_ROOT_NATIVE_ESCAPE (1U << 11)
/* Optional v12 extension: exact near-indirect CALL native continuation. */
#define KD_JIT_CAP_INDIRECT_CALL (1U << 12)
/* One exact original-task instruction can resume the retained ABI2 image. */
#define KD_JIT_CAP_ORIGIN_INSTRUCTION (1U << 13)
/* Registered returning primitive CALLs retain an exact ABI2 continuation. */
#define KD_JIT_CAP_ORIGIN_CALL (1U << 14)
/* One exact unlocked GS memory instruction returns to the retained image. */
#define KD_JIT_CAP_ORIGIN_MEMORY (1U << 15)
/* Exact origin preempt-count read aliases use returning instruction service. */
#define KD_JIT_CAP_ORIGIN_CONTEXT_READ (1U << 16)
/* Owned indirect JMP keeps the caller's existing source CALL word. */
#define KD_JIT_CAP_INDIRECT_TAIL (1U << 17)
/* Exact pending source instruction can end a retained ABI2 invocation. */
#define KD_JIT_CAP_SOURCE_FRONTIER (1U << 18)
#define KD_JIT_MUTEX_STACK_BYTES 256
#define KD_JIT_PERCPU_MODULE_BYTES (8 * 1024)
#define KD_JIT_PERCPU_ALIGNMENT 4
struct kd_jit_caps {
	__u32 version;
	__u32 features;
	__u32 mutex_stack_bytes;
	__u32 percpu_module_bytes;
};

#define KD_SOURCE_PIN _IOW('K', 0x70, struct kd_source_range)
#define KD_SOURCE_INFO _IOR('K', 0x71, struct kd_source_info)
#define KD_SOURCE_RETIRE _IO('K', 0x72)
#define KD_JIT_CAPS _IOR('K', 0x73, struct kd_jit_caps)

#endif
