/* SPDX-License-Identifier: GPL-2.0 */
/* Deterministic boundary checks around the actual production batch loop. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef int atomic_t;
struct task_struct { int pid; };
struct list_head { struct list_head *next, *prev; };
#include "types.h"
#define KD_MUTEX_TAIL_CPU_OFFSET 4
#define _Q_LOCKED_COMBINER_VAL 3
#define KD_EXE_NO_RUN 2
#define KD_EXE_NATIVE_DONE 7
#define READ_ONCE(x) (x)
#define BUG_ON(x) assert(!(x))
#define this_cpu_inc(x) (++(x))
#define container_of(p, type, member) ((type *)((char *)(p)-offsetof(type,member)))
#define pr_info(...) do { if (0) printf(__VA_ARGS__); } while (0)
#ifdef NUMA_AWARE
#define cpu_to_node(cpu) ((cpu)>=20)
#define numa_node_id() 0
#endif
static const int kd_mutex_batch_size=1024;
static unsigned long kd_mutex_combiner_count, kd_mutex_handoff_count, kd_mutex_jit_success_count;
static struct task_struct owner={1}, waiter={2};
static struct task_struct *current=&owner;
static struct kd_mutex lock;
static struct kd_mutex_node *nodes;
static unsigned int leases, lease_gets, lease_puts, calls, wakes, reclaims, native_done;
static int fail_at, native_at, early_at;
static bool source_open=true;
static int order[1200], awakened;
static bool kd_source_frame_get(void) { if(!source_open)return false;lease_gets++;leases++;return true; }
static void kd_source_frame_put(void) { assert(leases==1);leases--;lease_puts++; }
static void publish(u8 *p, int value)
{
    *p=value;
    for(int i=0;i<1200;i++) if(p==&nodes[i].locked) {wakes++;awakened=i;return;}
    abort();
}
#define smp_store_release(p,v) publish((p),(v))
static void kd_mutex_set_locked(struct kd_mutex *p) { p->locked=1; }
static void kd_mutex_clear_locked_set_completed(struct kd_mutex_node *p) {p->completed=1;p->locked=0;}
static void kd_mutex_prefetch_successor(struct kd_mutex_node *p) {(void)p;}
static void kd_mutex_wait_and_lock(struct kd_mutex *p)
{ assert(!p->physical_owner && leases==1);p->physical_owner=current;p->locked=1;reclaims++; }
int _kd_mutex_unlock_checked(struct kd_mutex *p)
{ assert(p->physical_owner==current && leases==1);p->physical_owner=NULL;p->locked=0;return 0; }
#include "helpers.h"
static int kd_mutex_execute_cs(struct kd_mutex *p, struct kd_mutex_node *node, struct kd_mutex_batch *batch)
{
    int index=node-nodes;
    assert(leases==1 && p->physical_owner==current && calls<1200);
    order[calls++]=index;
    if(index==fail_at) return KD_EXE_NO_RUN;
    if(index==early_at) {
        struct kd_exec_frame frame={.mutex_backend=true,.logical_task=&waiter,
            .outer_lock_addr=p->origin_mutex_addr,.outer_lock_index=0,.jit_lock_depth=2};
        frame.jit_lock_kind[0]=KD_EXEC_LOCK_QUEUE_OWNER;frame.jit_lock_node[0]=p;
        /* Outer release must splice the deferred prefix before publication. */
        assert(!batch->outer.release(&frame,&batch->outer));batch->outer.released=true;
    }
    if(index==native_at) {native_done++;return KD_EXE_NATIVE_DONE;}
    return 0;
}
#include "loop.h"
static void reset(unsigned int count)
{
    memset(nodes,0,1200*sizeof(*nodes));memset(&lock,0,sizeof(lock));
    lock.physical_owner=current;lock.origin_mutex_addr=0x123000;lock.locked=3;
    calls=wakes=reclaims=native_done=lease_gets=lease_puts=leases=0;awakened=-1;
    fail_at=native_at=early_at=-1;source_open=true;
    for(unsigned int i=0;i<count;i++) {
        nodes[i].next=i+1<count?&nodes[i+1]:NULL;
        nodes[i].tail=1<<KD_MUTEX_TAIL_CPU_OFFSET;
        nodes[i].entry_abi=KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
        nodes[i].packet_state=KD_PACKET_MINIMAL;nodes[i].locked=1;
        nodes[i].task_struct_ptr=&waiter;
    }
}
static void chain(int first,const int *expected,unsigned int count)
{
    struct kd_mutex_node *p=&nodes[first];
    for(unsigned int i=0;i<count;i++) {assert(p==&nodes[expected[i]] && !p->completed);p=p->next;}
    assert(!p);
}
static void mixed(void)
{
    for(int mode=0;mode<5;mode++) {
        reset(6);nodes[1].tail=nodes[3].tail=21<<KD_MUTEX_TAIL_CPU_OFFSET;
        if(mode==1)fail_at=0;
        if(mode==2)fail_at=2;
        if(mode==3)native_at=2;
        if(mode==4)early_at=2;
        kd_mutex_run_combiner(&lock,&nodes[0]);
        assert(!leases && lease_gets==1 && lease_puts==1 && wakes==1);
        if(mode==1) {assert(calls==1 && awakened==0);chain(0,(int[]){0,1,2,3,4,5},6);continue;}
#ifdef NUMA_AWARE
        assert(order[0]==0 && order[1]==2 && awakened==1);
        if(mode==0) {assert(calls==3 && order[2]==4);chain(1,(int[]){1,3,5},3);}
        if(mode==2) {assert(calls==2);chain(1,(int[]){1,2,3,4,5},5);}
        if(mode==3 || mode==4) {assert(calls==2);chain(1,(int[]){1,3,4,5},4);}
#else
        assert(order[0]==0 && order[1]==1);
        if(mode==0) {assert(calls==5 && awakened==5);chain(5,(int[]){5},1);}
        if(mode==2) {assert(calls==3 && awakened==2);chain(2,(int[]){2,3,4,5},4);}
        if(mode==3 || mode==4) {assert(calls==3 && awakened==3);chain(3,(int[]){3,4,5},3);}
#endif
        assert(native_done==(unsigned int)(mode==3));
        assert(reclaims==(unsigned int)(mode==4));
        assert(lock.physical_owner==current);
        if(mode==3)assert(!nodes[2].completed); /* no second native completion */
    }
}
static void bounds(void)
{
    reset(1100);kd_mutex_run_combiner(&lock,&nodes[0]);
    assert(calls==1024 && awakened==1024 && !leases && lease_puts==1);
    assert(!kd_mutex_batch_can_continue((void *)1,1024));
    reset(3);source_open=false;kd_mutex_run_combiner(&lock,&nodes[0]);
    assert(!calls && !lease_gets && !lease_puts && awakened==0);
#ifdef NUMA_AWARE
    for(int full=0;full<2;full++) {
        reset(6);nodes[1].tail=21<<4;
        if(full)nodes[2].packet_state=KD_PACKET_FULL;
        else nodes[2].entry_abi=KD_ENTRY_ABI_LEGACY;
        kd_mutex_run_combiner(&lock,&nodes[0]);
        assert(calls==1 && awakened==1 && !leases);
        chain(1,(int[]){1,2,3,4,5},5);
    }
    reset(1100);for(int i=1;i<1100;i++)nodes[i].tail=21<<4;
    struct kd_mutex_batch batch={.scan_left=1024,.local_node=0};
    assert(kd_mutex_next_node(&batch,nodes)==&nodes[1025] && !batch.scan_left);
    assert(batch.deferred_head==&nodes[1] && batch.deferred_tail==&nodes[1024]);
    assert(kd_mutex_splice_deferred(&batch,&nodes[1025])==&nodes[1]);
    assert(!batch.deferred_head && !batch.deferred_tail && nodes[1024].next==&nodes[1025]);
    /* The next field occupies a protected cacheline, but immutable tail/ABI
     * fields remain readable. A spent scan must not dereference next->next. */
    long size=sysconf(_SC_PAGESIZE);
    char *memory=mmap(NULL,2*size,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    assert(memory!=MAP_FAILED);
    struct kd_mutex_node *poison=(void *)(memory+size-64);
    poison->tail=21<<4;poison->entry_abi=2;poison->packet_state=KD_PACKET_MINIMAL;
    nodes[0].next=poison;assert(!mprotect(memory,size,PROT_NONE));
    batch.scan_left=0;
    assert(kd_mutex_next_node(&batch,nodes)==poison);
    assert(!munmap(memory,2*size));
#endif
}
int main(void)
{
    nodes=aligned_alloc(64,1200*sizeof(*nodes));assert(nodes);
    assert(sizeof(*nodes)==256);mixed();bounds();free(nodes);
    puts("[PASS] production mutex batch: native/refusal/early splice, body/scan bounds, deferred priority and source drain");
}
