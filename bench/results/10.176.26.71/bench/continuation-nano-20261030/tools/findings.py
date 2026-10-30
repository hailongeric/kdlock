#!/usr/bin/env python3
"""Read completed comparison JSON and ELF data; never execute inspected inputs."""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path

from elftools.elf.elffile import ELFFile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def profile(row):
    return f"{row['lock_kind']} {row['workload']} w{row['write_percent']}"


def counts(rows):
    return dict(points=len(rows), whole_losses=sum(r['metrics']['whole']['observed_loss'] for r in rows),
                peak_losses=sum(r['metrics']['peak']['observed_loss'] for r in rows),
                either_losses=sum(r['any_observed_loss'] for r in rows),
                whole_loss_ge_5_percent=sum(r['metrics']['whole']['change_pct'] <= -5 for r in rows))


def loss_bin(change):
    if change >= 0:
        return 'no_loss'
    magnitude = -change
    if magnitude < 1:
        return 'under_1_percent'
    if magnitude < 5:
        return '1_to_under_5_percent'
    if magnitude < 10:
        return '5_to_under_10_percent'
    return '10_percent_or_more'


def elf_data(path):
    with path.open('rb') as stream:
        elf = ELFFile(stream)
        sections = list(elf.iter_sections())
        def section_id(index):
            return sections[index].name if isinstance(index, int) else index
        allocated = {}
        for section in sections:
            if section['sh_flags'] & 2:
                allocated[section.name] = dict(type=section['sh_type'], flags=section['sh_flags'],
                    size=section['sh_size'], alignment=section['sh_addralign'],
                    sha256=None if section['sh_type'] == 'SHT_NOBITS' else sha(section.data()))
        relocations = {}
        for section in sections:
            if section['sh_type'] not in ('SHT_RELA', 'SHT_REL'):
                continue
            target = sections[section['sh_info']]
            if not target['sh_flags'] & 2:
                continue
            table = sections[section['sh_link']]
            rows = []
            for relocation in section.iter_relocations():
                symbol = table.get_symbol(relocation['r_info_sym'])
                rows.append(dict(offset=relocation['r_offset'], type=relocation['r_info_type'],
                    addend=relocation.entry.get('r_addend'), symbol=dict(name=symbol.name,
                    section=section_id(symbol['st_shndx']), value=symbol['st_value'], size=symbol['st_size'],
                    bind=symbol['st_info']['bind'], type=symbol['st_info']['type'],
                    visibility=symbol['st_other']['visibility'])))
            relocations[target.name] = rows
        return dict(file=str(path), sha256=sha(path.read_bytes()), allocated_sections=allocated,
                    allocated_relocations=relocations)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--unit-provider', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    validation = load(args.audit / 'validation.json')
    assert validation['completed'] and validation['validated'] and validation['current_points'] == 210
    source_receipts = {}
    summaries = {}
    flattened = []
    for baseline in ('acfa', '8446'):
        source = args.audit / f'vs-{baseline}' / 'points.json'
        source_receipts[str(source)] = sha(source.read_bytes())
        rows = load(source)
        assert len(rows) == 210 and all(r['rounds_per_point'] == 1 for r in rows)
        assert len({(r['lock_kind'], r['workload'], r['write_percent'], r['threads']) for r in rows}) == 210
        assert all(r['score_eligible'] and not r['performance_accepted'] for r in rows)
        s = counts(rows)
        s['whole_loss_magnitude_bins'] = dict(collections.Counter(loss_bin(r['metrics']['whole']['change_pct']) for r in rows))
        s['profiles'] = {p: counts([r for r in rows if profile(r) == p]) for p in sorted({profile(r) for r in rows})}
        s['workers'] = {str(n): counts([r for r in rows if r['threads'] == n]) for n in sorted({r['threads'] for r in rows})}
        s['worker_cohorts'] = {label: counts([r for r in rows if lower <= r['threads'] <= upper])
            for label, lower, upper in [('1-8', 1, 8), ('12-32', 12, 32), ('36-60', 36, 60)]}
        s['execution_transitions'] = {p: counts([r for r in rows if r['execution_transition'] == p])
            for p in sorted({r['execution_transition'] for r in rows})}
        summaries[baseline] = s
        for row in rows:
            item = dict(baseline=baseline, profile=profile(row), workers=row['threads'],
                whole_change_pct=row['metrics']['whole']['change_pct'], peak_change_pct=row['metrics']['peak']['change_pct'],
                any_observed_loss=row['any_observed_loss'], transition=row['execution_transition'],
                whole_loss_bin=loss_bin(row['metrics']['whole']['change_pct']))
            for side, key in [('reference', 'reference_kd'), ('current', 'current_kd')]:
                for field in ['whole_ops_s', 'peak_ops_s', 'jit_entries', 'jit_completions', 'jit_entry_share', 'jit_completion_share']:
                    item[f'{side}_{field}'] = row[key][field]
            flattened.append(item)
    for name, selected in [('all-points', flattened),
            ('workers-20-32-60', [r for r in flattened if r['workers'] in [20, 32, 60]]),
            ('whole-losses-at-least-5-percent', [r for r in flattened if r['whole_change_pct'] <= -5]),
            ('changed-execution-class', [r for r in flattened if len(set(r['transition'].split(' -> '))) > 1])]:
        with (args.out / f'{name}.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(flattened[0]))
            writer.writeheader()
            writer.writerows(selected)
    save(args.out / 'measured-summary.json', summaries)
    unit = elf_data(args.unit_provider)
    provenance = load(args.audit / 'current/elf-provenance.json')
    comparisons = []
    for key, record in provenance.items():
        if not key.endswith('/provider/kernel_module/kdlock_km.ko'):
            continue
        current = elf_data(Path(record['file']))
        assert current['sha256'] == record['sha256']
        current_alloc, unit_alloc = current['allocated_sections'], unit['allocated_sections']
        assert set(current_alloc) == set(unit_alloc)
        differences = [name for name in current_alloc if current_alloc[name] != unit_alloc[name]]
        executable = [name for name, data in current_alloc.items() if data['flags'] & 4]
        relocation_equal = current['allocated_relocations'] == unit['allocated_relocations']
        comparisons.append(dict(profile=key.split('/')[0], file=current['file'], sha256=current['sha256'],
            executable_sections=executable, executable_sections_equal=all(current_alloc[name] == unit_alloc[name] for name in executable),
            allocated_section_differences=differences, allocated_relocations_equal=relocation_equal,
            allocated_relocation_count=sum(map(len, current['allocated_relocations'].values())),
            text=current_alloc['.text']))
        assert all(current_alloc[name] == unit_alloc[name] for name in executable)
        assert differences == ['.note.gnu.build-id'] and relocation_equal
    assert len(comparisons) == 10
    save(args.out / 'actual-provider-identity.json', dict(unit_file=unit['file'], unit_sha256=unit['sha256'],
        unit_allocated_sections=unit['allocated_sections'],
        unit_allocated_relocation_sha256=sha(json.dumps(unit['allocated_relocations'], sort_keys=True).encode()),
        unit_allocated_relocation_count=sum(map(len, unit['allocated_relocations'].values())), profiles=comparisons,
        full_file_identity_claimed=False, runtime_load_address_identity_claimed=False))
    source_receipts[str(args.audit / 'current/elf-provenance.json')] = sha((args.audit / 'current/elf-provenance.json').read_bytes())
    source_receipts[str(args.audit / 'validation.json')] = sha((args.audit / 'validation.json').read_bytes())
    save(args.out / 'findings-receipt.json', dict(completed=True, operation='read-only completed-data and ELF inspection',
        arguments={k: str(v) for k, v in vars(args).items()}, tool_sha256=sha(Path(__file__).read_bytes()), inputs=source_receipts,
        outputs={p.name: sha(p.read_bytes()) for p in args.out.iterdir() if p.is_file() and p.name != 'findings-receipt.json'},
        builds=False, tests=False, artifact_execution=False, vm_actions=False, performance_accepted=False))
    print(json.dumps(dict(completed=True, comparisons={k: {x: v[x] for x in ['points', 'whole_losses', 'peak_losses', 'either_losses']} for k, v in summaries.items()}, provider_count=len(comparisons))))


if __name__ == '__main__':
    main()
