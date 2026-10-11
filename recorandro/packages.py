"""Deterministic stored ZIPs over current evidence, using the existing session owner."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import os
from pathlib import PurePosixPath
import stat
import uuid
import zipfile

from .storage import OwnedDirectory, MIB
from .inspection import _existing_child, _inspection_lock
from .session_state import _read, _validate, _folder, _check_file, artifact_entry, UUID
from .manifests import canonical_model, json_bytes, saved_report
from .exports import _json_blob

POLICY = 'stored_zip_v1'
DATE = (1980, 1, 1, 0, 0, 0)
ATTR = 0o100644 << 16
LIMIT = 32 * MIB
BLOCK = MIB


class PackageFailure(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def require(condition, message):
    if not condition:
        raise PackageFailure('invalid_package_evidence', message)


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def safe_member(name):
    require(isinstance(name, str) and name and '\\' not in name and ':' not in name and
            not name.startswith('/') and all(p not in ('', '.', '..') for p in name.split('/')) and
            not any(ord(c) < 32 or ord(c) == 127 for c in name), 'Unsafe ZIP member name.')
    require(str(PurePosixPath(name)) == name, 'Noncanonical ZIP member name.')


def member(entry):
    return {k: entry[k] for k in ('relative_path', 'size_bytes', 'sha256')}


def inline(blob):
    return {'size_bytes': len(blob), 'sha256': digest(blob), 'content': blob}


def revision(specs):
    return digest(json_bytes({name: {path: {k: v for k, v in entry.items() if k != 'content'}
                                    for path, entry in sorted(members.items())}
                              for name, members in sorted(specs.items())}))


def package_specs(directory, record, view):
    require(view['last_successful_state'] == 'manifested', 'Current complete manifests and audio must verify first.')
    model = canonical_model(directory, record, view)
    saved, _ = saved_report(directory, record)
    result = {}
    registry = view['artifact_registry']
    for part in model['parts']:
        index = part['part_index']
        aid = f"audio_part:{record['audio_export']['attempt_id']}:{index}"
        prefix = f'parts/part_{index:02}/'
        result[f'part_{index:02}.zip'] = {
            part['filename']: member(registry[aid]),
            'manifest.json': member(saved['files'][prefix + 'manifest.json']),
            'manifest.md': member(saved['files'][prefix + 'manifest.md'])}
    return result


def archive_decision(record):
    selected = record.get('archive_request')
    if selected is not None:
        require(isinstance(selected, dict) and selected.get('decision') in ('explicit_on', 'explicit_off'),
                'Invalid explicit archive decision.')
        return dict(selected)
    initial = record.get('storage_preflight', {}).get('archive', {})
    resolved = initial.get('resolved')
    require(resolved in ('requested', 'not_requested', 'unresolved'), 'Archive selection must be explicitly resolved.')
    return {'decision': {'requested': 'explicit_on', 'not_requested': 'explicit_off', 'unresolved': 'unresolved'}[resolved],
            'provenance': initial.get('provenance')}


def archive_specs(record, documents_view):
    # Keep exact session-relative locations so current source/report references
    # remain recoverable. ZIPs are rebuildable and deliberately not nested.
    snapshot = deepcopy(documents_view)
    for key in ('package_generation', 'full_archive', 'updated_at'):
        snapshot.pop(key, None)
    snapshot['artifact_registry'] = {key: entry for key, entry in snapshot['artifact_registry'].items()
                                    if entry['status'] in ('verified', 'canonical') and
                                    entry['type'] not in ('zip_package', 'full_archive')}
    snapshot.update(current_state='manifested', last_successful_state='manifested', active_stage=None,
                    package_status={'status': 'excluded_rebuild_required'},
                    archive_status={'status': 'snapshot_before_archive', 'decision': 'explicit_on'})
    result = {'session.json': inline(json_bytes(snapshot))}
    for entry in snapshot['artifact_registry'].values():
        if entry['status'] == 'verified':
            require(entry['relative_path'] not in result, 'Duplicate archive source path.')
            result[entry['relative_path']] = member(entry)
    return {'full_archive.zip': result}


def storage_check(specs, free_bytes, *, existing_artifact_bytes):
    require(type(free_bytes) is int and free_bytes >= 0, 'Invalid available storage measurement.')
    payload = sum(e['size_bytes'] for members in specs.values() for e in members.values())
    count = sum(len(members) for members in specs.values())
    # ZIP_STORED cannot expand media through compression. UTF-8 names, ZIP64,
    # central/local headers and footer get deliberately generous allowances.
    estimate = payload + sum(1024 + 2 * len(n.encode('utf-8')) for m in specs.values() for n in m) + 65536 * len(specs)
    reserve = max(256 * MIB, (estimate + 4) // 5)
    required = estimate + reserve
    return {'policy': 'actual_stored_zip_v1', 'existing_artifact_bytes': existing_artifact_bytes,
            'member_payload_bytes': payload, 'member_count': count, 'estimated_output_bytes': estimate,
            'temporary_generation_peak_bytes': estimate, 'publication_extra_copy_bytes': 0,
            'reserve_bytes': reserve, 'required_free_bytes': required, 'free_bytes': free_bytes,
            'decision': 'allow' if free_bytes >= required else 'deny'}


def _open(stack, directory, entry):
    folder, leaf = _folder(stack, directory, entry['relative_path'])
    stream = stack.enter_context(os.fdopen(folder.open(leaf, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0)), 'rb'))
    require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'ZIP input must be regular.')
    return stream


def verify_sources(directory, members):
    for name, entry in members.items():
        with ExitStack() as stack:
            safe_member(name)
            if 'content' in entry:
                require(len(entry['content']) == entry['size_bytes'] and digest(entry['content']) == entry['sha256'],
                        'Snapshot identity differs.')
            else:
                _check_file(stack, directory, entry)


def zip_info(name):
    safe_member(name)
    info = zipfile.ZipInfo(name, DATE)
    info.create_system = 3
    info.external_attr = ATTR
    info.compress_type = zipfile.ZIP_STORED
    return info


def write_zip(directory, stream, members):
    verify_sources(directory, members)
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for name, entry in sorted(members.items()):
            with ExitStack() as stack:
                source = io.BytesIO(entry['content']) if 'content' in entry else _open(stack, directory, entry)
                checksum, size = hashlib.sha256(), 0
                with archive.open(zip_info(name), 'w', force_zip64=True) as target:
                    for blob in iter(lambda: source.read(BLOCK), b''):
                        target.write(blob)
                        checksum.update(blob)
                        size += len(blob)
            require(size == entry['size_bytes'] and checksum.hexdigest() == entry['sha256'], 'ZIP source changed during creation.')
    verify_sources(directory, members)


def verify_zip(stream, members):
    try:
        stream.seek(0)
        with zipfile.ZipFile(stream, 'r') as archive:
            entries = archive.infolist()
            names = [i.filename for i in entries]
            require(names == sorted(members) and len(set(names)) == len(names), 'ZIP members differ from the exact specification.')
            require(archive.comment == b'', 'ZIP archive comment is noncanonical.')
            for info in entries:
                safe_member(info.filename)
                require(info.date_time == DATE and info.create_system == 3 and info.external_attr == ATTR and
                        not info.is_dir() and not stat.S_ISLNK(info.external_attr >> 16) and
                        info.compress_type == zipfile.ZIP_STORED and not info.comment and
                        not (info.flag_bits & ~0x800), 'ZIP metadata/entry type is noncanonical.')
                # Only ZIP64 size metadata is allowed, never Unix link/time extras.
                extra = info.extra
                while extra:
                    require(len(extra) >= 4, 'Malformed ZIP extra data.')
                    tag, length = int.from_bytes(extra[:2], 'little'), int.from_bytes(extra[2:4], 'little')
                    require(tag == 1 and len(extra) >= 4 + length, 'Unexpected ZIP extra metadata.')
                    extra = extra[4 + length:]
                expected = members[info.filename]
                require(info.file_size == expected['size_bytes'], 'ZIP member size differs.')
                checksum, size = hashlib.sha256(), 0
                with archive.open(info) as source:
                    for blob in iter(lambda: source.read(BLOCK), b''):
                        size += len(blob)
                        require(size <= expected['size_bytes'], 'ZIP member exceeds verified size.')
                        checksum.update(blob)
                require(size == expected['size_bytes'] and checksum.hexdigest() == expected['sha256'], 'ZIP member content identity differs.')
                # Reading to EOF above checks CRC for every entry, without a
                # redundant second read of an hour-long lecture archive.
    except (zipfile.BadZipFile, RuntimeError, EOFError, NotImplementedError) as exc:
        raise PackageFailure('invalid_zip', 'ZIP integrity or member decoding failed.') from exc


def report(directory, record, kind):
    pointer = record.get(kind)
    require(isinstance(pointer, dict) and isinstance(pointer.get('attempt_id'), str) and UUID.fullmatch(pointer['attempt_id']),
            'Invalid ZIP attempt identity.')
    path = f"generated/{kind}/{pointer['attempt_id']}/session.json"
    require(pointer.get('record_path') == path, 'ZIP journal path differs from revision.')
    with ExitStack() as stack:
        folder, _ = _folder(stack, directory, path)
        saved, checksum = _json_blob(folder, LIMIT)
    require(saved.get('session_id') == record['session_id'] and saved.get('attempt_id') == pointer['attempt_id'] and
            saved.get('policy') == POLICY and saved.get('schema_version') == 1, 'ZIP journal identity/policy differs.')
    return saved, checksum


def verify_output(directory, entry, members, kind, name=None):
    path = entry.get('relative_path', '')
    require(path.startswith(f'generated/{kind}/') and len(path.split('/')) == 4 and UUID.fullmatch(path.split('/')[2]),
            'ZIP output path is outside its owned attempts.')
    require(name is None or path.split('/')[-1] == name, 'ZIP output filename differs from its specification.')
    with ExitStack() as stack:
        _check_file(stack, directory, entry)
        verify_zip(_open(stack, directory, entry), members)


def verified_stage(directory, record, specs, kind):
    saved, checksum = report(directory, record, kind)
    pointer = record[kind]
    require(pointer.get('record_sha256') == checksum and pointer.get('status') == saved.get('status') and
            pointer.get('source_revision') == saved.get('source_revision') == revision(specs), 'ZIP journal/source revision is stale.')
    require(set(saved.get('files', {})) == set(specs), 'ZIP set specification differs.')
    entries, invalid = {}, []
    for name, members in specs.items():
        try:
            entry = saved['files'][name]
            require(entry.get('status') in ('verified', 'publication_ready'), 'ZIP member is incomplete.')
            verify_output(directory, entry, members, kind, name)
            aid = f"{kind}:{saved['attempt_id']}:{name}"
            entries[aid] = artifact_entry(aid, 'zip_package' if kind == 'package_generation' else 'full_archive',
                entry['relative_path'], status='verified', source=f"manifest_report:{record['manifest_generation']['attempt_id']}",
                size=entry['size_bytes'], sha256=entry['sha256'], created_at=entry['created_at'],
                verified_at=entry['verified_at'], revision=saved['source_revision'])
        except (ValueError, OSError, KeyError, TypeError):
            invalid.append(name)
    complete = not invalid and saved.get('status') == 'succeeded' and all(e.get('status') == 'verified' for e in saved['files'].values())
    return entries, complete, invalid, saved


def _generate(directory, record, specs, kind, free_bytes, existing_bytes):
    source_revision = revision(specs)
    prior, reusable = None, {}
    try:
        _, complete, _, prior = verified_stage(directory, record, specs, kind)
        if complete:
            return dict(record[kind], reused=True)
    except (ValueError, OSError, KeyError, TypeError):
        try:
            prior, _ = report(directory, record, kind)
        except (ValueError, OSError, KeyError, TypeError):
            prior = None
    if prior and prior.get('source_revision') == source_revision:
        for name, members in specs.items():
            try:
                entry = prior['files'][name]
                verify_output(directory, entry, members, kind, name)
                reusable[name] = dict(entry, status='verified')
            except (ValueError, OSError, KeyError, TypeError):
                pass
    else:
        prior = None
    with ExitStack() as stack:
        generated = stack.enter_context(directory.child('generated'))
        parent = stack.enter_context(generated.child(kind))
        now = datetime.now(timezone.utc).isoformat()
        if prior and len(reusable) == len(specs):
            attempt = prior
            output = _existing_child(stack, parent, prior['attempt_id'])
        else:
            aid = uuid.uuid4().hex
            output = stack.enter_context(parent.child(aid, exclusive=True))
            attempt = {'schema_version': 1, 'policy': POLICY, 'session_id': record['session_id'], 'attempt_id': aid,
                       'source_revision': source_revision, 'created_at': now, 'completed_at': None, 'files': {}}
        attempt['files'] = {name: reusable.get(name) or {'relative_path': f"generated/{kind}/{attempt['attempt_id']}/{name}",
                'status': 'pending', 'created_at': now, 'verified_at': None, 'size_bytes': None, 'sha256': None} for name in specs}
        missing = {name: members for name, members in specs.items() if name not in reusable}
        budget = storage_check(missing, free_bytes(), existing_artifact_bytes=existing_bytes)
        attempt.update(status='pending', preflight=budget, error=None)
        def persist():
            output.atomic_json(attempt)
            _, checksum = _json_blob(output, LIMIT)
            record[kind] = {key: attempt.get(key) for key in ('status', 'attempt_id', 'source_revision', 'created_at', 'completed_at', 'error', 'preflight')}
            record[kind].update(record_path=f"generated/{kind}/{attempt['attempt_id']}/session.json", record_sha256=checksum)
            directory.atomic_json(record)
        if missing and budget['decision'] != 'allow':
            attempt.update(status='skipped_due_to_storage' if kind == 'full_archive' else 'failed',
                           error={'code': 'insufficient_storage', 'message': 'Verified artifacts retained; ZIP storage check denied.'})
            persist()
            if kind == 'package_generation':
                raise PackageFailure('insufficient_storage', 'Part ZIP storage check denied; audio/manifests retained.')
            return dict(record[kind], reused=False)
        persist()
        temp = stack.enter_context(directory.child('temp'))
        staging = stack.enter_context(temp.child(kind + '-' + uuid.uuid4().hex, exclusive=True))
        try:
            for name, members in missing.items():
                verify_sources(directory, members)
                # Recheck remaining actual input sizes/reserve before each ZIP.
                remaining = {n: m for n, m in missing.items() if attempt['files'][n]['status'] == 'pending'}
                require(storage_check(remaining, free_bytes(), existing_artifact_bytes=existing_bytes)['decision'] == 'allow',
                        'Storage became insufficient before ZIP creation.')
                pending = 'pending-' + name
                with os.fdopen(staging.open(pending, os.O_RDWR | os.O_CREAT | os.O_EXCL), 'w+b') as stream:
                    write_zip(directory, stream, members)
                    stream.flush()
                    os.fsync(stream.fileno())
                    verify_zip(stream, members)
                    stream.seek(0)
                    checksum = hashlib.sha256()
                    for blob in iter(lambda: stream.read(BLOCK), b''):
                        checksum.update(blob)
                    size = os.fstat(stream.fileno()).st_size
                entry = attempt['files'][name]
                entry.update(size_bytes=size, sha256=checksum.hexdigest(), status='publication_ready',
                             verified_at=datetime.now(timezone.utc).isoformat())
                persist()  # Journal verified final identity BEFORE atomic publication.
                staging.publish(pending, name, output)
                verify_output(directory, entry, members, kind, name)
                entry['status'] = 'verified'
            attempt.update(status='succeeded', completed_at=attempt.get('completed_at') or datetime.now(timezone.utc).isoformat())
            persist()
        except (ValueError, OSError, zipfile.BadZipFile) as exc:
            attempt.update(status='failed', error={'code': getattr(exc, 'code', 'zip_generation_failed'),
                                                   'message': 'ZIP generation/publication failed; verified inputs retained.'})
            persist()
            if kind == 'package_generation':
                raise PackageFailure('zip_generation_failed', attempt['error']['message']) from exc
        return dict(record[kind], reused=False)


def _context(stack, config, session_id, token):
    require(isinstance(session_id, str) and UUID.fullmatch(session_id), 'Invalid session ID.')
    root = stack.enter_context(OwnedDirectory.root(config.data_root))
    sessions = _existing_child(stack, root, 'sessions')
    directory = _existing_child(stack, sessions, session_id)
    stack.enter_context(_inspection_lock(directory, token))
    record = _read(directory)
    _validate(record, session_id)
    return directory, record


def package_session(config, session_id, *, retry=False, _lock_token=None):
    from .session_state import project_session
    with ExitStack() as stack:
        directory, record = _context(stack, config, session_id, _lock_token)
        view = project_session(directory, record, _documents_only=True)
        specs = package_specs(directory, record, view)
        existing = sum(e['size_bytes'] for e in view['artifact_registry'].values() if e['status'] == 'verified')
        return _generate(directory, record, specs, 'package_generation', directory.free_bytes, existing)


def archive_session(config, session_id, *, decision=None, retry=False, _lock_token=None):
    from .session_state import project_session
    with ExitStack() as stack:
        directory, record = _context(stack, config, session_id, _lock_token)
        if decision is not None:
            require(decision in ('on', 'off'), 'Archive decision must be on or off.')
            selection = {'decision': 'explicit_' + decision, 'provenance': 'explicit_archive_command'}
            if record.get('archive_request') != selection:
                record['archive_request'] = selection
                directory.atomic_json(record)
        choice = archive_decision(record)
        if choice['decision'] != 'explicit_on':
            return dict(choice, status=choice['decision'], reused=True)
        view = project_session(directory, record, _packages_only=True)
        require(view['last_successful_state'] == 'packaged', 'All current part ZIPs must verify before full archive creation.')
        documents_view = project_session(directory, record, _documents_only=True)
        specs = archive_specs(record, documents_view)
        existing = sum(e['size_bytes'] for e in view['artifact_registry'].values() if e['status'] == 'verified')
        return _generate(directory, record, specs, 'full_archive', directory.free_bytes, existing)


def project_packages(directory, record, view, *, packages_only=False):
    """Extend the one canonical evidence projection; archive failure is nonfatal."""
    documents_view = deepcopy(view)
    view['package_status'] = {'status': 'not_generated'}
    try:
        choice = archive_decision(record)
    except ValueError:
        choice = {'decision': 'unresolved', 'error': {'code': 'invalid_archive_decision'}}
        view['progress_warnings'].append('optional_archive_invalid_decision')
    view['archive_status'] = dict(choice, status=choice['decision'] if choice['decision'] != 'explicit_on' else 'not_generated')
    if record.get('package_generation') is not None:
        try:
            specs = package_specs(directory, record, documents_view)
            entries, complete, invalid, saved = verified_stage(directory, record, specs, 'package_generation')
            view['artifact_registry'].update(entries)
            view['package_status'] = {'status': 'verified' if complete else saved['status'],
                                      'verified_count': len(entries), 'required_count': len(specs), 'invalid': invalid,
                                      'preflight': saved.get('preflight'), 'error': saved.get('error')}
            if complete:
                view.update(current_state='packaged', last_successful_state='packaged', active_stage=None)
            elif saved['status'] == 'failed' or saved['status'] == 'succeeded':
                raise PackageFailure('invalid_package_evidence', 'One or more required part ZIPs failed verification.')
            else:
                view['active_stage'] = 'package_generation'
        except (ValueError, OSError, KeyError, TypeError):
            view.update(current_state='failed', failed_stage='package_generation',
                        error_code='invalid_package_evidence', error_message='Current part ZIP set is incomplete, stale or invalid.', retryable=True)
    if not packages_only and view['last_successful_state'] == 'packaged' and choice['decision'] == 'explicit_on' and record.get('full_archive') is not None:
        try:
            specs = archive_specs(record, documents_view)
            entries, complete, invalid, saved = verified_stage(directory, record, specs, 'full_archive')
            view['artifact_registry'].update(entries)
            view['archive_status'].update(status='archived' if complete else saved['status'], preflight=saved.get('preflight'),
                                          error=saved.get('error'), invalid=invalid)
            if saved['status'] == 'failed' or (saved['status'] == 'succeeded' and not complete):
                view['archive_status']['status'] = 'failed_nonblocking'
        except (ValueError, OSError, KeyError, TypeError):
            view['archive_status'].update(status='failed_nonblocking', error={'code': 'invalid_archive_evidence'})
        if view['archive_status']['status'] not in ('archived', 'pending'):
            view['progress_warnings'].append('optional_archive_' + view['archive_status']['status'])
    return view
