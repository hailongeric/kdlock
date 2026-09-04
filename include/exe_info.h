#ifndef EXE_INFO_H
#define EXE_INFO_H

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
#define KD_EXE_UNUSED     -2   /* slot is free                              */
#define KD_EXE_UNINIT     -1   /* allocated, waiting for daemon translation */
#define KD_EXE_NORMAL      0   /* translation ready, code can be executed   */
#define KD_EXE_CALL_MISS   1   /* translated code hit an untranslated call  */
#define KD_EXE_IJ_MISS     2   /* translated code hit an indirect jump      */
#define KD_EXE_ERROR_INST  3   /* unsupported instruction encountered       */
#define KD_EXE_INST_LIMIT  4   /* instruction count limit exceeded          */

/* Runtime-only sandbox exit; never published as kd_exe_info.status_code. */
#define KD_EXE_HOSTCALL    5   /* sandbox requests an allowlisted service   */

struct kd_exe_info {
	int status_code;           /* KD_EXE_UNUSED through KD_EXE_INST_LIMIT  */
	int pid;                   /* thread id that triggered this entry      */
	int tgid;                  /* process id (thread-group leader)         */
	unsigned long RIP;         /* kernel instruction pointer of CS entry   */
	void* code_block;          /* vmalloc'd executable page for JIT code   */
	unsigned long jump_from;   /* source address for indirect jump fixup   */
	unsigned long tgt_addr;    /* target address for call-miss / ij-miss   */
	unsigned long gsbase;      /* reserved; waiter GS travels in args[0]   */
	int success_cnt;           /* successful delegation count              */
	int fail_cnt;              /* delegation failure count                 */
}__attribute__((aligned(64)));

/*
 * kd_recv_pkt — header written by daemon to /dev/kd_dev.
 *
 * The daemon sends one of these before each chunk of JIT binary so the
 * kernel module can locate the correct exe entry and copy the code.
 */
struct kd_recv_pkt {
	int status_code;           /* F_NORMAL when final chunk, -1 for more  */
	int pid;                   /* matches kd_exe_info.pid                  */
	unsigned long RIP;         /* matches kd_exe_info.RIP                  */
	unsigned long offset;      /* byte offset within code_block            */
};

#endif
