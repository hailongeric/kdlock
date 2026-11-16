/* SPDX-License-Identifier: GPL-2.0 */
#ifndef KD_BENCH_UAPI_H
#define KD_BENCH_UAPI_H

#include <linux/types.h>
#include <linux/ioctl.h>

#define KDB_MAX_WORKERS	64

enum { KDB_SPIN, KDB_MUTEX, KDB_RWLOCK, KDB_RWSEM,
	/*
	 * Test bodies (correctness of nesting and handback, not workloads):
	 *   NEST_SPIN   write_pct% of operations take spin A then spin B, the
	 *               rest take B alone, so B is contended inside A
	 *   NEST_MUTEX  the same with a mutex as A
	 *   MIX         mutex section that checks `current`, calls through a
	 *               function pointer, and 1/16 each calls yield() or
	 *               takes a second mutex (both leave delegated code)
	 * Every operation counts as a write. mismatches also counts outer
	 * sections whose own counter changed under them, and a final
	 * difference between outer sections run and the outer counter.
	 */
	KDB_NEST_SPIN, KDB_NEST_MUTEX, KDB_MIX,
	/*
	 * `current` inside the section, to measure what task-identity use
	 * costs a delegated section. Same body as SPIN / MUTEX plus
	 *   *_CURR  one read through `current` (current->pid)
	 *   *_CURW  rcu_read_lock()/rcu_read_unlock(), which with preemptible
	 *           RCU write the caller's task structure twice
	 */
	KDB_SPIN_CURR, KDB_SPIN_CURW, KDB_MUTEX_CURR, KDB_MUTEX_CURW,
	/*
	 * Test body, kd only: every operation takes two of four ww mutexes
	 * in random order under one acquire context, backs off on -EDEADLK,
	 * and increments the two counters they protect (run with lines = 2).
	 */
	KDB_WW,
	/*
	 * SPIN through the raw (never delegated) acquire: the plain path
	 * alone. With the native backend: the native queued spinlock code on
	 * the kd lock object.
	 */
	KDB_SPIN_RAW,
	/*
	 * Handback bodies: every sixteenth write section meets something only
	 * its own task may run, so the section is handed back in the middle
	 * and the role exchange is exercised.
	 *   SPIN_HB, RWLOCK_HB  an instruction with a fault fixup
	 *                       (copy_from_kernel_nofault)
	 *   RWSEM_HB            yield()
	 */
	KDB_SPIN_HB, KDB_RWLOCK_HB, KDB_RWSEM_HB,
	/*
	 * kd only: the clobber entries (kd_api.h, kd_*_cl()). The workloads
	 * are those of SPIN, MUTEX, RWLOCK and RWSEM with the writers' lock
	 * and release calls made through the macros; Native and TCLock run
	 * their ordinary bodies, so the three can be compared as usual.
	 *   SPIN_HB_CL, RWSEM_HB_CL  the handback bodies with clobber entries:
	 *                            a compact continuation continued from a
	 *                            full state
	 *   SPIN_MIXEND              alternately a clobber lock with an
	 *                            ordinary release and the reverse
	 *   NEST_SPIN_CL             NEST_SPIN with the outer lock through
	 *                            the clobber entries
	 */
	KDB_SPIN_CL, KDB_MUTEX_CL, KDB_RWLOCK_CL, KDB_RWSEM_CL,
	KDB_SPIN_HB_CL, KDB_RWSEM_HB_CL, KDB_SPIN_MIXEND, KDB_NEST_SPIN_CL,
	KDB_NR_FAMILY };
/*
 * KDB_TCLOCK: the original TCLock locks from tclock_backend/ (komb_*),
 * present only in a module built with KDB_TCLOCK=1, for the four base
 * families. Otherwise runs with it fail with EOPNOTSUPP.
 */
enum { KDB_NATIVE, KDB_KD, KDB_TCLOCK };

/*
 * One timed run. Layout is mirrored in bench/run_nano.py (RUN_FMT).
 * Workers are kernel threads, each bound to one CPU: worker i to CPU
 * first_cpu + i, or with cpus set to first_cpu + i % cpus, which puts
 * several workers on a CPU (more threads than CPUs).
 */
struct kdb_run {
	/* in */
	__u32 family, backend;
	__u32 lines;		/* padded counters in the protected body: 1 or 16 */
	__u32 write_pct;	/* ignored (100) for spin, mutex and mix */
	__u32 post;		/* register-only rounds after each unlock */
	__u32 workers;
	__u32 first_cpu;
	__u32 ms;
	__u32 cpus;		/* CPUs the workers share; 0: one each */
	__u32 pad;
	/* out */
	__u64 elapsed_ns;
	__u64 ops;
	__u64 writes;
	__u64 mismatches;	/* readers that saw unequal counters */
	__u64 sum_delta;	/* counter sum after - before; must equal writes * lines */
	__u64 worker_ops[KDB_MAX_WORKERS];
	__u64 worker_writes[KDB_MAX_WORKERS];
};

#define KDB_IOC_RUN	_IOWR('B', 1, struct kdb_run)
/*
 * Single-task check of every kd lock API variant: each call must leave the
 * lock state, the interrupt flag and the preempt count as the native
 * variant would. Returns the number of failed checks (details in dmesg).
 */
#define KDB_IOC_APITEST	_IO('B', 2)

#endif
