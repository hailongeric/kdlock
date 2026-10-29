/* Guest-only binding/lifetime fixture. Physical KD algorithms are mocked;
 * registry/selection/object initialization/destruction/routes are production. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <string.h>
typedef uint32_t u32;
typedef uint32_t __u32;
typedef int32_t __s32;
typedef uint64_t __u64;
typedef struct { int counter; } atomic_t;
typedef struct { long counter; } atomic_long_t;
typedef struct { unsigned int held; } spinlock_t;
struct mutex { unsigned long words[4]; };
typedef struct { atomic_t val; } kd_spinlock_t;
struct kd_mutex { unsigned long words[4]; };
struct module { int refs; bool allow; };
struct file { int number; };
struct task_struct { int refs; };
static struct task_struct tasks[40], *current = &tasks[0];
static bool admin = true;
static unsigned int checks, spin_native, mutex_native, spin_kd, mutex_kd;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "FAIL %u %s\n", __LINE__, #x); exit(1); } } while (0)
#define BUG_ON(x) do { if (x) { fprintf(stderr, "BUG %u %s\n", __LINE__, #x); exit(86); } } while (0)
#define CAP_SYS_ADMIN 21
#define ATOMIC_LONG_INIT(v) {v}
#define DEFINE_MUTEX(name) struct mutex name = {{0}}
#define static_assert _Static_assert
#define EXPORT_SYMBOL_GPL(name)
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define container_of(p,t,m) ((t *)((char *)(p) - offsetof(t,m)))
static bool capable(int cap) { CHECK(cap == CAP_SYS_ADMIN); return admin; }
static void mutex_lock(struct mutex *m) { CHECK(!m->words[0]); m->words[0] = 1; mutex_native++; }
static void mutex_unlock(struct mutex *m) { CHECK(m->words[0] == 1); m->words[0] = 0; }
static void mutex_init(struct mutex *m) { memset(m, 0, sizeof(*m)); }
static void spin_lock(spinlock_t *s) { CHECK(!s->held); s->held = 1; spin_native++; }
static void spin_unlock(spinlock_t *s) { CHECK(s->held == 1); s->held = 0; }
static void spin_lock_init(spinlock_t *s) { s->held = 0; }
static bool try_module_get(struct module *m) { if (!m->allow) return false; m->refs++; return true; }
static void module_put(struct module *m) { CHECK(m->refs > 0); m->refs--; }
static void get_task_struct(struct task_struct *t) { t->refs++; }
static void put_task_struct(struct task_struct *t) { CHECK(t->refs > 0); t->refs--; }
static long atomic_long_read(atomic_long_t *a) { return a->counter; }
static void atomic_long_inc(atomic_long_t *a) { a->counter++; }
static void atomic_long_dec(atomic_long_t *a) { CHECK(a->counter > 0); a->counter--; }

#include "api_types.h"
struct files_struct { kd_api_spinlock_t file_lock; const struct kd_api_provider *kd_lock_provider; };
struct pipe_inode_info { kd_api_mutex_t mutex; const struct kd_api_provider *kd_lock_provider; };
#include "api_binding_production.h"

static void s_init(kd_spinlock_t *s) { s->val.counter = 0; }
static bool s_idle(kd_spinlock_t *s) { return s->val.counter == 0; }
static void s_lock(kd_spinlock_t *s) { CHECK(!s->val.counter); s->val.counter = 7; spin_kd++; }
static void s_unlock(kd_spinlock_t *s) { CHECK(s->val.counter == 7); s->val.counter = 0; }
static void m_init(struct kd_mutex *m) { memset(m, 0, sizeof(*m)); }
static bool m_idle(struct kd_mutex *m) { return !m->words[0]; }
static void m_lock(struct kd_mutex *m) { CHECK(!m->words[0]); m->words[0] = 7; mutex_kd++; }
static void m_unlock(struct kd_mutex *m) { CHECK(m->words[0] == 7); m->words[0] = 0; }
static void s_clobber(kd_spinlock_t *s, unsigned long sp, unsigned long ip, unsigned long bp)
{ (void)s; (void)sp; (void)ip; (void)bp; abort(); }
static void m_clobber(struct kd_mutex *m, unsigned long sp, unsigned long ip, unsigned long bp)
{ (void)m; (void)sp; (void)ip; (void)bp; abort(); }

int main(int argc, char **argv)
{
	struct module owner = {.allow = true};
	struct kd_api_provider ops = {.spin_lock = s_clobber, .spin_unlock = s_clobber,
		.mutex_lock = m_clobber, .mutex_unlock = m_clobber,
		.spin_local_lock = s_lock, .spin_local_unlock = s_unlock,
		.mutex_local_lock = m_lock, .mutex_local_unlock = m_unlock,
		.spin_init = s_init, .spin_idle = s_idle, .mutex_init = m_init, .mutex_idle = m_idle,
		.owner = &owner, .version = KD_API_VERSION};
	struct file tokens[40] = {{0}};
	struct kd_api_select select = {.version = KD_API_VERSION, .files_budget = 1, .pipes_budget = 1};
	struct files_struct files, native;
	struct pipe_inode_info pipe;
	unsigned int before;

	CHECK(kd_api_register_provider(&ops) == 0);
	CHECK(kd_api_register_provider(&ops) == -EBUSY);
	admin = false;
	CHECK(kd_api_select_current(&tokens[0], &ops, &select) == -EPERM);
	admin = true;
	select.reserved = 1;
	CHECK(kd_api_select_current(&tokens[0], &ops, &select) == -EINVAL);
	select.reserved = 0;
	select.files_budget = 2;
	CHECK(kd_api_select_current(&tokens[0], &ops, &select) == -EINVAL);
	select.files_budget = 1;
	owner.allow = false;
	CHECK(kd_api_select_current(&tokens[0], &ops, &select) == -ENODEV);
	CHECK(owner.refs == 0 && tasks[0].refs == 0);
	owner.allow = true;
	CHECK(kd_api_select_current(&tokens[0], &ops, &select) == 0);
	CHECK(owner.refs == 1 && tasks[0].refs == 1);
	CHECK(kd_api_select_current(&tokens[1], &ops, &select) == -EBUSY);
	current = &tasks[1];
	CHECK(kd_api_select_current(&tokens[0], &ops, &select) == -EBUSY);
	CHECK(kd_api_files_init(&native) == 0 && native.kd_lock_provider == NULL);
	before = spin_native;
	kd_api_files_lock(&native.file_lock); kd_api_files_unlock(&native.file_lock);
	CHECK(spin_native == before + 1 && spin_kd == 0);
	kd_api_files_destroy(&native);
	current = &tasks[0];
	owner.allow = false;
	CHECK(kd_api_files_init(&files) == -ENODEV);
	CHECK(owner.refs == 1 && kd_api_selectors[0].files_left == 1);
	owner.allow = true;
	CHECK(kd_api_files_init(&files) == 0 && files.kd_lock_provider == &ops);
	CHECK(owner.refs == 2 && tasks[0].refs == 1 && atomic_long_read(&kd_api_objects) == 1);
	CHECK(kd_api_pipe_init(&pipe) == 0 && pipe.kd_lock_provider == &ops);
	CHECK(owner.refs == 2 && tasks[0].refs == 0 && atomic_long_read(&kd_api_objects) == 2);
	if (argc == 2 && !strcmp(argv[1], "unregister-live")) {
		kd_api_unregister_provider(&ops); return 0;
	}
	kd_api_cancel_selector(&tokens[0]); /* already consumed: never drops object refs */
	CHECK(owner.refs == 2);
	before = spin_native;
	kd_api_files_lock(&files.file_lock);
	if (argc == 2 && !strcmp(argv[1], "destroy-held")) {
		kd_api_files_destroy(&files); return 0;
	}
	kd_api_files_unlock(&files.file_lock);
	CHECK(spin_native == before && spin_kd == 1);
	before = mutex_native;
	kd_api_pipe_lock(&pipe.mutex); kd_api_pipe_unlock(&pipe.mutex);
	CHECK(mutex_native == before && mutex_kd == 1);
	kd_api_files_destroy(&files); kd_api_pipe_destroy(&pipe);
	CHECK(!owner.refs && !atomic_long_read(&kd_api_objects));
	/* Unpublished error cleanup and descriptor-final-close cancellation. */
	select.pipes_budget = 0;
	CHECK(kd_api_select_current(&tokens[0], &ops, &select) == 0);
	CHECK(kd_api_files_init(&files) == 0);
	kd_api_files_destroy(&files);
	CHECK(!owner.refs && !tasks[0].refs);
	CHECK(kd_api_select_current(&tokens[0], &ops, &select) == 0);
	current = &tasks[1];
	kd_api_cancel_selector(&tokens[0]);
	CHECK(!owner.refs && !tasks[0].refs);
	select.files_budget = 0;
	CHECK(kd_api_select_current(&tokens[1], &ops, &select) == 0);
	CHECK(!owner.refs);
	select.files_budget = 1;
	for (unsigned int i = 0; i < KD_API_SELECTORS; i++) {
		current = &tasks[i];
		CHECK(kd_api_select_current(&tokens[i], &ops, &select) == 0);
	}
	current = &tasks[KD_API_SELECTORS];
	CHECK(kd_api_select_current(&tokens[KD_API_SELECTORS], &ops, &select) == -ENOSPC);
	for (unsigned int i = 0; i < KD_API_SELECTORS; i++)
		kd_api_cancel_selector(&tokens[i]);
	CHECK(!owner.refs);
	for (unsigned int i = 0; i < 40; i++) CHECK(!tasks[i].refs);
	kd_api_unregister_provider(&ops);
	CHECK(kd_api_registered == NULL);
	printf("binding checks=%u, exact selector/object refs drained\n", checks);
	return 0;
}
