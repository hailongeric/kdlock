/*
 * exe.c — JIT sandbox execution engine (ported from BCD).
 *
 * Manages translated code blocks for delegated critical sections:
 *   - kd_exe_add()      allocate a vmalloc'd executable page for a new RIP
 *   - kd_exe_on_call()   execute the JIT sandbox for a futex-waiting task
 *   - kd_exe_on_call_hl() execute JIT sandbox on the combiner's behalf
 *
 * The JIT binary is written by the userspace daemon through /dev/kd_dev
 * (see sys.c).  At runtime the sandbox may report:
 *   - KD_EXE_CALL_MISS:  untranslated call → daemon extends tables, recompiles
 *   - KD_EXE_IJ_MISS:    untranslated indirect jump → same
 *   - KD_EXE_NORMAL:     futex syscall needs handling (wake/wait logic)
 *   - KD_EXE_INST_LIMIT: instruction count exhausted
 *
 * The end_point[] array lists kernel functions whose return indicates the
 * end of a critical section (e.g. _raw_spin_unlock, mutex_unlock).
 */
#include "exe.h"
#include "kd_exec.h"

#include <asm-generic/set_memory.h>
#include <asm/current.h>
#include <asm/fsgsbase.h>
#include <asm/smap.h>
#include <linux/mm.h>
#include <linux/moduleparam.h>
#include <linux/sched.h>
#include <linux/slab.h>
#include <linux/futex.h>
#include <linux/vmalloc.h>
#include <linux/sched/task_stack.h>
#include <asm/barrier.h>
#include <linux/sched/topology.h>
#include <linux/irqflags.h>
#include <linux/syscalls.h>
#include <linux/ktime.h>
#include <asm-generic/resource.h>
#include <asm-generic/mman.h>
#include <linux/rwsem.h>
#include <linux/spinlock.h>
#include <linux/mutex.h>
#include <asm/tlbflush.h>
#include <linux/kallsyms.h>
#include <linux/uaccess.h>
#include <asm/processor.h>
#include <linux/atomic.h>
#include <linux/kfifo.h>
#include <linux/cpumask.h>
#include <linux/numa.h>
#include <asm/tsc.h>
#include <linux/fs.h>

#include "utils.h"
#include "kd_lock.h"
#include "kd_spinlock.h"

#define invalid_addr_file_path "/tmp/kd_iva"

const int KD_NUM_PG = 160;

/*
 * Pre-allocated pool of executable code blocks.  kd_exe_add() is called from
 * the lock hooks which may run with interrupts disabled, so vmalloc and
 * set_memory_x cannot be used there.  All blocks are allocated and marked
 * executable during kd_exe_init().
 */
#define KD_CODE_BLOCK_POOL 64
#define KD_EXE_HL_MAX_CONTINUATIONS 16

/* One-shot high-level JIT fault injection for nested recovery tests. */
static int kd_jit_hl_fault_after_known_call;
module_param_named(jit_hl_fault_after_known_call,
		   kd_jit_hl_fault_after_known_call, int, 0644);
MODULE_PARM_DESC(jit_hl_fault_after_known_call,
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


extern long kd_success_cnt;
extern long kd_total_cnt;
extern long kd_success_wake_cnt;
atomic_t normal_wake_cnt;
atomic_t kd_d_lock;
atomic_t kd_com;
atomic_t kd_wake_state;
atomic_long_t count_uaddr_time;
atomic_long_t start_work_cycle;

atomic_t kd_is_delegating;
atomic_t int3_waiter_cnt;

spinlock_t int3_change_lock;

long long total_cycle = 0, total_cnt = 0;

unsigned long btc_t = 0;
unsigned long iva[32] = { 0 };
unsigned long end_point[4];
static int end_point_count;
static unsigned long raw_spin_lock_addr;
static unsigned long raw_spin_unlock_addr;
static unsigned long mutex_lock_addr;
static unsigned long mutex_unlock_addr;
static unsigned long ktime_get_addr;
static unsigned long ktime_get_ns_addr;

struct kd_exe_info* kd_exes;
struct kd_delegate_numanode** kd_numanodes;
struct kd_cycle_cnt* kd_cycle_cnts;
struct kd_uaddr_state* kd_uaddr_states;
struct kd_call_inst* kd_call_insts;
struct kd_thread* kd_threads;
int delegate_uaddr_cnt;

static loff_t get_file_size(struct file* file) {
	loff_t size;
	size = vfs_llseek(file, 0, SEEK_END);
	vfs_llseek(file, 0, SEEK_SET);
	return size;
}

struct kd_exe_info* kd_get_exe(unsigned int pid, unsigned long ip) {
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

struct kd_delegate_uaddrnode* kd_get_uaddrnode(unsigned long uaddr, struct kd_delegate_uaddrnode* u_list) {
	int pos = uaddr % KD_MAX_DELEGATE_UADDR;
	while (u_list[pos].uaddr != 0 && u_list[pos].uaddr != uaddr)
		pos = (pos + 1) % KD_MAX_DELEGATE_UADDR;
	if (u_list[pos].uaddr == 0)
		u_list[pos].uaddr = uaddr;
	return &u_list[pos];
}

struct kd_uaddr_state* kd_get_uaddr_state(unsigned long uaddr) {
	int pos = uaddr % KD_MAX_UADDR;
	while (kd_uaddr_states[pos].state != KD_UADDR_INIT && kd_uaddr_states[pos].uaddr != uaddr)
		pos = (pos + 1) % KD_MAX_UADDR;
	if (kd_uaddr_states[pos].state == KD_UADDR_INIT) {
		kd_uaddr_states[pos].uaddr = uaddr;
	}
	return &kd_uaddr_states[pos];
}

struct kd_call_inst* kd_get_call_inst(unsigned long addr) {
	int pos = addr % KD_MAX_CALL;
	while (kd_call_insts[pos].address != 0 && kd_call_insts[pos].address != addr)
		pos = (pos + 1) % KD_MAX_CALL;
	if (kd_call_insts[pos].address == 0)
		kd_call_insts[pos].address = addr;
	return &kd_call_insts[pos];
}

struct kd_thread* kd_get_thread(int pid) {
	int pos = pid % KD_MAX_THREAD;
	while (kd_threads[pos].pid != 0 && kd_threads[pos].pid != pid)
		pos = (pos + 1) % KD_MAX_THREAD;
	if (kd_threads[pos].pid == 0)
		kd_threads[pos].pid = pid;
	return &kd_threads[pos];
}

void kd_exe_init(void) {
	int i, j, k, ret, cpu, addr_num;
	unsigned long* addr_buffer;

	KD_PR_INFO("struct kd_delegate_uaddrnode %d", sizeof(struct kd_delegate_uaddrnode));

	/* Resolve unlock function addresses dynamically */
	end_point_count = 0;
	raw_spin_lock_addr = kallsyms_lookup_name("_raw_spin_lock");
	raw_spin_unlock_addr = kallsyms_lookup_name("_raw_spin_unlock");
	end_point[end_point_count] = raw_spin_unlock_addr;
	if (raw_spin_unlock_addr)
		end_point_count++;
	mutex_lock_addr = kallsyms_lookup_name("mutex_lock");
	mutex_unlock_addr = kallsyms_lookup_name("mutex_unlock");
	ktime_get_addr = kallsyms_lookup_name("ktime_get");
	ktime_get_ns_addr = kallsyms_lookup_name("ktime_get_ns");
	end_point[end_point_count] = mutex_unlock_addr;
	if (mutex_unlock_addr)
		end_point_count++;
	for (i = 0; i < end_point_count; i++)
		KD_PR_INFO("end_point[%d] = %lx", i, end_point[i]);
	if (mutex_lock_addr)
		KD_PR_INFO("mutex_lock addr = %lx", mutex_lock_addr);
	if (ktime_get_addr)
		KD_PR_INFO("ktime_get addr = %lx", ktime_get_addr);
	if (ktime_get_ns_addr)
		KD_PR_INFO("ktime_get_ns addr = %lx", ktime_get_ns_addr);

	kd_exes = vzalloc(sizeof(struct kd_exe_info) * KD_MAX_EXE);
	for (i = 0; i < KD_MAX_EXE; i++) {
		kd_exes[i].status_code = KD_EXE_UNUSED;
		kd_exes[i].code_block = NULL;
		kd_exes[i].gsbase = 0;
	}

	kd_numanodes = (struct kd_delegate_numanode**)vmalloc(sizeof(struct kd_delegate_numanode*) * num_online_nodes());
	for (i = 0;i < num_online_nodes();i++) {
		kd_numanodes[i] = (struct kd_delegate_numanode*)vmalloc_node(sizeof(struct kd_delegate_numanode), i);
		for (j = 0;j < KD_MAX_DELEGATE_UADDR;j++) {
			struct kd_delegate_uaddrnode* u_node = &kd_numanodes[i]->uaddr_node[j];
			u_node->uaddr = 0;
			atomic_long_set(&u_node->queue.q, 0);
			atomic_long_set(&u_node->wake_queue.q, 0);
			for (k = 0;k < 64;k++) {
				atomic_set(&u_node->completes[k].state, 0);
				u_node->completes[k].task = NULL;
				u_node->completes[k].regs = NULL;
				u_node->completes[k].rsp = 0;
			}
		}
	}

	kd_uaddr_states = (struct kd_uaddr_state*)vmalloc(sizeof(struct kd_uaddr_state) * KD_MAX_UADDR);
	for (i = 0;i < KD_MAX_UADDR;i++) {
		kd_uaddr_states[i].begin = 0;
		kd_uaddr_states[i].cnt = 0;
		kd_uaddr_states[i].end = 0;
		kd_uaddr_states[i].state = KD_UADDR_INIT;
		kd_uaddr_states[i].uaddr = 0;
		atomic_set(&kd_uaddr_states[i].mutex_origin_users, 0);
		atomic_set(&kd_uaddr_states[i].is_delegating, 0);
	}


	kd_call_insts = (struct kd_call_inst*)vmalloc(sizeof(struct kd_call_inst) * KD_MAX_CALL);
	for (i = 0;i < KD_MAX_CALL;i++) {
		kd_call_insts[i].address = 0;
		kd_call_insts[i].offset = 0;
	}

	kd_cycle_cnts = (struct kd_cycle_cnt*)vmalloc(sizeof(struct kd_cycle_cnt) * 64);
	for (i = 0;i < 64;i++) {	
		kd_cycle_cnts[i].min = INT_MAX;
		kd_cycle_cnts[i].total = 0;
		kd_cycle_cnts[i].total_cnt = 0;
		for (j = 0;j < 30;++j)
			kd_cycle_cnts[i].cnt[j] = 0;
	}
	delegate_uaddr_cnt = 0;

	atomic_set(&normal_wake_cnt, 0);
	atomic_set(&kd_d_lock, 0);
	atomic_set(&kd_com, 0);
	atomic_set(&kd_wake_state, 0);
	atomic_long_set(&start_work_cycle, 0);
	atomic_long_set(&count_uaddr_time, 2500000000);
	atomic_set(&kd_is_delegating, 0);
	atomic_set(&int3_waiter_cnt, 0);
	spin_lock_init(&int3_change_lock);

	/* Pre-allocate executable code blocks so kd_exe_add() never calls
	 * vmalloc or set_memory_x from inside a critical section. */
	atomic_set(&kd_code_block_gate, 0);
	kd_code_block_free = 0;
	for (i = 0; i < KD_CODE_BLOCK_POOL; i++) {
		void *block = vmalloc(KD_CODE_BLOCK_SIZE);

		if (!block)
			continue;
		ret = set_memory_x((unsigned long)block, KD_NUM_PG);
		if (ret) {
			vfree(block);
			continue;
		}
		kd_code_block_pool[kd_code_block_free++] = block;
	}
	KD_PR_INFO("JIT code block pool ready: %d/%d\n",
		   kd_code_block_free, KD_CODE_BLOCK_POOL);
}

void kd_exe_exit(void) {
	int i, j, cpu, range[30] = { 0 };
	unsigned long sum = 0, sum_cnt = 0;


	KD_PR_INFO("normal_wake_cnt: %d kd_d_lock: %d kd_com: %d kd_wake_state: %d", \
		atomic_read(&normal_wake_cnt), atomic_read(&kd_d_lock), atomic_read(&kd_com), atomic_read(&kd_wake_state));

	/* code_blocks are allocated from the pre-allocated pool, freed below */
	vfree(kd_exes);

	/* Free the pre-allocated code block pool */
	for (i = 0; i < KD_CODE_BLOCK_POOL; i++)
		vfree(kd_code_block_pool[i]);

	for (i = 0;i < 64;i++) {
		sum += kd_cycle_cnts[i].total;
		sum_cnt += kd_cycle_cnts[i].total_cnt;
		for (j = 0;j < 30;j++)
			range[j] += kd_cycle_cnts[i].cnt[j];
		if (kd_cycle_cnts[i].min < INT_MAX)
			KD_PR_INFO("min cycle: %lld", kd_cycle_cnts[i].min);
	}
	if (sum_cnt > 0)
		KD_PR_INFO("average cycle: %ld", sum / sum_cnt);
	for (i = 0;i < 30;i++)
		KD_PR_INFO("[%2d00 --- %2d00]: %d", i, i + 1, range[i]);

	vfree(kd_call_insts);

	vfree(kd_cycle_cnts);
	for (i = 0;i < num_online_nodes();i++)
		vfree(kd_numanodes[i]);
	vfree(kd_numanodes);

	for (i = 0;i < KD_MAX_UADDR;i++) {
		if ((kd_uaddr_states[i].state == KD_UADDR_DELEGATE || kd_uaddr_states[i].state == KD_UADDR_IGNORE) && kd_uaddr_states[i].cnt > 100)
			KD_PR_INFO("uaddr: %lx cycle: %ld state: %d cnt: %d", kd_uaddr_states[i].uaddr, kd_uaddr_states[i].end - kd_uaddr_states[i].begin, kd_uaddr_states[i].state, kd_uaddr_states[i].cnt);
	}
	vfree(kd_uaddr_states);

	// vfree(kd_threads);
	return;
}

extern void print_regs(char* s, int pid, struct pt_regs* regs);

int valid_address(unsigned long addr) {
	int length = sizeof(iva) / sizeof(iva[0]);
	int i;
	for (i = 0; i < length; i++) {
		if (addr == iva[i]) {
			return 0;
		}
	}
	for (i = 0; i < end_point_count; i++)
		if (addr == end_point[i])
			return 0;
	return 1;
}

static int is_end_point(unsigned long addr)
{
	int i;

	for (i = 0; i < end_point_count; i++)
		if (addr == end_point[i])
			return 1;
	return 0;
}

static int is_outer_lock_unlock(struct pt_regs *regs,
				unsigned long outer_lock_addr)
{
	if (regs->ip != raw_spin_unlock_addr &&
	    regs->ip != mutex_unlock_addr)
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

	if (regs->ip == raw_spin_lock_addr) {
		ret = kd_spin_jit_nested_lock_ctx((raw_spinlock_t *)regs->di,
						  regs, frame);
		return ret;
	}

	if (regs->ip == raw_spin_unlock_addr) {
		if (regs->di == outer_lock_addr) {
			/* An early outer unlock is a real OOO release.  Keep executing
			 * until every nested lock has released, then finish A once. */
			if (frame && kd_exec_frame_has_unreleased_nested(frame)) {
				ret = kd_spin_jit_outer_unlock_ooo_ctx(
					(raw_spinlock_t *)regs->di, regs, frame);
				if (ret)
					return ret;
				return advance_and_save_continuation(frame, regs);
			}
			return KD_EXE_KNOWN_OUTER_UNLOCK;
		}
		ret = kd_spin_jit_nested_unlock_ctx((raw_spinlock_t *)regs->di,
						    frame);
		return ret ? ret : advance_and_save_continuation(frame, regs);
	}

	if (regs->ip == ktime_get_addr) {
		regs->ax = ktime_to_ns(ktime_get());
		return advance_and_save_continuation(frame, regs);
	}

	if (regs->ip == ktime_get_ns_addr) {
		regs->ax = ktime_get_ns();
		return advance_and_save_continuation(frame, regs);
	}

	if (!mutex_lock_addr || !mutex_unlock_addr)
		return 0;

	if (regs->ip != mutex_lock_addr && regs->ip != mutex_unlock_addr)
		return 0;

	if (regs->ip == mutex_unlock_addr) {
		if (regs->di == outer_lock_addr)
			return KD_EXE_KNOWN_OUTER_UNLOCK;
		ret = kd_mutex_jit_nested_unlock((struct mutex *)regs->di);
	} else {
		ret = kd_mutex_jit_nested_lock((struct mutex *)regs->di);
	}

	if (ret)
		return ret;

	return advance_and_save_continuation(frame, regs);
}

//! IN MY VERSION PID IS TGID
void kd_exe_add(int pid, unsigned long RIP) {
	void* mem = NULL;
	struct kd_exe_info* p;

	kd_code_block_gate_lock();
	p = kd_get_exe(pid, RIP);
	if (!p) {
		kd_code_block_gate_unlock();
		KD_PR_ERR("kd_exe_add: translation table exhausted\n");
		return;
	}
	if (p->pid == pid && p->RIP == RIP) {
		kd_code_block_gate_unlock();
		return;
	}

	// if (!target_address(RIP)) return;

	if (p->status_code != KD_EXE_UNUSED)
		KD_PR_INFO( "exe add crash error %d %d %lx --- %d %lx\t%d---%d\n", p->status_code, p->pid, p->RIP, pid, RIP, zz_hash(p->pid, p->RIP) % KD_MAX_EXE, zz_hash(pid, RIP) % KD_MAX_EXE);

	/* Take a pre-allocated block from the pool (safe with IRQs off) */
	if (kd_code_block_free > 0)
		mem = kd_code_block_pool[--kd_code_block_free];

	if (!mem) {
		kd_code_block_gate_unlock();
		KD_PR_ERR("kd_exe_add: code block pool exhausted\n");
		return;
	}

	p->pid = pid;
	p->RIP = RIP;
	p->tgid = current->tgid;

	p->code_block = mem;
	p->success_cnt = 0;
	p->fail_cnt = 0;

	// if (p->fsbase == 0)
	// 	p->fsbase = x86_fsbase_read_cpu(); //! TODO dont use this register
	
	if(p->gsbase == 0){
		unsigned long gs_base;
    	asm volatile("rdgsbase %0" : "=r"(gs_base));
		p->gsbase = gs_base;
	}
	smp_store_release(&p->status_code, KD_EXE_UNINIT);
	kd_code_block_gate_unlock();
	// struct kd_thread* t = kd_get_thread(pid);
	// t->fsbase = x86_fsbase_read_cpu();


	KD_PR_INFO("exe added %d %lx %d\n", pid, RIP, current->tgid);
	//  printk(KERN_EMERG "exe added %d %lx %d\n", pid, RIP, current->tgid);
}

/*args is used to pass arguments to code block
  For input, the first arg is fs, and second being gs.
  For output, the first is return_code, or the address of indirect jump.
*/
void kd_exe_on_call(struct task_struct* task, struct pt_regs* regs, struct kd_exe_ret* r) {
	unsigned long long begin, end;

	// int cpu_id = smp_processor_id();
	// begin = rdtsc_ordered();

	// if (task->exit_state == EXIT_DEAD || task->exit_state == EXIT_ZOMBIE) {
	// 	KD_PR_INFO("[kd_exe_on_call] task is dead");
	// 	r->ret = -0xdead;
	// 	return;
	// }
	volatile int pid = task->pid;
	int tid = task->tgid;

	unsigned long args[2];
	void (*virt_ptr)(struct pt_regs* regs, unsigned long* args);
	struct kd_exe_info* exe;
	// struct kd_thread* th;
	unsigned long cur_uaddr;
	r->count = 0;

	unsigned long origin_uaddr = regs->di;

	while (1) {  // chaining
		// if (regs->ip == 0x7ffff7fb4330)
		// 	pid = task->tgid;

		unsigned long rip = regs->ip;


		exe = kd_get_exe(pid, rip);
		// spin_lock(&exe->lock);

		if (!exe || exe->status_code != KD_EXE_NORMAL ||
		    exe->RIP != regs->ip || exe->pid != pid) {
			if (!exe) {
				r->ret = -1;
				return;
			}
			if (exe->status_code == KD_EXE_NORMAL)
				KD_PR_INFO( "run error exe %lx %lx %lx %d %d!\n", exe->status_code, exe->RIP, regs->ip, exe->pid, pid);
			r->ret = -1;
			// spin_unlock(&exe->lock);
			return;
		}

		// th = kd_get_thread(pid);

		// kd_total_cnt++;

		virt_ptr = exe->code_block;

		// if (exe->fsbase == 0)
		// 	KD_PR_INFO("[exe on call]\tfsbase is zero !!!");

		if (exe->gsbase == 0)
			KD_PR_INFO("[exe on call]\tgsbase is zero !!!");

		// args[0] = exe->fsbase;  //!
		args[0] = exe->gsbase;  //!
		// if (th->fsbase == 0)
		// 	KD_PR_INFO("[exe on call]\tfsbase is zero !!!");
		// args[0] = th->fsbase;
		args[1] = 0;

		regs->cx = regs->ip;
		regs->r11 = regs->flags;
		regs->orig_ax = regs->ax;
		regs->ax = 0;

		// barrier();
		// rdmsrl_safe(0xC4, &begin);
		// barrier();

		stac();
		// pid = *((volatile int*)(0x5555556922a0));
		// ! important call 
		virt_ptr(regs, args);

		// barrier();
		// rdmsrl_safe(0xC4, &end);
		// barrier();

		if (args[0] == KD_EXE_NORMAL) {  // syscall
			if (regs->ax == 202) {  // legal syscall
				int kd_op = regs->si & 0x7f;
				if (!((regs->si) & FUTEX_PRIVATE_FLAG))
					KD_PR_INFO( "kd not shared flag\n");
				if (kd_op == 1) { // futex wake

					cur_uaddr = regs->di;
					r->uaddr[r->count] = cur_uaddr;
					r->wake_num[r->count] = regs->dx;
					r->count++;
					// exe->success_cnt++;
					// kd_success_cnt++;
					// kd_success_wake_cnt++;
					// exe->success_cnt++;
					// KD_PR_INFO( "wake number: %lx uaddr: %lx ip:%lx\n", regs->dx, origin_uaddr, regs->ip);
					if (cur_uaddr == origin_uaddr) { //wake same uaddr
						regs->ip += 2;
						regs->cx = regs->ip;
						regs->r11 = regs->flags;
						regs->orig_ax = regs->ax;
						//regs->ax = -38;
						regs->ax = 1;
						r->ret = 1;

						// end = rdtsc_ordered();
						// unsigned long cost = end - begin;
						// if (cost < 3000UL)
						// 	++kd_cycle_cnts[cpu_id].cnt[cost / 100UL];
						// else
						// 	++kd_cycle_cnts[cpu_id].cnt[29];
						// kd_cycle_cnts[cpu_id].min = kd_cycle_cnts[cpu_id].min < cost ? kd_cycle_cnts[cpu_id].min : cost;
						// kd_cycle_cnts[cpu_id].total += cost;
						// ++kd_cycle_cnts[cpu_id].total_cnt;

					}
					else { //wake another uaddr
						// regs->ip += 2;
						// regs->cx = regs->ip;
						// regs->r11 = regs->flags;
						// regs->orig_ax = regs->ax;
						// regs->ax = 1;
						// kd_exe_add(pid, regs->ip);
						// KD_PR_INFO( "not same wake.ip: %lx wake number: %lx uaddr: %lx ip:%lx rsi: %lx\n", exe->RIP, regs->dx, origin_uaddr, regs->ip, regs->si);
						// continue;
						r->ret = 2;
					}
				}
				else if (kd_op == 0 || kd_op == 9) { //futex wait
					cur_uaddr = regs->di;
					// kd_success_cnt++;
					if (cur_uaddr == origin_uaddr) {
						// regs->ip += 2;
						// regs->cx = regs->ip;
						// regs->r11 = regs->flags;
						// regs->orig_ax = regs->ax;
						// regs->ax = 0;
						r->ret = 0;


					}
					else {
						// KD_PR_INFO( "not same uaddr wait !");
						r->ret = 2;
					}
				}
				else {
					KD_PR_INFO( "illegal kd_op %d\n", kd_op);
					// exe->fail_cnt++;
					r->ret = -4;
				}
			}
			else {
				KD_PR_INFO( "illegal syscall %ld %lx\n", regs->ax, regs->ip);
				// exe->fail_cnt++;
				r->ret = -4;
			}
		}
		else if (args[0] == KD_EXE_CALL_MISS /*&& exe->success_cnt >= 0*/) {  // missing call
			exe->tgt_addr = regs->ip;
			// exe->fail_cnt++;
			if (valid_address(exe->tgt_addr)) {
				// exe->miss_cnt++;
				// if (exe->miss_cnt < 10)
				smp_store_release(&exe->status_code, KD_EXE_CALL_MISS);
				// else {
				// 	for (int i = 0;i < 10;i++) {
				// 		if (iva[i] == exe->tgt_addr)
				// 			break;
				// 		if (iva[i] == 0) {
				// 			iva[i] = exe->tgt_addr;
				// 			break;
				// 		}
				// 	}
				// }
			}
			// exe->fail_cnt++;
			r->ret = -1;
		}
		else if (args[0] == KD_EXE_INST_LIMIT) {
			KD_PR_INFO("inst limit\n");
			smp_store_release(&exe->status_code, KD_EXE_NORMAL);
			r->ret = 3;
		}
		else if (1/*exe->success_cnt >= 0*/) {  // ij
			// exe->fail_cnt++;
			exe->tgt_addr = regs->ip;
			exe->jump_from = args[0];
			if (valid_address(exe->tgt_addr) && valid_address(exe->jump_from))
				smp_store_release(&exe->status_code, KD_EXE_IJ_MISS);
			// exe->fail_cnt++;
			r->ret = -1;
		}
		break;
	}
	// spin_unlock(&exe->lock);
	// r->number++;
	clac();
	mb();

}



int kd_exe_on_call_hl_entry(struct pt_regs* regs, void* outgoing_rsp_ptr,
			    unsigned long entry_ip,
			    unsigned long outer_lock_addr) {
	unsigned long args[2];
	void (*virt_ptr)(struct pt_regs* regs, unsigned long* args);
	struct kd_exe_info* exe;
	int ret_flag;
	int call_ret;
	int continuation_count = 0;
	int fault_kind;


	exe = kd_get_exe(0, entry_ip);  /* rip-only lookup, same code for all */
	// spin_lock(&exe->lock);
	if (!exe || !kd_exe_is_ready(0, entry_ip)) {
		if (!exe) {
			KD_PR_INFO("run error: translation table exhausted entry=%lx\n",
				   entry_ip);
			return KD_EXE_NO_RUN;
		}
		KD_PR_INFO("run error exe(%px) %d %lx %lx %d %d!\n", exe, exe->status_code, exe->RIP, regs->ip, exe->pid, 0);
		return KD_EXE_NO_RUN;
	}
	// ! todo pid is not correct

	virt_ptr = exe->code_block;
	while (1) {
	// if (exe->fsbase == 0)
	// 	KD_PR_INFO("[exe on call]\tfsbase is zero !!!");

	if (exe->gsbase == 0)
		KD_PR_INFO("[exe on call]\tgsbase is zero !!!");

	// args[0] = exe->fsbase; //!
	args[0] = exe->gsbase; //!
	// if (th->fsbase == 0)
	// 	KD_PR_INFO("[exe on call]\tfsbase is zero !!!");
	// args[0] = th->fsbase;
	args[1] = 0;
	fault_kind = continuation_count > 0 ?
		xchg(&kd_jit_hl_fault_after_known_call, 0) : 0;
	if (unlikely(fault_kind)) {
		KD_PR_INFO("JIT injected runtime fault: kind=%d entry=%lx ip=%lx outer=%lx\n",
			   fault_kind, entry_ip, regs->ip, outer_lock_addr);
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
		virt_ptr(regs, args);
	}

	// regs->cx = regs->ip;
	// regs->r11 = regs->flags;
	// regs->orig_ax = regs->ax;
	// regs->ax = 0;

	// pid = *((volatile int*)(0x5555556922a0));
	// barrier();
	// rdmsrl_safe(0xC4, &end);
	// barrier();

	if (args[0] == KD_EXE_NORMAL) {  // syscall
		KD_PR_INFO( "illegal syscall %ld %lx\n", regs->ax, regs->ip);
		ret_flag = KD_EXE_RUN_ERROR;
	}
	else if (args[0] == KD_EXE_CALL_MISS /*&& exe->success_cnt >= 0*/) {  // missing call

		if (outer_lock_addr && is_outer_lock_unlock(regs, outer_lock_addr)) {
			call_ret = handle_known_call(regs, outer_lock_addr);
			if (call_ret == KD_EXE_KNOWN_OUTER_UNLOCK) {
				ret_flag = KD_EXE_RUN_TO_UNLOCK;
				break;
			}
			if (call_ret > 0) {
				continuation_count++;
				args[0] = exe->gsbase;
				args[1] = 0;
				continue;
			}
			ret_flag = KD_EXE_RUN_ERROR;
			break;
		} else if (!outer_lock_addr && is_end_point(regs->ip)) {
			ret_flag = KD_EXE_RUN_TO_UNLOCK;
		} else {
			if (continuation_count >=
			    KD_EXE_HL_MAX_CONTINUATIONS) {
				KD_PR_INFO("mutex JIT continuation limit hit: entry=%lx ip=%lx outer=%lx limit=%d\n",
					   entry_ip, regs->ip,
					   outer_lock_addr,
					   KD_EXE_HL_MAX_CONTINUATIONS);
				ret_flag = KD_EXE_RUN_ERROR;
				break;
			}
			call_ret = outer_lock_addr ?
				handle_known_call(regs, outer_lock_addr) : 0;
			if (call_ret == KD_EXE_KNOWN_OUTER_UNLOCK) {
				ret_flag = KD_EXE_RUN_TO_UNLOCK;
				break;
			}
			if (call_ret > 0) {
				continuation_count++;
				args[0] = exe->gsbase;
				args[1] = 0;
				continue;
			}
			if (call_ret < 0) {
				KD_PR_INFO("mutex known-call handler failed: ip=%lx di=%lx outer=%lx ret=%d\n",
					   regs->ip, regs->di, outer_lock_addr,
					   call_ret);
				ret_flag = KD_EXE_RUN_ERROR;
				break;
			}
			exe->tgt_addr = regs->ip;  // ! todo avoid raw_spin_unlock 
			// exe->fail_cnt++;
			if (valid_address(exe->tgt_addr)) {
				// exe->miss_cnt++;
				// if (exe->miss_cnt < 10)
				smp_store_release(&exe->status_code, KD_EXE_CALL_MISS);
			}
			ret_flag = KD_EXE_RUN_ERROR;
		}
	}
	else if (args[0] == KD_EXE_INST_LIMIT) {
		KD_PR_INFO("inst limit\n");
		smp_store_release(&exe->status_code, KD_EXE_NORMAL);
		ret_flag = KD_EXE_RUN_ERROR;
	}
	else  {  // ij
		// exe->fail_cnt++;
		exe->tgt_addr = regs->ip;
		exe->jump_from = args[0];
		if (valid_address(exe->tgt_addr) && valid_address(exe->jump_from))
			smp_store_release(&exe->status_code, KD_EXE_IJ_MISS);
		ret_flag = KD_EXE_RUN_ERROR;
	}
	break;
	}
	mb();
	return ret_flag;

}

int kd_exe_on_call_hl(struct pt_regs* regs, void* outgoing_rsp_ptr) {
	return kd_exe_on_call_hl_entry(regs, outgoing_rsp_ptr, regs->ip, 0);
}
