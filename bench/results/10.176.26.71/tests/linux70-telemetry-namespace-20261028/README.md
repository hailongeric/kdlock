# Frequency telemetry namespace correction

The first trusted-API campaign, `catalog-linux70-trusted-20261027`, stopped
before launching `taskname-w00`: its telemetry monitor found the existing
`/tmp/kdlock-linux70-taskname-w00-stop` marker and refused startup. That attempt
retains its `STOPPED` status, empty telemetry output and **zero timed points**.
Read-only diagnosis found no active monitor and confirmed the guest was idle
on normal boot `15dc5977-59d3-4471-a196-d71f03f450ed`, without kernel faults.
No old stop marker was deleted.

The monitor token now includes the actual campaign directory name, so the new
campaign uses `catalog-linux70-trusted-20261028-taskname-w00`. This also covers MM
callers that select their raw directory directly. Existing-marker rejection is
unchanged. Start receipts are written before launch and retain the PID before
script delivery; failures record the actual exit code or explicitly unknown
completion. Timeouts neither kill a child nor claim drain.

VM validation passed **nine catalog methods and nineteen MM-controller methods**
(28 total), followed by an idle check. The five added monitor cases exercise
cross-campaign namespace separation, an existing qualified marker, startup
timeout, stop timeout and unexpected early exit. Synchronization verified all
5,023 approved file hashes; only the controller and its focused test changed as
code. Eight documentation files also changed. [evidence.json](evidence.json)
binds the two changed source files, the sync receipt, VM checks and original
diagnosis.

The new campaign's initial telemetry receipt confirms startup with its qualified
token. Its [own progress and tables](../../bench/catalog-linux70-trusted-20261028/README.md)
are authoritative for later measurements. This checkpoint does not relabel the
old failed preflight or make a performance claim.
