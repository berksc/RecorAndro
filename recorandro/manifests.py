"""Deterministic operational documents over the existing verified audio chain.

The attempt journal uses the existing writer/lock/publication primitive. It is
not a manifest input: documents never hash themselves or canonical session.json.
"""

from contextlib import ExitStack
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import html
import json
import os
import uuid

from .storage import OwnedDirectory, StorageError
from .inspection import _existing_child, _inspection_lock
from .session_state import _read, _validate, _folder, _check_file, artifact_entry, UUID
from .exports import _json_blob, MAX_EXPORT_BYTES

SCHEMA_VERSION = 1
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
TIMELINE_NOTE = ('GLOBAL uses the immutable source timeline origin. Nominal intervals own lecture content once; '
                 'export intervals extend the preceding end by five seconds, without moving the next start. '
                 'LOCAL is playback within this part; overlap adds no lecture content.')


class ManifestFailure(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def require(condition, message):
    if not condition:
        raise ManifestFailure('invalid_manifest_evidence', message)


def json_bytes(model):
    return (json.dumps(model, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).replace('`', '\\u0060') + '\n').encode('utf-8')


def human(seconds):
    milliseconds = int((Decimal(str(seconds)) * 1000).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}'


def text(value):
    # Untrusted filenames/title/course remain data, never Markdown structure.
    value = html.escape(str(value), quote=True).replace('|', '&#124;')
    return ''.join(c if ord(c) >= 32 else ' ' for c in value).replace('`', '&#96;')


def summary(media):
    return dict(container=media.get('container_format'),
                **{k: media.get(k) for k in ('audio_codec', 'sample_rate', 'channels', 'duration_seconds')})


def canonical_model(directory, record, audio_view):
    """No inferred geometry; callers supply the existing audio evidence projection."""
    require(audio_view['last_successful_state'] in ('segments_exported', 'manifested'),
            'Current original, source, plan and complete export set must verify first.')
    with ExitStack() as stack:
        plan_folder, _ = _folder(stack, directory, record['segmentation']['record_path'])
        planning, plan_digest = _json_blob(plan_folder, MAX_EXPORT_BYTES)
        export_folder, _ = _folder(stack, directory, record['audio_export']['record_path'])
        exported, export_digest = _json_blob(export_folder, MAX_EXPORT_BYTES)
    require(plan_digest == record['segmentation']['record_sha256'] and
            export_digest == record['audio_export']['record_sha256'], 'Dependencies changed during document generation.')
    plan, norm = planning['plan'], record['normalization']
    parts = []
    for p in exported['parts']:
        part = {k: p[k] for k in ('part_index', 'filename', 'sha256', 'size_bytes',
                'global_start_seconds', 'global_end_seconds', 'nominal_start_seconds', 'nominal_end_seconds')}
        part.update(schema_version=SCHEMA_VERSION, session_id=record['session_id'],
                    media=summary(p['media']), local_duration_seconds=p['duration_seconds'],
                    local_start_seconds=0, local_end_seconds=p['duration_seconds'],
                    global_start_human=human(p['global_start_seconds']), global_end_human=human(p['global_end_seconds']),
                    nominal_start_human=human(p['nominal_start_seconds']), nominal_end_human=human(p['nominal_end_seconds']),
                    overlap_before_seconds=p['overlap_before_seconds'], overlap_after_seconds=p['overlap_after_seconds'],
                    source_artifact=p['source_artifact'], timeline_note=TIMELINE_NOTE)
        parts.append(part)
    warnings = list(record.get('warnings', []))
    for stage in ('inspection', 'normalization'):
        warnings.extend(record.get(stage, {}).get('warnings', []))
    warnings.extend(planning.get('warnings', []))
    warnings.extend(exported.get('warnings', []))
    warnings.extend(audio_view['progress_warnings'])
    require(all(isinstance(w, str) for w in warnings), 'Warning metadata must contain text codes.')
    warnings = sorted(set(w for w in warnings if w != 'media_eligibility_pending'))
    artifacts = []
    for key, entry in sorted(audio_view['artifact_registry'].items()):
        if entry['status'] == 'verified' and entry['type'] not in ('manifest', 'report'):
            artifacts.append({k: entry[k] for k in ('artifact_id', 'type', 'relative_path', 'sha256',
                             'size_bytes', 'source_artifact_id', 'revision_id', 'classification', 'status')})
    model = dict(schema_version=SCHEMA_VERSION, session_id=record['session_id'], profile=record['profile'],
                 created_at=record['created_at'],
                 original={k: record['audio'][k] for k in ('original_filename', 'size_bytes', 'sha256')},
                 probe=summary(record['inspection']['media']),
                 normalization={'requested_mode': norm['mode_requested'],
                    'result': 'applied' if norm['normalization_applied'] else 'skipped', 'reason': norm['decision'],
                    'gain_db': norm['gain_db'],
                    'source_artifact': dict(artifact_id='original_audio', **{k: record['audio'][k] for k in
                                           ('managed_path', 'size_bytes', 'sha256')}),
                    'normalized_artifact': dict(artifact_id='normalized_audio:' + norm['attempt_id'],
                        **{k: norm['working_source'][k] for k in ('managed_path', 'size_bytes', 'sha256')},
                        media=summary(norm['working_source']['media'])) if norm['normalization_applied'] else None},
                 segmentation={k: plan.get(k) for k in ('policy_version', 'mode_requested', 'mode_fulfilled',
                    'decision', 'plan_kind', 'source_duration_seconds', 'target_seconds', 'search_window_seconds',
                    'useful_multi_part_seconds', 'tiny_part_avoidance_adjustments')},
                 source_revisions={'inspection': record['inspection']['attempt_id'],
                    'normalization': norm['attempt_id'], 'segmentation': audio_view['segmentation_plan_identity'],
                    'export': {k: record['audio_export'][k] for k in ('attempt_id', 'record_path', 'record_sha256')}},
                 timeline={'origin': 'immutable_original_source', 'original_duration_seconds': record['inspection']['media']['duration_seconds'],
                    'working_source_end_seconds': plan['source_duration_seconds'], 'note': TIMELINE_NOTE,
                    'ownership_duration_seconds': plan['source_duration_seconds']},
                 visual_count=record['visual_count'], visual_status='none' if record['visual_count'] == 0 else
                    record.get('visual_status', 'pending'),
                 artifacts=artifacts, parts=parts,
                 storage_preflight={'import': record['storage_preflight'], 'normalization': norm.get('storage_preflight'),
                                    'audio_export': exported.get('storage_preflight')},
                 integrity={'original_verified': True, 'working_source_verified': True,
                            'all_parts_verified': True, 'coverage': exported['coverage']},
                 completion={'audio': 'segments_exported', 'documents': 'manifested',
                             'packaging': 'not_implemented', 'archive': 'not_implemented', 'globally_complete': False},
                 warnings=warnings, errors=[])
    model['segmentation'].update(part_count=len(parts), overlap_seconds=5)
    for key in ('title', 'course'):
        if record.get(key) is not None:
            require(isinstance(record[key], str), 'Supplied title/course must be text.')
            model[key] = record[key]
    return model


def part_table(parts):
    rows = ['| Part | Filename | Nominal ownership (GLOBAL) | Export (GLOBAL) | LOCAL duration (s) | Overlap before / after (s) |',
            '| --- | --- | --- | --- | --- | --- |']
    for p in parts:
        rows.append(f"| {p['part_index']} | {text(p['filename'])} | {p['nominal_start_human']}–{p['nominal_end_human']} | "
                    f"{p['global_start_human']}–{p['global_end_human']} | {p['local_duration_seconds']} | "
                    f"{p['overlap_before_seconds']} / {p['overlap_after_seconds']} |")
    return '\n'.join(rows)


def markdown(model, *, part=False):
    # The embedded canonical JSON makes every field auditable with exact parity.
    heading = f"Part {model['part_index']} manifest" if part else 'Session manifest'
    body = [f'# {heading}', '', f"Session: {text(model['session_id'])}", '', TIMELINE_NOTE, '']
    if not part:
        body.extend([part_table(model['parts']), ''])
    body.extend(['## Canonical data', '', '```json', json_bytes(model).decode().rstrip('\n'), '```', ''])
    return '\n'.join(body).encode('utf-8')


def report_markdown(model):
    n, s, p = model['normalization'], model['segmentation'], model['probe']
    lines = ['# Processing report', '', f"Session: {text(model['session_id'])}; profile: {text(model['profile'])}.", '']
    for key in ('title', 'course'):
        if key in model:
            lines.extend([f'{key.capitalize()}: {text(model[key])}', ''])
    lines.extend(['## Input', '', f"{text(model['original']['original_filename'])}; {model['original']['size_bytes']} bytes.",
                  f"SHA-256: {model['original']['sha256']}", '', '## Storage preflight', '',
                  '```json', json_bytes(model['storage_preflight']).decode().rstrip(), '```', '',
                  '## Probe', '', f"Container: {text(p['container'])}; codec: {text(p['audio_codec'])}; "
                  f"sample rate: {p['sample_rate']}; channels: {p['channels']}; source duration: {p['duration_seconds']} s.", '',
                  '## Normalization', '', f"{n['requested_mode']}: {n['result']}; {text(n['reason'])}; gain {n['gain_db']} dB.", '',
                  '## Segmentation', '', f"{s['mode_requested']}: {s['plan_kind']}; {text(s['decision'])}; "
                  f"{s['part_count']} part(s); target {s['target_seconds']} s; window {s['search_window_seconds']} s.", '',
                  f"Tiny-part adjustments: {text(json.dumps(s['tiny_part_avoidance_adjustments'], sort_keys=True))}", '',
                  TIMELINE_NOTE, '', part_table(model['parts']), '', '## Integrity', '',
                  f"Original, working source and {s['part_count']}/{s['part_count']} parts verified by size and SHA-256. "
                  'Accepted export verification and coverage passed. Documents manifested; packaging/archive unimplemented.', ''])
    if model['visual_count']:
        lines.extend(['## Visuals', '', f"{model['visual_count']} attachment(s); status: {text(model['visual_status'])}.", ''])
    lines.extend(['## Warnings / errors', '', 'Warnings: ' + (', '.join(text(w) for w in model['warnings']) or 'none'),
                  'Errors: ' + (', '.join(text(e) for e in model['errors']) or 'none'), ''])
    return '\n'.join(lines).encode('utf-8')


def documents(model):
    result = {'manifest.json': json_bytes(model), 'manifest.md': markdown(model),
              'processing_report.md': report_markdown(model)}
    for part in model['parts']:
        prefix = f"parts/part_{part['part_index']:02}/"
        result[prefix + 'manifest.json'] = json_bytes(part)
        result[prefix + 'manifest.md'] = markdown(part, part=True)
    require(all(0 < len(blob) <= MAX_DOCUMENT_BYTES for blob in result.values()), 'Document exceeds bounded size.')
    return result


def fingerprint(model):
    return hashlib.sha256(json_bytes(model)).hexdigest()


def saved_report(directory, record):
    pointer = record.get('manifest_generation')
    require(isinstance(pointer, dict) and isinstance(pointer.get('attempt_id'), str) and UUID.fullmatch(pointer['attempt_id']),
            'Invalid manifest attempt.')
    path = f"generated/manifests/{pointer['attempt_id']}/session.json"
    require(pointer.get('record_path') == path, 'Manifest journal path differs from its revision.')
    with ExitStack() as stack:
        folder, _ = _folder(stack, directory, path)
        saved, digest = _json_blob(folder, MAX_DOCUMENT_BYTES)
    require(saved.get('session_id') == record['session_id'] and saved.get('attempt_id') == pointer['attempt_id']
            and saved.get('schema_version') == SCHEMA_VERSION, 'Manifest journal identity differs.')
    return saved, digest


def matches(stack, directory, entry, blob):
    require(entry.get('sha256') == hashlib.sha256(blob).hexdigest() and entry.get('size_bytes') == len(blob),
            'Document differs from canonical content.')
    path = entry.get('relative_path', '')
    require(path.startswith('generated/manifests/') and len(path.split('/')) >= 4 and UUID.fullmatch(path.split('/')[2]),
            'Document must belong to an owned manifest attempt.')
    _check_file(stack, directory, entry)


def verify_stage(directory, record, audio_view):
    model = canonical_model(directory, record, audio_view)
    expected = documents(model)
    saved, digest = saved_report(directory, record)
    pointer = record['manifest_generation']
    require(pointer.get('status') == saved.get('status') == 'manifest_succeeded' and pointer.get('record_sha256') == digest,
            'Manifest journal is not a current completed revision.')
    require(pointer.get('source_revision') == saved.get('source_revision') == fingerprint(model), 'Manifest source revision is stale.')
    require(set(saved.get('files', {})) == set(expected), 'Manifest set is incomplete.')
    entries = {}
    with ExitStack() as stack:
        for logical, blob in expected.items():
            entry = saved['files'][logical]
            require(entry.get('status') == 'verified', 'Manifest member is not verified.')
            matches(stack, directory, entry, blob)
            aid = f"manifest:{saved['attempt_id']}:{logical}"
            entries[aid] = artifact_entry(aid, 'report' if logical == 'processing_report.md' else 'manifest',
                entry['relative_path'], status='verified', source=f"exports_report:{record['audio_export']['attempt_id']}",
                size=len(blob), sha256=entry['sha256'], created_at=entry.get('created_at', saved['created_at']),
                verified_at=saved['completed_at'], revision=saved['source_revision'])
        path = pointer['record_path']
        folder, leaf = _folder(stack, directory, path)
        aid = f"manifest_report:{saved['attempt_id']}"
        entries[aid] = artifact_entry(aid, 'report', path, status='verified',
            source=f"exports_report:{record['audio_export']['attempt_id']}", size=folder.info(leaf).st_size,
            sha256=digest, created_at=saved['created_at'], verified_at=saved['completed_at'], revision=saved['source_revision'])
    return entries


def generate_manifests(config, session_id, *, retry=False, _lock_token=None):
    """Idempotent generation/adoption. Invalid derived documents never touch audio."""
    from .session_state import project_session
    require(isinstance(session_id, str) and UUID.fullmatch(session_id), 'Invalid session identifier.')
    with ExitStack() as stack:
        root = stack.enter_context(OwnedDirectory.root(config.data_root))
        sessions = _existing_child(stack, root, 'sessions')
        directory = _existing_child(stack, sessions, session_id)
        stack.enter_context(_inspection_lock(directory, _lock_token))
        record = _read(directory)
        _validate(record, session_id)
        view = project_session(directory, record, _audio_only=True)
        model = canonical_model(directory, record, view)
        blobs, revision = documents(model), fingerprint(model)
        prior = None
        try:
            verify_stage(directory, record, view)
            return dict(record['manifest_generation'], reused=True)
        except (ValueError, OSError, KeyError, TypeError):
            pass
        try:
            prior, _ = saved_report(directory, record)
            if prior.get('source_revision') != revision:
                prior = None
        except (ValueError, OSError, KeyError, TypeError):
            pass
        # Crash after full file publication: adopt the current journal's exact
        # model-matching members, without creating a new attempt or touching audio.
        reusable = {}
        if prior:
            for logical, blob in blobs.items():
                try:
                    entry = prior['files'][logical]
                    matches(stack, directory, entry, blob)
                    reusable[logical] = dict(entry, status='verified')
                except (ValueError, OSError, KeyError, TypeError):
                    continue
        generated = stack.enter_context(directory.child('generated'))
        manifest_root = stack.enter_context(generated.child('manifests'))
        if prior and len(reusable) == len(blobs):
            attempt = prior
            output = _existing_child(stack, manifest_root, attempt['attempt_id'])
            attempt['files'] = reusable
        else:
            aid = uuid.uuid4().hex
            output = stack.enter_context(manifest_root.child(aid, exclusive=True))
            now = datetime.now(timezone.utc).isoformat()
            attempt = {'schema_version': SCHEMA_VERSION, 'session_id': session_id, 'attempt_id': aid,
                       'created_at': now, 'completed_at': None, 'status': 'manifest_pending',
                       'source_revision': revision, 'files': {}}
            for logical, blob in blobs.items():
                attempt['files'][logical] = reusable.get(logical) or {
                    'relative_path': f'generated/manifests/{aid}/{logical}', 'size_bytes': len(blob),
                    'sha256': hashlib.sha256(blob).hexdigest(), 'status': 'pending', 'created_at': now}
        def persist():
            output.atomic_json(attempt)
            saved, digest = _json_blob(output, MAX_DOCUMENT_BYTES)
            record['manifest_generation'] = {k: saved[k] for k in
                ('attempt_id', 'status', 'source_revision', 'created_at', 'completed_at')}
            record['manifest_generation'].update(record_path=f"generated/manifests/{attempt['attempt_id']}/session.json",
                                                  record_sha256=digest)
            directory.atomic_json(record)
        attempt['status'] = 'manifest_pending'
        persist()  # Full-set intent precedes the first no-replace publication.
        temporary_root = stack.enter_context(directory.child('temp'))
        staging = stack.enter_context(temporary_root.child('manifests-' + uuid.uuid4().hex, exclusive=True))
        for index, (logical, blob) in enumerate(blobs.items()):
            if logical in reusable:
                continue
            target = output
            for component in logical.split('/')[:-1]:
                target = stack.enter_context(target.child(component))
            name = f'pending-{index}'
            with os.fdopen(staging.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL), 'wb') as stream:
                stream.write(blob)
                stream.flush()
                os.fsync(stream.fileno())
            entry = attempt['files'][logical]
            _check_file(stack, directory, dict(entry, relative_path=f"temp/{staging.path.name}/{name}"))
            staging.publish(name, logical.split('/')[-1], target)
            matches(stack, directory, entry, blob)
            entry['status'] = 'verified'
        attempt.update(status='manifest_succeeded', completed_at=attempt.get('completed_at') or datetime.now(timezone.utc).isoformat())
        # Reader verification on canonical write requires every file/hash, exact
        # model revision and succeeded journal before exposing manifested state.
        persist()
        return dict(record['manifest_generation'], reused=False)
