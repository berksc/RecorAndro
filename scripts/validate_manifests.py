"""Read/manifest-only Android acceptance; never invokes audio processing stages.

Run from the repository: python scripts/validate_manifests.py --session-id SID
Uses normal configuration precedence, including RECORANDRO_DATA_ROOT.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recorandro.config import load_config
from recorandro.manifests import generate_manifests
from recorandro.session_state import session_status


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config')
    parser.add_argument('--session-id', required=True)
    parser.add_argument('--expected-parts', type=int, default=3)
    parser.add_argument('--expected-original-sha256')
    args = parser.parse_args()
    config = load_config(args.config)
    before = session_status(config, args.session_id)
    assert before['last_successful_state'] in ('segments_exported', 'manifested'), before['errors']
    assert before['part_count'] == args.expected_parts
    if args.expected_original_sha256:
        assert before['audio']['sha256'] == args.expected_original_sha256
    directory = config.data_root / 'sessions' / args.session_id
    # Include current protected original, normalized source if any, audio parts
    # and accepted stage reports. Stage projection has already verified paths.
    current = {e['relative_path']: e['sha256'] for e in before['artifacts'].values()
               if e['status'] == 'verified' and e['type'] not in ('manifest', 'report')}
    audio_before = {path: digest(directory / path) for path in current}
    assert audio_before == current
    first = generate_manifests(config, args.session_id)
    after = session_status(config, args.session_id)
    assert after['current_state'] == 'manifested', after['errors']
    assert {path: digest(directory / path) for path in current} == audio_before
    document_entries = {e['relative_path']: e for e in after['artifacts'].values()
                        if e['status'] == 'verified' and e['type'] in ('manifest', 'report')}
    assert len(document_entries) == 4 + 2 * args.expected_parts  # includes journal
    document_hashes = {path: digest(directory / path) for path in document_entries}
    for path, entry in document_entries.items():
        assert document_hashes[path] == entry['sha256']
        assert (directory / path).stat().st_size == entry['size_bytes']
        assert entry['regenerable'] and not entry['protected']
    metadata = (directory / 'session.json').read_bytes()
    second = generate_manifests(config, args.session_id)
    assert second['reused']
    assert (directory / 'session.json').read_bytes() == metadata
    assert {path: digest(directory / path) for path in document_entries} == document_hashes
    assert {path: digest(directory / path) for path in current} == audio_before
    journal = json.loads((directory / first['record_path']).read_bytes())
    model = json.loads((directory / journal['files']['manifest.json']['relative_path']).read_bytes())
    assert model['visual_count'] == 0 and model['visual_status'] == 'none'
    assert not any('missing_visual' in warning or 'missing_photo' in warning for warning in model['warnings'])
    assert model['parts'][-1]['global_end_seconds'] == model['timeline']['working_source_end_seconds']
    for previous, following in zip(model['parts'], model['parts'][1:]):
        assert previous['nominal_end_seconds'] == following['nominal_start_seconds']
        assert following['global_start_seconds'] == following['nominal_start_seconds']
        assert previous['global_end_seconds'] == previous['nominal_end_seconds'] + 5
    print(json.dumps({'ALL_PASS': True, 'current_state': after['current_state'],
                      'part_count': after['part_count'], 'audio_and_stage_records_unchanged': True,
                      'repeated_generation_byte_identical': True,
                      'manifest_path': journal['files']['manifest.json']['relative_path'],
                      'report_path': journal['files']['processing_report.md']['relative_path'],
                      'warnings': model['warnings']}, indent=2))


if __name__ == '__main__':
    main()
