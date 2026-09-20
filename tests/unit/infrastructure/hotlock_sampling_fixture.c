/* SPDX-License-Identifier: GPL-2.0 */
/* Execute production hash/list/window code with a controlled clock and CPUs.
 * Bucket invariants and conservative counts use an independent exact oracle. */
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
 unsigned int seen=0,count=0;
 for(unsigned int b=0;b<KD_HOTLOCK_BUCKETS;b++) {
  for(u8 i=t->buckets[b];i;i=t->slots[i-1].next) {
   assert(i<=t->used && !(seen&(1U<<i)));
   seen|=1U<<i; count++;
   assert(kd_hotlock_bucket(t->slots[i-1].address)==b);
   assert(kd_hotlock_find(t,t->slots[i-1].address)==&t->slots[i-1]);
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
int main(void)
{
 unsigned long keys[7]; unsigned int n=0;
 reset();
 /* Admission under a real lock pin must not add even a balanced pair.
  * Include busy rejection, query and invalid-address early return. */
 pins=1;
 unsigned int before_disable=disables, before_enable=enables;
 kd_hotlock_record_spin(0x1000);
 kd_hotlock_query_spin(0x1000);
 table(0)->busy=1;
 kd_hotlock_record_spin(0x1000);
 table(0)->busy=0;
 kd_hotlock_record_spin(0);
 assert(pins==1 && disables==before_disable && enables==before_enable);
 pins=0;
 kd_hotlock_record_mutex(0x2000);
 assert(!pins && disables==before_disable+1 && enables==before_enable+1);
 reset();
 /* Same-bucket collisions, duplicate identities, head/middle/tail unlink. */
 for(unsigned long k=1;n<7;k++) if(kd_hotlock_bucket(k)==0) keys[n++]=k;
 hits(keys[0], 3*KD_HOTLOCK_CHECK_INTERVAL);
 assert(kd_hotlock_query_spin(keys[0]));
 assert(!kd_hotlock_query_mutex(keys[0]));
 assert(clocks==4); /* initial read plus three completed blocks */
 for(unsigned int i=1;i<6;i++) hits(keys[i],10000+i);
 check_chains(table(0));
 unsigned int used=table(0)->used;
 hits(keys[3],1); assert(table(0)->used==used);
 /* Force each chain position to be the unique minimum, then check full keys. */
 for(unsigned int i=0;i<6;i++) {
  struct kd_hotlock_table *t=table(0);
  for(unsigned int j=0;j<6;j++) t->slots[j].score=20000+j;
  unsigned long old=t->slots[i].address;
  t->slots[i].score=15000; t->slots[i].error=0;
  unsigned long fresh=keys[6]+1000+i;
  assert(!kd_hotlock_record_spin(fresh));
  struct kd_hotlock_candidate *s=kd_hotlock_find(t,fresh);
  assert(s && s->score==15001 && s->error==15000);
  assert(!kd_hotlock_find(t,old)); check_chains(t);
 }
 /* Independent exact counts bound each retained Space-Saving estimate. */
 reset(); hits(0x1000,2*KD_HOTLOCK_CHECK_INTERVAL);
 unsigned int exact[29]={0};
 unsigned int rng=1;
 for(unsigned int i=0;i<90000;i++) {
  rng=rng*1664525U+1013904223U;
  unsigned int k=(rng>>8)%29; exact[k]++;
  kd_hotlock_record_spin(0x10000+k);
  struct kd_hotlock_candidate *s=kd_hotlock_find(table(0),0x10000+k);
  assert(s->score-s->error<=exact[k]); check_chains(table(0));
 }
 /* CPU and lock-kind isolation, no stale promotion transfer after eviction. */
 reset(); hits(keys[0],3*KD_HOTLOCK_CHECK_INTERVAL);
 cpu_id=1; assert(!kd_hotlock_query_spin(keys[0]));
 assert(!kd_hotlock_record_mutex(keys[0]) && !pins);
 cpu_id=0; assert(kd_hotlock_query_spin(keys[0]));
 /* Deadline equality resets, followed by genuine reheating. */
 now+=KD_HOTLOCK_INITIAL_WINDOW;
 hits(keys[0],KD_HOTLOCK_CHECK_INTERVAL);
 assert(!kd_hotlock_query_spin(keys[0]));
 hits(keys[0],KD_HOTLOCK_SAMPLE_TARGET);
 assert(kd_hotlock_query_spin(keys[0]));
 now+=KD_HOTLOCK_CPU_WINDOW;
 hits(keys[0],KD_HOTLOCK_CHECK_INTERVAL);
 assert(!kd_hotlock_query_spin(keys[0]));
 hits(keys[0],3*KD_HOTLOCK_CHECK_INTERVAL);
 assert(kd_hotlock_query_spin(keys[0]));
 /* Reentry at the batched clock loses only its sample and restores pins. */
 table(0)->rate_samples=KD_HOTLOCK_CHECK_INTERVAL-1;
 reentry=irq_reentry; hits(keys[0],1); assert(!reentry);
 /* Observe keeps fixed admission even when the statistics lock is busy. */
 kd_hotlock_exit();hotlock_mode="observe";assert(!kd_hotlock_init());
 table(0)->busy=1;assert(kd_hotlock_record_spin(keys[0]) && !pins);
 table(0)->busy=0;assert(kd_hotlock_record_mutex(keys[0]) && !pins);
 assert(!kd_hotlock_query_mutex(keys[0])); /* observe does not forge heat */
 kd_hotlock_exit();hotlock_mode="invalid";assert(kd_hotlock_init()==-EINVAL);
 fail_alloc=true;hotlock_mode="adaptive";assert(kd_hotlock_init()==-ENOMEM);
 puts("PASS hash: collision/duplicate/unlink/replacement/error/window/cooling/CPU/type/reentry/observe");
 return 0;
}
