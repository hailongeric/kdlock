"""Frozen pure policy validators for the native-first archive report.

Derived from the reviewed experimental session/run helpers. No live runner,
module operation or archived Python is imported or executed. Extraction and
normalization receipts are in audit-helper-provenance.json.
"""
from pathlib import Path
import re

from bench_runtime import ROOT, require

def tc_quiescent(params, lock_kind='spin'):
    # Exact parameter identity also rejects accidentally loading the previous
    # instrumented module. Protocol node/count state remains part of the oracle.
    expected = {'target_lock', 'komb_batch_size', 'quiescent'}
    if lock_kind == 'mutex':
        expected |= {'delegated', 'batches', 'parks'}
    require(set(params) == expected,
            'unexpected TCLock module parameters')
    require(params['quiescent'] == 1, 'active TCLock stack/queue', 'UNDRAINED')


OWNED_CALLER_FIELDS = ('owned_mutex_cabi', 'owned_caller_policy', 'owned_entry_abi',
                       'owned_mutex_native_first', 'owned_mutex_native_first_spins',
                       'owned_mutex_early_release')


def parse_owned_native_first_profile(messages, record):
    """ABI4 helper outcomes are separate from ABI2 gate and JIT counters."""
    enabled = record.get('profile_owned_native_first', False)
    require(type(enabled) is bool, 'invalid owned native-first profile flag')
    rows = re.findall(r'kd_mutex_profile ownednativefirst: ([^\n]+)', messages)
    if not enabled:
        require(not rows, 'unexpected owned native-first profile receipt')
        return None
    require(record.get('profile_lock') and record.get('diagnostic') and
            record.get('arm') == 'kdlock' and record.get('mutex_implementation') == 'owned-v1' and
            check_owned_caller_policy(record) and record.get('owned_mutex_native_first') is True and
            not record.get('profile_owned_preflight', False),
            'native-first profile requires an unscored ABI4 native-first caller')
    require(len(rows) == 1, 'missing or duplicate owned native-first profile receipt')
    fields = {'acquired', 'promote', 'self', 'other', 'missed'}
    tokens = rows[0].split()
    require(all(re.fullmatch(r'[a-z_]+=[0-9]+', token) for token in tokens),
            'malformed owned native-first counters')
    pairs = [token.split('=', 1) for token in tokens]
    require(len(pairs) == len(fields) and {key for key, _ in pairs} == fields,
            'incomplete owned native-first counters')
    result = {key: int(value) for key, value in pairs}
    require(result['other'] == result['missed'] == 0,
            'owned native-first profile missed returns or saw an unknown enum')
    return result


def check_owned_caller_policy(record):
    """Keep old ABI2 archives valid without normalizing their missing identity."""
    if not any(key in record for key in OWNED_CALLER_FIELDS):
        require(record.get('entry_abi', 2) == 2, 'unrecorded owned caller is not ABI2')
        return False
    require(all(key in record for key in OWNED_CALLER_FIELDS),
            'incomplete owned caller policy')
    cabi = record['owned_mutex_cabi']
    native_first = record['owned_mutex_native_first']
    spins = record['owned_mutex_native_first_spins']
    require(type(cabi) is bool and type(native_first) is bool and
            type(record['owned_mutex_early_release']) is bool and
            record['owned_caller_policy'] == ('c_abi_v2' if cabi else 'clobber_v1') and
            type(record['owned_entry_abi']) is int and
            record['owned_entry_abi'] == record.get('entry_abi') == (4 if cabi else 2) and
            record.get('caller_abi') == ('c' if cabi else 'clobber') and
            record.get('caller_shell') == ('owned_mutex_outer_cabi' if cabi else 'owned_mutex_outer_cookie'),
            'owned caller policy or ABI differs')
    require((not native_first or cabi) and type(spins) is int and
            spins in (1024, 4096) and (native_first or spins == 4096),
            'owned native-first policy or budget differs')
    require(not cabi or (record.get('owned_mutex_preflight') is False and
            record.get('owned_preflight_policy') == 'not_applicable' and
            record.get('owned_mutex_preflight_spins') == 0 and
            record.get('owned_mutex_preflight_queue') is False),
            'owned ABI4 cannot use ABI2 preflight')
    return cabi


def check_kd_parameters(params, record, lock_addr):
    # Parameter identity rejects an old provider that can disable mutex JIT.
    # Returned-body evidence remains a separate execution requirement.
    require(params['bench_quiet'] == 'Y' and params['jit_timing'] == 'N' and
            int(params['bench_lock_addr']) == lock_addr and
            'hotlock_mode' not in params and 'mutex_jit' not in params and
            int(params['spin_entry_ratio_limit']) == record['spin_entry_ratio_limit'] and
            int(params['spin_prefetch']) == record['spin_prefetch'] and
            'spin_cold_fastpath' not in params and 'spin_hot_min_queue' not in params and
            'mutex_blocking' not in params and record['mutex_wait_mode'] == 'blocking' and
            params['spin_delegate'] == ('N' if record.get('spin_delegate') == 'off' else 'Y'),
            'kdlock observation parameters differ')
    if record.get('mutex_implementation', 'legacy') == 'owned-v1':
        cabi = check_owned_caller_policy(record)
        require({'owned_mutex_spin_limit', 'owned_mutex_entry_ratio_limit',
                 'owned_mutex_self_route', 'owned_mutex_native_after_control'} <= set(params),
                'missing owned mutex provider parameters')
        require(record.get('mutex_routing', 'adaptive') in ('adaptive', 'self') and
                int(params['owned_mutex_spin_limit']) == record['mutex_spin_limit'] and
                int(params['owned_mutex_entry_ratio_limit']) == record['owned_mutex_entry_ratio_limit'] and
                params['owned_mutex_self_route'] == ('Y' if record.get('mutex_routing') == 'self' else 'N') and
                params['mutex_native_route'] == 'N' and
                int(params['owned_mutex_native_after_control']) ==
                int(record.get('owned_mutex_force_full', False)),
                'owned mutex observation parameters differ')
        # The initial finite-FIFO archive predates this opt-in control.
        require(('owned_mutex_refill' not in record or 'owned_mutex_refill' in params) and
                params.get('owned_mutex_refill', 'N') ==
                ('Y' if record.get('owned_mutex_refill', False) else 'N'),
                'owned FIFO refill parameter differs')
        policy = record.get('owned_preflight_policy')
        budget = record.get('owned_mutex_preflight_spins')
        enabled = record.get('owned_mutex_preflight')
        require('owned_mutex_preflight' not in record or (type(enabled) is bool and
                policy == ('not_applicable' if cabi else 'c_abi_v1' if enabled else 'capture_first')),
                'owned preflight compile-time policy differs')
        require((policy is None and budget is None and
                 int(params.get('owned_mutex_preflight_spins', 0)) == 0) or
                (policy == 'capture_first' and enabled is False and type(budget) is int and budget == 0 and
                 'owned_mutex_preflight_spins' in params and int(params['owned_mutex_preflight_spins']) == 0) or
                (cabi and policy == 'not_applicable' and enabled is False and type(budget) is int and budget == 0 and
                 'owned_mutex_preflight_spins' in params and int(params['owned_mutex_preflight_spins']) == 0) or
                (policy == 'c_abi_v1' and type(budget) is int and
                 budget in (0, 64, 256, 1024, 4096) and
                 'owned_mutex_preflight_spins' in params and
                 int(params['owned_mutex_preflight_spins']) == budget),
                'owned preflight policy or parameter differs')
        queued = record.get('owned_mutex_preflight_queue')
        require((queued is None and params.get('owned_mutex_preflight_queue', 'N') == 'N') or
                (type(queued) is bool and 'owned_mutex_preflight_queue' in params and
                 params['owned_mutex_preflight_queue'] == ('Y' if queued else 'N') and
                 (not queued or (policy == 'c_abi_v1' and budget > 0))),
                'owned queued preflight policy or parameter differs')
        for name in ('owned_mutex_native_first', 'owned_mutex_early_release'):
            require((name not in record or name in params) and
                    params.get(name, 'N') == ('Y' if record.get(name, False) else 'N'),
                    'owned caller stage provider parameter differs: ' + name)
        require(('owned_mutex_native_first_spins' not in record or
                 'owned_mutex_native_first_spins' in params) and
                int(params.get('owned_mutex_native_first_spins', 4096)) ==
                record.get('owned_mutex_native_first_spins', 4096),
                'owned native-first provider spin budget differs')
    else:
        require(int(params['mutex_spin_limit']) == record['mutex_spin_limit'] and
                int(params['mutex_entry_ratio_limit']) == record['mutex_entry_ratio_limit'] and
                params['mutex_native_route'] == ('Y' if record.get('mutex_routing') == 'native' else 'N'),
                'kdlock observation parameters differ')


def check_jit_evidence(record):
    # A policy may select self-execution. Keep NO_JIT explicit and retain all
    # publication/body counters; contended protocol positives still fail
    # without a returned body. Valid throughput is not JIT acceptance.
    record['execution_class'] = ('NATIVE' if record['arm'] == 'native' else
                                 'JIT' if record.get('jit_bodies', 0) > 0 else 'NO_JIT')
    if record['arm'] == 'kdlock' and record.get('lock_kind') == 'mutex':
        owned = record.get('mutex_implementation', 'legacy') == 'owned-v1'
        if owned:
            require(record.get('mutex_routing', 'adaptive') != 'native',
                    'owned mutex cannot use a Linux native route')
            record['execution_class'] = 'JIT' if record.get('jit_bodies', 0) > 0 else 'KD_SELF'
        if record.get('mutex_routing') == 'self':
            require(owned and record.get('jit_bodies', 0) == 0, 'self routing control executed JIT or is not owned')
            require(not record.get('functional', False), 'self control is not a functional JIT check')
            record.update(jit_acceptance='SELF_ROUTING_CONTROL', execution_class='KD_SELF', diagnostic=True)
            return
        if record.get('mutex_routing', 'adaptive') == 'native':
            require(record.get('jit_bodies', 0) == 0, 'native routing control executed JIT')
            require(not record.get('functional', False), 'native control is not a functional JIT check')
            record.update(jit_acceptance='NATIVE_ROUTING_CONTROL',
                          execution_class='NATIVE_ROUTING_CONTROL', diagnostic=True)
            return
        if record.get('mutex_acceptance', 'jit-required') == 'adaptive-performance':
            require(not record.get('functional', False), 'adaptive performance is not a functional JIT check')
            record['jit_acceptance'] = ('PASS' if record.get('jit_bodies', 0) > 0 else
                                        'ADAPTIVE_SELF' if owned else 'ADAPTIVE_NATIVE')
            record['execution_class'] = ('JIT' if record.get('jit_bodies', 0) > 0 else
                                         'KD_SELF' if owned else 'ADAPTIVE_NATIVE')
            return
    if (record['arm'] == 'kdlock' and record.get('lock_kind', 'spin') == 'spin' and
            record.get('spin_delegate', 'on') == 'off'):
        require(record.get('jit_bodies', 0) == 0, 'disabled control executed JIT')
        record['jit_acceptance'] = 'DISABLED_CONTROL'
        return
    # Adaptive admission samples actual MCS entries. Small cohorts can become
    # hot; do not infer native-only execution from their thread count.
    if (record['arm'] == 'kdlock' and record['threads'] in (2, 3) and
            record.get('scenario', 'plain') == 'plain' and
            not record.get('functional', False)):
        # Fast/pending acquisitions and native MCS queue heads can complete
        # without a serviceable follower. Preserve small-group performance data
        # while keeping zero returned bodies distinct from a JIT positive.
        record['jit_acceptance'] = ('PASS' if record.get('jit_bodies', 0) > 0
                                    else 'NO_JIT_LOW_CONTENTION')
        return
    required = (record['arm'] == 'kdlock' and record['threads'] > 1 and
                (record.get('functional', False) or record['threads'] >= 20 or
                 (record.get('lock_kind') == 'mutex' and record['threads'] >= 4) or
                 record.get('scenario', 'plain') in ('nested', 'early')))
    record['jit_acceptance'] = ('PASS' if record.get('jit_bodies', 0) > 0 else 'NO_JIT')
    require(not required or record['jit_bodies'] > 0,
            'contended kdlock arm had no actual JIT', 'NO_JIT')


MUTEX_ENTRY_RATIO_LIMITS = tuple(1 << shift for shift in range(1, 9))


OWNED_MUTEX_PREFLIGHT_SPINS = (0, 64, 256, 1024, 4096)


POST_WORK_SOURCE = 'workload_modules/spin_cacheline/post_work.h'


def source_post_work_rounds(root=None):
    """Read the fixed workload source; this is provenance, not a build override."""
    source = ((ROOT if root is None else Path(root))/POST_WORK_SOURCE).read_text()
    definitions = re.findall(
        r'^[ \t]*#[ \t]*define[ \t]+SC_POST_WORK_ROUNDS[ \t]+([0-9]+)[ \t]*$',
        source, re.MULTILINE)
    require(len(definitions) == 1, 'post-work source needs one literal round definition')
    rounds = int(definitions[0])
    require(1 <= rounds <= 256, 'post-work rounds must be 1..256')
    return rounds
