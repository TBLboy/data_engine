from __future__ import annotations

import io
import sys
import tempfile
import unittest
import json
import zipfile
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from app.core.db import Base
from app.models import Batch, Episode, ListRecord, ReviewerAnnotationRollup, TaskAnnotationRollup, TaskType, User
from app.services.annotation import (
    acquire_lock,
    annotation_statistics,
    annotation_eligibility,
    complete_task,
    create_schema,
    ensure_task_for_episode,
    publish_schema,
    recompute_annotation_rollup,
    reconcile_annotation_eligibility,
    save_draft,
)
from app.services.dataset_service import DatasetExportService
from app.services.batch_adjudication import adjudicate_batch


class AnnotationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.engine = create_engine(f'sqlite:///{Path(self.tmpdir.name) / "annotations.db"}', future=True)
        Base.metadata.create_all(self.engine)
        # Match the production session configuration: lifecycle services must
        # flush their own prerequisite mutations before reading projections.
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self.seed_data()

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmpdir.cleanup()

    def seed_data(self) -> None:
        with self.SessionLocal() as db:
            now = datetime(2026, 7, 18, 10, 0, 0)
            admin = User(
                id='user_admin', username='admin', name='Admin', role='admin', avatar='A',
                password_hash='unused', is_active=1,
            )
            reviewer = User(
                id='user_reviewer', username='reviewer', name='Reviewer', role='reviewer', avatar='R',
                password_hash='unused', is_active=1,
            )
            task_type = TaskType(
                id='task_type_pick', name='Pick', description='Pick', arm_mode='both_arms', is_active=True,
            )
            scan_id = 'scan_test'
            from app.models import ScanJob
            db.add(ScanJob(
                id=scan_id, bucket='robot', scope='full', status='done', total_prefixes=1,
                confirmed_lists=1, total_episodes=2, new_episodes=2, triggered_by='test',
                error_detail='', started_at=now, finished_at=now,
            ))
            db.add_all([admin, reviewer, task_type])
            db.add(ListRecord(
                id='list_test', bucket='robot', list_prefix='lists/test', confirmed_scan_id=scan_id,
                last_active_scan_id=scan_id, has_raw=True, has_processed=True, total_raw_episodes=2,
                total_processed_episodes=2, candidate_task_type='Pick', candidate_source='test',
                final_task_type_id=None, is_active=True, created_at=now, updated_at=now,
            ))
            db.add(Batch(
                id='batch_test', list_id='list_test', task_type_id=task_type.id, name='Test batch',
                imported_at=now, episode_count=2, sampled_episode_count=2, completed_sample_count=2,
                dispatch_mode='sampled', sampling_ratio=100, active_dispatch_generation=1,
                qc_status='done', pass_rate=1, top_reason='-', is_active=True,
                manual_pass_count=2, manual_fail_count=0, batch_decision='APPROVED',
                batch_decision_reason='', reject_threshold=0.1, failure_rate_denominator='SAMPLED_COUNT',
                decision_policy_version='test',
            ))
            db.add_all([
                Episode(
                    id='episode_qualified', batch_id='batch_test', task_name='Pick', duration_sec=2,
                    frame_count=20, qc_status='reviewed', qc_result='pass', reviewer='reviewer',
                    reason_code='-', updated_at=now, in_candidate_pool=1, sampled_for_qc=1,
                    manual_qc_status='MANUAL_PASS', final_dataset_status='QUALIFIED',
                    final_decision_source='MANUAL_QC', final_decision_reason='', is_exportable=True,
                    final_decision_policy_version='test',
                ),
                Episode(
                    id='episode_unqualified', batch_id='batch_test', task_name='Pick', duration_sec=2,
                    frame_count=20, qc_status='reviewed', qc_result='fail', reviewer='reviewer',
                    reason_code='-', updated_at=now, in_candidate_pool=1, sampled_for_qc=1,
                    manual_qc_status='MANUAL_FAIL', final_dataset_status='UNQUALIFIED',
                    final_decision_source='MANUAL_QC', final_decision_reason='', is_exportable=False,
                    final_decision_policy_version='test',
                ),
            ])
            db.commit()

    def create_published_schema(self, db, admin):
        schema = create_schema(db, task_type_id='task_type_pick', definitions=[{
            'sequenceNo': 1,
            'code': 'pick_object',
            'nameEn': 'Pick object',
            'nameZh': '抓取物体',
            'isRequired': True,
            'maxOccurrences': 2,
        }], user=admin)
        publish_schema(db, schema, admin)
        db.commit()
        return schema

    def test_schema_publish_retires_previous_version(self) -> None:
        with self.SessionLocal() as db:
            admin = db.get(User, 'user_admin')
            first = self.create_published_schema(db, admin)
            second = create_schema(db, task_type_id='task_type_pick', definitions=[{
                'sequenceNo': 1, 'code': 'place_object', 'nameEn': 'Place object',
            }], user=admin)
            publish_schema(db, second, admin)
            db.commit()
            db.refresh(first)
            self.assertEqual(first.status, 'retired')
            self.assertEqual(second.status, 'published')

    def test_qualified_task_is_idempotent_and_scope_is_enforced(self) -> None:
        with self.SessionLocal() as db:
            admin = db.get(User, 'user_admin')
            self.create_published_schema(db, admin)
            episode = db.get(Episode, 'episode_qualified')
            task = ensure_task_for_episode(db, episode)
            same_task = ensure_task_for_episode(db, episode)
            db.commit()
            self.assertEqual(task.id, same_task.id)
            with self.assertRaises(ValueError):
                ensure_task_for_episode(db, db.get(Episode, 'episode_unqualified'))

    def test_lock_cas_validation_and_immutable_revision(self) -> None:
        with self.SessionLocal() as db:
            admin = db.get(User, 'user_admin')
            reviewer = db.get(User, 'user_reviewer')
            self.create_published_schema(db, admin)
            task = ensure_task_for_episode(db, db.get(Episode, 'episode_qualified'))
            task.assigned_to = reviewer.id
            acquire_lock(db, task, reviewer)
            db.commit()
            row_version = task.row_version
            save_draft(db, task, reviewer, {
                'rowVersion': row_version,
                'canonicalInstructionEn': 'Pick the object',
                'taskOutcome': 'completed_normally',
                'occurrences': [{
                    'definitionId': task.schema.definitions[0].id,
                    'occurrenceNo': 1,
                    'status': 'observed',
                    'startStep': 1,
                    'endStepExclusive': 5,
                    'representativeStep': 3,
                }],
            })
            with self.assertRaises(ValueError):
                save_draft(db, task, reviewer, {
                    'rowVersion': row_version,
                    'canonicalInstructionEn': 'stale',
                    'taskOutcome': 'completed_normally',
                    'occurrences': [],
                })
            revision = complete_task(db, task, reviewer)
            db.commit()
            self.assertEqual(revision.revision_no, 1)
            self.assertEqual(task.work_status, 'completed')
            self.assertIsNone(task.lock_owner)
            self.assertEqual(len(task.revisions), 1)
            stats = annotation_statistics(db, task_type_id='task_type_pick')
            self.assertEqual(stats['byReviewer'], [])

    def test_statistics_reports_statuses_and_completion_rate(self) -> None:
        with self.SessionLocal() as db:
            admin = db.get(User, 'user_admin')
            reviewer = db.get(User, 'user_reviewer')
            self.create_published_schema(db, admin)
            task = ensure_task_for_episode(db, db.get(Episode, 'episode_qualified'))
            task.assigned_to = reviewer.id
            acquire_lock(db, task, reviewer)
            db.commit()
            stats = annotation_statistics(db, task_type_id='task_type_pick')
            self.assertEqual(stats['total'], 1)
            self.assertEqual(stats['byStatus'], {'in_progress': 1})
            self.assertEqual(stats['byReviewer'], [{'reviewerId': reviewer.id, 'count': 1}])
            self.assertEqual(stats['completionRate'], 0)
            self.assertEqual(task.task_type_id, 'task_type_pick')
            rollup = db.get(TaskAnnotationRollup, 'task_type_pick')
            self.assertEqual(rollup.total_count, 1)
            self.assertEqual(rollup.in_progress_count, 1)
            reviewer_rollup = db.get(ReviewerAnnotationRollup, ('task_type_pick', reviewer.id))
            self.assertEqual(reviewer_rollup.task_count, 1)
            eligibility = annotation_eligibility(db, task_type_id='task_type_pick')
            self.assertEqual(eligibility, {'eligibleCount': 1, 'taskCount': 1, 'unannotatedCount': 0})

    def test_completion_coverage_excludes_invalidated_completed_history(self) -> None:
        with self.SessionLocal() as db:
            admin = db.get(User, 'user_admin')
            self.create_published_schema(db, admin)
            episode = db.get(Episode, 'episode_qualified')
            task = ensure_task_for_episode(db, episode)
            task.work_status = 'completed'
            recompute_annotation_rollup(db, task.task_type_id)
            db.commit()

            active_stats = annotation_statistics(db, task_type_id='task_type_pick')
            self.assertEqual(active_stats['completed'], 1)
            self.assertEqual(active_stats['activeCompletedCount'], 1)
            self.assertEqual(active_stats['completionRate'], 1)

            episode.final_dataset_status = 'UNQUALIFIED'
            reconcile_annotation_eligibility(db, episode_ids={episode.id})
            db.commit()
            invalidated_stats = annotation_statistics(db, task_type_id='task_type_pick')
            self.assertEqual(invalidated_stats['completed'], 0)
            self.assertEqual(invalidated_stats['activeCompletedCount'], 0)
            self.assertEqual(invalidated_stats['completionRate'], 0)

    def test_reconcile_invalidates_and_restores_existing_task(self) -> None:
        with self.SessionLocal() as db:
            admin = db.get(User, 'user_admin')
            reviewer = db.get(User, 'user_reviewer')
            self.create_published_schema(db, admin)
            episode = db.get(Episode, 'episode_qualified')
            task = ensure_task_for_episode(db, episode)
            task.assigned_to = reviewer.id
            task.public_claim_enabled = True
            acquire_lock(db, task, reviewer)
            initial_row_version = task.row_version
            db.commit()

            episode.final_dataset_status = 'UNQUALIFIED'
            changes = reconcile_annotation_eligibility(
                db,
                episode_ids={episode.id},
                reason='batch_rejected',
            )
            db.commit()
            self.assertEqual(changes, {'invalidated': 1, 'restored': 0})
            self.assertEqual(task.work_status, 'invalidated')
            self.assertEqual(task.status_before_invalidation, 'in_progress')
            self.assertEqual(task.invalidation_reason, 'batch_rejected')
            self.assertFalse(task.public_claim_enabled)
            self.assertIsNone(task.lock_owner)
            self.assertGreater(task.row_version, initial_row_version)
            invalidated_stats = annotation_statistics(db, task_type_id='task_type_pick')
            self.assertEqual(invalidated_stats['total'], 1)
            self.assertEqual(invalidated_stats['activeTaskCount'], 0)
            self.assertEqual(invalidated_stats['byStatus'], {'invalidated': 1})
            self.assertEqual(invalidated_stats['completionRate'], 0)
            self.assertEqual(
                annotation_eligibility(db, task_type_id='task_type_pick'),
                {'eligibleCount': 0, 'taskCount': 0, 'unannotatedCount': 0},
            )

            episode.final_dataset_status = 'QUALIFIED'
            changes = reconcile_annotation_eligibility(
                db,
                episode_ids={episode.id},
                reason='batch_reaccepted',
            )
            db.commit()
            self.assertEqual(changes, {'invalidated': 0, 'restored': 1})
            self.assertEqual(task.work_status, 'assigned')
            self.assertEqual(task.assigned_to, reviewer.id)
            self.assertIsNone(task.lock_owner)
            self.assertIsNone(task.status_before_invalidation)
            self.assertIsNone(task.invalidation_reason)
            self.assertIsNone(task.invalidated_at)

    def test_reconcile_empty_episode_scope_does_not_touch_tasks(self) -> None:
        with self.SessionLocal() as db:
            admin = db.get(User, 'user_admin')
            self.create_published_schema(db, admin)
            task = ensure_task_for_episode(db, db.get(Episode, 'episode_qualified'))
            db.commit()
            changes = reconcile_annotation_eligibility(db, episode_ids=set())
            self.assertEqual(changes, {'invalidated': 0, 'restored': 0})
            self.assertEqual(task.work_status, 'pending')

    def test_batch_adjudication_reconciles_annotation_eligibility(self) -> None:
        with self.SessionLocal() as db:
            admin = db.get(User, 'user_admin')
            self.create_published_schema(db, admin)
            qualified = db.get(Episode, 'episode_qualified')
            unqualified = db.get(Episode, 'episode_unqualified')
            task = ensure_task_for_episode(db, qualified)
            db.commit()

            unqualified.manual_qc_status = 'MANUAL_FAIL'
            adjudicate_batch(db, 'batch_test', actor=admin.id)
            self.assertEqual(qualified.final_dataset_status, 'UNQUALIFIED')
            self.assertEqual(task.work_status, 'invalidated')

            unqualified.manual_qc_status = 'MANUAL_PASS'
            adjudicate_batch(db, 'batch_test', actor=admin.id)
            self.assertEqual(qualified.final_dataset_status, 'QUALIFIED')
            self.assertEqual(task.work_status, 'pending')

    def test_dataset_export_includes_qualified_without_annotation(self) -> None:
        with self.SessionLocal() as db:
            content, mime, count, filters, serialized = DatasetExportService.prepare_export(
                db, 'task_type_pick', 'json'
            )
            rows = json.loads(content)
            self.assertEqual(mime, 'application/json')
            self.assertEqual(count, 1)
            self.assertEqual(rows[0]['episode_id'], 'episode_qualified')
            self.assertFalse(rows[0]['annotationCompleted'])
            self.assertEqual(rows[0]['annotationStatus'], 'not_created')
            self.assertFalse(rows[0]['trainingDefaultIncluded'])
            self.assertIsNone(rows[0]['annotation'])
            self.assertEqual(filters['exportType'], 'qualified_dataset')
            self.assertEqual(filters['qualificationGate'][0], "episode.final_dataset_status = 'QUALIFIED'")
            self.assertEqual(filters['annotationCompletedCount'], 0)

            job = DatasetExportService.record_export(
                db, 'task_type_pick', 'json', count, created_by='Admin', filters=filters, rows=serialized
            )
            from app.models import DatasetExportItem
            items = db.query(DatasetExportItem).filter(DatasetExportItem.export_job_id == job.id).all()
            self.assertEqual(len(items), 1)
            self.assertFalse(items[0].annotation_completed)
            self.assertEqual(items[0].annotation_status, 'not_created')

    def test_dataset_export_attaches_completed_annotation_revision(self) -> None:
        with self.SessionLocal() as db:
            admin = db.get(User, 'user_admin')
            reviewer = db.get(User, 'user_reviewer')
            schema = self.create_published_schema(db, admin)
            task = ensure_task_for_episode(db, db.get(Episode, 'episode_qualified'))
            task.assigned_to = reviewer.id
            acquire_lock(db, task, reviewer)
            save_draft(db, task, reviewer, {
                'rowVersion': task.row_version,
                'canonicalInstructionEn': 'Pick the object',
                'taskOutcome': 'completed_normally',
                'occurrences': [{
                    'definitionId': schema.definitions[0].id,
                    'occurrenceNo': 1,
                    'status': 'observed',
                    'startStep': 1,
                    'endStepExclusive': 5,
                    'representativeStep': 3,
                }],
            })
            revision = complete_task(db, task, reviewer)
            db.commit()

            content, mime, count, filters, serialized = DatasetExportService.prepare_export(
                db, 'task_type_pick', 'json'
            )
            rows = json.loads(content)
            self.assertEqual(mime, 'application/json')
            self.assertEqual(count, 1)
            self.assertTrue(rows[0]['annotationCompleted'])
            self.assertEqual(rows[0]['annotationStatus'], 'completed')
            self.assertTrue(rows[0]['trainingDefaultIncluded'])
            self.assertEqual(rows[0]['annotationRevision']['id'], revision.id)
            self.assertEqual(rows[0]['annotationRevision']['contentHash'], revision.content_hash)
            self.assertEqual(rows[0]['annotationSchema']['id'], task.sub_goal_schema_id)
            self.assertEqual(filters['annotationCompletedCount'], 1)
            self.assertNotIn('annotationRevisionSnapshots', filters)

            job = DatasetExportService.record_export(
                db, 'task_type_pick', 'json', count, created_by='Admin', filters=filters, rows=serialized
            )
            from app.models import DatasetExportItem
            items = db.query(DatasetExportItem).filter(DatasetExportItem.export_job_id == job.id).all()
            self.assertEqual(len(items), 1)
            self.assertTrue(items[0].annotation_completed)
            self.assertEqual(items[0].annotation_revision_id, revision.id)
            self.assertEqual(items[0].content_hash, revision.content_hash)
            history = DatasetExportService.export_history(db, 'task_type_pick')
            self.assertNotIn('annotationRevisionSnapshots', history[0]['filters'])
            export_items = DatasetExportService.export_items(db, job.id)
            self.assertEqual(export_items[0]['annotationRevisionId'], revision.id)

            # Re-edit and complete again; historical export item must stay on revision 1.
            existing_instance_id = task.annotation.sub_goal_instances[0].id
            acquire_lock(db, task, reviewer)
            self.assertEqual(task.work_status, 'in_progress')
            save_draft(db, task, reviewer, {
                'rowVersion': task.row_version,
                'canonicalInstructionEn': 'Pick the object carefully',
                'taskOutcome': 'completed_with_retry',
                'occurrences': [{
                    'id': existing_instance_id,
                    'definitionId': schema.definitions[0].id,
                    'occurrenceNo': 1,
                    'status': 'observed',
                    'startStep': 1,
                    'endStepExclusive': 6,
                    'representativeStep': 3,
                }],
            })
            revision2 = complete_task(db, task, reviewer)
            db.commit()
            self.assertEqual(revision2.revision_no, 2)
            db.refresh(items[0])
            self.assertEqual(items[0].annotation_revision_id, revision.id)
            self.assertEqual(items[0].revision_no, 1)
            self.assertEqual(items[0].content_hash, revision.content_hash)

    def test_dataset_export_jsonl_package_contains_manifest_episodes_and_schemas(self) -> None:
        with self.SessionLocal() as db:
            admin = db.get(User, 'user_admin')
            reviewer = db.get(User, 'user_reviewer')
            schema = self.create_published_schema(db, admin)
            task = ensure_task_for_episode(db, db.get(Episode, 'episode_qualified'))
            task.assigned_to = reviewer.id
            acquire_lock(db, task, reviewer)
            save_draft(db, task, reviewer, {
                'rowVersion': task.row_version,
                'canonicalInstructionEn': 'Pick the object',
                'taskOutcome': 'completed_normally',
                'occurrences': [{
                    'definitionId': schema.definitions[0].id,
                    'occurrenceNo': 1,
                    'status': 'observed',
                    'startStep': 1,
                    'endStepExclusive': 5,
                    'representativeStep': 3,
                }],
            })
            complete_task(db, task, reviewer)
            db.commit()

            content, mime, count, filters, _ = DatasetExportService.prepare_export(
                db, 'task_type_pick', 'jsonl'
            )
            self.assertEqual(mime, 'application/zip')
            self.assertEqual(count, 1)
            self.assertEqual(filters['packageFiles'], ['manifest.json', 'episodes.jsonl', 'schemas.json'])
            self.assertTrue(filters.get('packageSha256'))

            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
                self.assertEqual(names, {'manifest.json', 'episodes.jsonl', 'schemas.json'})
                manifest = json.loads(archive.read('manifest.json'))
                episodes = [
                    json.loads(line)
                    for line in archive.read('episodes.jsonl').decode('utf-8').splitlines()
                    if line.strip()
                ]
                schemas = json.loads(archive.read('schemas.json'))
            self.assertEqual(manifest['exportType'], 'qualified_dataset')
            self.assertEqual(manifest['episodeCount'], 1)
            self.assertEqual(manifest['annotationCompletedCount'], 1)
            self.assertEqual(len(episodes), 1)
            self.assertTrue(episodes[0]['annotationCompleted'])
            self.assertIn(task.sub_goal_schema_content_hash, schemas)

    def test_generation_queue_claim_complete_and_idempotent_enqueue(self) -> None:
        from app.models import AnnotationGenerationJob
        from app.services.annotation_coordinator import (
            discover_eligible_tasks,
            enqueue_initial_job_for_task,
        )
        from app.services.annotation_generation_queue import (
            claim_next_job,
            complete_job,
        )

        with self.SessionLocal() as db:
            admin = db.get(User, 'user_admin')
            self.create_published_schema(db, admin)
            episode = db.get(Episode, 'episode_qualified')
            task = ensure_task_for_episode(db, episode, initial_source='vlm')
            db.flush()
            self.assertEqual(task.work_status, 'pending')
            job1 = enqueue_initial_job_for_task(db, task, request_group_id='g1', requested_by=admin.id)
            self.assertIsNotNone(job1, f'expected initial job for task {task.id} status={task.work_status}')
            job2 = enqueue_initial_job_for_task(db, task, request_group_id='g2', requested_by=admin.id)
            db.commit()
            self.assertIsNotNone(job2)
            self.assertEqual(job1.id, job2.id)
            self.assertEqual(job1.status, 'queued')
            self.assertEqual(
                db.query(AnnotationGenerationJob).filter(
                    AnnotationGenerationJob.annotation_task_id == task.id,
                    AnnotationGenerationJob.job_type == 'initial',
                ).count(),
                1,
            )

            claimed = claim_next_job(db, worker_id='worker-a', lease_seconds=60)
            db.commit()
            self.assertIsNotNone(claimed)
            self.assertEqual(claimed.id, job1.id)
            self.assertEqual(claimed.status, 'running')
            self.assertEqual(claimed.lease_owner, 'worker-a')

            # Global concurrency limit = 1.
            second = claim_next_job(db, worker_id='worker-b', lease_seconds=60)
            self.assertIsNone(second)

            ok = complete_job(db, job_id=claimed.id, worker_id='worker-a')
            db.commit()
            self.assertTrue(ok)
            db.refresh(claimed)
            self.assertEqual(claimed.status, 'succeeded')

            # Discovery must not create a second initial job after success.
            created = discover_eligible_tasks(db, limit=10)
            db.commit()
            self.assertEqual(created, 0)
            self.assertEqual(
                db.query(AnnotationGenerationJob).filter(
                    AnnotationGenerationJob.annotation_task_id == task.id,
                    AnnotationGenerationJob.job_type == 'initial',
                ).count(),
                1,
            )

    def test_generation_job_cancelled_when_task_invalidated(self) -> None:
        from app.services.annotation_coordinator import enqueue_initial_job_for_task
        from app.services.annotation_generation_queue import claim_next_job

        with self.SessionLocal() as db:
            admin = db.get(User, 'user_admin')
            self.create_published_schema(db, admin)
            episode = db.get(Episode, 'episode_qualified')
            task = ensure_task_for_episode(db, episode, initial_source='vlm')
            job = enqueue_initial_job_for_task(db, task, request_group_id='g-cancel')
            self.assertIsNotNone(job)
            db.commit()
            self.assertEqual(job.status, 'queued')

            # Leave active QUALIFIED scope so reconcile invalidates the task.
            episode.final_dataset_status = 'UNQUALIFIED'
            episode.is_exportable = False
            db.flush()
            result = reconcile_annotation_eligibility(
                db,
                episode_ids={task.episode_id},
                reason='test_invalidation',
            )
            db.commit()
            self.assertEqual(result['invalidated'], 1)
            db.refresh(job)
            self.assertEqual(job.status, 'cancelled')

            # Running job should get cancel_requested_at without immediate terminal status.
            task2_ep = Episode(
                id='episode_qualified_2', batch_id='batch_test', task_name='Pick', duration_sec=2,
                frame_count=20, qc_status='reviewed', qc_result='pass', reviewer='reviewer',
                reason_code='-', updated_at=datetime(2026, 7, 18, 10, 0, 0), in_candidate_pool=1,
                sampled_for_qc=1, manual_qc_status='MANUAL_PASS', final_dataset_status='QUALIFIED',
                final_decision_source='MANUAL_QC', final_decision_reason='', is_exportable=True,
                final_decision_policy_version='test',
            )
            db.add(task2_ep)
            db.commit()
            task2 = ensure_task_for_episode(db, task2_ep, initial_source='vlm')
            job2 = enqueue_initial_job_for_task(db, task2, request_group_id='g-running')
            self.assertIsNotNone(job2)
            claimed = claim_next_job(db, worker_id='worker-a', lease_seconds=60)
            db.commit()
            self.assertIsNotNone(claimed)
            self.assertEqual(claimed.id, job2.id)
            self.assertEqual(claimed.status, 'running')
            task2_ep.final_dataset_status = 'UNQUALIFIED'
            task2_ep.is_exportable = False
            db.flush()
            reconcile_annotation_eligibility(db, episode_ids={task2.episode_id}, reason='test_running_cancel')
            db.commit()
            db.refresh(claimed)
            self.assertEqual(claimed.status, 'running')
            self.assertIsNotNone(claimed.cancel_requested_at)


    def test_discovery_night_window_and_daily_limit(self) -> None:
        from types import SimpleNamespace
        from zoneinfo import ZoneInfo

        from app.models import AnnotationGenerationJob
        from app.services.annotation_coordinator import (
            discover_eligible_tasks,
            enqueue_initial_job_for_task,
            is_discovery_window_open,
            remaining_discovery_quota,
        )

        tz = ZoneInfo('Asia/Shanghai')
        settings = SimpleNamespace(
            annotation_discovery_enabled=True,
            annotation_discovery_timezone='Asia/Shanghai',
            annotation_discovery_window_start='00:00',
            annotation_discovery_window_end='06:00',
            annotation_discovery_daily_limit=1,
        )
        night = datetime(2026, 7, 20, 1, 30, tzinfo=tz)
        day = datetime(2026, 7, 20, 17, 30, tzinfo=tz)
        self.assertTrue(is_discovery_window_open(now=night, settings=settings))
        self.assertFalse(is_discovery_window_open(now=day, settings=settings))
        overnight = SimpleNamespace(**{**settings.__dict__, 'annotation_discovery_window_start': '22:00', 'annotation_discovery_window_end': '06:00'})
        self.assertTrue(is_discovery_window_open(now=datetime(2026, 7, 20, 23, 0, tzinfo=tz), settings=overnight))
        self.assertTrue(is_discovery_window_open(now=datetime(2026, 7, 20, 5, 0, tzinfo=tz), settings=overnight))
        self.assertFalse(is_discovery_window_open(now=datetime(2026, 7, 20, 12, 0, tzinfo=tz), settings=overnight))

        with self.SessionLocal() as db:
            admin = db.get(User, 'user_admin')
            self.create_published_schema(db, admin)
            episode = db.get(Episode, 'episode_qualified')
            # Outside window: auto discovery must not enqueue; manual still may.
            created = discover_eligible_tasks(db, limit=10, now=day, settings=settings)
            db.commit()
            self.assertEqual(created, 0)
            task = ensure_task_for_episode(db, episode, initial_source='vlm')
            manual = enqueue_initial_job_for_task(db, task, request_group_id='manual-day', requested_by=admin.id)
            db.commit()
            self.assertIsNotNone(manual)
            self.assertEqual(manual.status, 'queued')
            # Cancel manual so auto path can create under night window.
            manual.status = 'cancelled'
            db.commit()

            # Night window with daily_limit=1: first discover creates, second is blocked by quota.
            settings.annotation_discovery_daily_limit = 1
            created_night = discover_eligible_tasks(db, limit=10, now=night, settings=settings)
            db.commit()
            self.assertEqual(created_night, 1)
            auto_jobs = (
                db.query(AnnotationGenerationJob)
                .filter(AnnotationGenerationJob.request_group_id.like('auto-%'))
                .all()
            )
            self.assertEqual(len(auto_jobs), 1)
            self.assertEqual(remaining_discovery_quota(db, now=night, settings=settings), 0)
            created_again = discover_eligible_tasks(db, limit=10, now=night, settings=settings)
            db.commit()
            self.assertEqual(created_again, 0)

    def test_vlm_uniform_sample_and_occurrence_normalization(self) -> None:
        from app.services.annotation_vlm import (
            normalize_occurrences,
            normalize_task_outcome,
            parse_vlm_payload,
            uniform_sample_steps,
        )

        self.assertEqual(uniform_sample_steps(0), [])
        self.assertEqual(uniform_sample_steps(1), [0])
        samples = uniform_sample_steps(100, max_samples=5)
        self.assertEqual(samples[0], 0)
        self.assertEqual(samples[-1], 99)
        self.assertEqual(len(samples), 5)
        self.assertEqual(normalize_task_outcome('success'), 'completed_normally')
        self.assertEqual(normalize_task_outcome('failed'), 'failed')
        self.assertIsNone(normalize_task_outcome('not-a-real-outcome'))

        with self.SessionLocal() as db:
            admin = db.get(User, 'user_admin')
            schema = self.create_published_schema(db, admin)
            episode = db.get(Episode, 'episode_qualified')
            episode.frame_count = 100
            task = ensure_task_for_episode(db, episode, initial_source='vlm')
            db.commit()
            definitions = list(schema.definitions)
            raw = [
                {
                    'definitionCode': 'pick_object',
                    'occurrenceNo': 1,
                    'status': 'observed',
                    'startStep': 10,
                    'endStepExclusive': 40,
                    'representativeStep': 20,
                },
                {
                    'definitionCode': 'invented_code',
                    'occurrenceNo': 1,
                    'status': 'observed',
                    'startStep': 0,
                    'endStepExclusive': 5,
                },
                {
                    'definitionCode': 'pick_object',
                    'occurrenceNo': 2,
                    'status': 'skipped',
                    'startStep': 1,
                    'endStepExclusive': 2,
                },
            ]
            # max_occurrences=2 on seed definition; second skipped should drop invalid range fields.
            normalized = normalize_occurrences(raw, definitions=definitions, frame_count=100)
            self.assertEqual(len(normalized), 2)
            self.assertEqual(normalized[0]['definitionCode'], 'pick_object')
            self.assertEqual(normalized[0]['status'], 'observed')
            self.assertEqual(normalized[0]['startStep'], 10)
            self.assertEqual(normalized[0]['source'], 'vlm_initial')
            self.assertEqual(normalized[1]['status'], 'skipped')
            self.assertIsNone(normalized[1]['startStep'])
            parsed = parse_vlm_payload(
                '```json\n{"canonicalInstructionEn":"Pick","taskOutcome":"success","occurrences":[]}\n```'
            )
            self.assertEqual(parsed.get('canonicalInstructionEn'), 'Pick')
            self.assertEqual(normalize_task_outcome(parsed.get('taskOutcome')), 'completed_normally')
            # Meta/thinking prose must not become a fake instruction.
            meta = parse_vlm_payload(
                'We are given a fixed set of sub-goals. The task is to label the episode.\n'
                'Steps to follow: 1) use definitions 2) assign occurrences'
            )
            self.assertNotIn('canonicalInstructionEn', meta)
            self.assertEqual(meta.get('occurrences'), [])
            nested = parse_vlm_payload(
                '{"canonicalInstructionEn": "{\\"canonicalInstructionEn\\": \\"Collect one radish.\\", '
                '\\"taskOutcome\\": \\"completed_normally\\", \\"occurrences\\": []}"}'
            )
            self.assertEqual(nested.get('canonicalInstructionEn'), 'Collect one radish.')

    def test_frame_sampler_step_timestamp_mapping(self) -> None:
        from app.services.annotation_frame_sampler import _step_to_timestamp

        self.assertAlmostEqual(_step_to_timestamp(0, frame_count=100, duration_sec=10.0), 0.0, places=3)
        self.assertAlmostEqual(_step_to_timestamp(99, frame_count=100, duration_sec=10.0), 9.999, places=3)
        mid = _step_to_timestamp(50, frame_count=100, duration_sec=10.0)
        self.assertGreater(mid, 4.0)
        self.assertLess(mid, 6.0)


if __name__ == '__main__':
    unittest.main()
