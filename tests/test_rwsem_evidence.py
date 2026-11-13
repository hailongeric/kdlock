"""VM-only oracle regressions from the retained kernel15 failure and explicit variants.

The retained trace is evidence from a failed runner attempt. Synthetic variants
exercise validator decisions; they are not additional kernel execution results.
"""
import ast
import copy
import hashlib
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests/kernel'))
from rwsem.reader_cases import ReaderCases
from rwsem.ordinary_evidence import ORDINARY, ordinary_lifetimes


def runner_tuple(name):
    tree = ast.parse((ROOT / 'tests/kernel/run_runtime_fixture.py').read_text())
    values = [ast.literal_eval(node.value) for node in ast.walk(tree)
              if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name
                                                      for target in node.targets)]
    if len(values) != 1:
        raise AssertionError('runner event definition is not unique')
    return values[0]


FIELDS = runner_tuple('event_fields')
KINDS = {name: index + 1 for index, name in enumerate(runner_tuple('event_names'))}


def has(row, name):
    return row['kind'] == KINDS[name]


def ordered(rows):
    return [dict(row, index=index) for index, row in enumerate(rows)]


class RwsemEvidence(unittest.TestCase):
    def setUp(self):
        data = (ROOT / 'tests/rwsem_evidence/f3b1d75b-native-readers.bin').read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         'b1a797ef0f3fb9088e05022b49072ab2943ecde6d6347903fcced69d7c93efd1')
        self.assertEqual(struct.unpack_from('=5Q', data), (1, 20, 65536, 39, 0))
        self.assertEqual(len(data), 40 + 39 * 160)
        self.assertEqual(KINDS['ORDINARY_RWSEM_DONE'], 48)
        self.trace = [dict(zip(FIELDS, struct.unpack_from('=20Q', data, 40 + index * 160)), index=index)
                      for index in range(39)]
        self.cases = ReaderCases('rwsem', None, {}, None, None, None, has, None, None, None)

    def fast_writer(self, offset=0):
        acquire = dict(self.trace[32])
        identity = acquire['acquisition'] + offset
        acquire.update(node=0, acquisition=identity, related=identity, owner=identity,
                       source_user=identity, flags=ORDINARY)
        release = dict(acquire, kind=KINDS['NATIVE_WRITE_RELEASE'])
        done = dict(self.trace[38], acquisition=identity, related=identity, flags=ORDINARY)
        return acquire, release, done

    def converted_scene(self, queued):
        if queued:
            acquire, conversion, done = copy.deepcopy([self.trace[i] for i in (32, 33, 38)])
            prefix = [self.trace[26], self.trace[27]]
            retirement = self.trace[34:38]
        else:
            acquire, conversion, done = self.fast_writer()
            prefix, retirement = [], []
        conversion.update(kind=KINDS['NATIVE_DOWNGRADE'], phase=1 if queued else 0)
        read_release = dict(conversion, kind=KINDS['NATIVE_READ_RELEASE'] if queued else KINDS['READ_RELEASE'],
                            phase=1, owner=0, node=0)
        following = self.fast_writer(0x100000)
        return ordered(prefix + [acquire, conversion, self.trace[24]] + retirement +
                       [self.trace[28], self.trace[29], read_release, done] + list(following))

    def nested_reads(self, repeated=True):
        outer = [dict(self.trace[index]) for index in (24, 28, 29)]
        inner = copy.deepcopy(outer)
        for row in inner:
            row['acquisition'] += 0x100000
            row['related'] = row['acquisition']
            if row['source_user']:
                row['source_user'] = row['acquisition']
            if not repeated:
                row['object'] += 0x1000
        return ordered([outer[0], inner[0], inner[1], inner[2], outer[1], outer[2]])

    def test_retained_failed_trace_has_two_ordinary_reads_and_retired_local_writer(self):
        reads, writers = self.cases.native_evidence(self.trace[24:], 0)
        self.assertEqual([pair['acquire']['index'] for pair in reads], [24, 25])
        self.assertTrue(all(pair['reserve'] is None and pair['ordinary_local'] for pair in reads))
        self.assertEqual(writers[0]['free']['index'], 38)
        self.assertEqual(writers[0]['queue']['departed']['index'], 35)
        all_records = ordinary_lifetimes(self.trace, has)
        self.assertEqual((len(all_records['reads']), len(all_records['writes'])), (2, 9))

    def test_successor_admission_can_precede_previous_reader_done(self):
        rows = copy.deepcopy(self.trace[24:])
        done = next(row for row in rows if row['index'] == 31)
        rows.remove(done)
        rows.insert(next(index for index, row in enumerate(rows) if row['index'] == 32) + 1, done)
        self.cases.native_evidence(ordered(rows), 0)

    def test_unrelated_exit_detail_does_not_become_an_ordinary_record_flag(self):
        detail = dict(self.trace[32], kind=KINDS['JIT_EXIT'], flags=ORDINARY, acquisition=0)
        self.cases.native_evidence(ordered(self.trace[24:] + [detail]), 0)

    def test_writer_first_readers_can_precede_writer_done(self):
        acquire, release, done = self.fast_writer()
        rows = ordered([acquire, release, self.trace[24], self.trace[25], done] + self.trace[28:32])
        self.cases.native_evidence(rows, 2)

    def test_true_downgrade_keeps_same_record_until_read_release(self):
        for queued in (False, True):
            with self.subTest(queued=queued):
                reads, writers = self.cases.native_evidence(self.converted_scene(queued), 1)
                converted = next(pair for pair in reads if 'writer_acquire' in pair)
                self.assertEqual(converted['acquire']['acquisition'], converted['release']['acquisition'])
                self.assertEqual(converted['free']['phase'], 0)
                self.assertEqual(writers[0]['queued'], queued)

    def test_nested_read_records_are_distinct_and_release_inner_first(self):
        for repeated in (False, True):
            with self.subTest(repeated=repeated):
                self.cases.native_read_pair(self.cases.credits(self.nested_reads(repeated)), repeated)
        rows = self.nested_reads()
        with self.assertRaisesRegex(AssertionError, 'latest exact open credit'):
            self.cases.credits(ordered([rows[0], rows[1], rows[4], rows[5], rows[2], rows[3]]))

    def test_completion_requires_exact_identity_and_all_final_flags(self):
        for index, field, value in ((29, 'object', 99), (29, 'state', 99), (29, 'origin', 99),
                                    (29, 'task', 99), (29, 'acquisition', 99), (29, 'related', 99),
                                    (29, 'source_user', 99), (29, 'phase', 0), (29, 'flags', 0),
                                    (38, 'flags', ORDINARY | 4), (38, 'flags', ORDINARY | 2048),
                                    (38, 'node', 99), (38, 'owner', 99)):
            rows = copy.deepcopy(self.trace[24:])
            next(row for row in rows if row['index'] == index)[field] = value
            with self.subTest(index=index, field=field, value=value), self.assertRaises(AssertionError):
                self.cases.credits(rows)

    def test_missing_duplicate_or_early_done_cannot_retire_a_record(self):
        for index in (29, 31, 38):
            rows = [row for row in self.trace[24:] if row['index'] != index]
            with self.subTest(index=index), self.assertRaises(AssertionError):
                self.cases.credits(rows)
        rows = copy.deepcopy(self.trace[24:])
        rows.append(dict(self.trace[38], index=39))
        with self.assertRaises(AssertionError):
            self.cases.credits(rows)
        rows = ordered([self.trace[24], self.trace[29], self.trace[28]])
        with self.assertRaises(AssertionError):
            self.cases.credits(rows)

    def test_local_mcs_writer_needs_actual_queue_and_physical_retirement(self):
        for index in (26, 27, 34, 35, 36, 37):
            rows = [row for row in self.trace[24:] if row['index'] != index]
            with self.subTest(missing=index), self.assertRaises(AssertionError):
                self.cases.native_evidence(rows, 0)
        for index, field in ((26, 'node'), (27, 'owner'), (35, 'acquisition'),
                             (36, 'related'), (37, 'task')):
            rows = copy.deepcopy(self.trace[24:])
            next(row for row in rows if row['index'] == index)[field] += 1
            with self.subTest(index=index, field=field), self.assertRaises(AssertionError):
                self.cases.native_evidence(rows, 0)

    def test_native_writer_cannot_enter_before_last_read_release(self):
        rows = copy.deepcopy(self.trace[24:])
        acquire = next(row for row in rows if row['index'] == 32)
        rows.remove(acquire)
        rows.insert(next(index for index, row in enumerate(rows) if row['index'] == 30), acquire)
        with self.assertRaisesRegex(AssertionError, 'before the last exact reader'):
            self.cases.native_evidence(ordered(rows), 0)

    def test_conversion_rejects_new_identity_or_write_release_in_read_tail(self):
        for queued in (False, True):
            for mutation in ('identity', 'release_kind', 'phase'):
                rows = self.converted_scene(queued)
                converted = next(row for row in rows if has(row, 'NATIVE_DOWNGRADE'))
                release = next(row for row in rows if row['acquisition'] == converted['acquisition']
                               and (has(row, 'READ_RELEASE') or has(row, 'NATIVE_READ_RELEASE')))
                if mutation == 'identity':
                    converted['acquisition'] += 1
                elif mutation == 'release_kind':
                    release['kind'] = KINDS['NATIVE_WRITE_RELEASE']
                else:
                    release['phase'] = 0
                with self.subTest(queued=queued, mutation=mutation), self.assertRaises(AssertionError):
                    self.cases.native_evidence(rows, 1)

    def test_ordinary_record_cannot_be_lent_or_reused_before_done(self):
        acquire, release, done = [dict(self.trace[index]) for index in (24, 28, 29)]
        for kind in ('SELECT_PROXY', 'JIT_ENTER'):
            event = dict(acquire, kind=KINDS[kind], flags=0)
            with self.subTest(kind=kind), self.assertRaises(AssertionError):
                self.cases.credits(ordered([acquire, event, release, done]))
        with self.assertRaisesRegex(AssertionError, 'reused before final'):
            self.cases.credits(ordered([acquire, release, acquire, done]))

    def test_managed_inner_read_still_requires_its_real_reservation(self):
        outer = [dict(self.trace[index]) for index in (24, 28, 29)]
        acquired = dict(outer[0], flags=0, acquisition=101, related=102, source_user=103)
        released = dict(acquired, kind=KINDS['READ_RELEASE'])
        reserve = dict(acquired, kind=KINDS['SLOT_RESERVE'], node=104, related=105, owner=106, parent=107)
        freed = dict(reserve, kind=KINDS['SLOT_FREE'], flags=32 | 64, source_user=0)
        rows = ordered([outer[0], reserve, acquired, released, freed, outer[1], outer[2]])
        pairs = self.cases.credits(rows)
        self.assertIsNotNone(pairs[0]['reserve'])
        self.assertTrue(pairs[1]['ordinary_local'])
        with self.assertRaisesRegex(AssertionError, 'preceding request reservation'):
            self.cases.credits([row for row in rows if not has(row, 'SLOT_RESERVE')])

    def test_legacy_fast_read_still_needs_its_own_exact_done(self):
        acquire, release, done = [dict(self.trace[index], flags=8192) for index in (24, 28, 29)]
        done['kind'] = KINDS['FAST_READ_DONE']
        self.assertTrue(self.cases.credits(ordered([acquire, release, done]))[0]['fast_local'])
        with self.assertRaises(AssertionError):
            self.cases.credits(ordered([acquire, release]))


if __name__ == '__main__':
    unittest.main()
