#!/usr/bin/env python3
"""Read-only, independently scheduled owner-byte observations of original ELFs.

The module references protect the observed storage, not acquisition or teardown
authority. Only the retained collector's joined replies and retirement protocol
permit teardown. Neither a sampled byte nor a timeout establishes drain.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import select
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
RECORD = struct.Struct('<QQQB7x')  # intended deadline, pread bracket, byte
CAPACITY = 16384
CPU = 62
MAX_SECONDS = 15


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def offset_for(core, address):
    require(core.kernel_floor <= address < 2**64, 'non-kernel sample address')
    matches = [s for s in core.segments if s['address'] <= address <
               s['address']+min(s['size'], s['file_size'])]
    require(len(matches) == 1, 'ambiguous or unmapped sample byte')
    value = matches[0]['offset']+address-matches[0]['address']
    require(0 <= value < 2**63, 'sample byte outside signed pread offset')
    return value


def bind_object(path, module, name, size, symbols):
    from elftools.elf.elffile import ELFFile
    matches = [v for line in symbols.splitlines() if
               len(v := line.split()) == 4 and v[2:] == [name, '['+module+']']]
    require(len(matches) == 1, 'missing or ambiguous live object: '+name)
    live = int(matches[0][0], 16)
    with path.open('rb') as stream:
        elf = ELFFile(stream)
        require(elf.elfclass == 64 and elf.little_endian and
                elf['e_machine'] == 'EM_X86_64' and elf['e_type'] == 'ET_REL', 'unexpected module ELF')
        objects = elf.get_section_by_name('.symtab').get_symbol_by_name(name) or []
        require(len(objects) == 1, 'missing or ambiguous ELF object: '+name)
        obj = objects[0]
        require(obj['st_size'] == size and obj['st_info']['type'] == 'STT_OBJECT'
                and isinstance(obj['st_shndx'], int), 'object size/type differs: '+name)
        section = elf.get_section(obj['st_shndx'])
        require(section.name in ('.bss', '.data') and matches[0][1].lower() in ('b', 'd')
                and obj['st_value']+size <= section['sh_size'], 'unexpected object section')
        base = int((Path('/sys/module')/module/'sections'/section.name).read_text(), 16)
        require(base+obj['st_value'] == live, 'ELF/live section binding differs')
        return dict(name=name, module=module, address=live, size=size,
                    section=section.name, section_base=base, offset=obj['st_value'],
                    elf_sha256=sha(path))


def receive(fd, buffer, timeout):
    """Unbuffered protocol read; a deadline never kills a child or proves drain."""
    deadline = time.monotonic()+timeout
    while b'\n' not in buffer:
        left = deadline-time.monotonic()
        require(left > 0, 'sampler control deadline expired; drain unknown')
        if select.select([fd], [], [], min(left, .1))[0]:
            piece = os.read(fd, 4096)
            require(piece, 'sampler control closed before acknowledgement')
            buffer += piece
            require(len(buffer) <= 65536, 'unbounded sampler control response')
    line, buffer = buffer.split(b'\n', 1)
    return json.loads(line), buffer


def child(config_path):
    import route_snapshot
    config = json.loads(config_path.read_text())
    out = config_path.parent
    require(os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
            and Path('/proc/sys/kernel/random/boot_id').read_text().strip() == config['boot_id'],
            'sampler requires the original recovery VM')
    require(config['mode'] in ('reference', 'sampled'), 'unknown sampler mode')
    os.sched_setaffinity(0, {CPU})
    require(os.sched_getaffinity(0) == {CPU}, 'sampler affinity differs')
    buffer = bytearray(CAPACITY*RECORD.size)
    count, missed, pins, core = 0, 0, [], None
    receipt = dict(state='STARTING', mode=config['mode'], seed=config['seed'],
                   cpu=CPU, pid=os.getpid(), record_format=RECORD.format,
                   capacity=CAPACITY, accepted=False)
    try:
        # Both fops have THIS_MODULE owners; the workload control device has
        # no open/release callbacks. No ioctl or admission mutation is issued.
        for device in ('/dev/kd_dev', '/dev/real_api_control'):
            pins.append(os.open(device, os.O_RDONLY | os.O_CLOEXEC))
        symbols = Path('/proc/kallsyms').read_text()
        (out/'owner-kallsyms.txt').write_text(symbols)
        provider, workload = Path(config['provider']), Path(config['workload'])
        require(sha(provider) == config['provider_sha256'] and
                sha(workload) == config['workload_sha256'], 'original ELF identity differs')
        owner = bind_object(workload, 'real_api', 'kd_lock', 32, symbols)
        reference = bind_object(provider, 'kdlock_km', 'kd_jit_timing', 1, symbols)
        exported = int(Path('/sys/module/real_api/parameters/lock_addr').read_text())
        require(owner['address'] == exported == config['lock_addr'] and exported % 64 == 32,
                'owner storage/live parameter/collector address differ')
        core = route_snapshot.Kcore()
        parsed = route_snapshot.parse_symbols(symbols)
        paging = core.configure_paging(parsed['__pgtable_l5_enabled']['address'])
        address = owner['address']+7 if config['mode'] == 'sampled' else reference['address']
        file_offset = offset_for(core, address)
        fd = core.stream.fileno()
        # pread is intentionally independent of the ELF parser's buffered
        # stream; repeated buffered reads could return stale owner bytes.
        require(os.pread(fd, 1, offset_for(core, reference['address'])) == b'\0',
                'inclusive timing must remain disabled')
        require(os.pread(fd, 1, offset_for(core, owner['address']+7)) == b'\0',
                'owner was held before the joined measurement')
        save(out/'owner-binding.json', dict(owner=owner, reference=reference,
             address=address, file_offset=file_offset, paging=paging,
             kcore_segments=core.segments, config=config,
             kallsyms_sha256=hashlib.sha256(symbols.encode()).hexdigest()))
        print(json.dumps(dict(state='READY', pid=os.getpid())), flush=True)
        command, pending = receive(0, b'', 10)
        require(command == {'command': 'START'} and not pending, 'unexpected start command')
        rng = random.Random(config['seed'])
        start = time.monotonic_ns(); cpu_start = time.process_time_ns()
        receipt.update(started_ns=start, process_cpu_started_ns=cpu_start)
        deadline = start+rng.randrange(250000, 1750001)
        print(json.dumps(dict(state='RUNNING', started_ns=start)), flush=True)
        while True:
            now = time.monotonic_ns()
            require(now-start < MAX_SECONDS*10**9, 'sampler reached its fixed safety duration')
            if select.select([0], [], [], max(0, (deadline-now)/1e9))[0]:
                command, pending = receive(0, pending, 1)
                require(command == {'command': 'STOP'} and not pending, 'unexpected stop command')
                break
            require(count < CAPACITY, 'sample buffer overflow')
            began = time.monotonic_ns()
            value = os.pread(fd, 1, file_offset)
            ended = time.monotonic_ns()
            if len(value) != 1 or value[0] not in ((0, 255) if config['mode'] == 'sampled' else (0,)):
                receipt['invalid_read'] = dict(deadline_ns=deadline, started_ns=began,
                                               finished_ns=ended, bytes_hex=value.hex())
            require(len(value) == 1 and value[0] in ((0, 255) if config['mode'] == 'sampled' else (0,)),
                    'short or invalid owner/reference observation')
            RECORD.pack_into(buffer, count*RECORD.size, deadline, began, ended, value[0])
            count += 1
            deadline += rng.randrange(250000, 1750001)
            # Retain missed independent deadlines; never replace them with a
            # burst of back-to-back reads correlated with scheduler delays.
            while deadline <= ended:
                missed += 1
                deadline += rng.randrange(250000, 1750001)
        receipt.update(state='COMPLETE', stopped_ns=time.monotonic_ns(),
                       process_cpu_ns=time.process_time_ns()-cpu_start)
    except BaseException as error:
        receipt.update(state='FAILED', error=repr(error), stopped_ns=time.monotonic_ns())
        raise
    finally:
        if core is not None:
            core.close()
        for fd in reversed(pins):
            os.close(fd)
        receipt.update(samples=count, missed_deadlines=missed, pins_closed=True,
                       finished_ns=time.monotonic_ns())
        (out/'owner-samples.bin').write_bytes(memoryview(buffer)[:count*RECORD.size])
        receipt['samples_sha256'] = sha(out/'owner-samples.bin')
        save(out/'owner-process.json', receipt)
    print(json.dumps(dict(state='STOPPED', samples=count, pins_closed=True)), flush=True)


class Sampler:
    def __init__(self, session, script):
        self.session, self.script = session, script
        self.process = self.log = None
        self.pending = b''

    def expect(self, state):
        reply, self.pending = receive(self.process.stdout.fileno(), self.pending, 10)
        require(reply.get('state') == state, 'unexpected sampler state: '+repr(reply))
        return reply

    def prepare(self):
        s = self.session
        config = dict(mode=s.record['owner_mode'],
            seed=int.from_bytes(hashlib.sha256(s.record['name'].encode()).digest()[:8], 'little'),
            boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            provider=str(s.out/'build/kdlock_km.ko'), workload=str(s.workload_module),
            provider_sha256=sha(s.out/'build/kdlock_km.ko'), workload_sha256=sha(s.workload_module),
            lock_addr=s.record['lock_addr'], publication=s.record['published_before'])
        path = s.path/'owner-config.json'; save(path, config)
        self.log = (s.path/'owner-process.stderr').open('wb')
        argv = [sys.executable, '-B', str(self.script), '--child', str(path)]
        self.process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.log, bufsize=0, start_new_session=True)
        s.record['owner_process'] = dict(pid=self.process.pid, command=argv)
        s.save()
        self.expect('READY')

    def start(self):
        self.process.stdin.write(b'{"command":"START"}\n')
        self.expect('RUNNING')

    def finish(self):
        if self.process is None:
            return
        # A child that failed during preparation closes pins in its finally.
        # Closing stdin also lets a live child report a failed control exchange.
        try:
            if self.process.poll() is None:
                try:
                    self.process.stdin.write(b'{"command":"STOP"}\n')
                    self.expect('STOPPED')
                finally:
                    self.process.stdin.close()
            rc = self.process.wait(timeout=20)
            self.session.record['owner_process']['exit_code'] = rc
            self.session.save()
            require(rc == 0, 'sampler failed; inspect preserved process receipt')
            result = json.loads((self.session.path/'owner-process.json').read_text())
            require(result['state'] == 'COMPLETE' and result['pins_closed'], 'sampler did not close pins')
        finally:
            if self.process.poll() is not None:
                self.log.close()
                self.process.stdout.close()
                if not self.process.stdin.closed:
                    self.process.stdin.close()


def analyze(data, process, measured, delta, mode):
    """Estimate occupancy only when exact phase counters prove a local path."""
    require(len(data) % RECORD.size == 0 and process['samples'] == len(data)//RECORD.size
            and hashlib.sha256(data).hexdigest() == process['samples_sha256'], 'sample extent/hash differs')
    rows = list(RECORD.iter_unpack(data))
    begin, end = measured['started_ns'], measured['finished_ns']
    require(process['state'] == 'COMPLETE' and process['pins_closed'] and
            process['started_ns'] <= begin < end <= process['stopped_ns'] and
            end-begin == measured['wall_ns'] and measured['completed'] > 0,
            'sampling/measurement clocks or lifecycle differ')
    require(all(d <= a <= b and v in ((0,255) if mode == 'sampled' else (0,))
                for d,a,b,v in rows) and
            all(x[2] <= y[1] and x[0] < y[0] for x,y in zip(rows,rows[1:])), 'invalid sample sequence')
    inside = [(d,a,b,v) for d,a,b,v in rows if begin <= a <= b <= end]
    require(len(inside) >= 1000, 'insufficient measured sample coverage')
    counters = delta['counters']
    zeros = ('kd_bench_bodies','kd_bench_completions','kd_mutex_slowpath_count',
             'kd_mutex_origin_acquires','kd_mutex_origin_releases',
             'kd_mutex_nested_lock_count','kd_mutex_handoff_count')
    local = all(counters[n] == 0 for n in zeros) and not any(delta['native'].values())
    occupied = sum(v == 255 for _,_,_,v in inside)
    n, p = len(inside), occupied/len(inside)
    # Wilson bounds are explicitly conditional on independent samples. Blocks
    # below and schedule losses expose reasons that assumption may be false.
    z = 1.959963984540054
    center=(p+z*z/(2*n))/(1+z*z/n)
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    scale = measured['wall_ns']/measured['completed']
    blocks=[]
    for i in range(10):
        values=[v for _,a,b,v in inside if (a-begin)*10//(end-begin) == i]
        blocks.append(dict(index=i, samples=len(values), occupied=sum(v == 255 for v in values)))
    def distribution(values):
        values=sorted(values)
        return dict(min=values[0], median=values[len(values)//2],
                    p95=values[math.ceil(.95*len(values))-1], max=values[-1])
    return dict(mode=mode, local_only=local, local_zero_counters={n:counters[n] for n in zeros},
        native=delta['native'], samples=n, occupied=occupied, fraction=p,
        outside_or_boundary_samples=len(rows)-n, blocks=blocks,
        missed_deadlines=process['missed_deadlines'],
        read_ns=distribution([b-a for _,a,b,_ in inside]),
        lateness_ns=distribution([a-d for d,a,_,_ in inside]),
        gap_ns=distribution([y[1]-x[1] for x,y in zip(inside,inside[1:])]),
        estimated_mean_hold_ns=p*scale if local and mode == 'sampled' else None,
        iid_only_wilson95_hold_ns=[(center-half)*scale,(center+half)*scale]
            if local and mode == 'sampled' else None,
        process_cpu_ns=process['process_cpu_ns'], accepted=False,
        limits='Occupancy estimate, not per-acquisition timestamps or p95 latency. '
               'IID bounds ignore temporal dependence, missed schedules and read perturbation.')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child', type=Path, required=True)
    child(parser.parse_args().child)
