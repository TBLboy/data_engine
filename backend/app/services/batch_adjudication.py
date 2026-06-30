"""Batch adjudication service — determines batch pass/fail from QC results."""

from datetime import datetime
from sqlalchemy.orm import Session

from app.models import Batch, BatchDecisionLog, Episode, GeneralConfig


def adjudicate_batch(db: Session, batch_id: str, actor: str = 'system') -> BatchDecisionLog | None:
    """Execute batch adjudication. Idempotent — re-running produces same outcome.

    Returns the BatchDecisionLog, or None if not ready for adjudication.
    """
    batch = db.query(Batch).filter(Batch.id == batch_id).with_for_update().first()
    if not batch:
        return None

    episodes = db.query(Episode).filter(Episode.batch_id == batch_id).all()
    total_count = len(episodes)
    if total_count == 0:
        batch.batch_decision = 'PENDING'
        batch.batch_decision_reason = 'empty batch'
        _update_all_episodes_pending(db, batch_id)
        db.commit()
        return None

    sampled_episodes = [e for e in episodes if e.sampled_for_qc]
    sampled_count = len(sampled_episodes)
    reviewed = [e for e in sampled_episodes if e.manual_qc_status in ('MANUAL_PASS', 'MANUAL_FAIL')]
    reviewed_count = len(reviewed)
    manual_pass_count = sum(1 for e in reviewed if e.manual_qc_status == 'MANUAL_PASS')
    manual_fail_count = sum(1 for e in reviewed if e.manual_qc_status == 'MANUAL_FAIL')

    if sampled_count == 0 or reviewed_count < sampled_count:
        batch.batch_decision = 'PENDING'
        batch.batch_decision_reason = 'sample QC not completed'
        _update_all_episodes_pending(db, batch_id)
        batch.manual_pass_count = manual_pass_count
        batch.manual_fail_count = manual_fail_count
        db.commit()
        return None

    general_cfg = GeneralConfig.get_params(db)
    reject_threshold = general_cfg.get('batch_reject_threshold', 0.10)
    failure_rate = manual_fail_count / sampled_count if sampled_count > 0 else 0.0

    if failure_rate > reject_threshold:
        decision = 'REJECTED'
        reason = f'manual fail count ({manual_fail_count}/{sampled_count}) exceeds batch rejection threshold ({reject_threshold})'
    else:
        decision = 'ACCEPTED'
        reason = f'manual fail count ({manual_fail_count}/{sampled_count}) within batch rejection threshold ({reject_threshold})'

    now = datetime.utcnow()

    batch.manual_pass_count = manual_pass_count
    batch.manual_fail_count = manual_fail_count
    batch.failure_rate = round(failure_rate, 6)
    batch.reject_threshold = reject_threshold
    batch.failure_rate_denominator = 'SAMPLED_COUNT'
    batch.batch_decision = decision
    batch.batch_decision_reason = reason
    batch.decision_policy_version = 'batch-reject-v1'
    batch.adjudicated_at = now

    log = BatchDecisionLog(
        batch_id=batch_id,
        policy_version='batch-reject-v1',
        reject_threshold=reject_threshold,
        failure_rate_denominator='SAMPLED_COUNT',
        total_episode_count=total_count,
        sampled_episode_count=sampled_count,
        reviewed_episode_count=reviewed_count,
        manual_pass_count=manual_pass_count,
        manual_fail_count=manual_fail_count,
        failure_rate=round(failure_rate, 6),
        batch_decision=decision,
        decision_reason=reason,
        created_by=actor,
    )
    db.add(log)
    db.flush()

    for episode in episodes:
        if decision == 'REJECTED':
            if episode.manual_qc_status == 'MANUAL_FAIL':
                source = 'MANUAL_FAIL'
                final_status = 'UNQUALIFIED'
            elif episode.manual_qc_status == 'MANUAL_PASS':
                source = 'BATCH_REJECT_OVERRIDE_MANUAL_PASS'
                final_status = 'UNQUALIFIED'
            else:
                source = 'BATCH_REJECT_PROPAGATED_FAIL'
                final_status = 'UNQUALIFIED'
        else:  # ACCEPTED
            if episode.manual_qc_status == 'MANUAL_FAIL':
                source = 'MANUAL_FAIL'
                final_status = 'UNQUALIFIED'
            elif episode.manual_qc_status == 'MANUAL_PASS':
                source = 'MANUAL_PASS'
                final_status = 'QUALIFIED'
            else:
                source = 'BATCH_ACCEPT_INFERRED_PASS'
                final_status = 'QUALIFIED'

        episode.final_dataset_status = final_status
        episode.final_decision_source = source
        episode.final_decision_reason = reason
        episode.final_decided_at = now
        episode.is_exportable = final_status == 'QUALIFIED'
        episode.final_decision_policy_version = 'batch-reject-v1'
        episode.batch_decision_log_id = log.id

    db.commit()
    return log


def adjudicate_batch_if_ready(db: Session, batch_id: str) -> bool:
    """Check if batch is ready and adjudicate. Returns True if adjudication was performed."""
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        return False

    sampled = batch.sampled_episode_count
    completed = batch.completed_sample_count
    if sampled > 0 and completed >= sampled:
        adjudicate_batch(db, batch_id)
        return True
    return False


def _update_all_episodes_pending(db: Session, batch_id: str) -> None:
    for episode in db.query(Episode).filter(Episode.batch_id == batch_id).all():
        episode.final_dataset_status = 'PENDING'
        episode.final_decision_source = 'PENDING_NOT_ADJUDICATED'
        episode.final_decision_reason = 'batch not yet adjudicated'
        episode.is_exportable = False
