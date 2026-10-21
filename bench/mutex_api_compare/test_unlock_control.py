#!/usr/bin/env python3
"""VM-only negative audit checks against the actual original/derivative ELFs."""
import argparse
import io
from pathlib import Path
import struct
import tempfile

from elftools.elf.elffile import ELFFile
import unlock_control as control


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    control.require(not args.output.exists(), 'new audit receipt required')
    original = control.ORIGINAL/'baseline/pipecap'/control.BINARY
    control.elf_audit(original, False)
    result = control.elf_audit(args.candidate, True)
    data = args.candidate.read_bytes()
    elf = ELFFile(io.BytesIO(data))
    table = elf.get_section_by_name('.symtab')
    symbols = list(table.iter_symbols())

    def symbol_offset(name):
        selected = [i for i, symbol in enumerate(symbols) if symbol.name == name]
        assert len(selected) == 1
        return table['sh_offset']+selected[0]*table['sh_entsize']

    body = next(s for s in symbols if s.name == 'rb_body')
    section = elf.get_section(body['st_shndx'])
    edits = {
        'wrong-hot-rip': (symbol_offset('rb_entry')+8, '<Q',
                         next(s['st_value'] for s in symbols if s.name == 'rb_entry')+1),
        'wrong-mutex-size': (symbol_offset('kd_lock')+16, '<Q', 40),
        'unlock-capture-damaged': (section['sh_offset']+
            result['control_calls']['kd_mutex_direct_unlock_clobber_v1'][0]-14, '<B', 0x90),
    }
    with tempfile.TemporaryDirectory(prefix='kd-unlock-elf-negative-') as directory:
        for name, (offset, fmt, value) in edits.items():
            damaged = bytearray(data)
            struct.pack_into(fmt, damaged, offset, value)
            path = Path(directory)/(name+'.ko')
            path.write_bytes(damaged)
            try:
                control.elf_audit(path, True)
            except ValueError as error:
                print('PASS rejected', name, str(error))
            else:
                raise AssertionError('damaged ELF was accepted: '+name)
    print('PASS two actual ELF positives and three damaged-ELF rejections; no module loaded')
    control.save(args.output, dict(passed=True, original_sha256=control.sha(original),
        candidate_sha256=control.sha(args.candidate), auditor_sha256=control.sha(Path(control.__file__)),
        test_sha256=control.sha(Path(__file__)), rejected=list(edits), loaded=False))


if __name__ == '__main__':
    main()
