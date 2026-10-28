// SPDX-License-Identifier: GPL-2.0
/* Real production transitions; physical primitives, task routing and scheduling
 * are explicit substitutes. The live probe must still prove kernel execution. */
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef unsigned long atomic_long_t;
typedef unsigned int atomic_t;
typedef unsigned int raw_spinlock_t;
struct optimistic_spin_queue { atomic_t tail; };
struct task_struct { int pid; } __attribute__((aligned(8)));
struct list_head { struct list_head *next, *prev; };
#include "kd_regs.h"
#define KD_MUTEX_CUSTODY_LOCKS 8
#define KD_MUTEX_DIAG_MEMBER
#define KD_MUTEX_OWNER_FLAGS 7UL
#define U64_MAX UINT64_MAX
#define EXPORT_SYMBOL_GPL(name)
#define pr_info(...) do { } while (0)
#include "custody_types.h"

static struct task_struct ctask = {1}, wtask = {2};
static _Thread_local struct task_struct *current;
static _Thread_local unsigned long kd_mutex_custody_slots;
static _Thread_local struct { unsigned long node_slots; } kd_mutex_shadows;
static _Thread_local unsigned int pins, migration;
static struct kd_mutex lock, nested[10];
static struct kd_mutex_node cnode, wnode, next_node, deferred;
static struct kd_mutex_node *route;
static struct kd_exec_frame frame;
static struct kd_exec_context context;
static struct kd_mutex_batch batch;
static int source_refs, source_closed, task_puts, pops, releases, combines;
static unsigned int mode, shape, checks, failures;
static bool delayed_link;
static struct kd_regs captured;

#define CHECK(c) do { __atomic_add_fetch(&checks,1,__ATOMIC_RELAXED); if (!(c)) { \
    __atomic_add_fetch(&failures,1,__ATOMIC_RELAXED); \
    fprintf(stderr,"FAIL custody mode=%u shape=%u line=%d: %s\n",mode,shape,__LINE__,#c); } } while(0)
#define BUG_ON(c) do { if (c) { CHECK(!(c)); exit(1); } } while(0)
#define READ_ONCE(x) __atomic_load_n(&(x),__ATOMIC_RELAXED)
#define WRITE_ONCE(x,v) __atomic_store_n(&(x),(v),__ATOMIC_RELAXED)
#define smp_load_acquire(p) __atomic_load_n((p),__ATOMIC_ACQUIRE)
#define smp_store_release(p,v) __atomic_store_n((p),(v),__ATOMIC_RELEASE)
#define BIT(n) (1UL << (n))
#define this_cpu_read(x) (x)
#define this_cpu_or(x,v) ((x) |= (v))
#define this_cpu_and(x,v) ((x) &= (v))
#define atomic_long_read(p) READ_ONCE(*(p))
#define list_empty(h) ((h)->next == (h))
#define cmpxchg(p,o,n) ({ __typeof__(*(p)) old_=(o); __atomic_compare_exchange_n((p),&old_,(n),false,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST); old_; })
static void cpu_relax(void)
{
	if (current == &ctask && delayed_link) {
		delayed_link = false;
		smp_store_release(&wnode.next, &next_node);
	}
	sched_yield();
}
static struct kd_mutex_node *kd_mutex_decode_tail(u32 tail)
{
	if (tail == (u32)cnode.tail) return &cnode;
	if (tail == (u32)wnode.tail) return &wnode;
	if (tail == (u32)next_node.tail) return &next_node;
	BUG_ON(true); return NULL;
}
static u32 kd_mutex_xchg_tail(struct kd_mutex *mutex, u32 tail)
{
	return __atomic_exchange_n(&mutex->delegation_tail, tail, __ATOMIC_SEQ_CST);
}
static u64 kd_exe_queue_timing_start(void) { return 7; }
bool kd_source_frame_get(void)
{
	if (READ_ONCE(source_closed)) return false;
	__atomic_add_fetch(&source_refs,1,__ATOMIC_SEQ_CST); return true;
}
void kd_source_frame_put(void)
{
	BUG_ON(__atomic_sub_fetch(&source_refs,1,__ATOMIC_SEQ_CST) < 0);
}
bool kd_mutex_task_custody_reserve(struct task_struct *task, struct kd_mutex_node *node)
{
	CHECK(task == &wtask && node == &wnode);
	return cmpxchg(&route,NULL,node) == NULL;
}
struct kd_mutex_node *kd_mutex_task_custody(struct task_struct *task)
{
	return task == &wtask ? READ_ONCE(route) : NULL;
}
void kd_mutex_task_custody_clear(struct task_struct *task, struct kd_mutex_node *node)
{
	CHECK(task == &wtask && cmpxchg(&route,node,NULL) == node);
}
void kd_mutex_task_put(struct task_struct *task)
{
	CHECK(task == &wtask && !route); task_puts++;
}
int kd_mutex_transfer_owner(struct kd_mutex *mutex, struct task_struct *next)
{
	CHECK(current == &ctask && next == &wtask);
	CHECK((mutex->owner & ~7UL) == (unsigned long)&ctask);
	smp_store_release(&mutex->owner, (unsigned long)next | (mutex->owner & 7UL) | 4UL);
	return 0;
}
int kd_mutex_transfer_pickup(struct kd_mutex *mutex)
{
	CHECK(current == &wtask && smp_load_acquire(&mutex->owner) == ((unsigned long)&wtask | 5UL));
	WRITE_ONCE(mutex->owner, (unsigned long)&wtask | 1UL); return 0;
}
bool kd_mutex_delegation_owned(struct kd_mutex *mutex, struct task_struct *task)
{
	return (mutex->owner & ~7UL) == (unsigned long)task && !(mutex->owner & 4UL);
}
bool kd_exec_mutex_transfer_allowed(const struct kd_exec_frame *f)
{
	return f == &frame && !f->mutex_mixed.transferred;
}
bool kd_exec_frame_remote_pending(const struct kd_exec_frame *f)
{
	return f->remote_result != KD_EXEC_REMOTE_IDLE;
}
bool kd_exec_frame_validate(const struct kd_exec_frame *f) { return f != NULL; }
int kd_exec_frame_state(const struct kd_exec_frame *f) { return f->state; }
static void kd_exec_frame_set_state(struct kd_exec_frame *f,int state) { f->state=state; }
static int kd_exec_invariant_failure(void) { CHECK(false); return -EINVAL; }
bool kd_exec_frame_has_unreleased_nested(const struct kd_exec_frame *f) { return f->jit_lock_depth > 1; }
bool kd_exec_frame_can_complete(const struct kd_exec_frame *f) { return f->outer_unlock_seen; }
int kd_exec_frame_lock_mark_released(struct kd_exec_frame *f,unsigned long address)
{
	CHECK(address == f->outer_lock_addr); f->jit_lock_released[0]=true; return 0;
}
static struct kd_exec_context *kd_exec_current_context(void) { return &context; }
static unsigned int preempt_count(void) { return pins; }
static void preempt_disable(void) { pins++; }
static void preempt_enable(void) { BUG_ON(!pins); pins--; }
static void migrate_enable(void) { BUG_ON(!migration); migration--; }
static bool irqs_disabled(void) { return mode == 5; }
bool kd_exec_context_occupied(void) { return mode == 6; }
int _kd_mutex_unlock_checked(struct kd_mutex *mutex)
{
	CHECK(current == &wtask && kd_mutex_delegation_owned(mutex,current));
	CHECK(READ_ONCE(source_refs) > 0); mutex->owner=0; releases++; return 0;
}
static void kd_mutex_release_node(struct kd_mutex_node *node)
{
	CHECK(node == &wnode && !node->counted_lock && !route && !lock.owner);
	CHECK(!kd_mutex_custody_slots && pins > 0 && migration == 1);
	kd_mutex_shadows.node_slots &= ~BIT(node->slot); node->lock=NULL;
}
static enum kd_mutex_batch_result kd_mutex_run_combiner(struct kd_mutex *mutex,
	struct kd_mutex_node *head, struct kd_mutex_node *own, bool after_body)
{
	CHECK(after_body && !own && current == &wtask && head != &wnode);
	CHECK(wnode.custody.phase == KD_MUTEX_CUSTODY_COMBINING && !context.depth);
	combines++; BUG_ON(_kd_mutex_unlock_checked(mutex));
	smp_store_release(&head->locked,0);
	return KD_MUTEX_BATCH_RELEASED;
}
#include "custody_queue.h"
#include "custody_production.h"

static void setup(void)
{
	current=&ctask; pins=1; migration=1;
	memset(&lock,0,sizeof(lock)); memset(&frame,0,sizeof(frame));
	memset(&context,0,sizeof(context)); memset(&batch,0,sizeof(batch));
	memset(&cnode,0,sizeof(cnode)); memset(&wnode,0,sizeof(wnode));
	memset(&next_node,0,sizeof(next_node)); memset(&deferred,0,sizeof(deferred));
	route=NULL; source_refs=1; source_closed=0; task_puts=pops=releases=combines=0;
	lock.owner=(unsigned long)&ctask | 1UL; lock.delegation_tail=wnode.tail=2;
	cnode.tail=1; next_node.tail=3; cnode.slot=0; wnode.slot=1;
	cnode.lock=wnode.lock=&lock; cnode.counted_lock=wnode.counted_lock=&lock;
	cnode.count_seq=wnode.count_seq=2; cnode.task_struct_ptr=&ctask; wnode.task_struct_ptr=&wtask;
	cnode.entry_abi=wnode.entry_abi=KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
	cnode.packet_state=wnode.packet_state=KD_PACKET_MINIMAL;
	cnode.regs.ip=0xcafe; cnode.regs.sp=0x1000; wnode.locked=1; next_node.locked=1; deferred.locked=1;
	frame.mutex_backend=frame.complex_ready=frame.batch_lease=true;
	frame.entry_abi=KD_ENTRY_ABI_MUTEX_CLOBBER_V1; frame.logical_task=&wtask;
	frame.outer_lock_addr=(unsigned long)&lock; frame.jit_lock_addr[0]=(unsigned long)&lock;
	frame.jit_lock_node[0]=&lock; frame.jit_lock_kind[0]=KD_EXEC_LOCK_QUEUE_OWNER;
	frame.jit_lock_depth=frame.held_lock_depth=1; frame.state=KD_EXEC_FRAME_RUNNING;
	frame.packet_state=KD_PACKET_FULL; frame.regs.ip=0xbeef; frame.regs.sp=0x2000;
	frame.regs.r15=0x123456; frame.mutex_mixed.transfer_requested=true;
	frame.native_link.next=frame.native_link.prev=&frame.native_link;
	context.owner=&ctask; context.depth=1; context.top=&frame;
	batch.lock=&lock; batch.current_node=&wnode; batch.own_node=&cnode;
	delayed_link=shape==2;
	if (shape==1 || shape==2) {
		lock.delegation_tail=next_node.tail;
		if (shape==1) batch.next=wnode.next=&next_node;
	}
	if (shape==3) {
		lock.delegation_tail=next_node.tail; batch.next=wnode.next=&next_node;
		batch.deferred_head=batch.deferred_tail=&deferred; batch.deferred_count=1;
	}
}

static void *native_owner(void *unused)
{
	(void)unused; current=&wtask; pins=1; migration=1;
	kd_mutex_shadows.node_slots=BIT(wnode.slot); kd_mutex_custody_slots=0;
	while (smp_load_acquire(&wnode.locked)) cpu_relax();
	CHECK(wnode.native_resume && wnode.packet_state==KD_PACKET_FULL);
	captured=wnode.regs; /* The real trampoline copies FULL before pickup. */
	wnode.counted_lock=NULL; wnode.count_seq+=2; /* Origin waiter_exit. */
	kd_mutex_custody_pickup(&wnode,wnode.native_transfer);
	CHECK(captured.ip==0xbeef && captured.r15==0x123456);
	CHECK(source_refs==1 && frame.state==KD_EXEC_FRAME_UNUSED && !context.depth);
	CHECK(!frame.outer_unlock_seen && !frame.completion_seen && !frame.jit_lock_released[0]);
	CHECK(cnode.regs.ip==0xcafe && cnode.counted_lock==&lock && cnode.count_seq==2);
	CHECK(!wnode.native_transfer && wnode.custody.phase==KD_MUTEX_CUSTODY_NATIVE);
	preempt_enable();
	if (mode==1) pins++; /* Native spin B remains held at outer unlock. */
	if (mode==2 || mode==3) kd_mutex_custody_native_acquire(&nested[0]);
	if (mode==3) kd_mutex_custody_native_release(&nested[0]);
	if (mode==4) for(unsigned int i=0;i<10;i++) kd_mutex_custody_native_acquire(&nested[i]);
	CHECK(kd_mutex_custody_unlock(&lock));
	CHECK(releases==1 && combines==((mode==0 || mode==3)?1:0));
	CHECK(!route && !source_refs && task_puts==1 && !migration);
	CHECK(!wnode.lock && !kd_mutex_shadows.node_slots && !kd_mutex_custody_slots);
	CHECK(pins==(mode==1?1U:0U));
	return NULL;
}

static void receipt_checks(void)
{
	shape=0; mode=0; setup();
	frame.mutex_mixed.queue_transfer=frame.mutex_mixed.transferred=frame.mutex_mixed.picked_up=true;
	frame.mutex_mixed.queue.owner=&wnode; frame.mutex_mixed.queue.waiter=&cnode;
	frame.mutex_mixed.queue.head=&cnode; frame.mutex_mixed.queue.generation=4;
	wnode.count_seq=4; wnode.counted_lock=NULL; wnode.custody.head=&cnode;
	wnode.custody.generation=4; wnode.custody.phase=KD_MUTEX_CUSTODY_WAIT_READY;
	wnode.custody.source_lease=true; cnode.locked=1; route=&wnode;
	lock.owner=(unsigned long)&wtask | 1UL;
	CHECK(kd_exec_mutex_custody_accepted(&frame));
	frame.mutex_mixed.picked_up=false; CHECK(!kd_exec_mutex_custody_accepted(&frame)); frame.mutex_mixed.picked_up=true;
	wnode.custody.head=&next_node; CHECK(!kd_exec_mutex_custody_accepted(&frame)); wnode.custody.head=&cnode;
	wnode.custody.ready=true; CHECK(!kd_exec_mutex_custody_accepted(&frame)); wnode.custody.ready=false;
	wnode.count_seq=6; CHECK(!kd_exec_mutex_custody_accepted(&frame)); wnode.count_seq=4;
	lock.owner|=4UL; CHECK(!kd_exec_mutex_custody_accepted(&frame)); lock.owner&=~4UL;
	CHECK(!kd_exec_frame_record_event(&frame,KD_EXEC_EVENT_OWNER_TRANSFER,NULL));
	CHECK(frame.state==KD_EXEC_FRAME_TRANSFERRED && !frame.outer_unlock_seen && !frame.completion_seen);
	CHECK(!kd_exec_frame_pop(&frame,NULL) && !context.depth && frame.state==KD_EXEC_FRAME_UNUSED);
}

int main(void)
{
	receipt_checks();
	for(shape=0;shape<4;shape++) for(mode=0;mode<7;mode++) {
		pthread_t worker; setup();
		CHECK(!pthread_create(&worker,NULL,native_owner,NULL));
		CHECK(kd_mutex_try_role_swap(&lock,&wnode,&batch,&frame));
		CHECK(batch.swapped_owner==&wnode && !batch.next && !context.depth);
		CHECK(lock.delegation_tail==(u32)cnode.tail && !frame.outer_unlock_seen && !frame.completion_seen);
		kd_source_frame_put();
		/* Production batch's final access, after frame and old lease retire. */
		smp_store_release(&wnode.custody.ready,true);
		CHECK(!pthread_join(worker,NULL));
	}
	shape=mode=0; setup(); source_closed=1;
	CHECK(!kd_mutex_try_role_swap(&lock,&wnode,&batch,&frame));
	CHECK(!route && source_refs==1 && lock.delegation_tail==(u32)wnode.tail && !cnode.locked);
	source_closed=0; batch.after_body=true;
	CHECK(!kd_mutex_try_role_swap(&lock,&wnode,&batch,&frame));
	CHECK(!route && source_refs==1);
	printf("custody protocol checks=%u failures=%u\n",checks,failures);
	return failures ? 1 : 0;
}
