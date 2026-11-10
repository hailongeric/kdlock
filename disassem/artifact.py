"""Stateless assembly/C metadata export for one private constructed image.

This module writes no files, reads no source and performs no assembly, linking
or publication. The caller binds source_identity_symbol to its actual retained
source epoch object; a version string, manifest or generated descriptor supplies
no source/code hold. Final build symbol ownership, coherent publication and all
execution/return/source lifetimes remain caller responsibilities.
"""

from dataclasses import dataclass
import json
import re

from .coverage import EmissionReceipt, construct_emission_receipt
from .lowering import LoweredImage
from .source_decode import MASK64, MAX_INSTRUCTION_BYTES


_C_WORDS = frozenset({
    "alignas", "alignof", "asm", "auto", "bool", "break", "case", "char",
    "const", "constexpr", "continue", "default", "defined", "do", "double",
    "else", "enum", "extern", "false", "float", "for", "goto", "if",
    "inline", "int", "long", "nullptr", "register", "restrict", "return",
    "short", "signed", "sizeof", "static", "static_assert", "struct",
    "switch", "thread_local", "true", "typedef", "typeof", "typeof_unqual",
    "union", "unsigned", "void", "volatile", "while",
})
_UINT_MAX = (1 << 32) - 1


@dataclass(frozen=True)
class ArtifactSourceSite:
    """One retained source instruction, whether emitted or only classified."""

    ip: int
    next_ip: int
    kind: str
    raw: bytes


@dataclass(frozen=True)
class ImageArtifact:
    """Immutable construction output, never a published executable image.

    source_version_bytes uses strict UTF-8, without a synthetic trailing NUL.
    manifest_json is the serializable form of the exact construction receipt;
    receipt retains its frozen typed counterpart. Neither form is a runtime ACK.
    The assembly text is the original LoweredImage text, unchanged by export.
    """

    assembly: str
    c_metadata: str
    manifest_json: str
    source_version_bytes: bytes
    descriptor_symbol: str
    source_identity_symbol: str
    entry_symbol: str
    inputs_symbol: str
    entry_sites: tuple[int, ...]
    source_sites: tuple[ArtifactSourceSite, ...]
    receipt: EmissionReceipt


def _identifier(value: str) -> str:
    if (not isinstance(value, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z_0-9]*", value)
            or value in _C_WORDS):
        raise ValueError("artifact symbols need nonreserved ASCII C identifiers")
    return value


def _u64(value: int) -> int:
    if type(value) is not int or not 0 <= value <= MASK64:
        raise ValueError("artifact source addresses must be unsigned 64-bit integers")
    return value


def _c_uint(value: int, *, positive=False) -> int:
    if type(value) is not int or not (1 if positive else 0) <= value <= _UINT_MAX:
        raise ValueError("artifact value does not fit its unsigned int C field")
    return value


def _hex(value: int) -> str:
    return f"0x{value:016x}"


def _source_sites(image: LoweredImage) -> tuple[ArtifactSourceSite, ...]:
    sites = []
    for site, record in sorted(image.compilation.decoded.instructions.items()):
        _u64(site)
        if (record.site != site or not isinstance(record.raw, bytes)
                or not 1 <= len(record.raw) <= MAX_INSTRUCTION_BYTES
                or not isinstance(record.name, str) or not record.name):
            raise ValueError("retained instruction has inconsistent source identity")
        next_ip = _u64(record.next_site)
        if next_ip != ((site + len(record.raw)) & MASK64):
            raise ValueError("retained instruction has inconsistent next IP")
        # Graph clipping cannot erase a boundary CALL/JMP's actual source kind.
        # Dynamic CALLs retain this kind even without an observed ordinary target.
        kind = {"CALL": "KD_JIT_SITE_CALL", "JMP": "KD_JIT_SITE_JUMP"}.get(
            record.name.upper(), "KD_JIT_SITE_OTHER"
        )
        sites.append(ArtifactSourceSite(site, next_ip, kind, record.raw))
    _c_uint(len(sites))
    return tuple(sites)


def _c_metadata(image, descriptor, identity, symbols, sites, version):
    entries, source_table, version_data, version_length, byte_table, inputs = symbols[:6]
    raw_symbols = symbols[6:]
    declarations = (descriptor, identity, image.entry.symbol, *symbols)
    text = [
        "/* Constructed metadata only; source/code retention and publication are caller-owned. */\n",
        '#include "kernel/image_inputs.h"\n\n',
    ]
    # An identifier can still name a macro in the caller's build environment.
    # Diagnose that collision instead of allowing declaration/initializer rewriting.
    for symbol in declarations:
        text.append(f'#ifdef {symbol}\n#error "artifact symbol collides with a macro"\n#endif\n')
    text.extend([
        "\nstruct kd_jit_source_epoch;\n",
        f"extern struct kd_jit_source_epoch {identity};\n",
        f"extern void {image.entry.symbol}(struct kd_regs *, struct kd_jit_io *);\n\n",
        f'_Static_assert(KD_JIT_ABI_VERSION == {image.abi_version}U, "constructed image ABI");\n',
        f'_Static_assert(sizeof(struct kd_regs) == {image.packet_size}U, "constructed packet size");\n',
        f'_Static_assert(sizeof(struct kd_jit_io) == {image.io_size}U, "constructed IO size");\n\n',
        f"const unsigned char {version_data}[] = {{\n",
    ])
    for offset in range(0, len(version), 16):
        text.append("\t" + ", ".join(f"0x{value:02x}" for value in version[offset:offset + 16]) + ",\n")
    text.extend([
        "};\n",
        f"const unsigned long {version_length} = {len(version)}UL;\n\n",
        f"static const unsigned long {entries}[] = {{\n",
    ])
    text.extend(f"\t{_hex(site)}UL,\n" for site in image.entry.entry_sites)
    text.append("};\n\n")
    if sites:
        text.append(f"static const struct kd_jit_source_site {source_table}[] = {{\n")
        text.extend(
            f"\t{{ .ip = {_hex(site.ip)}UL, .next_ip = {_hex(site.next_ip)}UL, .kind = {site.kind} }},\n"
            for site in sites
        )
        text.append("};\n\n")
        for site, symbol in zip(sites, raw_symbols):
            raw = ", ".join(f"0x{value:02x}" for value in site.raw)
            text.append(f"static const unsigned char {symbol}[] = {{ {raw} }};\n")
        text.append(f"\nstatic const struct kd_jit_image_source_bytes {byte_table}[] = {{\n")
        text.extend(
            f"\t{{ .ip = {_hex(site.ip)}UL, .bytes = {symbol}, .length = {len(site.raw)}U }},\n"
            for site, symbol in zip(sites, raw_symbols)
        )
        text.append("};\n\n")
    text.extend([
        f"const struct kd_jit_image {descriptor} = {{\n",
        f"\t.source_identity = &{identity},\n",
        f"\t.abi_version = {image.abi_version}U,\n",
        f"\t.packet_size = {image.packet_size}U,\n",
        f"\t.io_size = {image.io_size}U,\n",
        f"\t.entry = {image.entry.symbol},\n",
        f"\t.entry_sites = {entries},\n",
        f"\t.entry_count = {len(image.entry.entry_sites)}U,\n",
        f"\t.source_sites = {source_table if sites else 'NULL'},\n",
        f"\t.source_count = {len(sites)}U,\n",
        "};\n\n",
        f"const struct kd_jit_image_inputs {inputs} = {{\n",
        f"\t.image = &{descriptor},\n",
        f"\t.source_version = {version_data},\n",
        f"\t.source_version_length = sizeof({version_data}),\n",
        f"\t.current_task_gs_offset = {_hex(image.entry.current_task_gs_offset)}UL,\n",
        f"\t.source_bytes = {byte_table if sites else 'NULL'},\n",
        f"\t.source_count = {len(sites)}U,\n",
        "};\n",
    ])
    return "".join(text)


def export_image(image: LoweredImage, *, descriptor_symbol: str,
                 source_identity_symbol: str) -> ImageArtifact:
    """Return coordinated source strings and immutable construction metadata.

    The external identity is an object of the caller-defined opaque tag
    struct kd_jit_source_epoch, not an exported version string or generated
    token. The caller defines that exact object/type and retains its actual
    source epoch through every image/source/return user. Artifact-local symbol
    collisions and reserved C spellings are rejected; generated C diagnoses
    macro collisions. Unique ownership in the final build remains caller-owned.
    """
    if not isinstance(image, LoweredImage):
        raise TypeError("artifact export needs one constructed LoweredImage")
    if (not isinstance(image.assembly, str)
            or image.source_version != image.compilation.snapshot.version):
        raise ValueError("constructed assembly and source version are inconsistent")
    descriptor = _identifier(descriptor_symbol)
    identity = _identifier(source_identity_symbol)
    entry = _identifier(image.entry.symbol)
    sites = _source_sites(image)
    symbols = tuple(_identifier(descriptor + suffix) for suffix in (
        "_entry_sites", "_source_sites", "_source_version", "_source_version_length",
        "_source_bytes", "_inputs",
        *(f"_source_bytes_{index}" for index in range(len(sites))),
    ))
    all_symbols = (descriptor, identity, entry, *symbols)
    if len(set(all_symbols)) != len(all_symbols):
        raise ValueError("artifact function, descriptor, identity and data symbols must differ")
    for value in (image.abi_version, image.packet_size, image.io_size):
        _c_uint(value, positive=True)
    if (not isinstance(image.entry.entry_sites, tuple) or not image.entry.entry_sites
            or len(set(image.entry.entry_sites)) != len(image.entry.entry_sites)):
        raise ValueError("artifact entry sites must be a nonempty unique tuple")
    _c_uint(len(image.entry.entry_sites), positive=True)
    for site in image.entry.entry_sites:
        _u64(site)
    _u64(image.entry.current_task_gs_offset)
    if not isinstance(image.source_version, str) or not image.source_version:
        raise ValueError("artifact source version must be a nonempty string")
    try:
        version = image.source_version.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ValueError("source version has no strict UTF-8 byte representation") from error
    receipt = construct_emission_receipt(image)
    observations = [
        {
            "site": _hex(observed.site), "target": _hex(observed.target),
            "kind": observed.kind.value, "emission_outcome": outcome.value,
            "planner_outcome": image.compilation.observation_outcomes[observed].value,
        }
        for observed, outcome in sorted(
            receipt.outcomes.items(),
            key=lambda pair: (pair[0].site, pair[0].kind.value, pair[0].target),
        )
    ]
    manifest = {
        "format": "kdlock_private_image_construction_v1",
        "descriptor_symbol": descriptor,
        "source_identity_symbol": identity,
        "entry_symbol": entry,
        "data_symbols": {
            "entry_sites": symbols[0], "source_sites": symbols[1] if sites else None,
            "source_version": symbols[2], "source_version_length": symbols[3],
            "source_bytes": symbols[4] if sites else None,
            "inputs": symbols[5], "source_byte_records": list(symbols[6:]),
        },
        "source_version": {"encoding": "utf-8", "bytes_hex": version.hex(), "length": len(version)},
        "abi_version": image.abi_version,
        "packet_size": image.packet_size,
        "io_size": image.io_size,
        "current_task_gs_offset": _hex(image.entry.current_task_gs_offset),
        "entry_sites": [_hex(site) for site in image.entry.entry_sites],
        "entry_count": len(image.entry.entry_sites),
        "source_count": len(sites),
        "source_sites": [
            {"ip": _hex(site.ip), "next_ip": _hex(site.next_ip), "kind": site.kind,
             "bytes_hex": site.raw.hex(), "length": len(site.raw)}
            for site in sites
        ],
        "emission_receipt": {
            "construction_only": True, "runtime_ack": False,
            "source_version_bytes_hex": version.hex(), "entry_symbol": receipt.entry_symbol,
            "observations": observations,
            "emitted_observations": [
                {"site": _hex(observed.site), "target": _hex(observed.target),
                 "kind": observed.kind.value}
                for observed in sorted(
                    receipt.emitted_observations,
                    key=lambda observed: (observed.site, observed.kind.value, observed.target),
                )
            ],
        },
        "emitted_sites": [_hex(site) for site in sorted(image.emitted_sites)],
        "refused_sites": [{"ip": _hex(site), "reason": reason}
                          for site, reason in sorted(image.refused_sites.items())],
        "boundaries": [
            {"ip": _hex(boundary.site), "kind": boundary.kind.value,
             "control_kind": boundary.control_kind, "bytes_hex": boundary.raw.hex(),
             "exit_label": boundary.exit_label}
            for boundary in image.boundaries
        ],
        "limits": {
            "lowered_sites": image.limits.lowered_sites,
            "lowered_text_bytes": image.limits.lowered_text_bytes,
            "runtime_block_visits": image.limits.runtime_block_visits,
        },
        "construction_consumption": {"attempted_sites": image.attempted_sites,
                                     "lowered_text_bytes": image.lowered_text_bytes},
    }
    return ImageArtifact(
        assembly=image.assembly,
        c_metadata=_c_metadata(image, descriptor, identity, symbols, sites, version),
        manifest_json=json.dumps(manifest, ensure_ascii=True, sort_keys=True, indent=2),
        source_version_bytes=version,
        descriptor_symbol=descriptor,
        source_identity_symbol=identity,
        entry_symbol=entry,
        inputs_symbol=symbols[5],
        entry_sites=image.entry.entry_sites,
        source_sites=sites,
        receipt=receipt,
    )
