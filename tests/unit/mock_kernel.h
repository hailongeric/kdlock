/*
 * mock_kernel.h — minimal kernel type mocks for user-space unit testing.
 *
 * Provides just enough of the kernel API surface to compile and test
 * the pure-logic parts of kdlock (hash tables, queues, state machines)
 * without touching the real kernel.
 */
#ifndef MOCK_KERNEL_H
#define MOCK_KERNEL_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <assert.h>

/* Basic kernel types */
typedef uint8_t  u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef int32_t  s32;
typedef int64_t  s64;

typedef struct { int counter; } atomic_t;
typedef struct { long counter; } atomic_long_t;

#define atomic_read(v)           ((v)->counter)
#define atomic_set(v, i)         ((v)->counter = (i))
#define atomic_long_read(v)      ((v)->counter)
#define atomic_long_set(v, i)    ((v)->counter = (i))
#define atomic_long_cmpxchg(v, old, new) \
    ({ long __o = (old); if ((v)->counter == __o) (v)->counter = (new); __o; })

/* Compiler hints */
#define likely(x)       __builtin_expect(!!(x), 1)
#define unlikely(x)     __builtin_expect(!!(x), 0)
#define __cacheline_aligned_in_smp
#undef __always_inline
#define __always_inline  inline
#define noinline
#define notrace
#define __attribute_noipa__

/* Locking stubs */
#define WRITE_ONCE(x, val)  ((x) = (val))
#define READ_ONCE(x)        (x)
#define smp_mb()            __sync_synchronize()
#define cpu_relax()         do {} while (0)
#define barrier()           __asm__ __volatile__("" ::: "memory")

/* cmpxchg mock */
#define cmpxchg(ptr, old, new) ({                \
    typeof(*(ptr)) __old = (old);                \
    typeof(*(ptr)) __new = (new);                \
    typeof(*(ptr)) __prev = *(ptr);              \
    if (__prev == __old) *(ptr) = __new;         \
    __prev;                                      \
})

/* xchg mock */
#define xchg(ptr, val) ({                        \
    typeof(*(ptr)) __prev = *(ptr);              \
    *(ptr) = (val);                              \
    __prev;                                      \
})

/* per-cpu stub (single CPU for unit tests) */
#define this_cpu_ptr(ptr)       (ptr)
#define per_cpu_ptr(ptr, cpu)   ((ptr) + 0)
#define smp_processor_id()      0
#define numa_node_id()          0
#define num_online_nodes()      1

/* printk stub */
#define KERN_INFO   ""
#define KERN_ALERT  ""
#define KERN_ERR    ""
#define printk(fmt, ...)      /* suppress */
#define printk_ratelimited(fmt, ...) /* suppress */
#define pr_info(fmt, ...)     /* suppress */
#define pr_err(fmt, ...)      fprintf(stderr, fmt, ##__VA_ARGS__)

#define KD_PR_INFO(fmt, ...)  /* suppress */
#define KD_PR_ERR(fmt, ...)   fprintf(stderr, "[ERR] " fmt "\n", ##__VA_ARGS__)
#define KD_PR_DEBUG(fmt, ...) /* suppress */

/* rdtsc mock */
static uint64_t mock_tsc __attribute__((unused)) = 1000000000UL;
static inline uint64_t rdtsc_ordered(void) { return mock_tsc++; }

/* current task stub */
struct mock_task_struct {
    int pid;
    int tgid;
    char comm[16];
};
static struct mock_task_struct mock_current __attribute__((unused)) = { .pid = 1000, .tgid = 1000, .comm = "test" };
#define current (&mock_current)

/* GFP flags */
#define GFP_KERNEL 0

/* vmalloc stubs */
#define vmalloc(sz)      calloc(1, (sz))
#define vfree(p)         free(p)
#define vzalloc(sz)      calloc(1, (sz))

#endif /* MOCK_KERNEL_H */
