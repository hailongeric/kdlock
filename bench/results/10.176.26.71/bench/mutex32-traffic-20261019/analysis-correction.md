# Analysis correction

The first summary attempt refused the synthetic rows because the runner adds
five derived fields after saving each session record. The corrected helper
requires exact saved fields and independently recomputes those five values.
No workload was rerun or relabeled to repair this analysis error. The original
helper, incomplete outputs and receipt remain in `analysis-first-attempt/`.

The first receipt records summary status 1 and profile status 0. These individual
statuses were inferred from the helpers' return logic and output completeness;
they were not separately captured by the combined shell command, which continued
to the profile analysis and returned zero. Final analyses and validation run with
failure propagation and their actual command results are retained separately.
