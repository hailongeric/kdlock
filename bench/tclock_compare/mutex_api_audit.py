"""Verify literal public spin/mutex/rwsem clobber continuations."""
from pathlib import Path

from elftools.elf.elffile import ELFFile


def audit_public_entries(binary, expected, *, lock_symbol='kd_mutex_direct_lock_clobber_v1',
                         unlock_symbol='kd_mutex_direct_unlock_clobber_v1',
                         integer_result=False):
    """Inspect relocatable x86-64 ELF, never infer an entry from source labels.

    The workload aliases the public clobber call's private numeric continuation. Require the
    exact emitted capture/CALL sequence and body extent before preparing it.
    Compiler changes that invalidate that observation must stop the run.
    """
    with Path(binary).open('rb') as stream:
        elf = ELFFile(stream)
        if elf['e_machine'] != 'EM_X86_64' or elf['e_type'] != 'ET_REL':
            raise ValueError('public clobber audit requires x86-64 relocatable ELF')
        symbols = elf.get_section_by_name('.symtab')
        if symbols is None:
            raise ValueError('public clobber audit requires symbols')
        result = {}
        for entry_name, body_name in expected.items():
            entries = symbols.get_symbol_by_name(entry_name) or []
            bodies = symbols.get_symbol_by_name(body_name) or []
            if len(entries) != 1 or len(bodies) != 1:
                raise ValueError('missing or ambiguous public entry/body: ' + entry_name)
            entry, body = entries[0], bodies[0]
            section = body['st_shndx']
            start, size = body['st_value'], body['st_size']
            address = entry['st_value']
            if (not isinstance(section, int) or entry['st_shndx'] != section
                    or not start < address < start + size
                    or body['st_info']['type'] != 'STT_FUNC'
                    or not elf.get_section(section)['sh_flags'] & 4):
                raise ValueError('public continuation outside its body: ' + entry_name)
            calls, unlocks = [], []
            for relocs in elf.iter_sections():
                if relocs['sh_type'] != 'SHT_RELA' or relocs['sh_info'] != section:
                    continue
                targets = elf.get_section(relocs['sh_link'])
                for relocation in relocs.iter_relocations():
                    offset = relocation['r_offset']
                    target = targets.get_symbol(relocation['r_info_sym']).name
                    if (start <= offset < start + size
                            and target == lock_symbol):
                        calls.append(relocation)
                    if (start <= offset < start + size
                            and target == unlock_symbol):
                        unlocks.append(relocation)
            if len(calls) != 1:
                raise ValueError('expected one public lock CALL: ' + entry_name)
            call = calls[0]
            offset = call['r_offset']
            code = elf.get_section(section).data()
            # mov rsp,rsi; lea after_call(%rip),rdx; mov rbp,rcx; call rel32.
            capture = bytes.fromhex('4889e6488d15080000004889e9e8')
            entry_delta = 4
            if integer_result:
                # Native CALL return jumps over XOR EAX,EAX; captured entry
                # starts at that explicit success-value definition.
                capture = bytes.fromhex('4889e6488d150a0000004889e9e8')
                entry_delta = 6
            if (call['r_info_type'] not in (2, 4) or call['r_addend'] != -4
                    or address != offset + entry_delta or offset - len(capture) < start
                    or code[offset-len(capture):offset] != capture
                    or code[offset:offset+4] != b'\0' * 4
                    or (integer_result and code[offset+4:offset+8] != b'\xeb\x02\x31\xc0')):
                raise ValueError('public continuation differs from captured RIP: ' + entry_name)
            if not unlocks or any(
                    unlock['r_info_type'] not in (2, 4) or unlock['r_addend'] != -4
                    or code[unlock['r_offset']-1:unlock['r_offset']] != b'\xe8'
                    for unlock in unlocks):
                raise ValueError('public body has no valid DIRECT unlock: ' + body_name)
            result[entry_name] = dict(body=body_name,
                section=elf.get_section(section).name, entry_offset=address,
                call_offset=offset-1, relocation_type=call['r_info_type'],
                unlock_offsets=[unlock['r_offset']-1 for unlock in unlocks])
            if integer_result:
                result[entry_name]['integer_result'] = True
        return result
