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
	KDB_NEST_SPIN, KDB_NEST_MUTEX, KDB_MIX };
/*
 * KDB_TCLOCK: the original TCLock locks from tclock_backend/ (komb_*),
 * present only in a module built with KDB_TCLOCK=1, for the four base
 * families. Otherwise runs with it fail with EOPNOTSUPP.
 */
enum { KDB_NATIVE, KDB_KD, KDB_TCLOCK };

/*
 * One timed run. Layout is mirrored in bench/run_nano.py (RUN_FMT).
 * Workers are kernel threads bound to CPUs first_cpu .. first_cpu+workers-1.
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

#endif
