"""Focused MM controller rejection checks. Execute only in the designated VM."""
import copy
import contextlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

import linux70_mm as controller
import mm_archive
import mm_plan
import mm_report


class PlanTests(unittest.TestCase):
    def full(self, suite):
        return [dict(row, repeat=0, observation='plain', duration_ms=2000,
                     cpus=list(range(row['threads'])), collector_cpu=63, collector_shared=False)
                for row in mm_plan.coordinates(suite)]

    def test_exact_private84_and_shared42(self):
        for suite, count in [('independent-mmap', 21), ('private-fault', 63), ('shared-native', 21), ('shared-kd', 21)]:
            plan = self.full(suite)
            self.assertEqual(len(plan), count)
            self.assertEqual(mm_plan.select(suite, plan, mm_plan.coordinates(suite)), plan)
            self.assertTrue(all(row['threads'] <= 60 for row in plan))
        self.assertEqual(len(mm_plan.coordinates('shared-mm')), 42)

    def test_subset_cannot_change_work_duration_cpu_or_repetition(self):
        for field, value in [('repeat', 1), ('duration_ms', 1000), ('observation', 'sampled'),
                             ('collector_cpu', 0), ('cpus', [63]), ('collector_shared', True)]:
            plan = self.full('private-fault'); plan[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                mm_plan.select('private-fault', plan, mm_plan.coordinates('private-fault')[3:])
        plan = self.full('private-fault')
        for selected in ([], [plan[0], plan[0]], plan[:3][::-1], [dict(plan[0], threads=64)]):
            with self.assertRaises(ValueError):
                mm_plan.select('private-fault', plan, selected)

    def test_empty_failed_directory_and_announced_coordinate_are_attempted(self):
        selected = mm_plan.coordinates('private-fault')
        first = mm_plan.session_name('private-fault', 0, selected[0])
        second = mm_plan.session_name('private-fault', 1, selected[1])
        inventory = {first: dict(kind='directory'), 'kernel-baseline': dict(kind='directory')}
        attempted = mm_plan.attempted_coordinates('private-fault', selected, inventory, 'START ' + second + '\n')
        self.assertEqual(attempted, selected[:2])
        self.assertEqual(mm_plan.remaining('private-fault', attempted), selected[2:])
        with self.assertRaises(ValueError):
            mm_plan.attempted_coordinates('private-fault', selected, {'workspace': dict(kind='directory')}, '')
        with self.assertRaises(ValueError):
            mm_plan.attempted_coordinates('private-fault', selected, {}, 'START unknown-coordinate\n')

    def test_duplicate_or_foreign_previous_coordinates_are_not_retried(self):
        selected = mm_plan.coordinates('independent-mmap')
        for prior in ([selected[0], selected[0]], [dict(selected[0], arm='kdlock')]):
            with self.assertRaises(ValueError): mm_plan.remaining('independent-mmap', prior)

    def test_different_boot_or_snapshot_cannot_restart_a_previously_attempted_suite(self):
        context = dict(boot_id='boot', snapshot='snapshot', mode='private')
        index = [dict(action='private-fault', suite='private-fault', context=context)]
        self.assertEqual(controller.existing_attempts(index,'private-fault',context,'private-fault'),index)
        for change in (dict(boot_id='other'),dict(snapshot='other')):
            with self.assertRaises(ValueError):
                controller.existing_attempts(index,'private-fault',dict(context,**change),'private-fault')

    def test_review_binds_all_attempt_bytes_boot_and_exact_remaining_grid(self):
        context = dict(mode='private', boot_id='boot', snapshot='snapshot')
        first = mm_plan.coordinates('private-fault')[0]
        attempt = dict(name='attempt', result_sha256='result', archive_sha256='archive', preservation_sha256='inventory',
                       session_receipts={}, attempted_coordinates=[first], preserved='/retained',
                       completion_confirmed=True, drained=True)
        fields = ('name', 'result_sha256', 'archive_sha256', 'preservation_sha256', 'session_receipts', 'attempted_coordinates')
        review = dict(schema=1, approved=True, purpose='resume-unmeasured-mm-coordinates', suite='private-fault',
                      campaign='campaign', context=context, source_manifest_sha256='source',
                      prior_attempts=[{key: attempt[key] for key in fields}],
                      coordinates=mm_plan.coordinates('private-fault')[1:])
        check = lambda r, a: controller.validate_review(r, 'private-fault', 'campaign', context, 'source', [a])
        self.assertEqual(check(review, attempt), review['coordinates'])
        for change in (dict(approved=False), dict(context=dict(context, boot_id='other')),
                       dict(source_manifest_sha256='changed'), dict(prior_attempts=[]),
                       dict(coordinates=mm_plan.coordinates('private-fault'))):
            with self.assertRaises(ValueError): check(dict(review, **change), attempt)
        for change in (dict(completion_confirmed=False), dict(drained=False)):
            with self.assertRaises(ValueError): check(review, dict(attempt, **change))


class ArchiveTests(unittest.TestCase):
    def test_actual_phase_validator_checks_source_prepared_runtime_and_binary_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); output=root/'phase'; output.mkdir()
            manifest=root/'source-manifest.json';manifest.write_text(json.dumps(dict(files={})))
            (output/'result.json').write_text('{}')
            entries={'source-sha256.json': ('source/input.c','input.c'),
                     'prepared-source-sha256.json': ('build/provider/prepared.c','prepared.c'),
                     'binary-sha256.json': ('client','client'),
                     'runtime-source-sha256.json': ('runtime.py',str(output/'runtime.py'))}
            for name,(target,entry) in entries.items():
                path=output/target;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'original')
                (output/name).write_text(json.dumps({entry:controller.sha(path)}))
            instance=controller.Controller.__new__(controller.Controller)
            instance.guest,instance.manifest,instance.manifest_sha,instance.env=root,manifest,controller.sha(manifest),[]
            def remote(label,argv,**kwargs):
                with contextlib.redirect_stdout(io.StringIO()):
                    exec(compile(kwargs['code'],'<actual-phase-validator>','exec'),{})
            instance.remote=remote
            instance.check_sources('check',output,required_manifests=tuple(entries))
            for name,(target,_) in entries.items():
                path=output/target;path.write_bytes(b'changed')
                with self.subTest(manifest=name),self.assertRaises(AssertionError):
                    instance.check_sources('check',output,required_manifests=tuple(entries))
                path.write_bytes(b'original')
            (output/'binary-sha256.json').unlink()
            with self.assertRaises(AssertionError):
                instance.check_sources('check',output,required_manifests=tuple(entries))

    def preserve(self, root, members, expected):
        instance = controller.Controller.__new__(controller.Controller)
        instance.raw, instance.env = root, []
        def remote(label, argv, **kwargs):
            target = root / (label + '.stdout')
            if 'inventory' in label:
                target.write_text(json.dumps(expected))
            else:
                with tarfile.open(target, 'w:gz') as archive:
                    for name, data, kind in members:
                        member = tarfile.TarInfo(name)
                        if kind == 'directory': member.type = tarfile.DIRTYPE; member.mode=0o755; archive.addfile(member)
                        elif kind == 'link': member.type = tarfile.SYMTYPE; member.mode=0o777; member.linkname = data; archive.addfile(member)
                        else:
                            member.size = len(data); archive.addfile(member, io.BytesIO(data))
        instance.remote = remote
        return instance.preserve('saved', Path('/guest/attempt'))

    def fixture(self):
        import hashlib
        return {'empty': dict(kind='directory', mode=16877),
                'result.json': dict(kind='file', sha256=hashlib.sha256(b'{}').hexdigest(), bytes=2, mode=33188, mtime_ns=1),
                'external': dict(kind='link', target='/outside/source', mode=41471)}

    def test_complete_archive_keeps_empty_directories_and_unmaterialized_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            saved = self.preserve(root, [('attempt', b'', 'directory'), ('attempt/empty', b'', 'directory'),
                        ('attempt/result.json', b'{}', 'file'), ('attempt/external', '/outside/source', 'link')], self.fixture())
            self.assertEqual((saved / 'result.json').read_bytes(), b'{}')
            self.assertFalse((saved / 'external').exists())
            receipt = json.loads((saved / 'preservation.json').read_text())
            self.assertEqual(receipt['inventory'], self.fixture())
            row = dict(name='saved', preserved=str(saved), archive_sha256=controller.sha(root/'saved-archive.stdout'),
                       result_sha256=controller.sha(saved/'result.json'), preservation_sha256=controller.sha(saved/'preservation.json'))
            controller.verify_preservation(row, root)
            (saved / 'result.json').write_bytes(b'{"changed":true}')
            with self.assertRaises(ValueError): controller.verify_preservation(row, root)

    def test_unsafe_duplicate_omitted_or_changed_archive_members_fail(self):
        good = [('attempt/empty', b'', 'directory'), ('attempt/result.json', b'{}', 'file'),
                ('attempt/external', '/outside/source', 'link')]
        variants = [good + [('attempt/../../escape', b'bad', 'file')], good + [good[1]], good[:-1],
                    [good[0], ('attempt/result.json', b'bad', 'file'), good[2]]]
        for members in variants:
            with tempfile.TemporaryDirectory() as temporary, self.assertRaises(ValueError):
                self.preserve(Path(temporary), members, self.fixture())

    def test_inventory_detects_new_partial_workspace_or_binary_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root/'client').write_bytes(b'original'); (root/'empty').mkdir()
            before = mm_archive.inventory(root)
            (root/'client').write_bytes(b'changed')
            self.assertNotEqual(mm_archive.inventory(root), before)
            self.assertEqual(before['empty']['kind'], 'directory')


class EndpointHealthTests(unittest.TestCase):
    def fixture(self, root):
        health = dict(idle=True, boot_id='current-boot', release='7.0.0-38-kdmm1',
                      modules='', dmesg='', taint=0, root_free=100, data_free=200)
        command = dict(returncode=0, completion_unconfirmed=False)
        capture, receipt = root/'health.stdout', root/'health-command.json'
        capture.write_text(json.dumps(health)); receipt.write_text(json.dumps(command))
        return capture, receipt, health, command

    def checked(self, capture, receipt):
        return controller.parse_health_capture(capture, receipt, boot_id='current-boot',
                                               release='7.0.0-38-kdmm1')

    def test_complete_same_boot_idle_capture_is_accepted_without_reinterpreting_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture, receipt, health, _ = self.fixture(Path(temporary))
            self.assertEqual(self.checked(capture, receipt), health)
            health.update(root_free=0, data_free=0)
            capture.write_text(json.dumps(health))
            self.assertEqual(self.checked(capture, receipt), health)

    def test_missing_empty_malformed_or_nonobject_endpoint_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for which in ('health', 'command'):
                for invalid in (None, '', '{', 'null', '[]', 'true', '0'):
                    with self.subTest(which=which, invalid=invalid):
                        capture, receipt, _, _ = self.fixture(root)
                        selected = capture if which == 'health' else receipt
                        if invalid is None:
                            selected.unlink()
                        else:
                            selected.write_text(invalid)
                        with self.assertRaises(ValueError):
                            self.checked(capture, receipt)

    def test_foreign_boot_release_and_nonliteral_idle_do_not_prove_drain(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for key, value in (('boot_id', 'previous-boot'), ('release', '7.0.0-38-kdlock1'),
                               ('idle', False), ('idle', 1), ('idle', 'true'), ('idle', None)):
                with self.subTest(key=key, value=value):
                    capture, receipt, health, _ = self.fixture(root)
                    health[key] = value; capture.write_text(json.dumps(health))
                    with self.assertRaises(ValueError):
                        self.checked(capture, receipt)
            capture, receipt, health, _ = self.fixture(root)
            del health['boot_id']; capture.write_text(json.dumps(health))
            with self.assertRaises(ValueError):
                self.checked(capture, receipt)

    def test_incomplete_or_invalid_health_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for key in ('modules', 'dmesg', 'taint', 'root_free', 'data_free'):
                invalids = (None, [], 0) if key in ('modules', 'dmesg') else (None, True, -1, '0', 0.0)
                for value in invalids:
                    with self.subTest(key=key, value=value):
                        capture, receipt, health, _ = self.fixture(root)
                        health[key] = value; capture.write_text(json.dumps(health))
                        with self.assertRaises(ValueError):
                            self.checked(capture, receipt)
                capture, receipt, health, _ = self.fixture(root)
                del health[key]; capture.write_text(json.dumps(health))
                with self.subTest(missing=key), self.assertRaises(ValueError):
                    self.checked(capture, receipt)

    def test_failed_unknown_or_unconfirmed_capture_command_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            changes = [dict(returncode=value) for value in (1, 255, None, False, '0')]
            changes += [dict(completion_unconfirmed=value) for value in (True, None, 0)]
            for change in changes:
                with self.subTest(change=change):
                    capture, receipt, _, command = self.fixture(root)
                    command.update(change); receipt.write_text(json.dumps(command))
                    with self.assertRaises(ValueError):
                        self.checked(capture, receipt)
            for key in ('returncode', 'completion_unconfirmed'):
                capture, receipt, _, command = self.fixture(root)
                del command[key]; receipt.write_text(json.dumps(command))
                with self.subTest(missing=key), self.assertRaises(ValueError):
                    self.checked(capture, receipt)

    def test_guest_failure_remains_primary_when_endpoint_stdout_is_empty(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture, receipt, _, _ = self.fixture(Path(temporary))
            capture.write_text('')
            row = dict(name='shared-mapping', drained=False)
            controller.record_phase_exit(row, dict(returncode=1, completion_unconfirmed=False))
            with self.assertRaises(ValueError) as failure:
                self.checked(capture, receipt)
            controller.stop_phase(row, failure.exception)
            self.assertEqual(row['state'], 'STOPPED')
            self.assertTrue(row['completion_confirmed'])
            self.assertFalse(row['drained'])
            self.assertEqual(row['primary_failure']['kind'], 'GUEST_EXIT')
            self.assertEqual(row['primary_failure']['returncode'], 1)
            self.assertEqual(row['primary_failure']['stdout'], 'shared-mapping.stdout')
            self.assertEqual(row['primary_failure']['stderr'], 'shared-mapping.stderr')
            self.assertEqual(row['primary_failure']['command_receipt'], 'shared-mapping-command.json')
            self.assertEqual(row['error'], row['primary_failure']['error'])
            self.assertIn('guest phase exited with status 1', row['error'])
            self.assertIn('unreadable endpoint evidence', row['secondary_error'])

    def test_successful_phase_or_transport_failure_does_not_invent_drain(self):
        for returncode, confirmed in ((0, True), (255, False)):
            with self.subTest(returncode=returncode):
                row = dict(name='phase', drained=False)
                controller.record_phase_exit(row, dict(returncode=returncode))
                self.assertEqual(row['completion_confirmed'], confirmed)
                self.assertNotIn('primary_failure', row)
                controller.stop_phase(row, ValueError('endpoint unavailable'))
                self.assertEqual(row['state'], 'STOPPED')
                self.assertFalse(row['drained'])
                self.assertIn('endpoint unavailable', row['error'])
                self.assertNotIn('secondary_error', row)


class PublicationTests(unittest.TestCase):
    def test_missing_or_failed_points_never_receive_rates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); session = root/'00-mmap-1-native-plain-r0'; session.mkdir()
            row = dict(mm_plan.coordinates('independent-mmap')[0], passed=True, drained=True, state='COMPLETE',
                       measurement=dict(completed=2000, errors=0, delegated=False, execution='NATIVE_MMAP_ONLY'))
            (session/'result.json').write_text(json.dumps(row))
            (session/'client.jsonl').write_text(json.dumps({'event':'ready'})+'\n'+json.dumps(
                dict(complete=True,data_ok=True,completed=2000,wall_ns=2000000000))+'\n')
            attempt = dict(preserved=str(root),name='attempt',endpoint_checked=True,
                           attempted_coordinates=mm_plan.coordinates('independent-mmap')[:2])
            rows = mm_report.rows('independent-mmap',[attempt])
            self.assertEqual(rows[0]['whole_mops_s'],.001)
            self.assertEqual(rows[1]['status'],'ATTEMPTED_NO_RECEIPT')
            self.assertEqual(rows[2]['status'],'NOT_RUN')
            self.assertTrue(all(row['whole_mops_s'] is None for row in mm_report.rows('independent-mmap',[dict(attempt,endpoint_checked=False)])))
            row['passed']=False;row['state']='FAILED';(session/'result.json').write_text(json.dumps(row))
            self.assertIsNone(mm_report.rows('independent-mmap',[attempt])[0]['whole_mops_s'])
            with self.assertRaises(ValueError): mm_report.rows('independent-mmap',[attempt,attempt])

    def test_telemetry_requires_all64_cpus_samples_and_clean_completion(self):
        rows = [dict(event='start',thermal={}), dict(event='sample',policy_ok=True,monotonic_ns=1,
                cpus=[dict(cpu=i) for i in range(64)]), dict(event='complete',stop_requested=True,samples=1,thermal={})]
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'frequency.jsonl'
            path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
            self.assertEqual(controller.checked_telemetry(path)['samples'],1)
            for mutation in (lambda r:r[1]['cpus'].pop(), lambda r:r[1].update(policy_ok=False),
                             lambda r:r[-1].update(stop_requested=False), lambda r:r.pop(1)):
                changed=copy.deepcopy(rows);mutation(changed)
                path.write_text(''.join(json.dumps(row)+'\n' for row in changed))
                with self.assertRaises(ValueError): controller.checked_telemetry(path)


if __name__ == '__main__':
    unittest.main()
