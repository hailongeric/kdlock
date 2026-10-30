# Offline nano audit inputs and reproduction

The completed audit used the exact two arm objects in `inputs.json`, SHA-256
`47b966fdae0e7741987386223964af3d1af6da3a8b47f8a2f8837cd243b4e943`.
The actual command on 380G10 was:

```
python3 /tmp/kdlock-killable-offline-20261031/nano_compare.py \
  --inputs /dev/shm/kdlock-killable-nano-comparison-inputs-20261031.json \
  --inputs-sha256 47b966fdae0e7741987386223964af3d1af6da3a8b47f8a2f8837cd243b4e943 \
  --trusted-checkout /home/eric/vm/vm-shared/kdlock \
  --cache-root /dev/shm \
  --output /dev/shm/kdlock-killable-nano-comparison-20261031
```

The command completed with return code 0. `validation.json` has SHA-256
`4db452836c12a1d8d05ff280c9731bf8008f6f51f714f5e8bac94740564eb858`.
Strict qualification and complete source/provider/raw-point validation passed;
the no-regression gate failed. These are distinct outcomes.

The five used analyzer Python files are retained unchanged under
`../tools/offline-nano/`. `original-tool-manifest.json` is the original complete
tool-bundle manifest, whose SHA-256 is
`42e411775a5afd99fb69ceedd797b880761468bcfe1acc12bb47a7b3d563e36b`;
unused MM/report helpers from that bundle are not duplicated here. Reproduction
requires the authenticated raw archives/control trees at the named paths and a
Git checkout containing both exact provider commits. Always choose a new output
directory; preserve any failed audit. This is offline data analysis, not a
benchmark rerun. Do not execute archived programs.

The derived workload/key-worker summary was produced by the retained
`../tools/kdlock-killable-nano-summarize-20261031.py`, SHA-256
`be4851be9b75222ed5273c4aff3acf0c8be972b69784eb190c7cc0a0aed54fd6`.
It rechecks every whole/peak loss with integer cross-products, then summarizes
the original validated points. `interpretation/summary.json` has SHA-256
`36ba48190eebc15df6bb6cf71b1d55a8be46e049bf7934c75102d850fb49cf55`.
The original 210-row CSV has SHA-256
`ff44a90a82d98f880e0aeb6f16dec8efdd47198eff9c2de816e992462572b8d0`.

All large raw/analyzer artifacts remain in source-host tmpfs; their identities
are listed in `retained-artifacts.json`. Guest originals remain separate. The
report copies selected output bytes verbatim and does not pool historical rates,
discard negative signs, or change `performance_accepted=false`.
