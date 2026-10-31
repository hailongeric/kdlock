"""Exercise the actual C writer classifier with captured proc bytes; VM only.

Only proc_text is replaced. No module, live worker or kernel probe is created.
The original writer_contention function decides every acceptance/rejection.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
PROC_STUB = r'''
static const char *fixture_samples[7];
static struct worker *fixture_worker;
static unsigned fixture_reads,fixture_limit;
static int proc_text(uint64_t tid,const char *name,char *buffer,size_t size)
{
    static const char *names[]={"stat","wchan","schedstat","stack","schedstat","wchan","stat"};
    unsigned index=fixture_reads%7;
    CHECK(tid==fixture_worker->observed.tid && !strcmp(name,names[index]));
    CHECK(strlen(fixture_samples[index])<size);
    strcpy(buffer,fixture_samples[index]);
    if(++fixture_reads==7*fixture_limit)
        atomic_store_explicit(&fixture_worker->done,1,memory_order_release);
    return 1;
}
'''
MAIN = r'''
#undef main
int main(int argc,char **argv)
{
    CHECK(argc==10);
    struct worker w={0};
    w.observed.tid=2;w.observed.mm=100;w.observed.mmap_lock=200;
    fixture_worker=&w;fixture_limit=strtoul(argv[2],NULL,10);
    CHECK(fixture_limit && fixture_limit<=8);
    for(unsigned i=0;i<7;i++)fixture_samples[i]=argv[i+3];
    if(!strcmp(argv[1],"kd") || !strcmp(argv[1],"gate") || !strncmp(argv[1],"chain=",6)) {
        chain_waiter=!strcmp(argv[1],"kd") ? "kd_mmap_down_write_killable" :
          !strcmp(argv[1],"gate") ? "kd_mmap_local_lock_slow_signal|kd_mmap_down_write_killable@69:77" : argv[1]+6;
        chain_wait[0]=chain_wait[1]=203;chain_adapter=43;
        chain_acquire="kd_mmap_write_lock_killable";
    } else if(!strcmp(argv[1],"native")) {
        chain_waiter=chain_acquire="kd_mmap_write_lock_killable";
        chain_wait[0]=chain_wait[1]=chain_adapter=60;
    } else CHECK(!strcmp(argv[1],"legacy"));
    int accepted=writer_contention(&w,1,231,136);
    printf("{\"event\":\"fixture_result\",\"accepted\":%s,\"reads\":%u}\n",
           accepted?"true":"false",fixture_reads);
    return 0;
}
'''


class WriterObservation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.geteuid() != 0 or os.uname().release not in (
                '7.0.0-38-kdlock1', '7.0.0-38-kdmm1'):
            raise RuntimeError('C classifier fixture must run in the Linux 7 development VM')
        text = (ROOT/'bench/mmap_writer/client.c').read_text()
        begin = 'static int proc_text('
        end = 'static char task_state('
        if text.count(begin) != 1 or text.count(end) != 1:
            raise RuntimeError('actual proc reader extraction boundary changed')
        start, stop = text.index(begin), text.index(end)
        if stop <= start:
            raise RuntimeError('actual proc reader extraction order changed')
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        directory = Path(cls.temporary.name)
        source = directory/'observation.c'
        source.write_text('#define main original_client_main\n'+text[:start]+PROC_STUB+text[stop:]+MAIN)
        cls.binary = directory/'observation'
        subprocess.run(['gcc','-O2','-Wall','-Wextra','-Werror','-pthread',
                        '-I'+str(ROOT/'workload_modules/mmap_writer'),str(source),'-o',str(cls.binary)],
                       check=True,timeout=30)

    def sample(self, mode='kd', caller='__vm_munmap'):
        offset = {'__vm_munmap':136, 'vm_mmap_pgoff':231}[caller]
        frames = [(caller,offset)]
        if mode in ('kd','native','gate'):
            frames.insert(0,('kd_mmap_write_lock_killable',60 if mode=='native' else 43))
        if mode in ('kd','gate'):
            frames.insert(0,('kd_mmap_down_write_killable',69 if mode=='gate' else 203))
        if mode=='gate':
            frames.insert(0,('kd_mmap_local_lock_slow_signal',203))
        stack = ''.join(f'[<0>] {name}+0x{off:x}/0x200\n' for name,off in frames)
        return ['2 (mw_worker) D 0 0\n',frames[0][0],'100 200 3\n',stack,
                '100 200 3\n',frames[0][0],'2 (mw_worker) D 0 0\n']

    def invoke(self, sample, *, mode='kd', limit=1):
        result = subprocess.run([str(self.binary),mode,str(limit),*sample],
                                check=True,capture_output=True,text=True,timeout=5)
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(rows[-1]['event'],'fixture_result')
        return rows

    def test_exact_native_kd_and_historical_classifier_paths(self):
        for mode in ('native','kd','legacy','gate'):
            for caller in ('vm_mmap_pgoff','__vm_munmap'):
                with self.subTest(mode=mode,caller=caller):
                    sample=self.sample(mode,caller);rows=self.invoke(sample,mode=mode)
                    self.assertTrue(rows[-1]['accepted'])
                    diagnostic=rows[0]
                    self.assertEqual(diagnostic['event'],'stack_observation')
                    self.assertTrue(diagnostic['diagnostic_only'])
                    self.assertTrue(diagnostic['classifier_accepts'])
                    self.assertEqual(diagnostic['rejections'],[])
                    for key,index in (('stat_before',0),('wchan_before',1),('schedstat_before',2),
                                      ('raw_stack',3),('schedstat_after',4),('wchan_after',5),('stat_after',6)):
                        self.assertEqual(diagnostic[key],sample[index])
                    self.assertEqual(rows[1]['event'],'writer_stack')
                    self.assertEqual(rows[1]['caller'],caller)

    def test_gate_intermediate_return_is_required_and_tail_frame_is_absent(self):
        sample=self.sample('gate')
        for offset in ('45','4d'):
            changed=sample.copy();changed[3]=changed[3].replace('+0x45/','+0x'+offset+'/')
            self.assertTrue(self.invoke(changed,mode='gate')[-1]['accepted'])
        for stack in (sample[3].replace('+0x45/','+0x46/'),
                      sample[3].replace('kd_mmap_down_write_killable','other'),
                      ''.join(sample[3].splitlines(keepends=True)[0:1]+sample[3].splitlines(keepends=True)[2:]),
                      sample[3].replace('[<0>] kd_mmap_down_write_killable',
                          '[<0>] kd_mmap_mutex_local_lock_signal+0x1/0x200\n[<0>] kd_mmap_down_write_killable')):
            bad=sample.copy();bad[3]=stack;rows=self.invoke(bad,mode='gate')
            self.assertFalse(rows[-1]['accepted'])
            self.assertIn('intermediate_symbol_or_return',rows[0]['rejections'])
        for suffix in ('|writer@0','|writer@1:2:3','|writer@1:',
                       '|writer@18446744073709551616','|writer@-1','|writer@1x','|writer'):
            rows=self.invoke(sample,mode='chain=kd_mmap_local_lock_slow_signal'+suffix)
            self.assertFalse(rows[-1]['accepted'])
            self.assertIn('intermediate_description',rows[0]['rejections'])

    def test_each_rejected_chain_and_sleep_bracket_stays_rejected(self):
        base=self.sample()
        changes=[(0,'2 (mw_worker) R 0 0\n','state_before'),
                 (6,'2 (mw_worker) R 0 0\n','state_after'),
                 (1,'0','wchan_before'),(5,'0','wchan_after'),
                 (4,'101 200 4\n','schedstat_changed'),
                 (3,'invalid stack\n','first_frame'),
                 (3,base[3].replace('+0xcb/','+0xcc/'),'waiter_symbol_or_return'),
                 (3,base[3].replace('kd_mmap_down_write_killable','other'),'waiter_symbol_or_return'),
                 (3,base[3].replace('+0x2b/','+0x2c/'),'adapter_symbol_or_return'),
                 (3,base[3].replace('kd_mmap_write_lock_killable','other'),'adapter_symbol_or_return'),
                 (3,''.join(base[3].splitlines(keepends=True)[:2]),'caller_frame'),
                 (3,base[3].replace('+0x88/','+0x89/'),'caller_site')]
        for index,value,reason in changes:
            with self.subTest(reason=reason,index=index):
                sample=base.copy();sample[index]=value;rows=self.invoke(sample)
                self.assertFalse(rows[-1]['accepted'])
                self.assertFalse(rows[0]['classifier_accepts'])
                self.assertIn(reason,rows[0]['rejections'])
                self.assertFalse(any(row['event']=='writer_stack' for row in rows))
        sample=base.copy();sample[2]=sample[4]='';rows=self.invoke(sample)
        self.assertFalse(rows[-1]['accepted'])
        self.assertIn('schedstat_empty',rows[0]['rejections'])

    def test_all_bracket_values_and_failures_survive_json_escaping(self):
        sample=self.sample()
        sample[0]='2 (worker "quoted"\\name) R 0 0\n';sample[6]='2 (worker) S 0 0\n'
        sample[1]='0\t';sample[5]='other';sample[2]='';sample[4]='1 2 3\n'
        rows=self.invoke(sample);diagnostic=rows[0]
        self.assertFalse(rows[-1]['accepted'])
        self.assertEqual(set(diagnostic['rejections']),{'state_before','state_after','wchan_before',
                         'wchan_after','schedstat_changed','schedstat_empty'})
        self.assertEqual(diagnostic['stat_before'],sample[0])
        self.assertEqual(diagnostic['wchan_before'],sample[1])

    def test_existing_four_nonempty_records_per_worker_bound(self):
        sample=self.sample();sample[1]='0';rows=self.invoke(sample,limit=8)
        self.assertFalse(rows[-1]['accepted'])
        self.assertEqual(rows[-1]['reads'],56)
        self.assertEqual(sum(row['event']=='stack_observation' for row in rows),4)
        sample[3]='';rows=self.invoke(sample,limit=8)
        self.assertEqual(len(rows),1)
        self.assertFalse(rows[-1]['accepted'])


if __name__=='__main__':
    unittest.main()
