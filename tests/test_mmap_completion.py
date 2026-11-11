"""VM-only pure saved-record checker cases, with no kernel or JIT execution.

The positive shapes use independently stated source/owner event ordering. All
addresses, CALL bytes, round success and ELF contents are synthetic inputs.
These cases establish checker behavior, not real syscall or MM completion.
Do not import, parse or execute this module on the source host.
"""
import copy
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "kernel"))
from mmap_api.completion import completion_report, read_function_spans


FIELDS = ("kind", "task", "state", "origin", "node", "acquisition", "parent", "owner",
          "owner_task", "object", "image", "ip", "cursor", "related", "phase", "result",
          "flags", "source_user", "return_user", "notifier")
# Exact public scalar event IDs. Do not derive these from the implementation
# under test, which would hide an accidental renumbering of that interface.
K = {"RESERVE": 1, "FREE": 2, "ENQUEUE": 3, "SELECT_PROXY": 5, "GRANT": 6,
     "QUEUE_DONE": 8, "NODE_READY": 9, "BIND": 10, "REQUEST": 11, "HANDLED": 15,
     "SOURCE_DROP": 16, "PHYS_BEGIN": 18, "PHYS_END": 19, "RELEASE_RETIRE": 20,
     "OWNER_RETIRE": 21, "FRAME": 22, "ENTER": 23, "EXIT": 24, "OPERATION": 25,
     "DONE": 27, "FORWARD": 28, "OWNER_STOP": 30, "RETAINED": 34, "QUERY": 44}
W, C = 0x11, 0x22
STATE, NODE, ACQUISITION = 0x100000, 0x100100, 0x100200
OWNER, RELEASE, CALLBACK = 0x200000, 0x200100, 0x200200
BINDING, SOURCE_USER = 0x300000, 0x400000
POOL, SLOT, CLAIM = 0x500000, 0x500100, 0x500200
GATE, IMAGE = 0x600000, 0x700000
SPANS = {"vm_mmap_pgoff": {"start": 0x1000, "end": 0x1080},
         "__vm_munmap": {"start": 0x2000, "end": 0x2080}}


def event(name, **values):
    row = dict.fromkeys(FIELDS, 0)
    row.update(kind=K[name], task=C, state=STATE, node=NODE,
               acquisition=ACQUISITION, origin=W)
    row.update(values)
    return row


def call(site, target, operation, prefix=b""):
    length = len(prefix) + 5
    raw = prefix + b"\xe8" + struct.pack("<i", target - site - length)
    return {"site": site, "length": length, "target": target, "indirect": False,
            "raw_hex": raw.hex(), "operation": operation}


def numbered(rows):
    for index, row in enumerate(rows):
        row["index"] = index
    return rows


def fixture(path="mmap", query=False, owner_action=0):
    base = 0x1000 if path == "mmap" else 0x2000
    root = call(base, 0x9000, "lock")
    unlock = call(base + (0x40 if path == "mmap" else 0x50),
                  0x9100 if path == "mmap" else 0x9300, "unlock")
    calls = [root, unlock]
    rows = [event("RESERVE", task=W, owner=POOL, related=SLOT, parent=CLAIM),
            event("FRAME", task=W, image=IMAGE, related=BINDING, phase=3),
            event("ENQUEUE", task=W, object=GATE, phase=1, flags=17),
            event("SELECT_PROXY", owner=OWNER, owner_task=C, object=GATE,
                  related=0x101100, phase=3),
            # Proxy detach publishes queue completion before binding the grant.
            event("QUEUE_DONE", object=GATE, phase=3, flags=21),
            event("BIND", node=0, owner=OWNER, owner_task=C, object=GATE,
                  related=RELEASE, source_user=SOURCE_USER),
            event("GRANT", owner=OWNER, owner_task=C, object=GATE,
                  related=RELEASE, flags=23),
            event("ENTER", image=IMAGE, related=BINDING, cursor=base + 5)]
    if query:
        predicate = call(base + 0x10, 0x9400, "query", b"\x2e")
        calls.append(predicate)
        rows += [event("EXIT", image=IMAGE, ip=predicate["site"], cursor=predicate["site"],
                       related=predicate["target"], result=1, flags=4, phase=1),
                 event("OPERATION", image=IMAGE, ip=predicate["site"], cursor=predicate["target"],
                       object=GATE, result=16, phase=2),
                 event("QUERY", image=IMAGE, ip=predicate["site"], cursor=predicate["site"] + predicate["length"],
                       object=GATE, related=16, result=1, phase=5),
                 event("ENTER", image=IMAGE, related=BINDING,
                       cursor=predicate["site"] + predicate["length"])]
    if path != "mmap":
        mode = call(base + 0x40, 0x9200, "mode_change")
        calls.append(mode)
        rows += [event("EXIT", image=IMAGE, ip=mode["site"], cursor=mode["site"],
                       related=mode["target"], result=1, flags=3, phase=1),
                 event("OPERATION", image=IMAGE, ip=mode["site"], cursor=mode["site"] + mode["length"],
                       object=GATE, related=NODE, result=10, phase=5),
                 event("RETAINED", object=GATE, owner=OWNER, related=BINDING,
                       cursor=mode["site"] + mode["length"], phase=2),
                 event("ENTER", image=IMAGE, related=BINDING, cursor=mode["site"] + mode["length"])]
    rows.append(event("EXIT", image=IMAGE, ip=unlock["site"], cursor=unlock["site"],
                      related=unlock["target"], result=1, flags=2, phase=1))
    route = 1 if path == "mmap" else 4
    rows += [event("REQUEST", node=0, owner=OWNER, owner_task=C, object=GATE,
                   related=RELEASE, source_user=SOURCE_USER, result=route, phase=1),
             event("HANDLED", node=0, owner=OWNER, owner_task=C, object=GATE,
                   related=RELEASE, source_user=SOURCE_USER, result=route, phase=4)]
    accepted = event("OPERATION", image=IMAGE, ip=unlock["site"],
                     cursor=unlock["site"] + unlock["length"], object=GATE, related=NODE,
                     result=9 if path == "mmap" else 7, phase=owner_action if path == "mmap" else 4)
    terminal = (event("DONE", cursor=accepted["cursor"], related=BINDING, result=3, flags=512 | 1024)
                if path == "mmap" else
                event("FORWARD", image=IMAGE, ip=unlock["site"], cursor=accepted["cursor"], related=unlock["target"]))
    physical = [event("OWNER_STOP", state=0x101000, node=0x101100, acquisition=0x101200,
                      origin=C, owner=OWNER, owner_task=C, object=GATE, flags=128),
                event("PHYS_BEGIN", state=0, node=0, acquisition=0, origin=0,
                      owner=OWNER, owner_task=C, object=GATE, related=CALLBACK, phase=1),
                event("PHYS_END", state=0, node=0, acquisition=0, origin=0,
                      owner=OWNER, owner_task=C, object=GATE, related=CALLBACK, phase=2)]
    # Ordinary write completion can precede callback completion. Retained read
    # acceptance must follow that callback's exact synchronous physical ACK.
    if path == "mmap":
        rows += [accepted, terminal] + physical
    else:
        rows += physical + [accepted, terminal]
    rows += [event("SOURCE_DROP", task=W, node=0, owner=OWNER, owner_task=C, object=GATE,
                   related=RELEASE, source_user=SOURCE_USER, phase=5),
             event("RELEASE_RETIRE", node=0, owner=OWNER, owner_task=C, object=GATE,
                   related=RELEASE, result=route, phase=6),
             event("NODE_READY", owner=OWNER, owner_task=C, object=GATE, related=RELEASE, phase=6, flags=15),
             event("FREE", task=W, owner=POOL, related=SLOT, parent=CLAIM, object=GATE,
                   phase=3, flags=1 | 2 | 4 | 8 | 32 | 64 | 2048),
             # This shared physical owner may retire after the member slot.
             event("OWNER_RETIRE", state=0, node=0, acquisition=0, origin=0,
                   owner=OWNER, owner_task=C, object=GATE, related=CALLBACK, phase=3)]
    return numbered(rows), calls


class MmapCompletionTests(unittest.TestCase):
    def report(self, rows, calls, memory=None):
        numbered(rows)
        source = {(item["site"], item["length"]): bytes.fromhex(item["raw_hex"]) for item in calls}
        read_source = memory if memory is not None else lambda address, length: source.get((address, length), b"")
        rounds = [{"round": 1, "begin": 0, "end": len(rows), "image": IMAGE, "effects_passed": True}]
        return completion_report(rows, calls, SPANS, rounds, GATE, read_source)

    def rejected(self, rows, calls):
        report = self.report(rows, calls)
        self.assertEqual(report["positive"], [])
        self.assertEqual(report["counts"], {"mmap": 0, "munmap_retained": 0})
        self.assertTrue(report["rejected"])
        return report

    def test_mmap_current_completion_allows_later_physical_and_shared_owner_retirement(self):
        for action in (0, 1):
            with self.subTest(action=action):
                rows, calls = fixture(owner_action=action)
                before = copy.deepcopy((rows, calls))
                report = self.report(rows, calls)
                self.assertEqual(report["counts"], {"mmap": 1, "munmap_retained": 0})
                proof = report["positive"][0]
                self.assertEqual(proof["terminal"]["image"], 0)
                self.assertLess(proof["terminal"]["index"], proof["retirement"]["physical_end"]["index"])
                self.assertLess(proof["retirement"]["queue_done"]["index"], proof["grant"]["index"])
                self.assertLess(proof["retirement"]["slot_free"]["index"], proof["retirement"]["owner_retire"]["index"])
                self.assertEqual((rows, calls), before)

    def test_retained_munmap_has_same_grant_and_physical_ack_before_exact_native_continuation(self):
        rows, calls = fixture("munmap_retained")
        report = self.report(rows, calls)
        self.assertEqual(report["counts"], {"mmap": 0, "munmap_retained": 1})
        proof = report["positive"][0]
        self.assertEqual(proof["terminal"]["kind"], 28)
        self.assertLess(proof["retirement"]["physical_end"]["index"], proof["operations"][-1]["operation"]["index"])
        self.assertFalse(any(row["kind"] == 27 for row in rows))

    def test_exact_query_return_can_continue_to_real_protected_completion(self):
        for operation in (16, 17):
            for value in (0, 1):
                with self.subTest(operation=operation, value=value):
                    rows, calls = fixture(query=True)
                    next(row for row in rows if row["kind"] == 25)["result"] = operation
                    result = next(row for row in rows if row["kind"] == 44)
                    result.update(related=operation, result=value)
                    report = self.report(rows, calls)
                    self.assertEqual(report["counts"]["mmap"], 1)
                    self.assertEqual(report["positive"][0]["operations"][0]["query"]["result"], value)
                    self.assertEqual(report["positive"][0]["operations"][0]["call"]["length"], 6)

    def test_early_native_handback_is_not_completion_despite_successful_round_effects(self):
        rows, calls = fixture()
        exited = next(row for row in rows if row["kind"] == 24)
        exited.update(kind=28, result=0, flags=0, phase=0)
        self.rejected(rows, calls)

    def test_post_query_reentry_must_match_current_cursor_and_binding(self):
        for field, value in (("cursor", 0x1050), ("related", BINDING + 1)):
            with self.subTest(field=field):
                rows, calls = fixture(query=True)
                entered = [row for row in rows if row["kind"] == 23][1]
                entered[field] = value
                self.rejected(rows, calls)

    def test_new_slot_claim_cannot_supply_an_old_incarnations_late_completion(self):
        rows, calls = fixture()
        index = next(i for i, row in enumerate(rows) if row["kind"] == 25)
        rows[index:index] = [event("FREE", task=W, owner=POOL, related=SLOT, parent=CLAIM),
                             event("RESERVE", task=W, owner=POOL, related=SLOT, parent=CLAIM + 1)]
        self.rejected(rows, calls)

    def test_old_owner_callback_cannot_be_reused_as_the_new_owners_physical_ack(self):
        rows, calls = fixture()
        old_callbacks = [copy.deepcopy(row) for row in rows if row["kind"] in (18, 19)]
        rows = [row for row in rows if row["kind"] not in (18, 19)]
        old_end = event("OWNER_RETIRE", state=0, node=0, acquisition=0, origin=0,
                        owner=OWNER, owner_task=C, object=GATE, phase=3)
        self.rejected(old_callbacks + [old_end] + rows, calls)

    def test_retained_up_read_cannot_precede_the_physical_ack(self):
        rows, calls = fixture("munmap_retained")
        physical = next(i for i, row in enumerate(rows) if row["kind"] == 19)
        operation = next(i for i, row in enumerate(rows) if row["kind"] == 25 and row["result"] == 7)
        rows[physical], rows[operation] = rows[operation], rows[physical]
        self.rejected(rows, calls)

    def test_nonzero_callback_result_and_live_result_user_refuse_retirement(self):
        for kind, field, value in ((19, "result", 1), (9, "flags", 15 | 16), (9, "phase", 0), (11, "phase", 0)):
            with self.subTest(kind=kind, field=field):
                rows, calls = fixture()
                next(row for row in rows if row["kind"] == kind)[field] = value
                self.rejected(rows, calls)

    def test_identical_call_records_deduplicate_but_conflicting_bytes_do_not(self):
        rows, calls = fixture(query=True)
        self.assertEqual(self.report(rows, calls + [dict(calls[0])])["counts"]["mmap"], 1)
        other = dict(calls[0], raw_hex="90" * calls[0]["length"])
        with self.assertRaisesRegex(ValueError, "conflicting"):
            self.report(rows, calls + [other])
        self.assertEqual(self.report(rows, calls, memory=lambda _address, length: b"\x90" * length)["positive"], [])


class MmapFunctionSpanTests(unittest.TestCase):
    def elf(self, *, duplicate=False, oversized=False, executable=True):
        names = b"\0vm_mmap_pgoff\0__vm_munmap\0"
        symbols = [(0, 0, 0, 0, 0, 0), (1, 0x12, 0, 1, 0x1000, 0x60),
                   (names.index(b"__vm_munmap"), 0x12, 0, 2, 0x2000, 0x100 if oversized else 0x60)]
        if duplicate:
            symbols.append((1, 0x12, 0, 1, 0x1001, 1))
        data = bytearray(0x440)
        ident = b"\x7fELF\x02\x01\x01" + b"\0" * 9
        struct.pack_into("<16sHHIQQQIHHHHHH", data, 0, ident, 2, 62, 1, 0, 0, 0x300, 0,
                         64, 0, 0, 64, 5, 0)
        data[0x100:0x200] = b"\x90" * 0x100
        data[0x200:0x200 + len(names)] = names
        for index, symbol in enumerate(symbols):
            struct.pack_into("<IBBHQQ", data, 0x240 + index * 24, *symbol)
        sections = [(0,) * 10,
                    (0, 1, 6 if executable else 2, 0x1000, 0x100, 0x80, 0, 0, 16, 0),
                    (0, 1, 6, 0x2000, 0x180, 0x80, 0, 0, 16, 0),
                    (0, 3, 0, 0, 0x200, len(names), 0, 0, 1, 0),
                    (0, 2, 0, 0, 0x240, len(symbols) * 24, 3, 1, 8, 24)]
        for index, section in enumerate(sections):
            struct.pack_into("<IIQQQQIIQQ", data, 0x300 + index * 64, *section)
        return bytes(data)

    def spans(self, data):
        # This creates a finite data fixture on the VM; it is never executed.
        with tempfile.TemporaryDirectory(prefix="kd-mm-span-case-") as directory:
            path = Path(directory) / "image.elf"
            path.write_bytes(data)
            return read_function_spans(path)

    def test_exact_function_names_and_file_backed_extents(self):
        spans = self.spans(self.elf())
        self.assertEqual(set(spans), {"vm_mmap_pgoff", "__vm_munmap"})
        self.assertEqual((spans["vm_mmap_pgoff"]["start"], spans["vm_mmap_pgoff"]["end"]), (0x1000, 0x1060))
        self.assertEqual((spans["__vm_munmap"]["start"], spans["__vm_munmap"]["end"]), (0x2000, 0x2060))

    def test_ambiguous_or_nonexecutable_or_oversize_symbols_are_refused(self):
        for parameters in ({"duplicate": True}, {"oversized": True}, {"executable": False}):
            with self.subTest(parameters=parameters), self.assertRaises(ValueError):
                self.spans(self.elf(**parameters))
