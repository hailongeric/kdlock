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

#include <asm-generic/set_memory.h>
#include <asm/current.h>
#include <asm/fsgsbase.h>
#include <asm/smap.h>
#include <linux/mm.h>
#include <linux/sched.h>
#include <linux/slab.h>
#include <linux/futex.h>
#include <linux/vmalloc.h>
#include <linux/sched/task_stack.h>
#include <asm/barrier.h>
#include <linux/sched/topology.h>
#include <linux/irqflags.h>
#include <linux/syscalls.h>
#include <asm-generic/resource.h>
#include <asm-generic/mman.h>
#include <linux/rwsem.h>
#include <linux/spinlock.h>
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

#define invalid_addr_file_path "/tmp/kd_iva"

const int KD_NUM_PG = 160;

/*
 * Pre-allocated pool of executable code blocks.  kd_exe_add() is called from
 * the lock hooks which may run with interrupts disabled, so vmalloc and
 * set_memory_x cannot be used there.  All blocks are allocated and marked
 * executable during kd_exe_init().
 */
#define KD_CODE_BLOCK_POOL 64
#define KD_CODE_BLOCK_SIZE  (4096 * KD_NUM_PG)

static void *kd_code_block_pool[KD_CODE_BLOCK_POOL];
static int kd_code_block_free;
static DEFINE_SPINLOCK(kd_code_block_lock);


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
	int pos = zz_hash(pid, ip) % KD_MAX_EXE;
	while (kd_exes[pos].status_code != KD_EXE_UNUSED && (kd_exes[pos].pid != pid || kd_exes[pos].RIP != ip))
		pos = (pos + 1) % KD_MAX_EXE;
	return &kd_exes[pos];
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
	end_point[end_point_count] = kallsyms_lookup_name("_raw_spin_unlock");
	if (end_point[end_point_count])
		end_point_count++;
	end_point[end_point_count] = kallsyms_lookup_name("mutex_unlock");
	if (end_point[end_point_count])
		end_point_count++;
	for (i = 0; i < end_point_count; i++)
		KD_PR_INFO("end_point[%d] = %lx", i, end_point[i]);

	kd_exes = (struct kd_exe_info*)vmalloc(sizeof(struct kd_exe_info) * KD_MAX_EXE);
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
	spin_lock_init(&kd_code_block_lock);
	for (i = 0; i < KD_CODE_BLOCK_POOL; i++) {
		kd_code_block_pool[i] = vmalloc(KD_CODE_BLOCK_SIZE);
		if (kd_code_block_pool[i])
			set_memory_x((unsigned long)kd_code_block_pool[i],
				     KD_NUM_PG);
	}
	kd_code_block_free = KD_CODE_BLOCK_POOL;
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

//! IN MY VERSION PID IS TGID
void kd_exe_add(int pid, unsigned long RIP) {
	void* mem = NULL;
	struct kd_exe_info* p = kd_get_exe(pid, RIP);

	if (p->pid == pid && p->RIP == RIP)  return;

	// if (!target_address(RIP)) return;

	if (p->status_code != KD_EXE_UNUSED)
		KD_PR_INFO( "exe add crash error %d %d %lx --- %d %lx\t%d---%d\n", p->status_code, p->pid, p->RIP, pid, RIP, zz_hash(p->pid, p->RIP) % KD_MAX_EXE, zz_hash(pid, RIP) % KD_MAX_EXE);

	/* Take a pre-allocated block from the pool (safe with IRQs off) */
	spin_lock(&kd_code_block_lock);
	if (kd_code_block_free > 0)
		mem = kd_code_block_pool[--kd_code_block_free];
	spin_unlock(&kd_code_block_lock);

	if (!mem) {
		KD_PR_ERR("kd_exe_add: code block pool exhausted\n");
		return;
	}

	p->pid = pid;
	p->RIP = RIP;
	p->tgid = current->tgid;

	p->code_block = mem;
	p->status_code = KD_EXE_UNINIT;
	p->success_cnt = 0;
	p->fail_cnt = 0;

	// if (p->fsbase == 0)
	// 	p->fsbase = x86_fsbase_read_cpu(); //! TODO dont use this register
	
	if(p->gsbase == 0){
		unsigned long gs_base;
    	asm volatile("rdgsbase %0" : "=r"(gs_base));
		p->gsbase = gs_base;
	}
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

		if (exe->status_code != KD_EXE_NORMAL || exe->RIP != regs->ip || exe->pid != pid) {
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
				exe->status_code = KD_EXE_CALL_MISS;
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
			exe->status_code = KD_EXE_NORMAL;
			r->ret = 3;
		}
		else if (1/*exe->success_cnt >= 0*/) {  // ij
			// exe->fail_cnt++;
			exe->tgt_addr = regs->ip;
			exe->jump_from = args[0];
			if (valid_address(exe->tgt_addr) && valid_address(exe->jump_from))
				exe->status_code = KD_EXE_IJ_MISS;
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



int kd_exe_on_call_hl(struct pt_regs* regs, void* outgoing_rsp_ptr) {
	int pid = current->pid;
	unsigned long args[2];
	void (*virt_ptr)(struct pt_regs* regs, unsigned long* args);
	struct kd_exe_info* exe;
	unsigned long rip = regs->ip;
	int ret_flag;


	exe = kd_get_exe(pid, rip);
	// spin_lock(&exe->lock);
	if (exe->status_code != KD_EXE_NORMAL || exe->RIP != regs->ip || exe->pid != pid) {
		if (exe->status_code == KD_EXE_NORMAL)
			KD_PR_INFO( "run error exe %d %lx %lx %d %d!\n", exe->status_code, exe->RIP, regs->ip, exe->pid, pid);
		// spin_unlock(&exe->lock);
		KD_PR_INFO("run error exe(%px) %d %lx %lx %d %d!\n", exe, exe->status_code, exe->RIP, regs->ip, exe->pid, pid);
		return KD_EXE_NO_RUN;
	}
	// ! todo pid is not correct

	virt_ptr = exe->code_block;
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

	// regs->cx = regs->ip;
	// regs->r11 = regs->flags;
	// regs->orig_ax = regs->ax;
	// regs->ax = 0;

	// pid = *((volatile int*)(0x5555556922a0));
	virt_ptr(regs, args);

	// barrier();
	// rdmsrl_safe(0xC4, &end);
	// barrier();

	if (args[0] == KD_EXE_NORMAL) {  // syscall
		KD_PR_INFO( "illegal syscall %ld %lx\n", regs->ax, regs->ip);
		ret_flag = KD_EXE_RUN_ERROR;
	}
	else if (args[0] == KD_EXE_CALL_MISS /*&& exe->success_cnt >= 0*/) {  // missing call

		if (is_end_point(regs->ip)) {
			ret_flag = KD_EXE_RUN_TO_UNLOCK;
		}else{
			exe->tgt_addr = regs->ip;  // ! todo avoid raw_spin_unlock 
			// exe->fail_cnt++;
			if (valid_address(exe->tgt_addr)) {
				// exe->miss_cnt++;
				// if (exe->miss_cnt < 10)
				exe->status_code = KD_EXE_CALL_MISS;
			}
			ret_flag = KD_EXE_RUN_ERROR;
		}
	}
	else if (args[0] == KD_EXE_INST_LIMIT) {
		KD_PR_INFO("inst limit\n");
		exe->status_code = KD_EXE_NORMAL;
		ret_flag = KD_EXE_RUN_ERROR;
	}
	else  {  // ij
		// exe->fail_cnt++;
		exe->tgt_addr = regs->ip;
		exe->jump_from = args[0];
		if (valid_address(exe->tgt_addr) && valid_address(exe->jump_from))
			exe->status_code = KD_EXE_IJ_MISS;
		ret_flag = KD_EXE_RUN_ERROR;
	}
	mb();
	return ret_flag;

}
