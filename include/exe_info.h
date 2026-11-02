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
};

/* Only FULL permits reading all GPR slots. MINIMAL and COMPLETE contain
 * ip/sp/bp; complete ip/sp already describe the post-unlock boundary. */
enum kd_packet_state {
	KD_PACKET_FULL = 0,
	KD_PACKET_MINIMAL = 1,
	KD_PACKET_COMPLETE = 2,
};
#define KD_EXE_CLOBBER_COMPLETE 7
/* A reviewed instruction was reached before execution; original waiter resumes. */
#define KD_EXE_NATIVE_ESCAPE 8
/* Checked spin address predicate failed before its source memory load. */
#define KD_EXE_ADDRESS_GUARD 9
/* Direct helper quota expired with the original CALL still pending. */
#define KD_EXE_DIRECT_CALL_LIMIT 10
/* Actual near indirect CALL: FULL IP is target, orig_ax is source CALL site. */
#define KD_EXE_INDIRECT_CALL 11
/* Exact CPU instruction on the original task, with retained JIT continuation. */
#define KD_EXE_ORIGIN_INSN 12

enum kd_exe_lock_kind {
	KD_EXE_LOCK_UNKNOWN = 0,
	KD_EXE_LOCK_SPIN = 1,
	KD_EXE_LOCK_MUTEX = 2,
};

/* A versioned register contract never changes a translation's lock backend. */
static inline int kd_entry_abi_valid(int kind, unsigned int abi)
{
	return (kind == KD_EXE_LOCK_SPIN || kind == KD_EXE_LOCK_MUTEX) &&
	       (abi == KD_ENTRY_ABI_LEGACY ||
		((abi == KD_ENTRY_ABI_SPIN_CLOBBER_V1 ||
		  abi == KD_ENTRY_ABI_RWLOCK_CLOBBER_V1) && kind == KD_EXE_LOCK_SPIN) ||
		(abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1 && kind == KD_EXE_LOCK_MUTEX));
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
#define KD_IMAGE_PROTOCOL_SERVICE_QUEUE 3U
#define KD_IMAGE_REQUIRE_NATIVE_ESCAPE (1U << 0)
#define KD_IMAGE_REQUIRE_ADDRESS_GUARD (1U << 1)
#define KD_IMAGE_REQUIRE_STRING_SERVICES (1U << 2)
#define KD_IMAGE_REQUIRE_STRING_WRITE (1U << 3)
#define KD_IMAGE_REQUIRE_DIRECT_STRINGS (1U << 4)
/* ABI1/3 markers require one pristine physical root and one invocation.
 * This is separate from ABI2, whose nested continuation contract is unchanged. */
#define KD_IMAGE_REQUIRE_ROOT_NATIVE_ESCAPE (1U << 5)
#define KD_IMAGE_REQUIRE_ORIGIN_INSN (1U << 6)
#define KD_IMAGE_REQUIRE_BUDGET_RESUME (1U << 7)
#define KD_IMAGE_REQUIRE_SERVICE_QUEUE (1U << 8)
#define KD_IMAGE_REQUIRE_ORIGIN_CALL (1U << 9)
#define KD_IMAGE_REQUIREMENTS (KD_IMAGE_REQUIRE_NATIVE_ESCAPE | KD_IMAGE_REQUIRE_ADDRESS_GUARD | KD_IMAGE_REQUIRE_STRING_SERVICES | KD_IMAGE_REQUIRE_STRING_WRITE | KD_IMAGE_REQUIRE_DIRECT_STRINGS | KD_IMAGE_REQUIRE_ROOT_NATIVE_ESCAPE | KD_IMAGE_REQUIRE_ORIGIN_INSN | KD_IMAGE_REQUIRE_BUDGET_RESUME | KD_IMAGE_REQUIRE_SERVICE_QUEUE | KD_IMAGE_REQUIRE_ORIGIN_CALL)

static inline int kd_image_requirements_valid(int kind, unsigned int abi,
					     unsigned int requirements)
{
	return !(requirements & ~KD_IMAGE_REQUIREMENTS) &&
	       (!(requirements & KD_IMAGE_REQUIRE_ORIGIN_CALL) ||
		(requirements & KD_IMAGE_REQUIRE_SERVICE_QUEUE)) &&
	       (!(requirements & KD_IMAGE_REQUIRE_SERVICE_QUEUE) ||
		(kind == KD_EXE_LOCK_MUTEX && abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1 &&
		 !(requirements & ~(KD_IMAGE_REQUIRE_SERVICE_QUEUE | KD_IMAGE_REQUIRE_BUDGET_RESUME |
				    KD_IMAGE_REQUIRE_ORIGIN_CALL)))) &&
	       (!(requirements & KD_IMAGE_REQUIRE_BUDGET_RESUME) ||
		(kind == KD_EXE_LOCK_MUTEX && abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1 &&
		 !(requirements & (KD_IMAGE_REQUIRE_NATIVE_ESCAPE |
		   KD_IMAGE_REQUIRE_ORIGIN_INSN | KD_IMAGE_REQUIRE_DIRECT_STRINGS)))) &&
	       (!(requirements & KD_IMAGE_REQUIRE_ORIGIN_INSN) ||
		(kind == KD_EXE_LOCK_MUTEX && abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1 &&
		 requirements == (KD_IMAGE_REQUIRE_NATIVE_ESCAPE | KD_IMAGE_REQUIRE_ORIGIN_INSN))) &&
	       (!(requirements & KD_IMAGE_REQUIRE_NATIVE_ESCAPE) ||
		(kind == KD_EXE_LOCK_MUTEX && abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1) ||
		(kind == KD_EXE_LOCK_SPIN && kd_entry_abi_spin_clobber(abi) &&
		 requirements == (KD_IMAGE_REQUIRE_NATIVE_ESCAPE |
				  KD_IMAGE_REQUIRE_ROOT_NATIVE_ESCAPE))) &&
	       (!(requirements & KD_IMAGE_REQUIRE_ROOT_NATIVE_ESCAPE) ||
		(kind == KD_EXE_LOCK_SPIN && kd_entry_abi_spin_clobber(abi) &&
		 requirements == (KD_IMAGE_REQUIRE_NATIVE_ESCAPE |
				  KD_IMAGE_REQUIRE_ROOT_NATIVE_ESCAPE))) &&
	       (!(requirements & KD_IMAGE_REQUIRE_ADDRESS_GUARD) ||
		(kind == KD_EXE_LOCK_SPIN && abi == KD_ENTRY_ABI_SPIN_CLOBBER_V1)) &&
	       (!(requirements & KD_IMAGE_REQUIRE_STRING_SERVICES) ||
		(kind == KD_EXE_LOCK_SPIN && abi == KD_ENTRY_ABI_SPIN_CLOBBER_V1)) &&
	       (!(requirements & KD_IMAGE_REQUIRE_STRING_WRITE) ||
		(kind == KD_EXE_LOCK_SPIN && abi == KD_ENTRY_ABI_SPIN_CLOBBER_V1)) &&
	       (!(requirements & KD_IMAGE_REQUIRE_DIRECT_STRINGS) ||
		(kind == KD_EXE_LOCK_SPIN && abi == KD_ENTRY_ABI_SPIN_CLOBBER_V1 &&
		 !(requirements & KD_IMAGE_REQUIRE_ADDRESS_GUARD) &&
		 (requirements & (KD_IMAGE_REQUIRE_STRING_SERVICES | KD_IMAGE_REQUIRE_STRING_WRITE))));
}
#define KD_IMAGE_HEADER_SIZE 48U
#define KD_IMAGE_SERVICE_HEADER_SIZE 64U
#define KD_IMAGE_VERSION_OFFSET 46U
#define KD_IMAGE_REQUIREMENTS_OFFSET 47U
#define KD_IMAGE_FULL_REQUIREMENTS_OFFSET 48U

static inline unsigned int kd_image_protocol(unsigned int requirements)
{
	return requirements & KD_IMAGE_REQUIRE_SERVICE_QUEUE ?
		KD_IMAGE_PROTOCOL_SERVICE_QUEUE : KD_IMAGE_PROTOCOL;
}

static inline int kd_image_protocol_valid(unsigned int version,
					unsigned int requirements)
{
	return version == kd_image_protocol(requirements) &&
		(version != KD_IMAGE_PROTOCOL || requirements <= 0xffU);
}

/* Shared by daemon and provider. The fixed ABI directory remains in the first
 * 48 bytes; only retained-service images append a full requirement word. */
static inline int kd_image_header_requirements(const unsigned char *header,
	unsigned long length, unsigned int *requirements)
{
	unsigned int value;

	if (!header || !requirements || length < KD_IMAGE_HEADER_SIZE)
		return 0;
	value = header[KD_IMAGE_REQUIREMENTS_OFFSET];
	if (header[KD_IMAGE_VERSION_OFFSET] == KD_IMAGE_PROTOCOL_SERVICE_QUEUE) {
		const unsigned char *word;

		if (length < KD_IMAGE_SERVICE_HEADER_SIZE)
			return 0;
		word = header + KD_IMAGE_FULL_REQUIREMENTS_OFFSET;
		value = (unsigned int)word[0] | ((unsigned int)word[1] << 8) |
			((unsigned int)word[2] << 16) | ((unsigned int)word[3] << 24);
		if (header[KD_IMAGE_REQUIREMENTS_OFFSET] != (value & 0xffU))
			return 0;
	}
	if (!kd_image_protocol_valid(header[KD_IMAGE_VERSION_OFFSET], value))
		return 0;
	*requirements = value;
	return 1;
}

#endif
