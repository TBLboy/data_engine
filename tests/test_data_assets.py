from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure backend is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from app.core.db import Base
from app.models import (
    Batch,
    BatchAssetRecomputeJob,
    BatchAssetRollup,
    Episode,
    ListRecord,
    ScanJob,
    TaskAssetRecomputeJob,
    TaskAssetRollup,
    TaskType,
)
from app.services.data_assets import (
    ROLLUP_VERSION,
    TASK_ROLLUP_VERSION,
    data_asset_batch_rows,
    data_asset_task_rows,
    data_assets_summary,
    enqueue_task_asset_recompute,
    process_pending_recompute_jobs,
    recompute_batch_asset_rollup,
    recompute_task_asset_rollup,
    rebuild_all_active_rollups,
)


class DataAssetsServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / 'data_assets_test.db'
        self.engine = create_engine(f'sqlite:///{self.db_path}', future=True)
        Base.metadata.create_all(
            self.engine,
            tables=[
                TaskType.__table__,
                ScanJob.__table__,
                ListRecord.__table__,
                Batch.__table__,
                Episode.__table__,
                BatchAssetRollup.__table__,
                BatchAssetRecomputeJob.__table__,
                TaskAssetRollup.__table__,
                TaskAssetRecomputeJob.__table__,
            ],
        )
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False)
        self.seed_data()

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmpdir.cleanup()

    def seed_data(self) -> None:
        now = datetime(2026, 7, 15, 10, 0, 0)
        with self.SessionLocal() as db:
            db.add_all(
                [
                    TaskType(
                        id='task_type_1',
                        name='Pick And Place',
                        description='task one',
                        arm_mode='both_arms',
                        is_active=True,
                    ),
                    TaskType(
                        id='task_type_2',
                        name='Drawer Open',
                        description='task two',
                        arm_mode='left_arm',
                        is_active=True,
                    ),
                    ScanJob(
                        id='scan_active',
                        bucket='robot',
                        scope='full',
                        status='done',
                        total_prefixes=1,
                        confirmed_lists=1,
                        total_episodes=4,
                        new_episodes=4,
                        triggered_by='test',
                        error_detail='',
                        started_at=now - timedelta(hours=1),
                        finished_at=now - timedelta(minutes=50),
                    ),
                    ScanJob(
                        id='scan_inactive',
                        bucket='robot',
                        scope='full',
                        status='done',
                        total_prefixes=1,
                        confirmed_lists=1,
                        total_episodes=1,
                        new_episodes=1,
                        triggered_by='test',
                        error_detail='',
                        started_at=now - timedelta(hours=2),
                        finished_at=now - timedelta(hours=1, minutes=50),
                    ),
                ]
            )
            db.add_all(
                [
                    ListRecord(
                        id='list_active',
                        bucket='robot',
                        list_prefix='lists/active',
                        confirmed_scan_id='scan_active',
                        last_active_scan_id='scan_active',
                        has_raw=True,
                        has_processed=True,
                        total_raw_episodes=4,
                        total_processed_episodes=4,
                        candidate_task_type='Pick And Place',
                        candidate_source='test',
                        final_task_type_id=None,
                        is_active=True,
                        created_at=now - timedelta(days=10),
                        updated_at=now - timedelta(days=1),
                    ),
                    ListRecord(
                        id='list_inactive',
                        bucket='robot',
                        list_prefix='lists/inactive',
                        confirmed_scan_id='scan_inactive',
                        last_active_scan_id='scan_inactive',
                        has_raw=True,
                        has_processed=True,
                        total_raw_episodes=1,
                        total_processed_episodes=1,
                        candidate_task_type='Drawer Open',
                        candidate_source='test',
                        final_task_type_id=None,
                        is_active=False,
                        created_at=now - timedelta(days=10),
                        updated_at=now - timedelta(days=1),
                    ),
                ]
            )
            db.add_all(
                [
                    Batch(
                        id='batch_active_ready',
                        list_id='list_active',
                        task_type_id='task_type_1',
                        name='Alpha Batch',
                        imported_at=now - timedelta(days=3),
                        episode_count=3,
                        sampled_episode_count=2,
                        completed_sample_count=2,
                        dispatch_mode='sampled',
                        sampling_ratio=25,
                        active_dispatch_generation=1,
                        qc_status='reviewing',
                        pass_rate=0.5,
                        top_reason='blur',
                        is_active=True,
                        manual_pass_count=1,
                        manual_fail_count=1,
                        failure_rate=0.5,
                        reject_threshold=0.1,
                        failure_rate_denominator='SAMPLED_COUNT',
                        batch_decision='REJECTED',
                        batch_decision_reason='manual fail count (1/2) exceeds threshold',
                        decision_policy_version='batch-reject-v1',
                        adjudicated_at=now - timedelta(hours=2),
                    ),
                    Batch(
                        id='batch_active_stale',
                        list_id='list_active',
                        task_type_id='task_type_2',
                        name='Beta Batch',
                        imported_at=now - timedelta(days=2),
                        episode_count=1,
                        sampled_episode_count=0,
                        completed_sample_count=0,
                        dispatch_mode='full',
                        sampling_ratio=100,
                        active_dispatch_generation=0,
                        qc_status='new',
                        pass_rate=0,
                        top_reason='-',
                        is_active=True,
                        manual_pass_count=0,
                        manual_fail_count=0,
                        failure_rate=None,
                        reject_threshold=0.2,
                        failure_rate_denominator='SAMPLED_COUNT',
                        batch_decision='PENDING',
                        batch_decision_reason='',
                        decision_policy_version='batch-reject-v1',
                        adjudicated_at=None,
                    ),
                    Batch(
                        id='batch_inactive_list',
                        list_id='list_inactive',
                        task_type_id='task_type_2',
                        name='Gamma Batch',
                        imported_at=now - timedelta(days=1),
                        episode_count=1,
                        sampled_episode_count=1,
                        completed_sample_count=1,
                        dispatch_mode='sampled',
                        sampling_ratio=50,
                        active_dispatch_generation=1,
                        qc_status='done',
                        pass_rate=1,
                        top_reason='-',
                        is_active=True,
                        manual_pass_count=1,
                        manual_fail_count=0,
                        failure_rate=0.0,
                        reject_threshold=0.2,
                        failure_rate_denominator='SAMPLED_COUNT',
                        batch_decision='APPROVED',
                        batch_decision_reason='good',
                        decision_policy_version='batch-reject-v1',
                        adjudicated_at=now - timedelta(hours=5),
                    ),
                    Batch(
                        id='batch_unmapped',
                        list_id=None,
                        task_type_id='task_type_1',
                        name='Delta Batch',
                        imported_at=now - timedelta(days=1),
                        episode_count=1,
                        sampled_episode_count=0,
                        completed_sample_count=0,
                        dispatch_mode='sampled',
                        sampling_ratio=20,
                        active_dispatch_generation=0,
                        qc_status='new',
                        pass_rate=0,
                        top_reason='-',
                        is_active=True,
                        manual_pass_count=0,
                        manual_fail_count=0,
                        failure_rate=None,
                        reject_threshold=0.1,
                        failure_rate_denominator='SAMPLED_COUNT',
                        batch_decision='PENDING',
                        batch_decision_reason='',
                        decision_policy_version='batch-reject-v1',
                        adjudicated_at=None,
                    ),
                ]
            )

            db.add_all(
                [
                    Episode(
                        id='ep_a1',
                        batch_id='batch_active_ready',
                        task_name='pick block',
                        duration_sec=10.5,
                        frame_count=300,
                        qc_status='reviewed',
                        qc_result='pass',
                        reviewer='alice',
                        reason_code='-',
                        updated_at=now - timedelta(minutes=30),
                        in_candidate_pool=1,
                        sampled_for_qc=1,
                        manual_qc_status='MANUAL_PASS',
                        manual_qc_result_id='result_1',
                        final_dataset_status='QUALIFIED',
                        final_decision_source='MANUAL_QC',
                        final_decision_reason='good',
                        final_decided_at=now - timedelta(minutes=25),
                        is_exportable=True,
                        final_decision_policy_version='episode-final-v1',
                        batch_decision_log_id=1,
                    ),
                    Episode(
                        id='ep_a2',
                        batch_id='batch_active_ready',
                        task_name='move block',
                        duration_sec=0,
                        frame_count=0,
                        qc_status='reviewed',
                        qc_result='fail',
                        reviewer='alice',
                        reason_code='blur',
                        updated_at=now - timedelta(minutes=20),
                        in_candidate_pool=1,
                        sampled_for_qc=1,
                        manual_qc_status='MANUAL_FAIL',
                        manual_qc_result_id='result_2',
                        final_dataset_status='UNQUALIFIED',
                        final_decision_source='MANUAL_QC',
                        final_decision_reason='blur',
                        final_decided_at=now - timedelta(minutes=15),
                        is_exportable=False,
                        final_decision_policy_version='episode-final-v1',
                        batch_decision_log_id=1,
                    ),
                    Episode(
                        id='ep_a3',
                        batch_id='batch_active_ready',
                        task_name='release block',
                        duration_sec=0,
                        frame_count=333,
                        qc_status='new',
                        qc_result='pending',
                        reviewer='-',
                        reason_code='-',
                        updated_at=now - timedelta(minutes=10),
                        in_candidate_pool=1,
                        sampled_for_qc=0,
                        manual_qc_status='NOT_REVIEWED',
                        manual_qc_result_id=None,
                        final_dataset_status='PENDING',
                        final_decision_source='PENDING_NOT_ADJUDICATED',
                        final_decision_reason='',
                        final_decided_at=None,
                        is_exportable=False,
                        final_decision_policy_version='',
                        batch_decision_log_id=None,
                    ),
                    Episode(
                        id='ep_b1',
                        batch_id='batch_active_stale',
                        task_name='open drawer',
                        duration_sec=4.0,
                        frame_count=120,
                        qc_status='new',
                        qc_result='pending',
                        reviewer='-',
                        reason_code='occlusion',
                        updated_at=now - timedelta(minutes=5),
                        in_candidate_pool=1,
                        sampled_for_qc=0,
                        manual_qc_status='NOT_REVIEWED',
                        manual_qc_result_id=None,
                        final_dataset_status='PENDING',
                        final_decision_source='PENDING_NOT_ADJUDICATED',
                        final_decision_reason='',
                        final_decided_at=None,
                        is_exportable=False,
                        final_decision_policy_version='',
                        batch_decision_log_id=None,
                    ),
                    Episode(
                        id='ep_c1',
                        batch_id='batch_inactive_list',
                        task_name='inactive list task',
                        duration_sec=9.0,
                        frame_count=90,
                        qc_status='reviewed',
                        qc_result='pass',
                        reviewer='bob',
                        reason_code='lighting',
                        updated_at=now - timedelta(minutes=40),
                        in_candidate_pool=1,
                        sampled_for_qc=1,
                        manual_qc_status='MANUAL_PASS',
                        manual_qc_result_id='result_3',
                        final_dataset_status='QUALIFIED',
                        final_decision_source='MANUAL_QC',
                        final_decision_reason='good',
                        final_decided_at=now - timedelta(minutes=35),
                        is_exportable=True,
                        final_decision_policy_version='episode-final-v1',
                        batch_decision_log_id=2,
                    ),
                ]
            )
            db.commit()

    def test_recompute_batch_asset_rollup_aggregates_counts(self) -> None:
        with self.SessionLocal() as db:
            rollup = recompute_batch_asset_rollup(db, 'batch_active_ready')
            db.commit()
            self.assertIsNotNone(rollup)
            assert rollup is not None
            self.assertEqual(rollup.episode_count, 3)
            self.assertAlmostEqual(rollup.total_duration_sec, 10.5)
            self.assertEqual(rollup.duration_covered_episode_count, 1)
            self.assertEqual(rollup.duration_missing_episode_count, 2)
            self.assertEqual(rollup.total_frame_count, 633)
            self.assertEqual(rollup.frame_covered_episode_count, 2)
            self.assertEqual(rollup.frame_missing_episode_count, 1)
            self.assertEqual(rollup.sampled_episode_count, 2)
            self.assertEqual(rollup.reviewed_count, 2)
            self.assertEqual(rollup.manual_pass_count, 1)
            self.assertEqual(rollup.manual_fail_count, 1)
            self.assertEqual(rollup.qualified_count, 1)
            self.assertEqual(rollup.unqualified_count, 1)
            self.assertEqual(rollup.pending_dataset_count, 1)
            self.assertEqual(rollup.last_episode_updated_at, datetime(2026, 7, 15, 9, 50, 0))
            self.assertIn('episodes:3:updated:', rollup.source_watermark)
            self.assertEqual(rollup.calculation_version, ROLLUP_VERSION)

    def test_data_assets_summary_respects_scope_and_staleness(self) -> None:
        with self.SessionLocal() as db:
            recompute_batch_asset_rollup(db, 'batch_active_ready')
            db.commit()

            summary = data_assets_summary(db)

            self.assertEqual(summary.batch_count, 2)
            self.assertEqual(summary.episode_count, 3)
            self.assertEqual(summary.task_type_count, 2)
            self.assertEqual(summary.failure_reason_count, 2)
            self.assertAlmostEqual(summary.total_duration_sec, 10.5)
            self.assertEqual(summary.total_frame_count, 633)
            self.assertEqual(summary.duration_covered_episode_count, 1)
            self.assertEqual(summary.duration_missing_episode_count, 2)
            self.assertEqual(summary.frame_covered_episode_count, 2)
            self.assertEqual(summary.frame_missing_episode_count, 1)
            self.assertEqual(summary.stale_batch_count, 1)
            self.assertEqual(summary.statistics_scope, 'active_list_active_batch_indexed_episodes')
            self.assertEqual(summary.calculation_version, ROLLUP_VERSION)
            self.assertIsNotNone(summary.oldest_refreshed_at)
            self.assertIsNotNone(summary.newest_refreshed_at)

    def test_data_asset_batch_rows_filter_and_payload_fields(self) -> None:
        with self.SessionLocal() as db:
            recompute_batch_asset_rollup(db, 'batch_active_ready')
            recompute_batch_asset_rollup(db, 'batch_active_stale')
            db.commit()

            items, total = data_asset_batch_rows(
                db,
                page=1,
                page_size=10,
                keyword='Alpha',
                task_type_id='task_type_1',
                batch_decision='REJECTED',
                qc_status='reviewing',
            )

            self.assertEqual(total, 1)
            self.assertEqual(len(items), 1)
            row = items[0]
            self.assertEqual(row.batch_id, 'batch_active_ready')
            self.assertEqual(row.batch_name, 'Alpha Batch')
            self.assertEqual(row.task_type_name, 'Pick And Place')
            self.assertEqual(row.reviewed_count, 2)
            self.assertEqual(row.manual_pass_count, 1)
            self.assertEqual(row.manual_fail_count, 1)
            self.assertEqual(row.pending_dataset_count, 1)
            self.assertEqual(row.batch_decision_reason, 'manual fail count (1/2) exceeds threshold')
            self.assertEqual(row.last_episode_updated_at, datetime(2026, 7, 15, 9, 50, 0))
            self.assertIsNotNone(row.refreshed_at)

    def test_process_pending_recompute_jobs_marks_job_done(self) -> None:
        with self.SessionLocal() as db:
            db.add(
                BatchAssetRecomputeJob(
                    batch_id='batch_active_ready',
                    reason='manual_rebuild',
                    requested_at=datetime(2026, 7, 15, 10, 5, 0),
                    status='pending',
                    attempts=0,
                    last_error='',
                    last_started_at=None,
                    last_finished_at=None,
                )
            )
            db.commit()

            processed = process_pending_recompute_jobs(db, limit=10)
            # Batch job success also enqueues/processes the parent task job in the same worker loop.
            self.assertGreaterEqual(processed, 1)

            job = db.query(BatchAssetRecomputeJob).filter(BatchAssetRecomputeJob.batch_id == 'batch_active_ready').one()
            rollup = db.query(BatchAssetRollup).filter(BatchAssetRollup.batch_id == 'batch_active_ready').one()
            task_job = db.query(TaskAssetRecomputeJob).filter(TaskAssetRecomputeJob.task_type_id == 'task_type_1').one()
            self.assertEqual(job.status, 'done')
            self.assertEqual(job.attempts, 1)
            self.assertEqual(job.last_error, '')
            self.assertIsNotNone(job.last_started_at)
            self.assertIsNotNone(job.last_finished_at)
            self.assertEqual(rollup.episode_count, 3)
            self.assertEqual(task_job.status, 'done')




    def test_recompute_task_asset_rollup_aggregates_from_batch_rollups(self) -> None:
        with self.SessionLocal() as db:
            recompute_batch_asset_rollup(db, 'batch_active_ready')
            recompute_batch_asset_rollup(db, 'batch_active_stale')
            db.commit()

            task1 = recompute_task_asset_rollup(db, 'task_type_1')
            task2 = recompute_task_asset_rollup(db, 'task_type_2')
            db.commit()

            self.assertIsNotNone(task1)
            self.assertIsNotNone(task2)
            assert task1 is not None
            assert task2 is not None

            self.assertEqual(task1.batch_count, 1)
            self.assertEqual(task1.episode_count, 3)
            self.assertEqual(task1.reviewed_count, 2)
            self.assertEqual(task1.not_reviewed_count, 1)
            self.assertEqual(task1.manual_pass_count, 1)
            self.assertEqual(task1.manual_fail_count, 1)
            self.assertEqual(task1.qualified_count, 1)
            self.assertEqual(task1.unqualified_count, 1)
            self.assertEqual(task1.pending_dataset_count, 1)
            self.assertAlmostEqual(task1.total_duration_sec, 10.5)
            self.assertEqual(task1.total_frame_count, 633)
            self.assertEqual(task1.rejected_batch_count, 1)
            self.assertEqual(task1.pending_batch_count, 0)
            self.assertEqual(task1.calculation_version, TASK_ROLLUP_VERSION)

            self.assertEqual(task2.batch_count, 1)
            self.assertEqual(task2.episode_count, 1)
            self.assertEqual(task2.pending_dataset_count, 1)
            self.assertEqual(task2.pending_batch_count, 1)
            self.assertAlmostEqual(task2.total_duration_sec, 4.0)

    def test_task_asset_rows_rate_null_when_denominator_zero(self) -> None:
        with self.SessionLocal() as db:
            recompute_batch_asset_rollup(db, 'batch_active_stale')
            recompute_task_asset_rollup(db, 'task_type_2')
            db.commit()

            items, total = data_asset_task_rows(
                db,
                page=1,
                page_size=20,
                task_type_id='task_type_2',
                include_inactive=True,
            )
            self.assertEqual(total, 1)
            row = items[0]
            self.assertIsNone(row['manual_pass_rate'])
            self.assertIsNone(row['final_qualified_rate'])
            self.assertEqual(row['episode_count'], 1)
            self.assertEqual(row['pending_dataset_count'], 1)

    def test_task_recompute_waits_for_pending_child_batch_jobs(self) -> None:
        with self.SessionLocal() as db:
            recompute_batch_asset_rollup(db, 'batch_active_ready')
            db.add(
                BatchAssetRecomputeJob(
                    batch_id='batch_active_ready',
                    reason='manual_rebuild',
                    requested_at=datetime(2026, 7, 16, 10, 0, 0),
                    status='pending',
                    attempts=0,
                    last_error='',
                    last_started_at=None,
                    last_finished_at=None,
                )
            )
            enqueue_task_asset_recompute(db, 'task_type_1', reason='child_batch_refreshed')
            db.commit()

            result = recompute_task_asset_rollup(db, 'task_type_1')
            db.commit()
            self.assertIsNone(result)
            job = db.query(TaskAssetRecomputeJob).filter(TaskAssetRecomputeJob.task_type_id == 'task_type_1').one()
            self.assertEqual(job.status, 'pending')
            self.assertEqual(job.last_error, 'waiting_for_child_batch_jobs')

    def test_process_pending_task_jobs_does_not_spin_on_pending_child(self) -> None:
        with self.SessionLocal() as db:
            recompute_batch_asset_rollup(db, 'batch_active_ready')
            db.add(
                BatchAssetRecomputeJob(
                    batch_id='batch_active_ready',
                    reason='manual_rebuild',
                    requested_at=datetime(2026, 7, 16, 10, 0, 0),
                    status='running',
                    attempts=1,
                    last_error='',
                    last_started_at=datetime(2026, 7, 16, 10, 0, 0),
                    last_finished_at=None,
                )
            )
            enqueue_task_asset_recompute(db, 'task_type_1', reason='child_batch_refreshed')
            db.commit()

            processed = process_pending_recompute_jobs(db, limit=20)

            self.assertEqual(processed, 0)
            job = db.query(TaskAssetRecomputeJob).filter(TaskAssetRecomputeJob.task_type_id == 'task_type_1').one()
            self.assertEqual(job.status, 'pending')

    def test_batch_recompute_enqueues_parent_task_job(self) -> None:
        with self.SessionLocal() as db:
            recompute_batch_asset_rollup(db, 'batch_active_ready')
            db.commit()
            job = db.query(TaskAssetRecomputeJob).filter(TaskAssetRecomputeJob.task_type_id == 'task_type_1').one()
            self.assertEqual(job.status, 'pending')
            self.assertEqual(job.reason, 'child_batch_refreshed')

    def test_rebuild_all_scope_task_and_all(self) -> None:
        with self.SessionLocal() as db:
            batch_only = rebuild_all_active_rollups(db, scope='batch')
            self.assertEqual(batch_only['rebuiltBatchCount'], 2)
            self.assertEqual(batch_only['rebuiltTaskCount'], 0)

            task_only = rebuild_all_active_rollups(db, scope='task')
            self.assertGreaterEqual(task_only['rebuiltTaskCount'], 2)

            all_result = rebuild_all_active_rollups(db, scope='all')
            self.assertEqual(all_result['rebuiltBatchCount'], 2)
            self.assertGreaterEqual(all_result['rebuiltTaskCount'], 2)

            task1 = db.query(TaskAssetRollup).filter(TaskAssetRollup.task_type_id == 'task_type_1').one()
            task2 = db.query(TaskAssetRollup).filter(TaskAssetRollup.task_type_id == 'task_type_2').one()
            self.assertEqual(task1.episode_count, 3)
            self.assertEqual(task2.episode_count, 1)

    def test_process_pending_recompute_jobs_handles_task_jobs(self) -> None:
        with self.SessionLocal() as db:
            recompute_batch_asset_rollup(db, 'batch_active_ready')
            recompute_batch_asset_rollup(db, 'batch_active_stale')
            enqueue_task_asset_recompute(db, 'task_type_1', reason='manual_rebuild')
            enqueue_task_asset_recompute(db, 'task_type_2', reason='manual_rebuild')
            db.commit()

            processed = process_pending_recompute_jobs(db, limit=20)
            self.assertGreaterEqual(processed, 2)

            task1 = db.query(TaskAssetRollup).filter(TaskAssetRollup.task_type_id == 'task_type_1').one()
            job1 = db.query(TaskAssetRecomputeJob).filter(TaskAssetRecomputeJob.task_type_id == 'task_type_1').one()
            self.assertEqual(task1.episode_count, 3)
            self.assertEqual(job1.status, 'done')


if __name__ == '__main__':
    unittest.main()
