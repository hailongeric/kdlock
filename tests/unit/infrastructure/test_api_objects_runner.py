"""Semantic receipts must preserve exact cases, objects, effects and joins."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('api_objects_runner_tests', ROOT/'tests/kernel/api_objects/run.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
ENTRIES = [0x1000,0x2000,0x3000]


def binding(kind, arm, number=1):
    return dict(version=1,kind=kind,backend=int(arm=='kd'),object=number*128,
                lock=number*128+32,provider=0x9000 if arm=='kd' else 0,entries=ENTRIES[:])


def fixture(kind, arm):
    initial = binding(1 if kind=='setfd' else 2,arm)
    ready = dict(ready=True,pid=123,backend=int(arm=='kd'))
    ready.update(initial if kind=='setfd' else dict(binding=initial))
    rows = [ready]
    for index,name in enumerate(runner.CASES[kind],1):
        row = dict(case=name,passed=True,joined=True,backend=int(arm=='kd'))
        if kind=='setfd':
            if name=='unshare_release':
                row.update(old_object=initial['object'],new_object=0x4000,new_backend=0)
            else:
                row.update({k:initial[k] for k in ('object','lock','provider')})
                row['operations'] = {'binding':1,'flags_and_duplicates':6,
                                      'concurrent_participants':18432,'fork_copy':1}[name]
        else:
            row.update(runner.PIPE_FIELDS[name])
            if name=='endpoint_release':
                row.update(eof_binding=binding(2,arm,8),epipe_binding=binding(2,arm,9))
            elif name=='selector_lifetime':
                for slot,key in enumerate(('first_binding','second_binding','cancelled_binding',
                                           'duplicate_token_binding','last_close_binding'),10):
                    row[key] = binding(2,arm if key in ('first_binding','duplicate_token_binding') else 'native',slot)
                row['selected_budget'] = int(arm=='kd')
            else:
                row['binding'] = binding(2,arm,index)
            if name in ('reader_wake','writer_wake'):
                row['sleeping_tid'] = 456
        rows.append(row)
    rows.append(dict(done=True,passed=True,joined=True,control_closed=True,backend=int(arm=='kd'),cases=len(rows)-1))
    return rows


class ApiObjectsRunnerTests(unittest.TestCase):
    def valid(self, rows, kind='pipe', arm='kd'):
        return runner.validate_lines(rows,kind,arm,123,ENTRIES)

    def test_both_protocols_and_complete_cases(self):
        for kind in ('setfd','pipe'):
            for arm in ('native','kd'):
                result = self.valid(fixture(kind,arm),kind,arm)
                self.assertTrue(result['joined'])
                self.assertEqual(result['cases'],list(runner.CASES[kind]))

    def test_missing_extra_reordered_failed_or_unjoined_cases_rejected(self):
        changes = (lambda r:r.pop(2), lambda r:r.insert(2,copy.deepcopy(r[1])),
                   lambda r:r[2].update(case=r[1]['case']), lambda r:r[2].update(passed=False),
                   lambda r:r[2].update(joined=False), lambda r:r[-1].update(joined=False),
                   lambda r:r[-1].update(control_closed=False), lambda r:r[-1].update(cases=7))
        for change in changes:
            rows=fixture('pipe','kd');change(rows)
            with self.assertRaises(runner.rt.Failure):self.valid(rows)

    def test_other_process_entry_set_or_provider_rejected(self):
        changes=(lambda r:r[0].update(pid=124), lambda r:r[0]['binding'].update(entries=[4,5,6]),
                 lambda r:r[2]['binding'].update(provider=0x9900),
                 lambda r:r[1]['binding'].update(object=0xdead),
                 lambda r:r[2]['binding'].update(backend=0))
        for change in changes:
            rows=fixture('pipe','kd');change(rows)
            with self.assertRaises(runner.rt.Failure):self.valid(rows)

    def test_pipe_data_conservation_is_not_replaced_by_pass_boolean(self):
        for index,key in ((1,'records_read'),(1,'bytes'),(2,'resizes'),(2,'occupied_shrink_errno'),
                          (3,'fault_errno'),(4,'observed_syscall'),(5,'completed_bytes'),
                          (6,'sigpipe_consumed'),(7,'invalid_queries'),(8,'objects_closed')):
            rows=fixture('pipe','kd');rows[index][key]+=1
            with self.subTest(key=key),self.assertRaises(runner.rt.Failure):self.valid(rows)

    def test_wake_requires_syscall_state_bracket_and_join(self):
        for index in (4,5):
            for change in (dict(syscall_state_syscall_bracket=False),dict(sleeping_tid=0),dict(workers_joined=0)):
                rows=fixture('pipe','kd');rows[index].update(change)
                with self.assertRaises(runner.rt.Failure):self.valid(rows)

    def test_selector_consumption_and_final_token_release(self):
        for key in ('second_binding','cancelled_binding','last_close_binding'):
            rows=fixture('pipe','kd');rows[8][key]=binding(2,'kd',22)
            with self.assertRaises(runner.rt.Failure):self.valid(rows)
        rows=fixture('pipe','kd');rows[8]['second_binding']['object']=rows[8]['first_binding']['object']
        with self.assertRaises(runner.rt.Failure):self.valid(rows)

    def test_setfd_same_object_and_replacement_rules(self):
        for index,change in ((2,dict(object=33)),(3,dict(operations=1)),
                             (5,dict(new_object=128)),(5,dict(old_object=0)),(5,dict(new_backend=1))):
            rows=fixture('setfd','kd');rows[index].update(change)
            with self.assertRaises(runner.rt.Failure):self.valid(rows,'setfd','kd')


if __name__=='__main__':
    unittest.main()
