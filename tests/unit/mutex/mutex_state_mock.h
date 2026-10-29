/* Deterministic primitive boundary for queue/routing fixtures. Actual embedded
 * state helpers are extracted unchanged; concurrent atomics run separately in
 * test_mutex_state.py. The observer injects a successor after FREE publication. */
#ifndef KD_MUTEX_STATE_MOCK_H
#define KD_MUTEX_STATE_MOCK_H
#ifndef U32_MAX
#define U32_MAX UINT32_MAX
#endif
#ifndef U64_MAX
#define U64_MAX UINT64_MAX
#endif
#ifndef smp_wmb
#define smp_wmb() ((void)0)
#endif
#ifndef READ_ONCE
#define READ_ONCE(v) (v)
#endif
#ifndef WRITE_ONCE
#define WRITE_ONCE(p, v) ((p) = (v))
#endif
#ifndef fixture_state_changed
#define fixture_state_changed(p) ((void)(p))
#endif
#define atomic_read(p) ((p)->counter)
#define atomic_read_acquire(p) atomic_read(p)
#define atomic_set_release(p, value) do { \
 (p)->counter = (value); fixture_state_changed(p); \
} while (0)
#define atomic_cmpxchg(p, old, value) ({ \
 int fixture_seen = (p)->counter; \
 if ((u32)fixture_seen == (u32)(old)) { \
  (p)->counter = (value); fixture_state_changed(p); \
 } fixture_seen; })
#define atomic_cmpxchg_release(p, old, value) atomic_cmpxchg(p, old, value)
#define atomic_fetch_andnot_release(mask, p) ({ \
 int fixture_old = (p)->counter; \
 (p)->counter = (u32)fixture_old & ~(u32)(mask); \
 fixture_state_changed(p); fixture_old; })
#define atomic_fetch_add(v, p) ({ int fixture_old = (p)->counter; \
 (p)->counter = (u32)fixture_old + (u32)(v); fixture_old; })
#define atomic_fetch_sub(v, p) ({ int fixture_old = (p)->counter; \
 (p)->counter = (u32)fixture_old - (u32)(v); fixture_old; })
#include "mutex_state_production.h"
#endif
