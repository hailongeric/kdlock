"""Focused VM-only site/readiness checks for the unchanged application controller."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('mmap1_delegated_unit', ROOT / 'tests/kernel/mmap1_identity/delegated.py')
controller = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(controller)


class Sites(unittest.TestCase):
    def test_merged_rodata_and_equal_bound_aliases_keep_exact_site_set(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'vmlinux').write_text('exact built ELF identity')
            path = base / 'sites.json'
            audit = dict(schema=1, kernel_component_source_commit=controller.KERNEL_COMPONENT,
                vmlinux=dict(path='/host/vmlinux', bytes=(base / 'vmlinux').stat().st_size,
                    sha256=controller.rt.digest(base / 'vmlinux'), build_id=controller.KERNEL_BUILD_ID),
                section=dict(name='.rodata', start=0x3000, end=0x3030, sha256='a' * 64),
                records=[dict(entry=0x1000, operation=3, reserved=0, function='mmap_alias',
                              aliases=['mmap_alias', 'vm_mmap_pgoff']),
                         dict(entry=0x2000, operation=3, reserved=0, function='__vm_munmap', aliases=['__vm_munmap']),
                         dict(entry=0x2100, operation=1, reserved=0, function='other_writer', aliases=['other_writer'])],
                entry_sites=dict(mmap=[0x1000], munmap=[0x2000]))
            args = argparse.Namespace(sites=path, kernel_source=base)
            binding = dict(build_id=controller.KERNEL_BUILD_ID, build_files={'vmlinux': audit['vmlinux']['sha256']})
            def check(value):
                path.write_text(json.dumps(value))
                args.sites_sha256 = controller.rt.digest(path)
                return controller.site_audit(args, binding)
            self.assertEqual(check(audit)['section']['name'], '.rodata')
            changes = (lambda x: x['section'].update(end=0x3040),
                       lambda x: x['records'][2].update(entry=0x1000),
                       lambda x: x['records'][1].update(operation=7),
                       lambda x: x['records'][0].update(aliases=['different']),
                       lambda x: x['entry_sites'].update(mmap=[0x2100]),
                       lambda x: x['vmlinux'].update(build_id='different'),
                       lambda x: x['vmlinux'].update(bytes=1),
                       lambda x: x.update(kernel_component_source_commit='0' * 40))
            for change in changes:
                bad = copy.deepcopy(audit)
                change(bad)
                with self.assertRaises(controller.rt.Failure):
                    check(bad)


class Readiness(unittest.TestCase):
    def test_reached_readiness_needs_no_image_or_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            item = controller.Controller.__new__(controller.Controller)
            item.args = SimpleNamespace(execution_mode='reached')
            item.model = Path(directory)
            values = dict(service_reached='Y', reached_stats=' '.join(f'{key}=0' for key in controller.reached.STATS))
            with patch.object(controller.rt, 'parameters', return_value=values), \
                 patch.object(controller.rt, 'registry', return_value=[]), \
                 patch.object(controller.rt, 'status', return_value=dict(state=0, frames=0, writers=0)), \
                 patch.object(controller.bench.execution, 'device_writers', return_value=[]):
                self.assertEqual(item.ready_reached(), [])
                with patch.object(controller.rt, 'registry', return_value=[dict(status=0)]), self.assertRaises(controller.rt.Failure):
                    item.ready_reached()
                with patch.object(controller.bench.execution, 'device_writers', return_value=[dict(pid=700)]), self.assertRaises(controller.rt.Failure):
                    item.ready_reached()
                with patch.object(controller.rt, 'status', return_value=dict(state=0, frames=1, writers=0)), self.assertRaises(controller.rt.Failure):
                    item.ready_reached()

    def test_all_sites_actual_preparer_and_complete_publication_before_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            item = controller.Controller.__new__(controller.Controller)
            item.model = Path(directory)
            item.audit = dict(records=[dict(entry=0x1000), dict(entry=0x2000)])
            daemon = SimpleNamespace(daemon=SimpleNamespace(pid=700, poll=lambda: None))
            rows = [dict(entry=entry, pid=0, tgid=os.getpid(), entry_abi=2, lock_kind=2,
                         status=0, code=entry+0x4000, generation=1) for entry in (0x1000, 0x2000)]
            with patch.object(controller.rt, 'registry', return_value=rows), \
                 patch.object(controller.rt, 'children', return_value=[]), \
                 patch.object(controller.rt, 'status', return_value={'writers': 1}):
                self.assertEqual(item.ready(daemon), rows)
                rows[1]['status'] = -1
                self.assertIsNone(item.ready(daemon))
                rows[1]['status'] = 0
                rows[1]['generation'] = 0
                self.assertIsNone(item.ready(daemon))
                rows[1]['generation'] = 1
                with patch.object(controller.rt, 'children', return_value=['701']):
                    self.assertIsNone(item.ready(daemon))
                with patch.object(controller.rt, 'status', return_value={'writers': 2}):
                    self.assertIsNone(item.ready(daemon))
                for bad in (rows[:1], rows+[dict(rows[0], entry=0x3000)],
                            [rows[0], dict(rows[1], tgid=0)], [rows[0], dict(rows[1], status=1)]):
                    with patch.object(controller.rt, 'registry', return_value=bad), self.assertRaises(controller.rt.Failure):
                        item.ready(daemon)


class Services(unittest.TestCase):
    def test_reached_task_read_requires_both_results_and_exact_instruction_ack(self):
        item = controller.Controller.__new__(controller.Controller)
        item.args = SimpleNamespace(execution_mode='reached')
        item.audit = dict(records=[dict(entry=0xa000)])
        root = dict(origin=101, executor=200, identity=0x1001, generation=1, entry=0xa000)
        proof = dict(completed_requests=[root])
        snapshot = dict(records=[dict(tid=101, backing=0x1100)])
        common = 'origin=101 executor=200 identity=1001 generation=1 family_generation=1'
        lines = [f'kd_reached event=family {common} entry=a000',
                 f'kd_service event=enter {common} object=1100 depth=0 entry=a000 may_delegate=1',
                 f'kd_reached event=service {common} artifact_sequence=2 kind=memory ip=8000 target=0 sp=7000']
        for stage, task in zip(('request', 'enter', 'done', 'resume'), (200, 101, 101, 200)):
            output = stage in ('done', 'resume')
            lines.append(f'kd_service memory: stage={stage} {common} task={task} sequence=1 '
                f'image_generation=0 ip=8000 next=8003 sp=7000 offset=0 width=32 operation=6 '
                f'preempt_operand=0 input_flags=203 output_flags={"203" if output else "0"} '
                f'preempt_seq=0 preempt_object=0 destination=0 value={"123" if output else "0"} '
                f'read=1 artifact_sequence=2 source_value=0 aux_value=0')
        lines += [f'kd_reached event=resume {common} artifact_sequence=2 kind=memory ip=8000 target=0 sp=7000',
                  f'kd_service event=release {common} object=1100 depth=0 entry=a000 may_delegate=1',
                  f'kd_service event=returned {common} object=1100 depth=0 entry=a000 may_delegate=1',
                  f'kd_reached event=retire {common} entry=a000']
        messages = '\n'.join(lines)
        self.assertEqual(item.validate_services(proof, [], messages, snapshot)['memory_transactions'], 1)
        for changed in (messages.replace('next=8003', 'next=8002'),
                        messages.replace('source_value=0', 'source_value=1', 1),
                        messages.replace('aux_value=0', 'aux_value=1', 1),
                        messages.replace(' aux_value=0', '', 1),
                        messages.replace('value=123', 'value=100000123'),
                        messages.replace('output_flags=203', 'output_flags=202'),
                        messages.replace('destination=0', 'destination=1')):
            with self.assertRaises(controller.rt.Failure):
                item.validate_services(proof, [], changed, snapshot)

    def test_reached_gs_subtraction_retains_instruction_and_result_ack(self):
        item = controller.Controller.__new__(controller.Controller)
        item.args = SimpleNamespace(execution_mode='reached')
        item.audit = dict(records=[dict(entry=0xa000)])
        root = dict(origin=101, executor=200, identity=0x1001, generation=1, entry=0xa000)
        proof = dict(completed_requests=[root])
        snapshot = dict(records=[dict(tid=101, backing=0x1100)])
        common = 'origin=101 executor=200 identity=1001 generation=1'
        family = 'family_generation=1'
        def trace(width):
            lines = [f'kd_reached event=family {common} {family} entry=a000',
                     f'kd_service event=enter {common} object=1100 depth=0 entry=a000 may_delegate=1 {family}',
                     f'kd_reached event=service {common} {family} artifact_sequence=2 kind=memory ip=8000 target=0 sp=7000']
            for stage, task in zip(('request', 'enter', 'done', 'resume'), (200, 101, 101, 200)):
                output = stage in ('done', 'resume')
                lines.append(f'kd_service memory: stage={stage} {common} task={task} sequence=1 '
                    f'image_generation=0 ip=8000 next=8009 sp=7000 offset=ffff width={width} operation=5 '
                    f'preempt_operand=0 input_flags=203 output_flags={"246" if output else "0"} '
                    f'preempt_seq=0 preempt_object=0 destination=8 value={"123" if output else "0"} read=1 '
                    f'{family} artifact_sequence=2 source_value=ffffffff80000123')
            lines += [f'kd_reached event=resume {common} {family} artifact_sequence=2 kind=memory ip=8000 target=0 sp=7000',
                      f'kd_service event=release {common} object=1100 depth=0 entry=a000 may_delegate=1 {family}',
                      f'kd_service event=returned {common} object=1100 depth=0 entry=a000 may_delegate=1 {family}',
                      f'kd_reached event=retire {common} {family} entry=a000']
            return '\n'.join(lines)
        for width in (32, 64):
            messages = trace(width)
            self.assertEqual(item.validate_services(proof, [], messages, snapshot)['memory_transactions'], 1)
            failures = (messages.replace(f'width={width}', 'width=16'),
                        messages.replace('destination=8', 'destination=4'),
                        messages.replace('destination=8', 'destination=17'),
                        messages.replace('read=1', 'read=0'),
                        messages.replace('output_flags=246', 'output_flags=247', 1),
                        messages.replace('value=123', 'value=124', 1),
                        messages.replace('source_value=ffffffff80000123', 'source_value=ffffffff80000124', 1),
                        messages.replace(' source_value=ffffffff80000123', '', 1),
                        messages.replace('value=0 read=1', 'value=1 read=1', 1),
                        messages.replace('artifact_sequence=2', 'artifact_sequence=3', 1))
            for changed in failures:
                with self.assertRaises(controller.rt.Failure):
                    item.validate_services(proof, [], changed, snapshot)
        with self.assertRaises(controller.rt.Failure):
            item.validate_services(proof, [], trace(32).replace('value=123', 'value=100000123'), snapshot)
        item.args.execution_mode = 'image'
        with self.assertRaises(controller.rt.Failure):
            item.validate_services(proof, [dict(entry=0xa000, generation=7)],
                trace(64).replace('image_generation=0', 'image_generation=7').replace(' family_generation=1', ''), snapshot)

    def test_reached_many_roots_on_one_worker_keep_separate_family_ledgers(self):
        item = controller.Controller.__new__(controller.Controller)
        item.args = SimpleNamespace(execution_mode='reached')
        item.audit = dict(records=[dict(entry=0xa000), dict(entry=0xb000)])
        proof = dict(completed_requests=[dict(origin=101, executor=200, identity=0x1001, generation=1, entry=0xa000)])
        snapshot = dict(records=[dict(tid=101, backing=0x1100)])
        lines = []
        for generation, identity, entry in ((1, 0x1001, 0xa000), (2, 0x1002, 0xb000)):
            common = f'origin=101 executor=200 identity={identity:x} generation={generation}'
            family = f'family_generation={generation}'
            lines += [f'kd_reached event=family {common} {family} entry={entry:x}',
                      f'kd_service event=enter {common} object=1100 depth=0 entry={entry:x} may_delegate=1 {family}',
                      f'kd_reached event=service {common} {family} artifact_sequence=2 kind=primitive ip={entry+2:x} target=dead sp=7000']
            for stage, task in zip(('request', 'enter', 'done', 'resume'), (200, 101, 101, 200)):
                lines.append(f'kd_service primitive: stage={stage} {common} task={task} sequence=1 target=dead return=beef '
                             f'image_generation=0 ax=55 flags=202 {family} artifact_sequence=2')
            lines += [f'kd_reached event=resume {common} {family} artifact_sequence=2 kind=primitive ip={entry+2:x} target=dead sp=7000',
                      f'kd_service event=release {common} object=1100 depth=0 entry={entry:x} may_delegate=1 {family}',
                      f'kd_service event=returned {common} object=1100 depth=0 entry={entry:x} may_delegate=1 {family}',
                      f'kd_reached event=retire {common} {family} entry={entry:x}']
        messages = '\n'.join(lines)
        result = item.validate_services(proof, [], messages, snapshot)
        self.assertEqual((result['captured_worker_roots'], result['other_worker_roots'], result['primitive_transactions']), (2, 1, 2))
        self.assertEqual(len(result['family_artifact_ledger']), 2)
        for changed in (messages.replace('family_generation=2 artifact_sequence=2', 'family_generation=1 artifact_sequence=2', 1),
                        '\n'.join(line for line in lines if not ('event=retire' in line and 'generation=2' in line)),
                        messages.replace('image_generation=0', 'image_generation=7', 1)):
            with self.assertRaises(controller.rt.Failure):
                item.validate_services(proof, [], changed, snapshot)

    def test_complete_call_and_gs_test_pairs_with_sequence_and_root_controls(self):
        item = controller.Controller.__new__(controller.Controller)
        root = dict(origin=101, executor=200, identity=0x1001, generation=1, entry=0xA000)
        proof = dict(completed_requests=[root])
        snapshot = dict(records=[dict(tid=101, backing=0x1100)])
        rows = [dict(entry=0xA000, generation=7), dict(entry=0xB000, generation=8)]
        root_line = 'kd_service event={} origin=101 executor=200 identity=1001 generation=1 object=1100 depth=0 entry=a000 may_delegate=1'
        lines = [root_line.format('enter')]
        for stage, task in zip(('request', 'enter', 'done', 'resume'), (200, 101, 101, 200)):
            lines.append('kd_service primitive: stage='+stage+' origin=101 executor=200 task='+str(task)+
                ' identity=1001 generation=1 sequence=1 target=dead return=beef image_generation=7 ax='+
                ('55' if stage in ('done', 'resume') else '0')+' flags='+('202' if stage in ('done', 'resume') else '0'))
        for stage, task in zip(('request', 'enter', 'done', 'resume'), (200, 101, 101, 200)):
            lines.append('kd_service memory: stage='+stage+' origin=101 executor=200 task='+str(task)+
                ' identity=1001 generation=1 sequence=1 image_generation=7 ip=8000 next=8009 sp=7000 offset=ffff width=16'+
                ' operation=4 preempt_operand=0 input_flags=203 output_flags='+('246' if stage in ('done', 'resume') else '0')+
                ' preempt_seq=0 preempt_object=0 destination=17 value=0 read=1')
        lines.extend([root_line.format('release'), root_line.format('returned')])
        messages = '\n'.join(lines)
        result = item.validate_services(proof, rows, messages, snapshot)
        self.assertEqual((result['primitive_transactions'], result['memory_transactions'], result['other_worker_roots']), (1, 1, 0))
        failures = (messages.replace('sequence=1', 'sequence=2'),
                    messages.replace('image_generation=7 ip=', 'image_generation=8 ip=', 1),
                    messages.replace('stage=done origin=101 executor=200 task=101',
                                     'stage=done origin=101 executor=200 task=200', 1),
                    messages.replace('output_flags=246 preempt_seq=0', 'output_flags=247 preempt_seq=0', 1),
                    messages.replace(' identity=1001 generation=1 sequence=', ' identity=2002 generation=1 sequence=', 1),
                    '\n'.join(lines[:6]+lines[7:]))
        for bad in failures:
            with self.assertRaises(controller.rt.Failure):
                item.validate_services(proof, rows, bad, snapshot)
        extra = root_line.replace('identity=1001', 'identity=2002').replace('entry=a000', 'entry=b000')
        other = messages+'\n'+'\n'.join(extra.format(event) for event in ('enter', 'release', 'returned'))
        self.assertEqual(item.validate_services(proof, rows, other, snapshot)['other_worker_roots'], 1)


class ApplicationContinuation(unittest.TestCase):
    def test_positive_tail_and_later_writer_required_without_expanding_scope(self):
        proof = dict(downgraded_read_tails=1, later_same_executor_writers=[
            dict(read_request=[0x1001, 1], later_writer=[0x1002, 2], executor=200)],
            fresh_reader_drain_observed=False, all_application_invocations_accounted=False,
            physical_batch_length_measured=False)
        original = copy.deepcopy(proof)
        accepted = controller.require_observed_continuation(proof)
        self.assertEqual(accepted['later_same_executor_writer_pairs'], 1)
        self.assertEqual(proof, original)
        for change in (lambda x: x.update(downgraded_read_tails=0),
                       lambda x: x.update(later_same_executor_writers=[])):
            missing = copy.deepcopy(proof)
            change(missing)
            with self.assertRaises(controller.rt.Failure):
                controller.require_observed_continuation(missing)
            self.assertFalse(missing['fresh_reader_drain_observed'])
            self.assertFalse(missing['all_application_invocations_accounted'])


if __name__ == '__main__':
    unittest.main()
