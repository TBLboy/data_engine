"""Dataset summary and export services."""

import csv
import io
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import (
    AnnotationRevision,
    AnnotationTask,
    AuditEvent,
    Batch,
    DatasetExportJob,
    Episode,
    ListRecord,
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
        completed_annotation_ids = set()
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

        source_counts = {}
        for e in episodes:
            src = e.final_decision_source
            source_counts[src] = source_counts.get(src, 0) + 1

        return {
            'taskId': task_type.id,
            'taskName': task_type.name,
            'qualifiedEpisodeCount': len(qualified),
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
            'annotationCompletedEpisodeCount': len(completed_annotation_ids),
            'annotationPendingEpisodeCount': len(qualified_ids) - len(completed_annotation_ids),
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
    """Export only QC-qualified episodes with an immutable completed annotation revision."""

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
        'annotation_task_id',
        'annotation_revision_id',
        'annotation_revision_no',
        'annotation_revision_hash',
        'annotation_schema_id',
        'annotation_schema_version',
        'annotation_schema_hash',
        'annotation_payload_json',
    ]

    @classmethod
    def _get_export_rows(cls, db: Session, task_type_id: str, batch_ids: list[str] | None = None):
        query = db.query(Episode, AnnotationTask, AnnotationRevision).join(
            Batch, Episode.batch_id == Batch.id
        ).join(
            ListRecord, Batch.list_id == ListRecord.id
        ).join(
            AnnotationTask, AnnotationTask.episode_id == Episode.id
        ).join(
            AnnotationRevision,
            (AnnotationRevision.annotation_task_id == AnnotationTask.id)
            & (AnnotationRevision.revision_no == AnnotationTask.current_revision_no),
        ).filter(
            Batch.task_type_id == task_type_id,
            Batch.is_active == True,
            ListRecord.is_active == True,
            Batch.list_id.is_not(None),
            Episode.is_active == True,
            Episode.final_dataset_status == 'QUALIFIED',
            AnnotationTask.task_type_id == task_type_id,
            AnnotationTask.work_status == 'completed',
        )
        if batch_ids:
            query = query.filter(Episode.batch_id.in_(batch_ids))
        rows = query.order_by(Episode.id).all()
        if not rows:
            raise ValueError(
                '没有满足导出门禁的 Episode：必须同时满足 QUALIFIED 且拥有 completed annotation revision'
            )
        return rows

    @staticmethod
    def _annotation_snapshot(task: AnnotationTask, revision: AnnotationRevision) -> dict:
        return {
            'annotationTaskId': task.id,
            'annotationRevisionId': revision.id,
            'annotationRevisionNo': revision.revision_no,
            'annotationRevisionHash': revision.content_hash,
            'annotationSchemaId': task.sub_goal_schema_id,
            'annotationSchemaVersion': task.sub_goal_schema_version,
            'annotationSchemaHash': task.sub_goal_schema_content_hash,
        }

    @classmethod
    def _serialize_row(cls, episode: Episode, task: AnnotationTask, revision: AnnotationRevision) -> dict:
        row = {field: fn(episode) for field, fn in cls.EXPORT_FIELDS}
        snapshot = cls._annotation_snapshot(task, revision)
        row.update({
            'annotation_task_id': snapshot['annotationTaskId'],
            'annotation_revision_id': snapshot['annotationRevisionId'],
            'annotation_revision_no': snapshot['annotationRevisionNo'],
            'annotation_revision_hash': snapshot['annotationRevisionHash'],
            'annotation_schema_id': snapshot['annotationSchemaId'],
            'annotation_schema_version': snapshot['annotationSchemaVersion'],
            'annotation_schema_hash': snapshot['annotationSchemaHash'],
            'annotation_payload_json': json.dumps(
                revision.annotation_payload or {}, ensure_ascii=False, sort_keys=True, separators=(',', ':')
            ),
            'annotation': revision.annotation_payload or {},
            'annotationRevision': {
                'id': snapshot['annotationRevisionId'],
                'revisionNo': snapshot['annotationRevisionNo'],
                'contentHash': snapshot['annotationRevisionHash'],
            },
            'annotationSchema': {
                'id': snapshot['annotationSchemaId'],
                'versionNo': snapshot['annotationSchemaVersion'],
                'contentHash': snapshot['annotationSchemaHash'],
            },
        })
        return row

    @classmethod
    def prepare_export(
        cls,
        db: Session,
        task_type_id: str,
        fmt: str = 'csv',
        batch_ids: list[str] | None = None,
    ) -> tuple[bytes, str, int, dict]:
        if fmt not in {'csv', 'json'}:
            raise ValueError('仅支持 csv 或 json 导出格式')
        rows = cls._get_export_rows(db, task_type_id, batch_ids=batch_ids)
        serialized = [cls._serialize_row(episode, task, revision) for episode, task, revision in rows]
        revision_snapshots = [
            {
                key: item[key]
                for key in (
                    'episode_id',
                    'annotation_task_id',
                    'annotation_revision_id',
                    'annotation_revision_no',
                    'annotation_revision_hash',
                    'annotation_schema_id',
                    'annotation_schema_version',
                    'annotation_schema_hash',
                )
            }
            for item in serialized
        ]
        filters = {
            'qualificationGate': [
                "episode.final_dataset_status = 'QUALIFIED'",
                "annotation_tasks.work_status = 'completed'",
                'annotation_revisions.revision_no = annotation_tasks.current_revision_no',
                'active_list_active_batch_indexed_episodes',
            ],
            'taskTypeId': task_type_id,
            'batchIds': sorted(batch_ids) if batch_ids else [],
            'episodeCount': len(serialized),
            'annotationRevisionSnapshots': revision_snapshots,
        }

        if fmt == 'json':
            content = json.dumps(serialized, ensure_ascii=False, indent=2).encode('utf-8')
            return content, 'application/json', len(serialized), filters

        output = io.StringIO()
        fields = [field for field, _ in cls.EXPORT_FIELDS] + cls.ANNOTATION_EXPORT_FIELDS
        writer = csv.writer(output)
        writer.writerow(fields)
        for item in serialized:
            writer.writerow([item[field] for field in fields])
        content = output.getvalue().encode('utf-8-sig')
        return content, 'text/csv', len(serialized), filters

    @classmethod
    def export_episodes(cls, db: Session, task_type_id: str, fmt: str = 'csv', batch_ids: list[str] | None = None) -> tuple[bytes, str, int]:
        content, mime_type, count, _ = cls.prepare_export(db, task_type_id, fmt, batch_ids=batch_ids)
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
    ) -> DatasetExportJob:
        job = DatasetExportJob(
            task_type_id=task_type_id,
            export_format=fmt,
            episode_count=episode_count,
            filters_json=json.dumps(filters or {}, ensure_ascii=False, sort_keys=True),
            created_by=created_by or 'system',
        )
        db.add(job)
        db.flush()

        ts = int(datetime.now(timezone.utc).timestamp() * 1000)
        db.add(AuditEvent(
            id=f'audit_export_{job.id}_{ts}',
            operator=created_by or 'system',
            action='导出数据集',
            target=task_type_id,
            detail=f'{fmt.upper()} 导出 {episode_count} 条 episode',
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
