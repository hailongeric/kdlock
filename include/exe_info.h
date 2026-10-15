#ifndef EXE_INFO_H
#define EXE_INFO_H

#define KD_MAX_EXE 511
#define KD_CODE_BLOCK_SIZE (4096UL * 160)

/*
 * kd_exe_info — per-critical-section translation entry.
 *
 * Each entry represents one kernel code address (RIP) whose critical section
 * has been promoted for delegation.  The userspace daemon polls these entries,
 * translates the kernel text at RIP into a JIT sandbox, and writes the binary
 * back.  The status_code tracks where this entry is in the translation
 * pipeline.
 */

/* --- status_code values -------------------------------------------------- */
#define KD_EXE_NATIVE_ONLY \
	-3 /* terminal policy rejection; never execute code */
#define KD_EXE_UNUSED -2 /* slot is free                              */
#define KD_EXE_UNINIT -1 /* allocated, waiting for daemon translation */
#define KD_EXE_NORMAL 0 /* translation ready, code can be executed   */
#define KD_EXE_CALL_MISS 1 /* translated code hit an untranslated call  */
#define KD_EXE_IJ_MISS 2 /* translated code hit an indirect jump      */
#define KD_EXE_ERROR_INST 3 /* unsupported instruction encountered       */
#define KD_EXE_INST_LIMIT 4 /* instruction count limit exceeded          */

/* Runtime-only sandbox exit; never published as kd_exe_info.status_code. */
#define KD_EXE_HOSTCALL 5 /* sandbox requests an allowlisted service   */
#define KD_EXE_ENTRY_REFUSED \
	6 /* entry predicate failed before any CS instruction */

/* Identity comes from the physical hook, never inferred from code bytes. */
enum kd_entry_abi {
	KD_ENTRY_ABI_LEGACY = 0,
	KD_ENTRY_ABI_SPIN_CLOBBER_V1 = 1,
	KD_ENTRY_ABI_MUTEX_CLOBBER_V1 = 2,
	/* Spin packet/completion ABI; writer admission precedes the body. */
	KD_ENTRY_ABI_RWLOCK_CLOBBER_V1 = 3,
	/* Owned outer CALL preserves the ordinary x86-64 nonvolatile registers. */
	KD_ENTRY_ABI_OWNED_MUTEX_CABI_V2 = 4,
};

/* Only FULL permits reading all GPR slots. MINIMAL and COMPLETE contain
 * ip/sp/bp; complete ip/sp already describe the post-unlock boundary. */
enum kd_packet_state {
	KD_PACKET_FULL = 0,
	KD_PACKET_MINIMAL = 1,
	KD_PACKET_COMPLETE = 2,
	/* IP/SP/BP, RBX/R12-R15; entry also defines synthetic RAX=0. */
	KD_PACKET_CALLEE_ENTRY = 3,
	KD_PACKET_CALLEE_COMPLETE = 4,
};
#define KD_EXE_CLOBBER_COMPLETE 7

enum kd_exe_lock_kind {
	KD_EXE_LOCK_UNKNOWN = 0,
	KD_EXE_LOCK_SPIN = 1,
	/* Wire value 2 is retired; never reuse it for owned objects. */
	KD_EXE_LOCK_OWNED_MUTEX = 3,
};

/* A versioned register contract never changes a translation's lock backend. */
static inline int kd_entry_abi_valid(int kind, unsigned int abi)
{
	if (kind == KD_EXE_LOCK_OWNED_MUTEX)
		return abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1 ||
		       abi == KD_ENTRY_ABI_OWNED_MUTEX_CABI_V2;
	return kind == KD_EXE_LOCK_SPIN &&
	       (abi == KD_ENTRY_ABI_LEGACY ||
		abi == KD_ENTRY_ABI_SPIN_CLOBBER_V1 ||
		abi == KD_ENTRY_ABI_RWLOCK_CLOBBER_V1);
}

static inline int kd_entry_abi_clobber(unsigned int abi)
{
	return abi == KD_ENTRY_ABI_SPIN_CLOBBER_V1 ||
	       abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1 ||
	       abi == KD_ENTRY_ABI_RWLOCK_CLOBBER_V1;
}

static inline int kd_entry_abi_spin_clobber(unsigned int abi)
{
	return abi == KD_ENTRY_ABI_SPIN_CLOBBER_V1 ||
	       abi == KD_ENTRY_ABI_RWLOCK_CLOBBER_V1;
}

static inline int kd_entry_abi_mutex_reduced(unsigned int abi)
{
	return abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1 ||
	       abi == KD_ENTRY_ABI_OWNED_MUTEX_CABI_V2;
}

static inline unsigned int kd_entry_packet_state(unsigned int abi)
{
	return abi == KD_ENTRY_ABI_OWNED_MUTEX_CABI_V2 ?
		KD_PACKET_CALLEE_ENTRY : KD_PACKET_MINIMAL;
}

static inline unsigned int kd_complete_packet_state(unsigned int abi)
{
	return abi == KD_ENTRY_ABI_OWNED_MUTEX_CABI_V2 ?
		KD_PACKET_CALLEE_COMPLETE : KD_PACKET_COMPLETE;
}

struct kd_exe_info {
	int status_code; /* KD_EXE_NATIVE_ONLY through KD_EXE_INST_LIMIT */
	int pid; /* thread id that triggered this entry      */
	int tgid; /* process id (thread-group leader)         */
	int lock_kind; /* immutable registration kind; uses old alignment padding */
	unsigned long RIP; /* kernel instruction pointer of CS entry   */
	void *code_block; /* vmalloc'd executable page for JIT code   */
	unsigned long jump_from; /* source address for indirect jump fixup   */
	unsigned long tgt_addr; /* target address for call-miss / ij-miss   */
	unsigned int entry_abi; /* immutable; occupies existing cacheline padding */
	unsigned int requirements; /* snapshot of the published image contract */
	unsigned long generation; /* runtime misses belong to this image only */
} __attribute__((aligned(64)));

/*
 * kd_recv_pkt — header written by daemon to /dev/kd_dev.
 *
 * The daemon sends one of these before each chunk of JIT binary so the
 * kernel module can locate the correct exe entry and copy the code. A
 * NATIVE_ONLY packet has offset zero and no binary payload.
 */
struct kd_recv_pkt {
	int status_code; /* NORMAL/UNINIT chunks, or header-only NATIVE_ONLY */
	int pid; /* matches kd_exe_info.pid                  */
	unsigned long RIP; /* matches kd_exe_info.RIP                  */
	unsigned long offset; /* byte offset within code_block            */
	unsigned int version;
	unsigned int entry_abi;
	unsigned int requirements;
	unsigned int reserved;
	unsigned long image_length;
	unsigned long upload_id;
	unsigned long base_generation;
};

#define KD_IMAGE_PROTOCOL 2U
#define KD_IMAGE_ORIGIN_SPIN (1U << 0)
#define KD_IMAGE_REQUIREMENTS KD_IMAGE_ORIGIN_SPIN
#define KD_IMAGE_HEADER_SIZE 48U
#define KD_IMAGE_VERSION_OFFSET 46U
#define KD_IMAGE_REQUIREMENTS_OFFSET 47U

#endif
