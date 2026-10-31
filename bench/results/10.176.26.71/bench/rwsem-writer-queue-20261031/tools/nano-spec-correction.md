# Nano spec completion-field correction

The original data-only builder `87094d88a95f7d48d096214613a5ec455d8fc0552701924ad2eff48a9be7b054`
omits `success_key` in the run and archive specs. The generic guest transport
therefore looks for `passed`, while both reviewed nano controller owners use
`completed`. This can make the outer transport report failure after successful
guest work. The controller, measurement, endpoint and archive gates are not
changed by this metadata error.

The new `kdlock-writer-queue-nano-spec-r2-20261031.py` adds only
`success_key: completed` to the run/archive spec object. Its source-host
endpoint spec and every guest argument, source hash, cohort and output remain
unchanged. Use this separate builder for future specs. Keep the original
builder, already generated run inputs and resulting wrapper failure intact.

Do not repeat an existing measurement. After its run finishes, root must inspect
the actual controller owner for completed/idle/210-point validation, preserve
the independently completed endpoint, and retain the outer transport status
as a distinct metadata failure before continuing to archive.

This correction was inspected statically only: no builder, guest controller,
transport, test or measurement was executed during preparation.
