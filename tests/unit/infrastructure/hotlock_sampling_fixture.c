/* SPDX-License-Identifier: GPL-2.0 */
/* Execute production hash/list/window and admission code with controlled clocks
 * and CPUs. Logical acquisitions and MCS publications are distinct events so
 * disabled delegation must recover using the same native sampling boundaries. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#undef assert
#define assert(c) do { if (!(c)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#c); exit(1); } } while(0)
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef unsigned long long u64;
#define U64_MAX UINT64_MAX
#define ____cacheline_aligned __attribute__((aligned(64)))
#define __percpu
#define __read_mostly
#define pr_info(...) do { if(0) printf(__VA_ARGS__); } while(0)
#define module_param(...)
#define module_param_named(...)
#define MODULE_PARM_DESC(...)
#define EXPORT_PER_CPU_SYMBOL_GPL(...)
#define TEST_CPUS 3
static unsigned int cpu_id, pins, clocks, disables, enables, guards, pin_checks;
static unsigned long now = 1;
static size_t stride;
static bool fail_alloc;
static bool kd_spin_delegate = true;
static bool check_spin_clock;
static void check_clock_counters(void);
struct qspinlock { u16 tail; };
#define _Q_TAIL_OFFSET_HL 16
#define xchg(address, value) ({ __typeof__(*(address)) previous=*(address); *(address)=(value); previous; })
#define alloc_percpu(type) (stride=sizeof(type), fail_alloc ? NULL : calloc(TEST_CPUS, sizeof(type)))
#define free_percpu(p) free(p)
#define per_cpu_ptr(p,c) ((__typeof__(p))((char *)(p)+stride*(c)))
#define this_cpu_ptr(p) per_cpu_ptr(p,cpu_id)
#define for_each_possible_cpu(c) for ((c)=0;(c)<TEST_CPUS;(c)++)
#define preempt_count() (++pin_checks, pins)
#define preempt_disable() do { ++pins; ++disables; } while(0)
#define preempt_enable() do { assert(pins); --pins; ++enables; } while(0)
#define barrier() asm volatile("" ::: "memory")
static unsigned long hash_long(unsigned long key,unsigned int bits)
{ return (key*0x61c8864680b583ebUL)>>(64-bits); }
static unsigned long rdtsc_ordered(void)
{
 if(check_spin_clock) check_clock_counters();
 clocks++; return now;
}
#define DECLARE_PER_CPU(type, name) extern type name[TEST_CPUS]
#define DEFINE_PER_CPU(type, name) type name[TEST_CPUS]
/* Static CPU arrays are independent of the dynamic exact-table stride. */
#define raw_cpu_ptr(p) (&(*(p))[cpu_id])
#define per_cpu(name, c) (name[c])
#define this_cpu_read(name) (name[cpu_id])
#define this_cpu_write(name, value) (name[cpu_id] = (value))
#define this_cpu_inc(name) (++name[cpu_id])
#define READ_ONCE(x) (x)
/* Production writes busy=1 only when entering the table guard. */
#define WRITE_ONCE(x, value) do { if ((value)==1) guards++; (x)=(value); } while(0)
#include "hotlock_production.h"
static struct kd_hotlock_table *table(unsigned int kind)
{ return &this_cpu_ptr(kd_hotlock_cpu)->tables[kind]; }
/* A successful spin comparison consumes both counters before its one clock. */
static void check_clock_counters(void)
{
 assert(!this_cpu_read(kd_hotlock_spin_entries));
 assert(!this_cpu_read(kd_hotlock_spin_mcs));
}
/* These calls isolate exact-key sampling from real lock-entry accounting. */
static void hits(unsigned long addr, unsigned int n)
{ while(n--) { kd_hotlock_record_spin(addr); assert(!pins); } }
static void mcs(unsigned int n)
{
 unsigned int before_disable=disables, before_enable=enables;
 pins++;
 while(n--) kd_hotlock_record_spin_mcs_pinned();
 assert(pins==1 && disables==before_disable && enables==before_enable);
 pins--;
}
static void reset_policy(unsigned int limit)
{
 if(kd_hotlock_cpu) kd_hotlock_exit();
 cpu_id=pins=clocks=guards=pin_checks=0; now=1;
 spin_entry_ratio_limit=limit; kd_spin_delegate=true; check_spin_clock=false;
 mutex_entry_ratio_limit=KD_HOTLOCK_MUTEX_RATIO_DEFAULT;
 assert(!kd_hotlock_init());
}
/* Time/hash tests explicitly disable the additional contention policy. */
static void reset(void) { reset_policy(0); }
static void warm_spin(unsigned long addr)
{ mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL); hits(addr,KD_HOTLOCK_SPIN_SAMPLE_TARGET); }
static void check_chains(struct kd_hotlock_table *t)
{
 bool seen[KD_HOTLOCK_ENTRIES]={false}; unsigned int count=0;
 for(unsigned int b=0;b<KD_HOTLOCK_BUCKETS;b++) {
  for(u16 i=t->buckets[b];i;i=t->entries[i-1].next) {
   assert(i<=t->used && !seen[i-1]); seen[i-1]=true; count++;
   assert(kd_hotlock_bucket(t->entries[i-1].address)==b);
   assert(kd_hotlock_find(t,t->entries[i-1].address)==&t->entries[i-1]);
  }
 }
 assert(count==t->used);
}
static void init_and_pins(void)
{
 reset(); assert(sizeof(struct kd_hotlock_entry)==24 && clocks==1);
 /* Moving spin heat out of the table must not grow the per-CPU allocation. */
 assert(offsetof(struct kd_hotlock_table,rate_samples)==4);
 assert(offsetof(struct kd_hotlock_table,rate_begin)==8);
 assert(offsetof(struct kd_hotlock_table,entries)==536);
 assert(sizeof(struct kd_hotlock_table)==6680 && __alignof__(struct kd_hotlock_table)==8);
 assert(offsetof(struct kd_hotlock_cpu,tables[1])==6680);
 assert(offsetof(struct kd_hotlock_cpu,mutex_rate_hot)==13360);
 assert(sizeof(struct kd_hotlock_cpu)==13376 && __alignof__(struct kd_hotlock_cpu)==64);
 assert(stride==13376);
 for(unsigned int c=0;c<TEST_CPUS;c++) {
  assert(!per_cpu(kd_hotlock_spin_entries,c) && !per_cpu(kd_hotlock_spin_mcs,c));
  assert(!per_cpu(kd_hotlock_spin_gate,c));
  assert(!per_cpu_ptr(kd_hotlock_cpu,c)->mutex_rate_hot);
  for(unsigned int k=0;k<2;k++) {
   struct kd_hotlock_table *t=&per_cpu_ptr(kd_hotlock_cpu,c)->tables[k];
   assert(t->rate_begin==now && !t->rate_samples && !t->used && !t->busy);
  }
 }
 pins=1;
 unsigned int before_disable=disables, before_enable=enables;
 kd_hotlock_spin_entry_pinned();
 unsigned int before_checks=pin_checks;
 kd_hotlock_record_spin_pinned(0x1000);
 assert(pin_checks==before_checks); /* The caller already supplied the pin. */
 kd_hotlock_record_spin(0x1000);
 assert(pin_checks==before_checks+1); /* Generic callers keep their check. */
 kd_hotlock_record_spin_mcs_pinned(); kd_hotlock_query_spin(0x1000);
 assert(pins==1 && disables==before_disable && enables==before_enable);
 assert(this_cpu_read(kd_hotlock_spin_entries)==1 && !table(0)->busy);
 before_checks=pin_checks;
 kd_hotlock_record_mutex_pinned(0x2000);
 assert(pin_checks==before_checks && pins==1);
 pins=0; kd_hotlock_record_mutex(0x2000);
 assert(!pins && disables==before_disable+1 && enables==before_enable+1);
}
static void boundaries(void)
{
 reset();
 /* The selected cutoff scales with the CPU batch; lock heat stays at 512. */
 assert((1U<<KD_HOTLOCK_SPIN_RATIO_SHIFT)==KD_HOTLOCK_SPIN_MCS_INTERVAL);
 assert(KD_HOTLOCK_CHECK_INTERVAL==1024);
 assert(KD_HOTLOCK_SAMPLE_TARGET==1024 && KD_HOTLOCK_SPIN_SAMPLE_TARGET==512);
 assert(KD_HOTLOCK_CPU_WINDOW==40000000000UL && KD_HOTLOCK_INITIAL_WINDOW==2500000000UL);
 assert(KD_HOTLOCK_SPIN_INITIAL_WINDOW==1250000000UL);
 hits(0x1000,5000);
 assert(clocks==1 && !table(0)->used && !this_cpu_read(kd_hotlock_spin_gate));
 unsigned long origin=table(0)->rate_begin; now+=100;
 unsigned int initial_guards=guards;
 for(unsigned int i=1;i<KD_HOTLOCK_SPIN_MCS_INTERVAL;i++) {
  mcs(1);
  assert(clocks==1 && !this_cpu_read(kd_hotlock_spin_gate) && guards==initial_guards);
  assert(table(0)->rate_begin==origin && !table(0)->used);
  assert(this_cpu_read(kd_hotlock_spin_mcs)==i);
 }
 mcs(1);
 assert(clocks==2 && this_cpu_read(kd_hotlock_spin_gate) && !table(0)->used);
 assert(guards==initial_guards+1);
 assert(!this_cpu_read(kd_hotlock_spin_mcs) && !this_cpu_read(kd_hotlock_spin_entries));
 assert(table(0)->rate_begin==now);
 hits(0x1000,KD_HOTLOCK_SPIN_SAMPLE_TARGET-1);
 struct kd_hotlock_entry *slot=kd_hotlock_find(table(0),0x1000);
 assert(slot && slot->count==511 && !slot->hot && slot->begin==now && clocks==2);
 assert(kd_hotlock_record_spin(0x1000));
 assert(clocks==3 && !slot->count && slot->hot);
 struct kd_hotlock_table before=*table(0);
 unsigned long before_entries=this_cpu_read(kd_hotlock_spin_entries);
 unsigned long before_mcs=this_cpu_read(kd_hotlock_spin_mcs);
 for(unsigned int i=0;i<100;i++) assert(kd_hotlock_query_spin(0x1000));
 assert(clocks==3 && !memcmp(&before,table(0),sizeof(before)));
 assert(before_entries==this_cpu_read(kd_hotlock_spin_entries));
 assert(before_mcs==this_cpu_read(kd_hotlock_spin_mcs));
 assert(!this_cpu_read(kd_hotlock_spin_entries) && !kd_hotlock_query_mutex(0x1000));
 hits(0x1000,KD_HOTLOCK_SPIN_SAMPLE_TARGET-1); origin=slot->begin; now+=100;
 mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL);
 assert(clocks==4 && slot->count==511 && slot->hot && slot->begin==origin);
 assert(kd_hotlock_record_spin(0x1000)); assert(clocks==5 && !slot->count);
 now+=100; assert(!kd_hotlock_record_spin(0x2000));
 slot=kd_hotlock_find(table(0),0x2000);
 assert(slot && slot->begin==table(0)->rate_begin && slot->begin<now && clocks==5);
}
static void windows(void)
{
 reset(); warm_spin(0x1000);
 struct kd_hotlock_entry *slot=kd_hotlock_find(table(0),0x1000);
 now=slot->begin+KD_HOTLOCK_SPIN_INITIAL_WINDOW-1;
 hits(0x1000,KD_HOTLOCK_SPIN_SAMPLE_TARGET-1);
 assert(kd_hotlock_record_spin(0x1000) && slot->hot && !slot->count);
 now=slot->begin+KD_HOTLOCK_SPIN_INITIAL_WINDOW;
 mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL);
 assert(slot->hot && !slot->count); /* CPU tick preserves a continuous epoch. */
 hits(0x1000,KD_HOTLOCK_SPIN_SAMPLE_TARGET-1); assert(slot->hot);
 assert(!kd_hotlock_record_spin(0x1000)); /* Equality is cold. */
 assert(!slot->hot && !slot->count && slot->begin==now && this_cpu_read(kd_hotlock_spin_gate));
 hits(0x1000,KD_HOTLOCK_SPIN_SAMPLE_TARGET); assert(slot->hot);
 now=table(0)->rate_begin+KD_HOTLOCK_CPU_WINDOW;
 assert(kd_hotlock_query_spin(0x1000)); /* Cached until a sampling boundary. */
 mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL);
 assert(!this_cpu_read(kd_hotlock_spin_gate) && !slot->hot && !slot->count && !kd_hotlock_query_spin(0x1000));
 hits(0x1000,2000); assert(!this_cpu_read(kd_hotlock_spin_gate) && !slot->count);
 mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL);
 assert(this_cpu_read(kd_hotlock_spin_gate) && !slot->hot && !slot->count && slot->begin==now);
 hits(0x1000,KD_HOTLOCK_SPIN_SAMPLE_TARGET); assert(slot->hot);
 reset(); now+=KD_HOTLOCK_CPU_WINDOW-1;
 mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL); assert(this_cpu_read(kd_hotlock_spin_gate));
 reset(); now+=KD_HOTLOCK_CPU_WINDOW;
 mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL); assert(!this_cpu_read(kd_hotlock_spin_gate));
}
static void hash_and_capacity(void)
{
 unsigned long keys[KD_HOTLOCK_ENTRIES+1]; unsigned int n=0;
 reset();
 for(unsigned long k=1;n<KD_HOTLOCK_ENTRIES+1;k++)
  if(kd_hotlock_bucket(k)==0) keys[n++]=k;
 warm_spin(keys[0]);
 for(unsigned int i=1;i<KD_HOTLOCK_ENTRIES;i++) {
  hits(keys[i],i%32+1); assert(kd_hotlock_find(table(0),keys[i])->count==i%32+1);
 }
 check_chains(table(0)); assert(table(0)->used==KD_HOTLOCK_ENTRIES);
 assert(kd_hotlock_query_spin(keys[0]));
 struct kd_hotlock_entry saved[KD_HOTLOCK_ENTRIES]; memcpy(saved,table(0)->entries,sizeof(saved));
 hits(keys[KD_HOTLOCK_ENTRIES],2048);
 assert(!kd_hotlock_find(table(0),keys[KD_HOTLOCK_ENTRIES]));
 assert(!memcmp(saved,table(0)->entries,sizeof(saved)) && !kd_hotlock_query_spin(keys[KD_HOTLOCK_ENTRIES]));
 for(unsigned int i=0;i<KD_HOTLOCK_ENTRIES;i++) assert(kd_hotlock_find(table(0),keys[i]));
 hits(keys[0],KD_HOTLOCK_SPIN_SAMPLE_TARGET); assert(kd_hotlock_query_spin(keys[0]));
 now=table(0)->rate_begin+KD_HOTLOCK_CPU_WINDOW; mcs(KD_HOTLOCK_SPIN_MCS_INTERVAL);
 assert(!this_cpu_read(kd_hotlock_spin_gate) && table(0)->used==KD_HOTLOCK_ENTRIES);
 for(unsigned int i=0;i<KD_HOTLOCK_ENTRIES;i++) {
  struct kd_hotlock_entry *s=kd_hotlock_find(table(0),keys[i]); assert(s && !s->hot && !s->count);
 }
 check_chains(table(0));
}
static void mutex_sampling(void)
{
 reset();
 unsigned long before_entries=this_cpu_read(kd_hotlock_spin_entries);
 unsigned long before_mcs=this_cpu_read(kd_hotlock_spin_mcs);
 for(unsigned int i=0;i<KD_HOTLOCK_CHECK_INTERVAL-1;i++) assert(!kd_hotlock_record_mutex(0x1000));
 assert(clocks==1 && !this_cpu_ptr(kd_hotlock_cpu)->mutex_rate_hot && !table(1)->used);
 assert(!kd_hotlock_record_mutex(0x1000)); assert(clocks==2 && this_cpu_ptr(kd_hotlock_cpu)->mutex_rate_hot);
 assert(before_entries==this_cpu_read(kd_hotlock_spin_entries));
 assert(before_mcs==this_cpu_read(kd_hotlock_spin_mcs));
 struct kd_hotlock_entry *s=kd_hotlock_find(table(1),0x1000); assert(s && s->count==1);
 for(unsigned int i=1;i<KD_HOTLOCK_SAMPLE_TARGET;i++) assert(!kd_hotlock_record_mutex(0x1000));
 assert(s->count==KD_HOTLOCK_SAMPLE_TARGET);
 assert(kd_hotlock_record_mutex(0x1000)); assert(s->hot && !s->count);
 /* Spin's shorter epoch must not change the mutex frequency criterion.
  * Just below 2.5e9 remains hot, equality cools, and a fresh batch can reheat. */
 now=s->begin+KD_HOTLOCK_INITIAL_WINDOW-1;
 for(unsigned int i=0;i<KD_HOTLOCK_SAMPLE_TARGET;i++) assert(kd_hotlock_record_mutex(0x1000));
 assert(kd_hotlock_record_mutex(0x1000) && s->hot && !s->count);
 now=s->begin+KD_HOTLOCK_INITIAL_WINDOW;
 for(unsigned int i=0;i<KD_HOTLOCK_SAMPLE_TARGET;i++) assert(kd_hotlock_record_mutex(0x1000));
 assert(!kd_hotlock_record_mutex(0x1000) && !s->hot && !s->count);
 for(unsigned int i=0;i<KD_HOTLOCK_SAMPLE_TARGET;i++) assert(!kd_hotlock_record_mutex(0x1000));
 assert(kd_hotlock_record_mutex(0x1000) && s->hot && !s->count);
 /* Drive natural records until CPU and lock windows close together; their
  * relatively prime intervals make the shared timestamp case infrequent. */
 for(unsigned int i=0;;i++) {
  assert(i<2*KD_HOTLOCK_CHECK_INTERVAL*(KD_HOTLOCK_SAMPLE_TARGET+1));
  if(table(1)->rate_samples==KD_HOTLOCK_CHECK_INTERVAL-1 && s->count==KD_HOTLOCK_SAMPLE_TARGET) break;
  assert(kd_hotlock_record_mutex(0x1000));
 }
 unsigned int before_clocks=clocks;
 assert(kd_hotlock_record_mutex(0x1000));
 assert(clocks==before_clocks+1 && !table(1)->rate_samples && !s->count);
 struct kd_hotlock_table before=*table(1);
 for(unsigned int i=0;i<100;i++) assert(kd_hotlock_query_mutex(0x1000));
 assert(!memcmp(&before,table(1),sizeof(before)) && clocks==before_clocks+1);
 assert(!table(0)->rate_samples && !this_cpu_read(kd_hotlock_spin_gate) && !table(0)->used);
 now=table(1)->rate_begin+KD_HOTLOCK_CPU_WINDOW-1;
 for(unsigned int i=0;i<KD_HOTLOCK_CHECK_INTERVAL;i++) kd_hotlock_record_mutex(0x1000);
 assert(this_cpu_ptr(kd_hotlock_cpu)->mutex_rate_hot && !table(1)->rate_samples);
 now=table(1)->rate_begin+KD_HOTLOCK_CPU_WINDOW;
 for(unsigned int i=0;i<KD_HOTLOCK_CHECK_INTERVAL-1;i++) kd_hotlock_record_mutex(0x1000);
 assert(this_cpu_ptr(kd_hotlock_cpu)->mutex_rate_hot); assert(!kd_hotlock_record_mutex(0x1000));
 assert(!this_cpu_ptr(kd_hotlock_cpu)->mutex_rate_hot && !s->count && !s->hot && s->begin==now);
 assert(before_entries==this_cpu_read(kd_hotlock_spin_entries));
 assert(before_mcs==this_cpu_read(kd_hotlock_spin_mcs));
}
/* Successful native attempts count toward the ratio without a clock or lock
 * observation. A guarded contention delays, rather than loses, comparison. */
static void mutex_contention_ratio(void)
{
 for(unsigned int limit=2;limit<=256;limit*=2) {
 const unsigned int bound=limit*1024;
 for(unsigned int entries=bound-1;entries<=bound;entries++) {
  reset();
  mutex_entry_ratio_limit=limit;
  for(unsigned int i=0;i<entries;i++) kd_hotlock_mutex_entry();
  assert(!pins && clocks==1 && !this_cpu_read(kd_hotlock_mutex_contentions));
  pins++;
  unsigned int before_guards=guards, before_checks=pin_checks;
  struct kd_hotlock_table cold=*table(1);
  for(unsigned int i=0;i<1023;i++) assert(!kd_hotlock_record_mutex_pinned(0x3000));
  assert(guards==before_guards && pin_checks==before_checks);
  assert(!memcmp(&cold,table(1),sizeof(cold)));
  assert(clocks==1 && this_cpu_read(kd_hotlock_mutex_entries)==entries);
  table(1)->busy=1;
  assert(!kd_hotlock_record_mutex(0x3000));
  assert(clocks==1 && this_cpu_read(kd_hotlock_mutex_contentions)==1024);
  table(1)->busy=0;
  assert(!kd_hotlock_record_mutex(0x3000));
  assert(clocks==2 && !this_cpu_read(kd_hotlock_mutex_entries));
  assert(!this_cpu_read(kd_hotlock_mutex_contentions) && !table(1)->rate_samples);
  assert(this_cpu_ptr(kd_hotlock_cpu)->mutex_rate_hot==(entries<bound));
  assert(!this_cpu_read(kd_hotlock_spin_entries) && !this_cpu_read(kd_hotlock_spin_mcs));
  pins--;
 }
 }
}
/* CPU isolation and the table guard protect hash mutation, independent of
 * whether approximate profiling samples lose or merge interrupt activity. */
static void isolation_and_guard(void)
{
 reset(); warm_spin(0x1000);
 cpu_id=1; assert(!kd_hotlock_query_spin(0x1000));
 assert(!kd_hotlock_record_mutex(0x1000) && !pins);
 cpu_id=0; assert(kd_hotlock_query_spin(0x1000));
 table(0)->busy=1;
 struct kd_hotlock_table before=*table(0);
 assert(!kd_hotlock_record_spin(0xdead) && !kd_hotlock_query_spin(0x1000));
 assert(!memcmp(&before,table(0),sizeof(before)));
 table(0)->busy=0;
 assert(kd_hotlock_query_spin(0x1000));
}
static void queue_event(void)
{
 struct qspinlock word={0}; unsigned int before_disable=disables, before_enable=enables;
 pins++; assert(!xchg_tail(&word,1U<<16) && word.tail==1);
 assert(pins==1 && disables==before_disable && enables==before_enable); pins--;
}
/* Native fast entries add only to the denominator; queued native entries also
 * use the same production tail-publication hook as delegated acquisitions. */
static void native_batch(unsigned int entries, unsigned int publications)
{
 assert(entries>=publications);
 for(unsigned int i=0;i<entries;i++) {
  pins++; kd_hotlock_spin_entry_pinned(); pins--;
  if(i>=entries-publications) queue_event();
 }
}
static void mcs_publications(void)
{
 reset(); kd_spin_delegate=false;
 for(unsigned int i=0;i<KD_HOTLOCK_SPIN_MCS_INTERVAL;i++) queue_event();
 assert(!this_cpu_read(kd_hotlock_spin_gate) && clocks==1 && !this_cpu_read(kd_hotlock_spin_mcs));
 kd_spin_delegate=true;
 for(unsigned int i=0;i<KD_HOTLOCK_SPIN_MCS_INTERVAL-1;i++) queue_event();
 assert(!this_cpu_read(kd_hotlock_spin_gate) && clocks==1);
 queue_event(); assert(this_cpu_read(kd_hotlock_spin_gate) && clocks==2);
 assert(!this_cpu_read(kd_hotlock_spin_mcs));
 cpu_id=1; assert(!kd_hotlock_spin_cpu_hot_pinned());
 native_batch(KD_HOTLOCK_SPIN_MCS_INTERVAL,KD_HOTLOCK_SPIN_MCS_INTERVAL);
 assert(this_cpu_read(kd_hotlock_spin_gate) && clocks==3);
 cpu_id=0; assert(kd_hotlock_spin_cpu_hot_pinned());
}
static void contention_ratio(void)
{
 const unsigned int interval=KD_HOTLOCK_SPIN_MCS_INTERVAL;
 reset_policy(2);
 native_batch(2*interval-2,interval-1);
 assert(!this_cpu_read(kd_hotlock_spin_gate) && clocks==1);
 assert(this_cpu_read(kd_hotlock_spin_entries)==2*interval-2 && this_cpu_read(kd_hotlock_spin_mcs)==interval-1);
 check_spin_clock=true; now+=100; native_batch(1,1);
 check_spin_clock=false;
 assert(this_cpu_read(kd_hotlock_spin_gate) && clocks==2 && table(0)->rate_begin==now);
 assert(!this_cpu_read(kd_hotlock_spin_entries) && !this_cpu_read(kd_hotlock_spin_mcs));
 hits(0x1000,512); assert(kd_hotlock_query_spin(0x1000));
 struct kd_hotlock_entry *slot=kd_hotlock_find(table(0),0x1000);
 native_batch(2*interval-1,interval); /* Just below the strict entry bound. */
 assert(kd_hotlock_query_spin(0x1000));
 unsigned int before_clocks=clocks;
 native_batch(interval,0); native_batch(interval-1,interval-1);
 assert(kd_hotlock_query_spin(0x1000) && clocks==before_clocks);
 check_spin_clock=true; now+=100; native_batch(1,1); /* Twice the interval rejects equality. */
 check_spin_clock=false;
 assert(!this_cpu_read(kd_hotlock_spin_gate) && !slot->hot && !slot->count && slot->begin==now);
 assert(!kd_hotlock_query_spin(0x1000));
 assert(!this_cpu_read(kd_hotlock_spin_entries) && !this_cpu_read(kd_hotlock_spin_mcs));
 /* Cold native publications recover without a separate retry policy. */
 native_batch(interval,interval); assert(this_cpu_read(kd_hotlock_spin_gate));
 assert(!slot->hot && !slot->count && !kd_hotlock_query_spin(0x1000));
 hits(0x1000,511); assert(!kd_hotlock_query_spin(0x1000));
 assert(kd_hotlock_record_spin(0x1000));
 /* Startup fast entries count immediately; there is no first-window priming. */
 reset_policy(2); native_batch(48000+interval,interval);
 assert(!this_cpu_read(kd_hotlock_spin_gate) && clocks==2);
 assert(!this_cpu_read(kd_hotlock_spin_entries) && !this_cpu_read(kd_hotlock_spin_mcs));
 native_batch(interval,interval); assert(this_cpu_read(kd_hotlock_spin_gate) && clocks==3);
 reset_policy(4); native_batch(4*interval-1,interval); assert(this_cpu_read(kd_hotlock_spin_gate));
 native_batch(4*interval,interval); assert(!this_cpu_read(kd_hotlock_spin_gate));
 native_batch(interval,interval); assert(this_cpu_read(kd_hotlock_spin_gate));
 /* Zero bypasses only the ratio, not CPU or lock frequency. */
 reset_policy(0); assert(!kd_hotlock_record_spin(0x1000));
 native_batch(8*interval,interval); native_batch(8*interval,interval);
 assert(this_cpu_read(kd_hotlock_spin_gate));
 assert(!this_cpu_read(kd_hotlock_spin_entries) && !this_cpu_read(kd_hotlock_spin_mcs));
 assert(!kd_hotlock_record_spin(0x1000));
 hits(0x1000,511); assert(kd_hotlock_query_spin(0x1000));
 now=table(0)->rate_begin+KD_HOTLOCK_CPU_WINDOW;
 native_batch(interval,interval); assert(!this_cpu_read(kd_hotlock_spin_gate));
 assert(!kd_hotlock_record_spin(0x1000));
 /* A comparison clears only its CPU's window. */
 reset_policy(2); native_batch(2*interval,interval-1);
 cpu_id=1; native_batch(2*interval-1,interval);
 assert(this_cpu_read(kd_hotlock_spin_gate) && clocks==2);
 assert(!this_cpu_read(kd_hotlock_spin_entries) && !this_cpu_read(kd_hotlock_spin_mcs));
 cpu_id=0;
 assert(this_cpu_read(kd_hotlock_spin_entries)==2*interval && this_cpu_read(kd_hotlock_spin_mcs)==interval-1);
 native_batch(1,1); assert(!this_cpu_read(kd_hotlock_spin_gate) && clocks==3);
 assert(per_cpu(kd_hotlock_spin_gate,1) && !per_cpu(kd_hotlock_spin_entries,1) && !per_cpu(kd_hotlock_spin_mcs,1));
 reset_policy(2); native_batch(3000,0);
 for(unsigned int i=0;i<KD_HOTLOCK_CHECK_INTERVAL;i++) kd_hotlock_record_mutex(0x2000);
 assert(this_cpu_ptr(kd_hotlock_cpu)->mutex_rate_hot && !this_cpu_read(kd_hotlock_spin_gate));
 assert(this_cpu_read(kd_hotlock_spin_entries)==3000 && !this_cpu_read(kd_hotlock_spin_mcs));
}
/* A busy exact table defers the whole sample. The next publication retries,
 * even beyond the interval; the approximate denominator still includes skipped entries. */
static void busy_sampling_retry(void)
{
 const unsigned int interval=KD_HOTLOCK_SPIN_MCS_INTERVAL;
 reset_policy(2); native_batch(interval,interval); hits(0x1000,512);
 assert(kd_hotlock_query_spin(0x1000));
 native_batch(2*interval-1,interval-1);
 table(0)->busy=1;
 struct kd_hotlock_table before=*table(0);
 unsigned int before_clocks=clocks, before_guards=guards;
 now+=100;
 native_batch(1,1);
 assert(this_cpu_read(kd_hotlock_spin_entries)==2*interval && this_cpu_read(kd_hotlock_spin_mcs)==interval);
 native_batch(1,1);
 assert(this_cpu_read(kd_hotlock_spin_entries)==2*interval+1 && this_cpu_read(kd_hotlock_spin_mcs)==interval+1);
 assert(this_cpu_read(kd_hotlock_spin_gate) && clocks==before_clocks && guards==before_guards);
 assert(!memcmp(&before,table(0),sizeof(before)));
 table(0)->busy=0;
 check_spin_clock=true; native_batch(1,1); check_spin_clock=false;
 assert(!this_cpu_read(kd_hotlock_spin_gate) && clocks==before_clocks+1 && guards==before_guards+1);
 assert(!this_cpu_read(kd_hotlock_spin_entries) && !this_cpu_read(kd_hotlock_spin_mcs));
 assert(table(0)->rate_begin==now && !kd_hotlock_query_spin(0x1000));
 native_batch(interval,interval); assert(this_cpu_read(kd_hotlock_spin_gate));
}
/* A native-head veto changes CPU admission only. Publication sampling still
 * controls retry, and reheating requires a fresh per-lock sample epoch. */
static void native_queue_cooling(void)
{
 const unsigned int interval=KD_HOTLOCK_SPIN_MCS_INTERVAL;
 reset_policy(2); native_batch(interval,interval); hits(0x1000,512);
 assert(kd_hotlock_query_spin(0x1000));
 struct kd_hotlock_table before=*table(0);
 unsigned long entries=this_cpu_read(kd_hotlock_spin_entries), publications=this_cpu_read(kd_hotlock_spin_mcs);
 unsigned int before_clocks=clocks, before_pins=pin_checks, before_guards=guards;
 pins=1; kd_hotlock_cool_spin_pinned(); assert(pins==1); pins=0;
 assert(!this_cpu_read(kd_hotlock_spin_gate));
 assert(!memcmp(&before,table(0),sizeof(before)));
 assert(entries==this_cpu_read(kd_hotlock_spin_entries) && publications==this_cpu_read(kd_hotlock_spin_mcs));
 assert(clocks==before_clocks && pin_checks==before_pins && guards==before_guards);
 assert(!kd_hotlock_query_spin(0x1000));
 native_batch(interval-1,interval-1); assert(!this_cpu_read(kd_hotlock_spin_gate));
 native_batch(1,1); assert(this_cpu_read(kd_hotlock_spin_gate) && !kd_hotlock_query_spin(0x1000));
 hits(0x1000,511); assert(!kd_hotlock_query_spin(0x1000));
 assert(kd_hotlock_record_spin(0x1000));
}
int main(void)
{
 assert(spin_entry_ratio_limit==2);
 assert(mutex_entry_ratio_limit==256);
 init_and_pins(); boundaries(); windows(); hash_and_capacity(); mutex_sampling(); mutex_contention_ratio();
 isolation_and_guard(); mcs_publications(); contention_ratio(); busy_sampling_retry(); native_queue_cooling();
 kd_hotlock_exit();
 const unsigned int invalid[]={1,3,6,UINT_MAX};
 for(unsigned int i=0;i<sizeof(invalid)/sizeof(invalid[0]);i++) {
  spin_entry_ratio_limit=invalid[i]; assert(kd_hotlock_init()==-EINVAL && !kd_hotlock_cpu);
 }
 const unsigned int valid[]={0,2,4,1U<<31};
 for(unsigned int i=0;i<sizeof(valid)/sizeof(valid[0]);i++) {
  spin_entry_ratio_limit=valid[i]; assert(!kd_hotlock_init()); kd_hotlock_exit();
 }
 const unsigned int invalid_mutex[]={0,1,3,6,257,512,UINT_MAX};
 for(unsigned int i=0;i<sizeof(invalid_mutex)/sizeof(invalid_mutex[0]);i++) {
  mutex_entry_ratio_limit=invalid_mutex[i]; assert(kd_hotlock_init()==-EINVAL && !kd_hotlock_cpu);
 }
 mutex_entry_ratio_limit=KD_HOTLOCK_MUTEX_RATIO_DEFAULT;
 fail_alloc=true; assert(kd_hotlock_init()==-ENOMEM); assert(!kd_hotlock_cpu);
 printf("PASS hotlock: shared MCS%u/ratio/CPU clock, independent spin512 and mutex1025 windows, exact keys/capacity, pins, read-only queries\n",KD_HOTLOCK_SPIN_MCS_INTERVAL);
 puts("PASS contention admission: native denominator, shifted ratio boundaries, first-window rejection, cold recovery, CPU isolation, zero ratio bypass, busy retry");
 return 0;
}
