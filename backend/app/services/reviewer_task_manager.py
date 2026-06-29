"""Reviewer task manager service — admin operations on reviewer task pools."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import QcTask, TaskOperationLog, User, Episode


class ReviewerTaskManager:
    """Manages reviewer task pools: list, revoke, reassign, release."""

    @staticmethod
    def get_reviewer_tasks(db: Session, reviewer_id: str, status: str | None = None) -> list[dict]:
        query = db.query(QcTask).filter(
            QcTask.assignee == reviewer_id,
            QcTask.is_active == 1,
        )
        if status:
            query = query.filter(QcTask.status == status)
        tasks = query.order_by(QcTask.created_at.desc()).limit(200).all()

        result = []
        for t in tasks:
            episode = db.query(Episode).filter(Episode.id == t.episode_id).first()
            result.append({
                'taskId': t.id,
                'episodeId': t.episode_id,
                'batchId': t.batch_id,
                'batchName': t.batch_name,
                'taskName': t.task_name,
                'status': t.status,
                'assignee': t.assignee,
                'createdAt': t.created_at.isoformat() if t.created_at else None,
                'lockAcquiredAt': t.lock_acquired_at.isoformat() if t.lock_acquired_at else None,
            })
        return result

    @staticmethod
    def revoke_task(db: Session, task_id: str, operator_id: str, reason: str = '') -> dict:
        task = db.query(QcTask).filter(QcTask.id == task_id).first()
        if not task:
            raise ValueError(f'Task {task_id} not found')
        if task.status not in ('new', 'assigned'):
            raise ValueError(f'Task {task_id} is in status {task.status}, cannot revoke')

        prev_reviewer = task.assignee
        task.assignee = '未派发'
        task.status = 'new'
        task.lock_owner_user_id = ''
        task.lock_owner_name = ''
        task.lock_acquired_at = None
        task.lock_expires_at = None

        log = TaskOperationLog(
            task_id=task_id,
            episode_id=task.episode_id,
            operation='revoke',
            from_reviewer=prev_reviewer,
            to_reviewer='',
            operator_id=operator_id,
            reason=reason,
        )
        db.add(log)
        db.commit()
        return {'success': True, 'taskId': task_id, 'operation': 'revoke'}

    @staticmethod
    def reassign_task(db: Session, task_id: str, to_reviewer_id: str, operator_id: str, reason: str = '') -> dict:
        task = db.query(QcTask).filter(QcTask.id == task_id).first()
        if not task:
            raise ValueError(f'Task {task_id} not found')
        if task.status not in ('new', 'assigned'):
            raise ValueError(f'Task {task_id} is in status {task.status}, cannot reassign')

        reviewer = db.query(User).filter(User.id == to_reviewer_id, User.is_active == True).first()
        if not reviewer:
            raise ValueError(f'Reviewer {to_reviewer_id} not found or inactive')

        prev_reviewer = task.assignee
        task.assignee = reviewer.name
        task.status = 'assigned'
        task.lock_owner_user_id = ''
        task.lock_owner_name = ''
        task.lock_acquired_at = None
        task.lock_expires_at = None

        log = TaskOperationLog(
            task_id=task_id,
            episode_id=task.episode_id,
            operation='reassign',
            from_reviewer=prev_reviewer,
            to_reviewer=reviewer.name,
            operator_id=operator_id,
            reason=reason,
        )
        db.add(log)
        db.commit()
        return {'success': True, 'taskId': task_id, 'operation': 'reassign', 'toReviewer': reviewer.name}

    @staticmethod
    def release_task(db: Session, task_id: str, operator_id: str, reason: str = '') -> dict:
        task = db.query(QcTask).filter(QcTask.id == task_id).first()
        if not task:
            raise ValueError(f'Task {task_id} not found')
        if task.status not in ('new', 'assigned'):
            raise ValueError(f'Task {task_id} is in status {task.status}, cannot release')

        prev_reviewer = task.assignee
        task.assignee = '未派发'
        task.status = 'new'
        task.lock_owner_user_id = ''
        task.lock_owner_name = ''
        task.lock_acquired_at = None
        task.lock_expires_at = None

        log = TaskOperationLog(
            task_id=task_id,
            episode_id=task.episode_id,
            operation='release',
            from_reviewer=prev_reviewer,
            to_reviewer='',
            operator_id=operator_id,
            reason=reason,
        )
        db.add(log)
        db.commit()
        return {'success': True, 'taskId': task_id, 'operation': 'release'}

    @staticmethod
    def bulk_revoke(db: Session, task_ids: list[str], operator_id: str, reason: str = '') -> dict:
        results = []
        for tid in task_ids:
            try:
                results.append(ReviewerTaskManager.revoke_task(db, tid, operator_id, reason))
            except ValueError as e:
                results.append({'taskId': tid, 'error': str(e)})
        return {'success': True, 'results': results}

    @staticmethod
    def bulk_reassign(db: Session, task_ids: list[str], to_reviewer_id: str, operator_id: str, reason: str = '') -> dict:
        results = []
        for tid in task_ids:
            try:
                results.append(ReviewerTaskManager.reassign_task(db, tid, to_reviewer_id, operator_id, reason))
            except ValueError as e:
                results.append({'taskId': tid, 'error': str(e)})
        return {'success': True, 'results': results}
