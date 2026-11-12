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
        self.learning = []
        results["reader_learning"] = self.learning
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
        fast_owners, fast_released = {}, set()
        for row in rows:
            if self.has(row, "READ_ACQUIRE") or self.has(row, "WRITE_DOWNGRADE_REAL"):
                key = tuple(row[name] for name in ("related", "state", "acquisition", "source_user"))
                if not all(key) or key in active or not row["object"]:
                    raise AssertionError("read credit lacks a distinct exact acquisition/user")
                if self.has(row, "READ_ACQUIRE") and (row["owner"] or row["node"]):
                    raise AssertionError("shared credit was represented as an exclusive owner")
                if row["flags"] & 8192:
                    if (self.family != "rwsem" or not self.has(row, "READ_ACQUIRE") or row["flags"] != 8192
                            or not row["task"] or row["task"] != row["origin"] or row["task"] in fast_owners
                            or row["related"] != row["acquisition"] or row["source_user"] != row["related"]):
                        raise AssertionError("fast shared credit has no exact original-task identity")
                    end = next((later["index"] for later in rows if later["index"] > row["index"]
                                and self.has(later, "READ_ACQUIRE") and later["flags"] & 8192
                                and later["acquisition"] == row["acquisition"]), rows[-1]["index"] + 1)
                    active[key] = (row, None, end)
                    fast_owners[row["task"]] = row
                    per_object.setdefault((row["state"], row["object"]), []).append(key)
                    continue
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
                if bool(row["flags"] & 8192) != bool(opened["flags"] & 8192):
                    raise AssertionError("read release changed its credit storage class")
                if not opened["index"] < row["index"] < end:
                    raise AssertionError("read release crossed its request slot lifetime")
                stack.pop()
                if reserve is None:
                    if row["flags"] != 8192 or row["task"] != opened["task"] or row["origin"] != row["task"]:
                        raise AssertionError("fast read physical release changed its exact owner")
                    free = next((later for later in rows if row["index"] < later["index"] < end
                                 and self.has(later, "FAST_READ_DONE") and all(later[field] == row[field]
                                 for field in ("state", "origin", "task", "object", "related", "acquisition"))
                                 and later["flags"] == 8192 and not any(later[field]
                                 for field in ("node", "owner", "source_user", "return_user", "notifier"))), None)
                    if free is None:
                        raise AssertionError("fast read credit lacks final object-access completion")
                    fast_released.add(row["task"])
                    pairs.append({"reserve": None, "acquire": opened, "release": row,
                                  "free": free, "fast_local": True})
                    continue
                free = next((later for later in rows if row["index"] < later["index"] < end
                             and self.has(later, "SLOT_FREE") and later["state"] == row["state"]
                             and later["acquisition"] == row["acquisition"]
                             and all(later[field] == reserve[field] for field in
                                     ("node", "related", "owner", "parent"))
                             and later["flags"] & (32 | 64) == (32 | 64)), None)
                if free is None:
                    raise AssertionError("released reader credit lacks final exact request retirement")
                pairs.append({"reserve": reserve, "acquire": opened, "release": row, "free": free})
            elif self.has(row, "FAST_READ_DONE"):
                opened = fast_owners.pop(row["task"], None)
                if (opened is None or row["task"] not in fast_released or any(row[field] != opened[field]
                        for field in ("state", "origin", "object", "related", "acquisition"))):
                    raise AssertionError("fast read completion crossed an acquisition lifetime")
                fast_released.remove(row["task"])
            elif self.has(row, "SELECT_PROXY") or self.has(row, "JIT_ENTER"):
                if row["task"] in fast_owners or row["origin"] in fast_owners:
                    raise AssertionError("a fast reader lent its continuation or served another origin")
        if active or fast_owners or fast_released:
            raise AssertionError("reader case retained an open credit after native task drain")
        return pairs

    def clean(self, values, workers):
        if (int(values["finished"]) != workers or int(values["completed"]) != workers
                or any(int(values[name]) for name in ("errors", "origin_errors", "core_errors", "rw_errors"))
                or int(values["locks_clear"]) != 1):
            raise AssertionError("reader effects/context or physical cleanup differ")
        if self.atomic:
            self.check_atomic(values, workers)
        elif self.family == "rwsem" and int(values["q_invalid"]):
            raise AssertionError("a physical query returned an int outside exact 0/1")

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
        if self.family == "rwsem" and mode == 1:
            proof["native_queries"] = self.query_counts(final, {4: (1, 0)}, 0)
            if any(self.has(row, "QUERY_RESULT") or self.has(row, "JIT_ENTER") for row in rows):
                raise AssertionError("the native real-downgrade scene unexpectedly entered generated query code")
        self.proofs.append(proof)

    def native(self):
        self.native_scene(0)
        self.native_scene(2)
        if not self.atomic:
            self.native_scene(1)
        begin = len(self.observations())
        self.body_case("native-read-read", 5, 1, 1)
        pairs = self.credits(self.rows(begin))
        if len(pairs) != 2:
            raise AssertionError("native distinct-object reads lost an exact credit")
        if not self.atomic and sum(pair.get("fast_local", False) for pair in pairs) != 1:
            raise AssertionError("native nested reads did not use one fast outer and one managed inner credit")
        self.proofs.append({"name": "native-read-read", "credits": pairs})
        begin = len(self.observations())
        self.body_case("native-repeated-read", 8, 1, 1)
        pairs = self.credits(self.rows(begin))
        if len(pairs) != 2 or pairs[0]["acquire"]["acquisition"] == pairs[1]["acquire"]["acquisition"]:
            raise AssertionError("repeated real reads did not retain two distinct acquisitions")
        if not self.atomic and [pair.get("fast_local", False) for pair in pairs] != [False, True]:
            raise AssertionError("same-object up_read did not release the managed inner before the fast outer")
        self.proofs.append({"name": "native-repeated-read", "credits": pairs})

    @staticmethod
    def exit_key(row):
        return (row["image"], row["result"], row["flags"], row["ip"],
                row["related"], row["cursor"], row["phase"])

    @staticmethod
    def fact_exit_key(fact):
        value = fact.exit
        return (int.from_bytes(fact.image_identity, "little"), value.kind, value.detail,
                value.source_ip, value.target, value.cursor, value.phase)

    def training(self, compiler_cycle, current_image, fact_states):
        modes = (6, 7, 12) if self.atomic else (6, 7, 9, 11, 12, 10)
        # Each pass must expose a new ordinary target or finish the selected
        # path. The caller supplies the scene bound and provisions every pass;
        # actual decoded CALL sites provide a second finite bound.
        limit = min(self.args.reader_learning_passes, len(self.calls) + 1)
        self.results["reader_learning_bound"] = {"caller_passes": self.args.reader_learning_passes,
            "decoded_call_sites": len(self.calls), "passes_per_mode": limit, "modes": list(modes)}
        for mode in modes:
            for attempt in range(1, limit + 1):
                image = current_image()
                prior_keys = {state.recorded.fact.key for state in fact_states()}
                proof, rows, final = self.source_scene(mode, image, learning=True)
                coverage = [row for row in rows if self.has(row, "JIT_EXIT") and row["result"] == 3]
                unexpected = [row for row in rows if self.has(row, "JIT_EXIT") and row["result"] not in (1, 3)]
                if unexpected:
                    raise AssertionError("controlled reader learning reached a non-coverage frontier")
                checkpoint = int(final["rw_miss_target"], 16) if mode in (10, 12) else None
                intended = [row for row in coverage if row["state"] == proof["state"]
                            and row["related"] == checkpoint and row["phase"] == 2]
                entry = {"mode": mode, "attempt": attempt, "image": image, "proof": proof,
                         "coverage_exits": coverage, "intentional_exits": intended}
                self.learning.append(entry)
                if not coverage:
                    if checkpoint is not None:
                        raise AssertionError("reader learning did not reach its deliberate native checkpoint")
                    self.validate_source_scene(proof, rows, final)
                    entry["status"] = "ordinary_path_completed"
                    break
                # Copy the actual claim and cumulative publication before any
                # further source invocation. Nonobservations remain pending.
                result = compiler_cycle()
                fresh = [state for state in fact_states() if state.recorded.fact.key not in prior_keys]
                remaining = list(fresh)
                matched = []
                for exited in coverage:
                    state = next((state for state in remaining
                                  if self.fact_exit_key(state.recorded.fact) == self.exit_key(exited)), None)
                    if state is None:
                        raise AssertionError("controlled exit lacks its exact newly recorded fact")
                    remaining.remove(state)
                    matched.append((exited, state))
                if remaining:
                    raise AssertionError("controlled claim contains an unobserved new exit")
                ordinary = []
                for exited, state in matched:
                    observation = state.recorded.feedback.observation
                    if observation is None:
                        if exited not in intended:
                            raise AssertionError("controlled reader learning reached an unexpected nonobservation")
                        continue
                    kind = ("indirect_call_target" if observation.kind.value == "call"
                            else "indirect_jump_target")
                    old = state.recorded.fact.producer
                    if (observation.target in old.emitted_sites and any(transfer.source == observation.site
                            and transfer.target == observation.target and transfer.kind == kind
                            for transfer in old.transfers)):
                        raise AssertionError("controlled miss repeated an already emitted ordinary edge")
                    ordinary.append((state, observation))
                if intended:
                    if len(intended) != 1 or any(row["state"] == proof["state"] and row not in intended
                                                 for row in coverage):
                        raise AssertionError("reader prefix handed back before its intended checkpoint")
                    self.validate_source_scene(proof, rows, final)
                if ordinary:
                    if result.candidate is None or result.publication is None or result.acknowledgment is None:
                        raise AssertionError("new ordinary scene facts lack actual publication and ACK")
                    acknowledged = set(result.acknowledgment.keys)
                    emitted = result.candidate.artifact.receipt.emitted_observations
                    if any(state.recorded.fact.key not in acknowledged or observation not in emitted
                           for state, observation in ordinary):
                        raise AssertionError("scene publication did not cover and ACK its reached ordinary miss")
                    if current_image() == image:
                        raise AssertionError("controlled learning did not advance its actual published image")
                    entry.update(status="ordinary_targets_published", next_image=current_image(),
                        acknowledged=[{"record": state.recorded.fact.record_identity.hex(),
                                       "incarnation": state.recorded.fact.incarnation}
                                      for state, _ in ordinary])
                    continue
                if len(intended) != len(coverage) or len(intended) != 1:
                    raise AssertionError("reader prefix did not end at its one exact native checkpoint")
                entry["status"] = "deliberate_checkpoint_reached"
                break
            else:
                raise AssertionError("explicit controlled reader learning pass bound exhausted")

    def source_scene(self, mode, image, learning=False):
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
            if learning:
                object_b = int(first["object_b"], 16)
                self.wait(lambda value: any(self.has(row, "ENQUEUE") and row["origin"] == tasks[4]
                    and row["object"] == object_b for row in self.rows(begin)), "learning-downgrade-B-request")
            else:
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
        if writer is None or (not learning and mode == 11 and child is None):
            raise AssertionError("reader case lost its actual writer request lifetime")
        if learning:
            requests = [row for row in rows if self.has(row, "ENQUEUE") and row["state"] == state
                        and row["origin"] == tasks[4]]
            for request in requests:
                self.retirement(rows, request, None, 1, image)
            proof.update(writer=writer, child=child, writer_requests=requests)
            return proof, rows, final
        self.retirement(rows, writer, child, 1, image)
        proof.update(writer=writer, child=child)
        return self.validate_source_scene(proof, rows, final)

    def validate_source_scene(self, proof, rows, final):
        mode, image, state = proof["mode"], proof["fixed_image"], proof["state"]
        tasks, entries, credits = proof["roles"], proof["entries"], proof["credits"]
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
        if self.family == "rwsem" and mode in (6, 9):
            proof["queries"] = self.query_scene(proof, rows, final)
        self.proofs.append(proof)
        return proof

    def query_counts(self, final, expected, role):
        if int(final["q_role"]) != role or int(final["q_invalid"]):
            raise AssertionError("query counters lack the exact original worker or contain non-Boolean ints")
        result = {}
        for point in range(5):
            prefix = f"q{point}_"
            values = {name: int(final[prefix + name]) for name in
                      ("visits", "locked", "write", "invalid", "last_locked", "last_write")}
            visits = int(point in expected)
            locked, write = expected.get(point, (0, 0))
            if (values["visits"] != visits or values["invalid"] or values["locked"] != visits * locked
                    or values["write"] != visits * write or
                    (visits and (values["last_locked"], values["last_write"]) != (locked, write))):
                raise AssertionError(f"query point {point} repeated, disappeared or returned the wrong physical predicate")
            result[point] = values
        return result

    def query_scene(self, proof, rows, final):
        image, state, origin = proof["fixed_image"], proof["state"], proof["roles"][4]
        object_a, object_b = int(final["object_a"], 16), int(final["object_b"], 16)
        unused = int(final["q_unlocked_object"], 16)
        if not unused or unused in (object_a, object_b):
            raise AssertionError("the unused B1 query object is not distinct")
        expected = {2: (1, 0)} if proof["mode"] == 6 else {0: (0, 0), 1: (1, 1), 3: (1, 1)}
        counters = self.query_counts(final, expected, 4)
        targets = {16: int(final["q_locked_target"], 16), 17: int(final["q_write_target"], 16)}
        if not all(targets.values()) or targets[16] == targets[17]:
            raise AssertionError("two distinct actual typed query targets are required")
        queries = [row for row in rows if self.has(row, "QUERY_RESULT") and row["state"] == state]
        if len(queries) != 2 * len(expected):
            raise AssertionError("fixed-image query results are missing or repeated")
        by_site = {call["site"]: call for call in self.calls if call.get("operation") == "query"}
        observations = []
        forbidden = ("GRANT", "ENQUEUE", "READ_ACQUIRE", "READ_RELEASE", "WRITE_DOWNGRADE_REAL",
                     "WRITE_DOWNGRADE_RETAINED")
        control = ("JIT_EXIT", "JIT_OPERATION", "QUERY_RESULT", "FORWARD", "EPISODE_DONE")
        for offset, (point, values) in enumerate(expected.items()):
            obj = object_b if point == 2 else unused if point == 0 else object_a
            for position, operation_kind in enumerate((16, 17)):
                row = queries[2 * offset + position]
                call = by_site.get(row["ip"])
                if (call is None or call["indirect"] or not call["raw_hex"] or
                        call["target"] != targets[operation_kind] or row["related"] != operation_kind or
                        row["object"] != obj or row["result"] != values[position] or row["phase"] != 5 or
                        row["cursor"] != call["site"] + call["length"] or row["image"] != image or
                        row["origin"] != origin or row["task"] == origin):
                    raise AssertionError("query result does not match its actual typed CALL/result/foreign executor")
                same = lambda item: all(item[name] == row[name] for name in
                                        ("state", "node", "acquisition", "origin"))
                reserves = [item for item in rows if item["index"] < row["index"] and
                            self.has(item, "SLOT_RESERVE") and same(item)]
                if not reserves:
                    raise AssertionError("query lost its exact request reservation")
                reserve = reserves[-1]
                end = next((item["index"] for item in rows if item["index"] > reserve["index"] and
                            (self.has(item, "SLOT_RESERVE") or self.has(item, "SLOT_FREE")) and
                            item["owner"] == reserve["owner"] and item["related"] == reserve["related"]),
                           float("inf"))
                if not reserve["parent"] or not reserve["owner"] or not reserve["related"] or row["index"] >= end:
                    raise AssertionError("query crossed a pool slot/claim incarnation")
                scope = [item for item in rows if reserve["index"] < item["index"] < end and same(item)]
                before = [item for item in scope if item["index"] < row["index"]]
                prepared = [item for item in before if self.has(item, "FRAME_PREPARE")]
                entered = [item for item in before if self.has(item, "JIT_ENTER")]
                if len(prepared) != 1 or not entered:
                    raise AssertionError("query has no unique frame and current generated entry")
                frame, entered = prepared[0], entered[-1]
                if (frame["image"] != image or frame["parent"] != row["parent"] or
                        entered["image"] != image or entered["task"] != row["task"] or not entered["related"]):
                    raise AssertionError("query frame/current image/binding differs")
                active = [item for item in before if item["index"] > entered["index"] and
                          any(self.has(item, name) for name in control)]
                if len(active) != 2 or not self.has(active[0], "JIT_EXIT") or not self.has(active[1], "JIT_OPERATION"):
                    raise AssertionError("query lacks its immediate source exit and prepared operation")
                exited, operation = active
                if (exited["result"] != 1 or exited["flags"] != 4 or exited["phase"] != 1 or
                        exited["ip"] != call["site"] or exited["cursor"] != call["site"] or
                        exited["related"] != call["target"] or operation["result"] != operation_kind or
                        operation["phase"] != 2 or operation["ip"] != call["site"] or
                        operation["cursor"] != call["target"] or operation["object"] != obj or operation["related"] or
                        any(item["task"] != row["task"] or item["image"] != image for item in active)):
                    raise AssertionError("query did not preserve the exact pre-CALL and entered-target phases")
                if any(item["state"] == state and exited["index"] < item["index"] < row["index"] and
                       any(self.has(item, name) for name in forbidden) for item in rows):
                    raise AssertionError("a query created or changed a source grant, queue or credit")
                resumed = next((item for item in scope if item["index"] > row["index"] and
                                self.has(item, "JIT_ENTER")), None)
                if (resumed is None or resumed["task"] != row["task"] or resumed["image"] != image or
                        resumed["related"] != entered["related"] or resumed["cursor"] != row["cursor"]):
                    raise AssertionError("query did not reenter at its exact current post-CALL continuation")
                if point == 2:
                    credit = proof["shared"]
                    support = credit["acquire"]
                    if (credit["reserve"] is None or credit["reserve"]["node"] != row["node"] or
                            support["acquisition"] != row["acquisition"] or
                            not support["index"] < row["index"] < credit["release"]["index"]):
                        raise AssertionError("shared-B query escaped its actual exact READ credit")
                else:
                    support = proof["writer_grant"]
                    if (support["node"] != row["node"] or support["acquisition"] != row["acquisition"] or
                            support["owner_task"] != row["task"] or support["index"] >= row["index"]):
                        raise AssertionError("writer query escaped its exact current physical owner")
                    retained = proof["retained"]
                    if point in (0, 1) and row["index"] >= retained["index"]:
                        raise AssertionError("write/unlocked query ran after logical downgrade")
                    if point == 3 and not retained["index"] < row["index"] < proof["physical"]["index"]:
                        raise AssertionError("retained-read query lost its physical writer")
                observations.append({"point": point, "reserve": reserve, "frame": frame,
                                     "enter": entered, "exit": exited, "operation": operation,
                                     "query": row, "resumed": resumed, "support": support, "call": call})
        if proof["mode"] == 9 and any(item["object"] == unused and
                any(self.has(item, name) for name in forbidden) for item in rows):
            raise AssertionError("the other B1 object was physically used during the controlled scene")
        return {"counters": counters, "observations": observations, "unused_object": unused}

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
        pairs = self.credits(self.rows(begin))
        if not self.atomic and [pair.get("fast_local", False) for pair in pairs] != [False, True]:
            raise AssertionError("warm repeated reads lost the distinct managed/fast release order")
        self.proofs.append({"name": "warm-repeated-read", "credits": pairs})
        if not self.atomic:
            begin = len(self.observations())
            self.body_case("warm-fast-read-write", 7, 1, 1)
            pairs = self.credits(self.rows(begin))
            if len(pairs) != 1 or not pairs[0].get("fast_local"):
                raise AssertionError("warm nested writer lost its retained fast outer reader")
            self.proofs.append({"name": "warm-fast-read-write", "credits": pairs})
        self.source_scene(6, image)
        self.source_scene(7, image)
        if not self.atomic:
            self.source_scene(9, image)
            self.source_scene(11, image)

    def deliberate_misses(self, image):
        self.source_scene(12, image)
        if not self.atomic:
            self.source_scene(10, image)

    def intentional_keys(self, states):
        # Prefix learning and final fixed-image checks can reach the same
        # intentional source exit in several image lifetimes. Preserve every
        # exact record/incarnation and its pending disposition independently.
        groups = {}
        for miss in self.misses:
            groups.setdefault(self.exit_key(miss), []).append(miss)
        keys = set()
        for signature, misses in groups.items():
            found = [state for state in states if self.fact_exit_key(state.recorded.fact) == signature]
            if len(found) != len(misses) or any(state.acknowledgment_identities for state in found):
                raise AssertionError("deliberate reader exits lost their exact unacknowledged records")
            keys.update(state.recorded.fact.key for state in found)
        return keys

    def archived(self, states, archive):
        keys = self.intentional_keys(states)
        if not keys <= set(archive.settlement.keys):
            raise AssertionError("deliberate reader exits were not exactly retained and SETTLED")
        self.results["reader_checks"] = self.proofs
        self.results["reader_miss_archived"] = [{"record": key.record_identity.hex(),
            "incarnation": key.incarnation} for key in sorted(keys,
                key=lambda key: (key.record_identity, key.incarnation))]
