#!/usr/bin/env python3
"""One instrumented point using a fixed receipt after one long learning run."""
import argparse
import json
from pathlib import Path
import traceback

import observe

campaign = observe.campaign
rt, bench = campaign.rt, campaign.bench


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
    def compiler_records(self):
        return [json.loads(line.split(' ', 1)[1]) for line in
                (self.out / 'daemon.log').read_text().splitlines()
                if line.startswith('KD_TRANSLATION_METRICS ')]

    def fixed_receipt(self, folder, learned):
        rt.require(not rt.children(self.daemon.daemon.pid), 'compiler remains active', 'UNDRAINED')
        source = rt.status()
        rt.require(source['state'] == source['frames'] == 0 and source['writers'] == 1,
                   'source is not settled', 'UNDRAINED')
        rows = rt.registry()
        bench.execution.ready_writer_entries(rows, self.args.writer_entries)
        rt.require(bench.execution.registry(rows) == learned['registry_after'],
                   'settled images differ from copied learning artifacts', 'LEARNING_ADVANCED')
        self.admit_images(rows)
        folder.mkdir()
        self.owner.model = folder
        exact = self.owner.session_receipt(self.daemon, rows)
        exact.verify()
        return exact

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
        self.result.update(instrumentation='selected-service-counters', scored=False,
                           stable_point_passed=False, preparation={}, quiet_performance_accepted=False)
        try:
            self.prepare()
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
