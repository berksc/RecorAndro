# Step 4.2 — part packages and optional full archive

Candidate based on accepted Step 4.1 commit
`2d6110057b51286f8819395a81d85dc205a81135`, verified at HEAD with a clean tree.
Preserve the frozen media/behavior contracts. Packaging reads verified existing
artifacts; it performs no import, normalization, planning, audio export or visuals.

## Canonical part ZIP specification

For each current verified part, `part_NN.zip` contains exactly these root members:

```text
manifest.json
manifest.md
part_NN.m4a                  # part_01.mp3 for the accepted single MP3 copy path
```

No original-storage audio alias, photos, large lecture report, private logs or
unrelated files are included. Audio-only packages are canonical and complete.
Part manifests retain Step 4.1's exact bytes and global/nominal/export/local
timeline semantics. Existing documents' packaging/archive fields describe their
Step 4.1 generation phase; current live outcomes are in session.json/status.

Policy `stored_zip_v1`: lexicographically sorted member paths, UTF-8 encoding
where required, ZIP_STORED (no compressor/version dependence), fixed ZIP DOS time
1980-01-01 00:00:00, Unix regular-file mode 0644, no comments or arbitrary extra
metadata, ZIP64 sizes when needed. Writer uses ZIP64-capable local headers.
There are no directory entries, symlinks, absolute paths, traversal, backslashes,
drive prefixes, control characters, duplicate names or unknown members.

Before generation, source hashes/sizes are checked through the existing owned
file verifier. Input identity is checked while streaming and again after writing.
ZIP verification checks the exact ordered member list, metadata policy, readable
content, CRC at EOF, size and SHA-256 against every source. The complete ZIP gets
its own size/SHA-256. Successful creation alone never establishes verification.

## Publication, registry, state and retry

Existing `.inspection.lock`, pinned `OwnedDirectory`, atomic metadata writer,
fsync and no-replace publication remain the only owners. ZIPs are generated under
`temp/package_generation-<id>/` and published under
`generated/package_generation/<attempt>/part_NN.zip`.

The `package_generation` canonical pointer references an atomic attempt journal
at the same attempt's session.json. Journal schema 1 carries policy, source
revision, status/times, storage check, errors and exact output file identities.
It records verified ZIP size/hash as `publication_ready` **before** final
publication, enabling recovery after a process death between publication and
metadata update. Canonical state advances to `packaged` only for a succeeded,
current journal and a fully verified required set. Individually verified sibling
ZIPs remain registry artifacts even when the set is incomplete.

The required frontier is now `packaged`; recovery `complete` means implemented
audio/documents/packages only. `complete` and `archived_or_skipped` persistent
states remain unused. Missing/corrupt packages regress packaging to verified
manifests; they do not invalidate audio/documents. `package-session` and
`retry ... package_generation` reuse verified siblings and regenerate only bad
ZIPs. Unchanged inputs regenerate byte-identical ZIP content. Completed calls
and repeated resume make no metadata or artifact writes.

```sh
python -m recorandro package-session "$session_id"
python -m recorandro retry "$session_id" package_generation
python -m recorandro archive-session "$session_id" --decision on
python -m recorandro archive-session "$session_id" --decision off
python -m recorandro retry "$session_id" full_archive
```

Resume adds required packaging after manifests. It also attempts a full archive
when a recorded decision is ON, without changing normalization/segmentation modes.
Repeated resume skips a verified archive or a recorded storage denial; explicit
archive/retry rechecks space. Optional archive errors are nonblocking for the core.

## Optional archive decision and compact layout

There is **no Lecture ON fallback**. Initial import's resolved archive choice is
honored: `requested` becomes `explicit_on`, `not_requested` becomes `explicit_off`,
and `unresolved` stays unresolved. Provenance distinguishes an explicit import
choice from an explicitly configured local profile setting. A later archive
command records `archive_request` with on/off and explicit-command provenance.
Unresolved/off decisions generate no archive. Outcomes include not_generated,
pending, archived, skipped_due_to_storage and failed_nonblocking.

`full_archive.zip` contains current verified session-relative paths:

```text
session.json                              # consistent recovery snapshot
originals/audio/<managed original>
generated/normalization/<current>/normalized.m4a    # only if applied
generated/normalization/<current>/session.json
generated/segmentation/<current>/session.json
generated/exports/<current>/session.json
generated/exports/<current-or-reused>/part_NN.m4a
generated/manifests/<current-or-reused>/manifest.json
generated/manifests/<current-or-reused>/manifest.md
generated/manifests/<current-or-reused>/processing_report.md
generated/manifests/<current>/session.json
generated/manifests/<current-or-reused>/parts/part_NN/manifest.json
generated/manifests/<current-or-reused>/parts/part_NN/manifest.md
```

Only referenced current verified records/files are included, never directory
scans, temporary/orphan files, stale revisions, previous archives, part ZIPs,
locks, external sources or unrelated sessions. Future managed original photos
may be retained when the existing registry actually verifies them; this step
does not import, index or recover photos and never requires them.

Snapshot paths match the original current references so accepted source, plan,
export and document evidence can be reloaded. Its state is `manifested`, package
status is `excluded_rebuild_required`, archive status is `snapshot_before_archive`.
Package/archive pointers and volatile updated_at are removed; registry entries
are limited to included verified audio/documents and unhashed canonical metadata.
The snapshot never claims the archive being generated already completed. Rebuild
part ZIPs after restoration from retained audio/documents; no media reprocessing
is needed. Tests reload an extracted snapshot with the existing status verifier.

The archive uses the same deterministic ZIP policy and publication journal as
parts, under `generated/full_archive/<attempt>/full_archive.zip`. Its input
revision excludes package/archive attempts, so rebuilding an identical package
does not obsolete a still-valid compact archive. Archive creation/verification
does not modify protected originals or previously accepted audio/documents.

## Duplication and actual-size second-stage preflight

Let O=original bytes, N=normalized bytes when applied, P=exported part bytes,
D=current document/stage-report bytes, Z=part ZIP bytes. Parts use independent
delivery copies as the frozen media contract requires; packaging does not alias
originals. ZIP_STORED gives Z approximately P plus small part-manifest/header
overhead. The compact archive adds approximately O+N+P+D plus snapshot/headers.
Live files after archiving total approximately O+N+P+D+Z+(O+N+P+D).
Embedding Z as well would add roughly another P and is deliberately avoided.
Normalized audio and independently generated parts remain separate even when
their hashes match, preserving the current recoverable source references.

The second-stage check measures free bytes on the same owned filesystem and
uses actual verified member sizes, including the deterministic snapshot:

```text
payload = sum(actual included member bytes)
output_bound = payload + sum(1024 + 2*UTF8_member_name_bytes) + 65536 per ZIP
reserve = max(256 MiB, ceil(output_bound/5))
required_free = output_bound + reserve
temporary_generation_peak = output_bound
publication_extra_copy = 0
```

Existing artifacts already consume disk space, so they are not subtracted again
from measured free bytes. Their current size total is reported separately.
Old/orphan files are likewise reflected in free space. Same-filesystem atomic
move changes the temporary ZIP into its final name without another whole copy.
The check repeats before each remaining ZIP. These conservative reserve/overhead
values are provisioning policy, not newly frozen media constants or a guarantee
against concurrent disk exhaustion/power loss. Archive storage denial records
required/free bytes and skipped_due_to_storage; no canonical partial archive is
published, no files are deleted, and packages remain successful.

Original audio and canonical session metadata stay protected. Normalized audio,
parts, manifests/reports, part ZIPs and full archives are regenerable. ZIP registry
entries include size/hash, manifest source artifact ID, input revision, times and
verified status. No recursive session.json/archive hashing is introduced.

## Redmi validation and storage measurements

Transfer the reviewed **source-review ZIP** to a fresh Termux source directory;
preserve the accepted deployment and existing managed data root. It is a developer
transfer, separate from this production ZIP capability. Review-info carries exact
source hashes. Run ordinary Termux, without root:

```sh
python -m compileall -q recorandro tests scripts
RECORANDRO_DATA_ROOT="$TMPDIR/recorandro-step4.2-unrelated-test-root" python -m unittest discover -s tests -v > android-step4.2-tests.txt 2>&1
PYTHONPATH=tests env -u RECORANDRO_DATA_ROOT python -m unittest test_packages -v > android-step4.2-packages-unset.txt 2>&1
```

Tests include dedicated disposable sessions and controlled child death after
part ZIP publication. Duplicate processing is rejected while its lock is active;
killing/reaping only that child releases the lock and resume reuses its ZIP.
Do not interrupt or intentionally corrupt the accepted lecture.
To run that controlled case by itself:

```sh
PYTHONPATH=tests env -u RECORANDRO_DATA_ROOT python -m unittest test_packages.PackageTests.test_controlled_child_death_after_part_zip_publication -v
```

Use the accepted RECORANDRO_DATA_ROOT setting (or the existing --config file;
normal environment precedence still applies). The following validator invokes
only packaging/archive, with no media stage calls. For a config-only deployment,
use the config's actual existing data_root path in the df commands and pass
--config to the validator and before the CLI subcommand:

```sh
sid=d0c39956c17943299dd17e67bf6d1d68
original_sha=9a3843145f2978defbf6a1afcb2b272abf77cbc520598573861b84682e5294ab
df -k "$RECORANDRO_DATA_ROOT" > android-space-before-packages.txt
python scripts/validate_packages.py --session-id "$sid" --expected-original-sha256 "$original_sha" > android-packages.json
df -k "$RECORANDRO_DATA_ROOT" > android-space-before-archive.txt
python scripts/validate_packages.py --session-id "$sid" --expected-original-sha256 "$original_sha" --archive-on > android-archive-measurements.json
df -k "$RECORANDRO_DATA_ROOT" > android-space-after-archive.txt
python -m recorandro status "$sid" > android-step4.2-status.json
```

The `--archive-on` command is a manual explicit request, not a default selection.
Record ALL_PASS, three package sizes/member lists, archive size/member tree,
free bytes before/after, command elapsed time and additional archive duplication
bytes/ratio from JSON. Source, normalized/part audio and all prior document/stage
hashes must remain unchanged. Repeated successful packaging/archive must preserve
ZIP hashes and session.json bytes. Insufficient space is a legitimate nonfatal
measurement; retain reported required/free values and all existing outputs.

**Lecture Full Archive default remains OPEN**, pending these real-device results
and later Part 3 decisions. Independent review, real Redmi acceptance and explicit
FINAL PASS are required before commit/push. No visuals, final UI or Part 3 work.
