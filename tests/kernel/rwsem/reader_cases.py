"""Reader/mode assertions over actual fixture operations and saved scalar rows.

Imported only by the VM runner for the selected rwsem/rwlock family. This module
creates no producer, publication, ownership or source-state objects.
"""


class ReaderCases:
    def __init__(self, family, args, results, control, wait, observations, has,
                 body_case, check_atomic, retirement):
        self.family, self.args, self.results = family, args, results
        self.control, self.wait, self.observations, self.has = control, wait, observations, has
        self.body_case, self.check_atomic, self.retirement = body_case, check_atomic, retirement
        self.atomic = family == "rwlock"
        self.read_lock, self.read_unlock = (11, 12) if self.atomic else (6, 7)
        self.write_lock, self.write_unlock = (13, 14) if self.atomic else (8, 9)
        self.calls = ()
        self.proofs = []
        self.misses = []
        results["reader_family"] = family
        # Keep completed checks in an actual failure receipt too. Appending a
        # diagnostic never changes the top-level failed/incomplete disposition.
        results["reader_checks"] = self.proofs
        results["reader_miss_records"] = self.misses

    def rows(self, begin):
        return self.observations()[begin:]

    def typed(self, row, operation):
        call = next((call for call in self.calls if call["site"] == row["ip"]
                     and "operation" in call), None)
        return (self.has(row, "JIT_OPERATION") and row["result"] == operation and call is not None
                and row["cursor"] == call["site"] + call["length"])

    def credits(self, rows):
        active, per_object, pairs = {}, {}, []
        for row in rows:
            if self.has(row, "READ_ACQUIRE") or self.has(row, "WRITE_DOWNGRADE_REAL"):
                key = tuple(row[name] for name in ("related", "state", "acquisition", "source_user"))
                if not all(key) or key in active or not row["object"]:
                    raise AssertionError("read credit lacks a distinct exact acquisition/user")
                if self.has(row, "READ_ACQUIRE") and (row["owner"] or row["node"]):
                    raise AssertionError("shared credit was represented as an exclusive owner")
                reserve = next((prior for prior in reversed(rows) if prior["index"] < row["index"]
                                and self.has(prior, "SLOT_RESERVE") and prior["state"] == row["state"]
                                and prior["acquisition"] == row["acquisition"]), None)
                if reserve is None:
                    raise AssertionError("read credit has no exact preceding request reservation")
                end = next((later["index"] for later in rows if later["index"] > reserve["index"]
                            and self.has(later, "SLOT_RESERVE") and later["related"] == reserve["related"]
                            and later["owner"] == reserve["owner"]), rows[-1]["index"] + 1)
                if (row["index"] >= end or any(self.has(prior, "SLOT_FREE")
                        and reserve["index"] < prior["index"] < row["index"]
                        and prior["related"] == reserve["related"] and prior["owner"] == reserve["owner"]
                        for prior in rows)):
                    raise AssertionError("read credit escaped its actual reserved slot lifetime")
                active[key] = (row, reserve, end)
                per_object.setdefault((row["state"], row["object"]), []).append(key)
            elif self.has(row, "READ_RELEASE"):
                key = tuple(row[name] for name in ("related", "state", "acquisition", "source_user"))
                lifetime = active.pop(key, None)
                stack = per_object.get((row["state"], row["object"]), [])
                if lifetime is None or not stack or stack[-1] != key:
                    raise AssertionError("read release did not select the latest exact open credit")
                opened, reserve, end = lifetime
                if not opened["index"] < row["index"] < end:
                    raise AssertionError("read release crossed its request slot lifetime")
                stack.pop()
                free = next((later for later in rows if row["index"] < later["index"] < end
                             and self.has(later, "SLOT_FREE") and later["state"] == row["state"]
                             and later["acquisition"] == row["acquisition"]
                             and all(later[field] == reserve[field] for field in
                                     ("node", "related", "owner", "parent"))
                             and later["flags"] & (32 | 64) == (32 | 64)), None)
                if free is None:
                    raise AssertionError("released reader credit lacks final exact request retirement")
                pairs.append({"reserve": reserve, "acquire": opened, "release": row, "free": free})
        if active:
            raise AssertionError("reader case retained an open credit after native task drain")
        return pairs

    def clean(self, values, workers):
        if (int(values["finished"]) != workers or int(values["completed"]) != workers
                or any(int(values[name]) for name in ("errors", "origin_errors", "core_errors", "rw_errors"))
                or int(values["locks_clear"]) != 1):
            raise AssertionError("reader effects/context or physical cleanup differ")
        if self.atomic:
            self.check_atomic(values, workers)

    def native_scene(self, mode):
        begin = len(self.observations())
        self.control(f"readscene {mode}")
        self.wait(lambda value: int(value["ready"], 16) == 7, f"readscene{mode}-ready")
        self.control("readgo 0")
        first_stage = 1 if mode in (1, 2) else 2
        self.wait(lambda value: int(value["rw_stage0"]) == first_stage, f"readscene{mode}-first")
        self.control("readgo 1")
        self.wait(lambda value: int(value["rw_attempt1"]) == 1, f"readscene{mode}-second-attempt")
        if mode == 1:
            self.control("readconvert")
        if mode != 2:
            overlap_raw, overlap = self.wait(lambda value: int(value["rw_stage0"]) == 2
                and int(value["rw_stage1"]) == 2, f"readscene{mode}-overlap")
            self.control("readgo 2")
            self.wait(lambda value: int(value["rw_attempt2"]) == 1, f"readscene{mode}-writer-attempt")
            self.control("readrelease 0")
            self.wait(lambda value: int(value["rw_stage0"]) == 3, f"readscene{mode}-first-release")
            self.control("readrelease 1")
            self.wait(lambda value: int(value["rw_stage2"]) == 1, f"readscene{mode}-writer-held")
            self.control("readrelease 2")
        else:
            self.control("readgo 2")
            self.wait(lambda value: int(value["rw_attempt1"]) and int(value["rw_attempt2"]),
                      "writer-first-readers-attempt")
            self.control("readrelease 0")
            overlap_raw, overlap = self.wait(lambda value: int(value["rw_stage1"]) == 2
                and int(value["rw_stage2"]) == 2, "writer-first-readers-overlap")
            self.control("readrelease 1"); self.control("readrelease 2")
        raw, final = self.wait(lambda value: int(value["finished"]) == 3, f"readscene{mode}-done")
        self.clean(final, 3)
        self.control("stop")
        rows = self.rows(begin)
        credits = self.credits(rows)
        if len(credits) != 2:
            raise AssertionError("native scene did not retain its two exact shared credits")
        first, second = sorted(credits, key=lambda pair: pair["acquire"]["index"])
        if not first["acquire"]["index"] < second["acquire"]["index"] < first["release"]["index"]:
            raise AssertionError("two readers never actually overlapped")
        writer_grants = [row for row in rows if self.has(row, "GRANT")
                         and row["object"] == first["acquire"]["object"]]
        if len(writer_grants) != (2 if mode == 1 else 1):
            raise AssertionError("native reader scene writer grant count differs")
        writer = writer_grants[-1]
        if mode != 2 and writer["index"] <= max(pair["release"]["index"] for pair in credits):
            raise AssertionError("writer entered before the last exact reader credit release")
        if mode == 2:
            request = next((row for row in rows if self.has(row, "RELEASE_REQUEST")
                            and row["acquisition"] == writer["acquisition"] and row["state"] == writer["state"]), None)
            if request is None or any(pair["acquire"]["index"] <= request["index"] for pair in credits):
                raise AssertionError("reader entered before the writer's matching release operation")
        if mode == 1:
            converted = next((pair for pair in credits if self.has(pair["acquire"], "WRITE_DOWNGRADE_REAL")), None)
            if converted is None or not any(self.has(row, "NATIVE_MODE") and row["result"] == 10 for row in rows):
                raise AssertionError("native downgrade did not establish a real same-grant reader")
            physical = next((row for row in rows if self.has(row, "PHYSICAL_END")
                             and row["owner"] == converted["acquire"]["owner"]), None)
            if physical is None or not converted["acquire"]["index"] < physical["index"] < converted["release"]["index"]:
                raise AssertionError("local writer was retained through its logical read tail")
        proof = {"name": ("concurrent-readers", "local-real-downgrade", "writer-first-readers")[mode],
                 "overlap_status": overlap_raw, "final_status": raw, "credits": credits}
        self.proofs.append(proof)

    def native(self):
        self.native_scene(0)
        self.native_scene(2)
        if not self.atomic:
            self.native_scene(1)
        begin = len(self.observations())
        self.body_case("native-repeated-read", 8, 1, 1)
        pairs = self.credits(self.rows(begin))
        if len(pairs) != 2 or pairs[0]["acquire"]["acquisition"] == pairs[1]["acquire"]["acquisition"]:
            raise AssertionError("repeated real reads did not retain two distinct acquisitions")
        self.proofs.append({"name": "native-repeated-read", "credits": pairs})

    def training(self, compiler_cycle):
        modes = [5, 6, 7, 8] + ([] if self.atomic else [9, 11])
        for mode in modes:
            self.body_case(f"learn-reader-{mode}", mode, 1 if mode == 8 else self.args.workers,
                           1 if mode == 8 else self.args.iterations)
            compiler_cycle()

    def source_scene(self, mode, image):
        begin = len(self.observations())
        self.control(f"scene {mode}")
        _, first = self.wait(lambda value: int(value["ready"], 16) == 31, f"reader{mode}-ready")
        tasks = [int(first[f"role{index}"], 16) for index in range(5)]
        self.control("go 0")
        self.wait(lambda value: int(value["held"], 16) & 1, f"reader{mode}-A-holder")
        if mode not in (9, 10):
            self.control("go 1")
            self.wait(lambda value: int(value["held"], 16) & 2, f"reader{mode}-B-holder")
        self.control("go 2")
        self.wait(lambda value: int(value["queued"], 16) & 4, f"reader{mode}-CA")
        self.control("go 4")
        if mode != 7:
            self.wait(lambda value: int(value["queued"], 16) & 16, f"reader{mode}-W")
        self.control("go 3")
        if mode not in (9, 10):
            self.wait(lambda value: int(value["queued"], 16) & 8, f"reader{mode}-CB")
        else:
            self.control("go 1")
        self.control("release 0")
        if mode in (6, 12):
            self.wait(lambda value: int(value["w_read_attempts"]) > 0, f"reader{mode}-shared-B-attempt")
            self.control("release 1")
        elif mode == 7:
            object_b = int(first["object_b"], 16)
            self.wait(lambda value: any(self.has(row, "ENQUEUE") and row["origin"] == tasks[4]
                and row["object"] == object_b for row in self.rows(begin)), "read-write-B-enqueue")
            self.control("release 1")
        elif mode == 11:
            self.wait(lambda value: int(value["child"], 16) != 0, "downgrade-B-child")
            self.control("release 1")
        raw, final = self.wait(lambda value: int(value["finished"]) == 5, f"reader{mode}-done")
        self.clean(final, 5)
        expected = {6: (4, 2, 0, 1, 0, 0), 7: (4, 1, 1, 1, 0, 0),
                    9: (3, 2, 0, 2, 1, 1), 10: (3, 2, 0, 2, 1, 2),
                    11: (4, 2, 1, 2, 1, 1), 12: (3, 2, 0, 1, 0, 1)}[mode]
        actual = tuple(int(final[name]) for name in ("calls", "a", "b", "rw_effects", "rw_post", "rw_native"))
        if actual != expected:
            raise AssertionError(f"reader source effects repeated or disappeared: {actual} != {expected}")
        self.control("stop")
        rows = self.rows(begin)
        credits = self.credits(rows)
        state = int(final["w_core"], 16)
        entries = [row for row in rows if self.has(row, "JIT_ENTER") and row["state"] == state
                   and row["image"] == image and row["task"] != tasks[4]]
        if not entries or (self.atomic and any(not row["flags"] & (1 << 12) for row in entries)):
            raise AssertionError("reader source lacks an actual foreign admitted generated entry")
        proof = {"name": f"reader-source-{mode}", "mode": mode, "fixed_image": image,
                 "state": state, "roles": tasks, "credits": credits, "raw_status": raw,
                 "entries": entries, "start": begin, "end": len(self.observations())}
        writer = next((row for row in rows if self.has(row, "ENQUEUE") and row["state"] == state
                       and row["origin"] == tasks[4] and row["task"] == tasks[4]), None)
        child = next((row for row in rows if mode == 11 and self.has(row, "ENQUEUE")
                      and row["state"] == state and row["origin"] == tasks[4]
                      and row["task"] == tasks[2]), None)
        if writer is None or (mode == 11 and child is None):
            raise AssertionError("reader case lost its actual writer request lifetime")
        self.retirement(rows, writer, child, 1, image)
        proof.update(writer=writer, child=child)
        if mode == 6:
            shared = next((pair for pair in credits if pair["acquire"]["state"] == state
                           and pair["acquire"]["object"] == int(final["object_b"], 16)
                           and pair["acquire"]["task"] == tasks[2]), None)
            accepted = next((row for row in rows if self.typed(row, self.read_unlock)
                             and row["state"] == state and row["object"] == int(final["object_b"], 16)), None)
            resumed = next((row for row in entries if accepted and row["index"] > accepted["index"]
                            and row["task"] == tasks[2] and row["cursor"] == accepted["cursor"]), None)
            if shared is None or accepted is None or resumed is None or not shared["release"]["index"] < accepted["index"]:
                raise AssertionError("shared B read release did not resume the enclosing A proxy")
            proof.update(shared=shared, accepted=accepted, resumed=resumed)
        elif mode in (9, 10, 11):
            retained = next((row for row in rows if self.has(row, "WRITE_DOWNGRADE_RETAINED")
                             and row["state"] == state and row["phase"] == 2), None)
            if retained is None:
                raise AssertionError("proxy downgrade did not retain its exact writer acquisition")
            grant = next((row for row in rows if self.has(row, "GRANT") and row["state"] == state
                          and row["acquisition"] == retained["acquisition"]), None)
            physical = next((row for row in rows if grant and self.has(row, "PHYSICAL_END")
                             and row["owner"] == grant["owner"] and row["index"] > retained["index"]), None)
            if grant is None or physical is None or retained["owner"] != grant["owner"]:
                raise AssertionError("retained read lost its original physical writer custody")
            competitor = next((pair for pair in credits if pair["acquire"]["origin"] == tasks[1]
                               and pair["acquire"]["object"] == retained["object"]), None)
            requested = next((row for row in rows if self.has(row, "RELEASE_REQUEST")
                              and row["state"] == state and row["acquisition"] == retained["acquisition"]
                              and row["index"] > retained["index"]), None)
            begun = next((row for row in rows if self.has(row, "PHYSICAL_BEGIN")
                          and row["owner"] == grant["owner"] and row["index"] > retained["index"]), None)
            # Reader admission can linearize inside the release callback, before
            # its later PHYSICAL_END diagnostic. Source acceptance still waits
            # for that full callback and exact physical ACK below.
            if (competitor is None or requested is None or begun is None
                    or not requested["index"] < begun["index"] < competitor["acquire"]["index"]):
                raise AssertionError("reader entered before matching retained up_read began physical release")
            if mode != 10:
                accepted = next((row for row in rows if self.typed(row, self.read_unlock)
                                 and row["state"] == state and row["object"] == retained["object"]
                                 and row["index"] > retained["index"]), None)
                forwarded = next((row for row in rows if accepted and self.has(row, "FORWARD")
                                  and row["state"] == state and row["cursor"] == accepted["cursor"]
                                  and row["index"] > accepted["index"]), None)
                if accepted is None or forwarded is None or not physical["index"] < accepted["index"]:
                    raise AssertionError("retained up_read did not return the exact completed continuation to W")
                if any(row["index"] > forwarded["index"] for row in entries):
                    raise AssertionError("an ancestor revived generated source after retained up_read")
                proof.update(accepted=accepted, forwarded=forwarded)
            else:
                self.record_miss(proof, rows, state, int(final["rw_miss_target"], 16))
                accepted = next((row for row in rows if self.has(row, "NATIVE_UNLOCK") and row["state"] == state
                                 and row["result"] == self.read_unlock and row["index"] > retained["index"]), None)
                if accepted is None or not physical["index"] < accepted["index"]:
                    raise AssertionError("post-downgrade native up_read completed before physical writer ACK")
                proof["native_accepted"] = accepted
            if mode == 11:
                ancestor = next((row for row in rows if self.has(row, "GRANT") and row["state"] == state
                                 and row["object"] == int(final["object_a"], 16)), None)
                old_release = next((row for row in rows if ancestor and self.has(row, "PHYSICAL_END")
                                    and row["owner"] == ancestor["owner"]), None)
                if ancestor is None or old_release is None or old_release["index"] <= proof["forwarded"]["index"]:
                    raise AssertionError("nested downgrade discarded its ancestor's retained physical duty")
                proof.update(ancestor=ancestor, ancestor_physical=old_release)
            proof.update(retained=retained, writer_grant=grant, physical=physical, competitor=competitor,
                         requested=requested, physical_begin=begun)
        elif mode == 12:
            self.record_miss(proof, rows, state, int(final["rw_miss_target"], 16))
        if mode == 7:
            outer = next((pair for pair in credits if pair["acquire"]["state"] == state
                          and pair["acquire"]["object"] == int(final["object_a"], 16)), None)
            selected = next((row for row in rows if self.has(row, "SELECT_PROXY") and row["state"] == state
                             and row["object"] == int(final["object_b"], 16) and row["task"] == tasks[3]), None)
            if outer is None or selected is None or not outer["acquire"]["index"] < selected["index"] < outer["release"]["index"]:
                raise AssertionError("nested writer did not retain the outer read credit")
            proof.update(outer_read=outer, nested_writer=selected)
        self.proofs.append(proof)
        return proof

    def record_miss(self, proof, rows, state, target):
        exited = next((row for row in rows if self.has(row, "JIT_EXIT") and row["state"] == state
                       and row["result"] == 3 and row["phase"] == 2 and row["related"] == target), None)
        if exited is None:
            raise AssertionError("read-held suffix lacks its exact once-staged ordinary CALL miss")
        call = next((call for call in self.calls if call["site"] == exited["ip"] and call["target"] == target), None)
        if call is None or call["site"] + call["length"] <= call["site"]:
            raise AssertionError("miss does not match its actual source CALL bytes")
        proof["miss"] = exited
        self.misses.append(exited)

    def warm(self, image):
        begin = len(self.observations())
        self.body_case("warm-repeated-read", 8, 1, 1)
        self.proofs.append({"name": "warm-repeated-read", "credits": self.credits(self.rows(begin))})
        self.source_scene(6, image)
        self.source_scene(7, image)
        if not self.atomic:
            self.source_scene(9, image)
            self.source_scene(11, image)

    def deliberate_misses(self, image):
        self.source_scene(12, image)
        if not self.atomic:
            self.source_scene(10, image)

    def archived(self, states, archive):
        keys = []
        for miss in self.misses:
            found = [state for state in states if state.recorded.fact.exit.source_ip == miss["ip"]
                     and state.recorded.fact.exit.target == miss["related"]
                     and state.recorded.fact.exit.kind == 3 and state.recorded.fact.exit.phase == 2]
            if (len(found) != 1 or found[0].recorded.fact.key not in archive.settlement.keys
                    or found[0].acknowledgment_identities):
                raise AssertionError("deliberate reader miss was not exactly retained and SETTLED")
            fact = found[0].recorded.fact
            keys.append({"record": fact.record_identity.hex(), "incarnation": fact.incarnation})
        self.results["reader_checks"] = self.proofs
        self.results["reader_miss_archived"] = keys
