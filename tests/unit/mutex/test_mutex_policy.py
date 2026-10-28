"""Guest-only bounded-policy checks using the production queue loop.

Ownership/ACK substitutes match the existing terminal fixture; these checks do
not prove real scheduler progress or a performance benefit from a larger cap.
"""
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from source_text import ROOT, read_source, without_includes
from test_mutex_terminal import production_sources

MAIN = r'''#ifdef KD_MUTEX_EXPECT_DEFAULT
_Static_assert(KDLOCK_MUTEX_BATCH==1024 && KDLOCK_MUTEX_NUMA_BOUNDARY==1024,
               "maintained mutex policy defaults differ");
#endif
int main(void)
{
    const unsigned int cap=KDLOCK_MUTEX_BATCH, boundary=KDLOCK_MUTEX_NUMA_BOUNDARY;
    scenario=1;reset(cap+2);
    CHECK(kd_mutex_run_combiner(&lock,&nodes[0],NULL,false)==KD_MUTEX_BATCH_OWNED);
    CHECK(calls==cap && completed==cap && wakes==1 && !nodes[cap].locked);
    CHECK(nodes[cap].next==&nodes[cap+1] && nodes[cap+1].locked && !cas_calls);finish();
    if(boundary>=cap) {
        /* A deferred remote cohort must not cut local service below the cap.
         * It still receives the first physical handoff with links intact. */
        const unsigned int prefixes[]={1,7,8};
        for(unsigned int p=0;p<3;p++) {
            const unsigned int deferred=prefixes[p];
            scenario=5;reset(cap+deferred+2);
            for(unsigned int i=0;i<deferred;i++)nodes[i].numa_node=1;
            CHECK(kd_mutex_run_combiner(&lock,&nodes[0],NULL,false)==KD_MUTEX_BATCH_OWNED);
            CHECK(calls==cap && completed==cap && wakes==1 && !nodes[0].locked);
            for(unsigned int i=0;i<cap;i++)CHECK(order[i]==i+deferred);
            for(unsigned int i=0;i<deferred;i++)CHECK(!nodes[i].completed);
            for(unsigned int i=0;i+1<deferred;i++)CHECK(nodes[i].next==&nodes[i+1]);
            CHECK(nodes[deferred-1].next==&nodes[cap+deferred] && nodes[cap+deferred].locked);finish();
        }
    }
    if(cap<=boundary+64) {
        printf("PASS policy cap=%u boundary=%u: smaller total cap wins, %u checks\n",cap,boundary,checks);
        return 0;
    }
    scenario=2;reset(boundary+10);
    for(unsigned int i=0;i<8;i++)nodes[i].numa_node=1;
    CHECK(kd_mutex_run_combiner(&lock,&nodes[0],NULL,false)==KD_MUTEX_BATCH_OWNED);
    CHECK(calls==boundary && completed==boundary && wakes==1 && !nodes[0].locked);
    for(unsigned int i=0;i<boundary;i++)CHECK(order[i]==i+8);
    for(unsigned int i=0;i<7;i++)CHECK(nodes[i].next==&nodes[i+1] && !nodes[i].completed);
    CHECK(nodes[7].next==&nodes[boundary+8] && nodes[boundary+8].locked);finish();
    scenario=3;reset(cap+2);
    for(unsigned int i=0;i<7;i++)nodes[i].numa_node=1;
    CHECK(kd_mutex_run_combiner(&lock,&nodes[0],NULL,false)==KD_MUTEX_BATCH_OWNED);
    CHECK(calls==cap && completed==cap && wakes==1 && !nodes[cap].locked);
    CHECK(order[boundary-1]==boundary+6 && order[boundary]==0 && order[boundary+6]==6);
    CHECK(order[boundary+7]==boundary+7 && order[cap-1]==cap-1);
    CHECK(nodes[cap].next==&nodes[cap+1] && nodes[cap+1].locked);finish();
    scenario=4;reset(boundary+100);
    for(unsigned int i=0;i<boundary+100;i++)nodes[i].numa_node=1;
    CHECK(kd_mutex_run_combiner(&lock,&nodes[0],NULL,false)==KD_MUTEX_BATCH_OWNED);
    CHECK(calls==boundary && completed==boundary && wakes==1 && !nodes[0].locked);
    for(unsigned int i=0;i<boundary;i++)CHECK(order[i]==i+64);
    CHECK(nodes[63].next==&nodes[boundary+64] && nodes[boundary+64].locked);finish();
    printf("PASS policy cap=%u boundary=%u: %u queue/ownership checks\n",cap,boundary,checks);
}
'''


def main():
    types, helpers, loop = production_sources()
    fixture = (ROOT/'tests/unit/mutex/mutex_terminal_fixture.c').read_text().split('int main(void)', 1)[0]
    fixture = fixture.replace('1030', '(KDLOCK_MUTEX_BATCH+100)')
    fixture = fixture.replace('kd_mutex_batch_size=1024', 'kd_mutex_batch_size=KDLOCK_MUTEX_BATCH') + MAIN
    with tempfile.TemporaryDirectory(prefix='kd-mutex-policy-') as tmp:
        path = Path(tmp)
        for name, text in [('types.h', types), ('helpers.h', helpers), ('loop.h', loop), ('fixture.c', fixture)]:
            (path/name).write_text(text)
        (path/'mutex_state_production.h').write_text(
            without_includes(read_source(ROOT/'include/kd_mutex_state.h')))
        command = shlex.split(os.environ.get('CC', 'cc')) + [
            '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
            '-I'+str(path), '-I'+str(ROOT/'tests/unit/mutex')]
        # No policy override: verify the actual header defaults as well as
        # the same queue/ownership checks used for explicit configurations.
        binary = path/'policy-default'
        subprocess.run(command+['-DKD_MUTEX_EXPECT_DEFAULT', str(path/'fixture.c'),
                                 '-o', str(binary)], check=True, timeout=30)
        subprocess.run([str(binary)], check=True, timeout=10)
        for cap, boundary in ((1, 256), (128, 256), (1024, 256), (4096, 256),
                              (1, 768), (128, 768), (1024, 768), (4096, 768),
                              (1, 1024), (128, 1024), (1024, 1024), (4096, 1024)):
            binary = path/f'policy-{cap}-{boundary}'
            flags = [f'-DKDLOCK_MUTEX_BATCH={cap}', f'-DKDLOCK_MUTEX_NUMA_BOUNDARY={boundary}']
            subprocess.run(command+flags+[str(path/'fixture.c'), '-o', str(binary)], check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=10)
        for cap, boundary in ((0, 256), (32768, 256), (1024, 0), (1024, 32768)):
            rejected = subprocess.run(command+[f'-DKDLOCK_MUTEX_BATCH={cap}',
                f'-DKDLOCK_MUTEX_NUMA_BOUNDARY={boundary}', '-fsyntax-only', str(path/'fixture.c')],
                text=True, capture_output=True, timeout=30)
            assert rejected.returncode != 0 and 'must be 1..' in rejected.stderr


if __name__ == '__main__':
    main()
