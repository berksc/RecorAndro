"""Non-destructive Step 4.2 acceptance/measurement over an already manifested session."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recorandro.config import load_config
from recorandro.packages import package_session, archive_session
from recorandro.session_state import session_status
from recorandro.storage import OwnedDirectory


def digest(path):
    checksum = hashlib.sha256()
    with path.open('rb') as source:
        for blob in iter(lambda: source.read(1024 * 1024), b''):
            checksum.update(blob)
    return checksum.hexdigest()


def free_bytes(root):
    with OwnedDirectory.root(root) as directory:
        return directory.free_bytes()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config')
    parser.add_argument('--session-id', required=True)
    parser.add_argument('--expected-parts', type=int, default=3)
    parser.add_argument('--expected-original-sha256')
    parser.add_argument('--archive-on', action='store_true', help='Explicitly request a real full archive and measure its storage')
    args = parser.parse_args()
    config = load_config(args.config)
    before = session_status(config, args.session_id)
    assert before['last_successful_state'] in ('manifested', 'packaged'), before['errors']
    assert before['part_count'] == args.expected_parts
    if args.expected_original_sha256:
        assert before['audio']['sha256'] == args.expected_original_sha256
    directory = config.data_root / 'sessions' / args.session_id
    inputs = {e['relative_path']: e['sha256'] for e in before['artifacts'].values()
              if e['status'] == 'verified' and e['type'] not in ('zip_package', 'full_archive')}
    assert {path: digest(directory / path) for path in inputs} == inputs
    measurement = {'free_bytes_before_packages': free_bytes(config.data_root)}
    started = time.monotonic()
    package_session(config, args.session_id)
    measurement.update(package_command_elapsed_seconds=round(time.monotonic() - started, 6),
                       free_bytes_after_packages=free_bytes(config.data_root))
    view = session_status(config, args.session_id)
    assert view['current_state'] == 'packaged', view['errors']
    packages = {e['relative_path']: e for e in view['artifacts'].values()
                if e['type'] == 'zip_package' and e['status'] == 'verified'}
    assert len(packages) == args.expected_parts
    package_hashes = {path: digest(directory / path) for path in packages}
    member_lists = {}
    for path, entry in packages.items():
        assert package_hashes[path] == entry['sha256']
        assert (directory / path).stat().st_size == entry['size_bytes']
        with zipfile.ZipFile(directory / path) as archive:
            assert archive.testzip() is None
            member_lists[path] = archive.namelist()
    metadata = (directory / 'session.json').read_bytes()
    assert package_session(config, args.session_id)['reused']
    assert (directory / 'session.json').read_bytes() == metadata
    assert {path: digest(directory / path) for path in packages} == package_hashes
    measurement['part_zip_bytes'] = sum(e['size_bytes'] for e in packages.values())
    measurement['current_artifact_bytes_before_archive'] = sum(e['size_bytes'] for e in view['artifacts'].values()
                                                              if e['status'] == 'verified')
    archive_result = None
    if args.archive_on:
        measurement['free_bytes_before_archive'] = free_bytes(config.data_root)
        started = time.monotonic()
        archive_result = archive_session(config, args.session_id, decision='on')
        measurement.update(archive_command_elapsed_seconds=round(time.monotonic() - started, 6),
                           free_bytes_after_archive=free_bytes(config.data_root))
        view = session_status(config, args.session_id)
        assert view['current_state'] == 'packaged', view['errors']
        if archive_result['status'] == 'succeeded':
            entries = [e for e in view['artifacts'].values() if e['type'] == 'full_archive' and e['status'] == 'verified']
            assert len(entries) == 1
            entry = entries[0]
            path = directory / entry['relative_path']
            assert path.stat().st_size == entry['size_bytes'] and digest(path) == entry['sha256']
            with zipfile.ZipFile(path) as archive:
                assert archive.testzip() is None
                names = archive.namelist()
                assert names == sorted(names) and len(names) == len(set(names))
                assert not any(n.endswith('.zip') for n in names)
                snapshot = json.loads(archive.read('session.json'))
                assert snapshot['archive_status']['status'] == 'snapshot_before_archive'
                assert 'full_archive' not in snapshot and 'package_generation' not in snapshot
            measurement.update(full_archive_path=entry['relative_path'], full_archive_bytes=entry['size_bytes'],
                               full_archive_sha256=entry['sha256'], full_archive_members=names,
                               additional_archive_duplication_bytes=entry['size_bytes'],
                               archive_to_existing_artifact_ratio=round(entry['size_bytes'] /
                                    measurement['current_artifact_bytes_before_archive'], 6))
            metadata = (directory / 'session.json').read_bytes()
            assert archive_session(config, args.session_id, decision='on')['reused']
            assert (directory / 'session.json').read_bytes() == metadata
            assert digest(path) == entry['sha256']
        elif archive_result['status'] == 'skipped_due_to_storage':
            measurement['archive_storage_denial'] = archive_result['preflight']
        else:
            raise AssertionError(archive_result)
    assert {path: digest(directory / path) for path in inputs} == inputs
    assert {path: digest(directory / path) for path in packages} == package_hashes
    assert view['visual_count'] == 0
    print(json.dumps({'ALL_PASS': True, 'session_id': args.session_id, 'current_state': view['current_state'],
                      'archive_status': view['archive_status'], 'part_zip_members': member_lists,
                      'audio_and_documents_unchanged': True, 'repeat_packages_byte_identical': True,
                      'measurements': measurement, 'lecture_default': 'OPEN'}, indent=2))


if __name__ == '__main__':
    main()
