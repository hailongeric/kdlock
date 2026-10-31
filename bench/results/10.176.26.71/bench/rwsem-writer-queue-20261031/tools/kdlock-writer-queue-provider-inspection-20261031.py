#!/usr/bin/env python3
"""Read measured ELF bytes and compare bounded instruction listings offline."""
import argparse
import difflib
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile
import time

from elftools.elf.elffile import ELFFile
from elftools.elf.descriptions import describe_reloc_type

COMMITS = {'baseline': 'f7a84065e84474380faa37eeadfdf534abd72a68',
           'candidate': '1b6f256b13e8743aa1fd7bdc958cc82ae7726463'}
SELECTED = ('mutex-throughput', 'rwsem-throughput-read', 'rwlock-throughput-read')
PREFIXES = ('kd_down_read', 'kd_up_read', 'kd_down_write', 'kd_up_write',
            'kd_downgrade_write', 'kd_rwsem_', 'kd_local_', 'kd_try_common',
            'kd_owner', 'kd_mutex_local_', 'kd_mutex_osq_', 'osq_',
            'kd_mutex_lock_killable', 'kd_mutex_lock_interruptible', 'kd_mutex_trylock',
            '__kd_mutex_lock_slowpath', 'kd_mutex_run_combiner',
            'kd_spin_', '_kd_spin_', '__kd_spin_', 'run_combiner')


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def checked(path, expected):
    need(sha(path) == expected, 'input differs: ' + str(path))
    return json.loads(Path(path).read_bytes())


def inventory(data):
    elf = ELFFile(io.BytesIO(data))
    need(elf['e_type'] == 'ET_REL' and elf['e_machine'] == 'EM_X86_64', 'expected x86-64 relocatable ELF')
    symbols = elf.get_section_by_name('.symtab')
    functions, relocs, sections = {}, {}, {}
    for index, section in enumerate(elf.iter_sections()):
        if section['sh_flags'] & 4:
            sections[section.name] = dict(index=index, bytes=section['sh_size'], alignment=section['sh_addralign'],
                                          sha256=digest(section.data()))
        if section['sh_type'] not in ('SHT_RELA', 'SHT_REL'):
            continue
        target = elf.get_section(section['sh_info'])
        if not target['sh_flags'] & 4:
            continue
        table = elf.get_section(section['sh_link'])
        rows = relocs.setdefault(target.name, [])
        for relocation in section.iter_relocations():
            symbol = table.get_symbol(relocation['r_info_sym'])
            symbol_section = elf.get_section(symbol['st_shndx']).name if isinstance(symbol['st_shndx'], int) else symbol['st_shndx']
            rows.append(dict(offset=relocation['r_offset'], type=describe_reloc_type(relocation['r_info_type'], elf),
                             symbol=symbol.name or symbol_section, symbol_type=symbol['st_info']['type'],
                             symbol_value=symbol['st_value'], addend=relocation['r_addend'] if relocation.is_RELA() else None))
    for symbol in symbols.iter_symbols():
        if symbol['st_info']['type'] != 'STT_FUNC' or not symbol['st_size'] or not isinstance(symbol['st_shndx'], int):
            continue
        name = symbol.name
        need(name not in functions, 'ambiguous defined function: ' + name)
        section = elf.get_section(symbol['st_shndx'])
        start, size = symbol['st_value'], symbol['st_size']
        body = section.data()[start:start + size]
        need(len(body) == size, 'truncated function: ' + name)
        rows = [dict(row, offset=row['offset'] - start) for row in relocs.get(section.name, [])
                if start <= row['offset'] < start + size]
        functions[name] = dict(section=section.name, offset=start, size=size, raw_sha256=digest(body), relocations=rows)
    return dict(elf_sha256=digest(data), bytes=len(data), sections=sections, functions=functions)


def disassemble(path, info, out, workload=False):
    text = subprocess.check_output(['objdump', '-d', '-r', '-w', '-z', str(path)], text=True, timeout=60)
    (out / 'objdump.txt').write_text(text)
    data = path.read_bytes()
    elf = ELFFile(io.BytesIO(data))
    sections = {section.name: section.data() for section in elf.iter_sections() if section['sh_flags'] & 4}
    instructions = {}
    section = None
    for line in text.splitlines():
        header = re.fullmatch(r'Disassembly of section (.+):', line)
        if header:
            section = header[1]
            continue
        match = re.fullmatch(r'\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*(\S.*)', line)
        if not match:
            continue
        address, raw, instruction = int(match[1], 16), bytes.fromhex(match[2]), match[3]
        # -w can append one or more relocation listings on the instruction row.
        instruction = re.split(r'\s+[0-9a-f]+:\s+R_X86_64_', instruction, maxsplit=1)[0].rstrip()
        need(section in sections and sections[section][address:address + len(raw)] == raw,
             'disassembly row differs from ELF bytes')
        need((section, address) not in instructions, 'duplicate instruction address')
        instructions[(section, address)] = dict(address=address, bytes=raw.hex(), instruction=instruction)
    selected = {}
    for name, function in info['functions'].items():
        if not workload and not name.startswith(PREFIXES):
            continue
        begin, end = function['offset'], function['offset'] + function['size']
        rows = [dict(row) for (section, address), row in instructions.items()
                if section == function['section'] and begin <= address < end]
        rows.sort(key=lambda row: row['address'])
        need(rows and rows[0]['address'] == begin and
             all(row['address'] + len(bytes.fromhex(row['bytes'])) == next_row['address'] for row, next_row in zip(rows, rows[1:])) and
             rows[-1]['address'] + len(bytes.fromhex(rows[-1]['bytes'])) == end,
             'function instruction coverage differs: ' + name)
        normalized = []
        for row in rows:
            offset, length = row['address'] - begin, len(bytes.fromhex(row['bytes']))
            relative = [dict(r, offset=r['offset'] - offset) for r in function['relocations']
                        if offset <= r['offset'] < offset + length]
            instruction = row['instruction']
            branch = re.fullmatch(r'((?:bnd\s+)?(?:callq?|jmpq?|j[a-z]+|loop[a-z]*))\s+([0-9a-f]+)\s+<([^>]+)>', instruction)
            if branch:
                target = int(branch[2], 16)
                if relative:
                    instruction = branch[1] + ' <encoded-relocation>'
                elif begin <= target < end:
                    instruction = branch[1] + ' <self+0x' + format(target - begin, 'x') + '>'
                else:
                    instruction = branch[1] + ' <' + branch[3] + '>'
            if relative:
                # Only objdump's calculated address comment is omitted. Actual
                # operands and every relocation target/addend stay separate.
                instruction = re.sub(r'\s+#\s+[0-9a-f]+\s+<[^>]+>$', '', instruction)
            row.update(offset=offset, relocations=relative)
            semantic_relocations = [{key: value for key, value in relocation.items() if key != 'symbol_value'}
                                    for relocation in relative]
            normalized.append(dict(instruction=instruction, relocations=semantic_relocations))
        encoded = json.dumps(normalized, sort_keys=True, separators=(',', ':')).encode()
        selected[name] = dict(function, instruction_count=len(rows), instruction_only_sha256=digest(encoded),
                              normalized=normalized, instructions=rows,
                              locked_operations=[row for row in rows if re.search(r'\block\s+', row['instruction'])])
    save(out / 'selected-functions.json', selected)
    return selected


def capture(args):
    arm = checked(args.arm_json, args.arm_sha256)
    transfer_path = args.arm_json.parent / 'transfer.json'
    transfer = checked(transfer_path, args.transfer_sha256)
    commit = COMMITS[args.label]
    need(transfer.get('completed') is True and transfer.get('transport_verified') is True and
         transfer.get('source_commit') == commit and transfer['analysis_arm_sha256'] == args.arm_sha256,
         'actual completed source-specific transfer required')
    directory = Path(arm['archives'])
    metadata = checked(directory / 'archives.json', arm['archives_sha256'])
    owner = checked(Path(arm['control']) / 'owner.json', arm['owner_sha256'])
    need(metadata['completed'] and metadata['guest_idle'] and owner['completed'] and owner['idle'] and
         owner['source_commit'] == commit and owner['validated_points'] == 210, 'completed KD210 arm required')
    need(not args.output.exists(), 'new output directory required')
    args.output.mkdir(parents=True)
    receipt = dict(completed=False, label=args.label, commit=commit, started=time.time(), artifact_execution=False,
                   vm_actions=False, tests=False, performance_accepted=False, tool_sha256=sha(__file__),
                   inputs=dict(arm_path=str(args.arm_json), arm_sha256=args.arm_sha256,
                               transfer_path=str(transfer_path), transfer_sha256=args.transfer_sha256,
                               archive_index_sha256=arm['archives_sha256'], owner_sha256=arm['owner_sha256']), profiles={})
    save(args.output / 'capture.json', receipt)
    try:
        for group in metadata['groups']:
            if group['group'] == 'metadata':
                continue
            profile = group['group']
            archive_path = directory / group['file']
            need(sha(archive_path) == group['sha256'] and archive_path.stat().st_size == group['bytes'], 'compressed group differs')
            prefix = metadata['archive_prefix'] + '/' + profile + '/'
            wanted, binary_map = {}, None
            with tarfile.open(archive_path, 'r|gz') as archive:
                for member in archive:
                    if not member.name.startswith(prefix) or not member.isfile():
                        continue
                    suffix = member.name[len(prefix):]
                    if suffix == 'binary-sha256.json':
                        binary_map = json.loads(archive.extractfile(member).read())
                    elif suffix == 'build/provider/kernel_module/kdlock_km.ko' or suffix.endswith('/rwlock_bench.ko'):
                        need(member.name not in wanted, 'duplicate selected module')
                        wanted[member.name] = archive.extractfile(member).read()
            need(binary_map is not None and len(wanted) == 2, 'one actual provider/workload pair required')
            record = dict(archive_group=group['file'], archive_sha256=group['sha256'], artifacts={})
            for member, data in wanted.items():
                relative = member[len(metadata['archive_prefix']) + 1:]
                original = metadata['guest_base'] + '/' + relative
                need(binary_map.get(original) == digest(data), 'ELF differs from measured binary map')
                kind = 'provider' if member.endswith('/kdlock_km.ko') else 'workload'
                info = inventory(data)
                target = args.output / profile
                target.mkdir(exist_ok=True)
                save(target / (kind + '-inventory.json'), info)
                artifact = dict(sha256=digest(data), bytes=len(data), member=member,
                                inventory=str((target / (kind + '-inventory.json')).relative_to(args.output)))
                if profile in SELECTED:
                    sub = target / kind
                    sub.mkdir()
                    path = sub / (kind + '.ko')
                    path.write_bytes(data)
                    selected = disassemble(path, info, sub, workload=kind == 'workload')
                    artifact.update(elf=str(path.relative_to(args.output)), selected=str((sub / 'selected-functions.json').relative_to(args.output)),
                                    selected_functions=len(selected))
                record['artifacts'][kind] = artifact
            receipt['profiles'][profile] = record
        need(len(receipt['profiles']) == 10 and set(SELECTED) <= set(receipt['profiles']), 'all ten provider profiles required')
        need(sha(transfer_path) == args.transfer_sha256 and sha(args.arm_json) == args.arm_sha256,
             'original receipt changed during offline capture')
        receipt.update(completed=True, finished=time.time(), files={str(path.relative_to(args.output)): sha(path)
                       for path in args.output.rglob('*') if path.is_file() and path != args.output / 'capture.json'})
    except BaseException as error:
        receipt.update(error=repr(error), finished=time.time())
        raise
    finally:
        save(args.output / 'capture.json', receipt)
    print(json.dumps(dict(completed=True, profiles=len(receipt['profiles']), output=str(args.output))))


def compare(args):
    before = checked(args.baseline / 'capture.json', args.baseline_sha256)
    after = checked(args.candidate / 'capture.json', args.candidate_sha256)
    need(before['completed'] and after['completed'] and before['commit'] == COMMITS['baseline'] and
         after['commit'] == COMMITS['candidate'] and before['tool_sha256'] == after['tool_sha256'] == sha(__file__),
         'two completed captures from this tool required')
    need(not args.output.exists(), 'new comparison output required')
    args.output.mkdir(parents=True)
    comparisons = {}
    for profile in SELECTED:
        for kind in ('provider', 'workload'):
            values = []
            for root, receipt in ((args.baseline, before), (args.candidate, after)):
                relative = receipt['profiles'][profile]['artifacts'][kind]['selected']
                values.append(checked(root / relative, receipt['files'][relative]))
            old, new = values
            rows = {}
            for name in sorted(old.keys() | new.keys()):
                left, right = old.get(name), new.get(name)
                row = dict(before_present=left is not None, after_present=right is not None)
                if left is not None and right is not None:
                    row.update(before_size=left['size'], after_size=right['size'], before_offset=left['offset'], after_offset=right['offset'],
                               raw_equal=left['raw_sha256'] == right['raw_sha256'], relocations_equal=left['relocations'] == right['relocations'],
                               instruction_only_equal=left['instruction_only_sha256'] == right['instruction_only_sha256'])
                    if not row['instruction_only_equal']:
                        def lines(body):
                            return [json.dumps(item, sort_keys=True) + '\n' for item in body['normalized']]
                        directory = args.output / profile / kind
                        directory.mkdir(parents=True, exist_ok=True)
                        (directory / (name + '.diff')).write_text(''.join(difflib.unified_diff(lines(left), lines(right), fromfile='baseline/' + name, tofile='candidate/' + name)))
                rows[name] = row
            comparisons[profile + '/' + kind] = rows
    save(args.output / 'comparison.json', dict(completed=True, baseline_sha256=args.baseline_sha256,
         candidate_sha256=args.candidate_sha256, comparisons=comparisons, artifact_execution=False,
         performance_accepted=False, limits='Instruction/layout evidence only; no path-frequency or performance-cause claim.'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    selected = commands.add_parser('capture')
    selected.add_argument('--label', choices=COMMITS, required=True)
    selected.add_argument('--arm-json', type=Path, required=True)
    selected.add_argument('--arm-sha256', required=True)
    selected.add_argument('--transfer-sha256', required=True)
    selected.add_argument('--output', type=Path, required=True)
    paired = commands.add_parser('compare')
    for name in ('baseline', 'candidate', 'output'):
        paired.add_argument('--' + name, type=Path, required=True)
    for name in ('baseline-sha256', 'candidate-sha256'):
        paired.add_argument('--' + name, required=True)
    args = parser.parse_args()
    capture(args) if args.action == 'capture' else compare(args)


if __name__ == '__main__':
    main()
