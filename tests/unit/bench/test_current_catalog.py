"""Guest-only current-catalog coverage and output-isolation checks."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('current_catalog_test', ROOT/'bench/catalog_single/current_plan.py')
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


class CatalogTests(unittest.TestCase):
    def test_active_nano_and_original_catalog_are_complete_and_isolated(self):
        destination = '/root/kdlock-evidence/10.176.26.71/bench/catalog-test'
        rows = list(catalog.commands(destination))
        self.assertEqual(len(rows), 61)
        self.assertEqual(len({name for name, _ in rows}), 61)
        historical = catalog.load('original_catalog_test', ROOT/'bench/catalog_single/plan.py')
        for (name, argv), (old_name, old_argv) in zip(rows[10:], historical.commands()):
            self.assertEqual(name, old_name)
            old_argv = list(old_argv)
            old_argv[old_argv.index('--output')+1] = destination+'/'+name
            old_argv[old_argv.index('--kernel-source')+1] = '/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build'
            old_argv[old_argv.index('--kernel-baseline')+1] = '/root/kdlock-kernel-baselines/linux70-kdlock1-20261027'
            self.assertEqual(argv, old_argv)
        expected = [*range(1, 9), *range(12, 61, 4)]
        for name, argv in rows:
            self.assertEqual(argv[argv.index('--kernel-source')+1],
                             '/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build')
            self.assertEqual(argv[argv.index('--kernel-baseline')+1],
                             '/root/kdlock-kernel-baselines/linux70-kdlock1-20261027')
            self.assertEqual(argv[argv.index('--output')+1], destination+'/'+name)
            self.assertEqual(argv[argv.index('--repeats')+1], '1')
            self.assertEqual(argv[argv.index('--duration-ms')+1], '2000')
            self.assertEqual(argv[argv.index('--collector-cpu')+1], '63')
            start = argv.index('--threads')+1
            actual = []
            for value in argv[start:]:
                if value.startswith('--'):
                    break
                actual.append(int(value))
            self.assertEqual(actual, expected)
        for name, argv in rows[:10]:
            self.assertTrue(name.startswith('nano-'))
            self.assertEqual(argv[argv.index('--post-work-rounds')+1], '256')
            self.assertEqual(argv[argv.index('--cachelines')+1], '1' if 'throughput' in name else '16')
            self.assertEqual(argv[argv.index('--workloads')+1], 'cacheline')
        self.assertFalse({'nano-mutex', 'nano-rwsem-read', 'nano-rwsem-mixed'} & {n for n, _ in rows})

    def test_rejects_source_or_nested_evidence_destination(self):
        for path in ('/root/host_fs/kdlock', '/tmp/run', 'relative',
                     '/root/kdlock-evidence/10.176.26.71/bench/new/nested',
                     '/root/kdlock-evidence/10.176.26.71/bench/../escape'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                list(catalog.commands(path))


if __name__ == '__main__':
    unittest.main()
