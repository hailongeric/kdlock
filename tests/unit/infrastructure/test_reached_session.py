"""Guest-only family/artifact ledger checks for the image-free runner."""
import copy
from pathlib import Path
import sys
import unittest

from source_text import ROOT

sys.path.insert(0, str(ROOT / 'tests/kernel/jit_continuation'))
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt
from helper_mode import primitive_events, validate_transaction
from reached_mode import STATS, parse_stats, reached_events, validate_ledger
import test_memory_continuation as memory_fixture
import memory_mode


ROOT_LINE = ('kd_service event=enter origin=10 executor=20 identity=abc generation=7 '
             'object=ff depth=0 entry=1000 may_delegate=1 family_generation=7')
FAMILY = ('kd_reached event=family origin=10 executor=20 identity=abc generation=7 '
          'family_generation=7 entry=1000')


def artifact(event, sequence, kind='control'):
    return (f'kd_reached event={event} origin=10 executor=20 identity=abc generation=7 '
            f'family_generation=7 artifact_sequence={sequence} kind={kind} '
            'ip=1010 target=2000 sp=3000')


def primitive(stage, task, sequence=2, artifact_sequence=12):
    return (f'kd_service primitive: stage={stage} origin=10 executor=20 task={task} '
            f'identity=abc generation=7 sequence={sequence} target=2000 return=1015 '
            f'image_generation=0 ax=0 flags=202 family_generation=7 '
            f'artifact_sequence={artifact_sequence}')


def ledger():
    return '\n'.join((ROOT_LINE, FAMILY, artifact('service', 11), artifact('resume', 11),
                      artifact('service', 12, 'primitive'), primitive('request', 20),
                      primitive('enter', 10), primitive('done', 10),
                      primitive('resume', 20), artifact('resume', 12, 'primitive')))


class ReachedSessionTests(unittest.TestCase):
    def test_exact_stats_and_unknown_observations(self):
        row = parse_stats(' '.join(f'{key}=0' for key in STATS) + ' extra=3')
        self.assertEqual(row, dict.fromkeys(STATS, 0))

    def test_missing_duplicate_and_negative_stats_are_rejected(self):
        valid = ' '.join(f'{key}=0' for key in STATS)
        for changed in (valid.replace('roots=0 ', ''), valid + ' roots=1',
                        valid.replace('active=0', 'active=-1')):
            with self.subTest(changed=changed), self.assertRaises(rt.Failure):
                parse_stats(changed)

    def test_exact_other_task_family_and_artifact_pairs(self):
        rows = validate_ledger(ledger(), [10])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['root']['family_generation'], 7)
        self.assertEqual(len(rows[0]['artifacts']), 4)

    def test_missing_or_stale_family_is_rejected(self):
        for text in (ledger().replace(FAMILY, ''), ledger().replace('family_generation=7', 'family_generation=8'),
                     ledger().replace('family_generation=7 entry=1000', 'entry=1000')):
            with self.subTest(text=text), self.assertRaises(rt.Failure):
                validate_ledger(text, [10])

    def test_changed_reply_or_unacknowledged_artifact_is_rejected(self):
        last = artifact('resume', 12, 'primitive')
        for text in (ledger().replace(last, ''), ledger().replace(last, last.replace('sp=3000', 'sp=3010')),
                     ledger().replace(last, last.replace('artifact_sequence=12', 'artifact_sequence=13'))):
            with self.subTest(text=text), self.assertRaises(rt.Failure):
                validate_ledger(text, [10])

    def test_reusing_an_artifact_sequence_is_rejected(self):
        text = ledger().replace('artifact_sequence=12', 'artifact_sequence=11')
        with self.assertRaises(rt.Failure):
            validate_ledger(text, [10])

    def test_undeclared_native_request_is_rejected(self):
        text = ledger().replace(primitive('request', 20), primitive('request', 20, artifact_sequence=13))
        with self.assertRaises(rt.Failure):
            validate_ledger(text, [10])

    def test_unexpected_root_and_canceled_service_are_rejected(self):
        for successful, canceled in (([], [10]), ([11], [])):
            with self.subTest(successful=successful), self.assertRaises(rt.Failure):
                validate_ledger(ledger(), successful, canceled)

    def test_cold_primitive_has_exact_four_stage_artifact_identity(self):
        root = validate_ledger(ledger(), [10])[0]['root']
        rows = primitive_events(ledger())
        checked = validate_transaction(rows, root, 10, 0x2000, 0, 0, sequence=2)
        self.assertEqual([row['artifact_sequence'] for row in checked], [12] * 4)

    def test_cold_primitive_cannot_change_artifact_or_claim_image(self):
        root = validate_ledger(ledger(), [10])[0]['root']
        original = primitive_events(ledger())
        for key, value in (('artifact_sequence', 13), ('family_generation', 8), ('image_generation', 1)):
            rows = copy.deepcopy(original)
            rows[2][key] = value
            with self.subTest(key=key), self.assertRaises(rt.Failure):
                validate_transaction(rows, root, 10, 0x2000, 0, 0, sequence=2)

    def test_zero_image_without_family_cannot_pass_image_checks(self):
        root = validate_ledger(ledger(), [10])[0]['root']
        root.pop('family_generation')
        with self.assertRaises(rt.Failure):
            validate_transaction(primitive_events(ledger()), root, 10, 0x2000, 0, 0, sequence=2)

    def test_artifact_trace_requires_complete_source_coordinates(self):
        text = artifact('service', 11).replace(' sp=3000', '')
        with self.assertRaises(rt.Failure):
            reached_events(text)

    def cold_memory(self):
        fixture = memory_fixture.MemoryObservations()
        lines = []
        for line in fixture.messages().splitlines():
            sequence = int(line.split('sequence=', 1)[1].split()[0])
            lines.append(line.replace('image_generation=44', 'image_generation=0') +
                         f' family_generation=7 artifact_sequence={100 + sequence}')
        return '\n'.join(lines), fixture.state()

    def test_cold_memory_retains_exact_artifact_and_native_flags_checks(self):
        text, state = self.cold_memory()
        root = dict(identity=0x100, generation=7, executor=20, family_generation=7)
        result = memory_mode.validate_memory_trace(text, root, 10, 0, state, 1)
        self.assertEqual(len(result['transactions']), 5)

    def test_cold_memory_changed_artifact_or_family_is_rejected(self):
        text, state = self.cold_memory()
        root = dict(identity=0x100, generation=7, executor=20, family_generation=7)
        for changed in (text.replace('artifact_sequence=101', 'artifact_sequence=999', 1),
                        text.replace('family_generation=7', 'family_generation=8', 1)):
            with self.subTest(changed=changed), self.assertRaises(rt.Failure):
                memory_mode.validate_memory_trace(changed, root, 10, 0, state, 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
