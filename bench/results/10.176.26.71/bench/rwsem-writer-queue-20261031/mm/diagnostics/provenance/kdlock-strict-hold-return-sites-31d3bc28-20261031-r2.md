# Strict-held package member correction

The first package used `manifest.json`; the unchanged flat diagnostic extractor
requires `diagnostic-manifest.json`. Its exact-member assertion failed before
creating the output recipe. Preserve that failed receipt and the original tar.

Use `/tmp/kdlock-strict-hold-return-sites-31d3bc28-20261031-r2.tar`, 51,200 bytes,
SHA256 `1b8bf7539bedaebb5acd9e459b514b60713c60d97b9696286cac903b6dcbb1e2`.
Only that member name changed. All seven members' bytes and metadata match the
original package; the external manifest, six committed sources, runner and
configuration are unchanged.

The external manifest remains
`/tmp/kdlock-strict-hold-return-sites-31d3bc28-20261031.manifest.json`, SHA256
`ed9fcddaf0b4dba2f4af3afd722cff5f184abcf6611177192d7d1666f9b5172e`.
After extraction its embedded path is `<new diagnostic root>/diagnostic-manifest.json`;
the earlier delivery example's `<root>/manifest.json` spelling is superseded.
The actual configuration uses the external manifest and needs no change.

Static archive inspection verified the exact seven regular members, permitted
modes, unchanged contents, and original tar hash. No extractor or VM action was
executed by the preparer. Root selects a separate receipt path for the retry.
