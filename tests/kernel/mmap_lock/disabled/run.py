#!/usr/bin/env python3
"""Guest-only disabled-config object/link check; no kernel build, install or boot."""
import argparse
import json
import os
from pathlib import Path
import re
import runpy
import shlex
import shutil
import subprocess
import sys
from elftools.elf.elffile import ELFFile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt
import kernel_identity

TARGETS = ('mm/mmap_lock', 'kernel/fork', 'kernel/bpf/task_iter', 'kernel/bpf/stackmap')
NATIVE = ('mm/mmap.c', 'mm/memory.c', 'mm/madvise.c', 'mm/rmap.c',
          'lib/maple_tree.c', 'arch/x86/mm/fault.c')
COMMON = ('init', 'read', 'read_killable', 'read_try', 'read_release',
          'read_non_owner', 'write', 'write_nested', 'write_killable',
          'write_try', 'write_release', 'downgrade', 'assert_read',
          'assert_write', 'contended')
ALIASES = {
    'init_rwsem': 'init_rwsem', 'down_write': 'down_write',
    'down_write_nested': 'down_write_nested',
    'down_write_killable': 'down_write_killable',
    'down_write_trylock': 'down_write_trylock', 'up_write': 'up_write',
    'downgrade_write': 'downgrade_write', 'down_read': 'down_read',
    'down_read_killable': 'down_read_killable',
    'down_read_trylock': 'down_read_trylock', 'up_read': 'up_read',
    'up_read_non_owner': 'up_read_non_owner', 'rwsem_is_locked': 'rwsem_is_locked',
    'rwsem_is_contended': 'rwsem_is_contended', 'write_owned': 'rwsem_is_locked',
}


def output(argv, cwd=None):
    return subprocess.check_output([str(x) for x in argv], cwd=cwd,
                                   text=True, timeout=30)


def undefined(path):
    return sorted(line.split()[-1] for line in output(['nm', '-u', path]).splitlines()
                  if line.strip())


def recipe(tree, target):
    p = Path(target)
    command = tree / p.parent / ('.' + p.name + '.o.cmd')
    line = command.read_text().splitlines()[0]
    prefix = 'cmd_' + target + '.o := '
    assert line.startswith(prefix), command
    args = shlex.split(line[len(prefix):])
    # Never evaluate a captured shell recipe. Accept the exact compiler-only
    # form from this recovery tree and retarget all outputs into private scratch.
    assert args[0] == 'gcc' and args.count('-o') == 1 and args[-1] == target + '.c'
    assert not any(x in args for x in (';', '&&', '|'))
    assert '-D__KERNEL__' in args and '-DMODULE' not in args
    return command, args


def compile_args(tree, target, source, dest, headers=None, integrated=False):
    _, original = recipe(tree, target)
    args = original.copy()
    dependency = [i for i, x in enumerate(args) if x.startswith('-Wp,-MMD,')]
    assert len(dependency) == 1
    args[dependency[0]] = '-Wp,-MMD,' + str(dest.with_suffix('.d'))
    args[args.index('-o') + 1] = str(dest)
    args[-1] = str(source)
    if headers:
        # Put patched headers BEFORE the captured native include search. A late
        # KCFLAGS include would silently compile the unmodified native headers.
        args[1:1] = ['-I' + str(headers),
                     '-fmacro-prefix-map=' + str(headers.parent) + '/=']
    if integrated:
        args.insert(1, '-DCHECK_INTEGRATED=1')
    if target == 'kernel/bpf/stackmap':
        # Its unchanged private freelist header is normally found beside the
        # native source. The copied source still finds the patched lifetime
        # header in its own directory first; other quoted headers stay native.
        args[1:1] = ['-iquote', str(tree/'kernel/bpf')]
    return args


def symbol_image(path, name):
    """Compare exact symbol bytes and relocations, independent of debug paths."""
    with path.open('rb') as stream:
        elf = ELFFile(stream)
        found = elf.get_section_by_name('.symtab').get_symbol_by_name(name)
        assert found and len(found) == 1, name
        symbol = found[0]
        section = elf.get_section(symbol['st_shndx'])
        start, size = symbol['st_value'], symbol['st_size']
        assert size
        relocations = []
        for reloc in elf.iter_sections():
            if reloc['sh_type'] not in ('SHT_RELA','SHT_REL') or reloc['sh_info'] != symbol['st_shndx']:
                continue
            table = elf.get_section(reloc['sh_link'])
            for entry in reloc.iter_relocations():
                if start <= entry['r_offset'] < start + size:
                    target = table.get_symbol(entry['r_info_sym'])
                    target_name = target.name or elf.get_section(target['st_shndx']).name
                    relocations.append(dict(offset=entry['r_offset']-start,
                                            type=entry['r_info_type'],target=target_name,
                                            addend=entry['r_addend'] if entry.is_RELA() else 0))
        return dict(size=size,bytes=section.data()[start:start+size].hex(),relocations=relocations)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reuse', type=Path,
                        help='reuse matching objects from a completed earlier check')
    kernel_identity.arguments(parser)
    a = parser.parse_args()
    assert os.geteuid() == 0 and str(ROOT).startswith('/root/')
    assert os.uname().release == '6.1.159-kdclobber2'
    idle = runpy.run_path(str(ROOT / 'bench/archive_run.py'))['idle']
    idle(Path('/root'), rt.idle)
    tree = a.kernel_source.resolve()
    out = a.output.resolve()
    assert not out.exists() and not out.is_relative_to(ROOT) and not out.is_relative_to(tree)
    out.mkdir(parents=True)
    result = dict(passed=False,installed=False,booted=False,kernel_image_built=False,
                  live_tests=0,source_unchanged=False)
    try:
        # Verify existing identity in place; do not duplicate the unchanged bundle.
        result['kernel_identity'] = kernel_identity.check(tree, a.kernel_baseline)
        integration = ROOT / 'kernel_integration/mmap_lock'
        expected = json.loads((integration / 'base-sha256.json').read_text())
        source_inputs = {str(p.relative_to(ROOT)): rt.digest(p) for p in
                         [Path(__file__), HERE/'payload/wrappers.c',
                          integration/'guest-kernel.patch', integration/'base-sha256.json']}
        native = {n: rt.digest(tree/n) for n in NATIVE}
        config = (tree/'include/generated/autoconf.h').read_text()
        assert not re.search(r'^#define CONFIG_(KD_MMAP_LOCK|LOCKDEP|DEBUG_LOCK_ALLOC|PREEMPT_RT)\b', config, re.M)
        assert '#define CONFIG_BPF_SYSCALL 1' in config and '#define CONFIG_SMP 1' in config
        original_objects = {n: tree/(n+'.o') for n in TARGETS}
        observed = sum(p.stat().st_size for p in original_objects.values())
        source_bytes = sum((tree/n).stat().st_size for n in expected)
        budget = source_bytes + 12 * observed
        free = shutil.disk_usage(out).free
        assert free > budget
        result['space'] = dict(free=free,budget=budget,original_object_bytes=observed,
                               wrapper_source_bytes=source_bytes)
        frozen = {n: rt.digest(tree/n) for n in
                  ['.config','include/generated/autoconf.h','include/config/auto.conf',
                   'include/generated/compile.h',*expected,*NATIVE,
                   'kernel/bpf/percpu_freelist.h',
                   *(target+'.c' for target in TARGETS)]}
        for target, obj in original_objects.items():
            command, _ = recipe(tree,target)
            frozen[str(command.relative_to(tree))] = rt.digest(command)
            frozen[str(obj.relative_to(tree))] = rt.digest(obj)
        rt.write_json(out/'recovery-inputs.json', frozen)
        rt.write_json(out/'source-inputs.json', source_inputs)
        result['compiler'] = (tree/'include/generated/compile.h').read_text()
        result['tools'] = dict(gcc=output(['gcc','--version']).splitlines()[0],
                               ld=output(['ld','--version']).splitlines()[0])
        assert all(value in result['compiler'] for value in result['tools'].values())
        reuse = a.reuse.resolve() if a.reuse else None
        prior = None
        if reuse:
            assert reuse != out
            prior = json.loads((reuse/'result.json').read_text())
            assert prior['passed'] and prior['source_unchanged'] and prior['tools']==result['tools']
            for n,h in json.loads((reuse/'source-inputs.json').read_text()).items():
                if n != str(Path(__file__).relative_to(ROOT)):
                    assert source_inputs[n]==h,(n,'reuse source mismatch')
            for n,h in json.loads((reuse/'recovery-inputs.json').read_text()).items():
                assert frozen[n]==h,(n,'reuse recovery mismatch')
            result['reused_from']=str(reuse)
        patched = out/'patched'
        patched.mkdir()
        for name, digest in expected.items():
            assert rt.digest(tree/name) == digest, name
            dest = patched/name; dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(tree/name,dest)
        rt.command(['patch','--batch','--fuzz=0','-p1','-i',integration/'guest-kernel.patch'],
                   out/'patch.log',timeout=30,cwd=patched)
        for target in TARGETS:
            name=target+'.c'
            if name not in expected:
                dest=patched/name;dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(tree/name,dest)
        if reuse:
            for n in expected:
                assert rt.digest(reuse/'patched'/n)==rt.digest(patched/n),(n,'reuse patch mismatch')
        # Keep configuration bytes identical to the verified native baseline.
        # The new bool has no default-y clause; its absent preprocessor symbol
        # selects the disabled path. No olddefconfig or recovery write occurs.
        shutil.copyfile(tree/'.config',out/'native.config')
        shutil.copyfile(tree/'include/generated/autoconf.h',out/'autoconf.h')
        assert 'config KD_MMAP_LOCK\n' in (patched/'mm/Kconfig').read_text()
        selection = out/'selection.mk'
        selection.write_text('include '+str(tree/'include/config/auto.conf')+'\ninclude '+
                             str(patched/'kernel/locking/Makefile')+
                             '\n.PHONY: selected\nselected:\n\t@printf "%s\\n" "$(obj-y)" "$(obj-m)"\n')
        selected = rt.command(['make','--no-builtin-rules','--no-print-directory','-f',selection,'selected'],
                              out/'selection.log',timeout=30,cwd=out)
        assert 'kd_mmap' not in selected
        built=[];compiled=0;reused={}
        for target in TARGETS:
            dest=out/(Path(target).name+'.o')
            args=compile_args(tree,target,patched/(target+'.c'),dest,patched/'include')
            header_root=patched
            if prior and dest.name in prior['output_sha256']:
                dest=reuse/dest.name;header_root=reuse/'patched'
                assert rt.digest(dest)==prior['output_sha256'][dest.name]
                recorded=json.loads((reuse/(Path(target).name+'-build.log.command.json')).read_text())
                assert recorded['argv']==compile_args(tree,target,header_root/(target+'.c'),dest,header_root/'include')
                reused[str(dest)]=rt.digest(dest)
            else:
                rt.command(args,out/(Path(target).name+'-build.log'),timeout=120,cwd=tree)
                compiled+=1
            dependencies=dest.with_suffix('.d').read_text()
            assert str(header_root/'include/linux/mm_types.h') in dependencies
            assert str(header_root/'include/linux/mmap_lock.h') in dependencies
            if target.startswith('kernel/bpf/'):
                assert str(header_root/'kernel/bpf/mmap_unlock_work.h') in dependencies
            built.append(dest)
        fixture=HERE/'payload/wrappers.c'
        fixtures={}
        for label,headers in [('native',None),('disabled',patched/'include')]:
            dest=out/(label+'-wrappers.o')
            args=compile_args(tree,'mm/mmap_lock',fixture,dest,headers,label=='disabled')
            if prior and dest.name in prior['output_sha256']:
                dest=reuse/dest.name
                assert rt.digest(dest)==prior['output_sha256'][dest.name]
                old_headers=reuse/'patched/include' if headers else None
                recorded=json.loads((reuse/(label+'-wrappers.log.command.json')).read_text())
                assert recorded['argv']==compile_args(tree,'mm/mmap_lock',fixture,dest,old_headers,label=='disabled')
                reused[str(dest)]=rt.digest(dest)
            else:
                rt.command(args,out/(label+'-wrappers.log'),timeout=120,cwd=tree)
                compiled+=1
            fixtures[label]=dest
            if label=='disabled':
                macro_args=[x for x in args if not x.startswith('-Wp,-MMD,')]
                index=macro_args.index('-o');del macro_args[index:index+2]
                macro_args.remove('-c');macro_args[1:1]=['-E','-dM']
                macros=output(macro_args,cwd=tree)
                assert not re.search(r'^#define CONFIG_KD_MMAP_LOCK\b',macros,re.M)
                for key,value in ALIASES.items():
                    assert '#define __mmap_sem_'+key+' '+value+'\n' in macros,key
                rt.write_json(out/'selected-aliases.json',ALIASES)
        comparisons={}
        for symbol in [*('disabled_'+name for name in COMMON),'disabled_static_mm','disabled_layout']:
            before=symbol_image(fixtures['native'],symbol)
            after=symbol_image(fixtures['disabled'],symbol)
            comparisons[symbol]=dict(equal=before==after,native=before,disabled=after)
        rt.write_json(out/'wrapper-comparison.json',comparisons)
        assert all(d['equal'] for d in comparisons.values()), 'inspect wrapper byte/relocation differences'
        destroy=symbol_image(fixtures['disabled'],'disabled_destroy')
        assert all(r['target'] in ('__fentry__','__x86_return_thunk') for r in destroy['relocations'])
        for label,objects in [('native',list(original_objects.values())),('disabled',built)]:
            rt.command(['ld','-r','-o',out/(label+'-linked.o'),*objects,fixtures[label]],
                       out/(label+'-link.log'),timeout=60)
        new_undefined=sorted(set(undefined(out/'disabled-linked.o'))-set(undefined(out/'native-linked.o')))
        assert not new_undefined,new_undefined
        symbols=output(['nm',out/'disabled-linked.o'])
        for name in ('mmap_read_unlock_prepare','mmap_read_unlock_complete','mmdrop_async'):
            assert re.search(r'\bT '+name+r'$',symbols,re.M),name
        assert not re.search(r'\bkd_mmap_\w+|\b\w*(?:split_vma_prepared|munmap_prepared|anon_vma_clone_prepared)\w*',symbols)
        assert not any(name.startswith('kd_mmap_') for name in undefined(fixtures['disabled']))
        rt.write_json(out/'link-comparison.json',dict(native_undefined=undefined(out/'native-linked.o'),
                      disabled_undefined=undefined(out/'disabled-linked.o'),new_undefined=new_undefined,
                      lifetime_symbols_resolved=True,kd_mmap_symbols=[]))
        for n,h in frozen.items():assert rt.digest(tree/n)==h,n
        for n,h in source_inputs.items():assert rt.digest(ROOT/n)==h,n
        for n,h in reused.items():assert rt.digest(Path(n))==h,n
        idle(Path('/root'),rt.idle)
        result.update(passed=True,source_unchanged=True,idle=True,compiled_objects=compiled,
                      reused_checked_objects=reused,reused_native_objects=len(TARGETS),
                      partial_links=2,wrapper_comparisons=len(COMMON),
                      selected_native_aliases=len(ALIASES),native_body_sha256=native,
                      config_sha256=frozen['.config'],autoconf_sha256=frozen['include/generated/autoconf.h'],
                      output_sha256={p.name:rt.digest(p) for p in out.glob('*.o')},
                      limits='Disabled preprocessor path and affected builtin objects/relocatable links only; no full kernel link, boot, runtime, RT or lockdep validation.')
    except BaseException as error:
        result['error']=repr(error)
        raise
    finally:
        rt.write_json(out/'result.json',result)
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    main()
