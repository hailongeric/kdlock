"""Offline checker regressions; synthetic rows are not live JIT evidence."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "kernel"))
from spin.batch_cases import continuous_pair


class BatchEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.rows = []
        self.tasks = [10, 11, 12, 13, 14]
        for number in (3, 4):
            for kind in ("SELECT_PROXY", "GRANT", "JIT_ENTER", "JIT_EXIT", "JIT_OPERATION", "PROXY_RETURN"):
                self.rows.append(dict(index=len(self.rows), kind=kind, node=number, acquisition=number+20,
                    state=number+30, task=12, origin=10+number, owner=100, owner_task=12,
                    object=200, image=300, related=number, flags=4096,
                    result=4 if kind=="PROXY_RETURN" else 1))
        for kind in ("PHYSICAL_BEGIN", "PHYSICAL_END"):
            self.rows.append(dict(index=len(self.rows),kind=kind,node=0,acquisition=0,state=0,
                task=12,origin=0,owner=100,owner_task=12,object=200,image=0,related=400,flags=0,result=0))
        self.retired=[]

    def check(self):
        return continuous_pair(self.rows, lambda row,name:row["kind"]==name,
            lambda row,node,image: row["kind"]=="JIT_OPERATION" and row["related"]==node and row["image"]==image,
            300,self.tasks,lambda rows,request,*args:self.retired.append(request["node"]))

    def test_two_complete_foreign_bodies(self):
        self.assertEqual(self.check()["completed_foreign_jit_bodies"],2)
        self.assertEqual(self.retired,[3,4])

    def test_selection_alone_is_insufficient(self):
        self.rows=[r for r in self.rows if r["kind"]!="JIT_ENTER"]
        with self.assertRaises(AssertionError):self.check()

    def test_separate_owners_are_not_a_batch(self):
        self.rows[6]["owner"]=101
        self.assertIsNone(self.check())

    def test_different_object_is_rejected(self):
        self.rows[6]["object"]=201
        with self.assertRaises(AssertionError):self.check()

    def test_handback_is_not_completion(self):
        self.rows[3]["result"]=2
        with self.assertRaises(AssertionError):self.check()

    def test_intervening_physical_release_is_rejected(self):
        duplicate=deepcopy(self.rows[-1]);duplicate["index"]=5.5
        self.rows.insert(6,duplicate)
        with self.assertRaises(AssertionError):self.check()

    def test_requeue_between_bodies_is_rejected(self):
        queued=deepcopy(self.rows[0]);queued.update(kind="ENQUEUE",index=5.5)
        self.rows.insert(6,queued)
        with self.assertRaises(AssertionError):self.check()

    def test_exit_must_precede_unlock_and_follow_entry(self):
        original = deepcopy(self.rows)
        for index in (0.5, 4.5, 14):
            with self.subTest(exit_index=index):
                self.rows = deepcopy(original)
                self.rows[3]["index"] = index
                self.rows.sort(key=lambda row: row["index"])
                with self.assertRaises(AssertionError):
                    self.check()

    def test_each_generated_entry_requires_its_exit(self):
        extra = deepcopy(self.rows[2])
        extra["index"] = 3.5
        self.rows.insert(4, extra)
        with self.assertRaises(AssertionError):
            self.check()

    def test_exit_keeps_exact_executor_origin_and_state(self):
        original = deepcopy(self.rows)
        for field in ("task", "origin", "state"):
            with self.subTest(field=field):
                self.rows = deepcopy(original)
                self.rows[3][field] += 1
                with self.assertRaises(AssertionError):
                    self.check()

    def test_balanced_but_overlapping_fragments_are_rejected(self):
        entry, exit_row = deepcopy(self.rows[2]), deepcopy(self.rows[3])
        entry["index"], exit_row["index"] = 2.5, 3.5
        self.rows.extend((entry, exit_row))
        self.rows.sort(key=lambda row: row["index"])
        with self.assertRaises(AssertionError):
            self.check()

    def test_multiple_ordered_generated_fragments_are_allowed(self):
        entry, exit_row = deepcopy(self.rows[2]), deepcopy(self.rows[3])
        entry["index"], exit_row["index"] = 3.25, 3.5
        self.rows[4:4] = [entry, exit_row]
        self.assertEqual(self.check()["completed_foreign_jit_bodies"], 2)

    def test_native_executor_is_not_foreign_jit(self):
        self.rows[2]["task"]=13
        with self.assertRaises(AssertionError):self.check()

if __name__ == "__main__":
    unittest.main()
