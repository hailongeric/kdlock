"""Read only retained JSON, bytes and tar members using the standard library.

This is an offline receipt audit. It executes no project, controller, kernel or
workload code and makes no VM connection.
"""
from pathlib import Path, PurePosixPath
import base64
import hashlib
import json
import stat
import sys
import tarfile


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def audit(root):
    root = Path(root)
    load = lambda path: json.loads((root / path).read_bytes())
    hashes = {}
    origins = load('origin-index.json')
    require(len(origins['copies']) == origins['files'] == 99, 'source-host copy count differs')
    require(sum(row['bytes'] for row in origins['copies']) == origins['bytes'] == 1116708,
            'source-host copy bytes differ')
    seen = set()
    for row in origins['copies']:
        name = PurePosixPath(row['path'])
        require(not name.is_absolute() and '..' not in name.parts and str(name) == row['path'] and
                row['path'] not in seen, 'unsafe or duplicate retained copy path')
        seen.add(row['path'])
        path = root / row['path']
        require(stat.S_ISREG(path.lstat().st_mode), 'retained copy is not a regular file')
        data = path.read_bytes()
        require(len(data) == row['bytes'] and digest(data) == row['sha256'], 'retained source-host bytes differ')
        hashes[row['path']] = row['sha256']
    index = load('collection/copy-index.json')
    require(digest((root/'collection/copy-index.json').read_bytes()) ==
            '6a5de2ae15580bd9a95d98507dd15b10d224ef97afda9c52b42b5ca4a60cb511', 'guest index differs')
    before = load('collection/.collection/inventory-before.json')
    after = load('collection/.collection/inventory-after.json')
    require(before['files'] == after['files'] and before['directories'] == after['directories'],
            'guest before/after identities differ')
    require(before['count'] == after['count'] == index['count'] == len(index['files']) == 42 and
            before['bytes'] == after['bytes'] == index['bytes'] == 214841, 'guest extent differs')
    members = {}
    for row in index['files']:
        name = PurePosixPath(row['name'])
        require(not name.is_absolute() and '..' not in name.parts and str(name) == row['name'] and
                row['name'] not in members and row['path'] == 'payload/' + row['name'], 'guest member path differs')
        require(before['files'][row['name']] == {
            'bytes':row['bytes'], 'sha256':row['sha256'], 'identity':row['identity'], 'path':row['guest_path']},
            'guest member identity differs from inventory')
        data = (root/'collection'/row['path']).read_bytes()
        require(len(data) == row['bytes'] and digest(data) == row['sha256'], 'guest member bytes differ')
        members[row['name']] = data
    collection = load('collection/collection.json')
    require(collection['status'] == 'COMPLETE' and collection['files'] == 42 and collection['bytes'] == 214841,
            'collection was not complete')
    archive = root/'collection/.collection/copy.tar'
    require(digest(archive.read_bytes()) == collection['archive_sha256'], 'raw tar hash differs')
    with tarfile.open(archive, 'r:') as source:
        entries = source.getmembers()
        require(len(entries) == 42 and len({row.name for row in entries}) == 42, 'raw tar member extent differs')
        for row in entries:
            require(row.isfile() and row.name in members and row.size == len(members[row.name]),
                    'raw tar member is not an exact selected regular file')
            require(source.extractfile(row).read() == members[row.name], 'raw tar member differs')
    runtime = load('collection/payload/runtime/result.json')
    require(hashes['collection/payload/runtime/result.json'] ==
            '5b1397d4b8832228ae3d95d3d0105884a98a084260fe1d5a5e464ce1fcece89e' and
            runtime['status'] == 'NATIVE_API_AND_MM_COMPLETE', 'runtime completion differs')
    config = load('collection/payload/input/config.json')
    require(config == runtime['configuration'] == load('controller/config.json') and
            digest((root/'controller/config.json').read_bytes()) == runtime['config_sha256'], 'live config binding differs')
    require(config['core_git_head'] == '0d42063ead37dc8fc1631fa56c8348890ede9c5f' and
            config['fixture_git_head'] == '140aecc4f83a6b6ae6f20245234e8a63504f9210', 'source epochs differ')
    linked_binaries = {}
    for key, filename in (('client','client'),('compatibility','native-api-signed.ko'),('provider','mmap-signed.ko')):
        saved = root.parent/'kernel8-affected-build-20261111/collection/payload/binaries'/filename
        require(digest(saved.read_bytes()) == config['binaries'][key]['sha256'], 'linked affected-build binary differs')
        linked_binaries[key] = {'evidence_path':str(saved.relative_to(root.parent)),
                                'sha256':config['binaries'][key]['sha256']}
    require(runtime == load('controller/completed-result.json') and
            load('controller/launch-result.json')['returncode'] == 0 and
            load('collection/payload/driver/result.json')['returncode'] == 0, 'driver completion differs')
    require(load('controller/actual-argv.json')[-2:] == ['--seconds', '300'], 'live deadline differs')
    require(hashes['collection/payload/input/controller.py'] ==
            '2c2082e0bf7c807819ec7e28f744c34aaa94f38aa07faf5be1a197b1baced074', 'controller source differs')
    for command in runtime['commands']:
        require(command['returncode'] == 0, 'runtime command failed')
        for suffix in ('stdout', 'stderr'):
            require(digest((root/('collection/payload/runtime/' + command['label'] + '.' + suffix)).read_bytes()) ==
                    command[suffix + '_sha256'], 'command output hash differs')
    require(len(runtime['commands']) == 12 and runtime['client_returncode'] == 0 and
            runtime['compat_driver_returncode'] == 0 and runtime['compatibility_pass'] is True,
            'command/child success extent differs')
    compat = load('collection/payload/runtime/compat-result.json')
    checks = compat['after']
    require(checks == load('collection/payload/runtime/compat-after-run.json') and
            compat['phase'] == 'COMPAT_PASS' and compat['run_errno'] == 0 and
            compat['drained'] is True and compat['fd_closed'] is True, 'compatibility disposition differs')
    require(len(checks['cases']) == 12 and all(row['ran'] == 1 and row['result'] == 0 for row in checks['cases']) and
            checks['created'] == checks['joined'] == 19 and checks['state'] == 2 and checks['error'] == 0 and
            checks['module_hold'] == checks['count_overflow'] == 0 and checks['pool_idle'] == 1,
            'compatibility cases/users differ')
    require(checks['try_returns'] == [1,1,0,0] and checks['turn_wait_proved'] == checks['turn_cleanup_proved'] == 1,
            'compatibility try/turn evidence differs')
    require(checks['native_counts'] == [10,11,10,9,1,4,2,12], 'compatibility native counts differ')
    for case in (4,5,6,10):
        require(checks['cases'][case]['returns'][1] == -4 and checks['cases'][case]['granted'][1] == 0,
                'blocked cancellation result/grant differs')
    for case in (7,8,9):
        require(checks['cases'][case]['returns'][0] == 0 and checks['cases'][case]['granted'][0] == 1 and
                checks['cases'][case]['pending'][0] == 1, 'readiness-before-signal evidence differs')
    mm = load('collection/payload/runtime/mmap-result.json')
    require(mm == load('collection/payload/runtime/mmap-client.stdout'), 'actual client stdout/result differs')
    require(mm['overall_pass'] is True and mm['status'] == 'syscall_completion_pass' and
            mm['threads'] == mm['created_threads'] == len(mm['workers']) == 4 and
            mm['iterations_per_thread'] == 64 and mm['completed_iterations'] == 256 and
            mm['worker_errors'] == mm['setup_errno'] == mm['arena_cleanup_errno'] == 0 and
            mm['deadline_exceeded'] is False and mm['deadline_ms'] == 60000 and
            mm['page_bytes'] == 4096 and mm['mapping_pages'] == 2 and mm['arena_reservations'] == 1,
            'real syscall completion/effects differ')
    for number, worker in enumerate(mm['workers']):
        require(worker['id'] == number and worker['completed'] == 64 and not worker['deadline_reached'] and
                worker['errno'] == 0 and worker['error'] == 'none' and
                worker['mmap_attempts'] == worker['mmap_successes'] == 192 and
                worker['munmap_attempts'] == worker['munmap_successes'] == 128 and
                worker['mincore_attempts'] == worker['unmapped_page_checks'] == 256 and
                worker['reuse_successes'] == 64 and
                worker['fresh_zero_bytes'] == worker['written_bytes'] == worker['readback_bytes'] == 1048576,
                'worker real effects/counters differ')
    gate = mm['selected_gate']; initial = gate['start']; final = gate['final']
    require(gate['requested'] is True and gate['end_attempts'] == 1 and gate['native_counts_balanced'] is True and
            not gate['cleanup_required'] and not gate['cleanup_failed'] and
            all(gate[name] == 0 for name in ('start_errno','open_errno','query_errno','wait_errno','end_errno','close_errno')),
            'ordinary selected-gate END/close differs')
    require(all(initial[key] == final[key] for key in ('gate_identity','object_identity','mm_identity','owner_pid','owner_tgid')) and
            final['owner_pid'] == final['owner_tgid'] == mm['pid'] and final['owner_is_current'] == final['owner_threads'] == 1 and
            final['state'] == 2 and final['pool_idle'] == 1 and final['native_capacity'] == 64 and
            all(final[key] == 0 for key in ('gate_locked','gate_write_locked','gate_contended','cleanup_required','count_overflow','source_calls','jit_observation_available')),
            'retired selected gate/identity differs')
    require(final['native_write_acquires'] == 1285 == final['native_write_releases'] + final['native_downgrades'] and
            final['native_read_releases'] == 2057 == final['native_read_acquires'] + final['native_downgrades'] and
            final['native_downgrades'] == 513 and final['native_write_releases'] == 772 and
            final['native_read_acquires'] == 1544 and final['native_try_misses'] == 393,
            'actual native grant/release balances differ')
    boot = config['boot_id']; release = '7.0.0-38-kdrebuild8'; build_id = config['build_id']
    require(boot == 'e001a3d2-3fcc-4e89-80ec-9187eb8ddfa0' and
            build_id == 'a33dd4d11d0f0c6649107507e685b6e86e716c1a' and runtime['running_build_id_after'] == build_id,
            'actual runtime identity differs')
    for name, taint in (('identity_before',0),('between_fixtures',4096),('identity_after',4096)):
        state = runtime[name]
        require(state['identity'] == {'boot':boot,'release':release,'taint':taint} and not state['activity'] and
                [line.split()[0] for line in state['modules'].splitlines()] == ['nls_iso8859_1'], 'idle/module/taint identity differs')
    post = load('postboot/guest-result.json'); gs = load('postboot/guest-gs-proof.json'); outer = load('postboot/result.json')
    require(hashes['postboot/guest-result.json'] == config['postboot_result']['sha256'] and
            hashes['postboot/guest-gs-proof.json'] == config['gs_proof']['sha256'] and
            hashes['postboot/result.json'] == config['postboot_return']['sha256'] and outer['returncode'] == 0 and
            post['phase'] == 'POSTBOOT_IDENTITY_VERIFIED' and post['boot_id'] == gs['boot_id'] == boot and
            post['running_build_id'] == gs['build_id'] == build_id and post['tainted'] == '0' and
            gs['verified_for_running_kernel'] is True and gs['current_task_gs_offset'] == '0xffffffff84425018' and
            gs['kernel_elf_sha256'] == config['kernel_files']['vmlinux']['sha256'], 'postboot/GS binding differs')
    pulled = load('postboot/actual-proof.json')
    for name, copy in (('result.json','postboot/guest-result.json'),('gs-proof.json','postboot/guest-gs-proof.json')):
        data = base64.b64decode(pulled['files'][name]['data'],validate=True)
        require(data == (root/copy).read_bytes() and digest(data) == pulled['files'][name]['sha256'], 'proof pull envelope differs')
    require(digest((root/'collection/payload/input/recovery.json').read_bytes()) == config['recovery']['sha256'] == runtime['recovery']['sha256'],
            'fresh recovery receipt binding differs')
    old = (root/'collection/payload/runtime/dmesg-before.stdout').read_bytes()
    new = (root/'collection/payload/runtime/dmesg-after.stdout').read_bytes()
    require(new.startswith(old) and len(new)-len(old) == 79, 'dmesg delta differs')
    require((root/'collection/payload/runtime/running-notes.bin').read_bytes() ==
            (root/'collection/payload/runtime/running-notes-after.bin').read_bytes(), 'running binary notes changed')
    return {'status':'SAVED_RECEIPTS_VERIFIED', 'scope':'Offline byte/receipt audit only. Native-local API and actual syscall outcomes; JIT observation is unavailable.',
            'copied_files':origins['files'], 'copied_bytes':origins['bytes'], 'guest_payload_files':42, 'guest_payload_bytes':214841,
            'raw_archive_members':42, 'runtime_result_sha256':hashes['collection/payload/runtime/result.json'],
            'identity':{'boot_id':boot,'release':release,'build_id':build_id,'core_git_head':config['core_git_head'],
                        'fixture_git_head':config['fixture_git_head'],'taint_before':0,'taint_after':4096},
            'linked_build_binaries':linked_binaries,
            'compatibility':{'cases_passed':12,'created':19,'joined':19,'try_returns':checks['try_returns'],
                             'turn_wait_proved':1,'turn_cleanup_proved':1,'native_counts':checks['native_counts']},
            'real_syscalls':{'threads':4,'iterations_each':64,'completed':256,'worker_mmap':768,'worker_munmap':512,
                             'worker_mincore_hole_checks':1024,'reuse_successes':256,'fresh_zero_bytes':4194304,
                             'written_bytes':4194304,'readback_bytes':4194304,'separate_parent_arena_mmap':1,'separate_parent_arena_munmap':1},
            'selected_native_gate':final, 'ordinary_cleanup':{'end_attempts':1,'retired':True,'pool_idle':True,'gate_clear':True,
                                                            'compat_fd_closed':True,'rmmod_returncodes':[0,0],'final_modules':['nls_iso8859_1'],'activity':[]},
            'commands':[(row['label'],row['returncode']) for row in runtime['commands']],
            'dmesg_append':new[len(old):].decode('utf-8'),
            'observational_limits':['source_calls=false; native-local route','jit_observation_available=0 is unavailable, not measured zero JIT',
                                    'native counters do not attribute individual syscall addresses','no MM JIT, auxiliary-context equivalence, performance or general support claim']}


if __name__ == '__main__':
    print(json.dumps(audit(Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent),indent=2,sort_keys=True))
