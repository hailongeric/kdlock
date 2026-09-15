/*
 * Role synchronization gates and stable mode numbers for the ioctl driver.
 * Private implementation included only by klock_module.c.
 * Keep this translation unit: static state, inlining and assembly labels
 * are shared with the adjacent components. This is not a standalone object.
 */

static atomic_t inner_holder_ready = ATOMIC_INIT(0);
static atomic_t inner_direct_waiting = ATOMIC_INIT(0);
static atomic_t inner_nested_waiting = ATOMIC_INIT(0);
static atomic_t inner_trailing_waiting = ATOMIC_INIT(0);
static atomic_t outer_holder_ready = ATOMIC_INIT(0);
static atomic_t outer_direct_waiting = ATOMIC_INIT(0);
static atomic_t outer_nested_waiting = ATOMIC_INIT(0);
static atomic_t outer_trailing_waiting = ATOMIC_INIT(0);
static atomic_t mutex_inner_holder_ready = ATOMIC_INIT(0);
static atomic_t mutex_inner_direct_waiting = ATOMIC_INIT(0);
static atomic_t mutex_inner_nested_waiting = ATOMIC_INIT(0);
static atomic_t mutex_inner_trailing_waiting = ATOMIC_INIT(0);
static atomic_t mutex_outer_holder_ready = ATOMIC_INIT(0);
static atomic_t mutex_outer_direct_waiting = ATOMIC_INIT(0);
static atomic_t mutex_outer_nested_waiting = ATOMIC_INIT(0);
static atomic_t mutex_outer_trailing_waiting = ATOMIC_INIT(0);
static atomic64_t gs_spin_attempts = ATOMIC64_INIT(0);
static atomic64_t gs_spin_successes = ATOMIC64_INIT(0);
static atomic64_t gs_spin_failures = ATOMIC64_INIT(0);
static atomic64_t gs_mutex_attempts = ATOMIC64_INIT(0);
static atomic64_t gs_mutex_successes = ATOMIC64_INIT(0);
static atomic64_t gs_mutex_failures = ATOMIC64_INIT(0);

#define MODE_ROLE_SYNCHRONIZED 0x80000000U
#define MODE_ROLE_OUTER_ONLY 0x40000000U

#define MODE_SPIN_CONTENTION 0
#define MODE_SPIN_NESTED 1
#define MODE_SPIN_API_IN_LOCK 2
#define MODE_MUTEX_CONTENTION 3
#define MODE_MUTEX_NESTED 4
#define MODE_MUTEX_API_IN_LOCK 5
#define MODE_SPIN_DEEP_NESTED 6
#define MODE_SPIN_OOO_NESTED 7
#define MODE_SPIN_INNER_CONTENTION 8
#define MODE_SPIN_ABORT_RECOVERY 9
#define MODE_SPIN_GS_CONTEXT 10
#define MODE_MUTEX_GS_CONTEXT 11
