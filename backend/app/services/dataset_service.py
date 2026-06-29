"""Dataset summary and export services."""

import csv
import io
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Batch, Episode, TaskType


class DatasetSummaryService:
    """Task-level dataset statistics for downstream consumers."""

    @staticmethod
    def task_summary(db: Session, task_type_id: str) -> dict | None:
        task_type = db.query(TaskType).filter(TaskType.id == task_type_id, TaskType.is_active == True).first()
        if not task_type:
            return None

        batches = db.query(Batch).filter(Batch.task_type_id == task_type_id, Batch.is_active == True).all()
        episodes = db.query(Episode).filter(
            Episode.batch.has((Batch.task_type_id == task_type_id) & (Batch.is_active == True))
        ).all()

        qualified = [e for e in episodes if e.final_dataset_status == 'QUALIFIED']
        total = len(episodes)
        batch_count = len(batches)
        accepted = sum(1 for b in batches if b.batch_decision == 'ACCEPTED')
        rejected = sum(1 for b in batches if b.batch_decision == 'REJECTED')
        pending = sum(1 for b in batches if b.batch_decision == 'PENDING')

        # Count by decision source
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
        }

    @staticmethod
    def task_batches(db: Session, task_type_id: str) -> list[dict]:
        batches = db.query(Batch).filter(Batch.task_type_id == task_type_id, Batch.is_active == True).order_by(Batch.imported_at.desc()).all()
        result = []
        for batch in batches:
            available = db.query(Episode).filter(
                Episode.batch_id == batch.id,
                Episode.final_dataset_status == 'QUALIFIED',
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
    """Export qualified episode metadata as CSV or JSON."""

    EXPORT_FIELDS = [
        ('episode_id', lambda e: e.id),
        ('task_name', lambda e: e.task_name),
        ('batch_id', lambda e: e.batch_id),
        ('batch_name', lambda e: e.batch.name if e.batch else ''),
        ('final_dataset_status', lambda e: e.final_dataset_status),
        ('final_decision_source', lambda e: e.final_decision_source),
        ('manual_qc_status', lambda e: e.manual_qc_status),
        ('final_decided_at', lambda e: e.final_decided_at.isoformat() if e.final_decided_at else ''),
        ('duration_sec', lambda e: e.duration_sec),
        ('frame_count', lambda e: e.frame_count),
        ('reason_code', lambda e: e.reason_code),
    ]

    @classmethod
    def export_episodes(cls, db: Session, task_type_id: str, fmt: str = 'csv') -> tuple[bytes, str, int]:
        """Export qualified episodes for a task type.

        Returns (file_content, mime_type, episode_count).
        """
        episodes = db.query(Episode).filter(
            Episode.batch.has((Batch.task_type_id == task_type_id) & (Batch.is_active == True)),
            Episode.final_dataset_status == 'QUALIFIED',
        ).order_by(Episode.id).all()

        if fmt == 'json':
            data = []
            for e in episodes:
                row = {field: fn(e) for field, fn in cls.EXPORT_FIELDS}
                data.append(row)
            content = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
            return content, 'application/json', len(episodes)
        else:  # csv
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([field for field, _ in cls.EXPORT_FIELDS])
            for e in episodes:
                writer.writerow([fn(e) for _, fn in cls.EXPORT_FIELDS])
            content = output.getvalue().encode('utf-8-sig')
            return content, 'text/csv', len(episodes)
