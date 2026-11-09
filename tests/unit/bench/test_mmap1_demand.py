"""Demand image provenance, learning and activation components (VM only)."""
import copy
import importlib.util
from pathlib import Path
import shlex
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('demand_bench', ROOT / 'bench/mmap1/run.py')
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
images = bench.execution
point_spec = importlib.util.spec_from_file_location('demand_point', ROOT / 'bench/mmap1/delegated_point.py')
point = importlib.util.module_from_spec(point_spec)
point_spec.loader.exec_module(point)


def row(entry=0x100, tgid=99, generation=1, code=0x1000, status=0):
    return dict(pid=0, entry=entry, tgid=tgid, generation=generation, code=code,
                status=status, requirements=8320, entry_abi=2, lock_kind=2)


class DemandRegistry(unittest.TestCase):
    def test_optional_syscall_argument_contract_is_explicit_and_versioned(self):
        setting, version = images.SYSCALL_SHAPE_PARAMETERS
        self.assertIsNone(images.syscall_shape_contract({}, False))
        self.assertEqual(images.syscall_shape_contract({setting: 'N', version: '1'}, False),
                         dict(version=1, enabled=False))
        self.assertEqual(images.syscall_shape_contract({setting: 'Y', version: '1'}, True),
                         dict(version=1, enabled=True))
        for parameters, enabled in (({}, True), ({version: '1'}, False),
                ({setting: 'Y'}, True), ({setting: 'Y', version: '2'}, True),
                ({setting: 'N', version: '1'}, True), ({setting: 'Y', version: '1'}, False),
                ({setting: 'Y', version: '1'}, 1)):
            with self.subTest(parameters=parameters, enabled=enabled), self.assertRaises(bench.rt.Failure):
                images.syscall_shape_contract(parameters, enabled)

    def test_learning_allowance_remains_bounded(self):
        self.assertEqual(point.learning_limits({}), (900, 3))
        for rounds in (1, 8, 9, 32, 33, 64):
            self.assertEqual(point.learning_limits(dict(learning_rounds=rounds,
                learning_timeout=1800)), (1800, rounds))
        for values in (dict(learning_rounds=0), dict(learning_rounds=65),
                       dict(learning_rounds=True), dict(learning_timeout=0),
                       dict(learning_timeout=3601), dict(learning_timeout=True)):
            with self.subTest(values=values), self.assertRaises(AssertionError):
                point.learning_limits(values)

    def test_scoring_requires_every_selected_image_ready(self):
        entries = [0x100, 0x200]
        ready = [row(), row(entry=0x200)]
        images.ready_writer_entries(ready, entries)
        images.ready_writer_entries([], [])
        for values in ([], ready[:1], [ready[0], row(entry=0x200, status=-3)],
                       [ready[0], row(entry=0x200, generation=0, code=0)],
                       [ready[0], row(entry=0x300)]):
            with self.subTest(values=values), self.assertRaises(bench.rt.Failure):
                images.ready_writer_entries(values, entries)

    def test_writer_scope_and_parameter_identity(self):
        self.assertEqual(images.selected_writer_entries([], {0x100, 0x200}), {0x100, 0x200})
        self.assertEqual(images.selected_writer_entries([0x100], {0x100, 0x200}), {0x100})
        self.assertEqual(images.parse_writer_entries('256,0x200\n'), [0x100, 0x200])
        self.assertEqual(images.parse_writer_entries('\n'), [])
        for values in ([0], [True], [0x100, 0x100], [0x300], [1 << 64], None):
            with self.subTest(values=values), self.assertRaises(bench.rt.Failure):
                images.selected_writer_entries(values, {0x100, 0x200})
        with self.assertRaises(bench.rt.Failure):
            images.parse_writer_entries(None)
        with self.assertRaises(bench.rt.Failure):
            images.parse_writer_entries('256,invalid')
        with self.assertRaises(bench.rt.Failure):
            images.demand_registry([row(entry=0x200)],
                images.selected_writer_entries([0x100], {0x100, 0x200}))

    def test_first_registrar_is_metadata(self):
        values = [row(), row(entry=0x200, tgid=1234)]
        self.assertEqual(len(images.demand_registry(values, {0x100, 0x200})), 2)
        self.assertEqual(images.demand_registry([], {0x100}), [])

    def test_entry_identity_and_publication_controls(self):
        for mutation in (dict(pid=1), dict(tgid=0), dict(entry=0x300),
                         dict(entry_abi=1), dict(lock_kind=1), dict(generation=0)):
            value = row()
            value.update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(bench.rt.Failure):
                images.demand_registry([value], {0x100})
        with self.assertRaises(bench.rt.Failure):
            images.demand_registry([row(), row(tgid=100)], {0x100})

    def test_misses_are_learning_without_a_new_generation(self):
        for status in (1, 2, 3, 4):
            before, after = row(), row(status=status)
            self.assertTrue(images.demand_transition([before], [after], {0x100}))
            images.demand_registry([after], {0x100}, settled=False)
            with self.assertRaises(bench.rt.Failure):
                images.demand_registry([after], {0x100})

    def test_new_generation_and_new_entry_are_learning(self):
        self.assertTrue(images.demand_transition([row()], [row(generation=2, code=0x2000),
            row(entry=0x200, tgid=101, generation=0, code=0, status=-1)], {0x100, 0x200}))
        for mutation in (dict(tgid=100), dict(generation=0, code=0, status=-1),
                         dict(code=0x2000), dict(requirements=0)):
            after = row()
            after.update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(bench.rt.Failure):
                images.demand_transition([row()], [after], {0x100})
        with self.assertRaises(bench.rt.Failure):
            images.demand_transition([row()], [], {0x100})

    def test_native_only_preserves_residency_and_is_terminal(self):
        for value in (row(status=-3), row(status=-3, generation=0, code=0)):
            images.demand_registry([value], {0x100})
            self.assertFalse(images.demand_transition([value], [copy.deepcopy(value)], {0x100}))
            with self.assertRaises(bench.rt.Failure):
                images.demand_transition([value], [row(generation=2, code=0x2000)], {0x100})
        self.assertTrue(images.demand_transition([row()], [row(status=-3)], {0x100}))


def function(source, name, result='int'):
    start = source.index(result + ' ' + name + '(')
    opening = source.index('{', start)
    depth = 0
    for index in range(opening, len(source)):
        depth += (source[index] == '{') - (source[index] == '}')
        if depth == 0:
            return source[start:index + 1]
    raise AssertionError('incomplete production function')


class DemandActivation(unittest.TestCase):
    def test_selection_requires_compiled_mm_support(self):
        source = (ROOT / 'kernel_module/kd_rwsem_provider.c').read_text()
        program = r'''
#include <stdbool.h>
#include <errno.h>
#define WRITE_ONCE(x,v) ((x)=(v))
static bool kd_rwsem_provider_initialized, kd_rwsem_provider_syscall_shape;
static unsigned int kd_rwsem_provider_entry_count;
'''
        program += function(source, 'kd_rwsem_provider_init')
        program += r'''
int main(void)
{
    kd_rwsem_provider_syscall_shape=true;
    if (kd_rwsem_provider_init()!=-EOPNOTSUPP || kd_rwsem_provider_initialized) return 1;
    kd_rwsem_provider_syscall_shape=false; kd_rwsem_provider_entry_count=1;
    if (kd_rwsem_provider_init()!=-EOPNOTSUPP || kd_rwsem_provider_initialized) return 2;
    kd_rwsem_provider_entry_count=0;
    return kd_rwsem_provider_init() || !kd_rwsem_provider_initialized;
}
'''
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            path, binary = directory / 'configuration.c', directory / 'configuration'
            path.write_text(program)
            built = subprocess.run(shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', str(path), '-o', str(binary)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            ran = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)

    def test_production_prepare_and_activate_with_supplied_primitives(self):
        source = (ROOT / 'kernel_module/kd_rwsem_provider.c').read_text()
        program = r'''
#include <stdbool.h>
#include <stdio.h>
#include <errno.h>
#include <string.h>
#define CONFIG_KDLOCK_MMAP 1
#define KD_RWSEM_OP_DOWN_WRITE 1
#define KD_RWSEM_OP_DOWN_WRITE_KILLABLE 3
#define KD_EXE_LOCK_MUTEX 2
#define KD_ENTRY_ABI_MUTEX_CLOBBER_V1 2
#define KD_EXE_UNUSED -2
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
struct kd_rwsem_site { unsigned long entry; unsigned int operation, reserved; };
struct kd_exe_info { unsigned long RIP; int status_code, entry_abi, lock_kind; };
static struct kd_rwsem_site sites[3];
static struct kd_exe_info entries[3];
static bool ready[3], kd_rwsem_provider_initialized, kd_rwsem_provider_registered;
static bool kd_rwsem_provider_syscall_shape;
static bool kd_rwsem_provider_demand, source_open, binding;
static unsigned long kd_rwsem_provider_entries[64];
static unsigned int kd_rwsem_provider_entry_count;
static int kd_rwsem_provider_state_lock, kd_rwsem_ops, cpus, adds, gets, binding_puts, registration;
static unsigned int site_count;
static void mutex_lock(int *p) { (void)p; }
static void mutex_unlock(int *p) { (void)p; }
static bool kd_source_is_open(void) { return source_open; }
static int num_online_cpus(void) { return cpus; }
static const struct kd_rwsem_site *kd_rwsem_provider_sites(unsigned int *n)
{ *n=site_count; return sites; }
static int index_of(unsigned long ip)
{ for (int i=0;i<3;i++) if (sites[i].entry==ip) return i; return -1; }
static void kd_exe_add_abi(int pid,unsigned long ip,int kind,int abi)
{ (void)pid; int i=index_of(ip); ++adds; entries[i]=(struct kd_exe_info){ip,-1,abi,kind}; }
static struct kd_exe_info *kd_get_exe(int pid,unsigned long ip)
{ (void)pid; int i=index_of(ip); return i>=0 ? &entries[i] : NULL; }
static void *kd_exe_capture_image(struct kd_exe_info *e,unsigned long ip)
{ int i=index_of(ip); return e && i>=0 && ready[i] ? e : NULL; }
static bool kd_source_binding_get(void) { ++gets; return binding; }
static void kd_source_binding_put(void) { ++binding_puts; }
static int kd_rwsem_register_provider(int *p) { (void)p; return registration; }
static void reset(bool demand)
{
    kd_rwsem_provider_initialized=source_open=binding=true;
    kd_rwsem_provider_registered=false; kd_rwsem_provider_demand=demand;
    kd_rwsem_provider_syscall_shape=false;
    cpus=2; adds=gets=binding_puts=registration=0; site_count=3;
    kd_rwsem_provider_entry_count=0;
    memset(ready,0,sizeof(ready)); memset(entries,0,sizeof(entries));
    for (int i=0;i<3;i++) sites[i]=(struct kd_rwsem_site){0x100UL+i, i==1?3:1, 0};
}
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"line %d\n",__LINE__); return 1; } } while(0)
'''
        program += '\n' + function(source, 'kd_rwsem_entry_selected', 'bool')
        program += '\n' + function(source, 'kd_rwsem_entry_scope_valid')
        program += '\n' + function(source, 'kd_rwsem_provider_prepare_entries')
        program += '\n' + function(source, 'kd_rwsem_provider_activate')
        program += r'''
#define TASK_UNINTERRUPTIBLE 1
#define TASK_INTERRUPTIBLE 2
#define TASK_KILLABLE 3
#define KD_ADMISSION_RWSEM_WRITE 2
#define __NR_mmap 9
#define __NR_munmap 11
#define PROT_READ 1
#define PROT_WRITE 2
#define MAP_PRIVATE 2
#define MAP_ANONYMOUS 32
#define PAGE_SIZE 4096UL
#define PF_KTHREAD 1UL
struct pt_regs { unsigned long args[6]; long number; bool user, native64; };
struct fixture_task { void *mm; unsigned long flags; };
static struct fixture_task fixture_task, *current=&fixture_task;
static struct pt_regs saved_registers;
static bool fixture_compat;
static struct pt_regs *task_pt_regs(struct fixture_task *task)
{ (void)task; return &saved_registers; }
static bool in_compat_syscall(void) { return fixture_compat; }
static bool user_64bit_mode(struct pt_regs *regs) { return regs->user && regs->native64; }
static long syscall_get_nr(struct fixture_task *task, struct pt_regs *regs)
{ (void)task; return regs->number; }
static void syscall_get_arguments(struct fixture_task *task,struct pt_regs *regs,unsigned long *args)
{ (void)task; memcpy(args,regs->args,sizeof(regs->args)); }
static int kd_provider_completion, capture_calls, local_calls[3], local_result;
static bool held;
static void kd_provider_down_write(void *object)
{ (void)object; ++local_calls[0]; held=true; }
static int kd_provider_down_write_interruptible(void *object)
{ (void)object; ++local_calls[1]; held=!local_result; return local_result; }
static int kd_provider_down_write_killable(void *object)
{ (void)object; ++local_calls[2]; held=!local_result; return local_result; }
static int kd_service_capture_bound(void *object,int kind,unsigned int state,
    unsigned long sp,unsigned long ip,unsigned long bp,const int *completion)
{
    (void)object; (void)kind; (void)state; (void)sp; (void)ip; (void)bp;
    (void)completion; ++capture_calls; return 77;
}
'''
        program += '\n' + function(source, 'kd_rwsem_syscall_shape_matches', 'bool')
        program += '\n' + function(source, 'kd_rwsem_capture_shape_selected', 'bool')
        program += '\n' + function(source, 'kd_provider_capture')
        program += r'''
int main(void)
{
    reset(false); CHECK(!kd_rwsem_provider_prepare_entries() && adds==3);
    CHECK(kd_rwsem_provider_activate()==-EAGAIN && gets==0);
    for (int i=0;i<3;i++) ready[i]=true;
    CHECK(!kd_rwsem_provider_activate() && gets==1 && kd_rwsem_provider_registered);
    reset(true); CHECK(!kd_rwsem_provider_prepare_entries() && adds==0);
    CHECK(!kd_rwsem_provider_activate() && gets==1 && kd_rwsem_provider_registered);
    reset(true); sites[1].reserved=1;
    CHECK(kd_rwsem_provider_prepare_entries()==-EINVAL && adds==0);
    CHECK(kd_rwsem_provider_activate()==-EINVAL && gets==0);
    reset(true); source_open=false;
    CHECK(kd_rwsem_provider_prepare_entries()==-ESHUTDOWN);
    CHECK(kd_rwsem_provider_activate()==-ESHUTDOWN);
    reset(true); site_count=0; CHECK(kd_rwsem_provider_activate()==-ENOENT);
    reset(true); cpus=1; CHECK(kd_rwsem_provider_activate()==-EOPNOTSUPP);
    reset(false); CHECK(kd_rwsem_entry_selected(0x999));
    CHECK(!kd_rwsem_entry_scope_valid(sites,site_count));
    CHECK(kd_provider_capture(&held,TASK_UNINTERRUPTIBLE,8,0x999,16)==77);
    CHECK(capture_calls==1 && !held && !local_calls[0]);
    reset(false); kd_rwsem_provider_entry_count=2;
    kd_rwsem_provider_entries[0]=0x100; kd_rwsem_provider_entries[1]=0x102;
    CHECK(!kd_rwsem_entry_scope_valid(sites,site_count));
    CHECK(kd_rwsem_entry_selected(0x100) && !kd_rwsem_entry_selected(0x101));
    CHECK(!kd_rwsem_provider_prepare_entries() && adds==2);
    ready[0]=ready[2]=true;
    CHECK(!kd_rwsem_provider_activate() && gets==1);
    CHECK(kd_provider_capture(&held,TASK_KILLABLE,8,0x100,16)==77 && capture_calls==2);
    CHECK(!kd_provider_capture(&held,TASK_UNINTERRUPTIBLE,8,0x101,16));
    CHECK(held && local_calls[0]==1 && capture_calls==2);
    held=false;
    CHECK(!kd_provider_capture(&held,TASK_KILLABLE,8,0x101,16));
    CHECK(held && local_calls[2]==1 && capture_calls==2);
    held=false; local_result=-EINTR;
    CHECK(kd_provider_capture(&held,TASK_KILLABLE,8,0x101,16)==-EINTR);
    CHECK(!held && local_calls[2]==2 && capture_calls==2);
    CHECK(kd_provider_capture(&held,TASK_INTERRUPTIBLE,8,0x101,16)==-EINTR);
    CHECK(!held && local_calls[1]==1 && capture_calls==2);
    local_result=0;
    CHECK(!kd_provider_capture(&held,TASK_INTERRUPTIBLE,8,0x101,16));
    CHECK(held && local_calls[1]==2 && capture_calls==2);
    kd_rwsem_provider_entries[1]=0x100;
    CHECK(kd_rwsem_entry_scope_valid(sites,site_count)==-EINVAL);
    kd_rwsem_provider_entries[1]=0;
    CHECK(kd_rwsem_entry_scope_valid(sites,site_count)==-EINVAL);
    kd_rwsem_provider_entries[1]=0x999;
    CHECK(kd_rwsem_entry_scope_valid(sites,site_count)==-EINVAL);
    kd_rwsem_provider_entries[1]=0x102; sites[2].reserved=1;
    CHECK(kd_rwsem_entry_scope_valid(sites,site_count)==-EINVAL);
    sites[2].reserved=0; sites[2].operation=2;
    CHECK(kd_rwsem_entry_scope_valid(sites,site_count)==-EINVAL);
    reset(true); binding=false; CHECK(kd_rwsem_provider_activate()==-ESHUTDOWN);
    reset(true); registration=-EBUSY;
    CHECK(kd_rwsem_provider_activate()==-EBUSY && gets==1 && binding_puts==1 && !kd_rwsem_provider_registered);
    reset(true); kd_rwsem_provider_syscall_shape=true;
    CHECK(kd_rwsem_entry_scope_valid(sites,site_count)==-EINVAL);
    kd_rwsem_provider_entry_count=1; kd_rwsem_provider_entries[0]=0x100;
    CHECK(!kd_rwsem_entry_scope_valid(sites,site_count));
    kd_rwsem_provider_demand=false;
    CHECK(kd_rwsem_entry_scope_valid(sites,site_count)==-EINVAL);
    kd_rwsem_provider_demand=true;
    fixture_task.mm=&held; fixture_task.flags=0;
    saved_registers=(struct pt_regs){.number=9,.user=true,.native64=true,.args={0,128UL*1024*1024,3,34,~0UL,0}};
    CHECK(kd_rwsem_capture_shape_selected());
    saved_registers.args[4]=0xffffffffUL; CHECK(kd_rwsem_capture_shape_selected());
    for (int i=0;i<6;i++) {
        unsigned long previous=saved_registers.args[i]; saved_registers.args[i]=i==4?0:previous+1;
        CHECK(!kd_rwsem_capture_shape_selected()); saved_registers.args[i]=previous;
    }
    saved_registers.number=9|0x40000000; CHECK(!kd_rwsem_capture_shape_selected());
    saved_registers.number=-1; CHECK(!kd_rwsem_capture_shape_selected());
    saved_registers.number=9; fixture_compat=true; CHECK(!kd_rwsem_capture_shape_selected());
    fixture_compat=false; saved_registers.user=false; CHECK(!kd_rwsem_capture_shape_selected());
    saved_registers.user=true; saved_registers.native64=false; CHECK(!kd_rwsem_capture_shape_selected());
    saved_registers.native64=true;
    saved_registers.user=true; fixture_task.flags=PF_KTHREAD; CHECK(!kd_rwsem_capture_shape_selected());
    fixture_task.flags=0; fixture_task.mm=NULL; CHECK(!kd_rwsem_capture_shape_selected());
    fixture_task.mm=&held;
    saved_registers.number=11; saved_registers.args[0]=0x1000;
    CHECK(kd_rwsem_capture_shape_selected());
    saved_registers.args[0]=0; CHECK(!kd_rwsem_capture_shape_selected());
    saved_registers.args[0]=0x1001; CHECK(!kd_rwsem_capture_shape_selected());
    saved_registers.args[0]=0x1000; saved_registers.args[1]/=2;
    CHECK(!kd_rwsem_capture_shape_selected());
    capture_calls=0; memset(local_calls,0,sizeof(local_calls)); held=false;
    local_result=-EINTR;
    CHECK(kd_provider_capture(&held,TASK_KILLABLE,8,0x100,16)==-EINTR);
    CHECK(!held && local_calls[2]==1 && capture_calls==0);
    CHECK(kd_provider_capture(&held,TASK_INTERRUPTIBLE,8,0x100,16)==-EINTR);
    CHECK(!held && local_calls[1]==1 && capture_calls==0);
    local_result=0;
    CHECK(!kd_provider_capture(&held,TASK_KILLABLE,8,0x100,16) && held && local_calls[2]==2);
    held=false; CHECK(!kd_provider_capture(&held,TASK_UNINTERRUPTIBLE,8,0x100,16));
    CHECK(held && local_calls[0]==1 && capture_calls==0);
    saved_registers.args[1]*=2;
    CHECK(kd_provider_capture(&held,TASK_KILLABLE,8,0x100,16)==77 && capture_calls==1);
    kd_rwsem_provider_syscall_shape=false; fixture_task.mm=NULL; fixture_compat=true;
    saved_registers.user=false; saved_registers.number=-1;
    CHECK(kd_rwsem_capture_shape_selected());
    CHECK(kd_provider_capture(&held,TASK_KILLABLE,8,0x100,16)==77 && capture_calls==2);
    puts("demand/default activation component checks passed");
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            path, binary = directory / 'activation.c', directory / 'activation'
            path.write_text(program)
            argv = shlex.split(os.environ.get('CC', 'cc')) + [
                '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', str(path), '-o', str(binary)]
            built = subprocess.run(argv, capture_output=True, text=True, timeout=30)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            ran = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)


if __name__ == '__main__':
    unittest.main()
