/*
 * exe.c — JIT sandbox execution engine (ported from BCD).
 *
 * Manages translated code blocks for delegated critical sections:
 *   - kd_exe_add()      allocate a vmalloc'd executable page for a new RIP
 *   - kd_exe_on_call()   execute the JIT sandbox for a futex-waiting task
 *   - kd_exe_on_call_hl_entry() executes JIT code for a queued waiter
 *
 * The JIT binary is written by the userspace daemon through /dev/kd_dev
 * (see sys.c).  At runtime the sandbox may report:
 *   - KD_EXE_CALL_MISS:  untranslated call → daemon extends tables, recompiles
 *   - KD_EXE_IJ_MISS:    untranslated indirect jump → same
 *   - KD_EXE_HOSTCALL:    allowlisted service → native dispatch, then JIT resume
 *   - KD_EXE_NORMAL:     futex syscall needs handling (wake/wait logic)
 *   - KD_EXE_INST_LIMIT: instruction count exhausted
 *
 * The end_points[] array lists kernel functions whose return indicates the
 * end of a critical section (e.g. _raw_spin_unlock, mutex_unlock).
 */
#include "exe.h"
#include "kd_exec.h"
#include "kd_segment.h"

#include <asm/current.h>
#include <asm/smap.h>
#include <asm/unistd.h>
#include <asm-generic/set_memory.h>
#include <linux/atomic.h>
#include <linux/futex.h>
#include <linux/kallsyms.h>
#include <linux/ktime.h>
#include <linux/moduleparam.h>
#include <linux/mutex.h>
#include <linux/sched.h>
#include <linux/spinlock.h>
#include <linux/vmalloc.h>

#include "utils.h"
#include "kd_lock.h"
#include "kd_mutex.h"
#include "kd_spinlock.h"
#include "kd_hostcall.h"

/*
 * Pre-allocated pool of executable code blocks.  kd_exe_add() is called from
 * the lock hooks which may run with interrupts disabled, so vmalloc and
 * set_memory_x cannot be used there.  All blocks are allocated and marked
 * executable during kd_exe_init().
 */
#define KD_CODE_BLOCK_POOL 64
#define KD_CODE_BLOCK_PAGES (KD_CODE_BLOCK_SIZE / PAGE_SIZE)
#define KD_EXE_HL_MAX_CONTINUATIONS 16
#define KD_EXE_HL_MAX_HOSTCALLS 16

/* One-shot high-level JIT fault injection for nested recovery tests. */
static int kd_jit_hl_fault_after_known_call;
module_param_named(jit_hl_fault_after_known_call,
		   kd_jit_hl_fault_after_known_call, int, 0644);
MODULE_PARM_DESC(
	jit_hl_fault_after_known_call,
	"Inject after a known JIT call: 1=call miss, 2=IJ miss, 3=inst limit");

static void *kd_code_block_pool[KD_CODE_BLOCK_POOL];
static int kd_code_block_free;
static atomic_t kd_code_block_gate = ATOMIC_INIT(0);

static void kd_code_block_gate_lock(void)
{
	while (atomic_cmpxchg_acquire(&kd_code_block_gate, 0, 1))
		cpu_relax();
}

static void kd_code_block_gate_unlock(void)
{
	atomic_set_release(&kd_code_block_gate, 0);
}

static unsigned long end_points[4];
static int end_point_count;
static unsigned long raw_spin_lock_addr;
static unsigned long raw_spin_unlock_addr;
static unsigned long mutex_lock_addr;
static unsigned long mutex_unlock_addr;

struct kd_hostcall_desc {
	enum kd_hostcall_id id;
	const char *symbol;
	unsigned long addr;
	unsigned int flags;
	int (*invoke)(struct pt_regs *regs);
};

static atomic64_t kd_hostcall_exits;
static atomic64_t kd_hostcall_executed;
static atomic64_t kd_hostcall_resumed;
static atomic64_t kd_hostcall_rejected;
static atomic64_t kd_hostcall_failed;
static atomic64_t kd_hostcall_limit;

static int kd_hostcall_invoke_ktime_get(struct pt_regs *regs)
{
	regs->ax = (unsigned long)ktime_to_ns(ktime_get());
	return 0;
}

static int kd_hostcall_invoke_ktime_get_ns(struct pt_regs *regs)
{
	regs->ax = (unsigned long)ktime_get_ns();
	return 0;
}

static struct kd_hostcall_desc kd_hostcalls[] = {
#define KD_HOSTCALL(name, service_id, service_symbol, service_flags) \
	{ KD_HOSTCALL_##name, #service_symbol, 0, service_flags,     \
	  kd_hostcall_invoke_##service_symbol },
#include "kd_hostcalls.def"
#undef KD_HOSTCALL
};

static const struct kd_hostcall_desc *kd_hostcall_lookup(unsigned long addr)
{
	int i;

	for (i = 0; i < ARRAY_SIZE(kd_hostcalls); i++)
		if (kd_hostcalls[i].addr && kd_hostcalls[i].addr == addr)
			return &kd_hostcalls[i];
	return NULL;
}

static int kd_hostcall_dispatch(struct pt_regs *regs)
{
	const unsigned int required_flags = KD_HOSTCALL_F_ATOMIC_SAFE |
					    KD_HOSTCALL_F_NO_TASK_CONTEXT |
					    KD_HOSTCALL_F_RETRY_SAFE;
	const struct kd_hostcall_desc *service;

	service = kd_hostcall_lookup(regs->ip);
	if (!service)
		return -ENOENT;
	if ((service->flags & required_flags) != required_flags)
		return -EPERM;
	return service->invoke(regs);
}

static struct kd_exe_info *kd_exes;

struct kd_exe_info *kd_get_exe(unsigned int pid, unsigned long ip)
{
	int pos;
	int probes;

	if (!kd_exes)
		return NULL;
	pos = zz_hash(pid, ip) % KD_MAX_EXE;
	for (probes = 0; probes < KD_MAX_EXE; probes++) {
		struct kd_exe_info *exe = &kd_exes[pos];

		if (READ_ONCE(exe->status_code) == KD_EXE_UNUSED ||
		    (READ_ONCE(exe->pid) == pid && READ_ONCE(exe->RIP) == ip))
			return exe;
		pos = (pos + 1) % KD_MAX_EXE;
	}
	return NULL;
}

const struct kd_exe_info *kd_exe_get_slot(unsigned int index)
{
	if (!kd_exes || index >= KD_MAX_EXE)
		return NULL;
	return &kd_exes[index];
}

bool kd_exe_is_ready(unsigned int pid, unsigned long ip)
{
	struct kd_exe_info *exe;

	if (!kd_exes || !ip)
		return false;
	exe = kd_get_exe(pid, ip);
	if (!exe)
		return false;
	if (smp_load_acquire(&exe->status_code) != KD_EXE_NORMAL)
		return false;
	return READ_ONCE(exe->pid) == pid && READ_ONCE(exe->RIP) == ip &&
	       READ_ONCE(exe->code_block) != NULL;
}

int kd_exe_init(void)
{
	int i, ret;

	/* Resolve unlock function addresses dynamically */
	end_point_count = 0;
	raw_spin_lock_addr = kallsyms_lookup_name("_raw_spin_lock");
	raw_spin_unlock_addr = kallsyms_lookup_name("_raw_spin_unlock");
	end_points[end_point_count] = raw_spin_unlock_addr;
	if (raw_spin_unlock_addr)
		end_point_count++;
	mutex_lock_addr = kallsyms_lookup_name("mutex_lock");
	mutex_unlock_addr = kallsyms_lookup_name("mutex_unlock");
	end_points[end_point_count] = mutex_unlock_addr;
	if (mutex_unlock_addr)
		end_point_count++;
	for (i = 0; i < end_point_count; i++)
		KD_PR_INFO("end_point[%d] = %lx", i, end_points[i]);
	if (mutex_lock_addr)
		KD_PR_INFO("mutex_lock addr = %lx", mutex_lock_addr);

	atomic64_set(&kd_hostcall_exits, 0);
	atomic64_set(&kd_hostcall_executed, 0);
	atomic64_set(&kd_hostcall_resumed, 0);
	atomic64_set(&kd_hostcall_rejected, 0);
	atomic64_set(&kd_hostcall_failed, 0);
	atomic64_set(&kd_hostcall_limit, 0);
	for (i = 0; i < ARRAY_SIZE(kd_hostcalls); i++) {
		kd_hostcalls[i].addr =
			kallsyms_lookup_name(kd_hostcalls[i].symbol);
		if (kd_hostcalls[i].addr)
			KD_PR_INFO(
				"hostcall service id=%u symbol=%s addr=%lx flags=%x\n",
				kd_hostcalls[i].id, kd_hostcalls[i].symbol,
				kd_hostcalls[i].addr, kd_hostcalls[i].flags);
		else
			KD_PR_INFO(
				"hostcall service unavailable id=%u symbol=%s\n",
				kd_hostcalls[i].id, kd_hostcalls[i].symbol);
	}

	kd_exes = vzalloc(sizeof(struct kd_exe_info) * KD_MAX_EXE);
	if (!kd_exes)
		return -ENOMEM;
	for (i = 0; i < KD_MAX_EXE; i++) {
		kd_exes[i].status_code = KD_EXE_UNUSED;
		kd_exes[i].code_block = NULL;
	}

	/* Lock hooks cannot allocate executable memory with IRQs disabled. */
	atomic_set(&kd_code_block_gate, 0);
	kd_code_block_free = 0;
	for (i = 0; i < KD_CODE_BLOCK_POOL; i++) {
		void *block = vmalloc(KD_CODE_BLOCK_SIZE);

		if (!block)
			continue;
		ret = set_memory_x((unsigned long)block, KD_CODE_BLOCK_PAGES);
		if (ret) {
			vfree(block);
			continue;
		}
		kd_code_block_pool[kd_code_block_free++] = block;
	}
	KD_PR_INFO("JIT code block pool ready: %d/%d\n", kd_code_block_free,
		   KD_CODE_BLOCK_POOL);
	if (!kd_code_block_free) {
		vfree(kd_exes);
		kd_exes = NULL;
		return -ENOMEM;
	}

	return 0;
}

void kd_exe_exit(void)
{
	int i;

	KD_PR_INFO(
		"kd_hostcall stats: exits=%lld executed=%lld resumed=%lld rejected=%lld failed=%lld limit=%lld\n",
		(long long)atomic64_read(&kd_hostcall_exits),
		(long long)atomic64_read(&kd_hostcall_executed),
		(long long)atomic64_read(&kd_hostcall_resumed),
		(long long)atomic64_read(&kd_hostcall_rejected),
		(long long)atomic64_read(&kd_hostcall_failed),
		(long long)atomic64_read(&kd_hostcall_limit));

	vfree(kd_exes);
	kd_exes = NULL;

	for (i = 0; i < KD_CODE_BLOCK_POOL; i++) {
		vfree(kd_code_block_pool[i]);
		kd_code_block_pool[i] = NULL;
	}
	kd_code_block_free = 0;
}

static int is_end_point(unsigned long addr)
{
	int i;

	for (i = 0; i < end_point_count; i++)
		if (addr == end_points[i])
			return 1;
	return 0;
}

static int is_outer_lock_unlock(struct pt_regs *regs,
				unsigned long outer_lock_addr)
{
	if (regs->ip != raw_spin_unlock_addr && regs->ip != mutex_unlock_addr)
		return 0;
	if (!outer_lock_addr)
		return 1;
	return regs->di == outer_lock_addr;
}

static int advance_after_known_call(struct pt_regs *regs)
{
	unsigned long return_ip;

	if (regs->sp == 0)
		return -EINVAL;

	return_ip = READ_ONCE(*(unsigned long *)regs->sp);
	regs->sp += sizeof(unsigned long);
	regs->ip = return_ip;
	return 1;
}

static int advance_and_save_continuation(struct kd_exec_frame *frame,
					 struct pt_regs *regs)
{
	int ret = advance_after_known_call(regs);

	if (ret > 0 && frame)
		kd_exec_frame_save_continuation(frame, regs);
	return ret;
}

static int handle_known_call(struct pt_regs *regs,
			     unsigned long outer_lock_addr)
{
	struct kd_exec_frame *frame = kd_exec_current_frame();
	int ret;

	/* Backend-specific lock stacks cannot represent mixed spin/mutex nesting.
	 * In particular, never enter a sleeping mutex service from a spin frame. */
	if (frame &&
	    ((frame->mutex_backend &&
	      (regs->ip == raw_spin_lock_addr || regs->ip == raw_spin_unlock_addr)) ||
	     (!frame->mutex_backend && mutex_lock_addr && mutex_unlock_addr &&
	      (regs->ip == mutex_lock_addr || regs->ip == mutex_unlock_addr))))
		return -EOPNOTSUPP;

	if (regs->ip == raw_spin_lock_addr) {
		ret = kd_spin_jit_nested_lock_ctx((raw_spinlock_t *)regs->di,
						  regs, frame);
		return ret;
	}

	if (regs->ip == raw_spin_unlock_addr) {
		if (regs->di == outer_lock_addr) {
			/* An early outer unlock is a real OOO release.  Keep executing
			 * until every nested lock has released, then finish A once. */
			if (frame &&
			    kd_exec_frame_has_unreleased_nested(frame)) {
				ret = kd_spin_jit_outer_unlock_ooo_ctx(
					(raw_spinlock_t *)regs->di, regs,
					frame);
				if (ret)
					return ret;
				return advance_and_save_continuation(frame,
								     regs);
			}
			return KD_EXE_KNOWN_OUTER_UNLOCK;
		}
		ret = kd_spin_jit_nested_unlock_ctx((raw_spinlock_t *)regs->di,
						    frame);
		return ret ? ret : advance_and_save_continuation(frame, regs);
	}

	if (!mutex_lock_addr || !mutex_unlock_addr)
		return 0;

	if (regs->ip != mutex_lock_addr && regs->ip != mutex_unlock_addr)
		return 0;

	if (regs->ip == mutex_unlock_addr) {
		if (regs->di == outer_lock_addr)
			return KD_EXE_KNOWN_OUTER_UNLOCK;
		ret = kd_mutex_jit_nested_unlock_ctx((struct mutex *)regs->di,
						    frame);
		if (!ret)
			kd_mutex_note_nested_jit();
	} else {
		return kd_mutex_jit_nested_lock_ctx((struct mutex *)regs->di,
						    regs, frame);
	}

	if (ret)
		return ret;

	return advance_and_save_continuation(frame, regs);
}

void kd_exe_add(int pid, unsigned long rip)
{
	void *mem = NULL;
	struct kd_exe_info *exe;

	kd_code_block_gate_lock();
	exe = kd_get_exe(pid, rip);
	if (!exe) {
		kd_code_block_gate_unlock();
		KD_PR_ERR("kd_exe_add: translation table exhausted\n");
		return;
	}
	if (exe->pid == pid && exe->RIP == rip) {
		kd_code_block_gate_unlock();
		return;
	}

	if (exe->status_code != KD_EXE_UNUSED)
		KD_PR_ERR(
			"translation slot collision: status=%d old=%d/%lx new=%d/%lx\n",
			exe->status_code, exe->pid, exe->RIP, pid, rip);

	/* The pool makes registration safe while a lock hook has IRQs disabled. */
	if (kd_code_block_free > 0)
		mem = kd_code_block_pool[--kd_code_block_free];

	if (!mem) {
		kd_code_block_gate_unlock();
		KD_PR_ERR("kd_exe_add: code block pool exhausted\n");
		return;
	}

	exe->pid = pid;
	exe->RIP = rip;
	exe->tgid = current->tgid;
	exe->code_block = mem;

	smp_store_release(&exe->status_code, KD_EXE_UNINIT);
	kd_code_block_gate_unlock();
	KD_PR_INFO("exe added %d %lx %d\n", pid, rip, current->tgid);
}

/* Legacy task-based entry: args carry waiter kernel GS and logical current. */
void kd_exe_on_call(struct task_struct *task, struct pt_regs *regs,
		    struct kd_exe_ret *result)
{
	unsigned long args[2];
	unsigned long origin_uaddr;
	unsigned long cur_uaddr;
	void (*translated)(struct pt_regs *regs, unsigned long *args);
	struct kd_exe_info *exe;
	int pid;
	int futex_op;

	if (!result)
		return;
	result->count = 0;
	result->ret = -EINVAL;
	if (!task || !regs)
		return;

	pid = task->pid;
	origin_uaddr = regs->di;
	args[0] = kd_kernel_gsbase_for_task(task);
	args[1] = (unsigned long)task;
	if (!args[0])
		return;

	exe = kd_get_exe(pid, regs->ip);
	if (!exe || smp_load_acquire(&exe->status_code) != KD_EXE_NORMAL ||
	    READ_ONCE(exe->RIP) != regs->ip || READ_ONCE(exe->pid) != pid ||
	    !READ_ONCE(exe->code_block)) {
		result->ret = -ENOENT;
		return;
	}

	translated = exe->code_block;
	regs->cx = regs->ip;
	regs->r11 = regs->flags;
	regs->orig_ax = regs->ax;
	regs->ax = 0;

	stac();
	translated(regs, args);

	if (args[0] == KD_EXE_NORMAL) {
		if (regs->ax != __NR_futex) {
			KD_PR_INFO("unsupported syscall %ld at %lx\n", regs->ax,
				   regs->ip);
			result->ret = -EOPNOTSUPP;
			goto out;
		}

		futex_op = regs->si & FUTEX_CMD_MASK;
		if (!(regs->si & FUTEX_PRIVATE_FLAG))
			KD_PR_INFO(
				"shared futex encountered in low-level JIT\n");
		cur_uaddr = regs->di;
		if (futex_op == FUTEX_WAKE) {
			result->uaddr[0] = cur_uaddr;
			result->wake_num[0] = regs->dx;
			result->count = 1;
			if (cur_uaddr == origin_uaddr) {
				regs->ip += 2;
				regs->cx = regs->ip;
				regs->r11 = regs->flags;
				regs->orig_ax = regs->ax;
				regs->ax = 1;
				result->ret = 1;
			} else {
				result->ret = 2;
			}
		} else if (futex_op == FUTEX_WAIT ||
			   futex_op == FUTEX_WAIT_BITSET) {
			result->ret = cur_uaddr == origin_uaddr ? 0 : 2;
		} else {
			KD_PR_INFO("unsupported futex operation %d\n",
				   futex_op);
			result->ret = -EOPNOTSUPP;
		}
	} else if (args[0] == KD_EXE_HOSTCALL) {
		KD_PR_INFO(
			"hostcall unsupported in low-level JIT: target=%lx\n",
			regs->ip);
		result->ret = -EOPNOTSUPP;
	} else if (args[0] == KD_EXE_CALL_MISS) {
		exe->tgt_addr = regs->ip;
		if (!is_end_point(exe->tgt_addr))
			smp_store_release(&exe->status_code, KD_EXE_CALL_MISS);
		result->ret = -EAGAIN;
	} else if (args[0] == KD_EXE_ERROR_INST) {
		KD_PR_INFO("unsupported translated instruction at %lx\n",
			   regs->ip);
		smp_store_release(&exe->status_code, KD_EXE_ERROR_INST);
		result->ret = -EILSEQ;
	} else if (args[0] == KD_EXE_INST_LIMIT) {
		KD_PR_INFO("translated instruction limit reached\n");
		result->ret = 3;
	} else {
		exe->tgt_addr = regs->ip;
		exe->jump_from = args[0];
		if (!is_end_point(exe->tgt_addr) &&
		    !is_end_point(exe->jump_from))
			smp_store_release(&exe->status_code, KD_EXE_IJ_MISS);
		result->ret = -EAGAIN;
	}

out:
	clac();
	mb();
}

int kd_exe_on_call_hl_entry(struct pt_regs *regs, unsigned long entry_ip,
			    unsigned long outer_lock_addr)
{
	struct kd_exec_frame *frame = kd_exec_current_frame();
	void (*translated)(struct pt_regs *regs, unsigned long *args);
	struct kd_exe_info *exe;
	unsigned long args[2];
	int continuation_count = 0;
	int hostcall_count = 0;
	bool resume_after_hostcall = false;
	int ret_flag;

	if (!regs || !frame || !kd_exec_frame_validate(frame) ||
	    !frame->gsbase || !frame->logical_task)
		return KD_EXE_RUN_ERROR;

	/* Kernel critical sections share translations by RIP, independent of PID. */
	exe = kd_get_exe(0, entry_ip);
	if (!exe || !kd_exe_is_ready(0, entry_ip)) {
		if (!exe) {
			KD_PR_INFO("translation table exhausted: entry=%lx\n",
				   entry_ip);
			return KD_EXE_NO_RUN;
		}
		KD_PR_INFO(
			"translation not ready: exe=%px status=%d entry=%lx ip=%lx pid=%d\n",
			exe, exe->status_code, exe->RIP, regs->ip, exe->pid);
		return KD_EXE_NO_RUN;
	}

	translated = exe->code_block;
	for (;;) {
		int call_ret;
		int fault_kind;

		args[0] = frame->gsbase;
		args[1] = (unsigned long)frame->logical_task;
		fault_kind =
			continuation_count > 0 ?
				xchg(&kd_jit_hl_fault_after_known_call, 0) :
				0;
		if (unlikely(fault_kind)) {
			KD_PR_INFO(
				"JIT injected runtime fault: kind=%d entry=%lx ip=%lx outer=%lx\n",
				fault_kind, entry_ip, regs->ip,
				outer_lock_addr);
			switch (fault_kind) {
			case 1:
				args[0] = KD_EXE_CALL_MISS;
				break;
			case 2:
				args[0] = entry_ip;
				break;
			case 3:
				args[0] = KD_EXE_INST_LIMIT;
				break;
			default:
				args[0] = KD_EXE_NORMAL;
				break;
			}
		} else {
			frame->executed = true;
			translated(regs, args);
			if (resume_after_hostcall)
				atomic64_inc(&kd_hostcall_resumed);
		}
		resume_after_hostcall = false;

		if (args[0] == KD_EXE_NORMAL) {
			KD_PR_INFO(
				"syscall unsupported in high-level JIT: nr=%ld ip=%lx\n",
				regs->ax, regs->ip);
			ret_flag = KD_EXE_RUN_ERROR;
		} else if (args[0] == KD_EXE_HOSTCALL) {
			atomic64_inc(&kd_hostcall_exits);
			if (hostcall_count >= KD_EXE_HL_MAX_HOSTCALLS ||
			    continuation_count >= KD_EXE_HL_MAX_CONTINUATIONS) {
				atomic64_inc(&kd_hostcall_limit);
				KD_PR_INFO(
					"JIT hostcall limit hit: entry=%lx target=%lx limit=%d\n",
					entry_ip, regs->ip,
					KD_EXE_HL_MAX_HOSTCALLS);
				ret_flag = KD_EXE_RUN_ERROR;
				break;
			}

			call_ret = kd_hostcall_dispatch(regs);
			if (call_ret) {
				if (call_ret == -ENOENT || call_ret == -EPERM)
					atomic64_inc(&kd_hostcall_rejected);
				else
					atomic64_inc(&kd_hostcall_failed);
				KD_PR_INFO(
					"JIT hostcall rejected: entry=%lx target=%lx ret=%d\n",
					entry_ip, regs->ip, call_ret);
				ret_flag = KD_EXE_RUN_ERROR;
				break;
			}
			atomic64_inc(&kd_hostcall_executed);

			call_ret = advance_and_save_continuation(
				kd_exec_current_frame(), regs);
			if (call_ret <= 0) {
				atomic64_inc(&kd_hostcall_failed);
				KD_PR_INFO(
					"JIT hostcall continuation failed: entry=%lx ip=%lx ret=%d\n",
					entry_ip, regs->ip, call_ret);
				ret_flag = KD_EXE_RUN_ERROR;
				break;
			}

			hostcall_count++;
			continuation_count++;
			resume_after_hostcall = true;
			continue;
		} else if (args[0] == KD_EXE_CALL_MISS) {
			if (outer_lock_addr &&
			    is_outer_lock_unlock(regs, outer_lock_addr)) {
				call_ret = handle_known_call(regs,
							     outer_lock_addr);
				if (call_ret == KD_EXE_KNOWN_OUTER_UNLOCK) {
					ret_flag = KD_EXE_RUN_TO_UNLOCK;
					break;
				}
				if (call_ret == KD_EXE_KNOWN_NATIVE) {
					ret_flag = KD_EXE_RUN_NATIVE;
					break;
				}
				if (call_ret > 0) {
					continuation_count++;
					continue;
				}
				ret_flag = KD_EXE_RUN_ERROR;
				break;
			}
			if (!outer_lock_addr && is_end_point(regs->ip)) {
				ret_flag = KD_EXE_RUN_TO_UNLOCK;
			} else {
				if (continuation_count >=
				    KD_EXE_HL_MAX_CONTINUATIONS) {
					KD_PR_INFO(
						"JIT continuation limit hit: entry=%lx ip=%lx outer=%lx limit=%d\n",
						entry_ip, regs->ip,
						outer_lock_addr,
						KD_EXE_HL_MAX_CONTINUATIONS);
					ret_flag = KD_EXE_RUN_ERROR;
					break;
				}

				call_ret =
					outer_lock_addr ?
						handle_known_call(
							regs, outer_lock_addr) :
						0;
				if (call_ret == KD_EXE_KNOWN_NATIVE) {
					ret_flag = KD_EXE_RUN_NATIVE;
					break;
				}
				if (call_ret == KD_EXE_KNOWN_OUTER_UNLOCK) {
					ret_flag = KD_EXE_RUN_TO_UNLOCK;
					break;
				}
				if (call_ret > 0) {
					continuation_count++;
					continue;
				}
				if (call_ret < 0) {
					KD_PR_INFO(
						"known-call handler failed: ip=%lx di=%lx outer=%lx ret=%d\n",
						regs->ip, regs->di,
						outer_lock_addr, call_ret);
					ret_flag = KD_EXE_RUN_ERROR;
					break;
				}

				exe->tgt_addr = regs->ip;
				if (!is_end_point(exe->tgt_addr))
					smp_store_release(&exe->status_code,
							  KD_EXE_CALL_MISS);
				/* Synthetic faults have no CALL frame and are not resumable. */
				ret_flag = fault_kind ? KD_EXE_RUN_ERROR :
							KD_EXE_RUN_NATIVE;
			}
		} else if (args[0] == KD_EXE_ERROR_INST) {
			KD_PR_INFO(
				"unsupported translated instruction: entry=%lx ip=%lx\n",
				entry_ip, regs->ip);
			smp_store_release(&exe->status_code, KD_EXE_ERROR_INST);
			ret_flag = KD_EXE_RUN_ERROR;
		} else if (args[0] == KD_EXE_INST_LIMIT) {
			KD_PR_INFO("translated instruction limit reached\n");
			ret_flag = KD_EXE_RUN_ERROR;
		} else {
			exe->tgt_addr = regs->ip;
			exe->jump_from = args[0];
			if (!is_end_point(exe->tgt_addr) &&
			    !is_end_point(exe->jump_from))
				smp_store_release(&exe->status_code,
						  KD_EXE_IJ_MISS);
			ret_flag = KD_EXE_RUN_ERROR;
		}
		break;
	}

	mb();
	return ret_flag;
}
