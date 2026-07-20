from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import verify_session_token
from app.models import AnnotationTask, Batch, Episode, SubGoalSchema, User
from app.models import SubGoalDefinition
from app.schemas.annotation import (
    AnnotationAssignmentRequest,
    AnnotationDraftRequest,
    AnnotationLockResponse,
    AnnotationPublicClaimRequest,
    SubGoalSchemaCreateRequest,
    AnnotationTaskEnsureRequest,
    AnnotationTaskListResponse,
)
from app.services.annotation import (
    acquire_lock,
    active_qualified_episode_query,
    annotation_statistics,
    audit,
    complete_task,
    create_schema,
    ensure_task_for_episode,
    ensure_tasks_for_episodes,
    format_time,
    get_task,
    get_task_for_update,
    publish_schema,
    release_lock,
    save_draft,
    serialize_schema,
    serialize_task,
    utcnow,
)
from app.services.authz import require_roles


router = APIRouter(prefix='/api/annotations', tags=['annotations'])
settings = get_settings()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Not authenticated')
    user_id = verify_session_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Session expired')
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='账号无效')
    if user.session_token and user.session_token != token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Session expired')
    return user


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get('/schemas')
def list_schemas(
    task_type_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager', 'reviewer', 'viewer')
    query = db.query(SubGoalSchema).options(joinedload(SubGoalSchema.definitions)).order_by(
        SubGoalSchema.task_type_id.asc(), SubGoalSchema.version_no.desc()
    )
    if task_type_id:
        query = query.filter(SubGoalSchema.task_type_id == task_type_id)
    return [serialize_schema(item) for item in query.all()]


@router.post('/schemas', status_code=status.HTTP_201_CREATED)
def create_annotation_schema(
    payload: SubGoalSchemaCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    try:
        schema = create_schema(
            db,
            task_type_id=payload.taskTypeId,
            definitions=[item.model_dump() for item in payload.definitions],
            user=current_user,
        )
        audit(db, user=current_user, action='创建标注 Schema', target=schema.id)
        db.commit()
        schema = db.query(SubGoalSchema).options(joinedload(SubGoalSchema.definitions)).filter(
            SubGoalSchema.id == schema.id
        ).one()
        return serialize_schema(schema)
    except Exception as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.post('/schemas/{schema_id}/publish')
def publish_annotation_schema(
    schema_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    schema = db.query(SubGoalSchema).options(joinedload(SubGoalSchema.definitions)).filter(
        SubGoalSchema.id == schema_id
    ).first()
    if not schema:
        raise HTTPException(status_code=404, detail='Schema 不存在')
    try:
        publish_schema(db, schema, current_user)
        audit(db, user=current_user, action='发布标注 Schema', target=schema.id)
        db.commit()
        return serialize_schema(schema)
    except Exception as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.get('/eligible')
def annotation_eligibility(
    task_type_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager', 'reviewer', 'viewer')
    query = active_qualified_episode_query(db)
    if task_type_id:
        # active_qualified_episode_query already joins Batch; do not join batches again.
        query = query.filter(Batch.task_type_id == task_type_id)
    total = query.count()
    task_count = db.query(AnnotationTask).filter(AnnotationTask.episode_id.in_(query.with_entities(Episode.id))).count() if total else 0
    return {'eligibleCount': total, 'taskCount': task_count, 'unannotatedCount': total - task_count}


@router.get('/statistics')
def annotation_operation_statistics(
    task_type_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager', 'reviewer', 'viewer')
    return annotation_statistics(db, task_type_id=task_type_id)


@router.post('/tasks/ensure')
def ensure_annotation_tasks(
    payload: AnnotationTaskEnsureRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    query = active_qualified_episode_query(db)
    if payload.taskTypeId:
        # active_qualified_episode_query already joins Batch; filter on that join.
        query = query.filter(Batch.task_type_id == payload.taskTypeId)
    if payload.episodeIds:
        query = query.filter(Episode.id.in_(payload.episodeIds))
    query = query.order_by(Episode.id.asc()).limit(payload.limit)
    tasks, skipped = ensure_tasks_for_episodes(db, query.all())
    created = [task.id for task in tasks]
    audit(db, user=current_user, action='创建标注任务', target='batch', detail=f'created={len(created)} skipped={len(skipped)}')
    db.commit()
    return {'createdCount': len(created), 'createdTaskIds': created, 'skipped': skipped}


@router.post('/tasks/{task_id}/public-claim')
def set_public_claim(
    task_id: str,
    payload: AnnotationPublicClaimRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    task = get_task_for_update(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail='标注任务不存在')
    if task.work_status != 'pending' or task.assigned_to:
        raise HTTPException(status_code=409, detail='只有未分配 pending 任务可以开放领取')
    task.public_claim_enabled = payload.enabled
    task.public_claim_enabled_by = current_user.id if payload.enabled else None
    task.public_claim_enabled_at = utcnow() if payload.enabled else None
    task.row_version += 1
    audit(db, user=current_user, action='设置标注公共领取', target=task.id, detail=f'enabled={payload.enabled}')
    db.commit()
    return serialize_task(get_task(db, task.id) or task)


@router.get('/tasks', response_model=AnnotationTaskListResponse)
def list_annotation_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    work_status: str | None = Query(default=None),
    task_type_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager', 'reviewer', 'viewer')
    query = db.query(AnnotationTask)
    if current_user.role == 'reviewer':
        query = query.filter(or_(
            AnnotationTask.assigned_to == current_user.id,
            (AnnotationTask.assigned_to.is_(None) & (AnnotationTask.public_claim_enabled.is_(True))),
        ))
    if work_status:
        query = query.filter(AnnotationTask.work_status == work_status)
    if task_type_id:
        query = query.filter(AnnotationTask.task_type_id == task_type_id)
    total = query.order_by(None).count()
    items = query.order_by(AnnotationTask.updated_at.desc(), AnnotationTask.id.asc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return {'items': [serialize_task(get_task(db, item.id) or item) for item in items], 'page': page, 'pageSize': page_size, 'total': total}


@router.get('/tasks/{task_id}')
def get_annotation_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager', 'reviewer', 'viewer')
    task = get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail='标注任务不存在')
    if current_user.role == 'reviewer' and task.assigned_to != current_user.id and not (
        task.work_status == 'pending' and task.public_claim_enabled and task.assigned_to is None
    ):
        raise HTTPException(status_code=403, detail='只能查看分配给本人的标注任务')
    return serialize_task(task)


@router.post('/tasks/{task_id}/assign')
def assign_annotation_task(
    task_id: str,
    payload: AnnotationAssignmentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    task = get_task_for_update(db, task_id)
    reviewer = db.query(User).filter(User.id == payload.reviewerId, User.is_active == 1, User.role == 'reviewer').first()
    if not task:
        raise HTTPException(status_code=404, detail='标注任务不存在')
    if not reviewer:
        raise HTTPException(status_code=400, detail='目标用户不是有效 reviewer')
    if task.work_status not in {'pending', 'assigned'}:
        raise HTTPException(status_code=409, detail='只有 pending 或 assigned 标注任务可以分配')
    if task.lock_owner and task.lock_expires_at and task.lock_expires_at > utcnow():
        raise HTTPException(status_code=409, detail='任务存在有效编辑锁')
    previous_reviewer_id = task.assigned_to
    task.assigned_to = reviewer.id
    task.assigned_by = current_user.id
    task.assigned_at = utcnow()
    task.assignment_note = payload.note.strip()
    task.public_claim_enabled = False
    task.work_status = 'assigned'
    task.row_version += 1
    audit(
        db,
        user=current_user,
        action='分配标注任务',
        target=task.id,
        detail=f'previous_reviewer={previous_reviewer_id or ""} reviewer={reviewer.id} row_version={task.row_version}',
    )
    db.commit()
    return serialize_task(get_task(db, task.id) or task)


@router.post('/tasks/{task_id}/claim')
def claim_annotation_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'reviewer')
    task = get_task_for_update(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail='标注任务不存在')
    if task.work_status != 'pending' or task.assigned_to or not task.public_claim_enabled:
        raise HTTPException(status_code=409, detail='任务当前不可领取')
    task.assigned_to = current_user.id
    task.assigned_at = utcnow()
    task.public_claim_enabled = False
    task.work_status = 'assigned'
    task.row_version += 1
    audit(db, user=current_user, action='领取标注任务', target=task.id)
    db.commit()
    return serialize_task(get_task(db, task.id) or task)


@router.post('/tasks/{task_id}/lock', response_model=AnnotationLockResponse)
def lock_annotation_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager', 'reviewer')
    task = get_task_for_update(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail='标注任务不存在')
    try:
        was_completed = task.work_status == 'completed'
        acquire_lock(db, task, current_user)
        audit(db, user=current_user, action='获取标注编辑锁', target=task.id)
        if was_completed:
            audit(db, user=current_user, action='重新编辑已完成标注', target=task.id, detail=f'revision={task.current_revision_no}')
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _http_error(exc) from exc
    return {
        'taskId': task.id,
        'lockOwner': task.lock_owner,
        'lockExpiresAt': format_time(task.lock_expires_at),
        'rowVersion': task.row_version,
    }


@router.delete('/tasks/{task_id}/lock', response_model=AnnotationLockResponse)
def unlock_annotation_task(
    task_id: str,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager', 'reviewer')
    task = get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail='标注任务不存在')
    try:
        release_lock(db, task, current_user, force=force)
        audit(db, user=current_user, action='释放标注编辑锁', target=task.id, detail=f'force={force}')
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _http_error(exc) from exc
    return {'taskId': task.id, 'lockOwner': task.lock_owner, 'lockExpiresAt': None, 'rowVersion': task.row_version}


@router.put('/tasks/{task_id}/draft')
def save_annotation_draft(
    task_id: str,
    payload: AnnotationDraftRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager', 'reviewer')
    task = get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail='标注任务不存在')
    try:
        save_draft(db, task, current_user, payload.model_dump())
        audit(db, user=current_user, action='保存标注草稿', target=task.id)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _http_error(exc) from exc
    return serialize_task(get_task(db, task.id) or task)


@router.post('/tasks/{task_id}/complete')
def complete_annotation_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager', 'reviewer')
    task = get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail='标注任务不存在')
    try:
        revision = complete_task(db, task, current_user)
        audit(db, user=current_user, action='完成标注任务', target=task.id, detail=f'revision={revision.revision_no}')
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _http_error(exc) from exc
    return {'task': serialize_task(get_task(db, task.id) or task), 'revisionNo': revision.revision_no, 'contentHash': revision.content_hash}
