from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from app.core.db import Base
from app.models import Batch, Episode, ListRecord, TaskType, User
from app.services.annotation import (
    acquire_lock,
    annotation_statistics,
    complete_task,
    create_schema,
    ensure_task_for_episode,
    publish_schema,
    save_draft,
)


class AnnotationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.engine = create_engine(f'sqlite:///{Path(self.tmpdir.name) / "annotations.db"}', future=True)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
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

    def test_statistics_reports_statuses_and_completion_rate(self) -> None:
        with self.SessionLocal() as db:
            admin = db.get(User, 'user_admin')
            self.create_published_schema(db, admin)
            task = ensure_task_for_episode(db, db.get(Episode, 'episode_qualified'))
            db.commit()
            stats = annotation_statistics(db, task_type_id='task_type_pick')
            self.assertEqual(stats['total'], 1)
            self.assertEqual(stats['byStatus'], {'pending': 1})
            self.assertEqual(stats['completionRate'], 0)
            self.assertEqual(task.task_type_id, 'task_type_pick')


if __name__ == '__main__':
    unittest.main()
