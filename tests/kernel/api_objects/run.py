#!/usr/bin/env python3
"""Actual syscall participants of scoped file-table/pipe objects; no timing score."""
import argparse
import errno
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SPEC = importlib.util.spec_from_file_location('kernel_api_semantic_support', ROOT/'bench/kernel_api/run.py')
api = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(api)
rt, platform, identity = api.rt, api.platform, api.identity
CASES = {
    'setfd': ('binding', 'flags_and_duplicates', 'concurrent_participants', 'fork_copy', 'unshare_release'),
    'pipe': ('mixed_io', 'resize', 'error_recovery', 'reader_wake', 'writer_wake',
             'endpoint_release', 'selector_errors', 'selector_lifetime'),
}
PIPE_FIELDS = {
    'mixed_io': dict(workers_started=7,workers_joined=7,records_written=512,records_read=512,
                     bytes=32768,byte_queries=1024,capacity_queries=1024),
    'resize': dict(workers_started=3,workers_joined=3,resizes=32,capacity_queries=512,
                   occupied_shrink_errno=errno.EBUSY,preserved_bytes=8192),
    'error_recovery': dict(fault_errno=errno.EFAULT,unsupported_errno=errno.ENOTTY,
                           recovery_queries=4,preserved_bytes=64),
    'reader_wake': dict(workers_started=1,workers_joined=1,observed_syscall=0,
                        syscall_state_syscall_bracket=True,completed_bytes=64),
    'writer_wake': dict(workers_started=1,workers_joined=1,observed_syscall=1,
                        syscall_state_syscall_bracket=True,completed_bytes=4096),
    'endpoint_release': dict(buffered_bytes_before_eof=64,eof_returns=1,epipe_errno=errno.EPIPE,sigpipe_consumed=1),
    'selector_errors': dict(invalid_selects=4,busy_selects=2,invalid_queries=4,cancels=2,
                            setup_only_kd_selector=True,recovery_bytes=64),
    'selector_lifetime': dict(objects_created=5,objects_closed=5,token_final_release_checked=True),
}


def check_binding(row, arm, kind, entries):
    backend = int(arm == 'kd')
    rt.require(row.get('version') == 1 and row.get('kind') == kind and row.get('backend') == backend and
               type(row.get('object')) is int and row['object'] > 0 and
               type(row.get('lock')) is int and row['lock'] > 0 and
               type(row.get('provider')) is int and bool(row['provider']) == bool(backend) and
               row.get('entries') == entries, 'actual object binding differs')


def validate_lines(rows, kind, arm, pid, entries):
    rt.require(len(rows) == len(CASES[kind])+2, 'missing or extra semantic receipts')
    ready, done = rows[0], rows[-1]
    backend = int(arm == 'kd')
    rt.require(ready.get('ready') is True and ready.get('pid') == pid and ready.get('backend') == backend,
               'client setup identity differs')
    if kind == 'setfd':
        binding = {k:ready.get(k) for k in ('version','kind','backend','object','lock','provider','entries')}
    else:
        binding = ready.get('binding', {})
    check_binding(binding, arm, 1 if kind == 'setfd' else 2, entries)
    rt.require(done.get('done') is True and done.get('passed') is True and done.get('joined') is True and
               done.get('cases') == len(CASES[kind]) and done.get('backend') == backend and
               done.get('control_closed') is True, 'final joined receipt missing')
    for row, name in zip(rows[1:-1], CASES[kind]):
        rt.require(row.get('case') == name and row.get('passed') is True and row.get('joined') is True and
                   row.get('backend') == backend, 'semantic case order, backend or completion differs')
        if kind == 'setfd':
            if name == 'unshare_release':
                rt.require(row.get('old_object') == binding['object'] and
                           row.get('new_object') not in (None, 0, binding['object']) and row.get('new_backend') == 0,
                           'files replacement/lifetime receipt differs')
            else:
                rt.require(all(row.get(k) == binding[k] for k in ('object','lock','provider')),
                           'setfd participants used another files object')
                expected = {'binding':1,'flags_and_duplicates':6,'concurrent_participants':18432,'fork_copy':1}[name]
                rt.require(row.get('operations') == expected, 'setfd completion conservation differs')
        else:
            rt.require(all(row.get(key) == value and type(row[key]) is type(value)
                           for key,value in PIPE_FIELDS[name].items()), 'pipe case data/conservation differs')
            names = ('eof_binding','epipe_binding') if name == 'endpoint_release' else (
                ('first_binding','second_binding','cancelled_binding','duplicate_token_binding','last_close_binding')
                if name == 'selector_lifetime' else ('binding',))
            for key in names:
                selected = arm if key in ('binding','eof_binding','epipe_binding','first_binding','duplicate_token_binding') else 'native'
                check_binding(row.get(key, {}), selected, 2, entries)
                rt.require(row[key]['provider'] == (binding['provider'] if selected == 'kd' else 0),
                           'pipe objects used another provider')
            if name == 'mixed_io':
                rt.require(row['binding'] == binding, 'mixed I/O used a different initial pipe')
            if 'workers_started' in row:
                rt.require(row['workers_started'] == row.get('workers_joined') and row['workers_started'] > 0,
                           'pipe worker join conservation differs')
            if name in ('reader_wake','writer_wake'):
                rt.require(type(row.get('sleeping_tid')) is int and row['sleeping_tid'] > 0,
                           'blocked syscall observation missing')
            if name == 'selector_lifetime':
                rt.require(row.get('selected_budget') == backend and
                           row['first_binding']['object'] != row['second_binding']['object'],
                           'one-shot selector lifetime differs')
    return dict(binding=binding, cases=list(CASES[kind]), joined=True)


def build(out, args):
    binaries, files = api.build(out, args)
    hashes = json.loads((out/'source-sha256.json').read_text())
    for path in sorted(HERE.rglob('*')):
        if not path.is_file() or path.suffix not in ('.py','.c','.h','.md'):
            continue
        relative = path.relative_to(ROOT)
        target = out/'source'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        expected = rt.digest(path)
        shutil.copyfile(path, target)
        rt.require(rt.digest(target) == expected, 'semantic source copy differs')
        hashes[str(relative)] = expected
        files[str(path)] = files[str(target)] = expected
    for kind in CASES:
        source = out/'source'/HERE.relative_to(ROOT)/'fixture'/(kind+'_client.c')
        binary = out/'build'/(kind+'-client')
        rt.command(['gcc','-O2','-g','-Wall','-Wextra','-Werror','-std=gnu11','-pthread',source,'-o',binary],
                   out/('build-'+kind+'.log'), timeout=60)
        binaries[kind+'_client'] = binary
        files[str(binary)] = rt.digest(binary)
    rt.write_json(out/'source-sha256.json', hashes)
    rt.write_json(out/'semantic-binaries.json', {k:dict(path=str(v),sha256=rt.digest(v)) for k,v in binaries.items()})
    api.verify_files(files)
    return binaries, files


class ObjectSession(api.BoundSession):
    def prepare(self):
        self.verify()
        self.run(['insmod',self.binaries['guard']], 'load-guard.log')
        self.run(['rmmod','tc_allocator_guard'], 'unload-guard.log')
        self.run(['insmod',self.binaries['provider'],'api_bind=1','bench_quiet=1','bench_complete_probe=0',
                  'hotlock_stats=0','jit_timing=0','target_process=sc_worker'], 'load-provider.log')
        self.loaded_kd = True
        self.record['api_bind'] = (api.PARAM/'api_bind').read_text().strip()
        rt.require(self.record['api_bind'] == 'Y', 'explicit API binding is not enabled')
        self.save()
        self.start_daemon()
        until = time.monotonic()+120
        while True:
            self.faults()
            rt.require(self.daemon.poll() is None, 'translator exited')
            text = (self.path/'daemon.log').read_text()
            rt.require(not re.search(r'\[KD_JIT\]\[ERROR\]|Traceback|command failed', text), 'translation failed')
            rows = rt.registry()
            if len(rows) == 3 and all(row['status'] == 0 and row['code'] and row['pid'] == 0 for row in rows) and not rt.children(self.daemon.pid):
                break
            rt.require(time.monotonic() < until, 'publication deadline expired')
            time.sleep(.05)
        rt.require(sorted((row['lock_kind'],row['entry_abi']) for row in rows) == [(1,1),(2,2),(2,2)],
                   'source entry class/ABI differs')
        self.stop_daemon()
        rt.require(rt.status()['frames'] == rt.status()['writers'] == 0, 'preparation did not drain')
        images = sorted((self.path/'workspace').rglob('jit.bin'))
        rt.require(len(images) == 3, 'emitted image set differs')
        self.record['publication'] = dict(registry=rows, images={str(p):rt.digest(p) for p in images})
        self.record['parameters'] = rt.parameters()
        rt.require(self.record['parameters']['bench_lock_addr'] == '0' and
                   self.record['parameters']['bench_complete_probe'] == 'N', 'semantic observation mode differs')
        self.record['execution_evidence'] = 'published images; returned JIT execution is not observed by this semantic test'
        self.verify()
        self.save()

    def exercise(self):
        command = [str(self.binaries[self.record['kind']+'_client']), self.record['arm']]
        self.client_log = (self.path/'client.stderr').open('w')
        self.client = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=self.client_log,
                                       start_new_session=True, text=True)
        self.record.update(client_pid=self.client.pid, client_command=command, execution_status='RUNNING')
        self.save()
        try:
            output, _ = self.client.communicate(timeout=90)
        except subprocess.TimeoutExpired as error:
            if error.output:
                data = error.output.decode() if isinstance(error.output, bytes) else error.output
                (self.path/'client.partial.jsonl').write_text(data)
            raise rt.Failure('UNDRAINED','semantic client did not exit; retain provider',unsafe=True) from error
        (self.path/'client.jsonl').write_text(output)
        self.faults()
        rt.require(self.client.returncode == 0, 'semantic client failed')
        rows = [json.loads(line) for line in output.splitlines()]
        # The site array order is fixed (setfd, FIONREAD, F_GETPIPE_SZ), while
        # registry allocation order need not be. Bind all three exact addresses.
        entries = rows[0].get('binding', rows[0]).get('entries', []) if rows else []
        rt.require(len(entries) == 3 and len(set(entries)) == 3 and
                   set(entries) == {row['entry'] for row in self.record['publication']['registry']},
                   'client queried a different selected entry set')
        self.record['semantic'] = validate_lines(rows,self.record['kind'],self.record['arm'],self.client.pid,entries)
        self.record['receipts'] = rows
        self.record['client_exit'] = self.client.returncode
        self.client_log.close()
        self.client = None
        rt.require(rt.registry() == self.record['publication']['registry'], 'published image metadata changed')
        api.verify_files(self.record['publication']['images'])
        self.verify()
        self.save()

    def cleanup(self):
        # BoundSession's exact source retire/refcount drain remains shared.
        # Its client handshake is already finished by a verified normal exit.
        self.faults()
        until = time.monotonic()+10
        while int(Path('/sys/module/kdlock_km/refcnt').read_text()) != 0:
            rt.require(time.monotonic() < until, 'object/device references remain', 'UNDRAINED')
            time.sleep(.01)
        rt.require(rt.status()['frames'] == rt.status()['writers'] == 0, 'frames/writers remain', 'UNDRAINED')
        import fcntl
        fd = os.open('/dev/kd_dev', os.O_RDONLY | os.O_CLOEXEC)
        try:
            fcntl.ioctl(fd, rt.RETIRE)
            self.record['retired'] = rt.info(fd)
        finally:
            os.close(fd)
        rt.require(self.record['retired'] == dict(state=2,modules=0,frames=0,writers=0), 'retirement incomplete')
        self.run(['rmmod','kdlock_km'], 'unload-provider.log')
        self.loaded_kd = False
        self.faults()
        self.record.update(passed=True,drained=True,execution_status='COMPLETE')
        self.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--host-state',type=Path,required=True)
    platform.arguments(parser)
    identity.arguments(parser)
    parser.set_defaults(kernel_variant='kdscope1-native',
        kernel_source=Path('/mnt/kdlock-builds/linux-7.0.0-38-kdscope1/build'),
        kernel_baseline=Path('/root/kdlock-kernel-baselines/linux70-kdscope1-native-20261030'))
    args = parser.parse_args()
    rt.require(args.kernel_variant == 'kdscope1-native', 'Native MM mode with enabled scoped API required')
    platform.guest(args.boot_id,release='7.0.0-38-kdscope1')
    rt.idle()
    out = args.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT), 'new external output required')
    out.mkdir(parents=True)
    result = dict(schema=1,passed=False,drained=False,boot_id=args.boot_id,scored=False,sessions=[])
    try:
        result['host'] = api.common.host_check(args.host_state,out,True,args.boot_id,
            reference=args.host_reference,reference_sha256=args.host_reference_sha256)
        result['kernel_identity'] = identity.capture(args,out,rt.command)
        binaries, files = build(out,args)
        result['files'] = files
        def verify():
            platform.guest(args.boot_id,release='7.0.0-38-kdscope1')
            policy = result['kernel_identity']['runtime_policy']
            rt.require(Path('/proc/cmdline').read_text().strip() == policy['cmdline'] and
                       Path('/sys/kernel/debug/sched/preempt').read_text().strip() == policy['preempt_control'],
                       'running policy changed')
            api.verify_files(files)
        for kind in CASES:
            for arm in ('native','kd'):
                rt.idle()
                spec = dict(name=kind+'-'+arm,kind=kind,arm=arm,scored=False)
                session = ObjectSession(out,spec,binaries,verify,False)
                try:
                    session.prepare()
                    session.exercise()
                    session.cleanup()
                    result['sessions'].append(session.record)
                except BaseException as error:
                    session.record.update(passed=False,error=repr(error),execution_status='FAILED')
                    session.save()
                    raise
                finally:
                    os.close(session.kmsg)
                rt.write_json(out/'result.json',result)
        verify()
        rt.idle()
        result.update(passed=True,drained=True,final_idle=True)
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        rt.write_json(out/'result.json',result)


if __name__ == '__main__':
    main()
