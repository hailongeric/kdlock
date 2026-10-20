"""Read original provider observations only while its workload is quiescent.

No provider code, admission flag or owner record is written. ELF sections and
live symbol addresses bind a narrow /proc/kcore read to the loaded original
module. Two equal reads and the collector's joined-worker boundary establish
stable observations, not permission to release or retire anything.
"""
import hashlib
import os
from pathlib import Path
import struct
import time

PERCPU = {name: 8 for name in (
    'kd_mutex_slowpath_count', 'kd_mutex_combiner_count', 'kd_mutex_handoff_count',
    'kd_mutex_jit_success_count', 'kd_mutex_jit_not_ready_count',
    'kd_mutex_jit_failure_count', 'kd_mutex_jit_resume_count',
    'kd_mutex_frame_failure_count', 'kd_mutex_node_overflow_count',
    'kd_mutex_multi_slot_count', 'kd_mutex_context_busy_count',
    'kd_mutex_nested_lock_count', 'kd_mutex_nested_fast_count',
    'kd_mutex_nested_queued_count', 'kd_mutex_nested_jit_count',
    'kd_mutex_nested_unlock_count', 'kd_mutex_nested_abort_release_count',
    'kd_mutex_origin_acquires', 'kd_mutex_origin_releases',
    'kd_mutex_task_failures', 'kd_mutex_task_reroutes',
    'kd_bench_bodies', 'kd_bench_completions',
    'kd_hotlock_mutex_checks', 'kd_hotlock_mutex_entries',
    'kd_hotlock_mutex_contentions', 'kd_hotlock_mutex_last_entries')}
PERCPU.update({name: 4 for name in (
    'kd_mutex_active_waiters', 'kd_mutex_reserved_nodes')})
GLOBALS = dict(kd_native_started=8, kd_native_completed=8, kd_native_unlocks=8,
               kd_jit_times=240, kd_jit_timing=1)
PHASES = ('dispatch', 'wrapper', 'hostcall', 'control', 'native_spin_wait',
          'native_mutex_wait', 'spin_queue', 'mutex_queue',
          'native_spin_handoff', 'native_mutex_handoff')
RESIDUAL = {'kd_hotlock_mutex_entries', 'kd_hotlock_mutex_contentions',
            'kd_hotlock_mutex_last_entries'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def parse_symbols(text, module='kdlock_km'):
    selected = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[3] == '['+module+']' and parts[2] in PERCPU | GLOBALS:
            require(parts[2] not in selected, 'duplicate provider symbol: '+parts[2])
            selected[parts[2]] = dict(address=int(parts[0], 16), kind=parts[1])
        if len(parts) == 3 and parts[2] in ('__per_cpu_offset', '__pgtable_l5_enabled'):
            require(parts[2] not in selected, 'duplicate kernel observation symbol')
            selected[parts[2]] = dict(address=int(parts[0], 16), kind=parts[1])
    require(set(selected) == set(PERCPU) | set(GLOBALS) | {'__per_cpu_offset', '__pgtable_l5_enabled'},
            'incomplete original provider symbol set')
    return selected


def decode_timing(data):
    require(len(data) == 24*len(PHASES), 'timing ELF size differs')
    result = {}
    for i, name in enumerate(PHASES):
        samples, ns, invalid = struct.unpack_from('<qqi', data, 24*i)
        require(samples >= 0 and ns >= 0 and invalid == 0,
                'invalid or overflowing timing observation: '+name)
        result[name] = dict(samples=samples, ns=ns, invalid=invalid)
    return result


class Kcore:
    def __init__(self):
        from elftools.elf.elffile import ELFFile
        self.stream = open('/proc/kcore', 'rb')
        try:
            elf = ELFFile(self.stream)
            require(elf.elfclass == 64 and elf.little_endian and
                    elf['e_machine'] == 'EM_X86_64', 'unexpected kcore ELF')
            self.kernel_floor = 0xffff800000000000
            self.segments = [dict(address=s['p_vaddr'], size=s['p_memsz'],
                                  offset=s['p_offset'], file_size=s['p_filesz'])
                             for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
        except BaseException:
            self.stream.close()
            raise

    def read(self, address, size):
        require(0 < size <= 1024*1024 and self.kernel_floor <= address < 2**64-size,
                'invalid kernel observation extent')
        candidates = [s for s in self.segments if s['address'] <= address and
                      address+size <= s['address']+min(s['size'], s['file_size'])]
        require(len(candidates) == 1, 'ambiguous or unmapped kernel observation')
        segment = candidates[0]
        self.stream.seek(segment['offset']+address-segment['address'])
        data = self.stream.read(size)
        require(len(data) == size, 'short kernel observation read')
        return data

    def close(self):
        self.stream.close()

    def configure_paging(self, address):
        # Bootstrap from the fixed kernel-image mapping, valid in both modes.
        # Hardware LA57 support alone does not establish active five-level paging.
        enabled = int.from_bytes(self.read(address, 4), 'little')
        require(enabled in (0, 1), 'invalid live paging-mode flag')
        self.kernel_floor = 0xff00000000000000 if enabled else 0xffff800000000000
        return dict(flag_address=address, l5_enabled=enabled,
                    virtual_address_bits=57 if enabled else 48,
                    kernel_floor=self.kernel_floor)


class Snapshot:
    def __init__(self, provider, module='kdlock_km'):
        from elftools.elf.elffile import ELFFile
        self.module = module
        self.module_root = Path('/sys/module')/module
        self.provider_sha256 = hashlib.sha256(provider.read_bytes()).hexdigest()
        self.kallsyms = Path('/proc/kallsyms').read_text()
        self.symbols = parse_symbols(self.kallsyms, module)
        layouts, bases = {}, set()
        with provider.open('rb') as stream:
            elf = ELFFile(stream)
            require(elf.elfclass == 64 and elf.little_endian and elf['e_type'] == 'ET_REL'
                    and elf['e_machine'] == 'EM_X86_64', 'unexpected provider ELF')
            table = elf.get_section_by_name('.symtab')
            for name, size in (PERCPU | GLOBALS).items():
                matches = table.get_symbol_by_name(name) or []
                require(len(matches) == 1, 'missing or ambiguous ELF object: '+name)
                symbol = matches[0]
                require(symbol['st_info']['type'] == 'STT_OBJECT' and symbol['st_size'] == size
                        and isinstance(symbol['st_shndx'], int), 'ELF object size/type differs: '+name)
                section = elf.get_section(symbol['st_shndx'])
                offset = symbol['st_value']
                require(offset+size <= section['sh_size'], 'ELF object outside section')
                live = self.symbols[name]
                if name in PERCPU:
                    require(section.name == '.data..percpu' and live['kind'].lower() == 'a',
                            'unexpected per-CPU symbol: '+name)
                    bases.add(live['address']-offset)
                else:
                    require(section.name in ('.bss', '.data') and live['kind'].lower() in ('b', 'd'),
                            'unexpected global observation: '+name)
                    base = int((self.module_root/'sections'/section.name).read_text(), 16)
                    require(base+offset == live['address'], 'live global/ELF section mismatch: '+name)
                layouts[name] = dict(section=section.name, offset=offset, size=size, **live)
        require(len(bases) == 1 and next(iter(bases)) >= 0, 'inconsistent per-CPU relocation')
        self.layouts = layouts
        self.core = Kcore()
        try:
            self.paging = self.core.configure_paging(self.symbols['__pgtable_l5_enabled']['address'])
            require(Path('/sys/devices/system/cpu/possible').read_text().strip() == '0-63',
                    'original 64-CPU domain required')
            self.offsets = list(struct.unpack('<64Q', self.core.read(self.symbols['__per_cpu_offset']['address'], 512)))
            require(len(set(self.offsets)) == 64, 'nonunique CPU offsets')
            self.begin = min(self.symbols[n]['address'] for n in PERCPU)
            self.end = max(self.symbols[n]['address']+s for n,s in PERCPU.items())
            require(0 < self.end-self.begin <= 1024*1024, 'unbounded per-CPU observation range')
        except BaseException:
            self.core.close()
            raise

    def read(self):
        rows = []
        for cpu, offset in enumerate(self.offsets):
            data = self.core.read(offset+self.begin, self.end-self.begin)
            values = {n: int.from_bytes(data[self.symbols[n]['address']-self.begin:
                         self.symbols[n]['address']-self.begin+s], 'little') for n,s in PERCPU.items()}
            require(values['kd_mutex_active_waiters'] == values['kd_mutex_reserved_nodes'] == 0,
                    'workload did not reach a joined, idle boundary')
            rows.append(dict(cpu=cpu, values=values))
        global_bytes = {n:self.core.read(self.symbols[n]['address'], s) for n,s in GLOBALS.items()}
        totals = {n:sum(row['values'][n] for row in rows) for n in PERCPU}
        return dict(cpus=rows, totals=totals,
                    native={n:int.from_bytes(global_bytes[n], 'little') for n in GLOBALS if n.startswith('kd_native_')},
                    timing_enabled=bool(global_bytes['kd_jit_timing'][0]),
                    timings=decode_timing(global_bytes['kd_jit_times']))

    def capture(self):
        # The open pins the provider's data against teardown. It adds no writer
        # and closes before the collector's existing retire/unload operation.
        fd = os.open('/dev/kd_dev', os.O_RDONLY | os.O_CLOEXEC)
        try:
            began = time.monotonic_ns()
            first, second = self.read(), self.read()
            require(first == second, 'provider counters changed at quiescent boundary')
            first.update(started_ns=began, finished_ns=time.monotonic_ns())
            return first
        finally:
            os.close(fd)

    def receipt(self):
        return dict(provider_sha256=self.provider_sha256, layouts=self.layouts,
                    paging=self.paging,
                    per_cpu_offsets=self.offsets, per_cpu_offset_symbol=self.symbols['__per_cpu_offset'],
                    kcore_segments=self.core.segments,
                    kallsyms_sha256=hashlib.sha256(self.kallsyms.encode()).hexdigest(),
                    method='Read-only original counter bytes; two stable reads outside worker intervals')

    def close(self):
        self.core.close()


def difference(before, after):
    require(before['timing_enabled'] == after['timing_enabled'] and
            before['finished_ns'] <= after['started_ns'], 'observation identity or time order differs')
    counters = {n:after['totals'][n]-before['totals'][n] for n in PERCPU if n not in RESIDUAL}
    native = {n:after['native'][n]-before['native'][n] for n in before['native']}
    timings = {phase:{field:after['timings'][phase][field]-before['timings'][phase][field]
                      for field in ('samples','ns')} for phase in PHASES}
    require(all(v >= 0 for v in (*counters.values(), *native.values())) and
            all(v >= 0 for row in timings.values() for v in row.values()), 'counter decreased')
    return dict(counters=counters, native=native, timings=timings,
                scope='Joined measure command only; no warmup or later check call',
                limits='Inclusive timing intervals overlap and include instrumentation; never sum as wall time. '
                       'Hotlock entry/contention residuals reset and are not lifetime counters.')
