#!/usr/bin/env python3
"""Short image-learning observations, separate from quiet performance scoring."""
import argparse
import json
from pathlib import Path
import traceback

import campaign


class Pilot(campaign.Campaign):
    def run(self):
        rt = campaign.rt
        rt.require(not self.out.exists(), 'pilot output already exists', 'DATA_ERROR')
        rt.require(self.c['learning_rounds'] == 1, 'one pilot application per point required', 'DATA_ERROR')
        self.result.update(preliminary=True, scored=False, pilot_data_passed=False)
        try:
            self.prepare()
            for model in self.models:
                self.current_model = model
                model_folder = self.out / model
                model_folder.mkdir()
                for workers in self.counts:
                    row = dict(model=model, workers=workers, state='LEARNING', scored=False)
                    self.result['points'].append(row)
                    self.save()
                    folder = model_folder / ('w%02d' % workers)
                    folder.mkdir()
                    limit = None
                    try:
                        self.learn(workers, folder / 'learning')
                    except rt.Failure as error:
                        if error.status != 'LEARNING_ADVANCED':
                            raise
                        limit = str(error)
                    path = folder / 'learning/learning.json'
                    rt.require(path.is_file(), 'pilot lacks a completed application', 'DATA_ERROR')
                    observations = json.loads(path.read_text())
                    rt.require(len(observations) == 1, 'pilot application count differs', 'DATA_ERROR')
                    observation = observations[0]
                    application = observation['application']
                    rt.require(application['passed'] and application['drained'] and
                               application['scored'] is False and application['image_learning'] is True,
                               'pilot application failed or did not drain', 'UNDRAINED')
                    row.update(state='DIAGNOSTIC_COMPLETE', application=application,
                        registry_before=observation['registry_before'],
                        registry_after=observation['registry_after'], learning_limit=limit,
                        delegation_proved=False)
                    self.save()
                    summary = dict(model=model, workers=workers, nominal_seconds=application['output']['nominal_seconds'],
                        rate=application['output']['pairs_per_nominal_second'],
                        passed=True, drained=True, scored=False, worker_attributed_proof=False,
                        coverage='image learning; JIT/native shares unmeasured',
                        registry_before=row['registry_before'], registry_after=row['registry_after'],
                        changing_history=row['registry_before'] != row['registry_after'])
                    print('PILOT_RESULT ' + json.dumps(summary), flush=True)
            self.result['pilot_data_passed'] = True
            self.save()
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
        Pilot(config, data).run()


if __name__ == '__main__':
    main()
