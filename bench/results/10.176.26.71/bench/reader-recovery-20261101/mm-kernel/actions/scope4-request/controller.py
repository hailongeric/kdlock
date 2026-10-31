#!/usr/bin/env python3
"""One explicit VM kernel stage/install/boot action; never runs the next action."""
import argparse, ast, datetime, hashlib, importlib.util, json, mmap, os, re, runpy
import shlex, shutil, stat, struct, subprocess, sys, time, types
from pathlib import Path
sys.dont_write_bytecode = True
GIB = 1024**3
NORMAL = '7.0.0-38-kdlock1'
INDEX_FILES = {'modules.dep', 'modules.dep.bin', 'modules.alias', 'modules.alias.bin',
               'modules.symbols', 'modules.symbols.bin', 'modules.softdep', 'modules.weakdep',
               'modules.devname', 'modules.builtin.bin', 'modules.builtin.alias.bin'}


def require(ok, message):
    if not ok: raise RuntimeError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 << 20), b''): h.update(chunk)
    return h.hexdigest()


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def checked(path, sha256):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and sha(path) == sha256, 'input bytes differ: '+str(path))
    return json.loads(path.read_text())


def ref(path):
    return dict(path=str(Path(path)), sha256=sha(path))


def record(path):
    path = Path(path)
    if path.is_symlink(): return dict(link=os.readlink(path), mode=path.lstat().st_mode)
    if not path.exists(): return dict(absent=True)
    require(path.is_file(), 'expected a file: '+str(path))
    return dict(bytes=path.stat().st_size, mode=path.stat().st_mode, sha256=sha(path))


def inventory(root):
    rows = {}
    for path in sorted(Path(root).rglob('*')):
        name = str(path.relative_to(root))
        if path.is_symlink() or path.is_file(): rows[name] = record(path)
        elif path.is_dir(): rows[name] = dict(directory=True, mode=path.stat().st_mode)
        else: raise RuntimeError('unexpected module member: '+str(path))
    return rows


def process_group(group):
    rows = []
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            fields = path.read_text().rsplit(')', 1)[1].split()
            if int(fields[2]) == group: rows.append(dict(pid=int(path.parent.name), state=fields[0]))
        except (FileNotFoundError, ProcessLookupError): pass
    return rows


# ELF and loader_identity below are retained from the reviewed scope2 module
# correspondence implementation. They inspect allocated contents and linkage.


class ELF:
    """Read the fixed ELF64 little-endian formats used by this x86 build."""
    def __init__(self, path):
        self.path = path
        self.stream = path.open('rb')
        self.data = mmap.mmap(self.stream.fileno(), 0, access=mmap.ACCESS_READ)
        d = self.data
        require(d[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', d, 18)[0] == 62,
                'not x86-64 little-endian ELF')
        self.elf_type = struct.unpack_from('<H', d, 16)[0]
        shoff = struct.unpack_from('<Q', d, 40)[0]
        entsize, count, names_index = struct.unpack_from('<HHH', d, 58)
        require(entsize == 64 and count > 0 and names_index < count and
                shoff + count * entsize <= len(d), 'unsupported ELF section headers')
        self.sections = []
        for i in range(count):
            fields = struct.unpack_from('<IIQQQQIIQQ', d, shoff + i * 64)
            self.sections.append(dict(zip(('name_index', 'type', 'flags', 'address', 'offset',
                'size', 'link', 'info', 'align', 'entsize'), fields)))
        strings = self.contents(self.sections[names_index])
        for section in self.sections:
            section['name'] = self.cstring(strings, section['name_index'])
        self.symbols = {}
        symtab = self.section('.symtab')
        require(symtab['entsize'] == 24 and symtab['size'] % 24 == 0, 'invalid symbol table')
        strings = self.contents(self.sections[symtab['link']])
        for offset in range(symtab['offset'], symtab['offset'] + symtab['size'], 24):
            name, info, other, index, value, size = struct.unpack_from('<IBBHQQ', d, offset)
            name = self.cstring(strings, name)
            if name:
                self.symbols.setdefault(name, []).append(dict(name=name, info=info, other=other,
                    index=index, value=value, size=size))

    @staticmethod
    def cstring(data, offset):
        require(0 <= offset < len(data), 'string offset outside table')
        end = data.find(b'\0', offset)
        require(end >= 0, 'unterminated ELF string')
        return data[offset:end].decode('utf-8')

    def contents(self, section):
        require(section['type'] != 8 and section['offset'] + section['size'] <= len(self.data),
                'missing/outside ELF section data')
        return self.data[section['offset']:section['offset'] + section['size']]

    def section(self, name):
        rows = [s for s in self.sections if s.get('name') == name]
        require(len(rows) == 1, 'missing/duplicate ELF section: ' + name)
        return rows[0]

    def symbol(self, name):
        rows = [s for s in self.symbols.get(name, []) if s['index'] != 0]
        distinct = {(s['index'], s['value'], s['size']) for s in rows}
        require(len(distinct) == 1, 'missing/ambiguous defined symbol: ' + name)
        return rows[0]

    def virtual(self, address, size, executable=False, readonly=False):
        rows = [s for s in self.sections if s['type'] != 8 and s['flags'] & 2 and
                s['address'] <= address and address + size <= s['address'] + s['size']]
        require(len(rows) == 1, 'virtual range not in one allocated section')
        section = rows[0]
        require(not executable or section['flags'] & 4, 'range is not executable')
        require(not readonly or not section['flags'] & 1, 'site table is writable')
        offset = section['offset'] + address - section['address']
        return self.data[offset:offset + size]

    def function(self, name):
        row = self.symbol(name)
        require(row['info'] & 15 == 2 and row['size'] > 0, 'not a sized function: ' + name)
        return row, self.virtual(row['value'], row['size'], executable=True)

    def close(self):
        self.data.close()
        self.stream.close()


def loader_identity(helper, path):
    """Allocated bytes and loader relocations/symbols; ignores removable DWARF.

    The module loader consumes SHF_ALLOC sections, their relocations and symbol
    bindings. Strip-debug can renumber sections/symbols, so those references are
    normalized by section/name/value rather than comparing index numbers.
    This is artifact correspondence, not a universal runtime ABI proof.
    """
    elf = helper.ELF(path)
    try:
        require(elf.elf_type == 1, 'module is not relocatable ELF: ' + str(path))
        allocated = {i: s for i, s in enumerate(elf.sections) if s['flags'] & 2}
        require(allocated and len({s['name'] for s in allocated.values()}) == len(allocated),
                'missing/duplicate allocated section names')
        sections = []
        for s in allocated.values():
            row = {k: s[k] for k in ('name', 'type', 'flags', 'size', 'align', 'entsize')}
            row['sha256'] = None if s['type'] == 8 else hashlib.sha256(elf.contents(s)).hexdigest()
            sections.append(row)
        tab = elf.section('.symtab')
        strings = elf.contents(elf.sections[tab['link']])
        symbols = []
        for offset in range(tab['offset'], tab['offset'] + tab['size'], 24):
            name, info, other, index, value, size = struct.unpack_from('<IBBHQQ', elf.data, offset)
            require(index != 0xffff, 'extended symbol indexes need separate review')
            target = elf.sections[index]['name'] if 0 < index < len(elf.sections) else index
            symbols.append(dict(name=elf.cstring(strings, name), info=info, other=other,
                                section=target, value=value, size=size))
        # FILE/debug-only symbols may disappear. Keep every allocated/undefined
        # and non-FILE absolute/common symbol that can affect module linkage.
        names = {s['name'] for s in allocated.values()}
        relocations = []
        referenced = set()
        for s in elf.sections:
            if s['type'] not in (4, 9) or s['info'] not in allocated:
                continue
            require(elf.sections[s['link']] is tab, 'relocation uses an unexpected symbol table')
            size = 24 if s['type'] == 4 else 16
            require(s['entsize'] == size and s['size'] % size == 0, 'invalid module relocations')
            for offset in range(s['offset'], s['offset'] + s['size'], size):
                where, info = struct.unpack_from('<QQ', elf.data, offset)
                require(info >> 32 < len(symbols), 'relocation symbol outside table')
                referenced.add(info >> 32)
                relocations.append(dict(section=allocated[s['info']]['name'], offset=where,
                    type=info & 0xffffffff, symbol=symbols[info >> 32],
                    addend=struct.unpack_from('<q', elf.data, offset + 16)[0] if size == 24 else None))
        # strip-debug may remove unused local section-name placeholders. Only
        # that canonical class is dispensable; a referenced one remains both
        # in this inventory and in its exact normalized relocation record.
        relevant = []
        for number, symbol in enumerate(symbols):
            if not (symbol['section'] in names or symbol['section'] == 0 or
                    (symbol['section'] in (0xfff1, 0xfff2) and symbol['info'] & 15 != 4)):
                continue
            unused_section = (number not in referenced and symbol['section'] in names
                and symbol['name'] == '' and symbol['info'] == 3 and symbol['other'] == 0
                and symbol['value'] == 0 and symbol['size'] == 0)
            if not unused_section:
                relevant.append(symbol)
        key = lambda row: json.dumps(row, sort_keys=True)
        return digest_json(dict(sections=sorted(sections, key=key),
                               symbols=sorted(relevant, key=key),
                               relocations=sorted(relocations, key=key)))
    finally:
        elf.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('stage','install','append','arm','request','capture','normal-request','normal-verify'))
    for name in ('config','output','host-state'): p.add_argument('--'+name, type=Path, required=True)
    for name in ('config-sha256','host-state-sha256','boot-id'): p.add_argument('--'+name, required=True)
    p.add_argument('--prior', type=Path); p.add_argument('--prior-sha256')
    p.add_argument('--mode', choices=('native','kd'))
    p.add_argument('--bundle-manifest-sha256')
    a = p.parse_args(); c = checked(a.config, a.config_sha256)
    require(c.get('schema') == 1 and os.geteuid() == 0 and sys.executable == c['python'], 'VM/config/interpreter differs')
    release = c['release']; root, source, build = map(Path, (c['recipe'],c['source'],c['build']))
    require(re.fullmatch(r'7\.0\.0-38-kdscope[3-9][0-9]*', release), 'distinct scoped release required')
    require(source.parent == build.parent and source.name == 'source' and build.name == 'build', 'separated source/output required')
    data = Path(c['data_mount']); stage = Path(c['stage']); live = Path('/lib/modules')/release
    boot = lambda: Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    require(boot() == a.boot_id and data.is_mount(), 'current boot or dedicated DATA mount differs')
    require(all(path.resolve() == path and path.is_relative_to(data) for path in (root,source,build,stage,a.output)),
            'canonical DATA recipe/build/evidence/stage paths required')
    require(all(not a.output.is_relative_to(path) for path in (root,source,build,stage)), 'evidence cannot modify frozen inputs')
    manifest = checked(c['manifest'], c['manifest_sha256'])
    require(manifest['source_commit'] == c['commit'], 'recipe commit differs')
    built = checked(c['build_result'], c['build_result_sha256'])
    require(built.get('passed') is True and built.get('state') == 'COMPLETE' and built.get('phase') == 'build' and
            not built.get('drain_unknown') and built['source_commit'] == c['commit'] and
            built['provider_commit'] == c['provider_commit'] and built['release'] == release and
            built['source'] == str(source) and built['build'] == str(build) and
            built.get('recipe_unchanged') is True and built.get('source_named_unchanged') is True and
            built['blocks'] and all(row.get('returncode') == 0 for row in built['blocks']), 'successful exact build receipt required')
    require((build/'include/config/kernel.release').read_text().strip() == release, 'built release differs')
    def inputs():
        for name, row in built['outputs'].items():
            require(sha(build/name) == row['sha256'] and (build/name).stat().st_size == row['bytes'], 'build output differs: '+name)
        for name, digest in built['source_named_sha256'].items(): require(sha(source/name) == digest, 'composed source differs: '+name)
        for name in ('bench/archive_run.py','bench/spin_cacheline/bench_runtime.py','bench/basic/capture_host.py',
                     'kernel_integration/linux70/capture.py','kernel_integration/linux70/verify.py'):
            require(sha(root/name) == manifest['files'][name]['sha256'], 'maintained helper differs: '+name)
    inputs()
    sys.path.insert(0, str(root/'bench/spin_cacheline')); import bench_runtime as rt
    idle = runpy.run_path(str(root/'bench/archive_run.py'))['idle']
    idle(root, rt.idle); idle(Path('/root/host_fs/kdlock'), rt.idle)
    host = checked(a.host_state, a.host_state_sha256)
    hs = importlib.util.spec_from_file_location('writer_kernel_host',root/'bench/basic/capture_host.py')
    hm = importlib.util.module_from_spec(hs); hs.loader.exec_module(hm); hm.validate(host)
    age = (datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(host['captured_utc'])).total_seconds()
    require(0 <= age < 240 and host['pins_verified'] and host['frequency_verified'] and host['snapshot_listed'] and
            host['recovery_snapshot'] == c['snapshot'], 'fresh actual recovery/host capture required')
    a.output.mkdir(parents=True, exist_ok=False)
    for path, name in ((a.config,'config.json'),(a.host_state,'host-state.json'),(Path(__file__),'controller.py')):
        shutil.copyfile(path,a.output/name)
    r = dict(schema=1, action=a.action, passed=False, state='STARTING', boot_id=a.boot_id, release=release,
             source_commit=c['commit'], provider_commit=c['provider_commit'], config_sha256=a.config_sha256,
             controller_sha256=sha(__file__), build_result=ref(c['build_result']), source=str(source), build=str(build),
             host_state=ref(a.output/'host-state.json'), snapshot=c['snapshot'], commands=[], started=time.time(),
             performance_accepted=False, drain_unknown=False)
    def save():
        temporary=a.output/'result.tmp'
        with temporary.open('w') as stream:
            stream.write(json.dumps(r,indent=2)+'\n');stream.flush();os.fsync(stream.fileno())
        temporary.replace(a.output/'result.json')
        directory=os.open(a.output,os.O_DIRECTORY);os.fsync(directory);os.close(directory)
    def output_json(name,value):
        path=a.output/name; path.write_text(json.dumps(value,indent=2)+'\n'); return ref(path)
    env=dict(os.environ,LANG='C',LC_ALL='C',PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(a.output),
             PATH=str(Path(c['python']).parent)+':'+os.environ['PATH'])
    def command(name,argv,timeout=120):
        argv=list(map(str,argv)); row=dict(name=name,argv=argv,started=time.time()); r['commands'].append(row); save()
        log=a.output/(name+'.log')
        with log.open('xb') as stream:
            child=subprocess.Popen(argv,cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            row['pid']=child.pid; row['process_group']=child.pid; r['drain_unknown']=True; save()
            try: code=child.wait(timeout=timeout)
            except subprocess.TimeoutExpired: row['timed_out']=True; save(); raise
        row.update(returncode=code,remaining_processes=process_group(child.pid),finished=time.time(),log=ref(log)); save()
        require(code == 0 and not row['remaining_processes'], 'command failed or not drained: '+name)
        r['drain_unknown']=False; save(); return log.read_text()
    def previous(path,sha256):
        value=checked(path,sha256)
        require(value['config_sha256'] == a.config_sha256 and value['controller_sha256'] == r['controller_sha256'] and
                value['source_commit'] == c['commit'] and value['release'] == release, 'prior action belongs to another generation')
        return value
    prior=previous(a.prior,a.prior_sha256) if a.prior else None
    if prior: r['prior']=ref(a.prior)
    def need_prior(action, same_boot=True):
        require(prior and prior['action'] == action and prior.get('passed') is True and not prior.get('drain_unknown'), 'completed prior action required: '+action)
        require(not same_boot or prior['boot_id'] == a.boot_id, 'prior boot differs')
    custom,grubcfg,grubenv=map(Path,('/boot/grub/custom.cfg','/boot/grub/grub.cfg','/boot/grub/grubenv'))
    def environment(name):
        return dict(line.split('=',1) for line in command(name,['grub-editenv',grubenv,'list']).splitlines() if '=' in line)
    def protected():
        paths={Path('/etc/default/grub'),custom,grubcfg,grubenv}
        for pattern in ('vmlinuz*','initrd*'): paths.update(Path('/').glob(pattern))
        for pattern in ('vmlinuz-*','initrd.img-*','config-*','System.map-*'): paths.update(Path('/boot').glob(pattern))
        return {str(path):record(path) for path in sorted(paths) if not path.name.endswith('-'+release)}
    def unchanged(before, allowed=()):
        after=protected(); require({k:v for k,v in before.items() if k not in allowed} ==
                                  {k:v for k,v in after.items() if k not in allowed}, 'old boot/default/link paths changed')
        return after
    def root_uuid():
        uuid=command('root-uuid',['findmnt','-n','-o','UUID','--target','/']).strip()
        require(re.fullmatch(r'[0-9a-fA-F-]{36}',uuid), 'one root UUID required')
        require(command('boot-uuid',['findmnt','-n','-o','UUID','--target','/boot']).strip() == uuid and
                command('grub-uuid',['grub-probe','--target=fs_uuid','/boot']).strip() == uuid, 'boot/root UUID differs')
        return uuid
    def default_check(uuid):
        normal_id='gnulinux-'+NORMAL+'-advanced-'+uuid
        default='gnulinux-advanced-'+uuid+'>'+normal_id
        require(default in re.findall(r'(?m)^\s*set default="([^"]+)"\s*$',grubcfg.read_text()), 'ordinary permanent default differs')
        return normal_id,default
    def installed_files(value):
        for name,row in value['boot_files'].items(): require(record(name) == row, 'new installed boot file differs: '+name)
        saved=checked(**value['module_manifest']); require(inventory(live) == saved, 'installed new module tree differs')
    save()
    try:
        before=protected(); r['protected_before']=output_json('protected-before.json',before)
        if a.action == 'stage':
            require(prior is None and not stage.exists() and not live.exists(), 'fresh uninstalled staging required')
            ordered=(build/'modules.order').read_text().splitlines()
            names=[name.removeprefix('./').removesuffix('.o')+'.ko' for name in ordered]
            require(ordered and all(name.endswith('.o') and not name.startswith('/') and '..' not in Path(name).parts for name in ordered)
                    and len(names)==len(set(names)), 'ordered module set differs')
            require({str(path.relative_to(build)) for path in build.rglob('*.ko')} == set(names), 'actual built module set differs')
            require(shutil.disk_usage(data).free > sum((build/name).stat().st_size for name in names)+2*GIB, 'DATA staging reserve unavailable')
            identities={name:dict(sha256=sha(build/name),identity=loader_identity(types.SimpleNamespace(ELF=ELF),build/name)) for name in names}
            stage.mkdir(parents=True)
            command('modules-install',['make','-C',source,'O='+str(build),'ARCH=x86','CC=x86_64-linux-gnu-gcc',
                    'KERNELRELEASE='+release,'-j32','INSTALL_MOD_PATH='+str(stage),'INSTALL_MOD_STRIP=1','modules_install'],1800)
            staged=stage/'lib/modules'/release
            require({str(path.relative_to(staged/'kernel')) for path in (staged/'kernel').rglob('*.ko')} == set(names), 'staged module set differs')
            for name in names:
                require(sha(build/name)==identities[name]['sha256'] and
                        loader_identity(types.SimpleNamespace(ELF=ELF),staged/'kernel'/name)==identities[name]['identity'], 'installed module linkage differs: '+name)
            for index in range(0,len(names),128):
                lines=command('module-release-'+str(index),['modinfo','-F','vermagic',*[staged/'kernel'/name for name in names[index:index+128]]]).splitlines()
                require(len(lines)==len(names[index:index+128]) and all(line.split()[0]==release for line in lines), 'staged module release differs')
            r.update(stage=str(staged),module_count=len(names),build_modules=output_json('build-module-identities.json',identities),
                     module_manifest=output_json('staged-modules.json',inventory(staged)),state='STAGED_NOT_INSTALLED')
        elif a.action == 'install':
            need_prior('stage'); staged=Path(prior['stage']); rows=checked(**prior['module_manifest'])
            require(inventory(staged)==rows and not live.exists(), 'stage changed or new release already installed')
            images={'arch/x86/boot/bzImage':Path('/boot/vmlinuz-'+release),'System.map':Path('/boot/System.map-'+release),'.config':Path('/boot/config-'+release)}
            initrd=Path('/boot/initrd.img-'+release)
            require(all(not path.exists() and not path.is_symlink() for path in (*images.values(),initrd)), 'new boot leaf already exists')
            reserve=sum(row.get('bytes',0) for row in rows.values())+sum((build/name).stat().st_size for name in images)+512*1024**2+2*GIB
            require(shutil.disk_usage('/').free>reserve and shutil.disk_usage(data).free>2*GIB, 'installation/root or DATA reserve unavailable')
            command('copy-modules',['cp','-a','--reflink=never','--',staged,live],300)
            require(inventory(live)==rows, 'module copy differs')
            command('depmod',['depmod','-a',release],300); installed=inventory(live)
            require({k:v for k,v in rows.items() if k not in INDEX_FILES} == {k:v for k,v in installed.items() if k not in INDEX_FILES}, 'depmod changed non-index members')
            for name,path in images.items():
                with path.open('xb') as target, (build/name).open('rb') as original: shutil.copyfileobj(original,target)
                path.chmod(0o644); require(sha(path)==built['outputs'][name]['sha256'], 'new boot copy differs')
            command('initramfs',['mkinitramfs','-o',initrd,release],900)
            require(0<initrd.stat().st_size<=512*1024**2, 'initramfs outside budget')
            extract=a.output/'initramfs'; command('extract-initramfs',['unmkinitramfs',initrd,extract],300)
            included={}
            require(any(path.name=='init' for path in extract.rglob('init')), 'initramfs init missing')
            for path in extract.rglob('*.ko'):
                parts=path.relative_to(extract).parts; indexes=[i for i in range(len(parts)-2) if parts[i:i+2]==('lib','modules')]
                require(len(indexes)==1 and parts[indexes[0]+2]==release, 'initramfs module release path differs')
                relative='/'.join(parts[indexes[0]+3:]); require(relative in installed and sha(path)==installed[relative]['sha256'], 'initramfs module bytes differ')
                included[str(path.relative_to(extract))]=installed[relative]['sha256']
            require(included and inventory(live)==installed and inventory(staged)==rows, 'initramfs modules absent or installed/stage bytes changed')
            require(shutil.disk_usage('/').free>2*GIB, 'root installation reserve consumed')
            r.update(boot_files={str(path):record(path) for path in (*images.values(),initrd)},
                     module_manifest=output_json('installed-modules.json',installed),initramfs_modules=output_json('initramfs-modules.json',included),
                     state='INSTALLED_NOT_ARMED')
        elif a.action == 'append':
            need_prior('install',False); installed_files(prior)
            require(os.uname().release==NORMAL and not environment('environment-before').get('next_entry'), 'ordinary boot with no queued entry required')
            uuid=root_uuid(); normal_id,default=default_check(uuid); generated=grubcfg.read_text()
            require('source ${config_directory}/custom.cfg' in generated or 'source $prefix/custom.cfg' in generated, 'custom entry source absent')
            lines=generated.splitlines(keepends=True)
            starts=[i for i,line in enumerate(lines) if re.match(r'^\s*menuentry\s',line) and re.search(r"['\"]"+re.escape(normal_id)+r"['\"]",line)]
            require(len(starts)==1,'normal advanced stanza ambiguous'); start=starts[0]; indent=re.match(r'^\s*',lines[start]).group()
            end=next(i for i in range(start+1,len(lines)) if lines[i].rstrip('\n')==indent+'}')
            stanza=''.join(lines[start:end+1]); linux=re.findall(r'(?m)^\s*linux\s+.*$',stanza); init=re.findall(r'(?m)^\s*initrd\s+.*$',stanza)
            require(len(linux)==len(init)==1,'normal stanza image commands differ')
            words=shlex.split(linux[0]); runtime=Path('/proc/cmdline').read_text().split()
            require(words[:2]==['linux','/boot/vmlinuz-'+NORMAL] and shlex.split(init[0])==['initrd','/boot/initrd.img-'+NORMAL] and
                    runtime.count('BOOT_IMAGE=/boot/vmlinuz-'+NORMAL)==1,'normal image path differs')
            parameters=[]
            for word in words[2:]:
                if word=='$vt_handoff': parameters.extend(['vt.handoff=7'] if 'vt.handoff=7' in runtime else [])
                else: require('$' not in word and '`' not in word,'unexpected GRUB expansion'); parameters.append(word)
            require(parameters==[word for word in runtime if not word.startswith('BOOT_IMAGE=')] and
                    all(parameters.count(word)==1 for word in ('root=UUID='+uuid,'ro','nokaslr','nopvspin','console=tty1','console=ttyS0')) and
                    not any(word.startswith('kd_mmap=') for word in parameters),'normal runtime arguments differ')
            require([word for word in parameters if word.startswith('preempt=')] in ([],['preempt=lazy']) and
                    re.findall(r'\((none|voluntary|full|lazy)\)',Path('/sys/kernel/debug/sched/preempt').read_text())==['lazy'],'active/requested preemption differs')
            if 'preempt=lazy' not in parameters: parameters.append('preempt=lazy')
            require(custom.is_file() and not custom.is_symlink() and custom.stat().st_uid==0,'regular root-owned custom.cfg required'); prefix=custom.read_bytes(); entries={}
            addition='\n# '+release+' explicit mode entries\n'
            for mode in ('native','kd'):
                entry='kdlock-'+release+'-'+mode; require(entry.encode() not in prefix and entry not in generated,'entry already exists'); entries[mode]=entry
                addition += ("menuentry '"+release+' '+mode+"' --id '"+entry+"' {\n  search --no-floppy --fs-uuid --set=root "+uuid+
                    '\n  linux /boot/vmlinuz-'+release+' '+shlex.join(parameters+['kd_mmap='+('off' if mode=='native' else 'on')])+
                    '\n  initrd /boot/initrd.img-'+release+'\n}\n')
            candidate=a.output/'custom.cfg';candidate.write_bytes(prefix+addition.encode()); command('grub-syntax',['grub-script-check',candidate])
            temporary=custom.with_name('.'+release+'.tmp'); require(not temporary.exists(),'custom temporary exists')
            with temporary.open('xb') as stream:stream.write(candidate.read_bytes());stream.flush();os.fsync(stream.fileno())
            temporary.chmod(stat.S_IMODE(custom.stat().st_mode));os.replace(temporary,custom)
            directory=os.open(custom.parent,os.O_DIRECTORY);os.fsync(directory);os.close(directory)
            require(custom.read_bytes()==prefix+addition.encode(),'custom append differs'); command('grub-installed-syntax',['grub-script-check',custom])
            r.update(installation=ref(a.prior),root_uuid=uuid,normal_default=default,entries=entries,custom_after=record(custom),state='ENTRIES_APPENDED_NOT_ARMED')
        elif a.action == 'arm':
            need_prior('append',False); require(a.mode in ('native','kd'),'explicit mode required')
            installed=previous(**prior['installation']); installed_files(installed)
            require(record(custom)==prior['custom_after'],'custom entries changed'); default_check(prior['root_uuid'])
            old=environment('environment-before'); require(not old.get('next_entry'),'another entry is queued')
            command('arm-once',['grub-reboot',prior['entries'][a.mode]])
            after=environment('environment-after'); require(after.get('next_entry')==prior['entries'][a.mode] and
                    {k:v for k,v in old.items() if k!='next_entry'}=={k:v for k,v in after.items() if k!='next_entry'},'one-shot environment differs')
            r.update(append=ref(a.prior),mode=a.mode,entry=after['next_entry'],state='ARMED_NOT_REBOOTED')
        elif a.action in ('request','normal-request'):
            need_prior('arm' if a.action=='request' else 'capture')
            if a.action=='request':
                append=previous(**prior['append']); expected=prior['entry']; r.update(arm=ref(a.prior),mode=prior['mode'])
            else:
                require(os.uname().release==release and prior['mode']=='kd' and not Path('/root/host_fs/kdlock').is_mount(),'final KD boot and source unbind required')
                append=previous(**prior['append']); expected=None; r.update(capture=ref(a.prior))
            require(record(custom)==append['custom_after'],'custom entries changed');default_check(append['root_uuid'])
            queued=environment('environment-before').get('next_entry')
            require((not queued) if expected is None else queued==expected,'queued next boot differs')
            r.update(append=prior['append'],state='REBOOT_INTENT_RECORDED',pre_request_idle=True);save()
            command('reboot',['systemctl','reboot'],30)
            r.update(state='REBOOT_REQUESTED_NOT_VERIFIED',passed=True);save()
            print(json.dumps(dict(passed=True,action=a.action,state=r['state'],output=str(a.output))),flush=True)
            return
        elif a.action in ('capture','normal-verify'):
            require(prior and prior['action']==('request' if a.action=='capture' else 'normal-request') and prior['boot_id']!=a.boot_id and
                    any(row.get('name')=='reboot' and row.get('pid') for row in prior['commands']), 'distinct boot and durable reboot command required')
            append=previous(**prior['append']);require(record(custom)==append['custom_after'],'custom entries changed');default_check(append['root_uuid'])
            require(not environment('environment-after').get('next_entry'),'one-shot entry not consumed')
            if a.action=='capture':
                arm=previous(**prior['arm']);mode=arm['mode'];variant=c['variants'][mode];bundle=Path(c['bundles'][mode])
                require(os.uname().release==release and [word for word in Path('/proc/cmdline').read_text().split() if word.startswith('kd_mmap=')]==
                        ['kd_mmap='+('off' if mode=='native' else 'on')],'running scoped release/backend differs')
                installed=previous(**append['installation']);installed_files(installed)
                if a.bundle_manifest_sha256: checked(bundle/'manifest.json',a.bundle_manifest_sha256)
                else:
                    require(not bundle.exists(),'new bundle already exists')
                    command('capture',[c['python'],root/'kernel_integration/linux70/capture.py','--variant',variant,'--preempt','lazy',
                            '--source',source,'--build',build,'--output',bundle,'--mmap-prepare',c['mmap_prepare'],
                            '--api-prepare',c['api_prepare'],'--composition',source.parent/'composition.json',
                            '--acquisition',Path(c['ubuntu'])/'source-acquisition.json','--source-archives',Path(c['ubuntu'])/'downloads'],900)
                bundle_sha=sha(bundle/'manifest.json')
                verify=json.loads(command('verify',[c['python'],root/'kernel_integration/linux70/verify.py','--variant',variant,
                            '--bundle',bundle,'--build-root',build,'--running'],900))
                require(sha(bundle/'manifest.json')==bundle_sha,'bundle changed during verification')
                r.update(mode=mode,bundle=str(bundle),bundle_manifest_sha256=sha(bundle/'manifest.json'),append=prior['append'])
            else:
                require(os.uname().release==NORMAL and not Path('/root/host_fs/kdlock').is_mount(),'ordinary release/source view differs')
                checked(Path(c['normal_bundle'])/'manifest.json',c['normal_bundle_sha256'])
                verify=json.loads(command('verify-normal',[c['python'],root/'kernel_integration/linux70/verify.py','--variant','kdlock1',
                            '--bundle',c['normal_bundle'],'--build-root',c['normal_build'],'--running'],900))
                r.update(normal_bundle=c['normal_bundle'],normal_bundle_manifest_sha256=c['normal_bundle_sha256'])
            require(verify.get('ok') is True and verify.get('schema')==2 and verify.get('runtime_policy_verified') is True,'running schema-2 identity failed')
            r.update(verification=verify,state='BOOT_RUNTIME_IDENTITY_VERIFIED')
        allowed=(str(custom),) if a.action=='append' else (str(grubenv),) if a.action=='arm' else ()
        r['protected_after']=output_json('protected-after.json',unchanged(before,allowed))
        inputs();idle(root,rt.idle);require(boot()==a.boot_id,'boot changed before action retirement')
        require(sha(a.config)==a.config_sha256 and sha(a.host_state)==a.host_state_sha256 and
                sha(c['manifest'])==c['manifest_sha256'] and sha(c['build_result'])==c['build_result_sha256'] and
                (a.prior is None or sha(a.prior)==a.prior_sha256),'retained action inputs changed')
        r.update(passed=True,final_idle=True,drain_unknown=False)
    except BaseException as error:r.update(state='FAILED',error=repr(error));raise
    finally:r['finished']=time.time();save()
    print(json.dumps(dict(passed=r['passed'],action=a.action,state=r['state'],output=str(a.output))),flush=True)


if __name__ == '__main__': main()
