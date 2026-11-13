"""VM-only focused checks for truthful evidence and the narrow recorder plan."""
import errno
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bench/nano'))
import evidence
import protocol
import run as nano_run


class RecordingEvidence(unittest.TestCase):
    def local_measurement(self):
        counts = dict(attached=1, detached=1, state=100, origin=200, errors=0, live=0,
                      reserved=5, freed=5, read_acquired=4, read_released=4,
                      completed=0, entered=0, fast_acquired=0, fast_released=0,
                      fast_read_acquired=0, fast_read_released=0)
        return dict(kd_evidence=dict(available=True, workers=[counts]),
                    workers=[dict(completed=5, reads=4, writes=1)], writes=1)

    def test_on_retains_no_jit_and_lifetime_validation(self):
        measurement = self.local_measurement()
        self.assertEqual(evidence.validate_kd(measurement, None)['jit_status'], 'NO_JIT')
        measurement['kd_evidence']['workers'][0]['freed'] = 4
        with self.assertRaisesRegex(ValueError, 'lifetime'):
            evidence.validate_kd(measurement, None)

    def test_off_has_no_invented_zero_counts_or_completion_pass(self):
        measurement = dict(kd_evidence=dict(available=False, workers=None))
        result = evidence.validate_kd(measurement, None, recording=False)
        self.assertEqual(result['jit_status'], 'EVIDENCE_UNAVAILABLE')
        for field in ('jit_entries', 'jit_completions', 'completed_writer_share'):
            self.assertIsNone(result[field])
        self.assertFalse(result['retirement_observations_available'])
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            evidence.validate_kd(measurement, None)

    def test_fast_pairs_have_separate_exact_lifetimes(self):
        measurement = self.local_measurement()
        measurement['spec'] = dict(lock_kind='mutex')
        counts = measurement['kd_evidence']['workers'][0]
        counts.update(reserved=4, freed=4, fast_acquired=1, fast_released=1)
        self.assertEqual(evidence.validate_kd(measurement, None)['jit_status'], 'NO_JIT')
        for changed in (dict(fast_released=0), dict(fast_acquired=2, fast_released=2),
                        dict(reserved=5, freed=5)):
            with self.subTest(changed=changed):
                before = counts.copy()
                counts.update(changed)
                with self.assertRaisesRegex(ValueError, 'lifetime'):
                    evidence.validate_kd(measurement, None)
                counts.update(before)

    def test_evidence_v4_preserves_proof_offsets_and_immutable_mode(self):
        self.assertEqual(protocol.EVIDENCE, 0x420D)
        def reply(device, command, buffer, mutate):
            self.assertEqual(command, protocol.EVIDENCE)
            struct.pack_into('=4Q', buffer, 0, 4, 2, 0, 0)
            for worker in range(2):
                offset = 32 + worker * 146 * 8
                struct.pack_into('=26Q', buffer, offset, *range(100 * worker, 100 * worker + 26))
                for record in range(6):
                    struct.pack_into('=20Q', buffer, offset + 26 * 8 + record * 160,
                                     *([1000 * worker + record + 1] * 20))
        with mock.patch('builtins.open', mock.mock_open()), mock.patch.object(protocol.fcntl, 'ioctl', reply):
            result = protocol.evidence()
        self.assertFalse(result['delegation_enabled'])
        self.assertEqual(result['proxy_limit'], 0)
        for worker, row in enumerate(result['workers']):
            self.assertEqual(row['fast_acquired'], 100 * worker + 16)
            self.assertEqual(row['fast_released'], 100 * worker + 17)
            self.assertEqual(row['fast_read_acquired'], 100 * worker + 18)
            self.assertEqual(row['fast_read_released'], 100 * worker + 19)
            self.assertEqual(row['ordinary_read_acquired'], 100 * worker + 20)
            self.assertEqual(row['ordinary_queued_write'], 100 * worker + 25)
            self.assertEqual([event['kind'] for event in row['records']],
                             [1000 * worker + record + 1 for record in range(6)])

    def test_atomic_ordinary_records_require_release_and_local_only_evidence(self):
        measurement = self.local_measurement()
        measurement['spec'] = dict(lock_kind='rwsem', delegation=False)
        measurement['kd_evidence'].update(version=4, delegation_enabled=False, proxy_limit=0)
        counts = measurement['kd_evidence']['workers'][0]
        counts.update(reserved=0, freed=0, proxy=0, ordinary_read_acquired=4,
                      ordinary_read_released=4, ordinary_write_acquired=1,
                      ordinary_write_released=1, ordinary_live=0, ordinary_queued_write=1)
        self.assertEqual(evidence.validate_kd(measurement, None)['jit_status'], 'LOCAL_ONLY')
        for change in (dict(ordinary_read_released=3), dict(ordinary_write_released=0),
                       dict(ordinary_live=1), dict(ordinary_queued_write=2), dict(proxy=1),
                       dict(entered=1), dict(reserved=1, freed=1), dict(read_released=3)):
            before = counts.copy()
            with self.subTest(change=change):
                counts.update(change)
                with self.assertRaises(ValueError):
                    evidence.validate_kd(measurement, None)
                counts.update(before)
        measurement['kd_evidence']['delegation_enabled'] = True
        with self.assertRaisesRegex(ValueError, 'delegation mode'):
            evidence.validate_kd(measurement, None)

    def test_rwsem_cannot_supply_fast_mutex_pairs(self):
        measurement = self.local_measurement()
        measurement['spec'] = dict(lock_kind='rwsem')
        measurement['kd_evidence']['workers'][0].update(
            reserved=4, freed=4, fast_acquired=1, fast_released=1)
        with self.assertRaisesRegex(ValueError, 'mutex family'):
            evidence.validate_kd(measurement, None)

    def test_fast_read_accounting_requires_exact_final_release(self):
        measurement = self.local_measurement()
        measurement['spec'] = dict(lock_kind='rwsem')
        counts = measurement['kd_evidence']['workers'][0]
        counts.update(reserved=1, freed=1, fast_read_acquired=4, fast_read_released=4)
        self.assertEqual(evidence.validate_kd(measurement, None)['jit_status'], 'NO_JIT')
        for changed in (dict(fast_read_released=3), dict(fast_read_acquired=5, fast_read_released=5),
                        dict(read_released=3), dict(reserved=2, freed=2)):
            before = counts.copy()
            counts.update(changed)
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                evidence.validate_kd(measurement, None)
            counts.update(before)
        measurement['spec']['lock_kind'] = 'mutex'
        with self.assertRaisesRegex(ValueError, 'rwsem family'):
            evidence.validate_kd(measurement, None)

    def test_off_rejects_observation_rows(self):
        with self.assertRaisesRegex(ValueError, 'explicit unavailability'):
            evidence.validate_kd(self.local_measurement(), None, recording=False)

    def test_only_unsupported_evidence_maps_to_unavailable(self):
        with mock.patch('builtins.open', mock.mock_open()), mock.patch.object(protocol.fcntl, 'ioctl') as ioctl:
            ioctl.side_effect = OSError(errno.EOPNOTSUPP, 'recording disabled')
            self.assertEqual(protocol.evidence()['workers'], None)
            self.assertFalse(protocol.evidence()['available'])
            ioctl.side_effect = OSError(errno.EBUSY, 'workers active')
            with self.assertRaises(OSError) as failure:
                protocol.evidence()
            self.assertEqual(failure.exception.errno, errno.EBUSY)

    def test_off_refuses_a_remaining_observation_listener(self):
        def reply(device, command, buffer, mutate):
            self.assertEqual(command, protocol.RECORDING)
            self.assertEqual(struct.unpack('=2Q', buffer), (0, 0))
            buffer[:] = struct.pack('=2Q', 0, 1)
        with mock.patch('builtins.open', mock.mock_open()), mock.patch.object(protocol.fcntl, 'ioctl', reply):
            with self.assertRaisesRegex(ValueError, 'listener'):
                protocol.set_recording(False)


class RecordingPlan(unittest.TestCase):
    def test_rwsem_split_uses_one_and_eight_workers_with_unrecorded_timings(self):
        for backend in ('native', 'kdlock'):
            with self.subTest(backend=backend):
                plan = nano_run.measurement_plan('rwsem-split', 'timing', backend)
                modes = ('on', 'off') if backend == 'kdlock' else ('unavailable',)
                self.assertEqual([(n, mode) for _, n, timed, mode in plan if not timed],
                                 [(n, mode) for mode in modes for n in (1, 8)])
                self.assertEqual([(n, mode) for _, n, timed, mode in plan if timed],
                                 [(n, modes[-1]) for _ in range(3) for n in (1, 8)])

    def test_rwsem_split_requires_both_immutable_delegation_modes(self):
        receipts = [dict(status='FUNCTIONAL_PASS', family='rwsem', backend=backend,
                         scope='rwsem-split', stage='functional', kd_delegation=mode,
                         recorder_modes=['on', 'off'] if backend == 'kdlock' else ['unavailable'],
                         build_receipt_sha256='build', boot_id='boot', runner_sha256='runner')
                    for backend, mode in (('native', None), ('kdlock', 'off'), ('kdlock', 'on'))]
        nano_run.validate_prerequisites(receipts, 'rwsem-split', 'rwsem', 'build', 'boot', 'runner')
        for field, value in (('kd_delegation', 'off'), ('recorder_modes', ['off']),
                             ('runner_sha256', 'other'), ('stage', 'timing')):
            changed = [dict(row) for row in receipts]
            changed[2][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                nano_run.validate_prerequisites(changed, 'rwsem-split', 'rwsem', 'build', 'boot', 'runner')

    def test_pair_has_only_six_single_worker_timings(self):
        plan = nano_run.measurement_plan('recorder-pair', 'timing')
        self.assertEqual([(n, timed) for _, n, timed, _ in plan],
                         [(1, False), (1, False)] + [(1, True)] * 6)
        self.assertEqual([mode for _, _, timed, mode in plan if timed],
                         ['on', 'off', 'off', 'on', 'on', 'off'])
        self.assertEqual(nano_run.measurement_plan('recorder-pair', 'functional'), plan[:2])

    def test_default_comparison_keeps_all_requested_sizes(self):
        plan = nano_run.measurement_plan('comparison', 'timing')
        self.assertEqual([n for _, n, timed, _ in plan if not timed], [1, 8, 36])
        self.assertEqual([n for _, n, timed, _ in plan if timed], [1, 8, 36] * 3)
        self.assertEqual({mode for _, _, _, mode in plan}, {'on'})

    def test_pair_prerequisite_cannot_substitute_for_comparison(self):
        receipt = dict(status='FUNCTIONAL_PASS', family='mutex', backend='kdlock',
                       scope='recorder-pair', recorder_modes=['on', 'off'],
                       build_receipt_sha256='build', boot_id='boot')
        nano_run.validate_prerequisites([receipt], 'recorder-pair', 'mutex', 'build', 'boot')
        for scope, family, build, boot in [('comparison', 'mutex', 'build', 'boot'),
                                          ('recorder-pair', 'rwsem', 'build', 'boot'),
                                          ('recorder-pair', 'mutex', 'changed', 'boot'),
                                          ('recorder-pair', 'mutex', 'build', 'changed')]:
            with self.subTest(scope=scope, family=family, build=build, boot=boot):
                with self.assertRaises(ValueError):
                    nano_run.validate_prerequisites([receipt], scope, family, build, boot)


if __name__ == '__main__':
    unittest.main()
