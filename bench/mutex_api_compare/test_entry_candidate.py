"""Guest-only checks for the isolated provider experiment's source/arm binding."""
import unittest
from pathlib import Path
import tempfile

import entry_candidate as candidate
import run


class CandidateTests(unittest.TestCase):
    def test_actual_provider_sources_must_match_the_declared_build_recipe(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            relative = 'kernel_module/body.c'
            for tree in ('provider-inputs', 'provider'):
                target = base/tree/relative
                target.parent.mkdir(parents=True)
                target.write_text('original source\n')
            expected = candidate.sha(base/'provider'/relative)
            common = {relative: expected}
            manifest = {'prepared': dict(common)}
            candidate.verify_provider_tree(base, common, manifest)
            for tree in ('provider', 'provider-inputs'):
                target = base/tree/relative
                target.write_text('unreviewed change\n')
                with self.assertRaises(ValueError):
                    candidate.verify_provider_tree(base, common, manifest)
                target.write_text('original source\n')

    def test_measurement_cannot_write_into_or_above_candidate_inputs(self):
        manifest = Path('/new-inputs/candidate.json')
        for output in ('/new-inputs', '/new-inputs/candidate-public/c08/result', '/'):
            with self.assertRaisesRegex(ValueError, 'overlaps'):
                run.candidate_output(manifest, Path(output))
        run.candidate_output(manifest, Path('/new-measurement'))

    def test_original_controls_keep_their_bundle_and_identity_selection(self):
        order = run.replay_order()
        changed = []
        for group, count, repeat, arm in order:
            old = run.bundle_key(group, arm)
            new = run.bundle_key(group, arm, {'validated': True})
            if old != new:
                changed.append((group, count, repeat, arm))
                self.assertEqual(arm, 'public-kd')
                self.assertEqual(new, 'candidate-public/'+group)
            else:
                self.assertNotEqual(arm, 'public-kd')
        self.assertEqual(len(changed), 30)
        self.assertEqual({r[0] for r in changed}, set(candidate.GROUPS))

    def test_source_delta_rejects_unrelated_change_or_stale_prepared_manifest(self):
        for prepared in (False, True):
            old = {candidate.ENTRY: candidate.OLD_ENTRY, 'disassem/tool.py': 'translator'}
            new = dict(old, **{candidate.ENTRY: candidate.NEW_ENTRY})
            if prepared:
                old.update({candidate.PREPARED+candidate.ENTRY: candidate.OLD_ENTRY,
                            candidate.PREPARED+'manifest.json': 'old-prepared'})
                new.update({candidate.PREPARED+candidate.ENTRY: candidate.NEW_ENTRY,
                            candidate.PREPARED+'manifest.json': 'new-prepared'})
            candidate.validate_source_delta(old, new, 'new-prepared')
            for key, value in [('disassem/tool.py', 'different'), (candidate.ENTRY, candidate.OLD_ENTRY)]:
                with self.assertRaises(ValueError):
                    candidate.validate_source_delta(old, dict(new, **{key: value}), 'new-prepared')
            with self.assertRaisesRegex(ValueError, 'source set changed'):
                candidate.validate_source_delta(old, dict(new, extra='untracked'), 'new-prepared')
            if prepared:
                with self.assertRaisesRegex(ValueError, 'manifest'):
                    candidate.validate_source_delta(old, new, 'old-prepared')


if __name__ == '__main__':
    unittest.main()
