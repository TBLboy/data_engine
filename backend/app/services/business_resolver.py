from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import (
    Batch,
    ClassificationRule,
    Episode,
    EpisodeInventory,
    EpisodeObject,
    ListRecord,
    ScanJob,
    TaskType,
)
from app.services.data_assets import enqueue_batch_asset_recompute, enqueue_list_scope_recompute
from app.services.list_snapshot import SELECTIVE_ROLES
from app.services.scan_v3_types import ListSnapshot, ResolutionResult


STATE_RANK = {'ingestable': 0, 'processable': 1, 'qc_ready': 2}
TIMESTAMP_SUFFIX_PATTERN = re.compile(r'([_-]?20\d{2}[-_]?\d{2}[-_]?\d{2}([_-]?\d{2}){3})$')
UNCLASSIFIED_TASK_TYPE_ID = 'task_type:unclassified'


def _utcnow() -> datetime:
    return datetime.utcnow()


def list_id(bucket: str, list_prefix: str) -> str:
    return f"list_{hashlib.sha1(f'{bucket}:{list_prefix}'.encode('utf-8')).hexdigest()[:16]}"


def inventory_id(bucket: str, list_prefix: str, episode_name: str) -> str:
    return f"inv_{hashlib.sha1(f'{bucket}:{list_prefix}:{episode_name}'.encode('utf-8')).hexdigest()}"


def batch_id(resolved_list_id: str) -> str:
    return f'batch_{resolved_list_id[5:]}'


def episode_id(resolved_batch_id: str, episode_name: str) -> str:
    return f'{resolved_batch_id}_{episode_name}'


def _normalize_classification_text(list_prefix: str) -> tuple[str, str]:
    full = list_prefix.strip('/').lower()
    basename = full.split('/')[-1] if full else ''
    basename = TIMESTAMP_SUFFIX_PATTERN.sub('', basename).strip('-_ ')
    return re.sub(r'[-_/]+', ' ', full).strip(), re.sub(r'[-_/]+', ' ', basename).strip()


def _match_rule(rules: list[ClassificationRule], list_prefix: str) -> ClassificationRule | None:
    normalized_full, normalized_basename = _normalize_classification_text(list_prefix)
    ordered = sorted(
        rules,
        key=lambda item: (
            -item.priority,
            -len(re.sub(r'[-_/]+', ' ', item.pattern.strip().lower())),
            0 if item.match_scope == 'basename' else 1,
            item.id or 0,
        ),
    )
    for rule in ordered:
        haystack = normalized_basename if rule.match_scope == 'basename' else normalized_full
        pattern = re.sub(r'[-_/]+', ' ', rule.pattern.strip().lower()).strip()
        if pattern and pattern in haystack:
            return rule
    return None


def _ensure_unclassified(db: Session) -> TaskType:
    task_type = db.query(TaskType).filter(TaskType.id == UNCLASSIFIED_TASK_TYPE_ID).first()
    if task_type is None:
        task_type = TaskType(
            id=UNCLASSIFIED_TASK_TYPE_ID,
            name='待分类',
            description='尚未完成任务类型确认的采集任务',
            arm_mode='both_arms',
            is_active=True,
        )
        db.add(task_type)
        db.flush()
    return task_type


def _manifest_metrics(manifest: dict | None, old_duration: float, old_frames: int) -> tuple[float, int]:
    if manifest is None:
        return old_duration, old_frames
    try:
        duration = float(manifest.get('duration', 0.0) or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    try:
        frames = int(manifest.get('frame_count', 0) or 0)
    except (TypeError, ValueError):
        frames = 0
    return duration, frames


def _derive_state(*, raw_exists: bool, processed_exists: bool, roles: set[str], manifest: dict | None) -> str:
    if manifest and isinstance(manifest.get('files'), dict):
        cameras = manifest['files'].get('cameras', {})
        has_rgb = any(isinstance(value, dict) and value.get('video') for value in cameras.values())
    else:
        has_rgb = 'camera_rgb_video' in roles
    # Unchanged episodes intentionally skip manifest reads. Persisted selective
    # roles still provide enough evidence to preserve the current readiness.
    if processed_exists and {'manifest', 'metadata', 'telemetry_npz'} <= roles and has_rgb:
        return 'qc_ready'
    if processed_exists:
        return 'processable'
    return 'ingestable'


def _advance_missing(record, *, shard_id: int, now: datetime, confirmation_seconds: int) -> bool:
    if record.source_status == 'present':
        record.source_status = 'suspect_missing'
        record.missing_streak = 1
        record.first_missing_at = now
        record.last_missing_at = now
        record.missing_evidence_shard_id = shard_id
        return False
    if record.source_status == 'suspect_missing':
        independent = record.missing_evidence_shard_id != shard_id
        elapsed = record.first_missing_at is not None and now - record.first_missing_at >= timedelta(seconds=confirmation_seconds)
        if independent and elapsed:
            record.source_status = 'missing'
            record.missing_streak += 1
            record.last_missing_at = now
            record.missing_evidence_shard_id = shard_id
            return True
    return False


def _confirm_missing(record, *, shard_id: int, now: datetime) -> bool:
    """Mark a child object missing once its owning episode is confirmed absent."""
    if record.source_status == 'missing':
        return False
    if record.source_status == 'present':
        record.missing_streak = 1
        record.first_missing_at = now
    else:
        record.missing_streak += 1
        record.first_missing_at = record.first_missing_at or now
    record.source_status = 'missing'
    record.last_missing_at = now
    record.missing_evidence_shard_id = shard_id
    return True


def _observe_scope(
    record: EpisodeInventory,
    *,
    scope: str,
    observed: bool,
    shard_id: int,
    now: datetime,
    confirmation_seconds: int,
    is_new: bool,
) -> tuple[bool, bool]:
    status_name = f'{scope}_source_status'
    streak_name = f'{scope}_missing_streak'
    evidence_name = f'{scope}_missing_evidence_shard_id'
    first_missing_name = f'{scope}_first_missing_at'
    last_missing_name = f'{scope}_last_missing_at'
    old_status = getattr(record, status_name)

    if observed:
        recovered = old_status != 'present'
        setattr(record, status_name, 'present')
        setattr(record, streak_name, 0)
        setattr(record, evidence_name, None)
        setattr(record, first_missing_name, None)
        setattr(record, last_missing_name, None)
        return recovered, False

    if is_new:
        setattr(record, status_name, 'missing')
        setattr(record, streak_name, 0)
        setattr(record, evidence_name, None)
        setattr(record, first_missing_name, None)
        setattr(record, last_missing_name, None)
        return False, False

    if old_status == 'present':
        setattr(record, status_name, 'suspect_missing')
        setattr(record, streak_name, 1)
        setattr(record, evidence_name, shard_id)
        setattr(record, first_missing_name, now)
        setattr(record, last_missing_name, now)
        return False, False
    if old_status == 'suspect_missing':
        first_missing_at = getattr(record, first_missing_name)
        independent = getattr(record, evidence_name) != shard_id
        elapsed = first_missing_at is not None and now - first_missing_at >= timedelta(seconds=confirmation_seconds)
        if independent and elapsed:
            setattr(record, status_name, 'missing')
            setattr(record, streak_name, getattr(record, streak_name) + 1)
            setattr(record, evidence_name, shard_id)
            setattr(record, last_missing_name, now)
            return False, True
    return False, False


def _mark_present(record, *, now: datetime) -> bool:
    recovered = record.source_status != 'present'
    record.source_status = 'present'
    record.missing_streak = 0
    record.missing_evidence_shard_id = None
    record.first_missing_at = None
    record.last_missing_at = None
    record.last_confirmed_present_at = now
    return recovered


def mark_list_not_found(
    db: Session,
    *,
    bucket: str,
    list_prefix: str,
    shard_id: int,
    confirmation_seconds: int,
    now: datetime | None = None,
) -> bool:
    timestamp = now or _utcnow()
    record = db.query(ListRecord).filter(
        ListRecord.bucket == bucket,
        ListRecord.list_prefix == list_prefix,
    ).first()
    if record is None:
        return False
    became_missing = _advance_missing(
        record,
        shard_id=shard_id,
        now=timestamp,
        confirmation_seconds=confirmation_seconds,
    )
    if became_missing and record.is_active:
        enqueue_list_scope_recompute(db, record.id, reason='list_scope_changed')
        record.is_active = False
        record.updated_at = timestamp
    return became_missing


def mark_list_episodes_not_found(
    db: Session,
    *,
    list_id: str,
    shard_id: int,
    confirmation_seconds: int,
    now: datetime | None = None,
) -> bool:
    """Advance episode absence when a successful full List scan is empty."""
    timestamp = now or _utcnow()
    needs_confirmation = False
    inventories = db.query(EpisodeInventory).filter(EpisodeInventory.list_id == list_id).all()
    touched_batch_ids: set[str] = set()
    for inventory in inventories:
        became_missing = _advance_missing(
            inventory,
            shard_id=shard_id,
            now=timestamp,
            confirmation_seconds=confirmation_seconds,
        )
        if inventory.source_status == 'suspect_missing':
            needs_confirmation = True
        if not became_missing:
            for episode_object in inventory.objects:
                _advance_missing(
                    episode_object,
                    shard_id=shard_id,
                    now=timestamp,
                    confirmation_seconds=confirmation_seconds,
                )
            continue
        inventory.raw_source_status = 'missing'
        inventory.processed_source_status = 'missing'
        inventory.raw_exists = False
        inventory.processed_exists = False
        inventory.state = 'ingestable'
        inventory.state_changed_at = timestamp
        for episode_object in inventory.objects:
            _confirm_missing(
                episode_object,
                shard_id=shard_id,
                now=timestamp,
            )
        if inventory.ingested_episode_id:
            episode = db.query(Episode).filter(Episode.id == inventory.ingested_episode_id).first()
            if episode is not None:
                episode.is_active = False
                episode.updated_at = timestamp
                touched_batch_ids.add(episode.batch_id)
    for batch_id in touched_batch_ids:
        enqueue_batch_asset_recompute(db, batch_id, reason='list_scope_changed')
    return needs_confirmation


def resolve_list_snapshot(
    db: Session,
    *,
    scan_job: ScanJob,
    shard_id: int,
    snapshot: ListSnapshot,
    missing_confirmation_seconds: int = 600,
    now: datetime | None = None,
) -> ResolutionResult:
    if not snapshot.enumeration_complete:
        raise ValueError('incomplete List snapshot cannot be published')
    timestamp = now or _utcnow()
    resolved_list_id = list_id(snapshot.bucket, snapshot.list_prefix)
    resolved_batch_id = batch_id(resolved_list_id)
    result = ResolutionResult(list_id=resolved_list_id, batch_id=resolved_batch_id)
    unclassified = _ensure_unclassified(db)
    rules = db.query(ClassificationRule).filter(ClassificationRule.is_active == True).order_by(
        ClassificationRule.priority.desc(), ClassificationRule.pattern.desc(), ClassificationRule.id.asc()
    ).all()
    rule = _match_rule(rules, snapshot.list_prefix)

    list_record = db.query(ListRecord).filter(ListRecord.id == resolved_list_id).first()
    if list_record is None:
        list_record = ListRecord(
            id=resolved_list_id,
            bucket=snapshot.bucket,
            list_prefix=snapshot.list_prefix,
            confirmed_scan_id=scan_job.id,
            last_active_scan_id=scan_job.id,
            has_raw=False,
            has_processed=False,
            total_raw_episodes=0,
            total_processed_episodes=0,
            candidate_task_type='',
            candidate_source='',
            final_task_type_id=unclassified.id,
            is_active=True,
            created_at=timestamp,
            updated_at=timestamp,
            source_status='present',
            missing_streak=0,
            last_confirmed_present_at=timestamp,
        )
        db.add(list_record)
    else:
        _mark_present(list_record, now=timestamp)
        list_record.last_active_scan_id = scan_job.id
        list_record.is_active = True
        list_record.updated_at = timestamp
    if rule is not None:
        list_record.candidate_task_type = rule.candidate_label
        list_record.candidate_source = 'prefix_keyword'
    else:
        list_record.candidate_task_type = ''
        list_record.candidate_source = ''

    db.flush()
    effective_task_type_id = list_record.final_task_type_id or unclassified.id
    linked_batches = db.query(Batch).filter(Batch.list_id == resolved_list_id).order_by(Batch.imported_at.asc()).all()
    batch = linked_batches[0] if linked_batches else db.query(Batch).filter(Batch.id == resolved_batch_id).first()
    if batch is None:
        batch = Batch(
            id=resolved_batch_id,
            list_id=resolved_list_id,
            task_type_id=effective_task_type_id,
            name=snapshot.list_prefix.rstrip('/').split('/')[-1],
            imported_at=timestamp,
            episode_count=0,
            sampled_episode_count=0,
            completed_sample_count=0,
            dispatch_mode='sampled',
            sampling_ratio=25,
            qc_status='new',
            pass_rate=0.0,
            top_reason='-',
            is_active=True,
        )
        db.add(batch)
        db.flush()
    else:
        resolved_batch_id = batch.id
        result.batch_id = batch.id
        batch.list_id = resolved_list_id
        batch.name = snapshot.list_prefix.rstrip('/').split('/')[-1]
        # Never overwrite an existing manual task assignment.

    inventory_query = db.query(EpisodeInventory).filter(EpisodeInventory.list_id == resolved_list_id)
    if snapshot.range_start:
        inventory_query = inventory_query.filter(EpisodeInventory.episode_name >= snapshot.range_start)
    if snapshot.range_end:
        inventory_query = inventory_query.filter(EpisodeInventory.episode_name < snapshot.range_end)
    existing_inventory = {
        item.episode_name: item
        for item in inventory_query.all()
    }
    seen_names = {item.episode_name for item in snapshot.episodes}
    existing_objects = {
        (item.episode_inventory_id, item.object_key): item
        for item in db.query(EpisodeObject).join(
            EpisodeInventory, EpisodeObject.episode_inventory_id == EpisodeInventory.id
        ).filter(
            EpisodeInventory.list_id == resolved_list_id,
            EpisodeObject.object_role.in_(SELECTIVE_ROLES),
        ).all()
    }
    existing_objects_by_inventory: dict[str, dict[str, EpisodeObject]] = {}
    for (object_inventory_id, object_key), episode_object in existing_objects.items():
        existing_objects_by_inventory.setdefault(object_inventory_id, {})[object_key] = episode_object
    existing_episode_ids = {
        item.id: item
        for item in db.query(Episode).filter(Episode.batch_id == batch.id).all()
    }

    raw_count = 0
    processed_count = 0
    for episode_snapshot in snapshot.episodes:
        raw_count += int(bool(episode_snapshot.raw_prefix))
        processed_count += int(bool(episode_snapshot.processed_prefix))
        inventory = existing_inventory.get(episode_snapshot.episode_name)
        is_new = inventory is None
        if inventory is None:
            inventory = EpisodeInventory(
                id=inventory_id(snapshot.bucket, snapshot.list_prefix, episode_snapshot.episode_name),
                list_id=resolved_list_id,
                episode_name=episode_snapshot.episode_name,
                episode_prefix=episode_snapshot.processed_prefix or episode_snapshot.raw_prefix,
                raw_prefix='',
                processed_prefix='',
                state='ingestable',
                max_observed_state='ingestable',
                raw_exists=False,
                processed_exists=False,
                manifest_hash='',
                metadata_hash='',
                episode_id_from_manifest='',
                duration_sec=0.0,
                frame_count=0,
                state_changed_at=timestamp,
                first_seen_scan_id=scan_job.id,
                last_seen_scan_id=scan_job.id,
                ingested_episode_id=None,
                source_status='present',
                missing_streak=0,
                last_confirmed_present_at=timestamp,
            )
            db.add(inventory)
            existing_inventory[episode_snapshot.episode_name] = inventory
            result.new_episode_count += 1
        else:
            if _mark_present(inventory, now=timestamp):
                result.recovered_episode_count += 1

        old_fingerprints = (inventory.raw_content_fingerprint, inventory.processed_content_fingerprint)
        new_fingerprints = (episode_snapshot.raw_content_fingerprint, episode_snapshot.processed_content_fingerprint)
        changed = is_new or old_fingerprints != new_fingerprints
        inventory.episode_prefix = episode_snapshot.processed_prefix or episode_snapshot.raw_prefix
        inventory.raw_prefix = episode_snapshot.raw_prefix
        inventory.processed_prefix = episode_snapshot.processed_prefix
        raw_observed = bool(episode_snapshot.raw_prefix)
        processed_observed = bool(episode_snapshot.processed_prefix)
        raw_recovered, raw_missing = _observe_scope(
            inventory,
            scope='raw',
            observed=raw_observed,
            shard_id=shard_id,
            now=timestamp,
            confirmation_seconds=missing_confirmation_seconds,
            is_new=is_new,
        )
        processed_recovered, processed_missing = _observe_scope(
            inventory,
            scope='processed',
            observed=processed_observed,
            shard_id=shard_id,
            now=timestamp,
            confirmation_seconds=missing_confirmation_seconds,
            is_new=is_new,
        )
        if raw_recovered or processed_recovered or raw_missing or processed_missing:
            changed = True
        if inventory.raw_source_status == 'suspect_missing' or inventory.processed_source_status == 'suspect_missing':
            result.needs_missing_confirmation = True
        # Keep source booleans true during the first suspect scan so a single
        # incomplete observation does not downgrade readiness. A confirmed
        # missing source is the only state that clears the booleans; using the
        # current observation also restores them after a confirmed recovery.
        inventory.raw_exists = raw_observed or inventory.raw_source_status != 'missing'
        inventory.processed_exists = processed_observed or inventory.processed_source_status != 'missing'
        inventory.raw_object_count = episode_snapshot.raw_object_count
        inventory.processed_object_count = episode_snapshot.processed_object_count
        inventory.raw_total_size_bytes = episode_snapshot.raw_total_size_bytes
        inventory.processed_total_size_bytes = episode_snapshot.processed_total_size_bytes
        inventory.raw_content_fingerprint = episode_snapshot.raw_content_fingerprint
        inventory.processed_content_fingerprint = episode_snapshot.processed_content_fingerprint
        inventory.latest_object_modified_at = episode_snapshot.latest_object_modified_at
        inventory.last_seen_scan_id = scan_job.id

        selective_keys = {item.object_key for item in episode_snapshot.selective_objects}
        roles: set[str] = set()
        manifest_hash = inventory.manifest_hash
        metadata_hash = inventory.metadata_hash
        for object_snapshot in episode_snapshot.selective_objects:
            roles.add(object_snapshot.object_role)
            object_key = (inventory.id, object_snapshot.object_key)
            episode_object = existing_objects.get(object_key)
            if episode_object is None:
                episode_object = EpisodeObject(
                    episode_inventory_id=inventory.id,
                    object_key=object_snapshot.object_key,
                    object_scope=object_snapshot.object_scope,
                    object_role=object_snapshot.object_role,
                    size_bytes=object_snapshot.size_bytes,
                    content_hash=object_snapshot.content_hash,
                    last_modified=object_snapshot.last_modified,
                    last_seen_scan_id=scan_job.id,
                    source_status='present',
                    missing_streak=0,
                    last_confirmed_present_at=timestamp,
                )
                db.add(episode_object)
                existing_objects[object_key] = episode_object
            else:
                _mark_present(episode_object, now=timestamp)
                episode_object.object_scope = object_snapshot.object_scope
                episode_object.object_role = object_snapshot.object_role
                episode_object.size_bytes = object_snapshot.size_bytes
                episode_object.content_hash = object_snapshot.content_hash
                episode_object.last_modified = object_snapshot.last_modified
                episode_object.last_seen_scan_id = scan_job.id
            if object_snapshot.object_role == 'manifest':
                manifest_hash = object_snapshot.content_hash
            elif object_snapshot.object_role == 'metadata':
                metadata_hash = object_snapshot.content_hash

        for object_key, episode_object in existing_objects_by_inventory.get(inventory.id, {}).items():
            if object_key in selective_keys:
                continue
            if _advance_missing(
                episode_object,
                shard_id=shard_id,
                now=timestamp,
                confirmation_seconds=missing_confirmation_seconds,
            ):
                changed = True
            if episode_object.source_status == 'suspect_missing':
                result.needs_missing_confirmation = True

        inventory.manifest_hash = manifest_hash
        inventory.metadata_hash = metadata_hash
        duration, frames = _manifest_metrics(episode_snapshot.manifest, inventory.duration_sec, inventory.frame_count)
        inventory.duration_sec = duration
        inventory.frame_count = frames
        if episode_snapshot.manifest:
            inventory.episode_id_from_manifest = str(
                episode_snapshot.manifest.get('episode_id') or episode_snapshot.episode_name
            )
        elif not inventory.episode_id_from_manifest:
            inventory.episode_id_from_manifest = episode_snapshot.episode_name

        current_present_roles = {
            item.object_role
            for item in existing_objects_by_inventory.get(inventory.id, {}).values()
            if item.source_status != 'missing'
        } | roles
        derived_state = _derive_state(
            raw_exists=inventory.raw_source_status != 'missing' and inventory.raw_exists,
            processed_exists=inventory.processed_source_status != 'missing' and inventory.processed_exists,
            roles=current_present_roles,
            manifest=episode_snapshot.manifest,
        )
        if inventory.state != derived_state:
            inventory.state = derived_state
            inventory.state_changed_at = timestamp
        if STATE_RANK[derived_state] > STATE_RANK.get(inventory.max_observed_state, 0):
            inventory.max_observed_state = derived_state

        resolved_episode_id = inventory.ingested_episode_id or episode_id(resolved_batch_id, episode_snapshot.episode_name)
        episode = existing_episode_ids.get(resolved_episode_id)
        if episode is None:
            if batch.batch_decision != 'PENDING':
                raise ValueError(f'adjudicated Batch {batch.id} cannot accept new Episode without an explicit reset')
            episode = Episode(
                id=resolved_episode_id,
                batch_id=resolved_batch_id,
                task_name=batch.task_type.name if batch.task_type else unclassified.name,
                duration_sec=duration,
                frame_count=frames,
                qc_status='new',
                qc_result='pending',
                reviewer='-',
                reason_code='-',
                updated_at=timestamp,
                in_candidate_pool=1,
                sampled_for_qc=0,
                is_active=True,
            )
            db.add(episode)
            existing_episode_ids[episode.id] = episode
        else:
            episode.batch_id = resolved_batch_id
            episode.is_active = True
            if changed or episode.duration_sec != duration or episode.frame_count != frames:
                episode.duration_sec = duration
                episode.frame_count = frames
                episode.updated_at = timestamp
        inventory.ingested_episode_id = resolved_episode_id
        if changed:
            result.changed_episode_count += 1

    for episode_name, inventory in existing_inventory.items():
        if episode_name in seen_names:
            continue
        became_missing = _advance_missing(
            inventory,
            shard_id=shard_id,
            now=timestamp,
            confirmation_seconds=missing_confirmation_seconds,
        )
        if inventory.source_status == 'suspect_missing':
            result.suspect_episode_count += 1
            result.needs_missing_confirmation = True
        if became_missing:
            result.missing_episode_count += 1
            inventory.raw_source_status = 'missing'
            inventory.processed_source_status = 'missing'
            inventory.raw_exists = False
            inventory.processed_exists = False
            inventory.state = 'ingestable'
            inventory.state_changed_at = timestamp
            for episode_object in inventory.objects:
                _confirm_missing(
                    episode_object,
                    shard_id=shard_id,
                    now=timestamp,
                )
            if inventory.ingested_episode_id:
                episode = db.query(Episode).filter(Episode.id == inventory.ingested_episode_id).first()
                if episode is not None:
                    episode.is_active = False
                    episode.updated_at = timestamp

    if snapshot.is_full_coverage:
        list_record.has_raw = raw_count > 0
        list_record.has_processed = processed_count > 0
        list_record.total_raw_episodes = raw_count
        list_record.total_processed_episodes = processed_count
        list_record.confirmed_scan_id = scan_job.id
    db.flush()
    batch.episode_count = db.query(Episode).filter(
        Episode.batch_id == batch.id,
        Episode.is_active == True,
    ).count()
    result.touched_batch_ids.add(batch.id)
    enqueue_batch_asset_recompute(db, batch.id, reason='scan_sync')
    return result
