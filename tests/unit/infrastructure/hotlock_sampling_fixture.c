/* SPDX-License-Identifier: GPL-2.0 */
/* Execute production hash/list/window code with a controlled clock and CPUs.
 * Exact-key counts and bucket membership use independent test identities. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* Mutation failures must be distinguished from crashes/timeouts. */
#undef assert
#define assert(c) do { if (!(c)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#c); exit(1); } } while(0)
typedef uint8_t u8;
typedef uint16_t u16;
typedef unsigned long long u64;
#define U64_MAX UINT64_MAX
#define ____cacheline_aligned __attribute__((aligned(64)))
#define __percpu
#define pr_info(...) do { if(0) printf(__VA_ARGS__); } while(0)
#define module_param(...)
#define MODULE_PARM_DESC(...)
#define TEST_CPUS 3
static unsigned int cpu_id, pins, clocks, disables, enables;
static unsigned long now = 1;
static size_t stride;
static bool fail_alloc;
static void (*reentry)(void);
#define alloc_percpu(type) (stride=sizeof(type), fail_alloc ? NULL : calloc(TEST_CPUS, sizeof(type)))
#define free_percpu(p) free(p)
#define per_cpu_ptr(p,c) ((__typeof__(p))((char *)(p)+stride*(c)))
#define this_cpu_ptr(p) per_cpu_ptr(p,cpu_id)
#define for_each_possible_cpu(c) for ((c)=0;(c)<TEST_CPUS;(c)++)
#define READ_ONCE(v) (v)
#define WRITE_ONCE(v,n) ((v)=(n))
#define cmpxchg(p,o,n) ({ __typeof__(*(p)) old=*(p); if(old==(o)) *(p)=(n); old; })
#define this_cpu_cmpxchg(v,o,n) cmpxchg(this_cpu_ptr(&(v)),o,n)
#define preempt_count() pins
#define preempt_disable() do { ++pins; ++disables; } while(0)
#define preempt_enable() do { assert(pins); --pins; ++enables; } while(0)
#define barrier() __asm__ __volatile__("" ::: "memory")
static unsigned long hash_long(unsigned long key,unsigned int bits)
{ return (key*0x61c8864680b583ebUL)>>(64-bits); }
static unsigned long rdtsc_ordered(void)
{
 void (*f)(void)=reentry; reentry=NULL; clocks++;
 if(f) f();
 return now;
}
#include "hotlock_production.h"
static struct kd_hotlock_table *table(unsigned int kind)
{ return &this_cpu_ptr(kd_hotlock_cpu)->tables[kind]; }
static void hits(unsigned long addr, unsigned int n)
{ while(n--) { kd_hotlock_record_spin(addr); assert(!pins); } }
static void reset(void)
{
 if(kd_hotlock_cpu) kd_hotlock_exit();
 cpu_id=pins=clocks=0; now=1; hotlock_mode="adaptive";
 assert(!kd_hotlock_init());
}
static void check_chains(struct kd_hotlock_table *t)
{
 bool seen[KD_HOTLOCK_ENTRIES]={false}; unsigned int count=0;
 for(unsigned int b=0;b<KD_HOTLOCK_BUCKETS;b++) {
  for(u16 i=t->buckets[b];i;i=t->entries[i-1].next) {
   assert(i<=t->used && !seen[i-1]);
   seen[i-1]=true; count++;
   assert(kd_hotlock_bucket(t->entries[i-1].address)==b);
   assert(kd_hotlock_find(t,t->entries[i-1].address)==&t->entries[i-1]);
  }
 }
 assert(count==t->used);
}
static void irq_reentry(void)
{
 struct kd_hotlock_table before=*table(0);
 assert(!kd_hotlock_record_spin(0xdead));
 assert(!memcmp(&before,table(0),sizeof(before)));
 assert(pins==1);
}
/* The API accepts initialized, valid identities. Invalid initialization is
 * checked separately; an invalid-address hot-path branch is not its contract. */
static void init_and_pins(void)
{
 reset();
 assert(sizeof(struct kd_hotlock_entry)==24);
 assert(sizeof(struct kd_hotlock_table)==6688 && sizeof(struct kd_hotlock_cpu)==13376);
 assert(clocks==1);
 for(unsigned int c=0;c<TEST_CPUS;c++)
  for(unsigned int k=0;k<2;k++) {
   struct kd_hotlock_table *t=&per_cpu_ptr(kd_hotlock_cpu,c)->tables[k];
   assert(t->rate_begin==now && !t->rate_samples && !t->rate_hot && !t->used);
  }
 pins=1;
 unsigned int before_disable=disables, before_enable=enables;
 kd_hotlock_record_spin_pinned(0x1000); kd_hotlock_record_spin(0x1000);
 kd_hotlock_query_spin(0x1000);
 table(0)->busy=1;
 struct kd_hotlock_table before=*table(0);
 assert(!kd_hotlock_record_spin(0x1000));
 assert(!memcmp(&before,table(0),sizeof(before)));
 table(0)->busy=0;
 assert(pins==1 && disables==before_disable && enables==before_enable);
 pins=0;
 kd_hotlock_record_mutex(0x2000);
 assert(!pins && disables==before_disable+1 && enables==before_enable+1);
}
/* CPU threshold remains 1024; lock threshold is strictly greater than 1024.
 * Their first checks coincide but subsequent batches drift independently. */
static void boundaries(void)
{
 reset();
 assert(KD_HOTLOCK_CHECK_INTERVAL==1024 && KD_HOTLOCK_SAMPLE_TARGET==1024);
 hits(0x1000,1023);
 assert(clocks==1 && !table(0)->used && !table(0)->rate_hot);
 assert(!kd_hotlock_record_spin(0x1000));
 struct kd_hotlock_entry *s=kd_hotlock_find(table(0),0x1000);
 assert(clocks==2 && table(0)->rate_hot && !table(0)->rate_samples);
 assert(s && s->count==1 && !s->hot && s->begin==now);
 hits(0x1000,1023);
 assert(clocks==2 && s->count==1024 && !s->hot);
 assert(kd_hotlock_record_spin(0x1000));
 assert(clocks==3 && !s->count && s->hot); /* call 2048: shared CPU/lock TSC */
 struct kd_hotlock_table before=*table(0);
 for(unsigned int i=0;i<2000;i++) assert(kd_hotlock_query_spin(0x1000));
 assert(clocks==3 && !memcmp(&before,table(0),sizeof(before)));
 assert(!kd_hotlock_query_mutex(0x1000) && clocks==3);
 hits(0x1000,1024);
 assert(clocks==4 && !table(0)->rate_samples && s->count==1024 && s->hot);
 assert(kd_hotlock_record_spin(0x1000));
 assert(clocks==5 && !s->count); /* only the lock checks this time */
 now+=100;
 assert(!kd_hotlock_record_spin(0x2000));
 s=kd_hotlock_find(table(0),0x2000);
 assert(s && s->begin==table(0)->rate_begin && s->begin<now && clocks==5);
}
static void windows(void)
{
 reset(); hits(0x1000,2048);
 struct kd_hotlock_entry *s=kd_hotlock_find(table(0),0x1000);
 now=s->begin+KD_HOTLOCK_INITIAL_WINDOW;
 hits(0x1000,1024);
 assert(s->hot && s->count==1024);
 assert(!kd_hotlock_record_spin(0x1000)); /* equality is cold */
 assert(!s->hot && !s->count && s->begin==now && table(0)->rate_hot);
 hits(0x1000,1025); assert(s->hot);
 now=table(0)->rate_begin+KD_HOTLOCK_CPU_WINDOW;
 hits(0x1000,1024-table(0)->rate_samples);
 assert(!table(0)->rate_hot && !s->hot && !s->count);
 assert(!kd_hotlock_query_spin(0x1000));
 hits(0x1000,1024);
 assert(table(0)->rate_hot && !s->hot && s->count==1 && s->begin==now);
 hits(0x1000,1024); assert(s->hot);
 reset(); now+=KD_HOTLOCK_CPU_WINDOW;
 hits(0x1000,1024); assert(!table(0)->rate_hot && !table(0)->used);
 hits(0x1000,1024); assert(table(0)->rate_hot && table(0)->used==1);
}
static void backwards_and_zero(void)
{
 reset(); now=100; hits(0x1000,3072);
 struct kd_hotlock_entry *s=kd_hotlock_find(table(0),0x1000);
 assert(s->hot && s->count==1024 && !table(0)->rate_samples);
 unsigned int before=clocks; now=50;
 assert(!kd_hotlock_record_spin(0x1000));
 assert(clocks==before+1 && table(0)->rate_hot && !s->hot && s->begin==50);
 hits(0x1000,1024-table(0)->rate_samples);
 assert(!table(0)->rate_hot && !s->count && !s->hot);
 reset(); now=0; hits(0x1000,1024);
 assert(!table(0)->rate_hot && !table(0)->used && clocks==2);
 hits(0x1000,1024);
 assert(table(0)->rate_hot && table(0)->rate_begin==0 && clocks==3);
 hits(0x1000,1023); before=clocks;
 assert(kd_hotlock_record_spin(0x1000));
 assert(clocks==before+1); /* coincident checks at zero read just once */
}
/* More than six locks must retain independent counters, even when every key
 * hashes to the same bucket. Full tables keep all existing identities intact. */
static void hash_and_capacity(void)
{
 unsigned long keys[KD_HOTLOCK_ENTRIES+1]; unsigned int n=0;
 reset();
 for(unsigned long k=1;n<KD_HOTLOCK_ENTRIES+1;k++)
  if(kd_hotlock_bucket(k)==0) keys[n++]=k;
 hits(keys[0],2048);
 for(unsigned int i=1;i<KD_HOTLOCK_ENTRIES;i++) {
  hits(keys[i],i+1);
  assert(kd_hotlock_find(table(0),keys[i])->count==i+1);
 }
 check_chains(table(0));
 assert(table(0)->used==KD_HOTLOCK_ENTRIES);
 for(unsigned int i=1;i<KD_HOTLOCK_ENTRIES;i++) {
  struct kd_hotlock_entry *s=kd_hotlock_find(table(0),keys[i]);
  assert(s && s->count==i+1 && !s->hot);
 }
 assert(kd_hotlock_query_spin(keys[0]));
 struct kd_hotlock_entry saved[KD_HOTLOCK_ENTRIES];
 memcpy(saved,table(0)->entries,sizeof(saved));
 hits(keys[KD_HOTLOCK_ENTRIES],2048);
 assert(!kd_hotlock_find(table(0),keys[KD_HOTLOCK_ENTRIES]));
 assert(!memcmp(saved,table(0)->entries,sizeof(saved)));
 assert(!kd_hotlock_query_spin(keys[KD_HOTLOCK_ENTRIES]));
 for(unsigned int i=0;i<KD_HOTLOCK_ENTRIES;i++) assert(kd_hotlock_find(table(0),keys[i]));
 hits(keys[0],1025);assert(kd_hotlock_query_spin(keys[0]));
 assert(table(0)->used==KD_HOTLOCK_ENTRIES);check_chains(table(0));
 /* Stable membership survives CPU cooling; heat and counts do not. */
 now=table(0)->rate_begin+KD_HOTLOCK_CPU_WINDOW;
 hits(keys[0],1024-table(0)->rate_samples);
 assert(!table(0)->rate_hot && table(0)->used==KD_HOTLOCK_ENTRIES);
 for(unsigned int i=0;i<KD_HOTLOCK_ENTRIES;i++) {
  struct kd_hotlock_entry *s=kd_hotlock_find(table(0),keys[i]);
  assert(s && !s->hot && !s->count);
 }
}
static void isolation_and_reentry(void)
{
 reset();hits(0x1000,2048);
 cpu_id=1;assert(!kd_hotlock_query_spin(0x1000));
 assert(!kd_hotlock_record_mutex(0x1000) && !pins);
 cpu_id=0;assert(kd_hotlock_query_spin(0x1000));
 hits(0x1000,1023);reentry=irq_reentry;hits(0x1000,1);assert(!reentry);
 assert(kd_hotlock_find(table(0),0x1000)->count==1024);
 reentry=irq_reentry;hits(0x1000,1);assert(!reentry);
 /* Both types use the same strict lock threshold but independent tables. */
 for(unsigned int i=0;i<2047;i++) assert(!kd_hotlock_record_mutex(0x1000));
 assert(kd_hotlock_record_mutex(0x1000) && kd_hotlock_query_mutex(0x1000));
 kd_hotlock_exit();hotlock_mode="observe";assert(!kd_hotlock_init());
 table(0)->busy=1;assert(kd_hotlock_record_spin(0x1000) && !pins);
 table(0)->busy=0;assert(kd_hotlock_record_mutex(0x1000) && !pins);
 assert(!kd_hotlock_query_mutex(0x1000));
 hits(0x1000,1024);
 for(unsigned int i=0;i<KD_HOTLOCK_ENTRIES;i++) assert(kd_hotlock_record_spin(0x10000+i));
 assert(kd_hotlock_record_spin(0x20000)); /* fixed policy, even at capacity */
 assert(!kd_hotlock_query_spin(0x20000));
}
int main(void)
{
 init_and_pins();boundaries();windows();backwards_and_zero();
 hash_and_capacity();isolation_and_reentry();
 kd_hotlock_exit();hotlock_mode="invalid";assert(kd_hotlock_init()==-EINVAL);
 fail_alloc=true;hotlock_mode="adaptive";assert(kd_hotlock_init()==-ENOMEM);
 assert(!kd_hotlock_cpu);
 puts("PASS exact hash: CPU1024/lock1025/collision/256-capacity/no-eviction/independent/shared-TSC/query/window/zero/reentry/observe");
 return 0;
}
