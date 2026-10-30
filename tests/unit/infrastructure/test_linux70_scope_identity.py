#!/usr/bin/env python3
"""Exact composition provenance and explicit scope profiles; run only in the VM."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


identity = load("scope_identity_test", "kernel_integration/linux70/verify.py")
scope = load("scope_composition_test", "kernel_integration/linux70/compose_scope.py")
capture = load("scope_capture_test", "kernel_integration/linux70/capture.py")


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ScopeIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="kd-scope-identity-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bundle, self.source = self.root / "bundle", self.root / "source"
        self.bundle.mkdir()
        self.source.mkdir()
        self.files = {}
        self.pristine = b"# upstream locking objects\n"
        self.mm = self.receipt("MM")
        self.api = self.receipt("API")
        self.mm["outputs"] = {name: sha(b"MM overlay") for name in scope.MM_OUTPUTS}
        self.mm["outputs"][scope.SHARED] = sha(self.pristine + scope.MM_SUFFIX)
        self.mm["native_body_sha256"] = {name: sha(b"untouched MM") for name in scope.MM_NATIVE_PATHS}
        self.api["outputs"] = {name: sha(b"API overlay") for name in scope.API_OUTPUTS}
        self.api["outputs"][scope.SHARED] = sha(self.pristine + scope.API_SUFFIX)
        self.api["inputs"][scope.API_RECIPE] = sha((ROOT / scope.API_RECIPE).read_bytes())
        self.api["native_body_sha256"] = {}
        pristine_api = {}
        for name, functions in scope.api_recipe().SELECTED.items():
            text = ""
            for function in functions:
                lock, unlock = (("spin_lock(&files->file_lock)", "spin_unlock(&files->file_lock)")
                                if name == "fs/file.c" else
                                ("mutex_lock(&pipe->mutex)", "mutex_unlock(&pipe->mutex)"))
                body = f"void {function}(void)\n{{\n\t{lock};\n\tnative_body++;\n\t{unlock};\n}}"
                text += body + "\n"
                self.api["native_body_sha256"][name + ":" + function] = sha(body.encode())
            pristine_api[name] = text.encode()
            transformed = text.replace("spin_lock(&files->file_lock)", "KD_API_FILES_LOCK(files)")
            transformed = transformed.replace("spin_unlock(&files->file_lock)", "KD_API_FILES_UNLOCK(files)")
            transformed = transformed.replace("mutex_lock(&pipe->mutex)", "kd_api_pipe_lock(&pipe->mutex)")
            transformed = transformed.replace("mutex_unlock(&pipe->mutex)", "kd_api_pipe_unlock(&pipe->mutex)")
            self.write(self.source / name, transformed.encode())
            self.api["outputs"][name] = sha(transformed.encode())
        base_files = {**{name: sha(b"pristine wrapper") for name in scope.MM_PATCH_PATHS | scope.API_PATCH_PATHS},
                      scope.SHARED: sha(self.pristine), **{k: sha(v) for k, v in pristine_api.items()},
                      **self.mm["native_body_sha256"]}
        self.put_json("scope-base-sha256.json", dict(files=base_files))
        patcher = mock.patch.object(scope, "BASE_SHA256", self.files["scope-base-sha256.json"])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.put_json("api-base-sha256.json", dict(source_package=identity.PACKAGE,
                      files={k: base_files[k] for k in scope.API_PATCH_PATHS}))
        self.put_json("mmap-base-sha256.json", dict(source_package=identity.PACKAGE,
                      files={k: base_files[k] for k in scope.MM_PATCH_PATHS},
                      native_bodies=self.mm["native_body_sha256"]))
        self.put("api-lock-binding.patch", "".join("+++ b/" + p + "\n" for p in sorted(scope.API_PATCH_PATHS)).encode())
        self.put("mmap-lock.patch", b"MM patch")
        self.put("core-kernel.patch", b"core patch")
        self.put("source-acquisition.json", b"authenticated acquisition")
        self.mm.update(patch_sha256=self.files["mmap-lock.patch"],
                       base_manifest_sha256=self.files["mmap-base-sha256.json"])
        self.api.update(patch_sha256=self.files["api-lock-binding.patch"],
                        manifest_sha256=self.files["api-base-sha256.json"])
        self.put_json("mmap-prepare.json", self.mm)
        self.put_json("api-prepare.json", self.api)
        for prefix, receipt in (("mmap-inputs/", self.mm), ("api-inputs/", self.api)):
            for name in receipt["inputs"]:
                self.put(prefix + name, (ROOT / name).read_bytes() if name == scope.API_RECIPE else b"reviewed generator")
        final = self.mm["outputs"] | self.api["outputs"] | self.mm["native_body_sha256"]
        final[scope.SHARED] = sha(self.pristine + scope.MM_SUFFIX + scope.API_SUFFIX)
        for names, data in ((scope.MM_OUTPUTS - {scope.SHARED}, b"MM overlay"),
                            (scope.API_OUTPUTS - {scope.SHARED, "fs/file.c", "fs/pipe.c"}, b"API overlay"),
                            (scope.MM_NATIVE_PATHS, b"untouched MM")):
            for name in names:
                self.write(self.source / name, data)
        self.write(self.source / scope.SHARED, self.pristine + scope.MM_SUFFIX + scope.API_SUFFIX)
        for name in identity.CORE_PATHS | set(identity.BASE_SOURCE):
            self.write(self.source / name, b"core or base fixture")
            final[name] = sha(b"core or base fixture")
        artifacts = {"base/" + scope.SHARED: self.pristine,
                     "mmap/" + scope.SHARED: self.pristine + scope.MM_SUFFIX,
                     "api/" + scope.SHARED: self.pristine + scope.API_SUFFIX,
                     **{"pristine-api/" + k: v for k, v in pristine_api.items()}}
        for name, data in artifacts.items():
            self.put("composition/" + name, data)
        inputs = {"kernel_integration/linux70/compose_scope.py": sha(b"composer"),
                  "kernel_integration/linux70/scope-base-sha256.json": scope.BASE_SHA256}
        self.put("composition-inputs/kernel_integration/linux70/compose_scope.py", b"composer")
        self.put("composition-inputs/kernel_integration/linux70/scope-base-sha256.json",
                 (self.bundle / "scope-base-sha256.json").read_bytes())
        self.composition = dict(schema=1, passed=True, source_unchanged=True, overlays_unchanged=True,
            config_modified=False, kernel_built=False, installed=False, booted=False,
            rule=scope.RULE, source_package=identity.PACKAGE, source=self.mm["source"],
            composed_source=str(self.source), source_archives=identity.SOURCE_ARCHIVES,
            inputs=inputs, artifacts={k: sha(v) for k, v in artifacts.items()}, final_source_files=final,
            overlap=dict(path=scope.SHARED, pristine=sha(self.pristine), mmap=self.mm["outputs"][scope.SHARED],
                         api=self.api["outputs"][scope.SHARED], final=final[scope.SHARED]))
        for key, name in (("scope_base_sha256", "scope-base-sha256.json"),
                          ("core_patch_sha256", "core-kernel.patch"),
                          ("mmap_prepare_sha256", "mmap-prepare.json"),
                          ("api_prepare_sha256", "api-prepare.json"),
                          ("acquisition_sha256", "source-acquisition.json")):
            self.composition[key] = self.files[name]
        self.put_json("composition.json", self.composition)
        self.manifest = dict(bundle_files=self.files, source_files=final,
                             api=dict(enabled=True, default_backend="native"))

    @staticmethod
    def receipt(kind):
        return dict(passed=True, source_unchanged=True, config_modified=False,
                    source_package=identity.PACKAGE, source="/authenticated/pristine",
                    inputs={kind + "/generator.py": sha(b"reviewed generator")}, outputs={})

    @staticmethod
    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def put(self, name, data):
        self.write(self.bundle / name, data)
        self.files[name] = sha(data)

    def put_json(self, name, data):
        self.put(name, json.dumps(data, sort_keys=True).encode())

    def check(self):
        identity.check_files(self.bundle, self.files)
        identity.check_files(self.source, self.manifest["source_files"])
        scope.check_bundle(identity, self.bundle, self.manifest, self.source, self.mm)

    def test_exact_composition_and_body_checks(self):
        self.check()
        self.assertNotEqual(self.mm["outputs"][scope.SHARED], self.manifest["source_files"][scope.SHARED])
        self.assertNotEqual(self.api["outputs"][scope.SHARED], self.manifest["source_files"][scope.SHARED])

    def test_mutated_receipt_claims_rejected_even_with_updated_bundle_hash(self):
        for field, bad in (("rule", "overwrite-last"), ("passed", False),
                           ("source_unchanged", False), ("overlays_unchanged", False),
                           ("config_modified", True), ("kernel_built", True),
                           ("composed_source", "/different/source"),
                           ("mmap_prepare_sha256", "0" * 64)):
            with self.subTest(field=field):
                altered = copy.deepcopy(self.composition)
                altered[field] = bad
                self.put_json("composition.json", altered)
                with self.assertRaises(ValueError):
                    self.check()
        self.put_json("composition.json", self.composition)

    def test_extra_collision_and_wrong_intermediate_bytes_rejected(self):
        altered = copy.deepcopy(self.api)
        altered["outputs"]["include/linux/kd_mmap_lock.h"] = sha(b"MM overlay")
        with self.assertRaisesRegex(ValueError, "collision"):
            scope.composed_outputs(self.mm, altered, self.pristine,
                                   self.pristine + scope.MM_SUFFIX, self.pristine + scope.API_SUFFIX)
        for mm, api in ((self.pristine + scope.MM_SUFFIX + b"extra", self.pristine + scope.API_SUFFIX),
                        (self.pristine + scope.MM_SUFFIX, self.pristine + scope.API_SUFFIX + b"extra")):
            with self.assertRaisesRegex(ValueError, "exact reviewed append"):
                scope.composed_outputs(self.mm, self.api, self.pristine, mm, api)

    def test_missing_input_artifact_and_final_scope_rejected(self):
        for name in ("api-inputs/API/generator.py", "composition/base/" + scope.SHARED,
                     "composition-inputs/kernel_integration/linux70/compose_scope.py"):
            expected = self.files.pop(name)
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.check()
            self.files[name] = expected
        self.manifest["source_files"] = self.manifest["source_files"] | {"unreviewed.c": sha(b"x")}
        self.write(self.source / "unreviewed.c", b"x")
        with self.assertRaisesRegex(ValueError, "final manifest differs"):
            self.check()

    def test_api_body_change_not_hidden_by_coherent_file_hash_updates(self):
        path = self.source / "fs/file.c"
        path.write_text(path.read_text().replace("native_body++", "native_body--"))
        # Rebind every enclosing hash; the unchanged native-body proof must
        # still fail instead of accepting a self-consistent altered manifest.
        digest = sha(path.read_bytes())
        self.api["outputs"]["fs/file.c"] = digest
        self.put_json("api-prepare.json", self.api)
        self.composition["api_prepare_sha256"] = self.files["api-prepare.json"]
        self.composition["final_source_files"]["fs/file.c"] = digest
        self.put_json("composition.json", self.composition)
        with self.assertRaisesRegex(ValueError, "native API body changed"):
            self.check()

    def test_coherent_extra_overlay_output_cannot_expand_named_scope(self):
        name = "fs/read_write.c"
        self.write(self.source / name, b"unreviewed body")
        expected = sha(b"unreviewed body")
        self.api["outputs"][name] = expected
        self.put_json("api-prepare.json", self.api)
        self.composition["api_prepare_sha256"] = self.files["api-prepare.json"]
        self.composition["final_source_files"][name] = expected
        self.put_json("composition.json", self.composition)
        with self.assertRaisesRegex(ValueError, "output pathname scope"):
            self.check()

    def test_current_normalizer_must_match_captured_recipe(self):
        self.api["inputs"][scope.API_RECIPE] = sha(b"changed normalizer")
        self.put("api-inputs/" + scope.API_RECIPE, b"changed normalizer")
        self.put_json("api-prepare.json", self.api)
        self.composition["api_prepare_sha256"] = self.files["api-prepare.json"]
        self.put_json("composition.json", self.composition)
        with self.assertRaisesRegex(ValueError, "normalization recipe differs"):
            self.check()

    def test_profiles_are_explicit_and_preserve_old_defaults(self):
        self.assertEqual(identity.variant_settings()["release"], "7.0.0-38-kdlock1")
        self.assertEqual(identity.variant_settings("kdmm1-kd")["release"], "7.0.0-38-kdmm1")
        profiles = (("kdscope1", "kdlock-builds", "20261030"),
                    ("kdscope2", "kdlock-builds2", "20261031"))
        for family, disk, date in profiles:
            for suffix, mode in (("native", "off"), ("kd", "on")):
                variant = family + "-" + suffix
                selected = identity.variant_settings(variant)
                self.assertEqual(selected["release"], "7.0.0-38-" + family)
                self.assertEqual(selected["source"], Path("/mnt/" + disk + "/linux-7.0.0-38-" + family + "/source"))
                self.assertEqual(selected["build"], Path("/mnt/" + disk + "/linux-7.0.0-38-" + family + "/build"))
                self.assertEqual(selected["mmap_mode"], mode)
                self.assertEqual(selected["bundle"].name, "linux70-" + variant + "-" + date)
                config = dict(CONFIG_KDLOCK_MMAP="y", CONFIG_KD_API_LOCKS="y")
                identity.check_variant_config(config, variant)
                for change in (dict(CONFIG_KDLOCK_MMAP="n"), dict(CONFIG_KD_API_LOCKS="n"),
                               dict(CONFIG_DEBUG_SPINLOCK="y")):
                    with self.assertRaises(identity.BaselineError):
                        identity.check_variant_config(config | change, variant)
                identity.runtime_policy("nokaslr nopvspin kd_mmap=" + mode, "full (lazy)", variant=variant)
                with self.assertRaises(identity.BaselineError):
                    identity.runtime_policy("nokaslr nopvspin kd_mmap=" + ("on" if mode == "off" else "off"),
                                            "full (lazy)", variant=variant)
        with self.assertRaises(identity.BaselineError):
            identity.check_variant_config(dict(CONFIG_KDLOCK_MMAP="y", CONFIG_KD_API_LOCKS="y"), "kdmm1-kd")

    def test_scope2_source_binding_cannot_reuse_scope1_or_opposite_mode(self):
        build = self.root / "scope2-build"
        build.mkdir()
        generated = (f"# Automatically generated by {self.source}/Makefile: don't edit\n"
                     f"export KBUILD_OUTPUT = {build}\ninclude {self.source}/Makefile\n")
        (build / "Makefile").write_text(generated)
        with mock.patch.object(identity, "SCOPE2_SOURCE_ROOT", self.source), \
                mock.patch.object(identity, "SCOPE2_BUILD_ROOT", build):
            for variant in ("kdscope2-native", "kdscope2-kd"):
                manifest = dict(variant=variant, source_root=str(self.source), build_root=str(build))
                self.assertEqual(identity.source_directory(build, manifest, variant=variant), self.source)
                for change in (dict(variant="kdscope1-kd"),
                               dict(variant="kdscope2-kd" if variant.endswith("native") else "kdscope2-native"),
                               dict(source_root=str(identity.SCOPE_SOURCE_ROOT)),
                               dict(build_root=str(identity.SCOPE_BUILD_ROOT))):
                    with self.subTest(variant=variant, change=change), self.assertRaises(identity.BaselineError):
                        identity.source_directory(build, manifest | change, variant=variant)
                with self.assertRaises(identity.BaselineError):
                    identity.source_directory(identity.SCOPE_BUILD_ROOT, manifest, variant=variant)
                (build / "Makefile").write_text(generated.replace(str(self.source), str(identity.SCOPE_SOURCE_ROOT)))
                with self.assertRaisesRegex(identity.BaselineError, "Makefile source/output binding"):
                    identity.source_directory(build, manifest, variant=variant)
                (build / "Makefile").write_text(generated)

    def test_capture_requires_both_scope_receipts_before_creating_output(self):
        for variant in identity.SCOPE_VARIANTS:
            selected = dict(release=identity.variant_settings(variant)["release"], source=self.source,
                            build=self.root / "build", bundle=self.root / ("new-" + variant))
            args = SimpleNamespace(variant=variant, source=None, build=None, output=None,
                                   mmap_prepare=self.root / "mm.json", api_prepare=None, composition=None)
            with mock.patch.object(capture.identity, "variant_settings", return_value=selected), \
                    mock.patch.object(capture.os, "geteuid", return_value=0), \
                    mock.patch.object(capture.os, "uname", return_value=SimpleNamespace(release=selected["release"])):
                for api, composition in ((None, None), (self.root / "api.json", None),
                                         (None, self.root / "composition.json")):
                    args.api_prepare, args.composition = api, composition
                    with self.assertRaisesRegex(capture.identity.BaselineError, "both receipts"):
                        capture.capture(args)
            self.assertFalse(selected["bundle"].exists())


if __name__ == "__main__":
    unittest.main()
