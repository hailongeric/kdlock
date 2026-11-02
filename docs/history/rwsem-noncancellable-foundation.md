# Incomplete rwsem foundation retained after direction correction

Base: 69fca435cb41135a3676f66e54f413b3ee5c714e on
codex/rwsem-delegated-protocol-20261102. The explicit archive reference is
codex/archive-rwsem-noncancellable-foundation. This work is not a candidate
for validation or promotion.

The attempted order implemented selected writer/read-credit records and began
ordinary prepared-writer transport before implementing delegated killable
acquisition. The user rejected that order: mmap/munmap require the killable
entry, including cancellation/publication/commit arbitration. Keeping callable
killable writers local would preserve their earlier local behavior but would
not implement the requested delegated mmap writers.

All edits were stopped. This snapshot retains partial phase/type changes,
incomplete runtime transport and frame changes, public wrapper/translation
changes, and unfinished test changes. The combiner controls were not completed.
The new proxy runner also has an unresolved duplicate diagnostic overlay.
No compilation, unit test, module load, application run or timing used these
bytes. There is no read-tail proxy proof or validated fresh writer acquisition.
The earlier VM preflight was read-only and does not validate this snapshot.

Continue from the preceding docs/observation checkpoint on a separate branch,
with the required order: killable continuation capture and cancellable request
commit protocol; admission encoding; delegated writer/read-tail transitions;
then candidate validation. A result-returning wrapper that only calls the local
killable function, or publishes through the existing uncancellable queue, is not
an implementation of the requested killable delegation path.

The maintained master checkout and its unrelated working changes were not
modified. This historical source remains reachable so the rejected attempt is
not lost or presented as tested work.
