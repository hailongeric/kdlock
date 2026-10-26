'''Guest-only traces of the production two-successor prefetch helpers.

The fixture records hint addresses and acquisition of the published link;
no cache instruction, live kernel queue or timing measurement is performed.
'''
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from source_text import ROOT, read_source
from test_spin_shadow import definition


FIXTURE = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
struct kd_mutex_node {
    struct kd_mutex_node *next;
    unsigned long entry_abi;
    struct { unsigned long sp; } regs;
    unsigned char completed, locked;
};
enum kind { READ_HINT, WRITE_HINT, READ_SP, ACQUIRE_LINK };
struct event { enum kind kind; const void *address; };
static struct event events[32];
static unsigned int count, cursor, acquisitions, checks;
#define CHECK(condition) do { checks++; if (!(condition)) { \
    fprintf(stderr,"FAIL prefetch line=%d: %s\n",__LINE__,#condition);exit(1); \
} } while (0)
static void trace(enum kind kind, const void *address)
{
    CHECK(count < sizeof(events)/sizeof(events[0]));
    if (kind == ACQUIRE_LINK) CHECK(++acquisitions == 1);
    events[count++] = (struct event){kind,address};
}
#define prefetch(p) trace(READ_HINT,(p))
#define prefetchw(p) trace(WRITE_HINT,(p))
#define READ_ONCE(value) ({ trace(READ_SP,&(value)); (value); })
#define smp_load_acquire(p) ({ trace(ACQUIRE_LINK,(p)); *(p); })
#include "helpers.h"
static void expect(enum kind kind, const void *address)
{
    CHECK(cursor < count);
    CHECK(events[cursor].kind == kind && events[cursor].address == address);
    cursor++;
}
static void expect_node(struct kd_mutex_node *node)
{
    expect(READ_HINT,node);
    expect(WRITE_HINT,&node->entry_abi);
    expect(WRITE_HINT,&node->regs);
    expect(READ_SP,&node->regs.sp);
    if (node->regs.sp) {
        expect(WRITE_HINT,(void *)node->regs.sp);
        expect(WRITE_HINT,(void *)(node->regs.sp-sizeof(unsigned long)));
    }
}
static void reset(void) { count=cursor=acquisitions=0; }
int main(void)
{
    unsigned long stack_a[4],stack_b[4];
    struct kd_mutex_node a={0},b={0};
    reset();kd_mutex_prefetch_successor(NULL);CHECK(!count && !acquisitions);
    /* An unpublished successor link is never waited on or dereferenced. */
    a.regs.sp=(unsigned long)&stack_a[2];
    reset();kd_mutex_prefetch_successor(&a);
    expect_node(&a);expect(ACQUIRE_LINK,&a.next);CHECK(cursor==count);
    /* Acquisition precedes every second-node hint. The third link is poison
     * and must not even be loaded: a second acquisition fails before use. */
    a.next=&b;b.next=(void *)1;b.regs.sp=(unsigned long)&stack_b[2];
    struct kd_mutex_node saved_a,saved_b;memcpy(&saved_a,&a,sizeof(a));memcpy(&saved_b,&b,sizeof(b));
    reset();kd_mutex_prefetch_successor(&a);
    expect_node(&a);expect(ACQUIRE_LINK,&a.next);expect_node(&b);
    CHECK(cursor==count && acquisitions==1);
    CHECK(!memcmp(&a,&saved_a,sizeof(a)) && !memcmp(&b,&saved_b,sizeof(b)));
    /* Zero virtual SP suppresses stack hints but retains header/packet hints. */
    a.regs.sp=b.regs.sp=0;
    reset();kd_mutex_prefetch_successor(&a);
    expect_node(&a);expect(ACQUIRE_LINK,&a.next);expect_node(&b);
    CHECK(cursor==count && acquisitions==1);
    printf("PASS successor prefetch: %u checks; first hints, acquire-linked second, no third or notification hints\n",checks);
}
'''


def main():
    source = read_source(ROOT/'kernel_module/kd_mutex.c')
    helpers = ''.join(definition(source, marker)+'\n' for marker in (
        'static void kd_mutex_prefetch_node(struct kd_mutex_node *next)',
        'static void kd_mutex_prefetch_successor(struct kd_mutex_node *next)'))
    second = 'kd_mutex_prefetch_node(smp_load_acquire(&next->next));'
    assert helpers.count(second) == 1
    candidates = {
        'production': helpers,
        'missing-second-hint': helpers.replace(second, '(void)smp_load_acquire(&next->next);'),
        'unordered-second-link': helpers.replace(second, 'kd_mutex_prefetch_node(READ_ONCE(next->next));'),
        'notification-hint': helpers.replace('prefetch(next);', 'prefetch(next); prefetchw(&next->locked);'),
        'third-link': helpers.replace(second, '{ '+second+' if (next->next) kd_mutex_prefetch_node(smp_load_acquire(&next->next->next)); }'),
    }
    with tempfile.TemporaryDirectory(prefix='kd-mutex-prefetch-') as temporary:
        path=Path(temporary)
        (path/'fixture.c').write_text(FIXTURE)
        for name, text in candidates.items():
            (path/'helpers.h').write_text(text)
            binary=path/name
            subprocess.run(shlex.split(os.environ.get('CC','cc'))+[
                '-std=gnu11','-O2','-Wall','-Wextra','-Werror','-I'+str(path),
                str(path/'fixture.c'),'-o',str(binary)],check=True,timeout=30)
            result=subprocess.run([str(binary)],text=True,capture_output=True,timeout=10)
            if name=='production':
                assert result.returncode==0,(result.stdout,result.stderr)
                print(result.stdout,end='')
            else:
                assert result.returncode==1 and 'FAIL prefetch' in result.stderr,(name,result.returncode,result.stdout,result.stderr)
                print('prefetch mutation detected:',name)


if __name__=='__main__':
    main()
