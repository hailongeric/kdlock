/* SPDX-License-Identifier: GPL-2.0 */
/* Real queue retirement/loop with scheduled publication interleavings. Body,
 * native ACK and physical-owner operations remain deterministic substitutes. */
#include <errno.h>
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
typedef struct { int counter; } atomic_t;
typedef struct task_struct *atomic_long_t;
typedef int raw_spinlock_t;
struct optimistic_spin_queue { atomic_t tail; };
struct hlist_node { struct hlist_node *next, **pprev; };
struct rcu_head { struct rcu_head *next; void (*fn)(struct rcu_head *); };
struct task_struct { int pid; } __attribute__((aligned(8)));
struct list_head { struct list_head *next, *prev; };
#include "types.h"
#define _Q_LOCKED_COMBINER_VAL 3
#define KD_EXE_NO_RUN 2
#define KD_EXE_NATIVE_DONE 7
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, v) ((x) = (v))
/* A cache hint has no effect in this deterministic protocol fixture. */
#define prefetch(p) ((void)(p))
#define NUMA_AWARE 1
static int numa_node_id(void) { return 0; }
#define smp_load_acquire(p) (*(p))
#define this_cpu_inc(x) (++(x))
#define container_of(p,type,member) ((type *)((char *)(p)-offsetof(type,member)))
#define pr_info(...) do { if (0) printf(__VA_ARGS__); } while (0)
static unsigned int scenario, checks;
#define CHECK(c) do { checks++; if (!(c)) { fprintf(stderr,"FAIL terminal scenario=%u line=%d: %s\n",scenario,__LINE__,#c);exit(1); } } while (0)
#define BUG_ON(c) CHECK(!(c))
#include "mutex_state_mock.h"
static struct task_struct owner={1}, waiter={2};
static struct task_struct *current=&owner;
static struct kd_mutex lock;
static struct kd_mutex_node nodes[1030];
static const int kd_mutex_batch_size=1024;
static unsigned long kd_mutex_combiner_count,kd_mutex_handoff_count,kd_mutex_jit_success_count;
static unsigned int leases,lease_gets,lease_puts,calls,completed,wakes,reclaims,polls,cas_calls;
static bool source_open,delayed_link,new_head_after_cas,new_head_pending;
static int refusal_at,native_at,early_at;
static struct kd_mutex_node *delayed_from,*delayed_to;
static bool kd_source_frame_get(void) { if(!source_open)return false;lease_gets++;leases++;return true; }
static void kd_source_frame_put(void) { CHECK(leases==1);leases--;lease_puts++; }
static void cpu_relax(void)
{
    CHECK(delayed_link && delayed_from && delayed_to && polls<3);
    if(++polls==2) { delayed_from->next=delayed_to;delayed_link=false; }
}
static u32 tail_cas(u32 *p,u32 old,u32 value)
{
    CHECK(p==&lock.delegation_tail && leases==1 && lock.owner==current);
    cas_calls++;
    if(delayed_link && !polls) { CHECK(*p==old);*p=delayed_to->tail; }
    u32 seen=*p;
    if(seen==old) {
        *p=value;
        if(new_head_after_cas) {
            /* New publisher receives old_tail=0 and never links old node. */
            CHECK(!*p && kd_mutex_gate_read(&lock) && lock.owner==current);
            *p=nodes[1].tail;new_head_pending=true;new_head_after_cas=false;
        }
    }
    return seen;
}
#define cmpxchg(p,o,n) tail_cas((p),(o),(n))
static void publish(u8 *p,int value)
{
    CHECK(value==0);
    *p=value;wakes++;
}
#define smp_store_release(p,v) publish((p),(v))
static void kd_mutex_set_locked(struct kd_mutex *p) { CHECK(p==&lock);kd_mutex_gate_set(p,KD_MUTEX_GATE_HELD); }
static void kd_mutex_clear_locked_set_completed(struct kd_mutex_node *node)
{
    CHECK(leases==1 && node->locked && lock.delegation_tail!=(u32)node->tail);
    node->completed=1;node->locked=0;completed++;
    /* Immediate slot reuse makes any old successor read observably invalid. */
    node->next=(void *)1;node->tail=0xdead;
}
static void kd_mutex_prefetch_successor(struct kd_mutex_node *node) { (void)node; }
static void kd_mutex_wait_and_lock(struct kd_mutex *p)
{ CHECK(p==&lock);CHECK(!lock.owner && leases==1);CHECK(kd_mutex_gate_trylock(p));lock.owner=current;kd_mutex_gate_set(p,KD_MUTEX_GATE_HELD);reclaims++; }
int _kd_mutex_unlock_checked(struct kd_mutex *p)
{ CHECK(p==&lock);CHECK(lock.owner==current && leases==1);kd_mutex_gate_set(p,KD_MUTEX_GATE_RELEASING);lock.owner=NULL;kd_mutex_gate_set(p,KD_MUTEX_GATE_FREE);return 0; }
#include "helpers.h"
static int kd_mutex_execute_cs(struct kd_mutex *p,struct kd_mutex_node *node,struct kd_mutex_batch *batch)
{
    int i=node-nodes;
    CHECK(p==&lock && leases==1 && lock.owner==current);
    calls++;
    if(i==refusal_at)return KD_EXE_NO_RUN;
    if(i==early_at) {
        struct kd_exec_frame frame={.mutex_backend=true,.logical_task=&waiter,
            .outer_lock_addr=(unsigned long)p,.jit_lock_depth=2};
        frame.jit_lock_kind[0]=KD_EXEC_LOCK_QUEUE_OWNER;frame.jit_lock_node[0]=p;
        CHECK(!batch->outer.release(&frame,&batch->outer));batch->outer.released=true;
        CHECK(!kd_mutex_gate_read(&lock) && !lock.owner);
    }
    if(i==native_at) {
        /* Mirrors the publication boundary; the separate outer fixture runs
         * the actual execute_cs/FULL/native path with node reuse before ACK. */
        kd_mutex_batch_retire_current(p,batch);
        CHECK(lock.delegation_tail!=(u32)node->tail);
        node->locked=0;node->native_resume=true;
        node->tail=0xdead;node->next=(void *)1;
        struct kd_mutex_node *saved_next=batch->next;
        u32 saved_tail=lock.delegation_tail;
        unsigned int saved_cas=cas_calls;
        kd_mutex_batch_retire_current(p,batch);
        CHECK(batch->next==saved_next && lock.delegation_tail==saved_tail && cas_calls==saved_cas);
        return KD_EXE_NATIVE_DONE;
    }
    return 0;
}
#include "loop.h"
static void reset(unsigned int count)
{
    memset(nodes,0,sizeof(nodes));memset(&lock,0,sizeof(lock));
    kd_mutex_gate_set(&lock,KD_MUTEX_GATE_COMBINER);lock.owner=current;
    source_open=true;delayed_link=new_head_after_cas=new_head_pending=false;
    refusal_at=native_at=early_at=-1;
    leases=lease_gets=lease_puts=calls=completed=wakes=reclaims=polls=cas_calls=0;
    for(unsigned int i=0;i<count;i++) {
        nodes[i].next=i+1<count?&nodes[i+1]:NULL;
        nodes[i].tail=(i+1)<<4;nodes[i].locked=1;
        nodes[i].entry_abi=KD_ENTRY_ABI_MUTEX_CLOBBER_V1;
        nodes[i].packet_state=KD_PACKET_MINIMAL;nodes[i].task_struct_ptr=&waiter;
    }
    lock.delegation_tail=nodes[count-1].tail;
}
static void finish(void)
{
    CHECK(!leases && lease_gets==lease_puts && lock.owner==current);
    CHECK(kd_mutex_gate_read(&lock)==1);
}
int main(void)
{
    scenario=1;reset(1);kd_mutex_run_combiner(&lock,&nodes[0]);
    CHECK(calls==1 && completed==1 && !wakes && !lock.delegation_tail && cas_calls==1);finish();
    scenario=2;reset(2);nodes[0].next=NULL;delayed_link=true;delayed_from=&nodes[0];delayed_to=&nodes[1];
    lock.delegation_tail=nodes[0].tail;kd_mutex_run_combiner(&lock,&nodes[0]);
    CHECK(calls==2 && completed==2 && polls==2 && !lock.delegation_tail && !wakes);finish();
    scenario=3;reset(2);nodes[0].next=NULL;lock.delegation_tail=nodes[0].tail;new_head_after_cas=true;
    kd_mutex_run_combiner(&lock,&nodes[0]);
    CHECK(calls==1 && completed==1 && new_head_pending && nodes[1].locked && !wakes);
    CHECK(lock.delegation_tail==(u32)nodes[1].tail && kd_mutex_gate_read(&lock) && lock.owner==current);finish();
    /* Its original KD physical owner cannot enter until the retained owner releases.
     * Afterwards the independently published head can acquire and clear tail. */
    lock.owner=NULL;kd_mutex_gate_set(&lock,KD_MUTEX_GATE_FREE);
    CHECK(new_head_pending && !kd_mutex_gate_read(&lock));kd_mutex_gate_set(&lock,KD_MUTEX_GATE_HELD);lock.owner=&waiter;
    CHECK(lock.delegation_tail==(u32)nodes[1].tail);lock.delegation_tail=0;new_head_pending=false;
    scenario=4;reset(1);refusal_at=0;u32 original_tail=lock.delegation_tail;
    kd_mutex_run_combiner(&lock,&nodes[0]);
    CHECK(calls==1 && !completed && wakes==1 && !nodes[0].locked && lock.delegation_tail==original_tail && !cas_calls);finish();
    scenario=5;reset(1);native_at=0;kd_mutex_run_combiner(&lock,&nodes[0]);
    CHECK(calls==1 && !completed && nodes[0].native_resume && !lock.delegation_tail && cas_calls==1 && !wakes);finish();
    scenario=6;reset(1);early_at=0;kd_mutex_run_combiner(&lock,&nodes[0]);
    CHECK(calls==1 && completed==1 && reclaims==1 && !lock.delegation_tail && !wakes);finish();
    scenario=7;reset(1026);kd_mutex_run_combiner(&lock,&nodes[0]);
    CHECK(calls==1024 && completed==1024 && wakes==1 && !nodes[1024].locked && nodes[1024].next==&nodes[1025] && !cas_calls);finish();
    for(scenario=8;scenario<10;scenario++) {
        reset(1);if(scenario==8)nodes[0].entry_abi=KD_ENTRY_ABI_LEGACY;else nodes[0].packet_state=KD_PACKET_FULL;
        original_tail=lock.delegation_tail;kd_mutex_run_combiner(&lock,&nodes[0]);
        CHECK(!calls && !lease_gets && !completed && wakes==1 && lock.delegation_tail==original_tail);finish();
    }
    scenario=10;reset(1);source_open=false;original_tail=lock.delegation_tail;kd_mutex_run_combiner(&lock,&nodes[0]);
    CHECK(!calls && !lease_gets && !completed && wakes==1 && lock.delegation_tail==original_tail);finish();
    /* Select local work without ever detaching the unlinked global tail. */
    scenario=11;reset(4);nodes[0].numa_node=nodes[2].numa_node=1;
    kd_mutex_run_combiner(&lock,&nodes[0]);
    CHECK(calls==4 && completed==4 && !wakes && !lock.delegation_tail && cas_calls==1);finish();
    /* An unexecuted/refused current node must not retain a link into the
     * deferred prefix, which would make rejoin publish a cycle. */
    scenario=12;reset(4);nodes[0].numa_node=nodes[2].numa_node=1;refusal_at=1;
    kd_mutex_run_combiner(&lock,&nodes[0]);
    CHECK(calls==1 && !completed && wakes==1 && !nodes[0].locked);
    CHECK(nodes[0].next==&nodes[2] && nodes[2].next==&nodes[1] && nodes[1].next==&nodes[3]);finish();
    scenario=13;reset(4);nodes[0].numa_node=1;native_at=1;
    kd_mutex_run_combiner(&lock,&nodes[0]);
    CHECK(calls==1 && !completed && wakes==1 && nodes[1].native_resume && !nodes[0].locked);
    CHECK(nodes[0].next==&nodes[2] && nodes[2].next==&nodes[3] && !cas_calls);finish();
    scenario=14;reset(4);nodes[0].numa_node=1;early_at=1;
    kd_mutex_run_combiner(&lock,&nodes[0]);
    CHECK(calls==1 && completed==1 && wakes==1 && reclaims==1 && !nodes[0].locked);
    CHECK(nodes[0].next==&nodes[2] && nodes[2].next==&nodes[3] && !cas_calls);finish();
    scenario=15;reset(140);
    for(unsigned int i=0;i<8;i++)nodes[i].numa_node=1;
    kd_mutex_run_combiner(&lock,&nodes[0]);
    CHECK(calls==128 && completed==128 && wakes==1 && !nodes[0].locked);
    CHECK(nodes[7].next==&nodes[136] && nodes[136].locked && !cas_calls);finish();
    scenario=16;reset(200);
    for(unsigned int i=0;i<200;i++)nodes[i].numa_node=1;
    kd_mutex_run_combiner(&lock,&nodes[0]);
    CHECK(calls==128 && completed==128 && wakes==1 && !nodes[0].locked);
    for(unsigned int i=0;i<63;i++)CHECK(nodes[i].next==&nodes[i+1] && !nodes[i].completed);
    CHECK(nodes[63].next==&nodes[192] && nodes[192].locked && !cas_calls);finish();
    scenario=17;reset(140);nodes[0].numa_node=1;
    kd_mutex_run_combiner(&lock,&nodes[0]);
    CHECK(calls==140 && completed==140 && !wakes && !lock.delegation_tail && cas_calls==1);finish();
    printf("PASS terminal queue: %u checks; singleton, delayed link, independent new head, refusal, native reuse, early release, bounds and packet boundaries\n",checks);
}
