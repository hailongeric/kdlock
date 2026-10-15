"""Production readiness transitions: deterministic races and slot reuse."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from source_text import ROOT

FIXTURE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <pthread.h>
#include "kd_image.h"
typedef uint32_t u32;
struct rcuwait { int wakes; };
struct kd_owned_mutex_node { u32 readiness; int origin_cpu; struct rcuwait *wait; };
#define READ_ONCE(x) __atomic_load_n(&(x),__ATOMIC_RELAXED)
#define smp_load_acquire(p) __atomic_load_n(p,__ATOMIC_ACQUIRE)
#define smp_store_release(p,v) __atomic_store_n(p,v,__ATOMIC_RELEASE)
#define try_cmpxchg(p,o,v) __atomic_compare_exchange_n(p,o,v,0,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST)
#define cmpxchg(p,o,v) ({ __typeof__(*(p)) old=(o); try_cmpxchg(p,&old,v); old; })
#define cmpxchg_release cmpxchg
#define cmpxchg_acquire cmpxchg
#define smp_mb() __atomic_thread_fence(__ATOMIC_SEQ_CST)
#define BUG_ON(x) assert(!(x))
#define this_cpu_inc(x) ((x)++)
static _Thread_local int cpu=1;
static int raw_smp_processor_id(void) {return cpu;}
static int preempt_count(void) {return 1;}
static bool owned_mutex_origin_spin=true;
static unsigned long kd_owned_mutex_claim_failures, kd_owned_mutex_claims, kd_owned_mutex_preparations;
static int rcuwait_wake_up(struct rcuwait *w) {return ++w->wakes;}
#include "readiness.inc"
static struct rcuwait wait;
static struct kd_owned_mutex_node node={.origin_cpu=0,.wait=&wait};
static struct kd_jit_image sensitive={.requirements=KD_IMAGE_ORIGIN_SPIN}, plain;
static pthread_barrier_t begin,end;
static void *parker(void *unused) {
 (void)unused; cpu=0;
 for(int i=0;i<10000;i++) {
  pthread_barrier_wait(&begin);
  bool withdrew=kd_owned_mutex_withdraw(&node);
  pthread_barrier_wait(&end);
  assert(withdrew == (READ_ONCE(node.readiness)==KD_ORIGIN_PARKABLE));
  pthread_barrier_wait(&end);
 }
 return NULL;
}
int main(void) {
 assert(kd_owned_mutex_claim(&node,&plain)); /* sleeping independent body */
 node.readiness=KD_ORIGIN_READY;
 assert(kd_owned_mutex_withdraw(&node)); /* parking deterministically wins */
 assert(!kd_owned_mutex_claim(&node,&sensitive));
 assert(!kd_owned_mutex_claim(&node,&sensitive));
 kd_owned_mutex_request_ready(&node); assert(wait.wakes==1);
 assert(node.readiness==KD_ORIGIN_REQUESTED);
 assert(!kd_owned_mutex_claim(&node,&sensitive)); /* wake is not authorization */
 cpu=0;kd_owned_mutex_acknowledge(&node);
 assert(!kd_owned_mutex_claim(&node,&sensitive)); /* same CPU */
 cpu=1;assert(kd_owned_mutex_claim(&node,&sensitive));
 for(int i=0;i<8192;i++) assert(!kd_owned_mutex_withdraw(&node));
 kd_owned_mutex_finish_claim(&node,false);assert(node.readiness==KD_ORIGIN_PARKABLE);
 kd_owned_mutex_request_ready(&node); cpu=0;kd_owned_mutex_acknowledge(&node);
 cpu=1;assert(kd_owned_mutex_claim(&node,&sensitive));
 kd_owned_mutex_finish_claim(&node,true);assert(node.readiness==KD_ORIGIN_FINISHED);
 pthread_barrier_init(&begin,NULL,2);pthread_barrier_init(&end,NULL,2);
 pthread_t t; assert(!pthread_create(&t,NULL,parker,NULL));
 for(int i=0;i<10000;i++) {
  node.readiness=KD_ORIGIN_READY;
  pthread_barrier_wait(&begin);
  bool claimed=kd_owned_mutex_claim(&node,&sensitive);
  pthread_barrier_wait(&end);
  assert(claimed == (READ_ONCE(node.readiness)==KD_ORIGIN_CLAIMED));
  pthread_barrier_wait(&end);
 }
 pthread_join(t,NULL);
 puts("origin readiness: 10000 exclusive park/claim races, wake-before-ack, same-CPU refusal, timeout and reuse passed");
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix='kd-origin-') as tmp:
        tmp = Path(tmp)
        (tmp / 'test.c').write_text(FIXTURE)
        subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
            '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread',
            '-I', str(ROOT / 'include'), '-I', str(ROOT / 'kernel_module/owned_mutex'),
            str(tmp / 'test.c'), '-o', str(tmp / 'check')], check=True, timeout=30)
        subprocess.run([str(tmp / 'check')], check=True, timeout=30)


if __name__ == '__main__':
    main()
