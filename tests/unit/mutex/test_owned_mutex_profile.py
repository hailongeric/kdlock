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
#define DEFINE_PER_CPU(type,name) type name
#define this_cpu_ptr(p) (p)
#define per_cpu(value,cpu) (value)
#define for_each_possible_cpu(cpu) for ((cpu)=0;(cpu)<1;(cpu)++)
#define READ_ONCE(x) (*(volatile __typeof__(x) *)&(x))
#define atomic_long_read(p) READ_ONCE(*(p))
#define ns_to_ktime(n) (n)
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define min_t(type,a,b) ((type)(a)<(type)(b)?(type)(a):(type)(b))
#define regs_return_value(p) ((p)->ax)
static unsigned long __per_cpu_offset[1];
static unsigned int raw_smp_processor_id(void) { return 0; }
static unsigned int fls64(u64 n) { return 64-__builtin_clzll(n); }
static unsigned int registrations, fail_registration, depth;
static const void *registered[16];
static bool timer_active;
static char output[16384];
static size_t output_used;
#define pr_info(...) do { \
 int length=snprintf(output+output_used,sizeof(output)-output_used,__VA_ARGS__); \
 assert(length>0 && (size_t)length<sizeof(output)-output_used); output_used+=length; \
} while (0)
static int register_one(const void *address)
{
 assert(depth<ARRAY_SIZE(registered));
 if (++registrations==fail_registration) return -EINVAL;
 registered[depth++]=address; return 0;
}
static void unregister_one(const void *address)
{
 assert(depth && registered[depth-1]==address); depth--;
}
static int register_kprobe(struct kprobe *p) { return register_one(p); }
static void unregister_kprobe(struct kprobe *p) { unregister_one(p); }
static int register_kprobes(struct kprobe **p, unsigned int n)
{
 assert(n==3); return register_one(p);
}
static void unregister_kprobes(struct kprobe **p, unsigned int n)
{
 assert(n==3); unregister_one(p);
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
 assert(!depth && !timer_active);
 registrations=0;fail_registration=failure;output_used=0;output[0]=0;
 target_lock=0x1000;success_counter=0x2000;kd=owned=preflight=true;spin=false;
 memset(&counts,0,sizeof(counts));
 preflight_probe.nmissed=preflight_probe.kp.nmissed=0;
 optimistic_probe.nmissed=optimistic_probe.kp.nmissed=0;
}
int main(void)
{
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
 regs.di=target_lock;assert(admission_entry(&instance,&regs)==0);
 regs.ax=0x100;preflight_return(&instance,&regs); /* AL zero, upper bits nonzero. */
 regs.ax=0x1234567800000001UL;preflight_return(&instance,&regs);
 assert(counts.gate_self==1 && counts.gate_capture==1);
 for(unsigned int value=0;value<=3;value++) {
  regs.ax=0x1234567800000000UL|value;optimistic_return(&instance,&regs);
 }
 assert(counts.optimistic_acquired==1 && counts.optimistic_busy==1 &&
        counts.optimistic_self==1 && counts.optimistic_other==1);
 preflight_probe.nmissed=3;preflight_probe.kp.nmissed=2;
 profile_exit();assert(!depth && !timer_active);
 assert(strstr(output,"kd_mutex_profile ownedpreflight: gate_self=1 gate_capture=1"));
 assert(strstr(output,"optimistic_other=1 missed=5"));
 reset(0);preflight=false;assert(profile_init()==0 && depth==5);
 profile_exit();assert(!depth && !timer_active);
 assert(!strstr(output,"ownedpreflight:"));
 puts("PASS diagnostic preflight probes: all registration unwinds, target filter, bool/enum ABI and missed returns");
 return 0;
}
'''


def main():
    source = without_includes((ROOT/'tests/kernel/mutex/profile/kd_mutex_profile.c').read_text())
    mutations = {
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
