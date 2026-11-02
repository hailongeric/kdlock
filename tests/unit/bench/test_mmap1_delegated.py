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


if __name__ == '__main__':
    unittest.main()
