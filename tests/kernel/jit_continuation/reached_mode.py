"""Positive family/artifact proof for explicitly selected image-free checks.

The image mode keeps its original immutable-image checks. This mode starts no
translator and requires exact other-task service traces plus resident execution
observations; an unpublished entry alone cannot pass.
"""
import re

import bench_runtime as rt
from killable_mode import PARAMETERS, trace_events

STATS = ('roots', 'completions', 'instructions', 'controls', 'primitives',
         'memory', 'cache_hits', 'cache_misses', 'cache_full', 'unsupported', 'active')
HEXADECIMAL = {'identity', 'entry', 'ip', 'next', 'target', 'sp'}


def parse_stats(text):
    words = text.split()
    pairs = [word.split('=', 1) for word in words]
    rt.require(all(len(pair) == 2 for pair in pairs) and
               len({pair[0] for pair in pairs}) == len(pairs),
               'reached execution counter format differs', 'DATA_ERROR')
    values = dict(pairs)
    rt.require(set(STATS) <= values.keys(), 'reached execution counters missing', 'DATA_ERROR')
    row = {key: int(values[key]) for key in STATS}
    rt.require(all(value >= 0 for value in row.values()), 'negative reached observation', 'DATA_ERROR')
    return row


def reached_events(messages):
    rows = []
    for line in messages.splitlines():
        if 'kd_reached event=' not in line:
            continue
        fields = dict(re.findall(r'(\w+)=([^\s]+)', line))
        event = fields.get('event')
        if event not in ('family', 'service', 'resume', 'retire'):
            continue
        required = {'origin', 'executor', 'identity', 'generation', 'family_generation'}
        required |= {'entry'} if event in ('family', 'retire') else {
            'artifact_sequence', 'kind', 'ip', 'target', 'sp'}
        rt.require(required <= fields.keys(), 'reached family/artifact trace incomplete', 'DATA_ERROR')
        row = {'event': event}
        for key in required:
            row[key] = fields[key] if key == 'kind' else int(
                fields[key], 16 if key in HEXADECIMAL else 10)
        rows.append(row)
    return rows


def validate_ledger(messages, successful, canceled=()):
    roots = [row for row in trace_events(messages) if row['event'] == 'enter']
    reached = reached_events(messages)
    result = []
    for pid in successful:
        matches = [row for row in roots if row['origin'] == pid]
        rt.require(len(matches) == 1, 'reached root entry is missing or repeated', 'DATA_ERROR')
        root = matches[0]
        rt.require(root.get('family_generation') == root['generation'] > 0 and
                   root['executor'] != pid, 'reached root family/executor differs', 'DATA_ERROR')
        same = [row for row in reached if row['origin'] == pid and
                row['identity'] == root['identity'] and row['generation'] == root['generation']]
        rt.require(all(row['family_generation'] == root['generation'] for row in same),
                   'reached request changed family generation', 'DATA_ERROR')
        families = [row for row in same if row['event'] == 'family']
        rt.require(len(families) == 1 and families[0]['entry'] == root['entry'] and
                   families[0]['executor'] in (0, root['executor']),
                   'reached root lacks its exact source family', 'DATA_ERROR')
        services = [row for row in same if row['event'] in ('service', 'resume')]
        rt.require(len(services) % 2 == 0, 'unacknowledged reached artifact', 'UNDRAINED')
        seen = set()
        for index in range(0, len(services), 2):
            request, reply = services[index:index + 2]
            rt.require(request['event'] == 'service' and reply['event'] == 'resume' and
                       request['artifact_sequence'] > 0 and
                       request['artifact_sequence'] not in seen and
                       request['kind'] in ('control', 'primitive', 'memory') and
                       request['executor'] == root['executor'] and
                       all(request[key] == reply[key] for key in (
                           'origin', 'executor', 'identity', 'generation', 'family_generation',
                           'artifact_sequence', 'kind', 'ip', 'target', 'sp')),
                       'reached artifact reply or exact source custody differs', 'DATA_ERROR')
            seen.add(request['artifact_sequence'])
        # Every actual Native/GS transaction must name one retained artifact;
        # duplicated or omitted declarations cannot be masked by root totals.
        for kind, marker in (('primitive', 'kd_service primitive:'), ('memory', 'kd_service memory:')):
            requests = []
            for line in messages.splitlines():
                if marker not in line:
                    continue
                fields = dict(re.findall(r'(\w+)=([^\s]+)', line))
                if fields.get('stage') != 'request' or int(fields.get('origin', '-1')) != pid:
                    continue
                rt.require({'family_generation', 'artifact_sequence'} <= fields.keys(),
                           'cold returning service lacks retained artifact identity', 'DATA_ERROR')
                requests.append((int(fields['family_generation']), int(fields['artifact_sequence'])))
            declared = [(row['family_generation'], row['artifact_sequence']) for row in services
                        if row['event'] == 'service' and row['kind'] == kind]
            rt.require(requests == declared, 'returning service and reached artifact ledgers differ', 'DATA_ERROR')
        result.append(dict(root=root, family=families[0], artifacts=services))
    for pid in canceled:
        rt.require(not any(row['origin'] == pid and row['event'] == 'service' for row in reached),
                   'canceled acquisition published a body service artifact', 'DATA_ERROR')
    rt.require(set(row['origin'] for row in roots) == set(successful),
               'unexpected cold root entered this phase', 'DATA_ERROR')
    return result


def validate_jit(messages, roots):
    events = []
    for line in messages.splitlines():
        if 'kd_reached event=jit ' not in line:
            continue
        fields = dict(re.findall(r'(\w+)=([^\s]+)', line))
        required = {'origin', 'executor', 'identity', 'generation', 'entries', 'retired', 'interpreted', 'code'}
        rt.require(required <= fields.keys(), 'incomplete generated-code execution record', 'DATA_ERROR')
        events.append({name: int(fields[name], 16 if name in ('identity', 'code') else 10)
                       for name in required})
    checked = []
    for root in roots:
        matches = [event for event in events if all(event[name] == root[name]
                   for name in ('origin', 'identity', 'generation'))]
        rt.require(len(matches) == 1, 'root lacks one exact generated-code completion record', 'DATA_ERROR')
        event = matches[0]
        rt.require(event['executor'] == root['executor'] != root['origin'] and
                   event['entries'] >= event['retired'] > 0 and
                   event['interpreted'] == 0 and event['code'] > 0,
                   'root did not return from other-task JIT execution without interpretation', 'DATA_ERROR')
        checked.append(event)
    return checked


def session_class(base):
    class ReachedSession(base):
        def service_generation(self):
            # No image exists. Family and exact artifact identity are checked
            # independently in every transaction and in the phase ledger.
            return 0

        def reached_stats(self):
            return parse_stats((PARAMETERS / 'reached_stats').read_text())

        def registry(self, label, expected):
            rows = self.registry_rows()
            rt.write_json(self.path / (label + '.registry.json'), rows)
            rt.require(all(row['status'] == -1 and row['generation'] == 0 and
                           row['requirements'] == 0 and row['lock_kind'] == 2 and
                           row['entry_abi'] == 2 and row['entry'] == self.record['layout']['entry']
                           for row in rows),
                       'image-free execution published an image or another entry', 'DATA_ERROR')
            return rows

        def publication(self):
            source = rt.status()
            stats = self.reached_stats()
            rt.require(source['state'] == 0 and source['frames'] == source['writers'] == 0 and
                       stats['active'] == 0 and stats['unsupported'] == 0,
                       'image-free source/family/service state is not drained', 'UNDRAINED')
            dependencies = self.record.setdefault('reached_source_modules', [])
            rt.require(not dependencies or source['modules'] >= dependencies[-1],
                       'source dependencies retired before session teardown', 'UNDRAINED')
            dependencies.append(source['modules'])
            # Reached targets may add resident module dependencies. Exact
            # ownership remains in the production source registry; this view
            # observes append-only growth and checks complete final retirement.
            return dict(mode='reached', source={key: source[key] for key in ('state', 'frames', 'writers')},
                        entries=self.registry('image-free-publication', 0))

        def prepare_reached(self):
            rt.require((PARAMETERS / 'service_reached').read_text().strip() == 'Y',
                       'image-free execution mode was not enabled', 'ENVIRONMENT')
            rt.require(self.daemon is None and not (self.path / 'workspace').exists(),
                       'image-free check unexpectedly created a translator workspace', 'DATA_ERROR')
            self.record['image_registry'] = self.registry('initial', 0)
            self.record['publication'] = self.publication()
            self.record['initial_parameters'] = rt.parameters()
            rt.require(self.record['initial_parameters']['target_process'] == 'kc_worker',
                       'provider worker eligibility name differs')
            self.record['reached'] = dict(before=self.reached_stats(), translator_started=False)
            self.save()

        def phase_begin(self, name):
            row = super().phase_begin(name)
            row['reached_before'] = self.reached_stats()
            self.save()
            return row

        def phase_end(self, result, successful=(), canceled=(), **kwargs):
            super().phase_end(result, successful=successful, canceled=canceled, **kwargs)
            messages = self.messages[self.trace_start:]
            roots = [row for row in trace_events(messages) if row['event'] == 'enter' and
                     row['origin'] in successful]
            result['jit_execution'] = validate_jit(messages, roots)
            after = self.reached_stats()
            before = result['reached_before']
            rt.require(all(after[key] >= before[key] for key in STATS if key != 'active'),
                       'reached observations moved backwards', 'DATA_ERROR')
            delta = {key: after[key] - before[key] for key in STATS}
            rt.require(after['active'] == 0 and delta['roots'] == delta['completions'] == len(successful) and
                       delta['unsupported'] == 0 and
                       delta['controls'] >= len(successful) and
                       (delta['instructions'] > 0 if successful else delta['instructions'] == 0),
                       'cold root, completion, instruction or unfinished-operation count differs', 'DATA_ERROR')
            result['reached_after'] = after
            result['reached_delta'] = delta
            result['reached_ledger'] = validate_ledger(
                self.messages[self.trace_start:], successful, canceled)
            for field, kind in (('controls', 'control'), ('primitives', 'primitive'), ('memory', 'memory')):
                declared = sum(row['event'] == 'service' and row['kind'] == kind
                               for entry in result['reached_ledger'] for row in entry['artifacts'])
                rt.require(delta[field] == declared,
                           'reached service observations and artifact ledger differ', 'DATA_ERROR')
            self.save()

        def measure(self):
            super().measure()
            final = self.reached_stats()
            rt.require(final['roots'] == final['completions'] > 0 and final['instructions'] > 0 and
                       final['cache_misses'] > 0 and final['unsupported'] == final['active'] == 0,
                       'image-free execution lacks cold progress or final family drain', 'DATA_ERROR')
            self.record['reached']['after'] = final
            for phase in self.record['phases']:
                phase['execution'] = phase.get('execution', '').replace('IMAGE', 'FAMILY')
            self.record['jit_status'] = 'REACHED_FAMILY_PROXY_AND_EXACT_RETIREMENT'
            self.save()
    return ReachedSession
