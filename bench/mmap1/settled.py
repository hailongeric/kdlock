#!/usr/bin/env python3
"""One instrumented point using a fixed receipt after one long learning run."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import struct
import time
import traceback

import observe
import provenance

campaign = observe.campaign
rt, bench = campaign.rt, campaign.bench


def frontier_emission(assembly, target, source_ip):
    label = 'loc_' + format(target, 'x')
    body = re.search(r'/\*\s*' + label + r'\s*\n.*?\*/\s*' + label + r':',
                     assembly, re.S) is not None
    code = re.sub(r'/\*.*?\*/', '', assembly, flags=re.S)
    terminal = re.search(r'(?m)^MOVABS\s+R14,\s*' + re.escape(hex(source_ip)) +
        r'\s*\nMOV\s+Stack_IJ,\s*(?:16|0x10)\s*\nJMP\s+full_exit(?:\s|$)', code) is not None
    return dict(translated_target=body, exact_terminal=terminal)


def current_capability():
    packet = bytearray(b'\xff' * 16)
    with open('/dev/kd_dev', 'rb', buffering=0) as device:
        result = fcntl.ioctl(device, 0x80104b73, packet, True)
    version, features, stack, percpu = struct.unpack('<IIII', packet)
    rt.require(type(result) is int and result == 0,
               'current provider capability query failed', 'DATA_ERROR')
    try:
        return provenance.capability_contract(version, features, stack, percpu)
    except ValueError as error:
        raise rt.Failure('DATA_ERROR', 'current publication capability differs: ' + str(error)) from error


def deltas(before, after):
    rows = []
    rt.require(set(before) == set(after), 'observation entries changed', 'DATA_ERROR')
    for entry in before:
        row = {key: after[entry][key] - before[entry][key] for key in observe.FIELDS}
        rt.require(all(value >= 0 for value in row.values()) and row['invalid_clock'] == 0,
                   'observation interval differs', 'DATA_ERROR')
        rows.append(dict(entry=hex(int(entry)), **row))
    return rows


def drained_counts(rows):
    for d in rows:
        rt.require(d['selected'] == d['local'] + d['submitted'] + d['prepublication_cancel'] and
                   d['local'] == d['local_success'] + d['local_cancel'] and
                   d['submitted'] == d['returned'] + d['handback_finished'] + d['canceled'] and
                   d['handback'] == d['handback_finished'] and
                   d['bound'] == d['jit_entered'] == d['dispatch_samples'] ==
                   d['shadow_samples'] == d['returned'] + d['handback'],
                   'drained observation conservation differs', 'DATA_ERROR')


class SettledObservation(observe.Observation):
    def provenance_failure(self, error):
        evidence = dict(passed=False, scope='source-derived immutable ABI2 upload association',
                        error=repr(error))
        self.result['required_publication'] = evidence
        self.save()
        raise rt.Failure('DATA_ERROR', 'required publication provenance unavailable: ' + str(error)) from error

    def configure_daemon_evidence(self, daemon):
        required = self.c.get('required_publication')
        if required is not None:
            daemon.provenance = dict(directory=self.out / 'provenance', entry=required['entry'])

    def compiler_records(self):
        return [json.loads(line.split(' ', 1)[1]) for line in
                (self.out / 'daemon.log').read_text().splitlines()
                if line.startswith('KD_TRANSLATION_METRICS ')]

    def fixed_receipt(self, folder, learned):
        rt.require(not rt.children(self.daemon.daemon.pid), 'compiler remains active', 'UNDRAINED')
        source = rt.status()
        rt.require(source['state'] == source['frames'] == 0 and source['writers'] == 1,
                   'source is not settled', 'UNDRAINED')
        scoped = getattr(self, 'c', {}).get('required_publication') is not None
        if scoped:
            read_start = time.monotonic_ns()
        rows = rt.registry()
        if scoped:
            read_end = time.monotonic_ns()
        bench.execution.ready_writer_entries(rows, self.args.writer_entries)
        rt.require(bench.execution.registry(rows) == learned['registry_after'],
                   'settled images differ from copied learning artifacts', 'LEARNING_ADVANCED')
        self.admit_images(rows)
        folder.mkdir()
        self.owner.model = folder
        exact = self.owner.session_receipt(self.daemon, rows)
        exact.verify()
        if scoped:
            observation = dict(schema=1, clock='CLOCK_MONOTONIC',
                read_site='SettledObservation.fixed_receipt', boot_id=exact.expected['boot_id'],
                observer=exact.expected['preparer'], read_start_ns=read_start,
                read_end_ns=read_end, registry=rows)
            destination = folder / 'provenance'
            try:
                bound = provenance.capture(self.out / 'provenance', destination, observation,
                                           exact.expected, self.c['required_publication'])
            except (OSError, ValueError, KeyError, TypeError) as error:
                self.provenance_failure(error)
            value = dict(exact.expected, files=dict(exact.expected['files'], **bound),
                provenance=dict(root=str(destination), observation=str(destination / 'observation.json'),
                                association=str(destination / 'association.json')))
            # Extend the not-yet-used receipt without another live observation.
            rt.write_json(exact.path, value)
            self.owner.files.update(bound)
            exact = bench.execution.ExecutionSession(exact.path, rt.digest(exact.path))
        return exact

    def publication_gate(self):
        required = self.c.get('required_publication')
        if required is None:
            return
        entry, target, source_ip = (required[key] for key in ('entry', 'call_target', 'source_ip'))
        self.exact.verify()
        captured = self.exact.expected.get('provenance')
        rt.require(captured is not None, 'required publication has no provenance chain', 'DATA_ERROR')
        try:
            observation = json.loads(Path(captured['observation']).read_bytes())
            chain, files, assembly, history = provenance.associate(
                captured['root'], observation, self.exact.expected, required)
            manifest = json.loads(files['compile-%d/manifest.json' % chain['compile_attempt_id']])
            compiler_capability = {name: manifest['capabilities'][name] for name in
                ('version', 'features', 'mutex_stack_bytes', 'percpu_module_bytes')}
            capability = current_capability()
            provenance.require(capability == compiler_capability,
                               'current and captured compiler capabilities differ')
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.provenance_failure(error)
        row = chain['registry']
        reached = target in {int(line, 16) for line in history.decode().splitlines() if line.strip()}
        emission = frontier_emission(assembly.decode(), target, source_ip)
        evidence = dict(required=required, registry=row, capability=capability,
            chain=chain, assembly=dict(sha256=hashlib.sha256(assembly).hexdigest()),
            history=dict(sha256=hashlib.sha256(history).hexdigest()),
            historically_reached_target=reached, leased_direction_compiler=True, **emission)
        evidence['passed'] = reached and all(emission.values())
        folder = self.out / 'required-publication'
        folder.mkdir()
        (folder / 'callee_table.txt').write_bytes(history)
        rt.write_json(folder / 'result.json', evidence)
        self.result['required_publication'] = evidence
        self.save()
        print('PUBLICATION_RESULT ' + json.dumps(evidence), flush=True)
        rt.require(evidence['passed'], 'fresh learning did not publish the required expanded root', 'LEARNING_ADVANCED')

    def fixed_point(self, folder, row):
        before = self.window_observer()
        compilers = self.compiler_records()
        row.update(before=before, compiler_records_before=compilers,
                   fixed_session=self.exact.identity(), instrumentation='selected-service-counters',
                   scored=False, stable=False)
        self.save()
        try:
            application = bench.run_point(folder / 'application',
                dict(model=self.current_model, workers=8, round=0, nominal_seconds=10,
                     upstream_samples=10, measured_samples=10, timeout_seconds=30, sample_window=True),
                self.inputs, self.verify, execution_session=self.exact,
                window_observer=self.window_observer)
            row['application'] = application
        finally:
            path = folder / 'application/result.json'
            if path.is_file():
                row['application'] = json.loads(path.read_text())
                row['application_receipt'] = dict(path=str(path), sha256=rt.digest(path))
            events = row.get('application', {}).get('sample_window', {})
            if isinstance(events, dict) and len(events.get('events', [])) == 2:
                first, last = events['events']
                row['measured_delta'] = deltas(first['observation']['service'],
                                               last['observation']['service'])
            after = self.window_observer()
            row.update(after=after, compiler_records_after=self.compiler_records(),
                       whole_application_delta=deltas(before['service'], after['service']))
            self.save()
        expected = bench.execution.registry(self.exact.expected['registry'])
        events = application['sample_window']['events']
        views = [before, *(event['observation'] for event in events), after]
        rt.require(all(bench.execution.registry(view['registry']) == expected and
                       view['superseded_reports'] == before['superseded_reports'] for view in views) and
                   row['compiler_records_after'] == compilers,
                   'fixed point changed image or learning history', 'LEARNING_ADVANCED')
        drained_counts(row['whole_application_delta'])
        rt.require(all(d['selected'] > 0 and d['submitted'] > 0 and d['bound'] > 0 and
                       d['jit_entered'] > 0 and d['local_no_image'] == 0
                       for d in row['whole_application_delta']),
                   'fixed point did not use each prepared image', 'DATA_ERROR')
        row['measured_delta'] = deltas(events[0]['observation']['service'],
                                       events[1]['observation']['service'])
        row.update(state='COMPLETE', stable=True, conservation_passed=True)
        self.result.update(stable_point_passed=True, application=application,
            upstream=application['output'], execution_session=self.exact.identity())
        self.save()
        print('SETTLED_POINT_RESULT ' + json.dumps(dict(model=self.current_model, workers=8,
            rate=application['output']['pairs_per_nominal_second'], stable=True,
            passed=application['passed'], drained=application['drained'], scored=False)), flush=True)

    def run(self):
        rt.require(not self.out.exists(), 'settled output already exists', 'DATA_ERROR')
        rt.require(self.models == ['processes'] and self.counts == [8] and
                   self.c['learning_rounds'] == 1 and self.c.get('long_warmup') is True,
                   'one process-model long learning run and one fixed point required', 'DATA_ERROR')
        required = self.c.get('required_publication')
        rt.require(required is None or (type(required) is dict and
                   set(required) == {'entry', 'call_target', 'source_ip'} and
                   all(type(value) is int and 0 < value < 1 << 64 for value in required.values()) and
                   required['entry'] in self.args.writer_entries),
                   'required publication must name one selected root, CALL target and instruction', 'DATA_ERROR')
        self.result.update(instrumentation='selected-service-counters', scored=False,
                           stable_point_passed=False, preparation={}, quiet_performance_accepted=False)
        try:
            self.prepare()
            if required is not None:
                self.result['capability_before_learning'] = current_capability()
                self.save()
            self.current_model = 'processes'
            folder = self.out / self.current_model
            folder.mkdir()
            limit = None
            try:
                self.learn(8, folder / 'learning')
            except rt.Failure as error:
                if error.status != 'LEARNING_ADVANCED':
                    raise
                limit = str(error)
            path = folder / 'learning/learning.json'
            rt.require(path.is_file(), 'long learning application receipt missing', 'DATA_ERROR')
            observations = json.loads(path.read_text())
            rt.require(len(observations) == 1 and observations[0]['application']['passed'] and
                       observations[0]['application']['drained'] and
                       observations[0]['application']['sample_window']['samples'] == 730,
                       'long learning application did not complete and drain', 'UNDRAINED')
            learned = observations[0]
            self.result['preparation'] = dict(path=str(path), sha256=rt.digest(path),
                application=learned['application'], registry_after=learned['registry_after'],
                learning_limit=limit)
            self.save()
            self.exact = self.fixed_receipt(folder / 'fixed-session', learned)
            self.publication_gate()
            row = dict(model=self.current_model, workers=8, state='MEASURING', scored=False)
            self.result['points'].append(row)
            self.save()
            self.fixed_point(folder, row)
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--finalize', action='store_true')
    args = parser.parse_args()
    data = args.config.read_bytes()
    config = json.loads(data)
    if args.finalize:
        campaign.finalize(config, data)
    else:
        SettledObservation(config, data).run()


if __name__ == '__main__':
    main()
