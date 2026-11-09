"""Opt-in original-image learning and retained current-position handback checks.

Reuse the generic fixture, caller control, source retirement and daemon. Old
returned-body modes keep their own stricter unchanged-publication contracts.
"""
import fcntl
import os
from pathlib import Path
import re
import shutil
import signal
import struct
import time

from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection
import bench_runtime as rt
from killable_mode import (DEVICE, PARAMETERS, RELEASE, control, snapshot,
                           trace_events, session_class as killable_session)
from helper_mode import (ARGUMENTS, expected_result, read_service_call_table,
                         descriptor_rows, session_class as helper_session)

SNAPSHOT = 0x83384513
FLAGS = (131072, 262144, 524288)


def decode_snapshot(packet):
    rt.require(len(packet) == 824, 'ordinary callee observation length differs', 'DATA_ERROR')
    words = struct.unpack('=103Q', packet)
    result = dict(version=words[0], wrapper=words[1], leaves=list(words[2:5]), body=words[5],
                  errors=words[6], slots=[])
    rt.require(result['version'] == 1 and not result['errors'] and result['wrapper'] > 0 and
               all(result['leaves']) and len(set(result['leaves'])) == 3,
               'ordinary callee observation identity differs', 'DATA_ERROR')
    for index in range(8):
        row = words[7 + 12 * index:19 + 12 * index]
        result['slots'].append(dict(calls=row[0], pid=row[1], entry_sp=row[2], return_word=row[3],
                                    arguments=list(row[4:10]), result=row[10], after=row[11]))
    return result


def ordinary_snapshot():
    packet = bytearray(824)
    with open(DEVICE, 'rb', buffering=0) as device:
        fcntl.ioctl(device, SNAPSHOT, packet, True)
    return decode_snapshot(packet)


def decoded_source_blocks(assembly):
    # Only source-block comments emitted from actual decoder blocks count.
    # Missing-callee stubs also have loc_<address> labels and count as absent.
    return {int(match['address'], 16): match['source'] for match in re.finditer(
        r'/\*\n(?P<source>.*?)\n \*/[ \t]*\nloc_(?P<address>[0-9a-f]+):\n',
        assembly, re.S)}


def decoded_ret_successors(source_blocks):
    # A bare x86 RET is one byte. Use actual decoded single-instruction blocks,
    # including the shared kernel return thunk, rather than guessing a callee PC.
    return {start + 1 for start, text in source_blocks.items()
            if [line.strip() for line in text.splitlines()[1:] if line.strip()] == ['RET']}


def validate_root(events, pid, slot, observation, image, return_words):
    roots = [event for event in events if event['origin'] == pid and event['depth'] == 0]
    entered = [event for event in roots if event['event'] == 'enter']
    rt.require(len(entered) == 1, 'ordinary body lacks one actual executor entry', 'NO_JIT')
    root = entered[0]
    fields = ('origin', 'executor', 'identity', 'generation', 'object', 'entry')
    rt.require(root['executor'] > 0 and root['executor'] != pid and root['identity'] > 0 and
               root['generation'] > 0 and root['may_delegate'] and root['entry'] == image['entry'] and
               all(all(event[field] == root[field] for field in fields) and
                   event.get('image_generation') == image['generation'] for event in roots),
               'ordinary body exact root/executor identity changed', 'DATA_ERROR')
    row = observation['slots'][slot]
    rt.require(row['calls'] == row['after'] == 1 and row['pid'] == pid and
               row['arguments'] == [slot, *ARGUMENTS] and row['result'] == expected_result(slot) and
               row['entry_sp'] > 0 and row['return_word'] in return_words,
               'ordinary callee arguments, source stack/return word or once-only effects differ', 'DATA_ERROR')
    handbacks = [event for event in roots if event['event'] == 'handoff_ready']
    returned = [event for event in roots if event['event'] == 'returned']
    if handbacks:
        finished = [event for event in roots if event['event'] == 'handoff_finished']
        rt.require(len(handbacks) == len(finished) == 1 and not returned and
                   roots.index(root) < roots.index(handbacks[0]) < roots.index(finished[0]),
                   'handback acceptance/terminal sequence differs', 'DATA_ERROR')
        point = handbacks[0]
        at_entry = (point.get('ip') in (observation['wrapper'], observation['leaves'][slot]) and
                    point.get('sp') == row['entry_sp'])
        after_return = point.get('ip') == row['return_word'] and point.get('sp') == row['entry_sp'] + 8
        rt.require(point.get('image_generation') == image['generation'] and
                   (at_entry or after_return),
                   'first unexecuted source IP/SP or capture image differs', 'DATA_ERROR')
        return root, point
    rt.require(len(returned) == 1 and not any(event['event'] == 'handoff_finished' for event in roots),
               'compiled body lacks its distinct returned completion', 'DATA_ERROR')
    return root, None


def source_call_return_offset(kind, addend, code, offset):
    # The snapshot stores the wrapper address as an absolute signed immediate.
    # It is not a source CALL and cannot supply a valid return-word location.
    if kind == 11:
        return None
    rt.require(kind in (2, 4) and addend == -4 and offset > 0 and code[offset - 1] == 0xE8,
               'ordinary wrapper source CALL encoding differs', 'DATA_ERROR')
    return offset + 4


def source_return_words(module):
    result = []
    with Path(module).open('rb') as source:
        elf = ELFFile(source)
        for section in elf.iter_sections():
            if not isinstance(section, RelocationSection):
                continue
            target = elf.get_section(section['sh_info'])
            if not target['sh_flags'] & 4:
                continue
            symbols = elf.get_section(section['sh_link'])
            for relocation in section.iter_relocations():
                if symbols.get_symbol(relocation['r_info_sym']).name != 'jit_test_handoff_wrapper':
                    continue
                offset = relocation['r_offset']
                return_offset = source_call_return_offset(relocation['r_info_type'], relocation['r_addend'],
                                                          target.data(), offset)
                if return_offset is None:
                    continue
                base = int((Path('/sys/module/jit_continuation_test/sections') / target.name).read_text(), 16)
                result.append(dict(section=target.name, offset=offset - 1, return_word=base + return_offset))
    rt.require(result, 'ordinary wrapper has no source CALL relocation', 'DATA_ERROR')
    return result


def source_jump_successor(module, wrapper):
    with Path(module).open('rb') as source:
        elf = ELFFile(source)
        symbols = [symbol for symbol in elf.get_section_by_name('.symtab').iter_symbols()
                   if symbol.name == 'jit_test_handoff_wrapper']
        rt.require(len(symbols) == 1, 'ordinary wrapper source symbol differs', 'DATA_ERROR')
        symbol = symbols[0]
        section = elf.get_section(symbol['st_shndx'])
        offset, length = symbol['st_value'], symbol['st_size']
        code = section.data()[offset:offset + length]
        rt.require(code.startswith(bytes.fromhex('f30f1efa')) and code.endswith(bytes.fromhex('ffe0')),
                   'ordinary wrapper source register JMP differs', 'DATA_ERROR')
        return wrapper + length


def session_class(base):
    class HandoffSession(killable_session(base)):
        after_source_retire = helper_session(base).after_source_retire

        def counts(self, label):
            if label == 'initial':
                self.helper_table_before = descriptor_rows(read_service_call_table(PARAMETERS))
            return super().counts(label)

        def pause_daemon(self):
            rt.require(self.daemon is not None and self.daemon.poll() is None and
                       not rt.children(self.daemon.pid), 'compiler is active before learning pause', 'UNDRAINED')
            os.kill(self.daemon.pid, signal.SIGSTOP)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if re.search(r'^State:\s+T', Path(f'/proc/{self.daemon.pid}/status').read_text(), re.M):
                    rt.require(not rt.children(self.daemon.pid), 'compiler raced learning pause', 'UNDRAINED')
                    return
                time.sleep(.005)
            raise rt.Failure('UNDRAINED', 'daemon learning pause did not complete', unsafe=True)

        def archive_image(self, label):
            publication = self.publication()
            entry = self.registry(label, 0)[0]
            rt.require(publication['entry']['generation'] == entry['generation'], 'publication changed during archive')
            folder = self.path / 'workspace/daemon' / hex(entry['entry']) / str(entry['tgid'])
            output = self.path / 'publications' / label
            output.mkdir(parents=True)
            files = {}
            for name in ('asm/jit.S', 'asm/jit.bin', 'asm/bin.txt', 'asm/callee_table.txt', 'asm/ij_table.txt'):
                source = folder / name
                rt.require(source.is_file(), 'learning artifact missing: ' + str(source), 'DATA_ERROR')
                dest = output / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, dest)
                files[name] = rt.digest(dest)
            assembly = (output / 'asm/jit.S').read_text()
            state = ordinary_snapshot()
            source_blocks = decoded_source_blocks(assembly)
            rt.write_json(output / 'source-blocks.json', source_blocks)
            coverage = {str(target): target in source_blocks
                        for target in (state['wrapper'], *state['leaves'], state['body'])}
            row = dict(label=label, entry=entry, files=files, coverage=coverage,
                       ret_next_pcs=sorted(decoded_ret_successors(source_blocks)),
                       source=publication['source'], path=str(output))
            pending = getattr(self, 'pending_learning', None)
            if pending is not None:
                calls = {int(line, 16) for line in (output / 'asm/callee_table.txt').read_text().splitlines() if line}
                edges = {tuple(int(word, 16) for word in line.split())
                         for line in (output / 'asm/ij_table.txt').read_text().splitlines() if line}
                rt.require(entry['generation'] > pending['generation'] and
                           (pending['target'] in calls if pending['status'] == 1 else
                            (pending['jump_from'], pending['target']) in edges),
                           'replacement omitted the actual reported CALL/IJ history', 'DATA_ERROR')
                row['learned_report'] = pending
                self.pending_learning = None
            self.record.setdefault('publications', []).append(row)
            self.save()
            return row

        def await_learning(self, previous):
            os.kill(self.daemon.pid, signal.SIGCONT)
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                self.faults()
                rt.require(self.daemon.poll() is None, 'daemon exited while learning')
                rows = self.registry_rows()
                if (len(rows) == 1 and rows[0]['entry'] == previous['entry'] and rows[0]['status'] == 0 and
                        rows[0]['generation'] > previous['generation'] and not rt.children(self.daemon.pid)):
                    self.pause_daemon()
                    return
                time.sleep(.02)
            raise rt.Failure('TIMEOUT', 'later immutable image was not published', unsafe=True)

        def drained(self, label):
            state = self.observe(label, lambda row: row['idle'] == 1)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                self.faults()
                source = rt.status()
                progress = (PARAMETERS / 'service_progress').read_text()
                if source['frames'] == 0 and 'total=0 shown=0' in progress:
                    return dict(workload=state, source=source, service_progress=progress)
                time.sleep(.005)
            raise rt.Failure('UNDRAINED', 'handoff frames/storage did not drain', unsafe=True)

        def ordinary_phase(self, name, index, image):
            result = self.phase_begin(name)
            client = self.start(name, 0, index, FLAGS[index])
            pid = client[0].pid
            self.observe(name + '-callee', lambda state: ordinary_snapshot()['slots'][index]['calls'] == 1)
            at_callee = ordinary_snapshot()
            self.faults()
            before_release = trace_events(self.messages[self.trace_start:])
            ready = [event for event in before_release if event['event'] == 'handoff_ready' and event['origin'] == pid]
            rt.require(len(ready) == 1, 'cold ordinary callee did not hand back before checkpoint', 'NO_JIT')
            control(RELEASE, 16)
            if index == 2:
                held = self.observe(name + '-read-tail', lambda state: state['slots'][index]['tail_ready'] == 1)
                rt.require(held['readers'] == 1, 'downgraded Native read credit was not retained', 'DATA_ERROR')
                successor = self.start(name + '-fresh-writer', 0, 3)
                queued = self.observe(name + '-reader-drain', lambda state:
                    successor[0].pid in state['queue_pid'] and state['slots'][3]['prefix'] == 0)
                rt.require(queued['readers'] == 1, 'fresh writer bypassed retained read tail', 'DATA_ERROR')
                result['read_credit_before_release'] = queued
                control(RELEASE, 8)
                self.join(successor)
            self.join(client)
            result['drain'] = self.drained(name + '-drain')
            observation = ordinary_snapshot()
            self.faults()
            events = trace_events(self.messages[self.trace_start:])
            root, point = validate_root(events, pid, index, observation, image['entry'], self.return_words)
            final = snapshot()
            body = final['slots'][index]
            rt.require(body['prefix'] == body['returned'] == 1 and body['result'] == 0,
                       'origin body prefix/return was repeated or lost', 'DATA_ERROR')
            if index == 1:
                children = [event for event in events if event['origin'] == pid and event['event'] == 'child_grant']
                releases = [event for event in events if event['origin'] == pid and event['event'] == 'native_release']
                rt.require(len(children) == 1 and children[0]['depth'] == 1 and
                           (children[0]['identity'], children[0]['generation']) != (root['identity'], root['generation']) and
                           events.index(children[0]) < events.index(point) and
                           len(releases) == 2 and body['child_prefix'] == 1 and
                           all(all(release[key] == acquired[key] for key in
                               ('origin', 'executor', 'identity', 'generation', 'object', 'depth', 'entry'))
                               for release, acquired in zip(releases, (root, children[0]))),
                           'nested retained owner or non-LIFO release proof differs', 'DATA_ERROR')
            if index == 2:
                rt.require(any(event['event'] == 'downgrade' and event['origin'] == pid for event in events) and
                           any(event['event'] == 'native_read_custody' and event['origin'] == pid for event in events) and
                           body['tail_done'] == 0x1234 and final['slots'][3]['prefix'] == 1 and not final['readers'],
                           'Native read custody/release or fresh writer proof differs', 'DATA_ERROR')
            pending = self.remember_report(image, point, observation)
            result.update(complete=True, origin=pid, observation=observation, at_callee=at_callee,
                          service_events=events, handback=point, pending_report=pending,
                          execution='EXACT_CURRENT_POSITION_HANDBACK')
            self.save()
            return point

        def remember_report(self, image, point, observation):
            pending = self.registry_rows()
            immutable = ('pid', 'tgid', 'lock_kind', 'entry', 'code', 'entry_abi', 'requirements', 'generation')
            expected_status = 1 if point['ip'] == observation['wrapper'] else 2
            valid_from = (pending and pending[0]['jump_from'] in image['ret_next_pcs']
                          if point['ip'] in self.return_words else
                          pending and pending[0]['jump_from'] == (0 if expected_status == 1 else self.jump_successor))
            rt.require(len(pending) == 1 and all(pending[0][key] == image['entry'][key] for key in immutable) and
                       pending[0]['status'] == expected_status and pending[0]['target'] == point['ip'] and valid_from,
                       'capture image changed or its actual source CALL/IJ/RET report differs', 'DATA_ERROR')
            self.pending_learning = pending[0]
            return pending

        def compiled_phase(self, image, index=0):
            result = self.phase_begin('learned-return-' + str(index) + '-' + str(image['entry']['generation']))
            control(RELEASE, 16 | (8 if index == 2 else 0))
            client = self.start(result['name'], 0, index, FLAGS[index])
            self.join(client)
            result['drain'] = self.drained(result['name'] + '-drain')
            self.faults()
            observation = ordinary_snapshot()
            events = trace_events(self.messages[self.trace_start:])
            root, point = validate_root(events, client[0].pid, index, observation, image['entry'], self.return_words)
            rt.require(image['coverage'][str(observation['wrapper'])] and
                       image['coverage'][str(observation['leaves'][index])] and
                       image['coverage'][str(observation['body'])],
                       'later image did not execute learned ordinary targets on E', 'NO_JIT')
            final = snapshot()['slots'][index]
            rt.require(final['prefix'] == final['returned'] == 1 and final['result'] == 0,
                       'learned prefix or API return differs', 'DATA_ERROR')
            if point is not None:
                rt.require(point['ip'] == observation['slots'][index]['return_word'],
                           'decoded callee reached an unexpected frontier', 'DATA_ERROR')
                result['pending_report'] = self.remember_report(image, point, observation)
            result.update(complete=True, service_events=events, observation=observation, handback=point,
                          execution='LEARNED_BODY_RETURNED_ON_EXECUTOR' if point is None else
                                    'POST_RET_SOURCE_CONTINUATION_HANDBACK')
            self.save()
            return point

        def cancellation_phase(self):
            result = self.phase_begin('killable-cancel-while-held')
            holder = self.start('cancel-holder', 1, 4)
            self.observe('cancel-holder-ready', lambda state: state['holder_mask'] == 1)
            client = self.start('cancel-writer', 0, 5)
            pid = client[0].pid
            self.observe('cancel-writer-queued', lambda state: pid in state['queue_pid'])
            os.kill(pid, signal.SIGKILL)
            canceled = self.observe('canceled-before-holder-release', lambda state: state['slots'][5]['returned'] == 1)
            self.join(client, killed=True)
            rt.require(canceled['holder_mask'] == 1 and canceled['slots'][5]['result'] == -4 and
                       canceled['slots'][5]['prefix'] == canceled['slots'][5]['child_prefix'] == 0 and
                       pid not in canceled['queue_pid'] and rt.status()['frames'] == 0 and
                       'total=0 shown=0' in (PARAMETERS / 'service_progress').read_text(),
                       'killable cancellation did not retire before the holder released', 'DATA_ERROR')
            control(RELEASE, 1)
            self.join(holder)
            result['drain'] = self.drained('canceled-source-drain')
            self.faults()
            events = trace_events(self.messages[self.trace_start:])
            rt.require(len([event for event in events if event['event'] == 'cancel' and event['origin'] == pid]) == 1 and
                       not any(event['event'] == 'enter' and event['origin'] == pid for event in events),
                       'canceled request entered a body or lost its exact cancellation', 'DATA_ERROR')
            result.update(complete=True, canceled=canceled, service_events=events)
            self.save()

        def compiled_read_phase(self, image):
            result = self.phase_begin('learned-read-tail-and-fresh-writer')
            control(RELEASE, 16)
            reader = self.start('learned-read-tail', 0, 2, FLAGS[2])
            held = self.observe('learned-tail-held', lambda state: state['slots'][2]['tail_ready'] == 1)
            rt.require(held['readers'] == 1 and not held['slots'][2]['returned'],
                       'learned executor did not retain a real downgraded credit', 'DATA_ERROR')
            writer = self.start('learned-fresh-writer', 0, 3)
            queued = self.observe('learned-writer-draining', lambda state:
                writer[0].pid in state['queue_pid'] and state['slots'][3]['prefix'] == 0)
            rt.require(queued['readers'] == 1, 'fresh compiled writer bypassed the held read tail', 'DATA_ERROR')
            control(RELEASE, 8)
            self.join(reader)
            self.join(writer)
            result['drain'] = self.drained('learned-read-write-drain')
            self.faults()
            events = trace_events(self.messages[self.trace_start:])
            observation = ordinary_snapshot()
            root, point = validate_root(events, reader[0].pid, 2, observation, image['entry'], self.return_words)
            successor = [event for event in events if event['origin'] == writer[0].pid and event['event'] == 'enter']
            returned = [event for event in events if event['origin'] == writer[0].pid and event['event'] == 'returned']
            rt.require(point is None and len(successor) == len(returned) == 1 and
                       successor[0]['executor'] != writer[0].pid and successor[0]['object'] == root['object'] and
                       (successor[0]['identity'], successor[0]['generation']) != (root['identity'], root['generation']) and
                       any(event['event'] == 'read_release' and event['origin'] == reader[0].pid for event in events) and
                       not any(event['event'] == 'handoff_ready' for event in events),
                       'delegated read tail or newly acquired successor writer did not return on E', 'NO_JIT')
            final = snapshot()
            rt.require(final['slots'][2]['tail_done'] == 0x1234 and final['slots'][3]['prefix'] == 1 and
                       final['slots'][3]['returned'] == 1 and final['slots'][3]['result'] == 0 and not final['readers'],
                       'fresh writer result or reader-credit retirement differs', 'DATA_ERROR')
            result.update(complete=True, held=held, queued=queued, service_events=events,
                          observation=observation, execution='DELEGATED_READ_TAIL_THEN_FRESH_WRITER')
            self.save()

        def measure(self):
            self.clients = []
            self.record['execution_status'] = 'MEASURING'
            self.record['escape_events'] = []
            (PARAMETERS / 'service_trace').write_text('1\n')
            self.return_site_records = source_return_words(self.workload_module)
            self.return_words = {row['return_word'] for row in self.return_site_records}
            self.record['source_call_sites'] = self.return_site_records
            ordinary = ordinary_snapshot()
            self.jump_successor = source_jump_successor(self.workload_module, ordinary['wrapper'])
            declared = {int(line.split()[1], 16) for line in read_service_call_table(PARAMETERS).splitlines()}
            rt.require(not {ordinary['wrapper'], *ordinary['leaves'], ordinary['body']} & declared,
                       'ordinary learning target was declared as a runtime service', 'DATA_ERROR')
            self.pause_daemon()
            seen = set()
            for wave in range(6):
                image = self.archive_image('root-' + str(wave))
                if (image['coverage'][str(ordinary['wrapper'])] and image['coverage'][str(ordinary['leaves'][0])] and
                        image['coverage'][str(ordinary['body'])]):
                    rt.require({ordinary['wrapper'], ordinary['leaves'][0]} <= seen,
                               'cold direct CALL and actual indirect edge were not both observed', 'NO_JIT')
                    point = self.compiled_phase(image)
                    if point is None:
                        break
                else:
                    point = self.ordinary_phase('root-cold-' + str(wave), 0, image)
                seen.add(point['ip'])
                self.await_learning(image['entry'])
            else:
                raise rt.Failure('NO_JIT', 'ordinary targets did not finish within bounded learning waves')
            for index, name in ((1, 'nested-cold'), (2, 'read-tail-cold')):
                image = self.archive_image(name)
                rt.require(not image['coverage'][str(ordinary['leaves'][index])],
                           'required nested/read cold target was already in the image', 'DATA_ERROR')
                self.ordinary_phase(name, index, image)
                self.await_learning(image['entry'])
            for wave in range(3):
                image = self.archive_image('read-return-' + str(wave))
                rt.require(image['coverage'][str(ordinary['leaves'][2])] and image['coverage'][str(ordinary['body'])],
                           'read leaf/body was not learned before the compiled read-tail check', 'NO_JIT')
                point = self.compiled_phase(image, index=2)
                if point is None:
                    break
                self.await_learning(image['entry'])
            else:
                raise rt.Failure('NO_JIT', 'read return continuation exceeded bounded learning waves')
            self.compiled_read_phase(image)
            self.cancellation_phase()
            self.record.update(accepted=True, jit_status='COLD_HANDOFF_AND_LATER_COMPILED_RETURN')
            self.save()

        def stop_daemon(self):
            if self.daemon is not None and self.daemon.poll() is None:
                rt.require(not rt.children(self.daemon.pid), 'translator has not exited', 'UNDRAINED')
                # A stopped daemon must see termination before it can compile
                # a pending report. The parent keeps its same child/drain guard.
                self.daemon.terminate()
                self.daemon.send_signal(signal.SIGCONT)
            super().stop_daemon()

    return HandoffSession
