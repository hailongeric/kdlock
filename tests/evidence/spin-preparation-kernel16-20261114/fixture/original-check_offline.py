"""Source and C syntax checks only; mock Linux/runtime declarations, real spin macros."""
from pathlib import Path
import hashlib,json,re,subprocess
root=Path(__file__).resolve().parent
base=Path('/tmp/kdlock-spin-nano-source-7338197a-20261114/base')
source=root/'tests/kernel/spin_simple/payload/kd_spin_simple.c'
stubs=root/'offline-stubs';stubs.mkdir(exist_ok=True)
common=r'''
#ifndef FIXTURE_STUB_H
#define FIXTURE_STUB_H
#include <stddef.h>
#include <stdbool.h>
#include <errno.h>
#define KDLOCK_MUTEX_H
struct kd_mutex { void *tail; void *owner; };
#define KD_MUTEX_INITIALIZER {0}
#define notrace
#define __init
#define __exit
#define HZ 100
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define smp_load_acquire(x) (*(x))
#define BUILD_BUG_ON(x) _Static_assert(!(x), #x)
#define IS_ENABLED(x) (x)
#define CONFIG_KDLOCK_REBUILD 1
#define CONFIG_PREEMPT_COUNT 1
#define CONFIG_PREEMPT_RT 0
#define CONFIG_DEBUG_SPINLOCK 0
#define CONFIG_DEBUG_MUTEXES 0
#define CONFIG_DEBUG_LOCK_ALLOC 0
#define CONFIG_LOCKDEP 0
#define module_param(a,b,c)
#define module_init(a)
#define module_exit(a)
#define MODULE_LICENSE(a)
#define MODULE_DESCRIPTION(a)
#define MOD_TEXT 0
struct module { struct {void *base; size_t size;} mem[1]; };
extern struct module mock_module;
#define THIS_MODULE (&mock_module)
struct task_struct;
struct completion { int unused; };
typedef struct {int counter;} atomic_t;
#define ATOMIC_INIT(x) {x}
extern int atomic_inc_return(atomic_t *);
extern int atomic_dec_return(atomic_t *);
extern int atomic_read(const atomic_t *);
extern void atomic_inc(atomic_t *);
extern void preempt_disable(void),preempt_enable(void),cond_resched(void);
extern void msleep(unsigned int);
extern void complete(struct completion *),complete_all(struct completion *);
extern void init_completion(struct completion *),wait_for_completion(struct completion *);
extern unsigned long wait_for_completion_timeout(struct completion *,unsigned long);
extern struct task_struct *kthread_create(int (*)(void *),void *,const char *,...);
extern void kthread_bind(struct task_struct *,unsigned int);
extern int kthread_stop(struct task_struct *),wake_up_process(struct task_struct *);
extern bool kthread_should_stop(void),cpu_online(unsigned int);
extern long schedule_timeout_interruptible(long);
extern void cpus_read_lock(void),cpus_read_unlock(void);
extern unsigned int nr_cpu_ids;
#define IS_ERR(p) ((unsigned long)(p) > (unsigned long)-4096)
#define PTR_ERR(p) ((long)(p))
extern int mock_log(const char *,...) __attribute__((format(printf,1,2)));
#define pr_info mock_log
#define pr_err mock_log
#define MSR_GS_BASE 0
#define rdmsrl(index,value) ((value)=0)
#define ASM_CALL_CONSTRAINT "=m"(*(char *)0)
struct kd_task_storage;
struct kd_execution_binding;
struct kd_task_root_context {struct {struct kd_execution_binding *binding;} core;};
struct kd_jit_source_provider;
struct kd_jit_runtime;
struct kd_jit_source_load_region {unsigned long start;size_t length;};
#define KD_JIT_SOURCE_IMMUTABLE_DEPENDENCIES 1
#define KD_LOCK_FAMILY_SPIN 1
struct kd_jit_source_provider_args {
 unsigned int contract;const unsigned char *version;size_t version_length;
 const struct kd_jit_source_load_region *regions;unsigned int region_count;
 const void *configuration_identity,*load_identity;unsigned long current_task_gs_offset;
 struct module *const *modules;unsigned int module_count;
};
struct mock_symbol {const char *data; size_t length;};
struct kd_jit_runtime_config {
 struct kd_jit_source_provider *source;unsigned int feedback_capacity,cycle_capacity,image_capacity,claim_capacity;
 struct {size_t code_capacity,artifact_capacity,flat_capacity,entry_capacity,source_capacity,observation_capacity;} compiled;
 struct {struct mock_symbol descriptor,source,producer,entry;} symbols;
 const char *channel_name;struct module *owner;size_t frame_capacity;unsigned int request_capacity;
 size_t auxiliary_bytes;unsigned long required_control_bytes;unsigned int proxy_limit;bool atomic_spin;int family;
};
extern int kd_jit_source_provider_create(const struct kd_jit_source_provider_args *,struct kd_jit_source_provider **);
extern int kd_jit_source_provider_close(struct kd_jit_source_provider *),kd_jit_source_provider_destroy(struct kd_jit_source_provider *);
extern int kd_jit_runtime_create(const struct kd_jit_runtime_config *,struct kd_jit_runtime **);
extern int kd_jit_runtime_enter_current(struct kd_jit_runtime *,unsigned long,struct kd_task_storage **);
extern int kd_jit_runtime_leave_current(struct kd_task_storage *,struct kd_execution_binding *,bool *);
extern int kd_jit_runtime_destroy(struct kd_jit_runtime *);
extern struct kd_task_root_context *kd_task_storage_root(struct kd_task_storage *);
#endif
'''
(stubs/'common.h').write_text(common)
for name in ['linux/module.h','linux/kthread.h','linux/completion.h','linux/cpu.h','linux/delay.h','linux/err.h','linux/build_bug.h','linux/preempt.h','linux/sched.h','linux/jiffies.h','linux/compiler.h','asm/msr.h','asm/msr-index.h','asm/asm.h','kernel/runtime.h','kernel/task_state.h']:
 p=stubs/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('#include "common.h"\n')
cmd=['gcc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-include',str(stubs/'common.h'),'-I'+str(stubs),'-I'+str(base)]
checks=[]
def run(label,args):
 p=subprocess.run(args,capture_output=True,text=True)
 (root/(label+'.log')).write_text(p.stdout+p.stderr)
 if p.returncode:raise RuntimeError(label+': '+p.stderr)
 checks.append(label)
 return p.stdout
run('mocked-syntax',cmd+['-fsyntax-only',str(source)])
expanded=run('real-spin-macro-routing',cmd+['-E',str(source)])
assert '"kd_spin_lock_entry_asm"' in expanded and '"kd_spin_unlock_entry_asm"' in expanded
assert 'call kd_spin' not in source.read_text() # Calls must remain source API macros.
exports=(base/'kernel/exports.c').read_text()
required=['kd_spin_init','kd_spin_lock_entry_asm','kd_spin_unlock_entry_asm','kd_jit_source_provider_create','kd_jit_source_provider_close','kd_jit_source_provider_destroy','kd_jit_runtime_create','kd_jit_runtime_enter_current','kd_jit_runtime_leave_current','kd_jit_runtime_destroy','kd_task_storage_root']
assert all('EXPORT_SYMBOL_GPL('+name+');' in exports for name in required)
assert 'policy_epoch' not in (base/'include/kd_spin_api.h').read_text()
checks.append('pinned-export-and-layout-source-check')
# Exact input identity, not a mock ABI validation.
expected=json.loads(Path('/home/eric/vm/vm-shared/kdlock-evidence/rwsem-writer-waits-kernel16-20261113-01/decoded/evidence-inputs/expected-kernel.json').read_text())
verified={}
for name,digest in expected['source_after']['package88'].items():
 path=base/name
 assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,name
 verified[name]=digest
checks.append('88-pinned-source-files-match-kernel16-receipt')
result={'status':'OFFLINE_CHECKS_PASSED','checks':checks,'scope':'Mocked Linux/runtime declarations plus actual pinned spin macro preprocessing; no kernel compile/link/runtime','expected_exported_imports':required,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'pinned_inputs':verified}
(root/'checks.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='pinned_inputs'},indent=2))
