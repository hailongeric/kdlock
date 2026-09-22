"""Execute the public direct unlock's real routing with ownership substitutes.

The existing queue/entry fixtures test the release internals. This checks the
new public boundary cannot drop a KD-word owner or double-release a native ACK.
"""
import subprocess
import tempfile
from pathlib import Path

from test_spin_shadow import definition

ROOT = Path(__file__).resolve().parents[3]
PRELUDE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#define noinline
#define notrace
struct qspinlock { int value; };
typedef struct qspinlock raw_spinlock_t;
struct kd_spin_ref { int token; };
static struct qspinlock lock;
static int fast_owned, native_ack, ticket, releases, lookups, preempt;
static bool kd_spin_fast_unlock(raw_spinlock_t *p) {
    assert(p == &lock);
    if (!fast_owned) return false;
    releases++; preempt--; return true;
}
static bool kd_exec_native_unlock(unsigned long p, bool mutex) {
    assert(p == (unsigned long)&lock && !mutex);
    if (!native_ack) return false;
    releases++; preempt--; return true;
}
static bool kd_spin_entry_find(raw_spinlock_t *p, struct kd_spin_ref *r) {
    assert(p == &lock); lookups++;
    r->token = ticket; return ticket != 0;
}
static void kd_spin_unlock_ref(struct qspinlock *p, const struct kd_spin_ref *r) {
    assert(p == &lock && r->token == ticket && ticket);
    releases++; preempt--;
}
typedef struct qspinlock kd_spinlock_t;
static void kd_spin_unlock_nondelegated(kd_spinlock_t *p) {
    assert(p == &lock && !fast_owned && !ticket && !native_ack);
    releases++; preempt--;
}
'''
MAIN = r'''
int main(void) {
    for (int mode = 0; mode < 4; mode++) {
        fast_owned = mode == 0; native_ack = mode == 1; ticket = mode == 2 ? 7 : 0;
        releases = lookups = 0; preempt = 1;
        kd_spin_unlock(&lock);
        assert(releases == 1 && preempt == 0);
        assert(lookups == (mode >= 2));
    }
    puts("PASS direct unlock: fast S/L, native ACK, queued ticket, KD nondelegated fallback");
}
'''


def main():
    source = (ROOT/'kernel_module/kd_spinlock.c').read_text()
    code = PRELUDE + 'void ' + definition(source, 'kd_spin_unlock_slow(struct qspinlock *lock)') + 'static inline void ' + definition(source, 'kd_spin_unlock_core(struct qspinlock *lock)') + definition(source, 'kd_spin_unlock(struct qspinlock *lock)').replace(
        'kd_spin_unlock(', 'void kd_spin_unlock(', 1) + MAIN
    with tempfile.TemporaryDirectory(prefix='kd-direct-unlock-') as temporary:
        path = Path(temporary)
        (path/'test.c').write_text(code)
        subprocess.run(['cc', '-O2', '-Wall', '-Wextra', '-Werror', str(path/'test.c'),
                        '-o', str(path/'test')], check=True, timeout=30)
        subprocess.run([path/'test'], check=True, timeout=10)


if __name__ == '__main__':
    main()
