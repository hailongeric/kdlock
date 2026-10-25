#!/usr/bin/env python3
"""Pure saved-evidence replay for the prospective prepared mmap window."""
import json
from pathlib import Path

import window


def qualify_window(out, client, directory, before, transport_endpoint, ready):
    import paired as p
    controller = p.common.load(directory / 'controller.json')
    endpoint_path = directory / 'window-endpoint.json'
    receipt = p.common.load(endpoint_path)
    roles_path = directory / 'window-roles.json'
    roles = p.common.load(roles_path)
    control = p.load_bound(client['window_control'])
    window.control_replay(control)
    admission = window.role_manifest(roles)
    window.require(all(window.admission_policy(r) == admission for r in (receipt, controller, client, ready, control)),
                   'mixed admission policies')
    if admission == window.WORKER_ADMISSION:
        window.require(ready['window_roles']['sha256'] == controller['roles_sha256'], 'readiness role policy differs')
        for digest in roles['evidence'].values():
            window.require(p.rt.digest(directory / 'role-evidence' / digest) == digest, 'retained role evidence differs')
        window.check_settling(control['post_setup_settling'])
        window.require(type(control['started_monotonic_ns']) is int and
                       control['post_setup_settling']['finished_ns'] <= control['started_monotonic_ns'],
                       'client started before post-setup settling completed')
    window.require(all(r.get(k) == v for r in (receipt, controller, client, ready)
                       for k, v in window.binding().items()), 'window policy/source binding differs')
    for name, key in (('window_controller.py', 'window_controller_sha256'),
                      ('window_host.py', 'window_observer_sha256')):
        window.require(controller[key] == p.rt.digest(Path(__file__).with_name(name)), 'window helper changed')
    window.require(controller['window_endpoint_sha256'] == p.rt.digest(endpoint_path) == control['endpoint_sha256'] and
                   controller['roles_sha256'] == p.rt.digest(roles_path), 'endpoint/role binding differs')
    window.require(receipt['nonce'] == controller['nonce'] == control['nonce'] and
                   control['completion_token'] == controller['completion_token'] and
                   controller['host_window_returncode'] == 0 and
                   not controller['host_window_completion_unconfirmed'], 'incomplete/mixed control exchange')
    protocol = window.Protocol(controller['nonce'])
    for event in controller['events']:
        window.require(event['nonce'] == protocol.nonce, 'controller nonce changed')
        protocol.add(event['event'])
    window.require(len(protocol.events) == len(protocol.ORDER), 'incomplete controller ordering')
    times = [controller[k] for k in ('go_sent_monotonic_ns', 'finished_observed_monotonic_ns',
              'endpoint_requested_monotonic_ns', 'endpoint_observed_monotonic_ns',
              'export_sent_monotonic_ns', 'guest_exit_observed_monotonic_ns')]
    window.require(all(type(v) is int for v in times) and times == sorted(times) and
                   0 <= times[2]-times[1] < 1_000_000_000, 'causal endpoint/publication order differs')
    for name, digest in controller['stream_sha256'].items():
        window.require(p.rt.digest(directory / (name + '.stream')) == digest, 'raw control stream changed')
    raw = [json.loads(line) for line in (directory / 'host.stream').read_text().splitlines()]
    window.require(raw and all(row['nonce'] == receipt['nonce'] for row in raw) and
                   raw[-1]['event'] == 'endpoint' and raw[-1]['receipt'] == receipt and
                   [r['event'] for r in raw].count('guard') == 1 and
                   all(r['event'] in ('sample', 'guard', 'endpoint') for r in raw), 'host stream ordering differs')
    samples = [r['sample'] for r in raw if r['event'] == 'sample']
    window.require(samples == receipt['samples'], 'window receipt differs from streamed observations')
    guard = next(i for i, r in enumerate(raw) if r['event'] == 'guard')
    index = raw[guard]['index']
    window.require(type(index) is int and index == receipt['guard_end'] == guard - 1 and
                   len(samples) > index + 1, 'missing guard or post-completion endpoint')
    old = p.host_check(before, fresh=False, measurement_policy=window.POLICY, role_manifest=roles)
    core = window.core_inventory(old, before)
    window.require(core == receipt['core'] == controller['core'], 'core admission binding differs')
    expected_identity = {k: p.PROFILE['host'][k] for k in ('pid', 'start_ticks', 'command_sha256')}
    check_args = dict(admission=admission, qemu_identity=expected_identity)
    resolved = roles['roles'] if admission == window.WORKER_ADMISSION else window.resolve_roles(samples[0]['tasks'], core, roles['roles'])
    window.require(resolved == receipt['roles'] and
                   all(r['evidence'] in roles['evidence'].values() for r in resolved), 'role evidence differs')
    window.check_samples(samples[:index+1], core, resolved, **check_args)
    deltas = window.check_samples(samples, core, resolved, **check_args)
    if admission == window.WORKER_ADMISSION:
        window.require(receipt['worker_activity'] == deltas, 'worker lifetime/activity record differs')
        observed = [r for r in deltas['lifetimes'] if r['role'] != 'core']
    else:
        window.require(receipt['final_deltas'] == deltas[-len(core)-len(resolved):], 'counter deltas differ')
        observed = resolved
    window.require(receipt['passed'] and receipt['observer_affinity'] == [62] and
                   type(receipt['observer_cpu_ns']) is int and receipt['observer_cpu_ns'] >= 0,
                   'observer activity/settings differ')
    # At S0 all counter reads precede GO; the last sample follows FINISHED.
    # Host/guest/source timestamps are never subtracted across clock domains.
    window.require(samples[-1]['end_ns'] - samples[index]['end_ns'] <= window.WINDOW_TIMEOUT_NS,
                   'window completion bound exceeded')
    end = receipt['environment_endpoint']
    p.host_check(end, fresh=False, measurement_policy=window.POLICY, role_manifest=roles)
    p.host_environment(end, ready['environment'], ready['topology'], window.POLICY, roles)
    key = lambda tasks: sorted((t['tid'], t['start_ticks'], t['comm'], t['affinity']) for t in tasks)
    window.require(key(core) == key(window.core_inventory(old, end)) ==
                   key(window.core_inventory(old, transport_endpoint)), 'core lifetime changed at endpoint')
    window.require(control['stdout_sha256'] == p.rt.digest(out / 'client.jsonl') and
                   control['stderr_sha256'] == p.rt.digest(out / 'client.stderr') and
                   (out / 'client.stderr').stat().st_size == 0, 'client output binding differs')
    return dict(**window.binding(), endpoint=p.bind(endpoint_path), roles=p.bind(roles_path),
                **window.admission_fields(roles),
                control=client['window_control'], host_stream=p.bind(directory / 'host.stream'),
                observer_cpu_ns=receipt['observer_cpu_ns'], observer_elapsed_ns=receipt['observer_elapsed_ns'],
                observed_auxiliaries=observed)
