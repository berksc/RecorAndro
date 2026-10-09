# RecorAndro

Android-first, local-only project. Step 1.1 provides Python configuration and
environment diagnostics. Step 1.2 adds conservative storage preflight and verified
immutable audio import. Step 2.1 adds managed-original ffprobe inspection.
Step 2.2 adds Auto/Force/Off normalization with full selected-stream decoding
and verified independent AAC/M4A artifacts for useful gain. Step 2.2 actual
Redmi validation is completed and accepted: **FINAL PASS**, with 125/125 Android
tests (exit code 0) and Python compilation PASS. Quiet Auto and usable Force
fixtures applied gain; usable Auto and quiet Off fixtures succeeded without a
derivative. The existing real lecture completed with `auto_already_usable_level`,
gain 0 and no normalized derivative, errors or warnings. Its original size and
SHA-256 were independently verified unchanged; session state remains `imported`
and successful normalization metadata was persisted and verified. See
[accepted Android normalization evidence](docs/SESSION_NORMALIZATION.md#accepted-android-validation--final-pass).

From the repository root (Python >=3.10), set an explicit owned data directory:

```sh
export RECORANDRO_DATA_ROOT="$HOME/recorandro-data"
python -m recorandro doctor --json
python -m unittest discover -s tests -v
python tools/check_media_capabilities.py
```

See [Termux installation and actual-device capability verification](docs/TERMUX_ENVIRONMENT.md).
Step 1.1 actual Redmi/Termux capability validation is accepted in
[its report](docs/STEP_1_1_REPORT.md). Step 1.2 actual-device validation is completed:
47/47 Android tests and small Unicode WAV / real lecture M4A imports passed.
This validates immutable import. Step 2.1 actual-device validation is completed
and accepted: **FINAL PASS**, with 84/84 Android tests and successful inspection
of the existing real lecture session without re-import. Duration was independently
confirmed and original integrity verified before/after; decoder eligibility
remains unverified. See [accepted inspection evidence](docs/SESSION_INSPECTION.md).

Temporary technical import CLI (from the repository root):

```sh
python -m recorandro import-audio "$HOME/lecture-audio.m4a" --profile lecture --provision-seconds 7200 --archive profile
```

`--provision-seconds` is a required user-supplied duration budget, not measured
media duration. No default Lecture archive choice is made. See
[session import, storage formula and Termux validation](docs/SESSION_IMPORT.md).

Inspect an existing imported session using its stored session identifier:

```sh
python -m recorandro inspect-session "$session_id"
# Explicit retry after a failed/interrupted inspection:
python -m recorandro inspect-session "$session_id" --retry
```

This probes only the verified managed original, preserves imported bytes, and
returns JSON metadata, integrity outcomes, warnings and processing blockers.
Probe success does not certify full decoding or normalization readiness. See
[inspection schema, safeguards and existing real-lecture Termux validation](docs/SESSION_INSPECTION.md).

Evaluate normalization for an already inspected session (Auto is the default):

```sh
python -m recorandro normalize-session "$session_id"
python -m recorandro normalize-session "$session_id" --mode force
python -m recorandro normalize-session "$session_id" --mode off
# Explicit retry after failed/interrupted normalization:
python -m recorandro normalize-session "$session_id" --mode auto --retry
```

Successful no-gain decisions retain the original and create no normalized audio.
New boosts receive attempt-owned verified outputs; prior outputs are preserved.
Input loudness fields are under `normalization.input_levels`, not `measurement`.
See [normalization policy, host and accepted Android evidence, transfer and existing-lecture validation](docs/SESSION_NORMALIZATION.md).
Analyze and save a nominal segmentation plan from that completed working source:

```sh
python -m recorandro plan-session "$session_id"               # Auto default
python -m recorandro plan-session "$session_id" --mode force
python -m recorandro plan-session "$session_id" --mode off
python -m recorandro plan-session "$session_id" --retry        # Failed/interrupted plan
```

This performs read-only quiet analysis when multiple useful parts are feasible;
it never normalizes again or cuts/exports audio. The fixed count and 600–1620 s
multi-part bounds preserve complete source coverage without tiny tails. See
[frozen planning policy, metadata, host fixtures and Android procedure](docs/SESSION_SEGMENTATION.md).
Step 2.3 actual-device validation is completed and accepted: **FINAL PASS**,
with 170/170 Android tests, zero failures or skips, and Python compilation PASS
on the Redmi Note 10 Pro in ordinary non-root Termux. The existing lecture
`d0c39956c17943299dd17e67bf6d1d68` used its verified managed original after
normalization Auto's no-gain outcome. Auto and Force planned three nominal parts
of 1500 / 1500 / 691.787029 seconds; Off covered the full 3691.787029-second source
in one part. There were no qualifying quiet intervals; both Auto boundaries used
`fallback_target`, and repeated Auto plans had identical nominal boundaries.
All modes covered source end without errors, silence removal, export, cutting
or re-normalization. See
[accepted Android planning evidence](docs/SESSION_SEGMENTATION.md#accepted-android-validation--step-23-final-pass).

Step 2.4 adds verified audio export from the **latest completed saved plan**:

```sh
python -m recorandro export-session "$session_id"
# Explicit retry after a failed/interrupted export:
python -m recorandro export-session "$session_id" --retry
```

It verifies the plan hash and current working-source revision, applies the frozen
end-only five-second overlap, then independently encodes and fully decodes each
part before atomic publication. Compatible full-length one-part AAC/M4A or MP3
results are independent exact byte copies. Completed parts survive failures and
are verified again before reuse. No replanning or normalization occurs.
See [export policy, ownership/retry metadata, host evidence and existing-lecture Android validation](docs/SESSION_EXPORT.md).
Step 2.4 actual-device validation is completed and accepted: **FINAL PASS**,
with 203/203 Android tests PASS and Python compilation PASS. The existing
3691.787029-second lecture exported three verified AAC-LC/M4A parts with measured
durations of 1505, 1505 and 691.787007 seconds. Five-second overlap, no gaps and
complete source-end coverage were verified; independent SHA-256 and size checks
passed for all three outputs and the original. Manual listening verification
was explicitly waived; no listening PASS is claimed. See
[accepted Android export evidence](docs/SESSION_EXPORT.md#accepted-android-validation--step-24-final-pass).
ZIP packaging and final manifests remain unimplemented. No commit/push or
subsequent step without separate authorization.
