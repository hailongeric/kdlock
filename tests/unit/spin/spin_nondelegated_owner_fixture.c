/* Real ownership records and paired bridge API; only physical acquisition
 * and kernel CPU/pin primitives are substitutes in this deterministic test. */
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdint.h>
struct task_struct { int id; } task;
#define current (&task)
typedef struct { unsigned char locked; } kd_spinlock_t;
typedef kd_spinlock_t raw_spinlock_t;
static unsigned int pins;
static unsigned int physical_entries;
static bool task_context = true;
#undef __always_inline
#define __always_inline inline __attribute__((always_inline))
#define DECLARE_PER_CPU(type, name) type name
#define PREEMPT_MASK 255U
#define in_task() task_context
#define preempt_count() pins
#define preempt_disable() (++pins)
#define preempt_enable() do { assert(pins); --pins; } while (0)
#define raw_cpu_ptr(p) (p)
#define this_cpu_inc(x) (++(x))
#define this_cpu_dec(x) do { assert(x); --(x); } while (0)
#define BUG_ON(x) assert(!(x))
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, v) ((x)=(v))
#define smp_store_release(p, v) (*(p)=(v))
#define for_each_possible_cpu(cpu) for ((cpu)=0;(cpu)<1;(cpu)++)
#define per_cpu(x,cpu) (x)
static void kd_spin_acquire_nondelegated(kd_spinlock_t *lock)
{ assert(pins && !lock->locked); lock->locked=1; }
/* Model only the CPU-local statistic; the extracted API owns its pin. */
static void kd_hotlock_spin_entry_pinned(void)
{ assert(pins); physical_entries++; }
#include "spin_nondelegated_api.h"
int main(void)
{
 kd_spinlock_t a={0}, b={0};
 kd_spin_lock_nondelegated(&a);
 assert(pins==1 && kd_spin_fast_cpu.held==&a && !kd_spin_fast_cpu.nondelegated);
 assert(physical_entries==1);
 kd_spin_lock_nondelegated(&b);
 assert(pins==2 && kd_spin_fast_cpu.held==&a && kd_spin_fast_cpu.nondelegated==1);
 assert(physical_entries==2);
 kd_spin_unlock_nondelegated(&b);
 assert(pins==1 && a.locked && !b.locked && !kd_spin_fast_cpu.nondelegated);
 kd_spin_unlock_nondelegated(&a); /* direct bridge, no public unlock router */
 assert(!pins && !a.locked && kd_spin_fast_idle());
 assert(physical_entries==2);
 task_context=false;
 kd_spin_lock_nondelegated(&a);
 assert(pins==1 && !kd_spin_fast_cpu.held && kd_spin_fast_cpu.nondelegated==1);
 kd_spin_unlock_nondelegated(&a);
 assert(!pins && kd_spin_fast_idle());
 assert(physical_entries==3);
 task_context=true; pins=2;
 kd_spin_lock_nondelegated(&a);
 assert(pins==3 && !kd_spin_fast_cpu.held && kd_spin_fast_cpu.nondelegated==1);
 kd_spin_unlock_nondelegated(&a);
 assert(pins==2 && kd_spin_fast_idle());
 assert(physical_entries==4);
 puts("PASS nondelegated owner: root, nested, IRQ/pinned and direct bridge release balanced");
}
