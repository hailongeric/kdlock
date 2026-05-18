#ifndef NEW_KD_LOCK
#define NEW_KD_LOCK

#include <linux/freezer.h>
#include <linux/sched/signal.h>
#include <linux/sched/task.h>

#include <linux/sched/task_stack.h>
#include <linux/string.h>
#include <linux/kernel.h>
#include <asm/barrier.h>

#include <linux/futex.h>
#include <linux/rtmutex.h>
#include <linux/sched/wake_q.h>

#include <linux/types.h>
#include <linux/restart_block.h>
#include <linux/lockdep.h>
#include <linux/spinlock.h>
#include <linux/mutex.h>

#ifdef CONFIG_PREEMPT_RT
#include <linux/rcuwait.h>
#endif

#include <asm/futex.h>


struct futex_hash_bucket {
    atomic_t waiters;
    spinlock_t lock;
    struct plist_head chain;
} ____cacheline_aligned_in_smp;

struct futex_pi_state {
    /*
     * list of 'owned' pi_state instances - these have to be
     * cleaned up in do_exit() if the task exits prematurely:
     */
    struct list_head list;

    /*
     * The PI object:
     */
    struct rt_mutex_base pi_mutex;

    struct task_struct* owner;
    refcount_t refcount;

    union futex_key key;
} __randomize_layout;

struct futex_q {
    struct plist_node list;

    struct task_struct* task;
    spinlock_t* lock_ptr;
    union futex_key key;
    struct futex_pi_state* pi_state;
    struct rt_mutex_waiter* rt_waiter;
    union futex_key* requeue_pi_key;
    u32 bitset;
    atomic_t requeue_state;
    //int nf_state;
#ifdef CONFIG_PREEMPT_RT
    struct rcuwait requeue_wait;
#endif
} __randomize_layout;

enum {
    Q_REQUEUE_PI_NONE = 0,
    Q_REQUEUE_PI_IGNORE,
    Q_REQUEUE_PI_IN_PROGRESS,
    Q_REQUEUE_PI_WAIT,
    Q_REQUEUE_PI_DONE,
    Q_REQUEUE_PI_LOCKED,
};

# define FLAGS_SHARED		0x00
#define FLAGS_HAS_TIMEOUT	0x04

enum futex_access {
    FUTEX_READ,
    FUTEX_WRITE
};

static inline int futex_match(union futex_key* key1, union futex_key* key2) {
    return (key1 && key2
        && key1->both.word == key2->both.word
        && key1->both.ptr == key2->both.ptr
        && key1->both.offset == key2->both.offset);
}

static inline int futex_hb_waiters_pending(struct futex_hash_bucket* hb) {
#ifdef CONFIG_SMP
    /*
     * Full barrier (B), see the ordering comment above.
     */
    smp_mb();
    return atomic_read(&hb->waiters);
#else
    return 1;
#endif
}

static inline void futex_hb_waiters_inc(struct futex_hash_bucket* hb) {
#ifdef CONFIG_SMP
    atomic_inc(&hb->waiters);
    /*
     * Full barrier (A), see the ordering comment above.
     */
    smp_mb__after_atomic();
#endif
}

static inline void futex_hb_waiters_dec(struct futex_hash_bucket* hb) {
#ifdef CONFIG_SMP
    atomic_dec(&hb->waiters);
#endif
}

extern void __futex_queue(struct futex_q* q, struct futex_hash_bucket* hb);

static inline void futex_queue(struct futex_q* q, struct futex_hash_bucket* hb)
__releases(&hb->lock) {
    __futex_queue(q, hb);
    spin_unlock(&hb->lock);
}

static inline void nf_preempt_disable_raw_spin_lock(raw_spinlock_t* lock) {
    spin_acquire(&lock->dep_map, 0, 0, _RET_IP_);
    LOCK_CONTENDED(lock, do_raw_spin_trylock, do_raw_spin_lock);
}

static __always_inline void nf_preempt_disable_spin_lock(spinlock_t* lock)
{
    nf_preempt_disable_raw_spin_lock(&lock->rlock);
}


void __kd_raw_spin_lock(raw_spinlock_t *lock, unsigned long ret_addr);
void __kd_raw_spin_unlock(raw_spinlock_t *lock, unsigned long ret_addr);

// ! kd mod
void __kd_mutex_lock(struct mutex  *lock, unsigned long ret_addr);
void __kd_mutex_unlock(struct mutex  *lock, unsigned long ret_addr);
int new_futex_wake1(u32 __user* uaddr, unsigned int flags, int nr_wake, u32 bitset);

int __nf_do_int3(struct pt_regs* regs);

void origin_raw_spin_lock(raw_spinlock_t *lock);
void origin_raw_spin_unlock(raw_spinlock_t *lock);



#define NF_WAKER 20
#define NF_WAKE_NUM 20
#define NF_FAST_PATH_WAKE_NUM 20
#define NF_SLOW_PATH_WAKE_NUM 20
#define NF_CNT_NUM 40
#define NF_E_QUEUE_NUM 20

#define fast_path_uninit 0
#define fast_path_ready 1
#define fast_path_success 2
#define fast_path_fail 3
#define fast_path_timeout 4
#define fast_path_no_need_to_sleep 5

#define fast_wake_ready 6
#define fast_wake_success 7
#define fast_wake_timeout 8
#define fast_to_slow_wake 9

#endif