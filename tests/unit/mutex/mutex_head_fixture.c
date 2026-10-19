/* Minimal field types and instrumented primitives around the real production
 * helper. The origin's CPU/slot reservation prevents encoded-tail reuse while
 * this helper runs. Publications below model another reserved node only. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint32_t u32;
struct kd_mutex { u32 delegation_tail; };
struct kd_mutex_node { struct kd_mutex_node *next; int tail; };
static struct kd_mutex lock;
static struct kd_mutex_node head, successor;
static unsigned int tail_reads, cas_calls, pauses;
static bool publish_at_cas, publish_after_pause;

#define CHECK(value) do { if (!(value)) { \
 fprintf(stderr, "FAIL head line %d: %s\n", __LINE__, #value); exit(1); \
} } while (0)

static void observe_read(const void *address)
{
 if (address == &lock.delegation_tail)
  tail_reads++;
}
#define READ_ONCE(value) ({ observe_read(&(value)); \
 (*(volatile __typeof__(value) *)&(value)); })
#define smp_load_acquire(word) __atomic_load_n((word), __ATOMIC_ACQUIRE)

static __attribute__((unused)) u32
test_cmpxchg(u32 *word, u32 expected, u32 next)
{
 u32 old;

 CHECK(word == &lock.delegation_tail && expected == (u32)head.tail && !next);
 cas_calls++;
 if (publish_at_cas) {
  /* The new tail becomes visible before its predecessor link. */
  CHECK(*word == (u32)head.tail && !head.next);
  *word = successor.tail;
  publish_at_cas = false;
  publish_after_pause = true;
 }
 old = *word;
 if (old == expected)
  *word = next;
 return old;
}
#define cmpxchg test_cmpxchg

static void cpu_relax(void)
{
 CHECK(++pauses <= 4);
 if (publish_after_pause) {
  CHECK(lock.delegation_tail == (u32)successor.tail && !head.next);
  head.next = &successor;
  publish_after_pause = false;
 }
}

#include "head_production.h"

static void reset(void)
{
 memset(&head, 0, sizeof(head));
 memset(&successor, 0, sizeof(successor));
 head.tail = 16;
 successor.tail = 32;
 lock.delegation_tail = head.tail;
 tail_reads = cas_calls = pauses = 0;
 publish_at_cas = publish_after_pause = false;
}

int main(void)
{
 reset();
 head.next = &successor;
 lock.delegation_tail = successor.tail;
 CHECK(kd_mutex_head_successor(&lock, &head) == &successor);
 CHECK(!tail_reads && !cas_calls && !pauses);
 CHECK(lock.delegation_tail == (u32)successor.tail && head.next == &successor);

 reset();
 CHECK(kd_mutex_head_successor(&lock, &head) == NULL);
 CHECK(tail_reads == 1 && cas_calls == 1 && !pauses);
 CHECK(!lock.delegation_tail && !head.next);
 /* A publication after successful retirement starts an independent head. */
 lock.delegation_tail = successor.tail;
 CHECK(!head.next);

 reset();
 lock.delegation_tail = successor.tail;
 publish_after_pause = true;
 CHECK(kd_mutex_head_successor(&lock, &head) == &successor);
 CHECK(tail_reads == 1 && !cas_calls && pauses == 1 && !publish_after_pause);
 CHECK(lock.delegation_tail == (u32)successor.tail);

 reset();
 publish_at_cas = true;
 CHECK(kd_mutex_head_successor(&lock, &head) == &successor);
 CHECK(tail_reads == 1 && cas_calls == 1 && pauses == 1);
 CHECK(!publish_at_cas && !publish_after_pause &&
       lock.delegation_tail == (u32)successor.tail);

 puts("PASS production mutex head: linked successor, exact last-node CAS, delayed link and racing publication");
 return 0;
}
