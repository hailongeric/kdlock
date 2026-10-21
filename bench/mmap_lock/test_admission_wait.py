"""VM-only focused checks for pending admission and immutable refusals."""
import copy
import unittest
import admission_wait


def original():
    return dict(captured_utc='2026-10-22T00:00:00+00:00',policy='fixed',
                qemu=[dict(tasks=[dict(tid=1,comm='qemu',affinity=[63])])])


def screen(before, after):
    if before['policy'] != after['policy']:
        return 'host control differs: policy'
    if before['qemu'][0]['tasks'] != after['qemu'][0]['tasks']:
        return 'strict original QEMU task set differs'
    return None


class AdmissionTests(unittest.TestCase):
    def test_extra_workers_wait_without_modifying_capture(self):
        base=original();host=copy.deepcopy(base)
        host['qemu'][0]['tasks'].append(dict(tid=2,comm='worker',affinity=[63]))
        frozen=copy.deepcopy(host)
        self.assertEqual(admission_wait.classify(base,host,screen)[0],'PENDING_EXTRA_WORKERS')
        self.assertEqual(host,frozen)
        self.assertIsNotNone(screen(base,host))

    def test_no_arbitrary_refusal_count_ends_wait(self):
        base=original();bad=copy.deepcopy(base)
        bad['qemu'][0]['tasks'].append(dict(tid=2,comm='worker',affinity=[63]))
        calls=[];records=[];sleeps=[]
        def observe(attempt):
            calls.append(attempt)
            return f'observation-{attempt}',bad if attempt<=25 else base,str(attempt)
        result=admission_wait.wait(base,observe,screen,records.append,
            sleep=sleeps.append,monotonic=lambda:100.)
        self.assertEqual(result,'observation-26')
        self.assertEqual(sleeps,[60]*25)
        self.assertEqual(len(records),26)
        self.assertTrue(all(r['state']=='PENDING_EXTRA_WORKERS' for r in records[:-1]))
        self.assertTrue(all(not r['full_guest_admission'] for r in records))

    def test_original_identity_and_affinity_changes_never_wait(self):
        for key,value in (('tid',3),('affinity',[62]),('comm','changed')):
            base=original();bad=copy.deepcopy(base);bad['qemu'][0]['tasks'][0][key]=value
            self.assertEqual(admission_wait.classify(base,bad,screen)[0],'REQUIRES_REVIEW')

    def test_unexpected_extra_or_policy_change_never_waits(self):
        for task in (dict(tid=2,comm='other',affinity=[63]),dict(tid=2,comm='worker',affinity=[0])):
            base=original();bad=copy.deepcopy(base);bad['qemu'][0]['tasks'].append(task)
            self.assertEqual(admission_wait.classify(base,bad,screen)[0],'REQUIRES_REVIEW')
        base=original();bad=copy.deepcopy(base);bad['policy']='changed'
        records=[];sleeps=[]
        with self.assertRaises(RuntimeError):
            admission_wait.wait(base,lambda n:('capture',bad,'hash'),screen,records.append,sleep=sleeps.append)
        self.assertEqual(len(records),1);self.assertFalse(sleeps)

    def test_busy_polling_is_rejected(self):
        with self.assertRaises(ValueError):
            admission_wait.wait(original(),None,None,None,interval=59)


if __name__=='__main__':
    unittest.main(verbosity=2)
