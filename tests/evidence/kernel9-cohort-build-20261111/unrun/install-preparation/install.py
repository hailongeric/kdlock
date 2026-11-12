#!/usr/bin/env python3
"""NOT DISPATCHABLE: source-only kernel9 stage/verify/install/arm preparation.

No reboot, module load, global GRUB regeneration or cleanup operation exists.
The main guard deliberately refuses execution while runtime validation is blocked.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import stat
from types import SimpleNamespace

BASE = Path('/mnt/kdlock-builds2/kdlock-main-kernel9-6e486ece-01')
SOURCE, BUILD = BASE/'source', BASE/'build'
STAGE = BASE/'install-stage-kdrebuild9-cohort-01'
RECEIPTS = BASE/'receipts/install-kdrebuild9-cohort-01'
RELEASE = '7.0.0-38-kdrebuild9'
CORE = '6e486ecec398111fb5d5e30ffc76495f32f557b7'
ENTRY = 'kdlock-kdrebuild9-cohort-01'
EXPECTED_NORMAL = {'boot': 'f1442f01-e060-46fa-a480-da508d7ce8a9',
                   'release': '7.0.0-38-kdlock1', 'taint': '0'}
REFERENCES = {'reference-install8.py': '409f640efa69425ee8b8849c4f1897b9df83e4c1a7eccbea2b596ab7bb99a99b',
              'reference-checks8.py': '1726d01a4794f82ca8cb1a92218a70dd59272fa2e5e8bdd27a266bd31d92a472'}
TOOLS = ('make', 'modinfo', 'readelf', 'modprobe', 'depmod', 'unshare', 'sh', 'env',
         'mkinitramfs', 'lsinitramfs', 'grub-script-check', 'grub-editenv', 'grub-reboot', 'sync')


def need(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for b in iter(lambda: stream.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def checked(path, expected):
    path = Path(path)
    need(path.is_absolute() and path.resolve(strict=True) == path and path.is_file() and
         len(expected) == 64 and sha(path) == expected, 'exact canonical input differs: '+str(path))
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('stage', 'verify', 'install', 'arm'))
    for n in ('config-json', 'config-sha256', 'recovery-json', 'recovery-sha256'):
        parser.add_argument('--'+n, required=True)
    parser.add_argument('--prior-sha256')
    args = parser.parse_args()
    need(os.geteuid() == 0, 'designated guest root required')
    config = checked(args.config_json, args.config_sha256)
    need(config['status'] == 'REVIEWED_ACTUAL_KERNEL9_INPUTS' and config['dispatch_authorized'] is True,
         'source preparation is not dispatchable')
    need(type(config['root_working_bytes']) is int and config['root_working_bytes'] > 0,
         'explicit measured-install metadata/GRUB working allowance required')
    here = Path(__file__).resolve().parent
    for name, expected in REFERENCES.items():
        need(sha(here/name) == expected, 'prior reusable recipe differs: '+name)
    lib = runpy.run_path(str(here/'reference-install8.py'))
    checks = runpy.run_path(str(here/'reference-checks8.py'))
    checked(config['build_driver'], config['build_driver_sha256']) if False else None
    need(sha(config['build_driver']) == config['build_driver_sha256'], 'exact build driver differs')
    native = runpy.run_path(config['build_driver'])
    plan = checked(config['plan_json'], config['plan_sha256'])
    built = checked(config['build_receipt'], config['build_receipt_sha256'])
    final = checked(config['final_identity'], config['final_identity_sha256'])
    need(plan['selected_commit'] == CORE and plan['release'] == RELEASE and
         plan['target'] == str(BASE) and plan['normal_identity'] == EXPECTED_NORMAL and
         plan['driver_sha256'] == config['build_driver_sha256'], 'fresh build plan identity differs')
    need(built['status'] == 'KERNEL9_BUILD_AND_LINKED_IDENTITY_COMPLETE' and
         built['selected_commit'] == CORE and built['kernelrelease'] == RELEASE and
         built['source'] == str(SOURCE) and built['build'] == str(BUILD) and
         built['plan_sha256'] == config['plan_sha256'] and
         built['driver_sha256'] == config['build_driver_sha256'] and
         built['final_identity_sha256'] == config['final_identity_sha256'] and
         all(row.get('returncode') == 0 for row in built['commands']), 'actual kernel9 build incomplete/different')
    need(final['source'] == str(SOURCE) and final['build'] == str(BUILD) and
         final['kernelrelease'] == RELEASE and final['module_count'] == 1 and
         final['module_vermagic'].split()[0] == RELEASE and len(final['files']) == 16 and
         final['gs_witness'] and set(final['return_symbols']) == {'its_return_thunk', '__x86_return_thunk'},
         'fresh linked16/GS/thunk/single-NLS identity incomplete')
    native['environment']()
    os.environ.update(PATH='/usr/sbin:/usr/bin:/sbin:/bin', LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')
    native['idle'](EXPECTED_NORMAL)
    recovery = native['recovery_check'](SimpleNamespace(recovery_json=args.recovery_json,
        recovery_sha256=args.recovery_sha256), plan)
    need(native['candidate_pins'](plan, SOURCE) == built['source_after'] and
         native['protected'](plan) == built['protected_after'], 'existing/full source/protected pins differ')
    native['pins'](BUILD, {n: r['sha256'] for n, r in final['files'].items()})
    for n, r in final['files'].items():
        need((BUILD/n).stat().st_size == r['bytes'], 'linked file size differs: '+n)
    need(Path('/lib/modules').resolve().is_dir() and BASE.stat().st_dev != Path('/').stat().st_dev,
         'actual off-root staging required')
    need(native['available'](BASE) >= 4*1024**3 and native['available']('/') >= 1024**3,
         'off-root/root headroom refused')
    need(set(config['tool_sha256']) == set(TOOLS), 'complete explicit install-tool pins required')
    tools = {}
    for name in TOOLS:
        value = Path(shutil.which(name)).resolve(strict=True)
        need(sha(value) == config['tool_sha256'][name], 'install tool differs: '+name)
        tools[name] = value
    phase = args.phase
    if phase == 'stage':
        need(not os.path.lexists(STAGE) and not os.path.lexists(RECEIPTS), 'fresh stage/receipts required')
        STAGE.mkdir(mode=0o700)
        RECEIPTS.mkdir(mode=0o700)
        prior = None
    else:
        before = {'verify': 'stage', 'install': 'verify', 'arm': 'install'}[phase]
        prior = checked(RECEIPTS/before/(before+'-complete.json'), args.prior_sha256 or '')
        need(prior['status'] == 'COMPLETE' and prior['phase'] == before and
             prior['config_sha256'] == args.config_sha256 and prior['helper_sha256'] == sha(__file__),
             'exact prior phase/helper/config differs')
    output = RECEIPTS/phase
    output.mkdir(mode=0o700)
    g = lib['stage_limited'].__globals__
    cg = checks['protected'].__globals__
    menu = (here/'candidate-entry.cfg').read_bytes()
    need(sha(here/'candidate-entry.cfg') == config['menu_sha256'], 'reviewed candidate menu differs')
    g.update(BASE=BASE, SOURCE=SOURCE, BUILD=BUILD, STAGE=STAGE, RECEIPTS=output,
        RELEASE=RELEASE, EXPECTED_CORE=CORE, ENTRY=ENTRY, FULL=STAGE/'full', LIMITED=STAGE/'limited',
        INITRD=STAGE/('initrd.img-'+RELEASE), PHASE=phase, MENU_APPEND=menu)
    cg.update(RELEASE=RELEASE, PREVIOUS=(), RECEIPTS=output, CANDIDATE=ENTRY)
    g['EVENTS'] = (output/'journal.jsonl').open('x')
    original_command = lib['command']
    sequence = [0]

    def command(label, argv, seconds):
        words = list(map(str, argv))
        name = Path(words[0]).name
        need(name in tools, 'undeclared install command: '+name)
        words[0] = str(tools[name])
        return original_command(label, words, seconds)

    def query(argv, seconds=30):
        sequence[0] += 1
        return command('query-%03d' % sequence[0], argv, seconds)

    g['command'] = command
    cg['run'] = query
    save = lib['save']
    stage_output = RECEIPTS/'stage'

    def preserved():
        actual = checks['protected']()
        if phase != 'stage':
            expected = json.loads((stage_output/'protected-before.json').read_text())
            need(actual == expected, 'old kernels/modules/default/GRUB inputs changed')
        return actual

    def grub(armed, appended):
        need(sha('/boot/grub/grub.cfg') == config['grub_cfg_sha256'], 'main GRUB file changed')
        prefix = (stage_output/'custom.cfg-before').read_bytes()
        custom = Path('/boot/grub/custom.cfg').read_bytes()
        need(custom == prefix+(menu if appended else b''), 'old custom prefix/candidate suffix differs')
        text = Path('/boot/grub/grub.cfg').read_text()
        need('set default="'+cg['DEFAULT']+'"' in text and
             'source ${config_directory}/custom.cfg' in text, 'normal default/custom loader differs')
        values = dict(line.split('=', 1) for line in query(['grub-editenv', '/boot/grub/grubenv', 'list']).splitlines() if '=' in line)
        need(not values.get('prev_saved_entry') and values.get('next_entry', '') == (ENTRY if armed else ''),
             'unexpected prior/one-shot boot selection')
        return values

    try:
        save('phase-inputs.json', dict(config_sha256=args.config_sha256, helper_sha256=sha(__file__),
            build_receipt_sha256=config['build_receipt_sha256'], final_identity_sha256=config['final_identity_sha256'],
            recovery=recovery, normal_identity=EXPECTED_NORMAL))
        if phase == 'stage':
            lib['require_fresh_targets']()
            need(native['boot_files']() == built['boot_after'], 'old boot files differ from completed build')
            save('protected-before.json', preserved())
            custom = Path('/boot/grub/custom.cfg')
            need(custom.is_file() and not custom.is_symlink() and custom.stat().st_nlink == 1 and
                 custom.stat().st_size == config['custom_cfg_bytes'] and
                 sha(custom) == config['custom_cfg_sha256'] and sha('/boot/grub/grub.cfg') == config['grub_cfg_sha256'],
                 'fresh actual old menu prefix differs')
            prefix = custom.read_bytes()
            need(ENTRY.encode() not in prefix+Path('/boot/grub/grub.cfg').read_bytes(), 'candidate menu already exists')
            (output/'custom.cfg-before').write_bytes(prefix)
            (STAGE/'custom.cfg-expected').write_bytes(prefix+menu)
            save('stage-grub-sources.json', dict(grub_cfg_sha256=config['grub_cfg_sha256'],
                custom_cfg_before_sha256=config['custom_cfg_sha256'], custom_cfg_before_size=len(prefix),
                custom_cfg_metadata=lib['menu_metadata'](custom.stat()), append_bytes=len(menu),
                append_sha256=sha(here/'candidate-entry.cfg'), custom_cfg_after_sha256=hashlib.sha256(prefix+menu).hexdigest(),
                custom_cfg_after_size=len(prefix+menu), candidate_entry=ENTRY))
            grub(False, False)
            command('main-menu-syntax', ['grub-script-check', '/boot/grub/grub.cfg'], 30)
            command('candidate-menu-syntax', ['grub-script-check', STAGE/'custom.cfg-expected'], 30)
            (STAGE/'full').mkdir(mode=0o700)
            command('native-modules-install', ['make', '-C', SOURCE, 'O='+str(BUILD),
                'INSTALL_MOD_PATH='+str(STAGE/'full'), 'INSTALL_MOD_STRIP=1',
                'KERNELRELEASE='+RELEASE, 'modules_install'], 300)
            full_modules = checks['modules'](STAGE/'full')
            need(full_modules['count'] == full_modules['signed'] == 1 and full_modules['unsigned'] == 0 and
                 all(r['sig_key'] and r['sig_hashalgo'] for r in full_modules['modules']), 'actual signed single-NLS stage required')
            need((STAGE/'full/lib/modules'/RELEASE/'modules.order').read_text().splitlines() ==
                 ['kernel/fs/nls/nls_iso8859-1.ko'], 'native module order differs from single NLS')
            save('native-modules.json', full_modules)
            lib['stage_limited']()
            need(native['boot_files']() == built['boot_after'], 'stage changed installed boot namespaces')
        elif phase == 'verify':
            preserved()
            modules = checks['modules'](STAGE/'limited')
            need(modules['count'] == modules['signed'] == 1, 'limited signed-NLS inventory differs')
            closure = lib['required_closure'](STAGE/'limited')
            need(sorted({p for v in closure.values() for p in v['modules']}) ==
                 ['kernel/fs/nls/nls_iso8859-1.ko'], 'eight-name dependency closure changed')
            lib['verify_initrd'](g['INITRD'], closure)
            save('verified-stage.json', dict(closure=closure, namespace=lib['tree_table'](STAGE/'limited/lib/modules'/RELEASE),
                initrd={'bytes': g['INITRD'].stat().st_size, 'sha256': sha(g['INITRD'])},
                budget=lib['budget'](config)))
            grub(False, False)
        elif phase == 'install':
            preserved()
            lib['require_fresh_targets']()
            verified = json.loads((RECEIPTS/'verify/verified-stage.json').read_text())
            limited = STAGE/'limited/lib/modules'/RELEASE
            need(lib['tree_table'](limited) == verified['namespace'] and sha(g['INITRD']) == verified['initrd']['sha256'],
                 'verified module/initrd bytes changed')
            save('root-budget-before-install.json', lib['budget'](config))
            grub(False, False)
            installed = g['MODULE_ROOT']/RELEASE
            shutil.copytree(limited, installed, copy_function=shutil.copy2)
            lib['syncdir'](g['MODULE_ROOT'])
            boot = []
            for source, prefix in ((BUILD/'arch/x86/boot/bzImage', 'vmlinuz'), (BUILD/'System.map', 'System.map'),
                                   (BUILD/'.config', 'config'), (g['INITRD'], 'initrd.img')):
                target = Path('/boot')/(prefix+'-'+RELEASE)
                with source.open('rb') as src, target.open('xb') as dst:
                    shutil.copyfileobj(src, dst); dst.flush(); os.fsync(dst.fileno())
                target.chmod(0o600)
                need(sha(source) == sha(target), 'exclusive boot copy differs')
                boot.append({'path': str(target), 'size': target.stat().st_size, 'sha256': sha(target)})
            lib['syncdir']('/boot')
            for name in ('stage-grub-sources.json', 'custom.cfg-before'):
                shutil.copyfile(stage_output/name, output/name)
            lib['append_candidate_menu']()
            need(lib['tree_table'](installed) == verified['namespace'], 'installed module namespace differs')
            need(lib['required_closure'](Path('/')) == verified['closure'], 'installed dependency closure differs')
            lib['verify_initrd'](Path('/boot')/('initrd.img-'+RELEASE), verified['closure'])
            preserved()
            environment = grub(False, True)
            save('installed.json', dict(files=boot, namespace=verified['namespace'], environment=environment))
        else:
            preserved()
            installed = json.loads((RECEIPTS/'install/installed.json').read_text())
            lib['verify_records'](installed['files'])
            need(lib['tree_table'](g['MODULE_ROOT']/RELEASE) == installed['namespace'], 'installed modules changed')
            before = grub(False, True)
            need(before == installed['environment'], 'GRUB environment changed since install')
            command('one-shot', ['grub-reboot', ENTRY], 30)
            after = grub(True, True)
            need({k:v for k,v in before.items() if k != 'next_entry'} ==
                 {k:v for k,v in after.items() if k != 'next_entry'}, 'one-shot changed other GRUB state')
            command('sync', ['sync'], 30)
        native['idle'](EXPECTED_NORMAL)
        need(native['candidate_pins'](plan, SOURCE) == built['source_after'] and
             native['protected'](plan) == built['protected_after'], 'source/protected drift')
        need(native['available']('/') >= 1024**3, 'root reserve consumed')
        save(phase+'-complete.json', dict(status='COMPLETE', phase=phase, config_sha256=args.config_sha256,
            helper_sha256=sha(__file__), reboot_performed=False, module_load_performed=False,
            prior_sha256=args.prior_sha256, entry=ENTRY))
    except BaseException as error:
        save('failure.json', dict(status='FAILED_OR_INCOMPLETE_RETAINED', phase=phase, error=repr(error),
             preserve_partial_state=True, one_shot_may_be_set=(phase == 'arm'), reboot_performed=False))
        raise
    finally:
        g['EVENTS'].close()


if __name__ == '__main__':
    raise SystemExit('NOT_DISPATCHABLE_SOURCE_PREPARATION: runtime validation is blocked; no phase executed.')
