#!/usr/bin/env python3
"""Render audited nano receipts on the source host; never run an oracle or workload."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sys

sys.dont_write_bytecode = True
ROOT = Path('/home/eric/vm/vm-shared/kdlock')
COMMIT = '6d8c8be736ecfc23e1470e3256ee51d6e16e666e'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True,
                        help='Public compact report directory copied from the successful guest audit')
    parser.add_argument('--plot-input', type=Path, required=True,
                        help='Ignored raw plot-input directory copied from the guest audit output')
    args = parser.parse_args()
    report = args.report.resolve(strict=True)
    inputs = args.plot_input.resolve(strict=True)
    require(socket.gethostname().lower() == '380g10', 'Render only on the designated source host')
    require(report.is_relative_to(ROOT / 'bench/results/10.176.26.71/bench') and
            inputs.is_relative_to(ROOT / 'bench/results/10.176.26.71/raw'),
            'Use the public compact-report and ignored raw-input locations')
    audit_path = report / 'audit.json'
    audit = read(audit_path)
    require(audit['passed'] is True and not audit['errors'] and
            audit['guest_idle_after_report'] is True, 'Guest audit did not pass and drain')
    require(audit['source_commit'] == COMMIT and audit['planned'] ==
            audit['valid_measurements'] == audit['valid_warmups'] == 630 and
            len(audit['profiles']) == 10 and audit['repetitions_per_point'] == 1,
            'Audit source or coverage differs')
    require(audit['graphical_rendering'] == 'pending_source_host',
            'This renderer consumes the explicit guest audit-only handoff')
    receipt_path = report / 'plot-receipt.json'
    require(not receipt_path.exists(), 'Retain the existing plotting attempt; do not overwrite it')
    profiles = audit['profiles']
    require(len({p['workload'] for p in profiles}) == 10 and
            len({p['source_directory'] for p in profiles}) == 10,
            'Duplicate audited workloads')
    for profile in profiles:
        original, concrete = profile['source_directory'], profile['workload']
        require(Path(original).name == original and Path(concrete).name == concrete,
                'Invalid profile path')
        source = inputs / original
        require(sha(source / 'plan.json') == profile['plan_sha256'] and
                sha(source / 'records.json') == profile['records_sha256'],
                'Plot inputs differ from guest-audited receipts: ' + original)
        require(not (report / concrete).exists(), 'Existing output must be retained: ' + concrete)
    receipt = dict(schema=1, completed=False, host=socket.gethostname(),
                   python=sys.executable, source_commit=COMMIT,
                   audit_sha256=sha(audit_path), input_directory=str(inputs),
                   rendering_scope=('Offline plotting of copied, successfully guest-audited receipts. '
                                    'No oracle, unit test, build, module, workload, or timing execution.'),
                   helper_sha256=sha(Path(__file__)),
                   renderer_sha256=sha(ROOT / 'bench/catalog_single/report.py'), profiles=[])
    save(receipt_path, receipt)
    (report / 'render-helper.py').write_bytes(Path(__file__).read_bytes())
    try:
        import matplotlib
        receipt['matplotlib_version'] = matplotlib.__version__
        renderer_path = ROOT / 'bench/catalog_single/report.py'
        spec = importlib.util.spec_from_file_location('nano_offline_renderer', renderer_path)
        catalog = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(catalog)
        for profile in profiles:
            original, concrete = profile['source_directory'], profile['workload']
            source = inputs / original
            title = (f"{profile['lock'].capitalize()} c{profile['cachelines']:02d}, "
                     f"{profile['write_percent']}% writes, post256")
            rows = catalog.render(source, report / concrete, title, False, exploratory=True)
            require(len(rows) == 63 and all(r['whole_mops_s'] is not None for r in rows),
                    'Renderer output differs from audited coverage: ' + concrete)
            outputs = [report / concrete / name for name in
                       ('README.md', 'table.csv', 'throughput.png', 'throughput.svg')]
            receipt['profiles'].append(dict(workload=concrete,
                input_hashes={name: sha(source / name) for name in ('plan.json', 'records.json')},
                outputs={str(p.relative_to(report)): dict(bytes=p.stat().st_size, sha256=sha(p))
                         for p in outputs}))
            save(receipt_path, receipt)
        require(sha(audit_path) == receipt['audit_sha256'], 'Guest audit changed during rendering')
        for profile in profiles:
            source = inputs / profile['source_directory']
            require(sha(source / 'plan.json') == profile['plan_sha256'] and
                    sha(source / 'records.json') == profile['records_sha256'],
                    'Plot input changed during rendering')
        overview = report / 'README.md'
        pending = ('Chart rendering is pending on the source host. After rendering, each workload link '
                   'provides its complete worker grid and PNG/SVG chart; the separate plot-receipt.json '
                   'records rendering completion and exact input/output hashes. ')
        text = overview.read_text()
        require(pending in text, 'Overview does not contain the expected pending-plot disclosure')
        overview.write_text(text.replace(pending,
            'Each workload link provides its complete worker grid and PNG/SVG chart. '
            '[Plot receipt](plot-receipt.json) records offline rendering completion, '
            'the matplotlib version and exact input/output hashes. ', 1))
        receipt.update(completed=True, overview_sha256=sha(overview),
                       scope_note='Guest audit.json remains unchanged; graphical completion is recorded here')
        save(receipt_path, receipt)
        print(json.dumps(dict(completed=True, profiles=len(profiles),
                              matplotlib=matplotlib.__version__, report=str(report)), sort_keys=True))
    except BaseException as error:
        receipt['error'] = repr(error)
        save(receipt_path, receipt)
        raise


if __name__ == '__main__':
    main()
