#ifndef EXE_H
#define EXE_H
#include "kd_image.h"
/* Registry and frame-backed executor interface. KD_EXE_RUN_* below are C
 * dispatcher results, not the similarly named wrapper/wire status constants
 * in exe_info.h; backends must preserve that distinction when handing off. */
#include "exe_info.h"
#include "kd_regs.h"
#include "kd_reached.h"

void kd_exe_add(int pid, unsigned long RIP, enum kd_exe_lock_kind kind);
void kd_exe_add_abi(int pid, unsigned long rip, enum kd_exe_lock_kind kind,
                    enum kd_entry_abi abi);
bool kd_exe_is_ready(unsigned int pid, unsigned long RIP);
struct kd_exe_info *kd_exe_find_ready(unsigned int pid, unsigned long ip);
/* Recheck a live registry slot without hashing. Neither a ready result nor
 * a stable slot pointer is an execution lease or an immutable image version. */
bool kd_exe_entry_is_ready(const struct kd_exe_info *exe, unsigned int pid,
			   unsigned long ip);
bool kd_exe_publish_status(struct kd_exe_info *exe, int status);
int kd_exe_init(void);
void kd_exe_exit(void);
void kd_exe_retire_all(void);

/*
 * Optional inclusive physical-owner wait, not the complete waiter suffix or
 * queue latency. These helpers do not change the two-word wrapper ABI.
 */
u64 kd_exe_native_timing_start(void);
void kd_exe_native_timing_end(bool mutex, u64 start);

/*
 * Wider envelope: start before borrowing/remote publication and finish after
 * owner wait, before frame cleanup. Only executor-local state crosses ACK.
 */
void kd_exe_native_handoff_timing_end(bool mutex, u64 start);

/*
 * Queue clocks stay outside JIT. Consume the node's timestamp before wake/reuse;
 * a refused JIT attempt leaves it pending until actual service or acquisition.
 */
u64 kd_exe_queue_timing_start(void);
void kd_exe_queue_timing_end(bool mutex, u64 *queued_at, u64 end);

#define KD_EXE_NO_RUN 2
#define KD_EXE_RUN_ERROR 3
#define KD_EXE_RUN_TO_UNLOCK 4
#define KD_EXE_KNOWN_OUTER_UNLOCK 5
#define KD_EXE_RUN_NATIVE 6
#define KD_EXE_NATIVE_DONE 7
#define KD_EXE_KNOWN_NATIVE 8
#define KD_EXE_KNOWN_SERVICE 9
#define KD_EXE_RUN_SERVICE 10
#define KD_EXE_RUN_YIELD 11
#define KD_EXE_RUN_NEED_OWNER 12
#define KD_EXE_KNOWN_ORIGIN_CALL 13
#define KD_EXE_RUN_ORIGIN_CALL 14
#define KD_EXE_RUN_ORIGIN_MEMORY 15
#define KD_EXE_RUN_HANDOFF 16

/* Kernel-only entry: pass the slot returned by find_ready and a validated
 * spin/mutex frame. Dispatch rechecks publication/admission after frame setup;
 * the admitted frame retains source residency through all continuations. */
struct kd_exec_frame;
/* Prepublication image eligibility; the caller separately retains its source
 * lease. The returned immutable image survives controlled session teardown. */
const struct kd_jit_image *kd_exe_capture_image(struct kd_exe_info *exe,
	unsigned long entry_ip);
/* Actual acquisition is already committed. Enter exactly the admitted image
 * without consulting fresh source/status admission again. */
int kd_exe_on_retained_entry(struct kd_exec_frame *frame,
	struct kd_exe_info *exe, const struct kd_jit_image *image);
int kd_exe_on_call_hl_entry(struct kd_exe_info *exe, struct kd_regs *regs,
			    unsigned long entry_ip,
			    unsigned long outer_lock_addr);
/* Resume the already bound immutable generation; no fresh source admission. */
int kd_exe_resume_retained(struct kd_exec_frame *frame);
int kd_exe_on_reached_entry(struct kd_exec_frame *frame);
void kd_exe_reached_ack(struct kd_exec_frame *frame);

/* Candidate scalar engine entry, separate from public acquisition/admission.
 * The caller owns stable state storage for this exact retained frame. No new
 * capture mode is activated until artifact/service joins are complete. */
int kd_exe_reached_begin(struct kd_exec_frame *frame,
	struct kd_reached_state *state, u64 budget);
enum kd_reached_result kd_exe_reached_run(struct kd_exec_frame *frame,
	struct kd_reached_state *state, unsigned int instruction_limit);

struct kd_exec_frame;
struct kd_jit_batch_call;
bool kd_exe_spin_batch_prepare(struct kd_exe_info *exe,
			       struct kd_exec_frame *frame,
			       struct kd_jit_batch_call *call);
/* Caller retains the prepared/bound frame through completion and retirement. */
bool kd_exe_spin_batch_completed(const struct kd_jit_batch_call *call,
				 const struct kd_exec_frame *frame);
int kd_exe_spin_batch_resume(struct kd_exe_info *exe,
			     const struct kd_jit_batch_call *call);

/* ABI2 mutex roots retain their owner ledger even on the simple path. */
bool kd_exe_mutex_batch_prepare(struct kd_exe_info *exe,
	struct kd_exec_frame *frame, struct kd_jit_batch_call *call);
bool kd_exe_mutex_batch_completed(const struct kd_jit_batch_call *call,
	const struct kd_exec_frame *frame);
int kd_exe_mutex_batch_resume(struct kd_exe_info *exe,
	const struct kd_jit_batch_call *call);

/* Resume a waiter after its critical section has already run in the sandbox. */
void jump_to_saved_regs(struct kd_regs *regs);
void jump_to_saved_regs_in_cs(struct kd_regs *regs);

struct kd_exe_info *kd_get_exe(unsigned int pid, unsigned long ip);
const struct kd_exe_info *kd_exe_get_slot(unsigned int index);

static inline unsigned int zz_hash(unsigned int pid, unsigned long ip)
{
	return (pid + (ip & 0xFFFF)) * 1000003;
}

#endif
