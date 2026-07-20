from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload

from app.models import (
    AnnotationRevision,
    AnnotationTask,
    AuditEvent,
    Batch,
    Episode,
    EpisodeAnnotation,
    EpisodeSubGoalInstance,
    ListRecord,
    SubGoalDefinition,
    SubGoalSchema,
    ReviewerAnnotationRollup,
    TaskAnnotationRollup,
    TaskType,
    User,
)


TASK_OUTCOMES = {
    'completed_normally',
    'completed_with_retry',
    'partially_completed',
    'failed',
    'uncertain',
}
INSTANCE_STATUSES = {'observed', 'failed', 'skipped', 'not_observed', 'not_applicable', 'uncertain'}
RANGED_INSTANCE_STATUSES = {'observed', 'failed'}
NO_RANGE_INSTANCE_STATUSES = {'skipped', 'not_observed', 'not_applicable'}
ANNOTATION_ROLES = {'admin', 'qc_manager', 'reviewer'}
ANNOTATION_ROLLUP_VERSION = 'task-annotation-rollup-v1'


def utcnow() -> datetime:
    return datetime.utcnow()


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def content_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def format_time(value: datetime | None) -> str | None:
    return value.replace(microsecond=0).isoformat() if value else None


def active_qualified_episode_query(db: Session):
    """Use the same active list/batch/episode scope as data-assets projections."""
    return db.query(Episode).join(Batch, Episode.batch_id == Batch.id).join(
        ListRecord, Batch.list_id == ListRecord.id
    ).filter(
        Episode.final_dataset_status == 'QUALIFIED',
        Episode.is_active.is_(True),
        Batch.is_active.is_(True),
        Batch.list_id.is_not(None),
        ListRecord.is_active.is_(True),
    )


def schema_payload(definitions: list[SubGoalDefinition]) -> dict:
    return {
        'definitions': [
            {
                'sequenceNo': item.sequence_no,
                'code': item.code,
                'nameEn': item.name_en,
                'nameZh': item.name_zh,
                'description': item.description,
                'actionVerb': item.action_verb,
                'isRequired': item.is_required,
                'isConditional': item.is_conditional,
                'maxOccurrences': item.max_occurrences,
                'objectRoleHints': item.object_role_hints or {},
            }
            for item in definitions
        ]
    }


def serialize_schema(schema: SubGoalSchema) -> dict:
    definitions = sorted(schema.definitions, key=lambda item: item.sequence_no)
    return {
        'id': schema.id,
        'taskTypeId': schema.task_type_id,
        'versionNo': schema.version_no,
        'status': schema.status,
        'contentHash': schema.content_hash,
        'definitions': [
            {
                'id': item.id,
                **payload,
            }
            for item, payload in zip(definitions, schema_payload(definitions)['definitions'])
        ],
        'createdAt': format_time(schema.created_at),
        'publishedAt': format_time(schema.published_at),
    }


def serialize_instance(instance: EpisodeSubGoalInstance) -> dict:
    definition = instance.definition
    return {
        'id': instance.id,
        'definitionId': instance.sub_goal_definition_id,
        'definitionCode': definition.code if definition else '',
        'definitionNameEn': definition.name_en if definition else '',
        'occurrenceNo': instance.occurrence_no,
        'status': instance.status,
        'startStep': instance.start_step,
        'endStepExclusive': instance.end_step_exclusive,
        'representativeStep': instance.representative_step,
        'failureReason': instance.failure_reason,
        'notes': instance.notes,
        'source': instance.source,
    }


def annotation_payload(annotation: EpisodeAnnotation) -> dict:
    return {
        'canonicalInstructionEn': annotation.canonical_instruction_en,
        'canonicalInstructionZh': annotation.canonical_instruction_zh,
        'instructionVariantsEn': annotation.instruction_variants_en or [],
        'episodeSummary': annotation.episode_summary,
        'objects': annotation.objects or [],
        'taskOutcome': annotation.task_outcome,
        'failureSubGoalInstanceId': annotation.failure_sub_goal_instance_id,
        'lastSuccessfulSubGoalInstanceId': annotation.last_successful_sub_goal_instance_id,
        'failureReason': annotation.failure_reason,
        'annotationNotes': annotation.annotation_notes,
        'annotationSchemaVersion': annotation.annotation_schema_version,
        'occurrences': [serialize_instance(item) for item in annotation.sub_goal_instances],
    }


def serialize_task(task: AnnotationTask) -> dict:
    episode = task.episode
    return {
        'id': task.id,
        'episodeId': task.episode_id,
        'batchId': task.batch_id,
        'batchName': task.batch.name if task.batch else '',
        'taskTypeId': task.task_type_id,
        'taskTypeName': task.task_type.name if task.task_type else '',
        'workStatus': task.work_status,
        'assignedTo': task.assigned_to,
        'assignedName': task.assigned_user.name if task.assigned_user else None,
        'assignedAt': format_time(task.assigned_at),
        'publicClaimEnabled': task.public_claim_enabled,
        'lockOwner': task.lock_owner,
        'lockExpiresAt': format_time(task.lock_expires_at),
        'currentRevisionNo': task.current_revision_no,
        'rowVersion': task.row_version,
        'initialSource': task.initial_source,
        'frameCount': episode.frame_count if episode else 0,
        'durationSec': episode.duration_sec if episode else 0,
        'finalDatasetStatus': episode.final_dataset_status if episode else '',
        'schema': serialize_schema(task.schema) if task.schema else None,
        'draft': annotation_payload(task.annotation) if task.annotation else None,
        'createdAt': format_time(task.created_at),
        'updatedAt': format_time(task.updated_at),
    }


def create_schema(
    db: Session,
    *,
    task_type_id: str,
    definitions: list[dict],
    user: User,
) -> SubGoalSchema:
    task_type = db.query(TaskType).filter(TaskType.id == task_type_id).first()
    if not task_type:
        raise ValueError('TaskType 不存在')
    if not definitions:
        raise ValueError('Schema 至少需要一个 Sub Goal Definition')
    seen_codes: set[str] = set()
    seen_sequences: set[int] = set()
    normalized: list[dict] = []
    for raw in definitions:
        code = str(raw.get('code') or '').strip()
        sequence_no = int(raw.get('sequenceNo', 0))
        if not code or code in seen_codes:
            raise ValueError('Definition code 不能为空且不得重复')
        if sequence_no < 1 or sequence_no in seen_sequences:
            raise ValueError('Definition sequenceNo 必须从 1 开始且不得重复')
        max_occurrences = raw.get('maxOccurrences')
        if max_occurrences is not None and int(max_occurrences) < 1:
            raise ValueError('maxOccurrences 必须为正整数')
        seen_codes.add(code)
        seen_sequences.add(sequence_no)
        normalized.append({
            'sequenceNo': sequence_no,
            'code': code,
            'nameEn': str(raw.get('nameEn') or '').strip(),
            'nameZh': str(raw.get('nameZh') or '').strip(),
            'description': str(raw.get('description') or '').strip(),
            'actionVerb': str(raw.get('actionVerb') or '').strip(),
            'isRequired': bool(raw.get('isRequired', False)),
            'isConditional': bool(raw.get('isConditional', False)),
            'maxOccurrences': int(max_occurrences) if max_occurrences is not None else None,
            'objectRoleHints': raw.get('objectRoleHints') or {},
        })
    normalized.sort(key=lambda item: item['sequenceNo'])
    version_no = (db.query(func.max(SubGoalSchema.version_no)).filter(
        SubGoalSchema.task_type_id == task_type_id
    ).scalar() or 0) + 1
    payload = {'definitions': normalized}
    schema = SubGoalSchema(
        task_type_id=task_type_id,
        version_no=version_no,
        status='draft',
        schema_payload=payload,
        content_hash=content_hash(payload),
        created_by=user.id,
    )
    db.add(schema)
    db.flush()
    for item in normalized:
        db.add(SubGoalDefinition(
            sub_goal_schema_id=schema.id,
            sequence_no=item['sequenceNo'],
            code=item['code'],
            name_en=item['nameEn'],
            name_zh=item['nameZh'],
            description=item['description'],
            action_verb=item['actionVerb'],
            is_required=item['isRequired'],
            is_conditional=item['isConditional'],
            max_occurrences=item['maxOccurrences'],
            object_role_hints=item['objectRoleHints'],
        ))
    db.flush()
    return schema


def publish_schema(db: Session, schema: SubGoalSchema, user: User) -> SubGoalSchema:
    if schema.status != 'draft':
        raise ValueError('只有 draft Schema 可以发布')
    if not schema.definitions:
        raise ValueError('Schema 至少需要一个 Definition')
    other = db.query(SubGoalSchema).filter(
        SubGoalSchema.task_type_id == schema.task_type_id,
        SubGoalSchema.status == 'published',
        SubGoalSchema.id != schema.id,
    ).all()
    now = utcnow()
    for item in other:
        item.status = 'retired'
        item.retired_by = user.id
        item.retired_at = now
        item.retirement_reason = f'replaced_by:{schema.id}'
    schema.status = 'published'
    schema.published_by = user.id
    schema.published_at = now
    task_type = db.query(TaskType).filter(TaskType.id == schema.task_type_id).first()
    if not task_type:
        raise ValueError('Schema 的 TaskType 不存在')
    task_type.default_published_sub_goal_schema_id = schema.id
    db.flush()
    return schema


def get_task(db: Session, task_id: str) -> AnnotationTask | None:
    return db.query(AnnotationTask).options(
        joinedload(AnnotationTask.episode),
        joinedload(AnnotationTask.batch),
        joinedload(AnnotationTask.task_type),
        joinedload(AnnotationTask.schema).joinedload(SubGoalSchema.definitions),
        joinedload(AnnotationTask.assigned_user),
        joinedload(AnnotationTask.annotation).joinedload(EpisodeAnnotation.sub_goal_instances).joinedload(
            EpisodeSubGoalInstance.definition
        ),
    ).filter(AnnotationTask.id == task_id).first()


def get_task_for_update(db: Session, task_id: str) -> AnnotationTask | None:
    """Lock task-state transitions so concurrent assignment or claim cannot overwrite ownership."""
    return db.query(AnnotationTask).filter(AnnotationTask.id == task_id).with_for_update().first()


def assert_task_editable(task: AnnotationTask, user: User, *, require_lock: bool = True) -> None:
    if user.role not in ANNOTATION_ROLES:
        raise PermissionError('无权限编辑标注')
    if task.work_status == 'invalidated':
        raise ValueError('标注任务已失效')
    if user.role == 'reviewer' and task.assigned_to != user.id:
        raise PermissionError('只能编辑分配给本人的标注任务')
    if require_lock and user.role == 'reviewer':
        if task.lock_owner != user.id or not task.lock_expires_at or task.lock_expires_at <= utcnow():
            raise ValueError('请先获取有效编辑锁')


def create_draft(db: Session, task: AnnotationTask) -> EpisodeAnnotation:
    if task.annotation:
        return task.annotation
    annotation = EpisodeAnnotation(annotation_task_id=task.id)
    task.annotation = annotation
    db.flush()
    return annotation


def ensure_task_for_episode(db: Session, episode: Episode, *, initial_source: str = 'manual') -> AnnotationTask:
    if episode.final_dataset_status != 'QUALIFIED':
        raise ValueError('Episode 不满足 QUALIFIED 标注资格')
    scoped = active_qualified_episode_query(db).filter(Episode.id == episode.id).first()
    if scoped is None:
        raise ValueError('Episode 不在 active_list_active_batch_indexed_episodes 作用域')
    existing = db.query(AnnotationTask).filter(AnnotationTask.episode_id == episode.id).first()
    if existing:
        if existing.work_status == 'invalidated':
            previous_status = existing.status_before_invalidation or 'pending'
            existing.work_status = restored_annotation_work_status(existing, previous_status)
            existing.status_before_invalidation = None
            existing.invalidated_at = None
            existing.invalidation_reason = None
            existing.row_version += 1
            audit(
                db,
                user=_system_annotation_user(),
                action='恢复标注任务资格',
                target=existing.id,
                detail=f'stored_status={previous_status} restored_status={existing.work_status} reason=ensure_eligible_task',
            )
            recompute_annotation_rollup(db, existing.task_type_id)
        return existing
    batch = db.query(Batch).filter(Batch.id == episode.batch_id).first()
    if not batch:
        raise ValueError('Episode 的 Batch 不存在')
    schema = db.query(SubGoalSchema).options(joinedload(SubGoalSchema.definitions)).filter(
        SubGoalSchema.id == batch.task_type.default_published_sub_goal_schema_id,
        SubGoalSchema.task_type_id == batch.task_type_id,
        SubGoalSchema.status == 'published',
    ).first()
    if not schema:
        raise ValueError('TaskType 缺少 default published Sub Goal Schema')
    task = AnnotationTask(
        episode_id=episode.id,
        batch_id=batch.id,
        task_type_id=batch.task_type_id,
        sub_goal_schema_id=schema.id,
        sub_goal_schema_version=schema.version_no,
        sub_goal_schema_content_hash=schema.content_hash,
        initial_source=initial_source,
    )
    db.add(task)
    db.flush()
    create_draft(db, task)
    recompute_annotation_rollup(db, task.task_type_id)
    return task


def ensure_tasks_for_episodes(
    db: Session,
    episodes: list[Episode],
) -> tuple[list[AnnotationTask], list[dict]]:
    tasks: list[AnnotationTask] = []
    skipped: list[dict] = []
    for episode in episodes:
        try:
            existing = db.query(AnnotationTask).filter(AnnotationTask.episode_id == episode.id).first()
            task = ensure_task_for_episode(db, episode)
            if existing is None:
                tasks.append(task)
        except Exception as exc:
            skipped.append({'episodeId': episode.id, 'reason': str(exc)})
    return tasks, skipped


def recompute_annotation_rollup(db: Session, task_type_id: str) -> TaskAnnotationRollup | None:
    """Refresh one TaskType's operational projection in the caller's transaction."""
    if not task_type_id:
        return None
    db.flush()
    now = utcnow()
    aggregate = db.query(
        func.count(AnnotationTask.id).label('total_count'),
        func.coalesce(func.sum(case((AnnotationTask.work_status == 'pending', 1), else_=0)), 0).label('pending_count'),
        func.coalesce(func.sum(case((AnnotationTask.work_status == 'assigned', 1), else_=0)), 0).label('assigned_count'),
        func.coalesce(func.sum(case((AnnotationTask.work_status == 'in_progress', 1), else_=0)), 0).label('in_progress_count'),
        func.coalesce(func.sum(case((AnnotationTask.work_status == 'completed', 1), else_=0)), 0).label('completed_count'),
        func.coalesce(func.sum(case((AnnotationTask.work_status == 'invalidated', 1), else_=0)), 0).label('invalidated_count'),
    ).filter(AnnotationTask.task_type_id == task_type_id).one()
    eligible_aggregate = active_qualified_episode_query(db).filter(
        Batch.task_type_id == task_type_id
    ).outerjoin(
        AnnotationTask, AnnotationTask.episode_id == Episode.id
    ).with_entities(
        func.count(Episode.id).label('eligible_episode_count'),
        func.coalesce(func.sum(case((AnnotationTask.id.is_(None), 1), else_=0)), 0).label('unannotated_count'),
        func.coalesce(func.sum(case((AnnotationTask.work_status == 'completed', 1), else_=0)), 0).label(
            'active_completed_count'
        ),
    ).one()
    rollup = db.query(TaskAnnotationRollup).filter(TaskAnnotationRollup.task_type_id == task_type_id).first()
    if rollup is None:
        rollup = TaskAnnotationRollup(task_type_id=task_type_id, refreshed_at=now)
        db.add(rollup)
    rollup.eligible_episode_count = int(eligible_aggregate.eligible_episode_count or 0)
    rollup.unannotated_count = int(eligible_aggregate.unannotated_count or 0)
    rollup.active_completed_count = int(eligible_aggregate.active_completed_count or 0)
    rollup.total_count = int(aggregate.total_count or 0)
    rollup.pending_count = int(aggregate.pending_count or 0)
    rollup.assigned_count = int(aggregate.assigned_count or 0)
    rollup.in_progress_count = int(aggregate.in_progress_count or 0)
    rollup.completed_count = int(aggregate.completed_count or 0)
    rollup.invalidated_count = int(aggregate.invalidated_count or 0)
    rollup.source_task_count = rollup.total_count
    rollup.calculation_version = ANNOTATION_ROLLUP_VERSION
    rollup.refreshed_at = now

    db.query(ReviewerAnnotationRollup).filter(
        ReviewerAnnotationRollup.task_type_id == task_type_id
    ).delete(synchronize_session='fetch')
    reviewer_rows = db.query(
        AnnotationTask.assigned_to,
        func.count(AnnotationTask.id),
    ).filter(
        AnnotationTask.task_type_id == task_type_id,
        AnnotationTask.assigned_to.is_not(None),
        AnnotationTask.work_status.in_({'assigned', 'in_progress'}),
    ).group_by(AnnotationTask.assigned_to).all()
    for reviewer_id, task_count in reviewer_rows:
        db.add(ReviewerAnnotationRollup(
            task_type_id=task_type_id,
            reviewer_id=reviewer_id,
            task_count=int(task_count or 0),
            refreshed_at=now,
        ))
    db.flush()
    return rollup


def rebuild_all_annotation_rollups(db: Session) -> int:
    task_type_ids = {
        task_type_id
        for (task_type_id,) in db.query(AnnotationTask.task_type_id).distinct().all()
        if task_type_id
    }
    task_type_ids.update(
        task_type_id
        for (task_type_id,) in active_qualified_episode_query(db).with_entities(Batch.task_type_id).distinct().all()
        if task_type_id
    )
    for task_type_id in task_type_ids:
        recompute_annotation_rollup(db, task_type_id)
    return len(task_type_ids)


def annotation_eligibility(db: Session, *, task_type_id: str | None = None) -> dict:
    """Read active-scope eligibility counts from the operational projection."""
    if task_type_id:
        rollup = db.query(TaskAnnotationRollup).filter(TaskAnnotationRollup.task_type_id == task_type_id).first()
        if rollup is None:
            rollup = recompute_annotation_rollup(db, task_type_id)
        eligible_count = int(rollup.eligible_episode_count or 0) if rollup else 0
        unannotated_count = int(rollup.unannotated_count or 0) if rollup else 0
        return {
            'eligibleCount': eligible_count,
            # This is the number of tasks inside the current active qualified
            # scope, not historical invalidated tasks for the TaskType.
            'taskCount': eligible_count - unannotated_count,
            'unannotatedCount': unannotated_count,
        }
    aggregate = db.query(
        func.coalesce(func.sum(TaskAnnotationRollup.eligible_episode_count), 0),
        func.coalesce(func.sum(TaskAnnotationRollup.unannotated_count), 0),
    ).one()
    return {
        'eligibleCount': int(aggregate[0] or 0),
        'taskCount': int(aggregate[0] or 0) - int(aggregate[1] or 0),
        'unannotatedCount': int(aggregate[1] or 0),
    }


def annotation_statistics(db: Session, *, task_type_id: str | None = None) -> dict:
    """Read operation statistics from persistent annotation rollups."""
    if task_type_id:
        rollup = db.query(TaskAnnotationRollup).filter(TaskAnnotationRollup.task_type_id == task_type_id).first()
        if rollup is None:
            rollup = recompute_annotation_rollup(db, task_type_id)
        total = int(rollup.total_count or 0) if rollup else 0
        completed = int(rollup.completed_count or 0) if rollup else 0
        eligible_count = int(rollup.eligible_episode_count or 0) if rollup else 0
        active_completed_count = int(rollup.active_completed_count or 0) if rollup else 0
        by_status = {
            status: count
            for status, count in {
                'pending': int(rollup.pending_count or 0) if rollup else 0,
                'assigned': int(rollup.assigned_count or 0) if rollup else 0,
                'in_progress': int(rollup.in_progress_count or 0) if rollup else 0,
                'completed': completed,
                'invalidated': int(rollup.invalidated_count or 0) if rollup else 0,
            }.items()
            if count
        }
        reviewer_rows = db.query(
            ReviewerAnnotationRollup.reviewer_id,
            ReviewerAnnotationRollup.task_count,
        ).filter(ReviewerAnnotationRollup.task_type_id == task_type_id).all()
    else:
        aggregate = db.query(
            func.coalesce(func.sum(TaskAnnotationRollup.total_count), 0),
            func.coalesce(func.sum(TaskAnnotationRollup.pending_count), 0),
            func.coalesce(func.sum(TaskAnnotationRollup.assigned_count), 0),
            func.coalesce(func.sum(TaskAnnotationRollup.in_progress_count), 0),
            func.coalesce(func.sum(TaskAnnotationRollup.completed_count), 0),
            func.coalesce(func.sum(TaskAnnotationRollup.invalidated_count), 0),
            func.coalesce(func.sum(TaskAnnotationRollup.active_completed_count), 0),
        ).one()
        total = int(aggregate[0] or 0)
        completed = int(aggregate[4] or 0)
        eligible_count = int(db.query(func.coalesce(func.sum(TaskAnnotationRollup.eligible_episode_count), 0)).scalar() or 0)
        active_completed_count = int(aggregate[6] or 0)
        by_status = {
            status: count
            for status, count in {
                'pending': int(aggregate[1] or 0),
                'assigned': int(aggregate[2] or 0),
                'in_progress': int(aggregate[3] or 0),
                'completed': completed,
                'invalidated': int(aggregate[5] or 0),
            }.items()
            if count
        }
        reviewer_rows = db.query(
            ReviewerAnnotationRollup.reviewer_id,
            func.coalesce(func.sum(ReviewerAnnotationRollup.task_count), 0),
        ).group_by(ReviewerAnnotationRollup.reviewer_id).all()
    invalidated_count = int(
        (rollup.invalidated_count if task_type_id and rollup else aggregate[5] if not task_type_id else 0) or 0
    )
    return {
        # Preserve total as all persisted task history so it remains the sum of
        # byStatus. Active operational counts are explicit separate fields.
        'total': total,
        'activeTaskCount': total - invalidated_count,
        'eligibleEpisodeCount': eligible_count,
        'completed': completed,
        'activeCompletedCount': active_completed_count,
        # Coverage uses the unified export scope as denominator. Invalidated
        # task history never dilutes the active annotation completion rate.
        'completionRate': active_completed_count / eligible_count if eligible_count else 0,
        'byStatus': by_status,
        'byReviewer': [
            {'reviewerId': reviewer_id, 'count': int(count or 0)}
            for reviewer_id, count in reviewer_rows
        ],
    }


def reconcile_annotation_eligibility(
    db: Session,
    *,
    episode_ids: set[str] | None = None,
    list_ids: set[str] | None = None,
    reason: str = 'episode_left_active_scope',
) -> dict[str, int]:
    """Synchronize existing task lifecycle with the canonical active QUALIFIED scope.

    This deliberately does not create missing tasks. New eligible data enters the
    annotation pool only through the explicit ensure flow or the future VLM queue.
    """
    # Core production sessions disable autoflush. Publish an adjudication or scan
    # mutation before querying the canonical scope, otherwise task invalidation
    # observes the previous Episode eligibility until a later transaction.
    db.flush()
    task_query = db.query(AnnotationTask).join(Episode, AnnotationTask.episode_id == Episode.id).join(
        Batch, Episode.batch_id == Batch.id
    )
    if episode_ids is not None:
        task_query = task_query.filter(AnnotationTask.episode_id.in_(episode_ids))
    if list_ids is not None:
        task_query = task_query.filter(Batch.list_id.in_(list_ids))
    tasks = task_query.with_for_update().all()
    affected_task_type_ids = {task.task_type_id for task in tasks if task.task_type_id}
    if episode_ids is not None:
        affected_task_type_ids.update(
            task_type_id
            for (task_type_id,) in db.query(Batch.task_type_id).join(
                Episode, Episode.batch_id == Batch.id
            ).filter(Episode.id.in_(episode_ids)).distinct().all()
            if task_type_id
        )
    if list_ids is not None:
        affected_task_type_ids.update(
            task_type_id
            for (task_type_id,) in db.query(Batch.task_type_id).filter(Batch.list_id.in_(list_ids)).distinct().all()
            if task_type_id
        )
    if episode_ids is None and list_ids is None:
        affected_task_type_ids.update(
            task_type_id
            for (task_type_id,) in active_qualified_episode_query(db).with_entities(Batch.task_type_id).distinct().all()
            if task_type_id
        )
    if not tasks:
        for task_type_id in affected_task_type_ids:
            recompute_annotation_rollup(db, task_type_id)
        return {'invalidated': 0, 'restored': 0}

    candidate_ids = {task.episode_id for task in tasks}
    eligible_ids = {
        episode_id
        for (episode_id,) in active_qualified_episode_query(db).with_entities(Episode.id).filter(
            Episode.id.in_(candidate_ids)
        ).all()
    }
    now = utcnow()
    invalidated = 0
    restored = 0
    for task in tasks:
        if task.episode_id in eligible_ids:
            if task.work_status == 'invalidated':
                previous_status = task.status_before_invalidation or 'pending'
                # Invalidation revokes the edit lease. Do not resurrect an
                # in-progress task without a lock; keep its assignment and
                # require the reviewer to acquire a fresh lease.
                restored_status = restored_annotation_work_status(task, previous_status)
                task.work_status = restored_status
                task.status_before_invalidation = None
                task.invalidated_at = None
                task.invalidation_reason = None
                task.row_version += 1
                audit(
                    db,
                    user=_system_annotation_user(),
                    action='恢复标注任务资格',
                    target=task.id,
                    detail=f'stored_status={previous_status} restored_status={restored_status} reason={reason}',
                )
                restored += 1
            continue
        if task.work_status == 'invalidated':
            continue
        task.status_before_invalidation = task.work_status
        task.work_status = 'invalidated'
        task.invalidated_at = now
        task.invalidation_reason = reason
        task.public_claim_enabled = False
        task.lock_owner = None
        task.lock_acquired_at = None
        task.lock_expires_at = None
        task.row_version += 1
        audit(
            db,
            user=_system_annotation_user(),
            action='标注任务资格失效',
            target=task.id,
            detail=f'status={task.status_before_invalidation} reason={reason}',
        )
        # Cancel pending VLM generation jobs for this task; running jobs
        # will observe task invalidation via re-check on publication.
        from app.services.annotation_generation_queue import cancel_pending_jobs_for_task
        cancel_pending_jobs_for_task(db, annotation_task_id=task.id)
        invalidated += 1
    for task_type_id in affected_task_type_ids:
        recompute_annotation_rollup(db, task_type_id)
    return {'invalidated': invalidated, 'restored': restored}


def restored_annotation_work_status(task: AnnotationTask, previous_status: str) -> str:
    """Restore an invalidated task without recreating its revoked edit lease."""
    if previous_status == 'in_progress':
        return 'assigned' if task.assigned_to else 'pending'
    return previous_status


def _system_annotation_user() -> User:
    return User(id='system', username='system', name='system', role='admin', avatar='S', password_hash='')


def invalidate_ineligible_tasks(db: Session, *, reason: str = 'episode_left_active_scope') -> int:
    """Compatibility entry point for full-scope reconciliation callers."""
    return reconcile_annotation_eligibility(db, reason=reason)['invalidated']


def acquire_lock(db: Session, task: AnnotationTask, user: User) -> None:
    assert_task_editable(task, user, require_lock=False)
    now = utcnow()
    if task.lock_owner and task.lock_expires_at and task.lock_expires_at > now and task.lock_owner != user.id:
        raise ValueError('任务已被其他用户锁定')
    task.lock_owner = user.id
    task.lock_acquired_at = now
    task.lock_expires_at = now + timedelta(minutes=5)
    # Re-editing a completed annotation starts a new pending revision cycle.
    if task.work_status == 'completed':
        task.work_status = 'pending'
    if task.work_status in {'pending', 'assigned'}:
        task.work_status = 'in_progress'
    task.row_version += 1
    recompute_annotation_rollup(db, task.task_type_id)


def release_lock(db: Session, task: AnnotationTask, user: User, *, force: bool = False) -> None:
    if not force and task.lock_owner != user.id:
        raise ValueError('当前用户不是锁持有者')
    if force and user.role not in {'admin', 'qc_manager'}:
        raise PermissionError('只有管理员可以强制释放编辑锁')
    task.lock_owner = None
    task.lock_acquired_at = None
    task.lock_expires_at = None
    task.row_version += 1


def _normalize_variants(variants: list[str]) -> list[str]:
    result = [item.strip() for item in variants if item and item.strip()]
    if len(result) > 5:
        raise ValueError('instruction_variants_en 最多 5 条')
    if len(set(result)) != len(result):
        raise ValueError('instruction_variants_en 不得重复')
    return result


def _replace_instances(db: Session, annotation: EpisodeAnnotation, occurrences: list[dict]) -> None:
    definitions = {item.id: item for item in annotation.task.schema.definitions}
    existing = {item.id: item for item in annotation.sub_goal_instances}
    keep: set[int] = set()
    normalized: list[tuple[EpisodeSubGoalInstance, dict]] = []
    for raw in occurrences:
        definition_id = str(raw.get('definitionId') or raw.get('sub_goal_definition_id') or '')
        definition = definitions.get(definition_id)
        if definition is None:
            raise ValueError('occurrence 引用了冻结 Schema 外的 Definition')
        occurrence_no = int(raw.get('occurrenceNo', raw.get('occurrence_no', 0)))
        if occurrence_no < 1:
            raise ValueError('occurrence_no 必须从 1 开始')
        item_id = raw.get('id')
        instance = existing.get(int(item_id)) if item_id is not None and str(item_id).isdigit() else None
        if instance is None:
            instance = EpisodeSubGoalInstance(
                episode_annotation_id=annotation.id,
                sub_goal_definition_id=definition_id,
                occurrence_no=occurrence_no,
            )
            annotation.sub_goal_instances.append(instance)
        instance.sub_goal_definition_id = definition_id
        instance.occurrence_no = occurrence_no
        instance.status = str(raw.get('status') or 'observed')
        instance.start_step = raw.get('startStep', raw.get('start_step'))
        instance.end_step_exclusive = raw.get('endStepExclusive', raw.get('end_step_exclusive'))
        instance.representative_step = raw.get('representativeStep', raw.get('representative_step'))
        instance.failure_reason = raw.get('failureReason', raw.get('failure_reason'))
        instance.notes = raw.get('notes')
        instance.source = str(raw.get('source') or 'human')
        if instance.id:
            keep.add(instance.id)
        normalized.append((instance, raw))
    db.flush()
    for old in list(annotation.sub_goal_instances):
        if old.id not in keep and old not in [item for item, _ in normalized]:
            db.delete(old)


def save_draft(db: Session, task: AnnotationTask, user: User, payload: dict) -> EpisodeAnnotation:
    assert_task_editable(task, user)
    annotation = create_draft(db, task)
    expected = int(payload['rowVersion'])
    if task.row_version != expected:
        raise ValueError('草稿版本已变更，请刷新后重试')
    annotation.canonical_instruction_en = str(payload.get('canonicalInstructionEn') or '').strip()
    annotation.canonical_instruction_zh = payload.get('canonicalInstructionZh')
    annotation.instruction_variants_en = _normalize_variants(payload.get('instructionVariantsEn') or [])
    annotation.episode_summary = payload.get('episodeSummary')
    annotation.objects = payload.get('objects') or []
    annotation.task_outcome = payload.get('taskOutcome')
    annotation.failure_sub_goal_instance_id = payload.get('failureSubGoalInstanceId')
    annotation.last_successful_sub_goal_instance_id = payload.get('lastSuccessfulSubGoalInstanceId')
    annotation.failure_reason = payload.get('failureReason')
    annotation.annotation_notes = payload.get('annotationNotes')
    annotation.human_modified = True
    _replace_instances(db, annotation, payload.get('occurrences') or [])
    annotation.row_version += 1
    task.row_version += 1
    db.flush()
    return annotation


def validate_completion(task: AnnotationTask) -> None:
    annotation = task.annotation
    if not annotation:
        raise ValueError('缺少标注草稿')
    instruction = (annotation.canonical_instruction_en or '').strip()
    if not instruction:
        raise ValueError('canonical_instruction_en 不能为空')
    if annotation.task_outcome not in TASK_OUTCOMES:
        raise ValueError('task_outcome 不是有效值')
    if annotation.failure_sub_goal_instance_id and not any(
        item.id == annotation.failure_sub_goal_instance_id for item in annotation.sub_goal_instances
    ):
        raise ValueError('failure_sub_goal_instance_id 不属于当前 Episode')
    if annotation.last_successful_sub_goal_instance_id and not any(
        item.id == annotation.last_successful_sub_goal_instance_id for item in annotation.sub_goal_instances
    ):
        raise ValueError('last_successful_sub_goal_instance_id 不属于当前 Episode')
    if annotation.task_outcome == 'failed' and (
        not annotation.failure_sub_goal_instance_id or not (annotation.failure_reason or '').strip()
    ):
        raise ValueError('task_outcome=failed 必须填写失败 occurrence 和 failure_reason')
    definitions = {item.id: item for item in task.schema.definitions}
    grouped: dict[str, list[EpisodeSubGoalInstance]] = {}
    for item in annotation.sub_goal_instances:
        definition = definitions.get(item.sub_goal_definition_id)
        if not definition:
            raise ValueError('occurrence 引用了冻结 Schema 外的 Definition')
        if item.status not in INSTANCE_STATUSES:
            raise ValueError('Sub Goal occurrence 状态无效')
        if item.status == 'uncertain':
            raise ValueError('uncertain occurrence 不能作为最终训练边界')
        if item.occurrence_no < 1:
            raise ValueError('occurrence_no 必须从 1 开始')
        if item.status in RANGED_INSTANCE_STATUSES:
            start, end, representative = item.start_step, item.end_step_exclusive, item.representative_step
            frame_count = task.episode.frame_count
            if start is None or end is None or representative is None or not (0 <= start < end <= frame_count):
                raise ValueError('有时间范围的 occurrence 必须在 Episode 边界内')
            if not (start <= representative < end):
                raise ValueError('representative_step 必须位于 occurrence 范围内')
            if item.status == 'failed' and not (item.failure_reason or '').strip():
                raise ValueError('failed occurrence 必须填写 failure_reason')
        elif item.status in NO_RANGE_INSTANCE_STATUSES:
            if any(value is not None for value in (item.start_step, item.end_step_exclusive, item.representative_step)):
                raise ValueError(f'{item.status} occurrence 禁止填写时间范围')
        grouped.setdefault(item.sub_goal_definition_id, []).append(item)
    for definition_id, items in grouped.items():
        definition = definitions[definition_id]
        if definition.max_occurrences is not None and len(items) > definition.max_occurrences:
            raise ValueError(f'{definition.code} 超过 max_occurrences')
        numbers = sorted(item.occurrence_no for item in items)
        if numbers != list(range(1, len(numbers) + 1)):
            raise ValueError(f'{definition.code} occurrence_no 必须连续')
        ranged = sorted(
            (item.start_step, item.end_step_exclusive)
            for item in items
            if item.start_step is not None and item.end_step_exclusive is not None
        )
        if any(ranged[index][1] > ranged[index + 1][0] for index in range(len(ranged) - 1)):
            raise ValueError(f'{definition.code} occurrence 时间范围不得重叠')
    for definition in definitions.values():
        if definition.is_required and not definition.is_conditional and not grouped.get(definition.id):
            raise ValueError(f'缺少必需 Sub Goal: {definition.code}')


def complete_task(db: Session, task: AnnotationTask, user: User) -> AnnotationRevision:
    assert_task_editable(task, user)
    validate_completion(task)
    payload = {
        'subGoalSchemaId': task.sub_goal_schema_id,
        'subGoalSchemaVersion': task.sub_goal_schema_version,
        'subGoalSchemaContentHash': task.sub_goal_schema_content_hash,
        **annotation_payload(task.annotation),
    }
    revision_no = task.current_revision_no + 1
    revision = AnnotationRevision(
        annotation_task_id=task.id,
        episode_annotation_id=task.annotation.id,
        revision_no=revision_no,
        annotation_payload=payload,
        content_hash=content_hash(payload),
        created_by=user.id,
    )
    db.add(revision)
    task.current_revision_no = revision_no
    task.work_status = 'completed'
    task.completed_by = user.id
    task.completed_at = utcnow()
    task.lock_owner = None
    task.lock_acquired_at = None
    task.lock_expires_at = None
    task.row_version += 1
    db.flush()
    recompute_annotation_rollup(db, task.task_type_id)
    return revision


def audit(db: Session, *, user: User, action: str, target: str, detail: str = '') -> None:
    db.add(AuditEvent(
        id=f'annotation_{action}_{target}_{int(utcnow().timestamp() * 1000)}',
        operator=user.name,
        action=action,
        target=target,
        detail=detail,
        time=utcnow(),
    ))
