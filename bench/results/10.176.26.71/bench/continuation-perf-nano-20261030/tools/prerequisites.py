"""Offline copied-receipt validation only; never import/execute archived inputs.

The exact reuse predicate is copied from reviewed nano controller c73bb5bf.
"""
import hashlib
import json
import nano_core as a

require = a.need
CURRENT = 'f7a84065e84474380faa37eeadfdf534abd72a68'
UNIT_CONTROLLER = 'fe9208ce981a4e0d524c8366fe7cce78683f45235316e0ef85514c4555fce996'
LIVE_CONTROLLER = 'fdce682d696a6eb76b6bea511b1edc02a12655fae3eec2ac5065922ff9a6359e'
UNIT_OWNER = '2356a8d0ee6a5ffd9be052a1a33db0845faada3e47b15b77fbf55a3662fbc70f'

REUSE_HASHES = {
    'owner.json': '313a1ad0a38891530ec29cd2ceb5aa781d1236056b94ea21fbb47738d32a7bea',
    'unit.log': '52068e4078c5491ab420bbc729e7bb844be55fa42f475f8823df26dfb30be757',
    'sync.json': 'e8f8c60840496de5c3636039a214321ce15b8b1f241a929e812c3f1c899b3e43',
    'controller.py': 'e60a9285bca40716fdad9dcd409026471fadbc771508eccab4483797a4247b71',
}

REUSED_DRIVERS = [
    'spin/test_spin_batch.py', 'spin/test_spin_shadow.py',
    'spin/test_spin_outer_progress.py', 'spin/test_spin_proxy_context.py',
    'mutex/test_mutex_origin_instruction.py', 'execution/test_bench_completion.py',
]

def verify_unit_reuse(unit, sync, commit, evidence):
    require(unit.get('unit_selection') == {
        'fresh': False, 'prior_checks_reused': True,
        'basic': ['basic/test_control_call', 'basic/test_daemon_policy'],
        'python_drivers': ['spin/test_spin_batch_context.py'], 'expected_passes': 3,
        'reused_python_drivers': REUSED_DRIVERS, 'effective_selected_checks': 9,
    }, 'explicit selective unit coverage differs')
    reuse = unit.get('unit_reuse', {})
    require(reuse.get('prior_source_commit') == '6bf690204fdf954ab9076a762000833ec18e6261' and
            reuse.get('current_source_commit') == commit and
            reuse.get('prior_owner_completed') is False and
            reuse.get('prior_error') == "AssertionError('unit')" and
            reuse.get('prior_unit_returncode') == 2 and
            reuse.get('prior_unit_log_sha256') == REUSE_HASHES['unit.log'] and
            reuse.get('reused_python_drivers') == REUSED_DRIVERS and
            reuse.get('reused_python_passes') == 6 and
            reuse.get('same_tracked_path_set') is True and
            reuse.get('compared_tracked_inputs') == 5922 and
            reuse.get('evidence_directory') == 'unit-reuse' and
            reuse.get('retained_sha256') == REUSE_HASHES,
            'unit reuse must retain the exact failed attempt and six passes')
    require(set(evidence) == set(REUSE_HASHES) and
            all(hashlib.sha256(evidence[name]).hexdigest() == expected
                for name, expected in REUSE_HASHES.items()), 'retained unit-reuse input differs')
    prior = json.loads(evidence['owner.json'])
    old_sync = json.loads(evidence['sync.json'])
    require(prior.get('completed') is False and prior.get('error') == "AssertionError('unit')" and
            prior.get('source_commit') == reuse['prior_source_commit'] and
            prior.get('boot_id') == unit['boot_id'] and
            [row['name'] for row in prior['blocks']] == ['kernel-identity', 'unit'] and
            [row.get('returncode') for row in prior['blocks']] == [0, 2] and
            reuse.get('prior_unit_argv') == prior['blocks'][1]['argv'],
            'failed prior unit status must remain explicit')
    old, current = old_sync['tracked_sha256'], sync['tracked_sha256']
    require(old_sync['git_head'] == reuse['prior_source_commit'] and
            old_sync['git_status'] == '' and old_sync['synchronization_completed'] is True and
            sync['git_head'] == commit and len(old) == len(current) == 5922 and
            set(old) == set(current), 'unit reuse source path set differs')
    changed = {name: dict(prior=before, current=current[name])
               for name, before in old.items() if before != current[name]}
    require(set(changed) == {
        'tests/unit/spin/spin_batch_context_fixture.c',
        'bench/results/10.176.26.71/bench/continuation-nano-20261030/README.md',
    } and reuse.get('changed_inputs') == changed,
            'unit reuse permits only the reviewed fixture and failure-record changes')


def verify(directory, run, sync):
    unit = a.local_json(directory/'unit.json')
    require(run['inputs']['unit.json'] == UNIT_OWNER and
            a.file_sha(directory/'unit.json') == UNIT_OWNER,
            'exact reviewed completed f7 unit owner required')
    require(unit['input_sha256']['controller.py'] == UNIT_CONTROLLER and
            unit['input_sha256']['sync.json'] == run['inputs']['sync.json'] and
            unit['source_commit'] == CURRENT and unit['boot_id'] == run['boot_id'] and
            unit['completed'] is True and unit['final_idle'] is True and
            [block['name'] for block in unit['blocks']] == ['kernel-identity','unit','build-provider'] and
            all(block['state'] == 'EXITED' and block['returncode'] == 0 for block in unit['blocks']),
            'current unit/build linkage or completion differs')
    evidence = {name:(directory/('unit-reuse-'+name)).read_bytes() for name in REUSE_HASHES}
    require(all(run['inputs']['unit-reuse-'+name] == expected for name,expected in REUSE_HASHES.items()),
            'run must bind every original failed-unit input')
    verify_unit_reuse(unit, sync, CURRENT, evidence)
    basic_dependency, phases = None, {}
    for phase in ('basic','origin','rwsem','mixed'):
        owner_file, result_file = phase+'-owner.json', phase+'-result.json'
        owner, result = a.local_json(directory/owner_file), a.local_json(directory/result_file)
        campaign = run['basic_campaign'] if phase == 'basic' else run['functional_campaign']
        require(owner.get('completed') is True and owner.get('final_idle') is True and
                owner.get('source_commit') == CURRENT and owner.get('boot_id') == run['boot_id'] and
                owner.get('phase') == phase and owner.get('returncode') == 0 and
                owner.get('timing_started') is False and
                owner['inputs']['sync.json'] == run['inputs']['sync.json'] and
                owner['inputs']['unit.json'] == UNIT_OWNER and
                owner['inputs']['controller.py'] == LIVE_CONTROLLER and
                all(owner['inputs'].get('unit-reuse-'+name) == expected for name,expected in REUSE_HASHES.items()),
                'functional prerequisite linkage differs: '+phase)
        require(owner['result_sha256'] == run['inputs'][result_file] == a.file_sha(directory/result_file) and
                result.get('passed') is True and result.get('drained',result.get('final_idle')) is True,
                'functional result incomplete: '+phase)
        if phase == 'basic':
            basic_dependency = dict(campaign=campaign,
                owner_path=campaign+'/basic-control/owner.json', owner_sha256=run['inputs'][owner_file],
                result_path=campaign+'/basic/result.json', result_sha256=run['inputs'][result_file])
            require(result.get('boot_id') == run['boot_id'] and result.get('timing_started') is False and
                    [row['family'] for row in result['results']] == ['spin','mutex','rwlock','rwsem'] and
                    all(row['passed'] and row['drained'] and row['jit_completions'] > 0 for row in result['results']),
                    'four-family basic evidence incomplete')
        else:
            require(owner.get('basic_campaign') == run['basic_campaign'] and
                    owner.get('basic_dependency') == basic_dependency,
                    'later live phase basic dependency differs: '+phase)
            require(result.get('origin_service') == (phase != 'mixed') and
                    result.get('origin_instructions') == (phase == 'origin') and
                    result.get('mixed_spin') == (phase == 'mixed') and
                    result.get('family') == ('rwsem' if phase == 'rwsem' else 'mutex') and
                    result.get('entry_abi') == 2 and result.get('image_requirements') == 65 and
                    result.get('capabilities',{}).get('version') == 13 and
                    result['capabilities']['features'] & (1 << 13),
                    'functional service scope differs: '+phase)
            require(len(result['phases']) == (7 if phase == 'origin' else 5) and
                    all(row['complete'] for row in result['phases']) and
                    all(row['execution_validated'] for row in result['phases'][1:]),
                    'functional phase validation incomplete: '+phase)
            session = a.local_json(directory/(phase+'-session.json'))
            require(session.get('drained') is True and session.get('retired') == a.RETIRED,
                    'functional frame/source retirement incomplete: '+phase)
        phases[phase] = dict(owner_sha256=run['inputs'][owner_file], result_sha256=run['inputs'][result_file],
                             passed=True, source_commit=CURRENT, original_campaign=campaign)
    return dict(unit_owner_sha256=UNIT_OWNER, unit_reuse=unit['unit_reuse'],
                retained_failed_inputs=REUSE_HASHES, functional_phases=phases,
                basic_dependency=basic_dependency, performance_accepted=False)
