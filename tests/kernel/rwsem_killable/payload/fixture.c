// SPDX-License-Identifier: GPL-2.0-only
/* Private rwsem mechanism bodies. RUN never performs an MM operation. */
#include <linux/capability.h>
#include <linux/completion.h>
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/rwsem.h>
#include <linux/limits.h>
#include <linux/mm.h>
#include <linux/mutex.h>
#include <linux/overflow.h>
#include <linux/sched.h>
#include <linux/sched/task.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include <asm/msr.h>
#include <asm/msr-index.h>
#include "include/kd_rwsem_api.h"
#include "include/kd_linux_rwsem.h"
#include "kernel/runtime.h"
#include "kernel/rw_admission.h"
#include "kernel/rw_native.h"
#include "kernel/observation.h"
#include "kernel/task_state.h"
#include "kernel/request_pool.h"

#define NAME "kd_rwsem_killable_fixture"
#define ROLES 5U
#define RUN 0x5301U
#define GO 0x5302U
#define RELEASE 0x5303U
#define RESET 0x5304U
#define RETIRE 0x5305U
#define EXIT_ACK 0x5306U
/* Actions 0/1 are managed source calls. Holders use callable Linux APIs. */
enum action { SOURCE_KILLABLE, SOURCE_WRITER, NATIVE_WRITER, NATIVE_READER, NATIVE_KILLABLE };
static unsigned long gs_offset, builtin_source_start, builtin_source_size;
static unsigned long total_source_byte_limit, auxiliary_bytes, control_bytes;
static unsigned long frame_capacity, event_capacity;
static unsigned int killable_size, writer_size, step_size, dependency_page_limit;
static unsigned int native_capacity, request_capacity, proxy_limit;
static unsigned int feedback_capacity, cycle_capacity, image_capacity, claim_capacity;
static unsigned int code_capacity, artifact_capacity, flat_capacity, entry_capacity;
static unsigned int source_capacity, observation_capacity;
static bool gs_verified, immutable_text, auxiliary_contract;
static char *source_version;
#define PARAM(name, type) module_param(name, type, 0444)
PARAM(gs_offset, ulong); PARAM(gs_verified, bool); PARAM(immutable_text, bool);
PARAM(auxiliary_contract, bool); PARAM(source_version, charp);
PARAM(killable_size, uint); PARAM(writer_size, uint); PARAM(step_size, uint);
PARAM(dependency_page_limit, uint); PARAM(total_source_byte_limit, ulong);
PARAM(builtin_source_start, ulong); PARAM(builtin_source_size, ulong);
PARAM(native_capacity, uint); PARAM(request_capacity, uint);
PARAM(auxiliary_bytes, ulong); PARAM(control_bytes, ulong); PARAM(proxy_limit, uint);
PARAM(feedback_capacity, uint); PARAM(cycle_capacity, uint);
PARAM(image_capacity, uint); PARAM(claim_capacity, uint); PARAM(frame_capacity, ulong);
PARAM(code_capacity, uint); PARAM(artifact_capacity, uint); PARAM(flat_capacity, uint);
PARAM(entry_capacity, uint); PARAM(source_capacity, uint); PARAM(observation_capacity, uint);
PARAM(event_capacity, ulong);

struct role {
 struct task_struct *task;
 struct kd_task_storage *storage;
 struct completion go, release, exit_release;
 unsigned int pid, action;
 bool gated, ready, active, done;
 int result, error;
 unsigned long effects, steps, helper_entered, helper_returned, helper_return_ip, seen_task;
 unsigned long state, regs;
};
static struct role roles[ROLES];
static DEFINE_MUTEX(control_mutex);
static struct rw_semaphore linux_sem;
static struct kd_rwsem gate;
static struct kd_linux_rwsem_binding binding;
static struct kd_rw_native_pool native_pool;
static struct kd_rw_native_record *native_records;
static struct kd_jit_source_provider *provider;
static struct kd_jit_runtime *runtime;
static const char configuration_identity, load_identity;
static bool retired, setup_complete, binding_live, trace_live, self_held;
static bool control_live, event_live;
static int setup_error, cleanup_error;
static struct kd_observation *events;
static unsigned long event_count, event_overflow;
static DEFINE_RAW_SPINLOCK(event_guard);

/* This normal callee is admitted as ordinary bytes, including actual RET. */
static noinline notrace void fixture_source_step(struct role *role)
{
 WRITE_ONCE(role->steps, READ_ONCE(role->steps) + 1);
}
/* This controller gate is deliberately OUTSIDE every admitted source region.
 * An ordinary source CALL reaches the normal pre-effect handback route. No
 * generated helper implementation or instruction-specific model exists.
 */
static noinline notrace void fixture_native_completion(struct role *role)
{
 if (current != role->task)
  WRITE_ONCE(role->error, -EUCLEAN);
 WRITE_ONCE(role->helper_return_ip, _RET_IP_);
 WRITE_ONCE(role->helper_entered, 1);
 wait_for_completion(&role->release);
 WRITE_ONCE(role->helper_returned, 1);
}
static void (*step_entry)(struct role *) = fixture_source_step;
static void (*completion_entry)(struct role *) = fixture_native_completion;

static noinline notrace int fixture_killable_body(struct role *role)
{
 int result = kd_rwsem_down_write_killable(&gate);

 WRITE_ONCE(role->result, result);
 if (!result) {
  WRITE_ONCE(role->seen_task, (unsigned long)current);
  WRITE_ONCE(role->effects, READ_ONCE(role->effects) + 1);
  READ_ONCE(step_entry)(role);
  if (role->gated)
   READ_ONCE(completion_entry)(role);
  kd_rwsem_up_write(&gate);
 }
 return result;
}
static noinline notrace void fixture_writer_body(struct role *role)
{
 kd_rwsem_down_write(&gate);
 WRITE_ONCE(role->result, 0);
 WRITE_ONCE(role->seen_task, (unsigned long)current);
 WRITE_ONCE(role->effects, READ_ONCE(role->effects) + 1);
 READ_ONCE(step_entry)(role);
 if (role->gated)
  READ_ONCE(completion_entry)(role);
 kd_rwsem_up_write(&gate);
}

static int (*killable_entry)(struct role *) = fixture_killable_body;
static void (*writer_entry)(struct role *) = fixture_writer_body;

static void observe(void *unused, const struct kd_observation *row)
{
 unsigned long flags;

 (void)unused;
 raw_spin_lock_irqsave(&event_guard, flags);
 if (event_count < event_capacity)
  events[event_count++] = *row;
 else
  event_overflow = 1;
 raw_spin_unlock_irqrestore(&event_guard, flags);
}

static ssize_t events_read(struct file *file, char __user *output,
                          size_t length, loff_t *position)
{
 u64 header[5];
 struct kd_observation row;
 unsigned long flags, index;
 size_t offset, bytes;

 (void)file;
 if (*position < 0)
  return -EINVAL;
 raw_spin_lock_irqsave(&event_guard, flags);
 header[0] = 1; header[1] = 20; header[2] = event_capacity;
 header[3] = event_count; header[4] = event_overflow;
 if (*position < sizeof(header)) {
  raw_spin_unlock_irqrestore(&event_guard, flags);
  bytes = min(length, sizeof(header) - (size_t)*position);
  if (copy_to_user(output, (char *)header + *position, bytes)) return -EFAULT;
  *position += bytes;
  return bytes;
 }
 index = (*position - sizeof(header)) / sizeof(row);
 offset = (*position - sizeof(header)) % sizeof(row);
 if (index >= event_count) {
  raw_spin_unlock_irqrestore(&event_guard, flags);
  return 0;
 }
 row = events[index];
 raw_spin_unlock_irqrestore(&event_guard, flags);
 bytes = min(length, sizeof(row) - offset);
 if (copy_to_user(output, (char *)&row + offset, bytes)) return -EFAULT;
 *position += bytes;
 return bytes;
}
static const struct file_operations event_ops = {
 .owner = THIS_MODULE, .read = events_read, .llseek = default_llseek,
};
static struct miscdevice event_device = {
 .minor = MISC_DYNAMIC_MINOR, .name = NAME "_events", .fops = &event_ops, .mode = 0400,
};

static unsigned int native_scopes(void)
{
 struct kd_jit_source_use *use;
 unsigned int count = 0;

 if (!provider) return 0;
 raw_spin_lock(&provider->epoch.guard);
 list_for_each_entry(use, &provider->epoch.users, epoch_link)
  if (use->kind == KD_JIT_SOURCE_USE_NATIVE) count++;
 raw_spin_unlock(&provider->epoch.guard);
 return count;
}
static bool gate_clear(void)
{
 bool clear;
 raw_spin_lock(&gate.core.guard);
 clear = !atomic_long_read(&gate.core.admission) && !gate.core.readers && !gate.core.writer_pending && !gate.core.writer &&
         !READ_ONCE(gate.core.queue.tail) && !READ_ONCE(gate.core.queue.owner);
 raw_spin_unlock(&gate.core.guard);
 return clear;
}
/* The enclosing RUN owns storage until it clears role.storage under the same
 * mutex before returning to userspace. It makes no second acquisition or exit
 * during this observer. Only node/control metadata is read, never source regs.
 * A root call's control/auxiliary or current-native endpoint pins its slot.
 */
static void role_metadata(struct role *role, unsigned long *node_id,
 unsigned long *acquisition, int *selection, int *admission,
 unsigned long *waiter, unsigned int *turn)
{
 struct kd_task_root_context *root;
 struct kd_request_pool *pool;
 struct kd_request_slot *slot;
 unsigned int index;
 unsigned long flags;

 if (!role->storage) return;
 root = kd_task_storage_root(role->storage);
 pool = root->core.requests;
 for (index = 0; index < pool->capacity; index++) {
  slot = &pool->slots[index];
  raw_spin_lock_irqsave(&pool->guard, flags);
  if (slot->phase != KD_REQUEST_SLOT_LIVE || !slot->call.node.enqueued) {
   raw_spin_unlock_irqrestore(&pool->guard, flags);
   continue;
  }
  raw_spin_unlock_irqrestore(&pool->guard, flags);
  raw_spin_lock(&gate.core.guard);
  *node_id = (unsigned long)&slot->call.node;
  *acquisition = (unsigned long)slot->call.node.acquisition;
  *selection = atomic_read(&slot->call.node.selection);
  *admission = slot->call.node.admission;
  *waiter = (unsigned long)slot->call.node.cancel_waiter;
  *turn = READ_ONCE(slot->call.node.turn);
  raw_spin_unlock(&gate.core.guard);
  return;
 }
}
static ssize_t status_read(struct file *file, char __user *output,
                           size_t length, loff_t *position)
{
 char *buffer;
 unsigned long flags, count, overflow, writer, tail, owner, readers;
 unsigned int index;
 bool pending;
 int used = 0;

 (void)file;
 buffer = kmalloc(8192, GFP_KERNEL);
 if (!buffer) return -ENOMEM;
 mutex_lock(&control_mutex);
 raw_spin_lock_irqsave(&event_guard, flags);
 count = event_count; overflow = event_overflow;
 raw_spin_unlock_irqrestore(&event_guard, flags);
 raw_spin_lock(&gate.core.guard);
 readers = kd_rw_admission_readers(&gate.core); pending = gate.core.writer_pending;
 writer = (unsigned long)gate.core.writer;
 tail = (unsigned long)READ_ONCE(gate.core.queue.tail);
 owner = (unsigned long)READ_ONCE(gate.core.queue.owner);
 raw_spin_unlock(&gate.core.guard);
 used += scnprintf(buffer + used, 8192 - used,
  "{\"setup_complete\":%u,\"setup_error\":%d,\"cleanup_error\":%d,\"binding_live\":%u,"
  "\"trace_live\":%u,\"runtime_live\":%u,\"source_live\":%u,\"self_held\":%u,"
  "\"retired\":%u,\"events\":%lu,\"overflow\":%lu,\"readers\":%lu,"
  "\"writer_pending\":%u,\"writer\":%lu,\"tail\":%lu,\"owner\":%lu,"
  "\"object\":%lu,\"native_helper\":%lu,\"pool_idle\":%u,\"native_scopes\":%u,\"roles\":[",
  setup_complete, setup_error, cleanup_error, binding_live, trace_live, runtime != NULL,
  provider != NULL, self_held, retired, count, overflow, readers, pending, writer, tail, owner,
  (unsigned long)&gate.core.queue, (unsigned long)fixture_native_completion, kd_rw_native_pool_idle(&native_pool), native_scopes());
 for (index = 0; index < ROLES; index++) {
  struct role *role = &roles[index];
  unsigned long node = 0, acquisition = 0, waiter = 0;
  unsigned int turn = 0;
  int selection = -1, admission = -1;

  role_metadata(role, &node, &acquisition, &selection, &admission, &waiter, &turn);
  used += scnprintf(buffer + used, 8192 - used,
   "%s{\"pid\":%u,\"task\":%lu,\"ready\":%u,\"active\":%u,\"done\":%u,"
   "\"exit_state\":%d,\"result\":%d,\"error\":%d,\"effects\":%lu,\"steps\":%lu,"
   "\"helper_entered\":%lu,\"helper_returned\":%lu,\"helper_return_ip\":%lu,\"seen_task\":%lu,"
   "\"state\":%lu,\"regs\":%lu,\"node\":%lu,\"acquisition\":%lu,"
   "\"selection\":%d,\"admission\":%d,\"cancel_waiter\":%lu,\"turn\":%u}",
   index ? "," : "", role->pid, (unsigned long)role->task, role->ready,
   role->active, role->done, role->task ? READ_ONCE(role->task->exit_state) : 0,
   READ_ONCE(role->result), READ_ONCE(role->error), READ_ONCE(role->effects),
   READ_ONCE(role->steps), READ_ONCE(role->helper_entered), READ_ONCE(role->helper_returned),
   READ_ONCE(role->helper_return_ip), READ_ONCE(role->seen_task), role->state, role->regs, node, acquisition,
   selection, admission, waiter, turn);
 }
 used += scnprintf(buffer + used, 8192 - used, "]}\n");
 mutex_unlock(&control_mutex);
 used = simple_read_from_buffer(output, length, position, buffer, used);
 kfree(buffer);
 return used;
}

static int run_role(unsigned int index, unsigned int action, bool gated)
{
 struct role *role;
 struct kd_task_storage *storage = NULL;
 unsigned long origin_gs;
 bool managed = action == SOURCE_KILLABLE || action == SOURCE_WRITER;
 int result = 0;

 mutex_lock(&control_mutex);
 if (!setup_complete || setup_error || retired || !runtime || index >= ROLES || action > NATIVE_KILLABLE || roles[index].task ||
     current->kd_root_context) { mutex_unlock(&control_mutex); return -EBUSY; }
 role = &roles[index];
 role->task = current; get_task_struct(current);
 role->pid = task_pid_nr(current); role->action = action; role->gated = gated;
 role->active = true; role->result = -EINPROGRESS;
 mutex_unlock(&control_mutex);
 if (managed) {
  preempt_disable(); rdmsrl(MSR_GS_BASE, origin_gs); preempt_enable();
  result = kd_jit_runtime_enter_current(runtime, origin_gs, &storage);
  mutex_lock(&control_mutex);
  role->storage = storage;
  if (storage) {
   struct kd_task_root_context *root = kd_task_storage_root(storage);
   role->state = (unsigned long)&root->core;
   role->regs = (unsigned long)&root->core.regs;
  }
  mutex_unlock(&control_mutex);
 }
 if (result) {
  /* Retained construction failures must keep this original task alive. */
  WRITE_ONCE(role->error, result);
  if (storage) for (;;) schedule_timeout_uninterruptible(HZ);
  goto done;
 }
 smp_store_release(&role->ready, true);
 wait_for_completion(&role->go);
 switch (action) {
 case SOURCE_KILLABLE: result = READ_ONCE(killable_entry)(role); break;
 case SOURCE_WRITER: READ_ONCE(writer_entry)(role); break;
 case NATIVE_READER:
  (down_read)(&linux_sem); WRITE_ONCE(role->effects, 1);
  wait_for_completion(&role->release); (up_read)(&linux_sem); break;
 case NATIVE_WRITER:
  (down_write)(&linux_sem); WRITE_ONCE(role->effects, 1);
  wait_for_completion(&role->release); (up_write)(&linux_sem); break;
 case NATIVE_KILLABLE:
  result = (down_write_killable)(&linux_sem);
  if (!result) {
   WRITE_ONCE(role->effects, 1);
   wait_for_completion(&role->release); (up_write)(&linux_sem);
  }
  break;
 }
 WRITE_ONCE(role->result, result);
done:
 mutex_lock(&control_mutex);
 /* Parent may inspect the retained current endpoint after API completion.
  * This gate is outside all admitted text and cannot advance source work.
  */
 role->done = true;
 mutex_unlock(&control_mutex);
 wait_for_completion(&role->exit_release);
 mutex_lock(&control_mutex);
 /* End every raw storage observer before actual do_exit can detach it. No
  * explicit leave is used, so task exit exercises the lifecycle hook.
  */
 role->storage = NULL; role->active = false;
 mutex_unlock(&control_mutex);
 return result;
}
static int reset_roles(void)
{
 unsigned int index;
 if (!gate_clear() || !kd_rw_native_pool_idle(&native_pool) || native_scopes()) return -EBUSY;
 for (index = 0; index < ROLES; index++)
  if (roles[index].task && (!roles[index].done || !READ_ONCE(roles[index].task->exit_state))) return -EBUSY;
 for (index = 0; index < ROLES; index++) {
  if (roles[index].task) put_task_struct(roles[index].task);
  roles[index] = (struct role) {};
  init_completion(&roles[index].go); init_completion(&roles[index].release);
  init_completion(&roles[index].exit_release);
 }
 return 0;
}
/* Ordinary checked teardown. Any refusal leaves its exact remaining roles
 * queryable. The executing fd or module-init return independently retains code
 * while this routine drops the selection's final self hold.
 */
static int retire_state(void)
{
 int result = reset_roles();

 if (result) return result;
 if (runtime) {
  result = kd_jit_runtime_destroy(runtime);
  if (result) return result;
  runtime = NULL;
 }
 if (provider) {
  result = kd_jit_source_provider_close(provider);
  if (result && result != -EALREADY) return result;
  result = kd_jit_source_provider_destroy(provider);
  if (result) return result;
  provider = NULL;
 }
 if (binding_live) {
  result = kd_linux_rwsem_unbind(&binding);
  if (result) return result;
  binding_live = false;
 }
 /* Trace text changes only after every source lease has ended. */
 if (trace_live) {
  unregister_trace_kdlock_observe_tp(observe, NULL);
  tracepoint_synchronize_unregister();
  trace_live = false;
 }
 setup_complete = false;
 retired = true;
 if (self_held) { self_held = false; module_put(THIS_MODULE); }
 return 0;
}
static long control_ioctl(struct file *file, unsigned int command, unsigned long argument)
{
 u64 words[4];
 unsigned int index;
 int result;
 (void)file;
 if (!capable(CAP_SYS_ADMIN)) return -EPERM;
 if (command != RUN && command != GO && command != RELEASE && command != RESET && command != RETIRE && command != EXIT_ACK) return -EINVAL;
 if (copy_from_user(words, (void __user *)argument, sizeof(words))) return -EFAULT;
 if (words[0] >= ROLES || words[3]) return -EINVAL;
 if (command == RUN) {
  if (words[1] > NATIVE_KILLABLE || words[2] > 1) return -EINVAL;
  return run_role(words[0], words[1], words[2]);
 }
 if (words[1] || words[2]) return -EINVAL;
 mutex_lock(&control_mutex);
 index = words[0];
 if (command == GO || command == RELEASE || command == EXIT_ACK) {
  complete_all(command == GO ? &roles[index].go : command == RELEASE ?
               &roles[index].release : &roles[index].exit_release); result = 0;
 } else if (command == RESET) result = reset_roles();
 else {
  result = retire_state();
  cleanup_error = result;
 }
 mutex_unlock(&control_mutex);
 return result;
}
static const struct file_operations control_ops = {
 .owner = THIS_MODULE, .read = status_read, .unlocked_ioctl = control_ioctl,
 .llseek = default_llseek,
};
static struct miscdevice control_device = {
 .minor = MISC_DYNAMIC_MINOR, .name = NAME "_ctl", .fops = &control_ops, .mode = 0600,
};

static int make_regions(struct kd_jit_source_load_region **out, unsigned int *count)
{
 struct kd_jit_source_load_region *rows;
 unsigned int pages = 0, dependencies, index, prior;
 size_t bytes;
#ifdef CONFIG_MITIGATION_ITS
 if (THIS_MODULE->arch.its_pages.num < 0 ||
     (THIS_MODULE->arch.its_pages.num && !THIS_MODULE->arch.its_pages.pages)) return -EINVAL;
 pages = THIS_MODULE->arch.its_pages.num;
#endif
 if (!builtin_source_start || !builtin_source_size || builtin_source_size > PAGE_SIZE ||
     builtin_source_size - 1 > ~0UL - builtin_source_start ||
     (builtin_source_start >> PAGE_SHIFT) != ((builtin_source_start + builtin_source_size - 1) >> PAGE_SHIFT) ||
     check_add_overflow(pages, 1U, &dependencies) || dependencies > dependency_page_limit ||
     check_add_overflow((size_t)killable_size, (size_t)writer_size, &bytes) ||
     check_add_overflow(bytes, (size_t)step_size, &bytes) ||
     check_add_overflow(bytes, (size_t)pages * PAGE_SIZE, &bytes) ||
     check_add_overflow(bytes, (size_t)builtin_source_size, &bytes) || bytes > total_source_byte_limit) return -E2BIG;
 *count = 3 + dependencies;
 rows = kcalloc(*count, sizeof(*rows), GFP_KERNEL);
 if (!rows) return -ENOMEM;
 rows[0] = (struct kd_jit_source_load_region) { (unsigned long)fixture_killable_body, killable_size };
 rows[1] = (struct kd_jit_source_load_region) { (unsigned long)fixture_writer_body, writer_size };
 rows[2] = (struct kd_jit_source_load_region) { (unsigned long)fixture_source_step, step_size };
#ifdef CONFIG_MITIGATION_ITS
 for (index = 0; index < pages; index++) {
  unsigned long start = (unsigned long)THIS_MODULE->arch.its_pages.pages[index];
  if (!start || !PAGE_ALIGNED(start)) goto invalid;
  rows[index + 3] = (struct kd_jit_source_load_region) { start, PAGE_SIZE };
 }
#endif
 rows[pages + 3] = (struct kd_jit_source_load_region) { builtin_source_start, builtin_source_size };
 for (index = 0; index < *count; index++) {
  unsigned long start = rows[index].start, last;
  if (!rows[index].length || rows[index].length - 1 > ~0UL - start) goto invalid;
  last = start + rows[index].length - 1;
  if (index < 3 && (!within_module_mem_type(start, THIS_MODULE, MOD_TEXT) ||
                  !within_module_mem_type(last, THIS_MODULE, MOD_TEXT))) goto invalid;
  for (prior = 0; prior < index; prior++)
   if (start <= rows[prior].start + rows[prior].length - 1 && rows[prior].start <= last) goto invalid;
 }
 *out = rows; return 0;
invalid:
 kfree(rows); return -EINVAL;
}
#define SYMBOL_BYTES(text) { .data = (text), .length = sizeof(text) - 1 }
static int __init fixture_init(void)
{
 struct kd_jit_source_load_region *regions = NULL;
 struct module *modules[] = { THIS_MODULE, NULL };
 struct kd_jit_source_provider_args source;
 struct kd_jit_runtime_config config;
 unsigned int count, index;
 int result;
 if (!gs_verified || !immutable_text || !auxiliary_contract || !source_version ||
     !*source_version || strnlen(source_version, 257) > 256 || !killable_size ||
     !writer_size || !step_size || killable_size > 65536 || writer_size > 65536 || step_size > 65536 ||
     !native_capacity || !request_capacity || !auxiliary_bytes || !control_bytes || !proxy_limit ||
     !feedback_capacity || !cycle_capacity || !image_capacity || !claim_capacity || !frame_capacity ||
     !code_capacity || !artifact_capacity || !flat_capacity || !entry_capacity || !source_capacity ||
     !observation_capacity || !event_capacity || event_capacity > (SIZE_MAX - 40) / sizeof(*events) ||
     event_capacity > ((unsigned long)LLONG_MAX - 40) / sizeof(*events)) return -EINVAL;
 native_records = kvcalloc(native_capacity, sizeof(*native_records), GFP_KERNEL);
 events = kvcalloc(event_capacity, sizeof(*events), GFP_KERNEL);
 if (!native_records || !events) { result = -ENOMEM; goto free; }
 kd_rwsem_init(&gate); init_rwsem(&linux_sem);
 result = kd_rw_native_pool_init(&gate.core, &native_pool, native_records, native_capacity);
 if (result) goto free;
 for (index = 0; index < ROLES; index++) {
  init_completion(&roles[index].go); init_completion(&roles[index].release);
  init_completion(&roles[index].exit_release);
 }
 /* No user can observe a partially changing composition. RUN remains closed
  * until setup_complete is published under this mutex.
  */
 mutex_lock(&control_mutex);
 result = misc_register(&control_device);
 if (result) { mutex_unlock(&control_mutex); goto free; }
 control_live = true;
 result = misc_register(&event_device);
 if (result) {
  setup_error = result; retired = true;
  mutex_unlock(&control_mutex);
  return 0; /* No source/binding/actor exists, and control remains queryable. */
 }
 event_live = true;
 if (!try_module_get(THIS_MODULE)) { result = -ENODEV; goto clean_failure; }
 self_held = true;
 result = kd_linux_rwsem_bind(&linux_sem, &binding, &gate, false);
 if (result) goto clean_failure;
 binding_live = true;
 result = make_regions(&regions, &count);
 if (result) goto clean_failure;
 result = register_trace_kdlock_observe_tp(observe, NULL);
 if (result) goto clean_failure;
 trace_live = true;
 source = (struct kd_jit_source_provider_args) {
  .contract = KD_JIT_SOURCE_IMMUTABLE_DEPENDENCIES,
  .version = (const unsigned char *)source_version, .version_length = strlen(source_version),
  .regions = regions, .region_count = count, .configuration_identity = &configuration_identity,
  .load_identity = &load_identity, .current_task_gs_offset = gs_offset,
  .modules = modules, .module_count = ARRAY_SIZE(modules),
 };
 /* Source-provider errors publish NULL and unwind their private snapshot. */
 result = kd_jit_source_provider_create(&source, &provider);
 kfree(regions); regions = NULL;
 if (result) goto clean_failure;
 config = (struct kd_jit_runtime_config) {
  .source = provider, .feedback_capacity = feedback_capacity, .cycle_capacity = cycle_capacity,
  .image_capacity = image_capacity, .claim_capacity = claim_capacity,
  .compiled = { .code_capacity = code_capacity, .artifact_capacity = artifact_capacity,
   .flat_capacity = flat_capacity, .entry_capacity = entry_capacity,
   .source_capacity = source_capacity, .observation_capacity = observation_capacity },
  .symbols = { .descriptor = SYMBOL_BYTES("kd_fixture_image"), .source = SYMBOL_BYTES("kd_fixture_epoch"),
   .producer = SYMBOL_BYTES("kd_fixture_producer"), .entry = SYMBOL_BYTES("kd_fixture_entry") },
  .channel_name = NAME, .owner = THIS_MODULE, .family = KD_LOCK_FAMILY_RWSEM,
  .frame_capacity = frame_capacity, .request_capacity = request_capacity,
  .auxiliary_bytes = auxiliary_bytes, .required_control_bytes = control_bytes, .proxy_limit = proxy_limit,
 };
 result = kd_jit_runtime_create(&config, &runtime);
 if (result) {
  setup_error = result;
  if (runtime) {
   /* A retained constructor result owns live source/feedback controls.
    * Do not guess a destroy or free any backing from module_init.
    */
   mutex_unlock(&control_mutex);
   return 0;
  }
  goto clean_failure;
 }
 setup_complete = true;
 mutex_unlock(&control_mutex);
 return 0;
clean_failure:
 setup_error = result;
 kfree(regions);
 /* Only clean NULL constructor outcomes use the ordinary checked unwind.
  * A refusal retains all remaining roles and the self hold for RETIRE.
  */
 cleanup_error = retire_state();
 mutex_unlock(&control_mutex);
 return 0;
free:
 kvfree(events); kvfree(native_records); return result;
}
static void __exit fixture_exit(void)
{
 BUG_ON(!retired || runtime || provider || binding_live || trace_live || self_held);
 if (event_live) misc_deregister(&event_device);
 if (control_live) misc_deregister(&control_device);
 kvfree(events); kvfree(native_records);
}
module_init(fixture_init);
module_exit(fixture_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Private managed killable rwsem mechanism fixture");
