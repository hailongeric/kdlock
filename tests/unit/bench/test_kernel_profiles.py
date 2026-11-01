"""VM-only profile selection, child-plan and archive admission checks."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
sys.path.insert(0, str(ROOT / 'bench/basic'))
import kernel_identity


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


nano = load('kernel_profiles_nano', 'bench/nano/best_case.py')
basic = load('kernel_profiles_basic', 'bench/basic/run.py')
archive = load('kernel_profiles_archive', 'bench/archive_run.py')

# Literal expectations catch accidental path construction (notably linux-),
# an inferred MM mode, and a scope bundle silently accepted by kdlock1.
EXPECTED = {
    'kdlock1': ('7.0.0-38-kdlock1',
               '/mnt/kdlock-builds/linux-7.0.0-38-kdlock1/build',
               '/root/kdlock-kernel-baselines/linux70-kdlock1-20261027'),
    'kdscope1-native': ('7.0.0-38-kdscope1',
                       '/mnt/kdlock-builds/linux-7.0.0-38-kdscope1/build',
                       '/root/kdlock-kernel-baselines/linux70-kdscope1-native-20261030'),
    'kdscope1-kd': ('7.0.0-38-kdscope1',
                   '/mnt/kdlock-builds/linux-7.0.0-38-kdscope1/build',
                   '/root/kdlock-kernel-baselines/linux70-kdscope1-kd-20261030'),
    'kdscope3-native': ('7.0.0-38-kdscope3',
                       '/mnt/kdlock-builds2/linux-7.0.0-38-kdscope3/build',
                       '/root/kdlock-kernel-baselines/linux70-kdscope3-native-20261031'),
    'kdscope3-kd': ('7.0.0-38-kdscope3',
                   '/mnt/kdlock-builds2/linux-7.0.0-38-kdscope3/build',
                   '/root/kdlock-kernel-baselines/linux70-kdscope3-kd-20261031'),
    'kdscope4-native': ('7.0.0-38-kdscope4',
                       '/mnt/kdlock-builds2/linux-7.0.0-38-kdscope4/build',
                       '/root/kdlock-kernel-baselines/linux70-kdscope4-native-20261101'),
    'kdscope4-kd': ('7.0.0-38-kdscope4',
                   '/mnt/kdlock-builds2/linux-7.0.0-38-kdscope4/build',
                   '/root/kdlock-kernel-baselines/linux70-kdscope4-kd-20261101'),
}
IDENTITY_OPTIONS = ('--kernel-variant', '--kernel-source', '--kernel-baseline')


def selection(variant='kdlock1', source=None, bundle=None):
    return argparse.Namespace(kernel_variant=variant, kernel_source=source,
                              kernel_baseline=bundle)


def workload_argv(argv):
    """Remove only identity option/value pairs from an actual child command."""
    result = list(argv)
    for option in IDENTITY_OPTIONS:
        index = result.index(option)
        del result[index:index + 2]
    return result


class KernelProfileTests(unittest.TestCase):
    def assert_identity_options(self, argv, variant):
        _, build, bundle = EXPECTED[variant]
        for option, value in zip(IDENTITY_OPTIONS, (variant, build, bundle)):
            self.assertEqual(argv.count(option), 1)
            self.assertEqual(argv[argv.index(option) + 1], value)

    def test_benchmark_cli_requires_explicit_known_family_and_mode(self):
        parser = argparse.ArgumentParser()
        kernel_identity.benchmark_arguments(parser)
        args = parser.parse_args([])
        self.assertEqual(args.kernel_variant, 'kdlock1')
        self.assertIsNone(args.kernel_source)
        self.assertIsNone(args.kernel_baseline)
        for variant in EXPECTED:
            self.assertEqual(parser.parse_args(['--kernel-variant', variant]).kernel_variant,
                             variant)
        for variant in ('kdmm1-native', 'kdmm1-kd', 'kdscope1', 'kdscope3', 'kdscope4', 'native', 'unknown'):
            with self.subTest(variant=variant), patch.object(sys, 'stderr'), \
                    self.assertRaises(SystemExit):
                parser.parse_args(['--kernel-variant', variant])

    def test_nonbenchmark_argument_defaults_are_preserved(self):
        parser = argparse.ArgumentParser()
        kernel_identity.arguments(parser)
        args = parser.parse_args([])
        self.assertEqual(args.kernel_source, Path(EXPECTED['kdlock1'][1]))
        self.assertEqual(args.kernel_baseline, Path(EXPECTED['kdlock1'][2]))
        self.assertEqual(parser.parse_args(['--kernel-variant', 'kdmm1-kd']).kernel_variant,
                         'kdmm1-kd')

    def test_profiles_resolve_only_the_literal_canonical_paths(self):
        self.assertEqual(set(kernel_identity.BENCHMARK_PROFILES), set(EXPECTED))
        for variant, (release, build, bundle) in EXPECTED.items():
            with self.subTest(variant=variant):
                args = selection(variant)
                profile = kernel_identity.benchmark_profile(args, release=release)
                self.assertEqual(profile, dict(release=release, build=Path(build),
                                               bundle=Path(bundle)))
                self.assertEqual((args.kernel_source, args.kernel_baseline),
                                 (Path(build), Path(bundle)))
                self.assertEqual(kernel_identity.benchmark_profile(args, release=release), profile)

    def test_release_and_both_paths_must_match_the_explicit_profile(self):
        for variant, (release, build, bundle) in EXPECTED.items():
            with self.subTest(variant=variant, field='release'), self.assertRaises(ValueError):
                kernel_identity.benchmark_profile(selection(variant), release=release + '-other')
            bad_paths = [(Path('/selected/build'), Path(bundle)),
                         (Path(build), Path('/selected/bundle')),
                         (Path(build).parent / 'alternate' / '..' / 'build', Path(bundle))]
            for other, (_, other_build, other_bundle) in EXPECTED.items():
                if other != variant:
                    bad_paths.append((Path(other_build), Path(other_bundle)))
            for source, baseline in bad_paths:
                with self.subTest(variant=variant, source=source, baseline=baseline), \
                        self.assertRaises(ValueError):
                    kernel_identity.benchmark_profile(selection(variant, source, baseline))
        for variant in ('kdmm1-native', 'kdmm1-kd', 'unknown', None):
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                kernel_identity.benchmark_profile(selection(variant))

    def test_scope_release_does_not_infer_variant_from_bundle(self):
        with self.assertRaises(ValueError):
            kernel_identity.benchmark_profile(selection(), release='7.0.0-38-kdscope1')
        # The two scope modes share a release/build, but not their selected
        # bundle or expected boot mode. Neither is a fallback for the other.
        with self.assertRaises(ValueError):
            kernel_identity.benchmark_profile(selection('kdscope1-native',
                Path(EXPECTED['kdscope1-kd'][1]), Path(EXPECTED['kdscope1-kd'][2])),
                release='7.0.0-38-kdscope1')

    def test_alternate_symlink_spelling_is_not_resolved_into_admission(self):
        with tempfile.TemporaryDirectory() as temporary:
            for field, target in (('kernel_source', EXPECTED['kdscope1-kd'][1]),
                                  ('kernel_baseline', EXPECTED['kdscope1-kd'][2])):
                alias = Path(temporary) / field
                alias.symlink_to(target, target_is_directory=True)
                args = selection('kdscope1-kd')
                setattr(args, field, alias)
                with self.subTest(field=field), self.assertRaises(ValueError):
                    kernel_identity.benchmark_profile(args)

    def test_nano_child_commands_change_only_kernel_identity(self):
        options = ['--output', '/tmp/kernel-profile-plan', '--plan-only']
        reference = list(nano.commands(nano.parser().parse_args(options)))
        self.assertEqual(len(reference), 10)
        for variant in EXPECTED:
            args = nano.parser().parse_args(options + ['--kernel-variant', variant])
            candidate = list(nano.commands(args))
            self.assertEqual([name for name, _ in candidate], [name for name, _ in reference])
            for (name, argv), (_, original) in zip(candidate, reference):
                with self.subTest(variant=variant, profile=name):
                    self.assert_identity_options(argv, variant)
                    self.assertEqual(workload_argv(argv), workload_argv(original))

    def test_basic_children_change_only_kernel_identity(self):
        out = Path('/tmp/kernel-profile-plan')
        reference = basic.plan(out, basic.FAMILIES)
        for variant in EXPECTED:
            candidate = basic.plan(out, basic.FAMILIES, kernel_variant=variant)
            self.assertEqual(len(candidate), 4)
            for row, original in zip(candidate, reference):
                with self.subTest(variant=variant, family=row['family']):
                    self.assertEqual((row['family'], row['output']),
                                     (original['family'], original['output']))
                    self.assert_identity_options(row['argv'], variant)
                    self.assertEqual(workload_argv(row['argv']), workload_argv(original['argv']))

    def test_scope_child_parsers_accept_actual_functional_commands(self):
        # Run only by the VM unit runner. --dry-run exercises both actual child
        # parsers/planners; it neither builds nor enters a live workload.
        for variant in ('kdscope1-native', 'kdscope1-kd', 'kdscope3-native', 'kdscope3-kd'):
            for row in basic.plan(Path('/tmp/kernel-profile-plan'), basic.FAMILIES,
                                  kernel_variant=variant):
                with self.subTest(variant=variant, family=row['family']):
                    result = subprocess.run([*row['argv'], '--dry-run'], check=True,
                                            capture_output=True, text=True, timeout=30)
                    plan = json.loads(result.stdout)
                    self.assertEqual(len(plan), 1)
                    self.assertIs(plan[0]['functional'], True)
                    self.assertEqual(plan[0]['threads'], 16)
                    self.assertEqual(plan[0]['duration_ms'], 0)

    def test_archive_performs_full_schema2_check_for_selected_mode(self):
        for variant, (release, build, bundle) in EXPECTED.items():
            verified = dict(ok=True, schema=2, runtime_policy_verified=True,
                            build_id='retained-build-id', variant=variant)
            with self.subTest(variant=variant), \
                    patch.object(archive.os, 'uname', return_value=SimpleNamespace(release=release)), \
                    patch.object(kernel_identity, 'check', return_value=verified) as check:
                result = archive.kernel_admission(selection(variant))
                self.assertIs(result, verified)
                check.assert_called_once_with(Path(build), Path(bundle), variant=variant)

    def test_archive_rejects_partial_or_failed_verification(self):
        valid = dict(ok=True, schema=2, runtime_policy_verified=True)
        failures = [{}, dict(valid, ok=False), dict(valid, ok=1),
                    dict(valid, schema=1), dict(valid, schema=None),
                    dict(valid, runtime_policy_verified=False),
                    dict(valid, runtime_policy_verified=1)]
        for result in failures:
            with self.subTest(result=result), \
                    patch.object(archive.os, 'uname', return_value=SimpleNamespace(
                        release=EXPECTED['kdscope1-kd'][0])), \
                    patch.object(kernel_identity, 'check', return_value=result) as check, \
                    self.assertRaises(RuntimeError):
                archive.kernel_admission(selection('kdscope1-kd'))
            check.assert_called_once()

    def test_archive_refuses_mismatch_before_verifier_and_propagates_errors(self):
        release = EXPECTED['kdscope1-kd'][0]
        for args, observed in ((selection('kdscope1-kd'), release + '-other'),
                               (selection('kdscope1-kd', Path('/wrong/build')), release),
                               (selection('kdscope1-native', bundle=Path(
                                   EXPECTED['kdscope1-kd'][2])), release)):
            with self.subTest(args=args, release=observed), \
                    patch.object(archive.os, 'uname', return_value=SimpleNamespace(release=observed)), \
                    patch.object(kernel_identity, 'check') as check, self.assertRaises(ValueError):
                archive.kernel_admission(args)
            check.assert_not_called()
        with patch.object(archive.os, 'uname', return_value=SimpleNamespace(release=release)), \
                patch.object(kernel_identity, 'check', side_effect=ValueError('build mismatch')), \
                self.assertRaisesRegex(ValueError, 'build mismatch'):
            archive.kernel_admission(selection('kdscope1-kd'))


if __name__ == '__main__':
    unittest.main()
