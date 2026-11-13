// SPDX-License-Identifier: GPL-2.0-only
/* Production transfer/release and writer preparation with controlled endpoints. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <sys/mman.h>
#include <unistd.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); abort(); } } while (0)
#define BUG_ON(x) CHECK(!(x))
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, v) ((x) = (v))
#define smp_load_acquire(p) (*(p))
#define container_of(p, t, m) ((t *)((char *)(p) - offsetof(t, m)))
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define TASK_UNINTERRUPTIBLE 2
#define KD_EXECUTION_NATIVE 0
#define KD_EXECUTION_JIT 1
#define KD_JIT_IMAGE_USE_SOURCE 1

struct list_head { struct list_head *next, *prev; };
static void INIT_LIST_HEAD(struct list_head *h) { h->next = h->prev = h; }
static bool list_empty(const struct list_head *h) { return h->next == h; }
static bool list_is_singular(const struct list_head *h) { return !list_empty(h) && h->next == h->prev; }
static void list_add_tail(struct list_head *e, struct list_head *h)
{ e->next = h; e->prev = h->prev; h->prev->next = e; h->prev = e; }
static void list_add(struct list_head *e, struct list_head *h) { list_add_tail(e, h->next); }
static void list_del_init(struct list_head *e)
{ e->prev->next = e->next; e->next->prev = e->prev; INIT_LIST_HEAD(e); }
static void list_replace_init(struct list_head *old, struct list_head *next)
{ next->next = old->next; next->prev = old->prev; next->next->prev = next; next->prev->next = next; INIT_LIST_HEAD(old); }
#define list_entry(p, t, m) container_of(p, t, m)
#define list_first_entry(h, t, m) list_entry((h)->next, t, m)
#define list_for_each_entry(p, h, m) \
 for (p = list_entry((h)->next, __typeof__(*p), m); &p->m != (h); p = list_entry(p->m.next, __typeof__(*p), m))
#define list_for_each_entry_reverse(p, h, m) \
 for (p = list_entry((h)->prev, __typeof__(*p), m); &p->m != (h); p = list_entry(p->m.prev, __typeof__(*p), m))

typedef long atomic_long_t;
typedef struct { unsigned int held; } raw_spinlock_t;
typedef struct { int unused; } wait_queue_head_t;
struct kd_thread_state;
struct kd_execution_binding;
struct kd_mutex_release;
struct kd_rw_read_credit;
struct kd_mutex_node { bool ready, enqueued; const void *acquisition; int queue_done, retirable; };
struct kd_mutex_batch { unsigned long unused[64]; };
struct kd_mutex { struct kd_mutex_node *tail; struct kd_mutex_batch *owner; };
#include "types.h"
struct kd_task_root_context;
struct task_struct { struct kd_task_root_context *kd_root_context; };
struct kd_execution_binding { int kind; struct kd_thread_state *state; struct task_struct *task; };
struct kd_thread_state {
 struct task_struct *origin;
 struct kd_execution_binding *binding;
 struct list_head grants;
 unsigned long continuation[4];
};
struct kd_mutex_release_owner { raw_spinlock_t guard; };
struct kd_mutex_release {
 struct kd_mutex_release_owner *owner;
 struct kd_thread_state *state;
 const void *acquisition, *source_user;
 enum kd_mutex_unlock_phase phase;
 enum kd_mutex_unlock_route route;
};
struct kd_episode_resources {
 struct list_head ordinary_free;
 struct { unsigned int proxy_limit; void *image_slot; } config;
};
struct kd_task_root_context {
 struct task_struct *task;
 bool attached;
 void *aux_entry;
 unsigned long mutex_control_bytes;
 struct kd_thread_state core;
 struct list_head native_grants, rwsem_reads;
 struct kd_episode_resources *mutex_resources;
};
struct kd_mutex_entry { unsigned long marker; };
struct kd_jit_image { unsigned long marker; };
struct kd_jit_image_use { const struct kd_jit_image *image; };
struct test_slot { struct { struct kd_mutex_node node; } call; struct kd_mutex_entry entry; struct kd_jit_image_use source_use; };
struct kd_episode_frame { bool source_image; struct test_slot *slot; unsigned long source_target; };
static struct task_struct original, foreign, *current;
static struct kd_task_root_context root;
static struct kd_execution_binding native, proxy;
static struct kd_episode_resources resources;
static struct kd_rw_local locals[4];
static struct kd_rwsem *outer, inner;
static struct kd_jit_image image;
static struct test_slot slot;
static struct kd_episode_frame frame;
static struct kd_observation events[64];
static unsigned int event_count, physical_puts, slow_reads, image_lookups, image_puts, local_writes, cancels;
static int prepare_error, entry_error, lookup_error;
static bool source_admitted, force_slow, protect_final;
static size_t page_bytes;
static unsigned int guards;

static void raw_spin_lock_init(raw_spinlock_t *g) { g->held = 0; }
static void raw_spin_lock(raw_spinlock_t *g) { CHECK(!g->held); g->held = 1; ++guards; }
static void raw_spin_unlock(raw_spinlock_t *g) { CHECK(g->held && guards); g->held = 0; --guards; }
static bool in_task(void) { return current != NULL; }
static bool in_atomic(void) { return false; }
static bool irqs_disabled(void) { return false; }
static void wake_up_all(wait_queue_head_t *q) { (void)q; }
static struct kd_task_root_context *kd_task_root_context_current(void) { return current->kd_root_context; }
static struct kd_thread_state *kd_task_state_own(void) { return &current->kd_root_context->core; }
static struct kd_task_root_context *kd_rw_local_root(void) { return &root; }
static bool kd_state_is_current(struct kd_thread_state *s, struct kd_execution_binding *b)
{ return s && b && s->binding == b && b->state == s && b->task == current; }
static struct kd_execution_binding *kd_state_current_binding(struct kd_thread_state *s) { return s->binding; }
static bool kd_operation_is_read(enum kd_operation_kind op) { return op == KD_OPERATION_RWSEM_UP_READ; }
static bool kd_operation_is_unlock(enum kd_operation_kind op)
{ return op == KD_OPERATION_RWSEM_UP_READ || op == KD_OPERATION_RWSEM_UP_WRITE; }
static bool kd_operation_is_mode_change(enum kd_operation_kind op) { return op == KD_OPERATION_RWSEM_DOWNGRADE_WRITE; }
static enum kd_lock_family kd_operation_family(enum kd_operation_kind op) { (void)op; return KD_LOCK_FAMILY_RWSEM; }
static long atomic_long_read(atomic_long_t *p) { return *p; }
static long atomic_cmp(atomic_long_t *p, long old, long next) { long seen = *p; if (seen == old) *p = next; return seen; }
#define atomic_long_cmpxchg_acquire(p, o, n) atomic_cmp(p, o, n)
#define kd_observe(k, ...) do { CHECK(event_count < 64); events[event_count++] = (struct kd_observation) { .kind = (k), .task = (unsigned long)current, __VA_ARGS__ }; } while (0)

static void kd_rw_admission_read_put(struct kd_rw *lock)
{
 CHECK(!guards && (lock->admission & KD_RW_ADMIT_READ_MASK) == KD_RW_ADMIT_READ);
 lock->admission -= KD_RW_ADMIT_READ;
 ++physical_puts;
 if (protect_final) CHECK(!mprotect(outer, page_bytes, PROT_NONE));
}
static int kd_rw_admission_read(struct kd_rw *lock, unsigned int state, void *ops, void *context)
{
 CHECK(force_slow && state == TASK_UNINTERRUPTIBLE && !ops && !context);
 ++slow_reads;
 lock->admission = KD_RW_ADMIT_READ;
 return 0;
}
static int kd_rw_native_write_reserved(struct kd_rw *lock, struct kd_rw_native_record *record)
{
 CHECK(lock == &inner.core && record->ordinary_write && record->ordinary_queued);
 CHECK(list_empty(&root.core.grants));
 ++local_writes;
 return 0;
}
#include "rw_functions.h"
#include "state_functions.h"
#include "rw_admission_functions.h"
#include "rw_local_functions.h"

static void kd_jit_image_use_init(struct kd_jit_image_use *use) { use->image = NULL; }
static int kd_jit_image_lookup(void *slot_pointer, struct kd_jit_image_use *use,
 struct kd_thread_state *state, void *holder, int kind)
{
 CHECK(slot_pointer == &image && state == &root.core && holder == use && kind == KD_JIT_IMAGE_USE_SOURCE);
 ++image_lookups;
 if (!lookup_error) use->image = &image;
 return lookup_error;
}
static int kd_jit_image_use_put(struct kd_jit_image_use *use, void *holder)
{ CHECK(use == holder && use->image == &image); ++image_puts; return 0; }
static int kd_episode_prepare_root_admitted(struct kd_episode_resources *r,
 struct kd_execution_binding *binding, enum kd_operation_kind op,
 struct kd_jit_image_use *admitted, struct kd_episode_frame **out)
{
 CHECK(r == &resources && binding == &native && op == KD_OPERATION_RWSEM_DOWN_WRITE);
 CHECK(admitted->image == &image && list_empty(&root.native_grants) && list_is_singular(&root.core.grants));
 if (prepare_error) return prepare_error;
 frame.source_image = source_admitted;
 frame.slot = &slot;
 slot.call.node.ready = source_admitted;
 slot.call.node.acquisition = &slot;
 slot.source_use.image = source_admitted ? &image : NULL;
 *out = &frame;
 return 0;
}
static int kd_episode_cancel_root(struct kd_episode_frame *f, struct kd_execution_binding *binding)
{ CHECK(f == &frame && binding == &native && !root.aux_entry); ++cancels; return 0; }
static void run_native(void) { CHECK(false); }
static int kd_mutex_prepare_entry(struct kd_mutex_entry *entry, struct kd_execution_binding *binding,
 void (*run)(void), void *context, unsigned long bytes)
{
 CHECK(entry == &slot.entry && binding == &native && run == run_native && context == &frame && bytes == 32768);
 if (entry_error) return entry_error;
 root.aux_entry = entry;
 return 0;
}
static struct kd_mutex_entry *prepare_current(struct kd_mutex *lock, enum kd_operation_kind op, unsigned long api)
{ (void)lock; (void)op; (void)api; CHECK(false); return NULL; }
static struct kd_mutex_entry *prepare_current_with_image(struct kd_mutex *lock,
 enum kd_operation_kind op, unsigned long api, struct kd_jit_image_use *admitted)
{ (void)lock; (void)op; (void)api; (void)admitted; CHECK(false); return NULL; }
#include "mutex_api_functions.h"

static void setup(bool slow)
{
 page_bytes = (size_t)sysconf(_SC_PAGESIZE);
 outer = mmap(NULL, page_bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
 CHECK(outer != MAP_FAILED && sizeof(*outer) < page_bytes);
 memset(&root, 0, sizeof(root)); memset(&inner, 0, sizeof(inner)); memset(&slot, 0, sizeof(slot));
 memset(&resources, 0, sizeof(resources)); memset(locals, 0, sizeof(locals));
 current = &original; original.kd_root_context = &root; foreign.kd_root_context = NULL;
 root.task = current; root.attached = true; root.mutex_resources = &resources; root.mutex_control_bytes = 32768;
 root.core.origin = current; native = (struct kd_execution_binding) { KD_EXECUTION_NATIVE, &root.core, current };
 proxy = (struct kd_execution_binding) { KD_EXECUTION_JIT, &root.core, &foreign }; root.core.binding = &native;
 root.core.continuation[0] = 0x123; root.core.continuation[1] = 0x456;
 INIT_LIST_HEAD(&root.core.grants); INIT_LIST_HEAD(&root.native_grants); INIT_LIST_HEAD(&root.rwsem_reads);
 INIT_LIST_HEAD(&resources.ordinary_free); resources.config.proxy_limit = 16; resources.config.image_slot = &image;
 outer->core.atomic_admission = inner.core.atomic_admission = true;
 INIT_LIST_HEAD(&outer->core.active_reads); INIT_LIST_HEAD(&inner.core.active_reads);
 for (unsigned int i = 0; i < 4; ++i) kd_rw_local_init(&locals[i], &resources.ordinary_free);
 event_count = physical_puts = slow_reads = image_lookups = image_puts = local_writes = cancels = guards = 0;
 prepare_error = entry_error = lookup_error = 0; source_admitted = true; force_slow = slow; protect_final = false;
 outer->core.admission = slow ? KD_RW_ADMIT_WRITE : 0;
 CHECK(kd_rw_local_read_lock(&outer->core));
 CHECK(slow_reads == (unsigned int)slow && outer->core.admission == KD_RW_ADMIT_READ);
 inner.core.admission = KD_RW_ADMIT_WRITE;
}
static struct kd_rw_native_record *read_record(void) { return &locals[0].record; }
static struct kd_mutex_entry *enter_writer(void)
{ return prepare_rwsem_writer(&inner, KD_OPERATION_RWSEM_DOWN_WRITE); }
static void original_read(void)
{
 struct kd_rw_native_record *r = read_record();
 CHECK(r->phase == KD_RW_NATIVE_ORDINARY_READ && r->grant_user && !r->ordinary_write);
 CHECK(outer->core.admission == KD_RW_ADMIT_READ && !outer->core.readers);
 CHECK(list_empty(&outer->core.active_reads) && list_empty(&root.core.grants));
 CHECK(root.rwsem_reads.next == &r->active_read.task_link && r->active_read.root == &root);
 CHECK(root.native_grants.next == &r->task_link && !physical_puts);
 for (unsigned int i = 0; i < event_count; ++i) CHECK(events[i].kind != KD_OBS_READ_PROMOTE);
}
static void release_bridge(void)
{
 root.aux_entry = NULL;
 CHECK(!kd_rw_local_read_release_promoted(&root, &native, &outer->core.queue, KD_OPERATION_RWSEM_UP_READ));
 CHECK(physical_puts == 1 && read_record()->phase == KD_RW_NATIVE_FREE);
 CHECK(list_empty(&root.core.grants) && list_empty(&root.native_grants) && list_empty(&root.rwsem_reads));
 CHECK(events[event_count - 2].kind == KD_OBS_READ_RELEASE && events[event_count - 1].kind == KD_OBS_ORDINARY_RWSEM_DONE);
 CHECK(events[event_count - 2].acquisition == (unsigned long)read_record());
 CHECK(events[event_count - 1].acquisition == (unsigned long)read_record());
 CHECK(root.core.continuation[0] == 0x123 && root.core.continuation[1] == 0x456);
}
static void check_bridge(bool slow)
{
 setup(slow); CHECK(enter_writer() == &slot.entry);
 struct kd_rw_native_record *r = read_record();
 CHECK(r->phase == KD_RW_NATIVE_PROMOTED_READ && r->read_bridge.published);
 CHECK(list_empty(&root.native_grants) && list_is_singular(&root.core.grants));
 CHECK(r->read_bridge.grant.acquisition == r && r->read_bridge.grant.user == r);
 CHECK(r->read_bridge.credit.state == &root.core && r->read_bridge.credit.active_read.logical_owner == &original);
 CHECK(outer->core.admission == KD_RW_ADMIT_READ && outer->core.readers == 1);
 CHECK(!kd_rw_admission_write_try(&outer->core, true) && !physical_puts);
 CHECK(image_lookups == 1 && image_puts == 1 && !local_writes && !cancels);
 CHECK(event_count == 2 && events[1].kind == KD_OBS_READ_PROMOTE && events[1].node == (unsigned long)&slot.call.node);
 CHECK(frame.source_target == KD_OPERATION_RWSEM_DOWN_WRITE);
 release_bridge(); CHECK(kd_rw_admission_write_try(&outer->core, true));
 CHECK(!munmap(outer, page_bytes));
}
static void check_scope(void)
{
 setup(false); struct kd_rw_native_record *r = read_record();
 CHECK(!kd_rw_local_read_candidate(&root, &outer->core));
 r->ordinary_write = true; CHECK(!kd_rw_local_read_candidate(&root, &inner.core)); r->ordinary_write = false;
 r->phase = KD_RW_NATIVE_READ_HELD; CHECK(!kd_rw_local_read_candidate(&root, &inner.core)); r->phase = KD_RW_NATIVE_ORDINARY_READ;
 r->non_owner = true; CHECK(!kd_rw_local_read_candidate(&root, &inner.core)); r->non_owner = false;
 CHECK(kd_rw_local_read_candidate(&root, &inner.core) == r);
 CHECK(kd_rw_local_read_lock(&outer->core)); CHECK(!kd_rw_local_read_candidate(&root, &inner.core));
 CHECK(!enter_writer() && local_writes == 1 && !image_lookups && list_empty(&root.core.grants));
 CHECK(!munmap(outer, page_bytes));
}
static void check_ineligible(void)
{
 for (int mode = 0; mode < 3; ++mode) {
  setup(false);
  if (mode == 0) resources.config.proxy_limit = 0;
  if (mode == 1) lookup_error = -ENOENT;
  if (mode == 2) inner.core.admission = 0;
  CHECK(!enter_writer()); original_read();
  CHECK(image_lookups == (unsigned int)(mode == 1) && !image_puts && !cancels);
  CHECK(local_writes == (unsigned int)(mode != 2)); CHECK(!munmap(outer, page_bytes));
 }
}
static void check_rollback(void)
{
 for (int mode = 0; mode < 3; ++mode) {
  setup(false);
  if (mode == 0) prepare_error = -EAGAIN;
  if (mode == 1) source_admitted = false;
  if (mode == 2) entry_error = -EINVAL;
  CHECK(!enter_writer()); original_read();
  CHECK(!root.aux_entry && image_lookups == 1 && image_puts == 1 && local_writes == 1);
  CHECK(cancels == (unsigned int)(mode != 0));
  CHECK(kd_rw_local_read_release(&outer->core) && physical_puts == 1);
  CHECK(!munmap(outer, page_bytes));
 }
}
static void check_owner(void)
{
 setup(false); CHECK(enter_writer() == &slot.entry); root.aux_entry = NULL;
 current = &foreign; root.core.binding = &proxy;
 CHECK(kd_rw_local_read_release_promoted(&root, &proxy, &outer->core.queue, KD_OPERATION_RWSEM_UP_READ) == -EPERM);
 CHECK(outer->core.admission == KD_RW_ADMIT_READ && !physical_puts);
 current = &original; root.core.binding = &native;
 release_bridge();
 CHECK(kd_rw_local_read_release_promoted(&root, &native, &outer->core.queue, KD_OPERATION_RWSEM_UP_READ) == -EOPNOTSUPP);
 CHECK(physical_puts == 1 && !munmap(outer, page_bytes));
}
static void check_final(void)
{
 setup(false); CHECK(enter_writer() == &slot.entry); protect_final = true;
 release_bridge();
 CHECK(!mprotect(outer, page_bytes, PROT_READ | PROT_WRITE)); protect_final = false;
 CHECK(kd_rw_local_read_lock(&outer->core));
 CHECK(root.native_grants.next == &read_record()->task_link && read_record()->phase == KD_RW_NATIVE_ORDINARY_READ);
 CHECK(kd_rw_local_read_release(&outer->core) && physical_puts == 2);
 CHECK(!munmap(outer, page_bytes));
}
int main(int argc, char **argv)
{
 CHECK(argc == 2);
 if (!strcmp(argv[1], "fast")) check_bridge(false);
 else if (!strcmp(argv[1], "slow")) check_bridge(true);
 else if (!strcmp(argv[1], "scope")) check_scope();
 else if (!strcmp(argv[1], "ineligible")) check_ineligible();
 else if (!strcmp(argv[1], "rollback")) check_rollback();
 else if (!strcmp(argv[1], "owner")) check_owner();
 else if (!strcmp(argv[1], "final")) check_final();
 else CHECK(false);
 printf("PASS %s\n", argv[1]); return 0;
}
