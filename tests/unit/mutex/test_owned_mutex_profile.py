"""Guest-only extraction of diagnostic probe registration and return handlers.

No probes are installed by this fixture. Kernel registration/timer operations
are modeled to check error unwinding, target filtering and ABI result widths.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from source_text import ROOT, without_includes

FIXTURE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef unsigned long long u64;
typedef unsigned long atomic_long_t;
struct pt_regs { unsigned long di, ax; };
struct kprobe {
 const char *symbol_name;
 int (*pre_handler)(struct kprobe *, struct pt_regs *);
 unsigned long nmissed;
};
struct kretprobe_instance { unsigned long data[4]; };
struct kretprobe {
 struct kprobe kp; int maxactive; size_t data_size;
 int (*entry_handler)(struct kretprobe_instance *, struct pt_regs *);
 int (*handler)(struct kretprobe_instance *, struct pt_regs *);
 unsigned long nmissed;
};
enum hrtimer_restart { HRTIMER_RESTART = 1 };
struct hrtimer { enum hrtimer_restart (*function)(struct hrtimer *); };
#define CLOCK_MONOTONIC 1
#define HRTIMER_MODE_REL_PINNED 1
#define __init
#define __exit
#define module_param(...)
#define MODULE_PARM_DESC(...)
#define module_init(...)
#define module_exit(...)
#define MODULE_LICENSE(...)
#define MODULE_DESCRIPTION(...)
#define __percpu
#define PROFILE_CPUS 2
#define alloc_percpu(type) allocate_counts(sizeof(type))
#define this_cpu_ptr(p) ((__typeof__(p)) checked_counts((p), test_cpu))
#define per_cpu_ptr(p,cpu) ((__typeof__(p)) checked_counts((p), (cpu)))
#define for_each_possible_cpu(cpu) for ((cpu)=0;(cpu)<PROFILE_CPUS;(cpu)++)
#define READ_ONCE(x) (*(volatile __typeof__(x) *)&(x))
#define atomic_long_read(p) READ_ONCE(*(p))
#define ns_to_ktime(n) (n)
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define min_t(type,a,b) ((type)(a)<(type)(b)?(type)(a):(type)(b))
#define regs_return_value(p) ((p)->ax)
static unsigned long __per_cpu_offset[PROFILE_CPUS];
static unsigned int test_cpu;
static unsigned int raw_smp_processor_id(void) { return test_cpu; }
static unsigned int fls64(u64 n) { return 64-__builtin_clzll(n); }
static unsigned int registrations, fail_registration, depth;
static const void *registered[16];
static bool timer_active;
static bool fail_allocation;
static void *allocated_counts;
static size_t counts_stride;
static unsigned int allocations, frees;
static void *allocate_counts(size_t stride)
{
 assert(!allocated_counts && !depth && !timer_active);
 allocations++;
 if (fail_allocation) return NULL;
 counts_stride=stride;
 allocated_counts=calloc(PROFILE_CPUS,stride);assert(allocated_counts);
 return allocated_counts;
}
static void *checked_counts(void *p, unsigned int cpu)
{
 assert(p && p==allocated_counts && cpu<PROFILE_CPUS);
 return (char *)p + cpu*counts_stride;
}
static void free_percpu(void *p)
{
 assert(p && p==allocated_counts && !depth && !timer_active);
 free(p);allocated_counts=NULL;frees++;
}
static char output[16384];
static size_t output_used;
#define pr_info(...) do { \
 int length=snprintf(output+output_used,sizeof(output)-output_used,__VA_ARGS__); \
 assert(length>0 && (size_t)length<sizeof(output)-output_used); output_used+=length; \
} while (0)
static int register_one(const void *address)
{
 assert(allocated_counts && depth<ARRAY_SIZE(registered));
 if (++registrations==fail_registration) return -EINVAL;
 registered[depth++]=address; return 0;
}
static void unregister_one(const void *address)
{
 assert(allocated_counts && depth && registered[depth-1]==address); depth--;
}
static int register_kprobe(struct kprobe *p) { return register_one(p); }
static void unregister_kprobe(struct kprobe *p) { unregister_one(p); }
static int register_kprobes(struct kprobe **p, unsigned int n)
{
 assert(n==4); return register_one(p);
}
static void unregister_kprobes(struct kprobe **p, unsigned int n)
{
 assert(n==4); unregister_one(p);
}
static int register_kretprobe(struct kretprobe *p) { return register_one(p); }
static void unregister_kretprobe(struct kretprobe *p) { unregister_one(p); }
static void hrtimer_init(struct hrtimer *timer,int clock,int mode)
{
 assert(!timer_active && clock==CLOCK_MONOTONIC && mode==HRTIMER_MODE_REL_PINNED);
}
static void hrtimer_start(struct hrtimer *timer,unsigned long interval,int mode)
{
 assert(timer->function && interval==100000 && mode==HRTIMER_MODE_REL_PINNED);
 timer_active=true;
}
static void hrtimer_cancel(struct hrtimer *timer) { assert(timer_active);timer_active=false; }
static void hrtimer_forward_now(struct hrtimer *timer,unsigned long interval) { }
#include "profile_production.h"
static void reset(unsigned int failure)
{
 assert(!depth && !timer_active && !allocated_counts && !counts);
 registrations=0;fail_registration=failure;output_used=0;output[0]=0;
 target_lock=0x1000;success_counter=0x2000;kd=owned=preflight=true;spin=false;
 local_first=false;
 allocations=frees=0;fail_allocation=false;test_cpu=0;
 preflight_probe.nmissed=preflight_probe.kp.nmissed=0;
 optimistic_probe.nmissed=optimistic_probe.kp.nmissed=0;
 local_first_probe.nmissed=local_first_probe.kp.nmissed=0;
 owned_wait_probe.nmissed=0;
 last_owner=owner_samples=owner_zero=owner_changes=0;
}
int main(void)
{
 /* Exercise the actual sampler: all owned flags leave identity unchanged,
  * ownerless D is zero, and the Native format retains bit 3 as pointer data. */
 unsigned long owner_word;
 reset(0);target_lock=(unsigned long)&owner_word;
 for(unsigned long flags=0;flags<16;flags++) {
  owner_word=0x8000|flags;sample_owner(&owner_timer);
  assert(last_owner==0x8000 && owner_changes==0 && owner_zero==0);
 }
 owner_word=8;sample_owner(&owner_timer);
 assert(owner_zero==1 && owner_changes==0);
 owner_word=0x900f;sample_owner(&owner_timer);
 assert(last_owner==0x9000 && owner_changes==1 && owner_samples==18);
 reset(0);owned=false;target_lock=(unsigned long)&owner_word;
 for(unsigned long flags=0;flags<8;flags++) {
  owner_word=0x8008|flags;sample_owner(&owner_timer);
  assert(last_owner==0x8008 && owner_changes==0 && owner_zero==0);
 }
 /* Allocation refusal installs no callback, and invalid parameters do not
  * allocate. Every supported mode frees after its successful probe prefix. */
 reset(0);fail_allocation=true;
 assert(profile_init()==-ENOMEM && allocations==1 && !frees && !counts);
 assert(!allocated_counts && !registrations && !depth && !timer_active);
 reset(0);target_lock=0;
 assert(profile_init()==-EINVAL && !allocations && !counts && !depth);
 const struct { bool kd_mode, spin_mode, owned_mode; unsigned int probes; } modes[] = {
  {false,false,false,2}, {false,true,false,1},
  {true,false,false,4}, {true,false,true,5},
 };
 for(unsigned int mode=0;mode<ARRAY_SIZE(modes);mode++) {
  for(unsigned int failure=0;failure<=modes[mode].probes;failure++) {
   reset(failure);kd=modes[mode].kd_mode;spin=modes[mode].spin_mode;
   owned=modes[mode].owned_mode;preflight=false;
   int result=profile_init();
   if(failure) assert(result==-EINVAL && registrations==failure);
   else { assert(!result && depth==modes[mode].probes);profile_exit(); }
   assert(!counts && !allocated_counts && !depth && !timer_active);
   assert(allocations==1 && frees==1);
  }
 }
 /* Every registration boundary, including both new return probes, must
  * unwind exactly the successful prefix without a lingering timer/probe. */
 for(unsigned int failure=1;failure<=7;failure++) {
  reset(failure);assert(profile_init()==-EINVAL);
  assert(!depth && !timer_active && registrations==failure);
 }
 reset(0);owned=kd=false;
 assert(profile_init()==-EINVAL && !registrations && !depth);
 reset(0);assert(profile_init()==0 && depth==7 && timer_active);
 assert(preflight_probe.entry_handler==admission_entry);
 assert(optimistic_probe.entry_handler==admission_entry);
 struct kretprobe_instance instance={0};
 struct pt_regs regs={.di=target_lock+8};
 assert(admission_entry(&instance,&regs)==1);
 native_entry(&owned_wait_probe,&regs);assert(counts->owned_wait==0);
 regs.di=target_lock;assert(admission_entry(&instance,&regs)==0);
 native_entry(&owned_wait_probe,&regs);
 assert(counts->owned_wait==1 && counts->owned_calls==0 && counts->owned_slow==0 && counts->native_slow==0);
 regs.ax=0x100;preflight_return(&instance,&regs); /* AL zero, upper bits nonzero. */
 regs.ax=0x1234567800000001UL;preflight_return(&instance,&regs);
 assert(counts->gate_self==1 && counts->gate_capture==1);
 for(unsigned int value=0;value<=3;value++) {
  regs.ax=0x1234567800000000UL|value;optimistic_return(&instance,&regs);
 }
 assert(counts->optimistic_acquired==1 && counts->optimistic_busy==1 &&
        counts->optimistic_self==1 && counts->optimistic_other==1);
 preflight_probe.nmissed=3;preflight_probe.kp.nmissed=2;
 profile_exit();assert(!depth && !timer_active);
 assert(strstr(output,"kd_mutex_profile ownedpreflight: gate_self=1 gate_capture=1"));
 assert(strstr(output,"optimistic_other=1 missed=5"));
 assert(strstr(output,"self_calls=0 self_slow=0 self_wait=1 missed=0"));
 reset(0);preflight=false;assert(profile_init()==0 && depth==5);
 /* A return on another CPU must survive aggregation of all possible CPUs. */
 test_cpu=1;regs.di=target_lock;native_entry(&owned_wait_probe,&regs);
 assert(!counts->owned_wait && per_cpu_ptr(counts,1)->owned_wait==1);
 profile_exit();assert(!depth && !timer_active && !counts && !allocated_counts);
 assert(strstr(output,"self_calls=0 self_slow=0 self_wait=1 missed=0"));
 assert(!strstr(output,"ownedpreflight:"));
 assert(!strstr(output,"ownedlocalfirst:"));
 /* ABI4 uses one different helper probe; no old gate probe is registered. */
 for(unsigned int failure=1;failure<=6;failure++) {
  reset(failure);preflight=false;local_first=true;
  assert(profile_init()==-EINVAL);
  assert(!depth && !timer_active && registrations==failure);
 }
 reset(0);local_first=true;
 assert(profile_init()==-EINVAL && !registrations && !depth);
 reset(0);preflight=false;local_first=true;
 assert(profile_init()==0 && depth==6 && timer_active);
 assert(local_first_probe.entry_handler==admission_entry);
 assert(!strcmp(local_first_probe.kp.symbol_name,"kd_owned_mutex_outer_cabi_gate"));
 regs.di=target_lock+8;assert(local_first_probe.entry_handler(&instance,&regs)==1);
 regs.di=target_lock;assert(local_first_probe.entry_handler(&instance,&regs)==0);
 /* Full-width cookie pointers may have a zero low byte or low dword.
  * Cover a second CPU, aggregate lifetime and exact missed-return counts. */
 regs.ax=0;local_first_return(&instance,&regs);
 regs.ax=0x8765432100000000UL;local_first_return(&instance,&regs);
 assert(counts->local_first_acquired==1 && counts->local_first_failed==1);
 test_cpu=1;
 regs.ax=0;local_first_return(&instance,&regs);
 regs.ax=0xfeedbeef00000100UL;local_first_return(&instance,&regs);
 assert(per_cpu_ptr(counts,1)->local_first_acquired==1 &&
        per_cpu_ptr(counts,1)->local_first_failed==1);
 local_first_probe.nmissed=3;local_first_probe.kp.nmissed=2;
 profile_exit();assert(!depth && !timer_active);
 assert(strstr(output,"ownedlocalfirst: acquired=2 failed=2 missed=5"));
 assert(!strstr(output,"ownedpreflight:"));
 puts("PASS diagnostic preflight probes: dynamic allocation/unwinds, two-CPU aggregation, target filter, bool/enum ABI and missed returns");
 return 0;
}
'''


def main():
    source = without_includes((ROOT/'tests/kernel/mutex/profile/kd_mutex_profile.c').read_text())
    mutations = {
        'leak-init-counters': (
            'free_counts:\n\tfree_percpu(counts);',
            'free_counts:\n\t/* leaked allocation */'),
        'leak-exit-counters': (
            'free_percpu(counts);\n\tcounts = NULL;\n\tpr_info(',
            '/* leaked allocation */\n\tcounts = NULL;\n\tpr_info('),
        'free-before-probe-drain': (
            '\tif (!spin)\n\t\thrtimer_cancel(&owner_timer);',
            '\tfree_percpu(counts);\n\tif (!spin)\n\t\thrtimer_cancel(&owner_timer);'),
        'omit-secondary-cpu': (
            'for_each_possible_cpu(cpu) {',
            'for (cpu = 0; cpu < 1; cpu++) {'),
        'leak-preflight-registration': (
            'preflight_gate:\n\tunregister_kretprobe(&preflight_probe);',
            'preflight_gate:\n\t/* leaked registration */'),
        'accept-other-lock': ('return regs->di != target_lock;', 'return 0;'),
        'bool-upper-bits': ('regs_return_value(regs) & 0xff', 'regs_return_value(regs)'),
        'enum-upper-bits': ('switch ((unsigned int)regs_return_value(regs))',
                            'switch (regs_return_value(regs))'),
        'discard-unknown-enum': ('default: c->optimistic_other++; break;', 'default: break;'),
        'omit-nested-probe-misses': (
            'preflight_probe.nmissed + preflight_probe.kp.nmissed +',
            'preflight_probe.nmissed +'),
        'reverse-local-first-outcome': (
            'c->local_first_acquired++;', 'c->local_first_failed++;'),
        'local-first-bool-eax': (
            'if (regs_return_value(regs))\n\t\tc->local_first_acquired++;',
            'if (regs_return_value(regs) & 0xff)\n\t\tc->local_first_acquired++;'),
        'omit-local-first-probe-misses': (
            'local_first_probe.nmissed + local_first_probe.kp.nmissed',
            'local_first_probe.nmissed'),
        'leak-local-first-registration': (
            'if (local_first)\n\t\tunregister_kretprobe(&local_first_probe);',
            'if (local_first) { /* leaked registration */ }'),
        'owned-delegation-bit-as-owner': ('(owned ? ~15UL : ~7UL)', '~7UL'),
        'native-owner-bit-as-flag': ('(owned ? ~15UL : ~7UL)', '~15UL'),
        'omit-self-wait-count': ('c->owned_wait++;', '{ /* omitted SELF continuation */ }'),
    }
    variants = [('production', source)]
    for name, (old, new) in mutations.items():
        assert old in source, name
        variants.append((name, source.replace(old, new)))
    with tempfile.TemporaryDirectory(prefix='kd-owned-profile-') as directory:
        path=Path(directory)
        (path/'fixture.c').write_text(FIXTURE)
        for name, body in variants:
            (path/'profile_production.h').write_text(body)
            binary=path/name
            subprocess.run(shlex.split(os.environ.get('CC','cc')) + [
                '-std=gnu11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-parameter',
                '-I'+directory,str(path/'fixture.c'),'-o',str(binary),
            ],check=True,timeout=30)
            result=subprocess.run([binary],capture_output=True,text=True,timeout=10)
            if name=='production':
                assert result.returncode==0,result.stdout+result.stderr
                print(result.stdout,end='')
            else:
                assert result.returncode!=0,f'mutation survived: {name}'
                print(f'[PASS] diagnostic preflight fixture rejects {name}')


if __name__=='__main__':
    main()
