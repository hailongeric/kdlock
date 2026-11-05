"""Require complete allocated bytes before extracting an unlinked JIT object."""

from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection


def require_complete_object(path):
    """Raw objcopy does not apply even defined-symbol ELF relocations.

    Debug sections and zero-filled storage contribute no stored image bytes.
    Inspect every allocated section with contents, including data/metadata.
    """
    with open(path, "rb") as stream:
        elf = ELFFile(stream)
        if (elf.elfclass != 64 or elf["e_machine"] != "EM_X86_64" or
                elf["e_type"] != "ET_REL"):
            raise ValueError("expected an x86-64 relocatable JIT object")
        for section in elf.iter_sections():
            if not isinstance(section, RelocationSection):
                continue
            target = elf.get_section(section["sh_info"])
            if (not target["sh_flags"] & 2 or target["sh_type"] == "SHT_NOBITS" or
                    not target["sh_size"]):
                continue
            symbols = elf.get_section(section["sh_link"])
            for relocation in section.iter_relocations():
                symbol = symbols.get_symbol(relocation["r_info_sym"])
                raise ValueError(
                    f"incomplete JIT object: {section.name} at "
                    f"{relocation['r_offset']:#x} targets emitted {target.name}; "
                    f"unapplied relocation for {symbol.name or '<section>'}")
