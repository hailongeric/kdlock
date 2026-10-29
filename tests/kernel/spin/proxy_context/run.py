#!/usr/bin/env python3
"""Ordinary spin root-context positives, local contexts and mixed-IF stress."""
import fcntl
import importlib.util
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
_shared = Path(__file__).resolve().parent.parent/'address_guard/run.py'
_spec = importlib.util.spec_from_file_location('spin_context_shared_session', _shared)
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)
probe.DEVICE = '/dev/kd_spin_proxy_context'
probe.WORKER_COMM = 'kctx_worker'
probe.RUNNER = 'tests/kernel/spin/proxy_context'
probe.PAYLOAD = probe.RUNNER+'/payload'
probe.MODULE = 'kd_spin_proxy_context_test'
probe.CAP_VERSIONS, probe.CAP_BIT, probe.IMAGE_REQUIREMENT = (12,), 6, 0
probe.SUCCESS_MESSAGE = ('PASS: ordinary IF-on/off returned delegation; homogeneous BH/RCU/preempt/migration local; '
                         'mixed-IF stress only; exact effects/state and source drain')
BIND, MODE = 0x40084505, 0x40044504
PHASES = (('if-on',0,'delegated'), ('if-off',1,'delegated'),
          ('bh-local',2,'local'), ('rcu-local',3,'local'),
          ('preempt-local',4,'local'), ('migration-local',5,'local'),
          ('mixed-if-stress',6,'stress'), ('if-on-final',0,'delegated'))


def ordinary_entry(module):
    """Resolve the actual ordinary macro CALL, never a nearby C/assembly label."""
    from elftools.elf.elffile import ELFFile
    from elftools.elf.relocation import RelocationSection
    with Path(module).open('rb') as stream:
        elf = ELFFile(stream)
        probe.rt.require(elf.elfclass == 64 and elf['e_machine'] == 'EM_X86_64', 'x86-64 payload required')
        symbols = elf.get_section_by_name('.symtab')
        functions = symbols.get_symbol_by_name('proxy_body') or []
        ends = symbols.get_symbol_by_name('proxy_body_end') or []
        probe.rt.require(len(functions) == len(ends) == 1, 'one ordinary body and end marker required')
        function, end = functions[0], ends[0]
        section_index = function['st_shndx']
        begin, size = function['st_value'], function['st_size']
        probe.rt.require(function['st_info']['type'] == 'STT_FUNC' and isinstance(section_index,int) and
                         end['st_shndx'] == section_index and begin < end['st_value'] < begin+size,
                         'invalid ordinary body bounds')
        data = elf.get_section(section_index).data()
        candidates, calls = [], []
        for section in elf.iter_sections():
            if not isinstance(section,RelocationSection) or section['sh_info'] != section_index:
                continue
            linked = elf.get_section(section['sh_link'])
            for relocation in section.iter_relocations():
                offset = relocation['r_offset']
                if not begin < offset < end['st_value']:
                    continue
                symbol = linked.get_symbol(relocation['r_info_sym'])
                if relocation['r_info_type'] in (2,4) and data[offset-1] == 0xe8:
                    calls.append((offset+4-begin, symbol.name))
                if symbol.name != 'kd_spin_lock_clobber_v1':
                    continue
                probe.rt.require(relocation['r_info_type'] in (2,4) and relocation['r_addend'] == -4 and
                                 data[offset-1] == 0xe8 and offset+4 < end['st_value'],
                                 'ordinary acquisition is not the expected direct CALL')
                candidates.append(offset+4-begin)
        probe.rt.require(len(candidates) == 1, 'one actual ordinary acquisition CALL required')
        after_lock = [(offset,name) for offset,name in calls if offset > candidates[0]]
        probe.rt.require(len(after_lock) == 1 and after_lock[0][1] == 'kd_spin_unlock_clobber_v1',
                         'positive body has an unexpected native helper CALL')
        return dict(return_offset=candidates[0], body_end_offset=end['st_value']-begin,
                    body_size=size, payload_sha256=probe.rt.digest(Path(module)),
                    symbol='kd_spin_lock_clobber_v1', caller_shell='ordinary-source-macro',
                    unlock_return_offset=after_lock[0][0], source_body_helper_calls=0)


def phase_result(delta, expected):
    bodies, completed = delta['bench_jit_bodies'], delta['bench_jit_completions']
    probe.rt.require(delta['address_guard_count'] == 0 and bodies == completed and bodies >= 0,
                     'unexpected native escape or unmatched body completion', 'DATA_ERROR')
    if expected == 'delegated':
        probe.rt.require(bodies > 0, 'positive context has no returned delegated body', 'NO_JIT')
    elif expected == 'local':
        probe.rt.require(bodies == 0, 'preexisting context unexpectedly delegated', 'DATA_ERROR')
    else:
        probe.rt.require(expected == 'stress', 'unknown phase oracle')
    return dict(expected=expected, returned_delegated_bodies=completed,
                mismatch_refusal_proved=False)


class ContextSession(probe.EscapeSession):
    def prepare(self):
        probe.rt.require(8 <= len(self.record['cpus']) <= 60 and
                         1 <= self.record['iterations'] <= 4096 and
                         1 <= self.record['warmup_iterations'] <= 1000000,
                         '8..60 CPUs, <=4096 context operations and bounded ordinary warmup required')
        super().prepare()

    def counts(self, label):
        if label == 'initial':
            initial = probe.snapshot()
            binding = ordinary_entry(self.workload_module)
            probe.rt.require(initial['marker']-initial['entry'] == binding['body_end_offset'],
                             'loaded ordinary function bounds differ from ELF')
            selected = initial['entry']+binding['return_offset']
            with open(probe.DEVICE,'rb',buffering=0) as device:
                fcntl.ioctl(device,BIND,struct.pack('=Q',selected))
            self.record['ordinary_call_binding'] = dict(binding, function=initial['entry'], entry=selected,
                                                         end=initial['marker'])
            self.save()
        return super().counts(label)

    def measure(self):
        self.record['execution_status']='MEASURING'
        warmup = self.phase('ordinary-warmup',self.record['warmup_iterations'],0)
        warmup['context_oracle']=phase_result(warmup['jit_delta'],'delegated')
        for name,mode,expected in PHASES:
            with open(probe.DEVICE,'rb',buffering=0) as device:
                fcntl.ioctl(device,MODE,struct.pack('=I',mode))
            row=self.phase(name,self.record['iterations'],mode)
            row['context_oracle']=phase_result(row['jit_delta'],expected)
            probe.rt.require(self.registry(name,0)==self.record['image_registry'] and
                             self.publication()==self.record['publication'], 'immutable root image changed')
            self.save()
        self.record.update(jit_status='IF_MATCHED_COMPLETE_AND_LOCAL_CONTEXTS',escape_events=[],accepted=True,
                           mixed_if_scope='stress only; deterministic mismatch proof belongs to production unit fixture',
                           final_parameters=probe.rt.parameters())
        self.verify()


probe.EscapeSession=ContextSession


def main():
    if len(sys.argv)>1 and sys.argv[1]=='--worker':
        return probe.main()
    # Keep the shared source freeze/build/retire implementation. Short context
    # phases restore IRQ/BH/RCU/preempt/migration state after EVERY operation.
    for option,value in (('--iterations','2048'),('--warmup-iterations','32768'),('--phase-timeout','60')):
        if not any(arg == option or arg.startswith(option+'=') for arg in sys.argv[1:]):
            sys.argv.extend((option,value))
    return probe.main()


if __name__=='__main__':
    raise SystemExit(main())
