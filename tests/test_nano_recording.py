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
                      completed=0, entered=0)
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
