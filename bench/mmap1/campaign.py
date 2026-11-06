#!/usr/bin/env python3
"""Persistent original-image mmap1 learning, proof and one-round scaling."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import traceback

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


point = load_module('mmap1_campaign_point', ROOT / 'bench/mmap1/delegated_point.py')
controller = load_module('mmap1_campaign_controller', ROOT / 'tests/kernel/mmap1_identity/delegated.py')
bench, rt = controller.bench, controller.rt


def validate_counts(values):
    rt.require(type(values) is list and values and len(values) == len(set(values)) and
               all(type(value) is int and value in bench.WORKERS for value in values),
               'distinct supported worker counts required', 'DATA_ERROR')
    return values


def image_pool(parameters):
    values = {name: int(value) for name, value in
              (word.split('=') for word in (parameters / 'jit_image_usage').read_text().split())}
    rt.require(0 <= values['published'] <= values['used'] <= values['capacity'] and
               values['used'] + values['free_descriptors'] == values['capacity'],
               'image pool observation differs', 'DATA_ERROR')
    return values


def require_headroom(value, roots):
    rt.require(value['capacity'] == 128 and value['private'] == 0 and
               value['free_descriptors'] >= roots,
               'retained image pool lacks headroom for another application', 'IMAGE_CAPACITY')


def applications_drained(folder):
    for command in folder.rglob('command.json'):
        result = command.with_name('result.json')
        if not result.is_file() or json.loads(result.read_text()).get('drained') is not True:
            return False
    return True


def complete_collection(summary):
    rt.require(summary['complete'] and not summary['fault_detected'],
               'lifecycle kernel collection incomplete or faulted', 'DATA_ERROR')


def finalize(config, config_bytes):
    """Retire only the exact closed session recorded by a previous process."""
    campaign = Campaign(config, config_bytes)
    out = campaign.out
    original_path = out / 'result.json'
    original_hash = rt.digest(original_path)
    original = json.loads(original_path.read_text())
    rt.require(original['state'] in ('MEASURED_RETIREMENT_PENDING', 'STOPPED_RETIREMENT_PENDING') and
               original['config_sha256'] == campaign.result['config_sha256'] and applications_drained(out),
               'campaign is not ready for exact retirement', 'UNDRAINED')
    controller.source_manifest(campaign.args)
    campaign.args.captured_runtime_policy = original['environment']['kernel_identity']['runtime_policy']
    bench.verify_boot(campaign.args)
    params = controller.PARAMETERS
    expected = original['retirement_snapshot']
    rt.require((params / 'rwsem_provider_active').read_text().strip() == 'N' and
               rt.status() == expected['source'] and expected['source']['writers'] == 0 and
               expected['source']['frames'] == 0 and not bench.execution.device_writers() and
               rt.registry() == expected['registry'] and
               rt.digest(bench.execution.NOTE) == expected['module_note_sha256'] ==
               bench.execution.module_note_sha256(Path(config['provider'])) and
               (params / 'service_progress').read_text().strip() == 'total=0 shown=0' and
               not Path('/sys/module/kd_mmap1_identity').exists(),
               'exact campaign retirement identity differs', 'UNDRAINED')
    result = dict(passed=False, drained=False, original_result_sha256=original_hash)
    result_path = out / 'finalization.json'
    rt.require(not result_path.exists(), 'finalization output already exists', 'DATA_ERROR')
    rt.write_json(result_path, result)
    if int((params / 'rwsem_provider_bindings').read_text()):
        postrun = load_module('mmap1_campaign_postrun', ROOT / 'bench/mmap1/postrun.py')
        result['ordinary_cpu_progress'] = postrun.progress(params, rt.status)
        rt.write_json(result_path, result)
    deadline = time.monotonic() + 10
    while int((params / 'rwsem_provider_bindings').read_text()):
        rt.require(time.monotonic() < deadline, 'campaign bindings did not drain', 'UNDRAINED')
        time.sleep(.02)
    rt.require(rt.status() == expected['source'] and rt.registry() == expected['registry'],
               'source or registry changed before retirement', 'UNDRAINED')
    with open('/dev/kd_dev', 'rb', buffering=0) as device:
        fcntl.ioctl(device, rt.RETIRE)
        result['retired'] = rt.info(device.fileno())
    rt.require(result['retired'] == dict(state=2, modules=0, frames=0, writers=0),
               'campaign source retirement incomplete', 'UNDRAINED')
    rt.command(['rmmod', 'kdlock_km'], out / 'unload.log', timeout=30)
    bench.idle()
    rt.require(rt.digest(original_path) == original_hash, 'original campaign result changed', 'DATA_ERROR')
    complete = original['state'] == 'MEASURED_RETIREMENT_PENDING'
    result.update(passed=complete, campaign_complete=complete, retirement_passed=True,
                  drained=True, final_idle=True)
    rt.write_json(result_path, result)
    print('FINALIZATION_RESULT ' + json.dumps(result), flush=True)
    return result


def executor_cpu():
    tasks = []
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            text = path.read_text()
            command = text[text.index('(') + 1:text.rindex(')')]
            if not command.startswith('kd_service/'):
                continue
            words = text.rsplit(')', 1)[1].split()
            tasks.append(dict(pid=int(path.parent.name), start_ticks=int(words[19]),
                              user_ticks=int(words[11]), system_ticks=int(words[12])))
        except (FileNotFoundError, ProcessLookupError):
            continue
    return dict(at_ns=time.monotonic_ns(), clock_ticks=os.sysconf('SC_CLK_TCK'),
                tasks=sorted(tasks, key=lambda row: row['pid']),
                guest_stat=Path('/proc/stat').read_text())


class Campaign:
    def __init__(self, config, config_bytes):
        self.c, self.config_bytes = config, config_bytes
        self.root, self.out = ROOT, Path(config['output'])
        self.counts = validate_counts(config['worker_counts'])
        self.models = config.get('models', [config['model']])
        rt.require(type(self.models) is list and self.models and len(set(self.models)) == len(self.models) and
                   all(model in bench.MODELS for model in self.models), 'distinct mmap1 models required', 'DATA_ERROR')
        rt.require(config['mode'] == 'kd' and config['demand'] is True and config['profile'] is False and
                   config['writer_entries'] and type(config.get('pause_translation')) is bool,
                   'scoped original-image KD campaign required', 'DATA_ERROR')
        timeout, _ = point.learning_limits(config)
        self.deadline = time.monotonic() + timeout
        self.args = argparse.Namespace(mode='kd', boot_id=config['boot_id'],
            kernel_variant=config['variant'], kernel_source=Path(config['kdir']),
            kernel_baseline=Path(config['bundle']), host_state=Path(config['host_state']),
            host_reference=Path(config['host_state']), host_reference_sha256=config['host_sha256'],
            execution_mode='image', demand=True, sites=Path(config['sites']),
            sites_sha256=config['sites_sha256'], source_commit=config['source_commit'],
            source_state=ROOT / 'source-state.json', source_manifest=ROOT / 'source-sha256.json',
            source_state_sha256=config['state_sha256'], source_manifest_sha256=config['manifest_sha256'],
            writer_entries=config['writer_entries'], syscall_shape=config.get('syscall_shape', False))
        rt.require(type(self.args.syscall_shape) is bool, 'syscall argument selection must be boolean', 'DATA_ERROR')
        self.result = dict(schema=1, passed=False, drained=False, accepted=False,
            state='STARTING', mode='kd', models=self.models, workers=2, worker_counts=self.counts,
            config_sha256=hashlib.sha256(config_bytes).hexdigest(), source_commit=config['source_commit'],
            provider_source_commit=config['provider_source_commit'], boot_id=config['boot_id'],
            execution_mode='image', delegation_proved=False, physical_batch_length_measured=False,
            writer_entries=config['writer_entries'], points=[], proofs=[], pool_observations=[])
        self.daemon = self.owner = self.exact = None
        self.proof_key = None
        self.provider_loaded = self.observer_loaded = False
        self.current_model = self.models[0]

    def save(self):
        rt.write_json(self.out / 'result.json', self.result)

    def verify(self):
        bench.verify_boot(self.args)
        bench.verified_files(self.files)

    def pool(self, rows):
        value = image_pool(controller.PARAMETERS)
        rt.require(value['capacity'] == 128, 'declared image capacity differs', 'DATA_ERROR')
        if not self.result['pool_observations'] or self.result['pool_observations'][-1] != value:
            self.result['pool_observations'].append(value)
            self.save()
        return value

    def admit_images(self, rows):
        require_headroom(self.pool(rows), len(self.args.writer_entries))

    def extra_provider_parameters(self):
        return []

    def prepare(self):
        self.out.mkdir(parents=True, exist_ok=False)
        self.save()
        rt.require(os.geteuid() == 0 and sys.executable == controller.PYTHON,
                   'guest root and pinned interpreter required', 'DATA_ERROR')
        controller.source_manifest(self.args)
        bench.idle()
        self.result['environment'] = bench.admit(self.args, self.out)
        self.save()
        rt.require(rt.digest(Path(self.c['inputs'])) == self.c['inputs_sha256'], 'prepared inputs differ')
        self.inputs = bench.inputs_from(Path(self.c['inputs']))
        self.files = dict(self.inputs['files'])
        self.files[str(self.args.sites)] = self.c['sites_sha256']
        self.audit = controller.site_audit(self.args, self.result['environment']['kernel_binding'])
        bench.execution.selected_writer_entries(self.args.writer_entries,
            {row['entry'] for row in self.audit['records']})
        for name in ('provider', 'daemon', 'probe'):
            rt.require(rt.digest(Path(self.c[name])) == self.c[name + '_sha256'], name + ' bytes differ')
            self.files[self.c[name]] = self.c[name + '_sha256']
        load = ['insmod', self.c['provider'], 'bench_quiet=1', 'bench_complete_probe=0',
            'jit_timing=0', 'hotlock_stats=0', 'service_cpus=0-61', 'rwsem_provider_demand=1',
            'rwsem_provider_entries=' + ','.join(hex(value) for value in self.args.writer_entries)]
        if self.args.syscall_shape:
            load.append('rwsem_provider_syscall_shape=1')
        load.extend(self.extra_provider_parameters())
        rt.command(load, self.out / 'load.log', timeout=30)
        self.provider_loaded = True
        params = controller.PARAMETERS
        rt.require(bench.execution.parse_writer_entries((params / 'rwsem_provider_entries').read_text()) ==
                   self.args.writer_entries and (params / 'service_trace').read_text().strip() == 'N' and
                   (params / 'rwsem_provider_active').read_text().strip() == 'N', 'provider settings differ')
        self.daemon = controller.Daemon(self.out, ROOT, Path(self.c['daemon']))
        self.daemon.start()
        self.owner = controller.Controller.__new__(controller.Controller)
        self.owner.args, self.owner.files, self.owner.audit = self.args, self.files, self.audit
        self.owner.model = self.out
        self.owner.binaries = {name: Path(self.c[name]) for name in ('provider', 'probe')}
        (params / 'rwsem_provider_mode').write_text('prepare\n')
        (params / 'rwsem_provider_mode').write_text('activate\n')

    def learn(self, workers, folder):
        rt.require(time.monotonic() < self.deadline, 'campaign learning deadline reached', 'LEARNING_ADVANCED')
        folder.mkdir()
        config = dict(self.c, workers=workers, model=self.current_model)
        self.exact, observations = point.demand_learning(config, folder, self.owner, self.daemon,
            bench, rt, self.inputs, self.verify, deadline=self.deadline, quiescent=self.pool,
            before_application=self.admit_images,
            window_observer=getattr(self, 'window_observer', None) if self.c.get('long_warmup', False) else None)
        bench.execution.ready_writer_entries(self.exact.expected['registry'], self.args.writer_entries)
        return observations

    def proof(self, number):
        folder = self.out / ('proof-%02d' % number)
        folder.mkdir()
        rows = rt.registry()
        bench.execution.ready_writer_entries(rows, self.args.writer_entries)
        self.admit_images(rows)
        params = controller.PARAMETERS
        (params / 'rwsem_provider_mode').write_text('deactivate\n')
        rt.require(rt.status()['frames'] == 0 and not rt.children(self.daemon.daemon.pid),
                   'proof setup is not quiescent', 'UNDRAINED')
        self.daemon.translation_phase(True)
        fd = os.open('/dev/kmsg', os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        os.lseek(fd, 0, os.SEEK_END)
        logs = folder / 'lifecycle-log'
        logs.mkdir()
        collector = bench.kernel_log.DiagnosticKernelLog(fd, logs, rt.FAULT,
            fault_check=rt.kernel_fault, max_bytes=self.c.get('diagnostic_log_mib', 128) * 1024**2)
        self.owner.model, self.owner.collector = folder, collector
        proof = None
        try:
            collector.start()
            rt.command(['insmod', self.c['probe'], 'target=mmap1_' + self.current_model, 'pair_limit=8'],
                folder / 'load-observer.log', timeout=30)
            self.observer_loaded = True
            (params / 'service_trace').write_text('1\n')
            (params / 'rwsem_provider_mode').write_text('activate\n')
            exact = self.owner.session_receipt(self.daemon, rows)
            application = bench.run_point(folder / 'application', dict(model=self.current_model, workers=2,
                round=0, nominal_seconds=2), self.inputs, self.verify, diagnostic=True,
                execution_session=exact, diagnostic_collector=collector,
                diagnostic_log_bytes=self.c.get('diagnostic_log_mib', 128) * 1024**2)
            snapshot = self.owner.stop_observer()
            exact.verify(allow_identity_probe=True)
            symbols = [int(line.split()[0], 16) for line in Path('/proc/kallsyms').read_text().splitlines()
                       if len(line.split()) == 4 and line.split()[2:] == ['kd_rwsem_ops', '[kdlock_km]']]
            rt.require(len(symbols) == 1, 'exact live provider identity unavailable')
            messages = (folder / 'application/kernel.log').read_text()
            proof = controller.observer.validate_delegated(snapshot, application, os.sysconf('SC_CLK_TCK'),
                messages, self.audit['entry_sites'], symbols[0])
            proof['service_transactions'] = self.owner.validate_services(proof, rows, messages, snapshot)
            lifecycle = logs / 'kernel.log'
            deadline = time.monotonic() + 2
            while 'kd_mm_pair: event=stop ' not in lifecycle.read_text():
                rt.require(time.monotonic() < deadline, 'syscall pair STOP summary missing', 'DATA_ERROR')
                collector.checkpoint()
                time.sleep(.02)
            proof['syscall_pairs'] = controller.pairs.validate(lifecycle.read_text(), snapshot, proof,
                self.audit['entry_sites'], 8)
            proof['continuation'] = controller.require_observed_continuation(proof)
            proof['registry'] = rows
        finally:
            try:
                (params / 'rwsem_provider_mode').write_text('deactivate\n')
                (params / 'service_trace').write_text('0\n')
                if applications_drained(folder) and rt.status()['frames'] == 0:
                    if self.observer_loaded:
                        rt.command(['rmmod', 'kd_mmap1_identity'], folder / 'unload-observer.log', timeout=30)
                        self.observer_loaded = False
            finally:
                summary = collector.finish()
                rt.write_json(folder / 'collection.json', summary)
                if not collector.thread.is_alive():
                    os.close(fd)
                self.owner.collector = None
                complete_collection(summary)
        rt.require(proof is not None and not self.observer_loaded,
                   'execution proof cleanup did not complete', 'UNDRAINED')
        proof['model'] = self.current_model
        rt.write_json(folder / 'proof.json', proof)
        self.result['proofs'].append(dict(path=str(folder / 'proof.json'),
            sha256=rt.digest(folder / 'proof.json'), model=self.current_model, registry=rows))
        self.result['delegation_proved'] = True
        self.proof_key = (self.current_model, bench.execution.registry(rows))
        self.save()

    def close(self):
        if not self.provider_loaded:
            rt.require(not controller.PARAMETERS.exists(), 'provider preparation state is unknown', 'UNDRAINED')
            return
        params = controller.PARAMETERS
        (params / 'rwsem_provider_mode').write_text('deactivate\n')
        (params / 'service_trace').write_text('0\n')
        rt.require(applications_drained(self.out) and not self.observer_loaded,
                   'application or observer lifetime remains live', 'UNDRAINED')
        if (self.daemon is not None and self.daemon.daemon is not None and
                rt.children(self.daemon.daemon.pid) and rt.status()['frames'] == 0 and
                self.daemon.translation_state() in ('T', 't')):
            self.daemon.translation_phase(False)
        deadline = time.monotonic() + 40
        while (self.daemon is not None and self.daemon.daemon is not None and
               rt.children(self.daemon.daemon.pid)) or rt.status()['frames']:
            rt.require(time.monotonic() < deadline, 'campaign close did not reach quiescence', 'UNDRAINED')
            time.sleep(.05)
        if self.daemon is not None:
            self.daemon.stop()
        self.result['retirement_snapshot'] = dict(source=rt.status(), registry=rt.registry(),
            bindings=int((params / 'rwsem_provider_bindings').read_text()),
            service_progress=(params / 'service_progress').read_text().strip(),
            module_note_sha256=rt.digest(bench.execution.NOTE))
        self.result['retirement'] = 'fresh finalizer after controller exit required'
        self.result['state'] = 'MEASURED_RETIREMENT_PENDING' if all(
            row.get('state') == 'COMPLETE' for row in self.result['points']) and len(
                self.result['points']) == len(self.counts) * len(self.models) else 'STOPPED_RETIREMENT_PENDING'
        self.save()

    def run(self):
        rt.require(not self.out.exists(), 'campaign output already exists', 'DATA_ERROR')
        try:
            self.prepare()
            proof_number = 0
            for model in self.models:
                self.current_model = model
                model_folder = self.out / model
                model_folder.mkdir()
                for workers in self.counts:
                    row = dict(model=model, workers=workers, state='LEARNING', learning=[])
                    self.result['points'].append(row)
                    self.save()
                    folder = model_folder / ('w%02d' % workers)
                    folder.mkdir()
                    for attempt in range(32):
                        row['learning'].append(self.learn(workers, folder / ('learn-%02d' % attempt)))
                        rows = self.exact.expected['registry']
                        if (model, bench.execution.registry(rows)) == self.proof_key:
                            break
                        rt.require(time.monotonic() < self.deadline,
                                   'campaign learning deadline reached before proof', 'LEARNING_ADVANCED')
                        try:
                            self.proof(proof_number)
                        except rt.Failure as error:
                            if error.status != 'LEARNING_ADVANCED':
                                raise
                            row.setdefault('proof_learning', []).append(dict(number=proof_number, error=str(error)))
                        proof_number += 1
                    else:
                        raise rt.Failure('LEARNING_ADVANCED', 'bounded proof and learning attempts did not settle')
                    self.admit_images(rows)
                    self.exact.verify()
                    before = executor_cpu()
                    application = bench.run_point(folder / 'application', dict(model=model, workers=workers,
                        round=0, nominal_seconds=2), self.inputs, self.verify, execution_session=self.exact)
                    after = executor_cpu()
                    row.update(state='COMPLETE', application=application, executor_cpu_before=before,
                        executor_cpu_after=after, cpu_scope='whole run_point including warmup and validation')
                    self.result.update(application=application, execution_session=self.exact.identity(),
                        upstream=application['output'])
                    self.save()
                    print('POINT_RESULT ' + json.dumps(dict(model=model, workers=workers,
                        rate=application['output']['pairs_per_nominal_second'], passed=application['passed'],
                        drained=application['drained'], delegation_proved=True)), flush=True)
        except BaseException as error:
            self.result.update(error=repr(error), traceback=traceback.format_exc())
            self.save()
            raise
        finally:
            try:
                self.close()
            except BaseException as error:
                self.result.update(state='LIVE_STATE_RETAINED', cleanup_error=repr(error),
                    cleanup_traceback=traceback.format_exc())
                self.save()
                raise
        return self.result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--finalize', action='store_true')
    args = parser.parse_args()
    data = args.config.read_bytes()
    config = json.loads(data)
    if args.finalize:
        finalize(config, data)
    else:
        Campaign(config, data).run()


if __name__ == '__main__':
    main()
