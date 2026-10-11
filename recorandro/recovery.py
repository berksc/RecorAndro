"""Local recovery over canonical stage records; no orphan scanning or new registry."""

from contextlib import ExitStack
from copy import deepcopy

from .inspection import _existing_child, _inspection_lock, inspect_session
from .normalization import normalize_session
from .segmentation import plan_session, MAX_PLAN_BYTES
from .exports import export_session, _json_blob, MAX_EXPORT_BYTES, POLICY
from .session_state import _read, _validate, _folder, project_session, UUID
from .storage import OwnedDirectory

STAGES = ('inspection', 'normalization', 'segmentation', 'audio_export')
MILESTONES = ('imported', 'probed', 'normalized_or_skipped',
              'segmentation_planned', 'segments_exported')
SUCCESS = ('probed', 'normalization_succeeded', 'planned', 'export_succeeded')
PENDING = ('probe_pending', 'normalization_pending', 'planning_pending', 'export_pending')
REPORTS = {'normalization': 'normalization', 'segmentation': 'segmentation', 'audio_export': 'exports'}


class RecoveryFailure(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _decision(view):
    frontier = view['last_successful_state']
    if frontier not in MILESTONES:
        classification, next_stage = 'failed_manual_attention', None
    elif frontier == 'segments_exported':
        classification, next_stage = 'complete', None
    else:
        next_stage = STAGES[MILESTONES.index(frontier)]
        classification = 'failed_retryable' if view['current_state'] == 'failed' else 'resumable'
        if view.get('error_code') in ('unsafe_managed_path', 'invalid_lock_owner'):
            classification = 'failed_manual_attention'
    code, message = view.get('error_code'), view.get('error_message')
    for stage, succeeded, pending, failed in zip(STAGES, SUCCESS, PENDING,
            ('probe_failed', 'normalization_failed', 'planning_failed', 'export_failed')):
        pointer = view.get(stage)
        if pointer is None:
            continue
        if not isinstance(pointer, dict) or pointer.get('status') not in (succeeded, pending, failed):
            classification, next_stage = 'failed_manual_attention', None
            code, message = 'invalid_stage_record', 'Stage structure/status needs manual attention; retained without replacement.'
            break
        if stage in ('normalization', 'segmentation') and pointer.get('mode_requested') not in ('auto', 'force', 'off'):
            classification, next_stage = 'failed_manual_attention', None
            code, message = 'invalid_recorded_mode', 'Recorded mode needs manual attention; no default substitution.'
            break
    return {'classification': classification, 'completion_scope': 'implemented_audio_stages',
            'current_state': view['current_state'], 'last_successful_state': frontier,
            'next_stage': next_stage, 'error_code': code,
            'error_message': message, 'part_count': view['verified_part_count']}


def _reconcile(directory, record):
    """Repair only a current pending pointer from its own atomically saved report.

    A success report is accepted only through the unchanged Step 3.1 evidence
    gates. Partial export reports supply candidates, never success. Missing final
    bytes (including pre-publication journals) cannot establish completion.
    """
    adopted = []
    for stage, success, pending in zip(STAGES, SUCCESS, PENDING):
        pointer = record.get(stage)
        if stage not in REPORTS or not isinstance(pointer, dict) or pointer.get('status') != pending:
            continue
        attempt = pointer.get('attempt_id')
        if not isinstance(attempt, str) or not UUID.fullmatch(attempt):
            continue
        path = f'generated/{REPORTS[stage]}/{attempt}/session.json'
        if stage != 'normalization' and pointer.get('record_path') != path:
            continue
        publishing = False
        try:
            with ExitStack() as stack:
                folder, _ = _folder(stack, directory, path)
                saved, digest = _json_blob(folder, MAX_EXPORT_BYTES if stage == 'audio_export' else MAX_PLAN_BYTES)
            intent = (stage == 'normalization' and saved.get('status') == 'normalization_pending' and
                      isinstance(saved.get('publication_intent'), dict))
            if intent:
                if (saved.get('session_id') != record['session_id'] or saved.get('attempt_id') != attempt or
                        saved.get('mode_requested') != pointer.get('mode_requested')):
                    continue
                saved = saved['publication_intent']
            if (saved.get('session_id') != record['session_id'] or saved.get('attempt_id') != attempt or
                    saved.get('mode_requested') != pointer.get('mode_requested')):
                continue
            trial = deepcopy(record)
            if stage == 'normalization':
                trial[stage] = saved
            else:
                candidate = dict(pointer, status=saved.get('status'), record_sha256=digest,
                                 source=saved.get('source'), error=saved.get('error'),
                                 completed_at=saved.get('completed_at'))
                if stage == 'segmentation' and isinstance(saved.get('plan'), dict):
                    candidate.update({k: saved['plan'].get(k) for k in
                                      ('expected_part_count', 'mode_fulfilled', 'decision')})
                if stage == 'audio_export':
                    candidate.update(success=saved.get('success'), plan_reference=saved.get('plan_reference'),
                                     part_count=saved.get('part_count'),
                                     verified_part_count=sum(p.get('status') == 'verified' for p in saved.get('parts', [])
                                                             if isinstance(p, dict)))
                trial[stage] = candidate
            view = project_session(directory, trial, _normalization_intent=intent)
            required = MILESTONES[STAGES.index(stage) + 1]
            verified = (saved.get('status') == success and
                        view['last_successful_state'] in MILESTONES and
                        MILESTONES.index(view['last_successful_state']) >= MILESTONES.index(required))
            baseline = project_session(directory, record)
            reference = baseline.get('segmentation_plan_identity') or {}
            partial = (stage == 'audio_export' and saved.get('status') in
                       ('export_pending', 'export_failed', 'export_succeeded') and
                       baseline['last_successful_state'] == 'segmentation_planned' and
                       saved.get('policy') == POLICY and
                       saved.get('source') == record['segmentation'].get('source') and
                       saved.get('plan_reference') == {k: reference.get(k) for k in ('attempt_id', 'record_path', 'sha256')})
            if not (verified or partial):
                continue
            if partial and not verified and saved.get('status') == 'export_succeeded':
                # A completed report whose set is now damaged is still useful
                # as hashed reuse evidence. Keep the canonical attempt pending;
                # its report status mismatch cannot advance the state. The
                # exporter verifies every candidate and rebuilds only bad parts.
                trial[stage].update(status='export_pending', success=False, completed_at=None)
            if trial[stage] == record[stage]:
                continue
            # A partial set remains pending/failed even if every filename exists.
            publishing = True
            if intent:
                # Only verified FINAL bytes can turn ready evidence into a
                # completed report, before canonical pointer publication.
                with ExitStack() as stack:
                    folder, _ = _folder(stack, directory, path)
                    folder.atomic_json(saved)
            directory.atomic_json(trial)
            record = trial
            adopted.append(stage)
        except (ValueError, OSError, KeyError, TypeError, AttributeError):
            if publishing:
                raise RecoveryFailure('metadata_persistence_failed',
                                      'Cannot publish verified recovery metadata; artifacts retained. Retry after fixing storage.')
            # Invalid derived evidence is regenerated by the regular stage code.
            continue
    return record, adopted


def recover_session(config, session_id, *, stage=None, inspect_only=False):
    """Resume to the implemented audio frontier, or retry one required stage.

    Completed stage retry is a verified no-op. Import recovery needs the user's
    source selection; no external path is reconstructed or original overwritten.
    """
    if not isinstance(session_id, str) or not UUID.fullmatch(session_id):
        raise RecoveryFailure('invalid_session_id', 'Use an existing session identifier.')
    if stage is not None and stage not in STAGES:
        raise RecoveryFailure('invalid_retry_stage', 'Retry stage must be inspection, normalization, segmentation or audio_export.')
    with ExitStack() as stack:
        if not config.data_root.is_dir():
            raise RecoveryFailure('session_unavailable', 'Configured session data root is unavailable.')
        root = stack.enter_context(OwnedDirectory.root(config.data_root))
        sessions = _existing_child(stack, root, 'sessions')
        directory = _existing_child(stack, sessions, session_id)
        token = stack.enter_context(_inspection_lock(directory))
        try:
            record = _read(directory)
            _validate(record, session_id)
            view = project_session(directory, record)
        except (ValueError, OSError) as exc:
            return {'session_id': session_id, 'classification': 'failed_manual_attention',
                    'error_code': getattr(exc, 'code', 'invalid_session_metadata'),
                    'error_message': 'Canonical metadata cannot be validated; retained without guessing.',
                    'performed_stages': [], 'reconciled_stages': []}
        # Verify originals before considering any orphaned publication evidence.
        if view['last_successful_state'] in MILESTONES and not inspect_only:
            try:
                record, reconciled = _reconcile(directory, record)
            except RecoveryFailure as exc:
                decision = _decision(project_session(directory, _read(directory)))
                return dict(decision, session_id=session_id,
                            classification='failed_manual_attention' if decision['classification'] == 'failed_manual_attention'
                            else 'failed_retryable',
                            error_code=exc.code, error_message=str(exc), performed_stages=[], reconciled_stages=[])
            if reconciled:
                view = project_session(directory, record)
        else:
            reconciled = []
        decision = _decision(view)
        performed = []
        if not inspect_only and decision['classification'] != 'failed_manual_attention':
            if stage is not None and decision['next_stage'] is not None:
                if STAGES.index(stage) > STAGES.index(decision['next_stage']):
                    raise RecoveryFailure('prerequisite_unverified', 'Retry the earlier unverified prerequisite first.')
                if STAGES.index(stage) < STAGES.index(decision['next_stage']):
                    return dict(decision, session_id=session_id, performed_stages=[], reconciled_stages=reconciled)
            while decision['next_stage'] is not None:
                current = decision['next_stage']
                previous = record.get(current) or {}
                mode = previous.get('mode_requested', 'auto')
                if mode not in ('auto', 'force', 'off'):
                    raise RecoveryFailure('invalid_recorded_mode', 'Recorded mode needs manual correction; no default substitution.')
                try:
                    operation = {'inspection': inspect_session, 'normalization': normalize_session,
                                 'segmentation': plan_session, 'audio_export': export_session}[current]
                    kwargs = {'retry': True, '_lock_token': token}
                    if current in ('normalization', 'segmentation'):
                        kwargs['mode'] = mode
                    operation(config, session_id, **kwargs)
                    performed.append(current)
                except (ValueError, OSError) as exc:
                    record = _read(directory)
                    decision = _decision(project_session(directory, record))
                    decision.update(classification='failed_retryable' if decision['classification'] != 'failed_manual_attention'
                                    else 'failed_manual_attention', error_code=getattr(exc, 'code', 'stage_access_failed'),
                                    error_message=str(exc) if isinstance(exc, ValueError) else 'Cannot safely access stage storage.')
                    break
                record = _read(directory)
                decision = _decision(project_session(directory, record))
                if stage is not None or decision['classification'] == 'failed_manual_attention':
                    break
                if decision['next_stage'] == current:
                    raise RecoveryFailure('stage_not_verified', 'Stage returned without verified completion.')
        return dict(decision, session_id=session_id, performed_stages=performed, reconciled_stages=reconciled)
