"""Dataset summary and unified QUALIFIED export services."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.models import (
    AnnotationRevision,
    AnnotationTask,
    AuditEvent,
    Batch,
    DatasetExportItem,
    DatasetExportJob,
    Episode,
    ListRecord,
    SubGoalSchema,
    TaskType,
)


class DatasetSummaryService:
    """Task-level dataset statistics for downstream consumers."""

    @staticmethod
    def task_summary(db: Session, task_type_id: str) -> dict | None:
        task_type = db.query(TaskType).filter(TaskType.id == task_type_id, TaskType.is_active == True).first()
        if not task_type:
            return None

        batches = db.query(Batch).join(ListRecord, Batch.list_id == ListRecord.id).filter(
            Batch.task_type_id == task_type_id,
            Batch.is_active == True,
            ListRecord.is_active == True,
        ).all()
        episodes = db.query(Episode).join(Batch, Episode.batch_id == Batch.id).join(
            ListRecord, Batch.list_id == ListRecord.id
        ).filter(
            Batch.task_type_id == task_type_id,
            Batch.is_active == True,
            ListRecord.is_active == True,
            Episode.is_active == True,
        ).all()

        qualified = [e for e in episodes if e.final_dataset_status == 'QUALIFIED']
        qualified_ids = [e.id for e in qualified]
        completed_annotation_ids: set[str] = set()
        if qualified_ids:
            completed_annotation_ids = {
                episode_id for episode_id, in db.query(AnnotationTask.episode_id).join(
                    AnnotationRevision,
                    (AnnotationRevision.annotation_task_id == AnnotationTask.id)
                    & (AnnotationRevision.revision_no == AnnotationTask.current_revision_no),
                ).filter(
                    AnnotationTask.episode_id.in_(qualified_ids),
                    AnnotationTask.task_type_id == task_type_id,
                    AnnotationTask.work_status == 'completed',
                ).all()
            }
        total = len(episodes)
        batch_count = len(batches)
        accepted = sum(1 for b in batches if b.batch_decision == 'ACCEPTED')
        rejected = sum(1 for b in batches if b.batch_decision == 'REJECTED')
        pending = sum(1 for b in batches if b.batch_decision == 'PENDING')

        source_counts: dict[str, int] = {}
        for e in episodes:
            src = e.final_decision_source
            source_counts[src] = source_counts.get(src, 0) + 1

        completed_count = len(completed_annotation_ids)
        qualified_count = len(qualified_ids)
        return {
            'taskId': task_type.id,
            'taskName': task_type.name,
            'qualifiedEpisodeCount': qualified_count,
            'totalEpisodeCount': total,
            'batchCount': batch_count,
            'acceptedBatchCount': accepted,
            'rejectedBatchCount': rejected,
            'pendingBatchCount': pending,
            'manualPassCount': sum(1 for e in episodes if e.manual_qc_status == 'MANUAL_PASS'),
            'manualFailCount': sum(1 for e in episodes if e.manual_qc_status == 'MANUAL_FAIL'),
            'inferredPassCount': source_counts.get('BATCH_ACCEPT_INFERRED_PASS', 0),
            'propagatedFailCount': source_counts.get('BATCH_REJECT_PROPAGATED_FAIL', 0),
            'overrideManualPassFailCount': source_counts.get('BATCH_REJECT_OVERRIDE_MANUAL_PASS', 0),
            'exportableEpisodeCount': sum(1 for e in episodes if e.is_exportable),
            'annotationCompletedEpisodeCount': completed_count,
            'annotationPendingEpisodeCount': qualified_count - completed_count,
            'annotationCoverageRate': (completed_count / qualified_count) if qualified_count else None,
        }

    @staticmethod
    def task_batches(db: Session, task_type_id: str) -> list[dict]:
        batches = db.query(Batch).join(ListRecord, Batch.list_id == ListRecord.id).filter(
            Batch.task_type_id == task_type_id,
            Batch.is_active == True,
            ListRecord.is_active == True,
        ).order_by(Batch.imported_at.desc()).all()
        result = []
        for batch in batches:
            available = db.query(Episode).filter(
                Episode.batch_id == batch.id,
                Episode.final_dataset_status == 'QUALIFIED',
                Episode.is_active == True,
            ).count()
            result.append({
                'batchId': batch.id,
                'batchName': batch.name,
                'totalCount': batch.episode_count,
                'sampledCount': batch.sampled_episode_count,
                'reviewedCount': batch.completed_sample_count,
                'manualFailCount': batch.manual_fail_count,
                'manualPassCount': batch.manual_pass_count,
                'failureRate': batch.failure_rate,
                'batchDecision': batch.batch_decision,
                'batchDecisionReason': batch.batch_decision_reason,
                'adjudicatedAt': batch.adjudicated_at.isoformat() if batch.adjudicated_at else None,
                'availableEpisodeCount': available,
            })
        return result


class DatasetExportService:
    """Export all active-scope QUALIFIED episodes with optional annotation enhancements."""

    EXPORT_FIELDS = [
        ('episode_id', lambda e: e.id),
        ('task_name', lambda e: e.task_name),
        ('batch_id', lambda e: e.batch_id),
        ('batch_name', lambda e: e.batch.name if e.batch else ''),
        ('final_dataset_status', lambda e: e.final_dataset_status),
        ('final_decision_source', lambda e: e.final_decision_source),
        ('final_decision_reason', lambda e: e.final_decision_reason),
        ('manual_qc_status', lambda e: e.manual_qc_status),
        ('reviewer', lambda e: e.reviewer if e.reviewer and e.reviewer != '-' else ''),
        ('reason_code', lambda e: e.reason_code if e.reason_code and e.reason_code != '-' else ''),
        ('duration_sec', lambda e: e.duration_sec),
        ('frame_count', lambda e: e.frame_count),
        ('final_decided_at', lambda e: e.final_decided_at.isoformat() if e.final_decided_at else ''),
        ('updated_at', lambda e: e.updated_at.isoformat() if e.updated_at else ''),
    ]

    ANNOTATION_EXPORT_FIELDS = [
        'annotation_completed',
        'annotation_status',
        'training_default_included',
        'annotation_task_id',
        'annotation_revision_id',
        'annotation_revision_no',
        'annotation_revision_hash',
        'annotation_schema_id',
        'annotation_schema_version',
        'annotation_schema_hash',
        'task_outcome',
        'annotation_payload_json',
    ]

    @classmethod
    def _qualified_episode_query(cls, db: Session, task_type_id: str, batch_ids: list[str] | None = None):
        query = db.query(Episode).options(joinedload(Episode.batch)).join(
            Batch, Episode.batch_id == Batch.id
        ).join(
            ListRecord, Batch.list_id == ListRecord.id
        ).filter(
            Batch.task_type_id == task_type_id,
            Batch.is_active == True,
            ListRecord.is_active == True,
            Batch.list_id.is_not(None),
            Episode.is_active == True,
            Episode.final_dataset_status == 'QUALIFIED',
        )
        if batch_ids:
            query = query.filter(Episode.batch_id.in_(batch_ids))
        return query.order_by(Episode.id)

    @classmethod
    def _annotation_lookup(
        cls,
        db: Session,
        task_type_id: str,
        episode_ids: list[str],
    ) -> dict[str, tuple[AnnotationTask, AnnotationRevision | None]]:
        if not episode_ids:
            return {}
        tasks = db.query(AnnotationTask).options(
            joinedload(AnnotationTask.revisions),
        ).filter(
            AnnotationTask.episode_id.in_(episode_ids),
            AnnotationTask.task_type_id == task_type_id,
        ).all()
        result: dict[str, tuple[AnnotationTask, AnnotationRevision | None]] = {}
        for task in tasks:
            revision = None
            if task.work_status == 'completed' and task.current_revision_no > 0:
                revision = next(
                    (item for item in task.revisions if item.revision_no == task.current_revision_no),
                    None,
                )
            result[task.episode_id] = (task, revision)
        return result

    @staticmethod
    def _annotation_status(task: AnnotationTask | None, revision: AnnotationRevision | None) -> str:
        if task is None:
            return 'not_created'
        if task.work_status == 'invalidated':
            return 'invalidated'
        if task.work_status == 'completed' and revision is not None:
            return 'completed'
        if task.work_status == 'completed' and revision is None:
            return 'revision_missing'
        if task.work_status == 'in_progress':
            return 'in_progress'
        if task.work_status == 'assigned':
            return 'assigned'
        return task.work_status or 'pending'

    @classmethod
    def _serialize_row(
        cls,
        episode: Episode,
        task: AnnotationTask | None,
        revision: AnnotationRevision | None,
    ) -> dict:
        row = {field: fn(episode) for field, fn in cls.EXPORT_FIELDS}
        annotation_status = cls._annotation_status(task, revision)
        annotation_completed = annotation_status == 'completed'
        task_outcome = None
        if revision and isinstance(revision.annotation_payload, dict):
            task_outcome = revision.annotation_payload.get('taskOutcome')
        training_default_included = bool(
            annotation_completed and task_outcome and task_outcome != 'uncertain'
        )

        row.update({
            'annotation_completed': annotation_completed,
            'annotation_status': annotation_status,
            'training_default_included': training_default_included,
            'annotation_task_id': task.id if task else '',
            'annotation_revision_id': revision.id if revision else '',
            'annotation_revision_no': revision.revision_no if revision else '',
            'annotation_revision_hash': revision.content_hash if revision else '',
            'annotation_schema_id': task.sub_goal_schema_id if task and revision else '',
            'annotation_schema_version': task.sub_goal_schema_version if task and revision else '',
            'annotation_schema_hash': task.sub_goal_schema_content_hash if task and revision else '',
            'task_outcome': task_outcome or '',
            'annotation_payload_json': json.dumps(
                revision.annotation_payload or {},
                ensure_ascii=False,
                sort_keys=True,
                separators=(',', ':'),
            ) if revision else '',
            'annotationCompleted': annotation_completed,
            'annotationStatus': annotation_status,
            'trainingDefaultIncluded': training_default_included,
            'annotationTaskId': task.id if task else None,
            'annotationRevision': {
                'id': revision.id,
                'revisionNo': revision.revision_no,
                'contentHash': revision.content_hash,
            } if revision else None,
            'annotationSchema': {
                'id': task.sub_goal_schema_id,
                'versionNo': task.sub_goal_schema_version,
                'contentHash': task.sub_goal_schema_content_hash,
            } if task and revision else None,
            'annotation': revision.annotation_payload if revision else None,
            'taskOutcome': task_outcome,
        })
        return row

    @classmethod
    @classmethod
    def _schema_snapshots(cls, db: Session, serialized: list[dict]) -> dict[str, dict]:
        schema_ids = sorted({
            item['annotation_schema_id']
            for item in serialized
            if item.get('annotation_schema_id')
        })
        if not schema_ids:
            return {}
        schemas = db.query(SubGoalSchema).options(
            joinedload(SubGoalSchema.definitions)
        ).filter(SubGoalSchema.id.in_(schema_ids)).all()
        result: dict[str, dict] = {}
        for schema in schemas:
            definitions = sorted(schema.definitions, key=lambda item: item.sequence_no)
            payload = {
                'id': schema.id,
                'taskTypeId': schema.task_type_id,
                'versionNo': schema.version_no,
                'status': schema.status,
                'contentHash': schema.content_hash,
                'definitions': [
                    {
                        'id': item.id,
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
                ],
            }
            result[schema.content_hash] = payload
        return result

    @classmethod
    def _build_jsonl_package(
        cls,
        *,
        task_type_id: str,
        serialized: list[dict],
        filters: dict,
        schemas: dict[str, dict],
    ) -> bytes:
        episodes_jsonl = '\n'.join(
            json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            for item in serialized
        )
        if episodes_jsonl:
            episodes_jsonl += '\n'
        schemas_body = json.dumps(schemas, ensure_ascii=False, indent=2, sort_keys=True)
        manifest = {
            'exportType': 'qualified_dataset',
            'taskTypeId': task_type_id,
            'format': 'jsonl_package',
            'qualificationGate': filters.get('qualificationGate') or [],
            'batchIds': filters.get('batchIds') or [],
            'episodeCount': len(serialized),
            'annotationCompletedCount': filters.get('annotationCompletedCount') or 0,
            'trainingDefaultIncludedCount': filters.get('trainingDefaultIncludedCount') or 0,
            'trainingDefaultPolicy': {
                'includeCompletedNormally': True,
                'includeCompletedWithRetry': True,
                'includePartiallyCompleted': True,
                'includeFailed': True,
                'includeUncertain': False,
            },
            'schemaHashes': sorted(schemas.keys()),
            'createdAt': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        episodes_hash = hashlib.sha256(episodes_jsonl.encode('utf-8')).hexdigest()
        schemas_hash = hashlib.sha256(schemas_body.encode('utf-8')).hexdigest()
        manifest['episodesSha256'] = episodes_hash
        manifest['schemasSha256'] = schemas_hash
        manifest_body = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode='w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json', manifest_body)
            archive.writestr('episodes.jsonl', episodes_jsonl)
            archive.writestr('schemas.json', schemas_body)
        return buffer.getvalue()

    @classmethod
    def prepare_export(
        cls,
        db: Session,
        task_type_id: str,
        fmt: str = 'csv',
        batch_ids: list[str] | None = None,
    ) -> tuple[bytes, str, int, dict, list[dict]]:
        if fmt not in {'csv', 'json', 'jsonl'}:
            raise ValueError('仅支持 csv、json 或 jsonl 导出格式')

        episodes = cls._qualified_episode_query(db, task_type_id, batch_ids=batch_ids).all()
        annotation_map = cls._annotation_lookup(db, task_type_id, [item.id for item in episodes])
        serialized = []
        for episode in episodes:
            task, revision = annotation_map.get(episode.id, (None, None))
            serialized.append(cls._serialize_row(episode, task, revision))

        completed_count = sum(1 for item in serialized if item['annotation_completed'])
        default_training_count = sum(1 for item in serialized if item['training_default_included'])
        filters = {
            'exportType': 'qualified_dataset',
            'qualificationGate': [
                "episode.final_dataset_status = 'QUALIFIED'",
                'active_list_active_batch_indexed_episodes',
            ],
            'taskTypeId': task_type_id,
            'batchIds': sorted(batch_ids) if batch_ids else [],
            'episodeCount': len(serialized),
            'annotationCompletedCount': completed_count,
            'trainingDefaultIncludedCount': default_training_count,
            'annotationRevisionSnapshots': [
                {
                    'episode_id': item['episode_id'],
                    'annotation_completed': item['annotation_completed'],
                    'annotation_status': item['annotation_status'],
                    'training_default_included': item['training_default_included'],
                    'annotation_task_id': item['annotation_task_id'] or None,
                    'annotation_revision_id': item['annotation_revision_id'] or None,
                    'annotation_revision_no': item['annotation_revision_no'] or None,
                    'annotation_revision_hash': item['annotation_revision_hash'] or None,
                    'annotation_schema_id': item['annotation_schema_id'] or None,
                    'annotation_schema_version': item['annotation_schema_version'] or None,
                    'annotation_schema_hash': item['annotation_schema_hash'] or None,
                    'task_outcome': item['task_outcome'] or None,
                }
                for item in serialized
            ],
        }

        if fmt == 'json':
            content = json.dumps(serialized, ensure_ascii=False, indent=2).encode('utf-8')
            return content, 'application/json', len(serialized), filters, serialized

        if fmt == 'jsonl':
            schemas = cls._schema_snapshots(db, serialized)
            content = cls._build_jsonl_package(
                task_type_id=task_type_id,
                serialized=serialized,
                filters=filters,
                schemas=schemas,
            )
            filters['packageFiles'] = ['manifest.json', 'episodes.jsonl', 'schemas.json']
            filters['packageSha256'] = hashlib.sha256(content).hexdigest()
            return content, 'application/zip', len(serialized), filters, serialized

        output = io.StringIO()
        fields = [field for field, _ in cls.EXPORT_FIELDS] + cls.ANNOTATION_EXPORT_FIELDS
        writer = csv.writer(output)
        writer.writerow(fields)
        for item in serialized:
            writer.writerow([item[field] for field in fields])
        content = output.getvalue().encode('utf-8-sig')
        return content, 'text/csv', len(serialized), filters, serialized

    @classmethod
    def export_episodes(
        cls,
        db: Session,
        task_type_id: str,
        fmt: str = 'csv',
        batch_ids: list[str] | None = None,
    ) -> tuple[bytes, str, int]:
        content, mime_type, count, _, _ = cls.prepare_export(db, task_type_id, fmt, batch_ids=batch_ids)
        return content, mime_type, count

    @classmethod
    def record_export(
        cls,
        db: Session,
        task_type_id: str,
        fmt: str,
        episode_count: int,
        created_by: str = '',
        filters: dict | None = None,
        rows: list[dict] | None = None,
    ) -> DatasetExportJob:
        payload = filters or {}
        snapshots = payload.get('annotationRevisionSnapshots') or []
        job = DatasetExportJob(
            task_type_id=task_type_id,
            export_type=str(payload.get('exportType') or 'qualified_dataset'),
            export_format=fmt,
            episode_count=episode_count,
            annotation_completed_count=int(payload.get('annotationCompletedCount') or 0),
            training_default_included_count=int(payload.get('trainingDefaultIncludedCount') or 0),
            filters_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            created_by=created_by or 'system',
        )
        db.add(job)
        db.flush()

        row_by_episode = {item.get('episode_id'): item for item in (rows or [])}
        for snapshot in snapshots:
            episode_id = snapshot.get('episode_id')
            episode_snapshot = row_by_episode.get(episode_id) or {
                'episode_id': episode_id,
                'annotation_completed': snapshot.get('annotation_completed'),
                'annotation_status': snapshot.get('annotation_status'),
                'training_default_included': snapshot.get('training_default_included'),
            }
            db.add(DatasetExportItem(
                export_job_id=job.id,
                episode_id=str(episode_id or ''),
                inclusion_status='included',
                episode_snapshot_json=json.dumps(episode_snapshot, ensure_ascii=False, sort_keys=True),
                annotation_completed=bool(snapshot.get('annotation_completed')),
                annotation_status=str(snapshot.get('annotation_status') or 'not_created'),
                training_default_included=bool(snapshot.get('training_default_included')),
                annotation_task_id=snapshot.get('annotation_task_id'),
                annotation_revision_id=snapshot.get('annotation_revision_id'),
                revision_no=snapshot.get('annotation_revision_no'),
                content_hash=snapshot.get('annotation_revision_hash'),
                schema_id=snapshot.get('annotation_schema_id'),
                schema_version=snapshot.get('annotation_schema_version'),
                schema_content_hash=snapshot.get('annotation_schema_hash'),
                task_outcome=snapshot.get('task_outcome'),
            ))

        ts = int(datetime.now(timezone.utc).timestamp() * 1000)
        db.add(AuditEvent(
            id=f'audit_export_{job.id}_{ts}',
            operator=created_by or 'system',
            action='导出数据集',
            target=task_type_id,
            detail=f'{fmt.upper()} 导出 {episode_count} 条 QUALIFIED episode',
            time=datetime.now(timezone.utc),
            event_type='business_action',
            severity='info',
            operator_id=created_by or None,
        ))

        db.commit()
        db.refresh(job)
        return job

    @classmethod
    def export_history(cls, db: Session, task_type_id: str | None = None) -> list[dict]:
        query = db.query(DatasetExportJob).order_by(DatasetExportJob.created_at.desc())
        if task_type_id:
            query = query.filter(DatasetExportJob.task_type_id == task_type_id)
        jobs = query.limit(50).all()
        return [
            {
                'id': j.id,
                'taskTypeId': j.task_type_id,
                'exportFormat': j.export_format,
                'episodeCount': j.episode_count,
                'filters': json.loads(j.filters_json or '{}'),
                'createdBy': j.created_by,
                'createdAt': j.created_at.isoformat() if j.created_at else None,
            }
            for j in jobs
        ]
