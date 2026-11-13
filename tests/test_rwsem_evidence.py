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
from rwsem.scene_evidence import scene6_ordering


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


class RwsemSceneOrdering(unittest.TestCase):
    """The positive ordering is synthetic; the old live scene remains failed."""

    def setUp(self):
        data = (ROOT / 'tests/rwsem_evidence/f3b1d75b-reader-scene6.bin').read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         'c01371d4ca68bbff9f02b8acf9063d5fb41d5193460f2a9b881c98dcf651a65b')
        self.assertEqual(struct.unpack_from('=5Q', data), (1, 20, 65536, 1149, 0))
        self.assertEqual(len(data), 40 + 1149 * 160)
        self.trace = [dict(zip(FIELDS, struct.unpack_from('=20Q', data, 40 + index * 160)), index=index)
                      for index in range(1149)]
        self.tasks = [self.trace[index]['task'] for index in (1078, 1079, 1082, 1088, 1085)]
        self.object_a = self.trace[1078]['object']
        self.image = self.trace[1084]['image']

    def synthetic(self, done_after_grant=False):
        # H_B's prelude uses actual ordinary row shapes, with a distinct cold
        # identity. H_A's queued rows use the retained C_A request shapes.
        reader = [dict(self.trace[index], task=self.tasks[1], origin=self.tasks[1],
                       state=self.trace[1079]['state']) for index in (24, 28, 29)]
        for row in reader:
            if row['owner_task']:
                row['owner_task'] = self.tasks[1]
        holder = [dict(self.trace[index]) for index in (1080, 1081, 1082, 1091, 1093)]
        for row in holder:
            row.update(task=self.tasks[0], origin=self.tasks[0], state=0x1000,
                       node=0x1100, acquisition=0x1200)
            if row['owner_task']:
                row['owner_task'] = self.tasks[0]
            if row['owner']:
                row['owner'] = 0x1300
        holder[0]['related'], holder[0]['parent'] = 0x1400, 0x1200
        holder[2]['related'], holder[3]['related'], holder[4]['related'] = 0, 0x1100, 0x1500
        candidate = [dict(self.trace[index]) for index in (1080, 1081, 1082)]
        candidate[-1]['related'] = holder[2]['node']
        waiter = [dict(self.trace[index]) for index in (1083, 1084, 1085)]
        middle = ([reader[2]] + holder[3:] if not done_after_grant
                  else holder[3:] + [reader[2]])
        prefix = ordered([reader[0]] + holder[:3] + [reader[1]] + middle + candidate + waiter)
        released = dict(self.trace[1096], task=self.tasks[0], state=0x1000,
                        acquisition=0x1200, owner=0x1300, owner_task=self.tasks[0], related=0x1500)
        departed = dict(self.trace[1100], task=self.tasks[0], origin=self.tasks[0], state=0x1000,
                        node=0x1100, acquisition=0x1200, owner=0x1300, owner_task=self.tasks[0],
                        related=candidate[-1]['node'])
        selected = dict(self.trace[1107], kind=KINDS['SELECT_PROXY'], task=self.tasks[2],
                        owner_task=self.tasks[2], related=candidate[-1]['node'], phase=3)
        return prefix, ordered(prefix + [released, departed, selected])

    def check(self, rows, before_release=True):
        return scene6_ordering(rows, has, self.tasks, self.object_a, self.image,
                               before_release=before_release)

    def test_retained_scene6_did_not_have_a_queue_backed_holder(self):
        rows = self.trace[1078:]
        self.assertEqual(self.trace[1082]['related'], 0)
        self.assertEqual(self.trace[1085]['related'], self.trace[1082]['node'])
        self.assertEqual(self.trace[1085]['phase'], 1)
        self.assertFalse(any(has(row, 'SELECT_PROXY') or has(row, 'JIT_ENTER') for row in rows))
        with self.assertRaisesRegex(AssertionError, 'ordinary prelude acquisition'):
            self.check(rows, before_release=False)

    def test_prelude_done_and_holder_grant_both_precede_candidate(self):
        for delayed_done in (False, True):
            with self.subTest(delayed_done=delayed_done):
                prefix, complete = self.synthetic(delayed_done)
                proof = self.check(prefix)
                self.assertLess(proof['reader']['free']['index'], proof['candidate']['index'])
                self.assertLess(proof['grant']['index'], proof['candidate']['index'])
                self.assertEqual(self.check(complete, before_release=False)['proxy_selected']['task'],
                                 self.tasks[2])

    def test_prelude_requires_exact_read_completion_and_holder_grant(self):
        prefix, _ = self.synthetic()
        for kind in ('ORDINARY_RWSEM_DONE', 'READ_RELEASE', 'GRANT', 'SELECT_LOCAL', 'FRAME_PREPARE'):
            with self.subTest(missing=kind), self.assertRaises(AssertionError):
                self.check([row for row in prefix if not has(row, kind)])
        for field in ('state', 'origin', 'acquisition', 'object', 'related', 'phase', 'flags'):
            rows = copy.deepcopy(prefix)
            next(row for row in rows if has(row, 'ORDINARY_RWSEM_DONE'))[field] += 1
            with self.subTest(field=field), self.assertRaises(AssertionError):
                self.check(rows)

    def test_prelude_record_may_be_reused_only_after_its_exact_done(self):
        prefix, _ = self.synthetic()
        read = next(row for row in prefix if has(row, 'READ_ACQUIRE'))
        reused = dict(self.trace[1079], acquisition=read['acquisition'], related=read['acquisition'],
                      owner=read['acquisition'], source_user=read['acquisition'], state=read['state'])
        # H_B's later B grant stays open while the prelude itself is verified.
        self.check(ordered(prefix + [reused]))
        rows = copy.deepcopy(prefix)
        rows.insert(next(i for i, row in enumerate(rows) if has(row, 'ORDINARY_RWSEM_DONE')), reused)
        with self.assertRaisesRegex(AssertionError, 'reused before final'):
            self.check(ordered(rows))

    def test_wrong_predecessor_offer_identity_or_image_cannot_prove_queue(self):
        prefix, _ = self.synthetic()
        for task in (self.tasks[2], self.tasks[4]):
            for field, value in (('related', 0), ('node', 0), ('state', 0), ('acquisition', 0),
                                  ('phase', 2), ('flags', 1)):
                rows = copy.deepcopy(prefix)
                next(row for row in rows if has(row, 'ENQUEUE') and row['task'] == task)[field] = value
                with self.subTest(task=task, field=field), self.assertRaises(AssertionError):
                    self.check(rows)
            rows = copy.deepcopy(prefix)
            next(row for row in rows if has(row, 'FRAME_PREPARE') and row['task'] == task)['image'] += 1
            with self.subTest(task=task, field='image'), self.assertRaises(AssertionError):
                self.check(rows)
            duplicated = next(row for row in prefix if has(row, 'ENQUEUE') and row['task'] == task)
            with self.subTest(task=task, duplicate_offer=True), self.assertRaises(AssertionError):
                self.check(ordered(prefix + [duplicated]))

    def test_candidate_cannot_start_before_reader_retirement_or_holder_grant(self):
        prefix, _ = self.synthetic()
        for kind in ('ORDINARY_RWSEM_DONE', 'GRANT'):
            rows = copy.deepcopy(prefix)
            moved = next(row for row in rows if has(row, kind))
            rows.remove(moved)
            rows.append(moved)
            with self.subTest(kind=kind), self.assertRaises(AssertionError):
                self.check(ordered(rows))

    def test_early_holder_release_and_local_successor_do_not_satisfy_proxy_proof(self):
        prefix, complete = self.synthetic()
        with self.assertRaisesRegex(AssertionError, 'before the release gate'):
            self.check(complete)
        for field, value in (('kind', KINDS['SELECT_LOCAL']), ('task', self.tasks[4]),
                              ('related', 0), ('acquisition', 1)):
            rows = copy.deepcopy(complete)
            rows[-1][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                self.check(rows, before_release=False)
        for position in (0, len(prefix) - 1):
            rows = copy.deepcopy(complete)
            release = rows.pop(len(prefix))
            rows.insert(position, release)
            with self.subTest(position=position), self.assertRaises(AssertionError):
                self.check(ordered(rows), before_release=False)
        for kind, field in (('RELEASE_REQUEST', 'owner'), ('RELEASE_REQUEST', 'related'),
                             ('QUEUE_DONE', 'related'), ('QUEUE_DONE', 'acquisition'),
                             ('QUEUE_DONE', 'owner_task'), ('QUEUE_DONE', 'phase')):
            rows = copy.deepcopy(complete)
            next(row for row in rows if has(row, kind))[field] += 1
            with self.subTest(kind=kind, field=field), self.assertRaises(AssertionError):
                self.check(rows, before_release=False)


class RwsemReadPromotionEvidence(unittest.TestCase):
    """Synthetic provider transitions; no generated execution is claimed here."""

    def setUp(self):
        self.cases = ReaderCases('rwsem', None, {}, None, None, None, has, None, None, None)

    def synthetic(self):
        def row(name, **values):
            return dict(dict.fromkeys(FIELDS, 0), kind=KINDS[name], **values)
        identity = dict(task=10, origin=10, state=20, object=30, acquisition=40)
        acquire = row('READ_ACQUIRE', **identity, related=40, source_user=40,
                      owner_task=10, flags=ORDINARY, phase=1)
        prepared = row('FRAME_PREPARE', task=10, origin=10, state=20, node=60,
                       acquisition=70, image=80, phase=3)
        promotion = row('READ_PROMOTE', **identity, related=50, source_user=40,
                        node=60, parent=70, image=80, phase=1, flags=ORDINARY)
        writer = row('ENQUEUE', task=10, origin=10, state=20, node=60, acquisition=70,
                     object=90, phase=1, flags=17)
        selected = dict(writer, kind=KINDS['SELECT_PROXY'], task=13, phase=3)
        entered = dict(writer, kind=KINDS['JIT_ENTER'], task=13, image=80)
        released = row('READ_RELEASE', **identity, related=50, source_user=40, phase=1)
        done = row('ORDINARY_RWSEM_DONE', **identity, related=40, flags=ORDINARY, phase=1)
        return ordered([acquire, prepared, promotion, writer, selected, entered, released, done])

    def test_exact_transfer_keeps_one_read_through_foreign_writer_and_native_release(self):
        rows = self.synthetic()
        pairs = self.cases.credits(rows)
        self.assertEqual(len(pairs), 1)
        self.assertTrue(pairs[0]['promoted_read'])
        self.assertFalse(pairs[0]['ordinary_local'])
        self.assertEqual(pairs[0]['acquire']['acquisition'], pairs[0]['release']['acquisition'])
        proof = dict(mode=7, fixed_image=80, state=20, roles=[1, 2, 3, 13, 10],
                     entries=[rows[5]], credits=pairs, writer=rows[3])
        result = self.cases.validate_source_scene(proof, rows, dict(object_a='1e', object_b='5a'))
        self.assertEqual(result['outer_read_promotion']['free'], rows[-1])

    def test_missing_promotion_does_not_make_local_read_eligible(self):
        rows = [row for row in self.synthetic() if not has(row, 'READ_PROMOTE')]
        with self.assertRaises(AssertionError):
            self.cases.credits(rows)

    def test_promotion_requires_exact_original_owner_credit_and_writer(self):
        for field in ('task', 'origin', 'state', 'object', 'acquisition', 'source_user',
                      'node', 'parent', 'image', 'phase', 'flags'):
            rows = self.synthetic()
            rows[2][field] += 1
            with self.subTest(field=field), self.assertRaises(AssertionError):
                self.cases.credits(rows)
        for kind in ('FRAME_PREPARE', 'ENQUEUE'):
            with self.subTest(missing=kind), self.assertRaises(AssertionError):
                self.cases.credits([row for row in self.synthetic() if not has(row, kind)])

    def test_release_requires_original_task_and_exact_promoted_credit(self):
        for field in ('task', 'origin', 'state', 'acquisition', 'related', 'source_user', 'flags'):
            rows = self.synthetic()
            rows[6][field] += 1
            with self.subTest(field=field), self.assertRaises(AssertionError):
                self.cases.credits(rows)

    def test_repeated_promotion_release_or_premature_completion_is_rejected(self):
        for index in (0, 2, 6):
            rows = self.synthetic()
            rows.insert(index + 1, dict(rows[index]))
            with self.subTest(duplicate=index), self.assertRaises(AssertionError):
                self.cases.credits(ordered(rows))
        rows = self.synthetic()
        rows[6], rows[7] = rows[7], rows[6]
        with self.assertRaises(AssertionError):
            self.cases.credits(ordered(rows))

    def test_original_task_cannot_serve_a_foreign_source_while_read_is_promoted(self):
        rows = self.synthetic()
        rows[4]['task'], rows[4]['origin'] = 10, 99
        with self.assertRaises(AssertionError):
            self.cases.credits(rows)

    def test_scene_still_requires_selected_inner_writer_and_live_read_interval(self):
        rows = self.synthetic()
        pairs = self.cases.credits(rows)
        proof = dict(mode=7, fixed_image=80, state=20, roles=[1, 2, 3, 13, 10],
                     entries=[rows[5]], credits=pairs, writer=rows[3])
        with self.assertRaises(AssertionError):
            self.cases.validate_source_scene(copy.deepcopy(proof),
                [row for row in rows if not has(row, 'SELECT_PROXY')], dict(object_a='1e', object_b='5a'))
        proof['entries'] = [dict(rows[5], index=rows[6]['index'] + 1)]
        with self.assertRaises(AssertionError):
            self.cases.validate_source_scene(proof, rows, dict(object_a='1e', object_b='5a'))


if __name__ == '__main__':
    unittest.main()
