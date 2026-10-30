#!/usr/bin/env python3
"""Offline ELF/DWARF/disassembly inspection; never execute an input artifact."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess

from elftools.elf.elffile import ELFFile

BASE = '8617e97c02432a7c0b931aa8263d5edd0f6eb5b8'
CURRENT = 'f7a84065e84474380faa37eeadfdf534abd72a68'
BASE_SHA = 'e602695d23676fa0e05f467ff92e23abe25b373d2f8792449af23d679f02c33d'
RWSEM = ['kd_down_read', 'kd_down_read_interruptible', 'kd_down_read_killable',
         'kd_down_read_trylock', 'kd_down_read_non_owner', 'kd_up_read',
         'kd_up_read.part.0', 'kd_up_read_non_owner', 'kd_down_write',
         'kd_down_write_interruptible', 'kd_down_write_killable',
         'kd_down_write_trylock', 'kd_up_write', 'kd_downgrade_write',
         'kd_rwsem_drain_readers', 'kd_rwsem_write_release',
         'kd_rwsem_delegate_enter', 'kd_rwsem_delegate_exit',
         'kd_rwsem_down_write_clobber_v1']
NAMES = RWSEM + ['run_combiner', '__kd_mutex_lock_slowpath',
                'kd_mutex_run_combiner', 'kd_mutex_execute_cs',
                '_kd_mutex_lock_abi', 'kd_exe_dispatch', 'kd_exe_dispatch.cold']
TYPES = ['kd_spin_batch', 'kd_spin_node', 'kd_mutex_node', 'kd_mutex', 'kd_exec_frame']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def command(argv):
    return subprocess.check_output(argv, text=True, timeout=60)


def inspect(path, label, out):
    result = dict(path=str(path), sha256=sha(path.read_bytes()), sections={}, functions={},
                  types={name: [] for name in TYPES}, members={}, layout={}, witness={})
    listings, normalized = {}, {}
    with path.open('rb') as stream:
        elf = ELFFile(stream)
        assert elf['e_type'] == 'ET_REL' and elf['e_machine'] == 'EM_X86_64'
        for section in elf.iter_sections():
            if section.name.startswith('.text'):
                result['sections'][section.name] = dict(size=section['sh_size'], sha256=sha(section.data()))
        for symbol in elf.get_section_by_name('.symtab').iter_symbols():
            if symbol.name in NAMES and symbol['st_info']['type'] == 'STT_FUNC' and isinstance(symbol['st_shndx'], int):
                assert symbol.name not in result['functions']
                section = elf.get_section(symbol['st_shndx'])
                start, size = symbol['st_value'] - section['sh_addr'], symbol['st_size']
                result['functions'][symbol.name] = dict(offset=symbol['st_value'], size=size,
                    section=section.name, raw_sha256=sha(section.data()[start:start+size]))
    assert set(result['functions']) == set(NAMES), 'missing/ambiguous expected function'
    dwarf = command(['readelf', '--debug-dump=info', str(path)])
    blocks = re.split(r'(?m)^(?= <\d+><[0-9a-f]+>: Abbrev Number:)', dwarf)
    for i, block in enumerate(blocks):
        if '(DW_TAG_structure_type)' not in block:
            continue
        name = re.search(r'DW_AT_name\s*:[^\n]*?\b(' + '|'.join(TYPES) + r')\s*$', block, re.M)
        size = re.search(r'DW_AT_byte_size\s*:\s*(\d+)', block)
        if not name or not size:
            continue
        name, size = name.group(1), int(size.group(1))
        if size not in result['types'][name]:
            result['types'][name].append(size)
        if name not in ['kd_spin_batch', 'kd_mutex_node']:
            continue
        depth = int(re.match(r' <(\d+)>', block).group(1))
        members = {}
        for child in blocks[i+1:]:
            match = re.match(r' <(\d+)>', child)
            if match and int(match.group(1)) <= depth:
                break
            if '(DW_TAG_member)' not in child:
                continue
            member = re.search(r'DW_AT_name\s*:[^\n]*?\b([A-Za-z_][A-Za-z_0-9]*)\s*$', child, re.M)
            location = re.search(r'DW_AT_data_member_location\s*:\s*(\d+)', child)
            if member and location:
                members[member.group(1)] = int(location.group(1))
        if name in result['members']:
            assert result['members'][name] == members
        result['members'][name] = members
    assert all(len(sizes) == 1 for sizes in result['types'].values()), 'ambiguous/missing DWARF type'
    for name, row in result['functions'].items():
        listing = command(['objdump', '-d', '--no-show-raw-insn', '--disassemble=' + name, str(path)])
        (out / f'{label}-{name}.dis').write_text(listing)
        lines = []
        for line in listing.splitlines():
            match = re.match(r'^\s*([0-9a-f]+):\s+(.*)$', line)
            if match:
                lines.append(dict(address=int(match.group(1), 16), instruction=match.group(2).rstrip()))
        listings[name] = lines
        normalized[name] = '\n'.join(re.sub(r'\b[0-9a-f]+(?=\s+<)', '', x['instruction']).rstrip() for x in lines) + '\n'
        row.update(instruction_count=len(lines), normalized_sha256=sha(normalized[name].encode()))
    for name in ['run_combiner', '__kd_mutex_lock_slowpath']:
        (out / f'{label}-{name}.relocations-lines.dis').write_text(command([
            'objdump', '-drl', '--no-show-raw-insn', '--disassemble=' + name, str(path)]))
    spin = listings['run_combiner']
    result['layout']['stack_subtractions'] = [x for x in spin if re.match(r'sub\s+\$0x[0-9a-f]+,%rsp$', x['instruction'])]
    result['layout']['rep_initialization_windows'] = [spin[max(0, i-5):i+2] for i, x in enumerate(spin) if x['instruction'].startswith('rep stos')]
    # Locate only the simple load/test/Jcc shape. Preserve all matches for review;
    # do not infer source identity from a bare numeric offset alone.
    offset = result['members']['kd_mutex_node']['native_resume']
    mutex = listings['__kd_mutex_lock_slowpath']
    matches = []
    for i in range(len(mutex)-2):
        load, test, branch = mutex[i:i+3]
        if (re.match(r'movzbl\s+0x' + format(offset, 'x') + r'\([^)]*\),%eax$', load['instruction'])
                and re.match(r'test\s+%al,%al$', test['instruction'])
                and re.match(r'j(e|ne)\s', branch['instruction'])):
            zero_fallthrough = bool(re.match(r'jne\s', branch['instruction']))
            matches.append(dict(load=load, test=test, branch=branch,
                zero_falls_through=zero_fallthrough, surrounding=mutex[max(0, i-4):i+8]))
    result['witness']['native_resume_zero_branches'] = matches
    result['witness']['native_resume_zero_fallthrough'] = matches[0]['zero_falls_through'] if len(matches) == 1 else None
    result['witness']['generic_dispatch_windows'] = [spin[max(0, i-5):i+38] for i, x in enumerate(spin)
        if re.search(r'\bcall\s+[0-9a-f]+\s+<execute_cs(?:[.+][^>]*)?>', x['instruction'])]
    result['witness']['context_refresh_control_flow'] = 'Manual review required using relocation/source-line listing and generic-dispatch windows; no automatic semantic pass.'
    return result, normalized


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--candidate-sha256', required=True)
    parser.add_argument('--baseline', type=Path, default=Path('/tmp/kdlock-continuation-8617e97c-provider.ko'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    assert re.fullmatch('[0-9a-f]{64}', args.candidate_sha256)
    assert not args.out.exists(), 'fresh output directory required'
    args.out.mkdir(parents=True)
    receipt = dict(completed=False, base_commit=BASE, candidate_commit=CURRENT,
        tool_sha256=sha(Path(__file__).read_bytes()), arguments={k: str(v) for k, v in vars(args).items()},
        scope='Built provider static inspection; source identity supplied by parent build receipt, not inferred from ELF.',
        artifact_execution=False, vm_actions=False, tests=False, performance_accepted=False)
    save(args.out / 'inspection-receipt.json', receipt)
    try:
        assert sha(args.baseline.read_bytes()) == BASE_SHA, 'baseline bytes changed'
        assert sha(args.candidate.read_bytes()) == args.candidate_sha256, 'candidate bytes differ from parent receipt'
        old, old_normal = inspect(args.baseline, '8617e97c', args.out)
        new, new_normal = inspect(args.candidate, 'f7a84065', args.out)
        comparisons = {}
        for name in NAMES:
            before, after = old['functions'][name], new['functions'][name]
            comparisons[name] = dict(old_size=before['size'], new_size=after['size'],
                same_raw_bytes=before['raw_sha256'] == after['raw_sha256'],
                same_normalized_instructions=before['normalized_sha256'] == after['normalized_sha256'])
            (args.out / f'8617e97c-to-f7a84065-{name}.normalized.diff').write_text(''.join(
                difflib.unified_diff(old_normal[name].splitlines(True), new_normal[name].splitlines(True),
                                    fromfile='8617e97c/' + name, tofile='f7a84065/' + name)))
        report = dict(baseline=old, candidate=new, comparison=comparisons,
            rwsem_functions=RWSEM, rwsem_all_raw_equal=all(comparisons[x]['same_raw_bytes'] for x in RWSEM),
            rwsem_all_normalized_equal=all(comparisons[x]['same_normalized_instructions'] for x in RWSEM))
        save(args.out / 'comparison.json', report)
        receipt['completed'] = True
        receipt['output_sha256'] = {p.name: sha(p.read_bytes()) for p in args.out.iterdir() if p.name != 'inspection-receipt.json'}
        print(json.dumps(dict(completed=True, candidate_sha256=new['sha256'],
            mutex_zero_fallthrough=new['witness']['native_resume_zero_fallthrough'],
            spin_batch_bytes=new['types']['kd_spin_batch'], rwsem_all_raw_equal=report['rwsem_all_raw_equal'],
            context_refresh_manual_review_required=True)))
    except BaseException as error:
        receipt['error'] = repr(error)
        raise
    finally:
        save(args.out / 'inspection-receipt.json', receipt)


if __name__ == '__main__':
    main()
