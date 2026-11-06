#!/usr/bin/env python3
"""Bounded priming applications and one eight-worker observation."""
import argparse
import json
from pathlib import Path

import campaign
import pilot


FIELDS = ('selected local local_no_image local_success local_cancel prepublication_cancel '
          'submitted bound jit_entered handback returned handback_finished canceled local_ns '
          'dispatch_samples dispatch_ns shadow_samples shadow_ns invalid_clock').split()


class Observation(pilot.Pilot):
    def extra_provider_parameters(self):
        campaign.rt.require(len(self.models) == 1, 'one task name per observation session required', 'DATA_ERROR')
        return ['service_observe=1', 'service_observe_comm=mmap1_' + self.models[0],
                'service_observe_entries=' + ','.join(hex(v) for v in self.args.writer_entries)]

    def snapshot(self):
        params = campaign.controller.PARAMETERS
        campaign.rt.require((params / 'service_observe').read_text().strip() == 'Y' and
            (params / 'service_observe_comm').read_text().strip() == 'mmap1_' + self.models[0],
            'observation parameters differ', 'DATA_ERROR')
        rows = {}
        for line in (params / 'service_observe_stats').read_text().splitlines():
            fields = dict(word.split('=', 1) for word in line.split())
            entry = int(fields.pop('entry'), 16)
            campaign.rt.require(set(fields) == set(FIELDS) and entry not in rows,
                                'observation fields differ', 'DATA_ERROR')
            rows[entry] = {name: int(value) for name, value in fields.items()}
        campaign.rt.require(set(rows) == set(self.args.writer_entries),
                            'observation entries differ', 'DATA_ERROR')
        return rows

    def learn(self, workers, folder):
        before = self.snapshot()
        try:
            return super().learn(workers, folder)
        finally:
            after = self.snapshot()
            rows = []
            for entry in self.args.writer_entries:
                d = {name: after[entry][name] - before[entry][name] for name in FIELDS}
                campaign.rt.require(all(v >= 0 for v in d.values()) and d['invalid_clock'] == 0,
                                    'observation counter interval differs', 'DATA_ERROR')
                rows.append(dict(entry=hex(entry), **d))
            observation = dict(model=self.current_model, workers=workers,
                scope='whole application including six warmup and two measured samples',
                timers='inclusive elapsed ns; overlapping intervals are not additive',
                whole_critical_section_time_measured=False, dynamic_instructions_measured=False,
                before=before, after=after, delta=rows)
            path = folder / 'learning.json'
            if path.is_file():
                applications = json.loads(path.read_text())
                if len(applications) == 1 and applications[0]['application'].get('drained'):
                    for d in rows:
                        campaign.rt.require(d['selected'] == d['local'] + d['submitted'] +
                            d['prepublication_cancel'] and
                            d['local'] == d['local_success'] + d['local_cancel'] and
                            d['submitted'] == d['returned'] + d['handback_finished'] + d['canceled'] and
                            d['handback'] == d['handback_finished'] and
                            d['bound'] == d['jit_entered'] == d['dispatch_samples'] ==
                            d['shadow_samples'] == d['returned'] + d['handback'],
                            'drained observation conservation differs', 'DATA_ERROR')
                    observation['conservation_passed'] = True
            self.result.setdefault('service_observations', []).append(observation)
            if folder.is_dir():
                campaign.rt.write_json(folder / 'service-observation.json', observation)
            self.save()
            print('OBSERVATION_RESULT ' + json.dumps(observation), flush=True)

    def run(self):
        campaign.rt.require(self.models in (['threads'], ['processes']) and self.counts in ([1, 8], [1, 2, 8]),
                            'one or two priming applications and one eight-worker observation required', 'DATA_ERROR')
        self.result['instrumentation'] = 'selected-service-counters'
        self.result['translation_during_application'] = not self.c['pause_translation']
        return super().run()


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
        Observation(config, data).run()


if __name__ == '__main__':
    main()
