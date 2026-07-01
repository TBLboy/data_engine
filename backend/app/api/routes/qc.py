from __future__ import annotations

import io
import random
from datetime import datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_session_token, hash_password, verify_password, verify_session_token
from app.models import AuditEvent, Batch, Episode, EpisodeInventory, EpisodeObject, GeneralConfig, L3V2Config, ListRecord, QcReviewRevision, QcTask, ScanJob, TaskType, User
from app.schemas.qc import (
    AccountListPayloadSchema,
    AccountSchema,
    AssignTaskRequest,
    AuthLoginRequest,
    BatchDispatchAssignRequest,
    BatchSummarySchema,
    BatchTaskTypeUpdateRequest,
    CreateAccountRequest,
    DashboardPayloadSchema,
    DatabasePayloadSchema,
    DispatchPlanRequest,
    DispatchPreviewSchema,
    HistoryExportPayloadSchema,
    HistoryPayloadSchema,
    HistoryReportPayloadSchema,
    HomePayloadSchema,
    IngestJobSchema,
    IngestScanRequest,
    LoginResponseSchema,
    ManualQcClaimResponseSchema,
    ManualQcContextSchema,
    ManualQcMediaRefreshRequestSchema,
    ManualQcMediaRefreshResponseSchema,
    ManualQcSubmitRequest,
    ManualQcSubmitResponseSchema,
    QcTaskSchema,
    ResetPasswordRequest,
    ReviewerDashboardPayloadSchema,
    SessionPayloadSchema,
    TaskPoolPayloadSchema,
    TaskTypeCreateRequest,
    TaskTypeDetailPayloadSchema,
    TaskTypeSchema,
    TaskTypeUpdateRequest,
    UpdateAccountStatusRequest,
)
from app.services.authz import require_roles
from app.services.minio_client import get_minio_service
from app.services.payloads import (
    _superseded_task_counts_by_batch,
    _task_counts_by_batch,
    build_history_export_payload,
    build_history_report_payload,
    dashboard_payload,
    database_payload,
    dispatch_preview_payload,
    history_payload,
    home_payload,
    manual_qc_context_payload,
    review_lock_payload,
    reviewer_dashboard_payload,
    serialize_account,
    serialize_ingest_job,
    serialize_task,
    serialize_task_type,
    serialize_user,
    sync_batch_metrics,
    task_pool_payload,
    task_type_active_counts,
    task_type_detail_payload,
    unclassified_batch_payload,
)
from app.services.scan_queue import enqueue_scan_job

router = APIRouter(prefix='/api', tags=['qc'])
settings = get_settings()
UNCLASSIFIED_TASK_TYPE_ID = 'task_type:unclassified'


@router.get('/health')
def healthcheck() -> dict[str, str]:
    return {'status': 'ok'}


def _utcnow() -> datetime:
    return datetime.utcnow()


def _active_lock_owner(task: QcTask) -> str:
    if task.lock_owner_user_id and task.lock_expires_at and task.lock_expires_at > _utcnow():
        return task.lock_owner_user_id
    return ''


def _clear_task_lock(task: QcTask) -> None:
    task.lock_owner_user_id = ''
    task.lock_owner_name = ''
    task.lock_acquired_at = None
    task.lock_expires_at = None


def _active_task_for_episode(db: Session, episode_id: str) -> QcTask | None:
    return db.query(QcTask).filter(QcTask.episode_id == episode_id, QcTask.is_active == 1).order_by(QcTask.dispatch_generation.desc(), QcTask.created_at.desc()).first()


def _active_batch_tasks(db: Session, batch_id: str):
    return db.query(QcTask).filter(QcTask.batch_id == batch_id, QcTask.is_active == 1)


def _supersede_pending_batch_tasks(db: Session, batch_id: str, *, next_generation: int) -> list[QcTask]:
    """退役该批次所有旧任务（包括 done），为新派发版本让路。"""
    tasks = _active_batch_tasks(db, batch_id).all()
    superseded = []
    for task in tasks:
        _clear_task_lock(task)
        task.is_active = 0
        task.dispatch_generation = max(task.dispatch_generation, next_generation - 1)
        superseded.append(task)
    return superseded


def _ensure_task_claimable(task: QcTask, current_user: User) -> None:
    active_owner = _active_lock_owner(task)
    # 锁已自然过期但任务状态仍卡在 in_review → 回退，防止出现"进行中却待认领"矛盾态
    if not active_owner and task.status == 'in_review':
        task.status = 'assigned' if task.assignee != '未派发' else 'new'
        _clear_task_lock(task)
    if active_owner and active_owner != current_user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='任务已被其他审核员认领')
    if current_user.role == 'reviewer' and task.assignee not in ('未派发', current_user.name):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='该任务未派发给当前审核员')


def _claim_task(task: QcTask, episode: Episode, current_user: User) -> None:
    now = _utcnow()
    _clear_task_lock(task)
    task.lock_owner_user_id = current_user.id
    task.lock_owner_name = current_user.name
    task.lock_acquired_at = now
    task.lock_expires_at = now + timedelta(seconds=settings.review_lock_ttl_seconds)
    task.status = 'in_review'
    task.assignee = current_user.name
    task.version += 1
    episode.qc_status = 'in_review'
    episode.reviewer = current_user.name
    episode.updated_at = now


def set_session_cookie(response: Response, user: User) -> None:
    token = create_session_token(user.id)
    user.session_token = token
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        samesite='lax',
        secure=settings.session_cookie_secure,
        max_age=settings.session_max_age_seconds,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        samesite='lax',
        secure=settings.session_cookie_secure,
    )


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Not authenticated')

    user_id = verify_session_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Session expired')

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='User not found')
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='账号已停用')
    if user.session_token and user.session_token != token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Session expired — account logged in from another device')
    request.state.user = user
    return user


def _get_task_type_or_404(db: Session, task_type_id: str) -> TaskType:
    task_type = db.query(TaskType).filter(TaskType.id == task_type_id).first()
    if not task_type:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='任务类型不存在')
    return task_type


def _normalize_task_type_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='任务类型名称不能为空')
    if len(normalized) > 50:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='任务类型名称不能超过 50 个字符')
    if any(char in normalized for char in '<>'):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='任务类型名称不能包含尖括号等特殊字符')
    return normalized


def _task_type_id_from_name(name: str) -> str:
    slug = ''.join(char.lower() if char.isalnum() else '_' for char in name).strip('_')
    slug = '_'.join(part for part in slug.split('_') if part)
    if not slug:
        slug = f'task_{int(_utcnow().timestamp())}'
    return f'task_type:{slug}'


def _ensure_task_type_name_available(db: Session, name: str, *, exclude_id: str | None = None) -> None:
    query = db.query(TaskType).filter(TaskType.name == name)
    if exclude_id:
        query = query.filter(TaskType.id != exclude_id)
    if query.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='任务类型名称已存在')


def _audit_event_id(prefix: str, target: str) -> str:
    return f'audit_{prefix}_{target}_{int(_utcnow().timestamp())}'


def _reassign_batch_task_type(db: Session, *, batch: Batch, task_type: TaskType) -> None:
    batch.task_type_id = task_type.id
    for episode in batch.episodes:
        episode.task_name = task_type.name
        episode.updated_at = _utcnow()
    for task in batch.qc_tasks:
        task.task_name = task_type.name
        task.batch_name = batch.name
    # Bulk update any episodes that might not be in the loaded relationship
    db.query(Episode).filter(
        Episode.batch_id == batch.id,
        Episode.task_name != task_type.name,
    ).update({Episode.task_name: task_type.name}, synchronize_session=False)


def _refresh_task_type_stats(db: Session, *task_type_ids: str) -> None:
    unique_ids = {task_type_id for task_type_id in task_type_ids if task_type_id}
    for task_type_id in unique_ids:
        task_type = db.query(TaskType).filter(TaskType.id == task_type_id).first()
        if not task_type:
            continue
        task_type.total_batches, task_type.total_episodes = task_type_active_counts(db, task_type.id)


@router.get('/task-types', response_model=list[TaskTypeSchema])
def list_task_types(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    task_types = db.query(TaskType).order_by(TaskType.id.asc()).all()
    _refresh_task_type_stats(db, *[t.id for t in task_types])
    db.commit()
    return [serialize_task_type(item) for item in task_types]


@router.post('/task-types', response_model=TaskTypeSchema, status_code=status.HTTP_201_CREATED)
def create_task_type(
    payload: TaskTypeCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    name = _normalize_task_type_name(payload.name)
    description = payload.description.strip()
    _ensure_task_type_name_available(db, name)
    task_type = TaskType(
        id=_task_type_id_from_name(name),
        name=name,
        description=description or name,
        is_active=True,
        total_batches=0,
        total_episodes=0,
    )
    if db.query(TaskType).filter(TaskType.id == task_type.id).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='任务类型标识已存在，请更换名称')
    db.add(task_type)
    now = _utcnow()
    db.add(AuditEvent(
        id=_audit_event_id('task_type_create', task_type.id),
        operator=current_user.name,
        action='创建任务类型',
        target=task_type.id,
        detail=f'name={task_type.name}',
        time=now,
    ))
    db.commit()
    db.refresh(task_type)
    return serialize_task_type(task_type)


@router.patch('/task-types/{task_type_id}', response_model=TaskTypeSchema)
def update_task_type(
    task_type_id: str,
    payload: TaskTypeUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    task_type = _get_task_type_or_404(db, task_type_id)
    if task_type.id == UNCLASSIFIED_TASK_TYPE_ID:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='待分类任务类型不可编辑')
    name = _normalize_task_type_name(payload.name)
    description = payload.description.strip()
    _ensure_task_type_name_available(db, name, exclude_id=task_type.id)
    task_type.name = name
    task_type.description = description or name
    for batch in db.query(Batch).filter(Batch.task_type_id == task_type.id).all():
        for episode in batch.episodes:
            episode.task_name = task_type.name
            episode.updated_at = _utcnow()
        for task in batch.qc_tasks:
            task.task_name = task_type.name
    now = _utcnow()
    db.add(AuditEvent(
        id=_audit_event_id('task_type_update', task_type.id),
        operator=current_user.name,
        action='更新任务类型',
        target=task_type.id,
        detail=f'name={task_type.name}',
        time=now,
    ))
    db.commit()
    db.refresh(task_type)
    return serialize_task_type(task_type)


@router.delete('/task-types/{task_type_id}', response_model=TaskTypeSchema)
def delete_task_type(
    task_type_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    task_type = _get_task_type_or_404(db, task_type_id)
    if task_type.id == UNCLASSIFIED_TASK_TYPE_ID:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='待分类任务类型不可删除')
    unclassified = _get_task_type_or_404(db, UNCLASSIFIED_TASK_TYPE_ID)
    affected_batches = db.query(Batch).filter(Batch.task_type_id == task_type.id, Batch.is_active == True).all()
    for batch in affected_batches:
        _reassign_batch_task_type(db, batch=batch, task_type=unclassified)
    task_type.is_active = False
    now = _utcnow()
    db.add(AuditEvent(
        id=_audit_event_id('task_type_delete', task_type.id),
        operator=current_user.name,
        action='停用任务类型',
        target=task_type.id,
        detail=f'batch_ids={"|".join(batch.id for batch in affected_batches)} -> {UNCLASSIFIED_TASK_TYPE_ID}',
        time=now,
    ))
    _refresh_task_type_stats(db, task_type.id, unclassified.id)
    db.commit()
    db.refresh(task_type)
    return serialize_task_type(task_type)


@router.get('/task-types/{task_type_id}/batches', response_model=TaskTypeDetailPayloadSchema)
def task_type_batches(
    task_type_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    task_type = _get_task_type_or_404(db, task_type_id)
    return task_type_detail_payload(db, task_type)


@router.get('/batches', response_model=list[BatchSummarySchema])
def list_batches(
    task_type_id: str = Query(UNCLASSIFIED_TASK_TYPE_ID),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    if task_type_id == UNCLASSIFIED_TASK_TYPE_ID:
        return unclassified_batch_payload(db)
    task_type = _get_task_type_or_404(db, task_type_id)
    return task_type_detail_payload(db, task_type)['batches']


@router.post('/task-types/{task_type_id}/batches:attach', response_model=TaskTypeDetailPayloadSchema)
def attach_batches_to_task_type(
    task_type_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    batch_ids = payload.get('batchIds') if isinstance(payload, dict) else None
    if not isinstance(batch_ids, list) or not all(isinstance(item, str) for item in batch_ids):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='batchIds 必须是字符串数组')
    require_roles(current_user, 'admin', 'qc_manager')
    task_type = _get_task_type_or_404(db, task_type_id)
    if task_type.id == UNCLASSIFIED_TASK_TYPE_ID:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='不能向待分类执行加入操作')
    unclassified = _get_task_type_or_404(db, UNCLASSIFIED_TASK_TYPE_ID)
    batches = db.query(Batch).filter(Batch.id.in_(batch_ids), Batch.is_active == True).all()
    if len(batches) != len(set(batch_ids)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='存在批次不存在')
    for batch in batches:
        if batch.task_type_id != UNCLASSIFIED_TASK_TYPE_ID:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f'批次 {batch.name} 不在待分类池中')
    for batch in batches:
        _reassign_batch_task_type(db, batch=batch, task_type=task_type)
    now = _utcnow()
    db.add(AuditEvent(
        id=_audit_event_id('task_type_attach', task_type.id),
        operator=current_user.name,
        action='批次加入任务类型',
        target=task_type.id,
        detail=f'from={unclassified.id} batches={"|".join(batch.id for batch in batches)}',
        time=now,
    ))
    _refresh_task_type_stats(db, task_type.id, unclassified.id)
    db.commit()
    db.refresh(task_type)
    return task_type_detail_payload(db, task_type)


@router.post('/task-types/{task_type_id}/batches/{batch_id}:detach', response_model=TaskTypeDetailPayloadSchema)
def detach_batch_from_task_type(
    task_type_id: str,
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    task_type = _get_task_type_or_404(db, task_type_id)
    if task_type.id == UNCLASSIFIED_TASK_TYPE_ID:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='待分类中的批次不能继续移出')
    batch = db.query(Batch).filter(Batch.id == batch_id, Batch.is_active == True).first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='批次不存在')
    if batch.task_type_id != task_type.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='该批次不属于当前任务类型')
    unclassified = _get_task_type_or_404(db, UNCLASSIFIED_TASK_TYPE_ID)
    _reassign_batch_task_type(db, batch=batch, task_type=unclassified)
    now = _utcnow()
    db.add(AuditEvent(
        id=_audit_event_id('task_type_detach', batch.id),
        operator=current_user.name,
        action='批次移出任务类型',
        target=batch.id,
        detail=f'from={task_type.id} to={unclassified.id}',
        time=now,
    ))
    _refresh_task_type_stats(db, task_type.id, unclassified.id)
    db.commit()
    db.refresh(task_type)
    return task_type_detail_payload(db, task_type)


def _validate_account_role(role: str) -> str:
    normalized = role.strip()
    if normalized not in {'admin', 'qc_manager', 'reviewer', 'viewer'}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='不支持的角色类型')
    return normalized


def _get_account_or_404(db: Session, user_id: str) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='账号不存在')
    return user


def _normalize_history_batch_id(selected_batch_id: str, db: Session) -> str:
    if selected_batch_id == 'all':
        return selected_batch_id
    batch = db.query(Batch).filter(Batch.id == selected_batch_id).first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='批次不存在')
    return selected_batch_id


@router.get('/accounts', response_model=AccountListPayloadSchema)
def list_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        require_roles(current_user, 'admin', 'qc_manager')
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    accounts = db.query(User).order_by(User.role.asc(), User.username.asc()).all()
    return {'accounts': [serialize_account(item) for item in accounts]}


@router.post('/accounts', response_model=AccountSchema, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: CreateAccountRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        require_roles(current_user, 'admin')
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    username = payload.username.strip()
    name = payload.name.strip()
    password = payload.password.strip()
    role = _validate_account_role(payload.role)
    if not username or not name or not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='账号、姓名、密码不能为空')
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='账号已存在')

    user = User(
        id=f'user_{username}',
        username=username,
        name=name,
        role=role,
        avatar=(name or username)[:1].upper(),
        password_hash=hash_password(password),
        is_active=1,
        password_changed_at=_utcnow(),
    )
    db.add(user)
    now = _utcnow()
    db.add(AuditEvent(
        id=f'audit_account_create_{username}_{int(now.timestamp())}',
        operator=current_user.name,
        action='创建账号',
        target=user.id,
        detail=f'username={username} role={role}',
        time=now,
    ))
    db.commit()
    db.refresh(user)
    return serialize_account(user)


@router.post('/accounts/{user_id}/reset-password', response_model=AccountSchema)
def reset_account_password(
    user_id: str,
    payload: ResetPasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        require_roles(current_user, 'admin')
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    user = _get_account_or_404(db, user_id)
    password = payload.password.strip()
    if not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='新密码不能为空')

    now = _utcnow()
    user.password_hash = hash_password(password)
    user.password_changed_at = now
    db.add(AuditEvent(
        id=f'audit_account_reset_{user.username}_{int(now.timestamp())}',
        operator=current_user.name,
        action='重置密码',
        target=user.id,
        detail=f'username={user.username}',
        time=now,
    ))
    db.commit()
    db.refresh(user)
    return serialize_account(user)


@router.post('/accounts/{user_id}/status', response_model=AccountSchema)
def update_account_status(
    user_id: str,
    payload: UpdateAccountStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        require_roles(current_user, 'admin')
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    user = _get_account_or_404(db, user_id)
    if user.id == current_user.id and not payload.isActive:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='不能停用当前登录账号')

    now = _utcnow()
    user.is_active = 1 if payload.isActive else 0
    db.add(AuditEvent(
        id=f'audit_account_status_{user.username}_{int(now.timestamp())}',
        operator=current_user.name,
        action='启停账号',
        target=user.id,
        detail=f'is_active={bool(user.is_active)}',
        time=now,
    ))
    db.commit()
    db.refresh(user)
    return serialize_account(user)


@router.post('/auth/login', response_model=LoginResponseSchema)
def login(payload: AuthLoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username.strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='用户名或密码错误')
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='账号已停用')

    audit = AuditEvent(
        id=_audit_event_id('login', user.id),
        operator=user.username,
        action='登录',
        target=user.id,
        detail=f'用户 {user.username} 登录成功',
        time=_utcnow(),
        event_type='auth_event',
        severity='info',
        operator_id=user.id,
    )
    db.add(audit)

    set_session_cookie(response, user)
    db.commit()
    session_payload = {'user': serialize_user(user)}
    return {
        'user': session_payload['user'],
        'session': session_payload,
    }


@router.post('/auth/logout', status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, current_user: User = Depends(get_current_user)):
    clear_session_cookie(response)


@router.get('/auth/session', response_model=SessionPayloadSchema)
def session(current_user: User = Depends(get_current_user)):
    return {'user': serialize_user(current_user)}


@router.get('/bootstrap', response_model=HomePayloadSchema)
def bootstrap(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return home_payload(db, current_user)


@router.get('/dashboard', response_model=DashboardPayloadSchema)
def dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return dashboard_payload(db, current_user)


@router.get('/reviewer/dashboard', response_model=ReviewerDashboardPayloadSchema)
def reviewer_dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != 'reviewer':
        raise HTTPException(status_code=403, detail='仅审核员可访问')
    return reviewer_dashboard_payload(db, current_user.id)


@router.get('/database', response_model=DatabasePayloadSchema)
def database(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    keyword: str = Query(''),
    batch_id: str = Query(''),
    qc_status: str = Query(''),
    qc_result: str = Query(''),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return database_payload(
        db,
        page=page,
        page_size=page_size,
        keyword=keyword,
        batch_id=batch_id,
        qc_status=qc_status,
        qc_result=qc_result,
    )


def _expire_stale_scan_jobs(db: Session, *, bucket: str, stale_after: timedelta = timedelta(minutes=30)) -> None:
    cutoff = _utcnow() - stale_after
    stale_jobs = db.query(ScanJob).filter(
        ScanJob.bucket == bucket,
        ScanJob.status.in_(['scanning', 'classifying']),
        ScanJob.finished_at.is_(None),
        ScanJob.started_at < cutoff,
    ).all()
    if not stale_jobs:
        return
    now = _utcnow()
    for job in stale_jobs:
        job.status = 'failed'
        job.error_detail = 'stale queued job'
        job.finished_at = now
    db.commit()


@router.post('/database/scan', response_model=IngestJobSchema)
def scan_database(
    payload: IngestScanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    bucket = payload.bucket.strip()
    if not bucket:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='bucket 不能为空')

    _expire_stale_scan_jobs(db, bucket=bucket)

    existing_scan = db.query(ScanJob).filter(
        ScanJob.bucket == bucket,
        ScanJob.status.in_(['scanning', 'classifying']),
    ).order_by(ScanJob.started_at.desc()).first()
    if existing_scan:
        return serialize_ingest_job(existing_scan)

    scan_job = ScanJob(
        id=f'queued_{int(datetime.utcnow().timestamp())}_{current_user.id}',
        bucket=bucket,
        scope=payload.scope,
        status='scanning',
        total_prefixes=0,
        confirmed_lists=0,
        total_episodes=0,
        new_episodes=0,
        triggered_by=current_user.id,
        error_detail='queued',
        started_at=datetime.utcnow(),
        finished_at=None,
    )
    db.add(scan_job)
    db.commit()
    db.refresh(scan_job)

    enqueue_scan_job(scan_job.id, current_user.id)
    return serialize_ingest_job(scan_job)


@router.get('/task-pool', response_model=TaskPoolPayloadSchema)
def task_pool(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return task_pool_payload(db, current_user)


@router.get('/qc-history', response_model=HistoryPayloadSchema)
def qc_history(
    revision_page: int = Query(1, ge=1),
    revision_page_size: int = Query(20, ge=1, le=200),
    audit_page: int = Query(1, ge=1),
    audit_page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return history_payload(db, revision_page, revision_page_size, audit_page, audit_page_size)


@router.get('/qc-history/report', response_model=HistoryReportPayloadSchema)
def qc_history_report(
    batch_id: str = Query('all'),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    selected_batch_id = _normalize_history_batch_id(batch_id, db)
    return build_history_report_payload(db, selected_batch_id)


@router.get('/qc-history/export', response_model=HistoryExportPayloadSchema)
def qc_history_export(
    batch_id: str = Query('all'),
    scope: str = Query('report'),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    selected_batch_id = _normalize_history_batch_id(batch_id, db)
    normalized_scope = scope.strip() or 'report'
    if normalized_scope not in {'report', 'episodes', 'audits'}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='不支持的导出范围')
    return build_history_export_payload(db, selected_batch_id, normalized_scope)


@router.get('/episodes/{episode_id}/qc-context', response_model=ManualQcContextSchema)
def manual_qc_context(episode_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise HTTPException(status_code=404, detail='Episode not found')
    return manual_qc_context_payload(db, episode_id, current_user)


@router.get('/episodes/{episode_id}/telemetry-curve')
def telemetry_curve(episode_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """返回 qpos/actions 时序数据用于前端遥操作曲线图."""
    from app.services.payloads import _lookup_inventory_for_episode, _read_minio_npz, _read_minio_json
    import numpy as np

    inventory_row = _lookup_inventory_for_episode(db, episode_id)
    if not inventory_row:
        raise HTTPException(status_code=404, detail='Episode not found')
    inventory, bucket = inventory_row

    object_rows = db.query(EpisodeObject).filter(
        EpisodeObject.episode_inventory_id == inventory.id,
        EpisodeObject.object_scope == 'processed',
        EpisodeObject.object_role.in_(['telemetry_npz', 'metadata']),
    ).all()
    obj_map = {item.object_role: item.object_key for item in object_rows}
    telemetry_key = obj_map.get('telemetry_npz')
    if not telemetry_key:
        raise HTTPException(status_code=404, detail='Telemetry data not available')

    with _read_minio_npz(bucket, telemetry_key) as telemetry:
        ts = telemetry['timestamps'].astype(np.float64)
        t_rel = (ts - ts[0]).tolist()
        qpos = telemetry['qpos'].astype(np.float64)
        actions = telemetry['actions'].astype(np.float64)

        # Auto-detect arm/hand dims
        qpos_range = np.max(qpos, axis=0) - np.min(qpos, axis=0)
        active = qpos_range > 1e-8
        qpos_active = np.max(np.abs(qpos[:, active]), axis=0)
        arm_mask = qpos_active <= 3.5
        hand_mask = ~arm_mask
        active_idx = np.where(active)[0]
        arm_dims = active_idx[arm_mask].tolist()
        hand_dims = active_idx[hand_mask].tolist()

        # Downsample if > 500 frames
        n = len(t_rel)
        stride = max(1, n // 500)
        idx = list(range(0, n, stride))
        t_sampled = [t_rel[i] for i in idx]

        qpos_arm = qpos[:, arm_dims][idx, :].tolist() if arm_dims else []
        qpos_hand = qpos[:, hand_dims][idx, :].tolist() if hand_dims else []
        actions_arm = actions[:, arm_dims][idx, :].tolist() if arm_dims else []
        actions_hand = actions[:, hand_dims][idx, :].tolist() if hand_dims else []

    return {
        'timestamps': t_sampled,
        'armDims': len(arm_dims),
        'handDims': len(hand_dims),
        'qposArm': qpos_arm,
        'qposHand': qpos_hand,
        'actionsArm': actions_arm,
        'actionsHand': actions_hand,
    }


def _get_episode_inventory_object_or_404(db: Session, episode_id: str, object_id: str) -> tuple[EpisodeObject, EpisodeInventory]:
    episode_object = db.query(EpisodeObject).filter(EpisodeObject.id == int(object_id)).first()
    if not episode_object:
        raise HTTPException(status_code=404, detail='Object not found')
    inventory = db.query(EpisodeInventory).filter(EpisodeInventory.id == episode_object.episode_inventory_id).first()
    if not inventory:
        raise HTTPException(status_code=404, detail='Episode inventory not found')
    if inventory.ingested_episode_id != episode_id and inventory.episode_id_from_manifest != episode_id and inventory.episode_name != episode_id:
        raise HTTPException(status_code=404, detail='Object does not belong to episode')
    return episode_object, inventory


def _media_refreshable(task: QcTask | None, current_user: User) -> bool:
    if not task:
        return False
    lock_payload = review_lock_payload(task, current_user)
    return bool(lock_payload['isMine'])


@router.post('/episodes/{episode_id}/media/refresh', response_model=ManualQcMediaRefreshResponseSchema)
def refresh_manual_qc_media(
    episode_id: str,
    payload: ManualQcMediaRefreshRequestSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise HTTPException(status_code=404, detail='Episode not found')

    task = db.query(QcTask).filter(QcTask.episode_id == episode_id).first()
    if not _media_refreshable(task, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='当前未持有审核锁，不能刷新媒体预览')

    media = []
    preview_ttl = timedelta(minutes=5)
    minio_service = get_minio_service()
    for object_id in payload.objectIds:
        episode_object, inventory = _get_episode_inventory_object_or_404(db, episode_id, object_id)
        if not episode_object.object_key.endswith('.mp4'):
            continue
        list_record = db.query(ListRecord).filter(ListRecord.id == inventory.list_id).one()
        media.append({
            'objectId': str(episode_object.id),
            'previewUrl': minio_service.presigned_get_object(list_record.bucket, episode_object.object_key, expires=preview_ttl),
            'previewExpiresAt': (datetime.utcnow() + preview_ttl).replace(microsecond=0).isoformat() + 'Z',
            'refreshable': True,
        })

    return {'media': media}


@router.get('/episodes/{episode_id}/objects/{object_id}/download')
def download_episode_object(
    episode_id: str,
    object_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise HTTPException(status_code=404, detail='Episode not found')

    episode_object, inventory = _get_episode_inventory_object_or_404(db, episode_id, object_id)
    list_record = db.query(ListRecord).filter(ListRecord.id == inventory.list_id).one()
    response = get_minio_service().get_object(list_record.bucket, episode_object.object_key)
    filename = episode_object.object_key.rsplit('/', 1)[-1]
    return StreamingResponse(
        response,
        media_type='application/octet-stream',
        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get('/qc/batches/{batch_id}/dispatch-preview', response_model=DispatchPreviewSchema)
def dispatch_preview(batch_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail='Batch not found')
    counts_by_batch = _task_counts_by_batch(db, [batch_id])
    superseded_by_batch = _superseded_task_counts_by_batch(db, [batch_id])
    return dispatch_preview_payload(batch, counts_by_batch.get(batch_id), superseded_by_batch.get(batch_id, 0))


@router.post('/qc/batches/{batch_id}/dispatch-plan', response_model=DispatchPreviewSchema)
def apply_dispatch_plan(
    batch_id: str,
    payload: DispatchPlanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail='Batch not found')

    active_tasks = _active_batch_tasks(db, batch_id).all()
    now = datetime.utcnow()
    if any(task.status == 'in_review' and task.lock_expires_at and task.lock_expires_at > now for task in active_tasks):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='当前批次存在审核中的任务，不能重生成派发任务')

    batch.dispatch_mode = payload.dispatchMode
    batch.sampling_ratio = 100 if payload.dispatchMode == 'full' else payload.samplingRatio
    next_generation = batch.active_dispatch_generation + 1
    batch.active_dispatch_generation = next_generation

    episodes = db.query(Episode).filter(Episode.batch_id == batch_id).order_by(Episode.id).all()
    target_count = batch.episode_count if payload.dispatchMode == 'full' else max(1, round(batch.episode_count * batch.sampling_ratio / 100))

    # 清理所有 episode 的上一轮 QC 痕迹，归零为干净数据
    for episode in episodes:
        episode.qc_status = 'new'
        episode.qc_result = 'pending'
        episode.reviewer = '-'
        episode.reason_code = '-'
        episode.manual_qc_status = 'NOT_REVIEWED'
        episode.manual_qc_result_id = None
        episode.sampled_for_qc = 0
        episode.final_dataset_status = 'PENDING'
        episode.final_decision_source = ''
        episode.is_exportable = False
        episode.updated_at = now
    db.flush()

    # 退役该批次所有旧任务，为新派发版本让路
    superseded = _supersede_pending_batch_tasks(db, batch_id, next_generation=next_generation)

    # 随机抽样
    if payload.dispatchMode == 'full':
        target_episode_ids = {episode.id for episode in episodes}
    else:
        target_episode_ids = {episode.id for episode in random.sample(episodes, min(target_count, len(episodes)))}

    new_task_count = 0
    for episode in episodes:
        if episode.id not in target_episode_ids:
            continue
        episode.sampled_for_qc = 1
        task_id = f'task_{batch_id[-6:]}_{next_generation:03d}_{episode.id[-6:]}'
        db.add(QcTask(
            id=task_id,
            episode_id=episode.id,
            batch_id=batch.id,
            batch_name=batch.name,
            task_name=episode.task_name,
            assignee='未派发',
            status='new',
            priority='high' if episode.id == episodes[0].id else 'normal',
            dispatch_mode=batch.dispatch_mode,
            sampling_ratio=batch.sampling_ratio,
            dispatch_generation=next_generation,
            is_active=1,
            assignment_mode='unassigned',
            created_at=now,
        ))
        new_task_count += 1

    db.flush()  # 确保 sampled_for_qc 和新任务对 sync 查询可见
    sync_batch_metrics(db, batch)
    db.add(AuditEvent(
        id=f'audit_dispatch_{batch_id}_{next_generation}_{int(datetime.utcnow().timestamp())}',
        operator=current_user.name,
        action='更新派发计划',
        target=batch_id,
        detail=f'generation={next_generation} {payload.dispatchMode}:{batch.sampling_ratio}% {payload.note}'.strip(),
        time=datetime.utcnow(),
    ))
    db.commit()
    db.refresh(batch)
    return dispatch_preview_payload(batch, {'new': new_task_count, 'assigned': 0, 'in_review': 0, 'done': 0}, len(superseded))


@router.post('/qc/batches/{batch_id}/dispatch-assign', response_model=DispatchPreviewSchema)
def assign_batch_tasks(
    batch_id: str,
    payload: BatchDispatchAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail='Batch not found')

    active_tasks = _active_batch_tasks(db, batch_id).filter(QcTask.status == 'new').order_by(QcTask.created_at.asc(), QcTask.id.asc()).all()
    if not active_tasks:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='当前批次没有待派发任务')

    reviewers = db.query(User).filter(User.id.in_(payload.reviewerIds), User.role == 'reviewer', User.is_active == 1).order_by(User.username.asc()).all()
    if len(reviewers) != len(set(payload.reviewerIds)) or not reviewers:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='请选择有效的审核员账号')

    assignment_plan: list[tuple[str, int]] = []
    if payload.mode == 'even':
        base = len(active_tasks) // len(reviewers)
        remainder = len(active_tasks) % len(reviewers)
        for index, reviewer in enumerate(reviewers):
            assignment_plan.append((reviewer.name, base + (1 if index < remainder else 0)))
    elif payload.mode == 'custom_counts':
        count_map = {item.reviewerId: item.count for item in payload.reviewers}
        total = sum(max(0, count_map.get(reviewer.id, 0)) for reviewer in reviewers)
        if total != len(active_tasks):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='自定义派发条数之和必须等于待派发任务数')
        for reviewer in reviewers:
            assignment_plan.append((reviewer.name, max(0, count_map.get(reviewer.id, 0))))
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='不支持的派发模式')

    offset = 0
    now = datetime.utcnow()
    for reviewer_name, count in assignment_plan:
        for task in active_tasks[offset:offset + count]:
            task.assignee = reviewer_name
            task.status = 'assigned'
            task.assignment_mode = payload.mode
            _clear_task_lock(task)
            episode = db.query(Episode).filter(Episode.id == task.episode_id).one()
            episode.reviewer = reviewer_name
            episode.qc_status = 'assigned'
            episode.updated_at = now
        offset += count

    sync_batch_metrics(db, batch)
    db.add(AuditEvent(
        id=f'audit_dispatch_assign_{batch_id}_{int(now.timestamp())}',
        operator=current_user.name,
        action='批量派发任务',
        target=batch_id,
        detail=f'mode={payload.mode} reviewers={"|".join(item.id for item in reviewers)}',
        time=now,
    ))
    db.commit()
    db.refresh(batch)
    return dispatch_preview_payload(batch)


@router.post('/qc/tasks/{task_id}/assign', response_model=QcTaskSchema)
def assign_task(
    task_id: str,
    payload: AssignTaskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    task = db.query(QcTask).filter(QcTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail='Task not found')

    task.assignee = payload.assignee
    task.status = 'assigned'
    _clear_task_lock(task)
    episode = db.query(Episode).filter(Episode.id == task.episode_id).one()
    episode.reviewer = payload.assignee
    episode.qc_status = 'assigned'
    episode.updated_at = datetime.utcnow()

    batch = db.query(Batch).filter(Batch.id == task.batch_id).one()
    sync_batch_metrics(db, batch)
    db.add(AuditEvent(
        id=f'audit_assign_{task_id}_{int(datetime.utcnow().timestamp())}',
        operator=current_user.name,
        action='指派任务',
        target=task_id,
        detail=f'assignee={payload.assignee}',
        time=datetime.utcnow(),
    ))
    db.commit()
    db.refresh(task)
    return serialize_task(task, current_user)


@router.post('/qc/manual/{episode_id}/claim', response_model=ManualQcClaimResponseSchema)
def claim_manual_qc(
    episode_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager', 'reviewer')
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise HTTPException(status_code=404, detail='Episode not found')

    task = _active_task_for_episode(db, episode_id)
    if not task:
        raise HTTPException(status_code=404, detail='Qc task not found')

    _ensure_task_claimable(task, current_user)
    _claim_task(task, episode, current_user)
    batch = db.query(Batch).filter(Batch.id == task.batch_id).one()
    sync_batch_metrics(db, batch)
    now = _utcnow()
    db.add(AuditEvent(
        id=f'audit_claim_{episode_id}_{int(now.timestamp())}',
        operator=current_user.name,
        action='认领人工质检',
        target=episode_id,
        detail=f'task={task.id} version={task.version}',
        time=now,
    ))
    db.commit()
    db.refresh(task)
    return {'status': 'claimed', 'reviewLock': serialize_task(task, current_user)['reviewLock']}


@router.post('/qc/manual/{episode_id}/release', response_model=ManualQcClaimResponseSchema)
def release_manual_qc(
    episode_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager', 'reviewer')
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise HTTPException(status_code=404, detail='Episode not found')

    task = _active_task_for_episode(db, episode_id)
    if not task:
        raise HTTPException(status_code=404, detail='Qc task not found')

    active_owner = _active_lock_owner(task)
    is_manager = current_user.role in ('admin', 'qc_manager')
    if active_owner and active_owner != current_user.id and not is_manager:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='当前锁属于其他审核员')
    if not active_owner and current_user.role == 'reviewer' and task.assignee not in ('未派发', current_user.name):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='该任务未派发给当前审核员')

    now = _utcnow()
    _clear_task_lock(task)
    task.version += 1
    task.status = 'assigned' if task.assignee != '未派发' else 'new'
    if episode.qc_status != 'done':
        episode.qc_status = task.status
    episode.updated_at = now

    batch = db.query(Batch).filter(Batch.id == task.batch_id).one()
    sync_batch_metrics(db, batch)
    db.add(AuditEvent(
        id=f'audit_release_{episode_id}_{int(now.timestamp())}',
        operator=current_user.name,
        action='释放人工质检锁',
        target=episode_id,
        detail=f'task={task.id} version={task.version}',
        time=now,
    ))
    db.commit()
    db.refresh(task)
    return {'status': 'released', 'reviewLock': serialize_task(task, current_user)['reviewLock']}


@router.post('/qc/manual/{episode_id}')
def submit_manual_qc(
    episode_id: str,
    payload: ManualQcSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager', 'reviewer')
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise HTTPException(status_code=404, detail='Episode not found')

    task = _active_task_for_episode(db, episode_id) or db.query(QcTask).filter(QcTask.episode_id == episode_id).first()
    if task:
        if payload.version != task.version:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='任务版本已变更，请刷新后重试')
        if _active_lock_owner(task) != current_user.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='请先认领该任务后再提交')

    now = _utcnow()
    episode.qc_result = payload.result
    episode.qc_status = 'done'
    episode.reviewer = current_user.name
    episode.reason_code = payload.primaryReason or '-'
    episode.updated_at = now
    episode.manual_qc_status = 'MANUAL_PASS' if payload.result == 'pass' else 'MANUAL_FAIL'

    if task:
        task.status = 'done'
        task.assignee = current_user.name
        task.version += 1
        _clear_task_lock(task)
        batch = db.query(Batch).filter(Batch.id == task.batch_id).one()
    else:
        batch = db.query(Batch).filter(Batch.id == episode.batch_id).one()

    revision_count = db.query(QcReviewRevision).filter(QcReviewRevision.episode_id == episode_id).count()
    rev = QcReviewRevision(
        episode_id=episode_id,
        revision_no=revision_count + 1,
        result=payload.result,
        primary_reason=payload.primaryReason or '-',
        operator=current_user.name,
        note=payload.note,
        time=now,
    )
    db.add(rev)
    db.flush()  # Ensure rev.id is available and episode changes are visible to sync_batch_metrics
    episode.manual_qc_result_id = str(rev.id) if rev.id else None
    sync_batch_metrics(db, batch)
    db.add(AuditEvent(
        id=f'audit_submit_{episode_id}_{int(now.timestamp())}',
        operator=current_user.name,
        action='提交人工质检',
        target=episode_id,
        detail=f"{payload.result} / {payload.primaryReason or '-'} / version={task.version if task else payload.version}",
        time=now,
    ))
    db.commit()

    # Trigger batch adjudication after QC submit
    from app.services.batch_adjudication import adjudicate_batch_if_ready
    adjudicate_batch_if_ready(db, episode.batch_id)

    # pipeline: remaining tasks for this reviewer
    remaining_count = 0
    next_episode_id = None
    if current_user.role == 'reviewer' and task:
        pending_tasks = db.query(QcTask).filter(
            QcTask.assignee == current_user.name,
            QcTask.is_active == 1,
            QcTask.status.in_(['new', 'assigned']),
        ).order_by(QcTask.created_at.asc()).all()
        remaining_count = len(pending_tasks)
        if pending_tasks:
            next_episode_id = pending_tasks[0].episode_id

    return {
        'success': True,
        'message': 'QC 结果已提交',
        'remainingCount': remaining_count,
        'nextEpisodeId': next_episode_id,
    }


# ── L3 v2 参数配置 ──

@router.get('/admin/l3-v2-params')
def get_l3_v2_params(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin')
    return L3V2Config.get_params(db)


@router.put('/admin/l3-v2-params')
def update_l3_v2_params(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin')
    L3V2Config.save_params(db, payload, updated_by=current_user.name)
    return {'success': True, 'message': 'L3 v2 参数已保存'}


# ── 通用配置 ──

@router.get('/admin/general-config')
def get_general_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin')
    return GeneralConfig.get_params(db)


@router.put('/admin/general-config')
def update_general_config(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin')
    GeneralConfig.save_params(db, payload, updated_by=current_user.name)
    return {'success': True, 'message': '通用配置已保存'}


# ── 训练数据集管理 API ──


@router.get('/dataset/tasks')
def list_dataset_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出可供下游查看的任务列表."""
    task_types = db.query(TaskType).filter(TaskType.is_active == True).order_by(TaskType.name.asc()).all()
    return [serialize_task_type(tt) for tt in task_types]


@router.get('/dataset/tasks/{task_type_id}/summary')
def dataset_task_summary(
    task_type_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """任务级统计."""
    from app.services.dataset_service import DatasetSummaryService
    result = DatasetSummaryService.task_summary(db, task_type_id)
    if not result:
        raise HTTPException(status_code=404, detail='Task type not found')
    return result


@router.get('/dataset/tasks/{task_type_id}/batches')
def dataset_task_batches(
    task_type_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """任务下批次列表."""
    from app.services.dataset_service import DatasetSummaryService
    return DatasetSummaryService.task_batches(db, task_type_id)


@router.post('/dataset/tasks/{task_type_id}/recompute-decisions')
def recompute_task_batch_decisions(
    task_type_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按任务重判全部批次，确保训练数据集页状态与最新 QC 结果一致."""
    require_roles(current_user, 'admin', 'qc_manager')
    task_type = db.query(TaskType).filter(TaskType.id == task_type_id, TaskType.is_active == True).first()
    if not task_type:
        raise HTTPException(status_code=404, detail='Task type not found')

    from app.services.batch_adjudication import adjudicate_batch

    batches = db.query(Batch).filter(Batch.task_type_id == task_type_id, Batch.is_active == True).all()
    refreshed = 0
    accepted = 0
    rejected = 0
    pending = 0

    for batch in batches:
        adjudicate_batch(db, batch.id, actor=current_user.name)
        db.refresh(batch)
        refreshed += 1
        if batch.batch_decision == 'ACCEPTED':
            accepted += 1
        elif batch.batch_decision == 'REJECTED':
            rejected += 1
        else:
            pending += 1

    return {
        'success': True,
        'taskTypeId': task_type_id,
        'taskName': task_type.name,
        'refreshedBatchCount': refreshed,
        'acceptedBatchCount': accepted,
        'rejectedBatchCount': rejected,
        'pendingBatchCount': pending,
    }


@router.get('/dataset/tasks/{task_type_id}/episodes')
def dataset_task_episodes(
    task_type_id: str,
    status: str = Query(None),
    batch_id: str = Query(None),
    final_decision_source: str = Query(None),
    manual_qc_status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """任务下 Episode 列表，支持筛选与分页."""
    query = db.query(Episode).filter(
        Episode.batch.has((Batch.task_type_id == task_type_id) & (Batch.is_active == True)),
    )
    if status:
        query = query.filter(Episode.final_dataset_status == status)
    if batch_id:
        query = query.filter(Episode.batch_id == batch_id)
    if final_decision_source:
        query = query.filter(Episode.final_decision_source == final_decision_source)
    if manual_qc_status:
        query = query.filter(Episode.manual_qc_status == manual_qc_status)

    total = query.count()
    items = query.order_by(Episode.id).offset((page - 1) * page_size).limit(page_size).all()

    def _serialize(e: Episode) -> dict:
        return {
            'episodeId': e.id,
            'taskName': e.task_name,
            'batchId': e.batch_id,
            'batchName': e.batch.name if e.batch else '',
            'finalDatasetStatus': e.final_dataset_status,
            'finalDecisionSource': e.final_decision_source,
            'manualQcStatus': e.manual_qc_status,
            'durationSec': e.duration_sec,
            'frameCount': e.frame_count,
            'reasonCode': e.reason_code,
            'finalDecidedAt': e.final_decided_at.isoformat() if e.final_decided_at else None,
        }

    return {
        'items': [_serialize(e) for e in items],
        'total': total,
        'page': page,
        'pageSize': page_size,
    }


@router.post('/dataset/tasks/{task_type_id}/exports')
def dataset_export_episodes(
    task_type_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出合格 episode 清单."""
    from app.services.dataset_service import DatasetExportService
    fmt = payload.get('format', 'csv')
    batch_ids = payload.get('batchIds') or None
    content, mime_type, count = DatasetExportService.export_episodes(db, task_type_id, fmt, batch_ids=batch_ids)
    DatasetExportService.record_export(db, task_type_id, fmt, count, created_by=current_user.name)
    return StreamingResponse(
        io.BytesIO(content),
        media_type=mime_type,
        headers={
            'Content-Disposition': f"attachment; filename*=UTF-8''{quote(f'qualified_episodes_{task_type_id}.{fmt}')}",
        },
    )


@router.post('/batches/{batch_id}/recompute-decision')
def recompute_batch_decision(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动重算批次判定."""
    require_roles(current_user, 'admin', 'qc_manager')
    from app.services.batch_adjudication import adjudicate_batch
    log = adjudicate_batch(db, batch_id, actor=current_user.name)
    if not log:
        raise HTTPException(status_code=400, detail='Batch not ready for adjudication or empty')
    return {
        'success': True,
        'batchDecision': log.batch_decision,
        'failureRate': log.failure_rate,
        'reason': log.decision_reason,
    }


# ── RDDQF v1.2: 导出历史 ──

@router.get('/dataset/exports')
def dataset_export_history(
    task_type_id: str = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.dataset_service import DatasetExportService
    return DatasetExportService.export_history(db, task_type_id)


# ── RDDQF v1.2: 管理员任务池管理 ──

@router.get('/admin/reviewers/{reviewer_id}/tasks')
def admin_get_reviewer_tasks(
    reviewer_id: str,
    name: str = Query(None),
    status: str = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    from app.services.reviewer_task_manager import ReviewerTaskManager
    return ReviewerTaskManager.get_reviewer_tasks(db, name or reviewer_id, status)


@router.post('/admin/qc-tasks/{task_id}/revoke')
def admin_revoke_task(
    task_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    from app.services.reviewer_task_manager import ReviewerTaskManager
    try:
        return ReviewerTaskManager.revoke_task(db, task_id, current_user.id, payload.get('reason', ''))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/admin/qc-tasks/{task_id}/reassign')
def admin_reassign_task(
    task_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    from app.services.reviewer_task_manager import ReviewerTaskManager
    try:
        return ReviewerTaskManager.reassign_task(
            db, task_id, payload.get('toReviewerId', ''), current_user.id, payload.get('reason', '')
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/admin/qc-tasks/{task_id}/release')
def admin_release_task(
    task_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    from app.services.reviewer_task_manager import ReviewerTaskManager
    try:
        return ReviewerTaskManager.release_task(db, task_id, current_user.id, payload.get('reason', ''))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/admin/qc-tasks/bulk-revoke')
def admin_bulk_revoke(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    from app.services.reviewer_task_manager import ReviewerTaskManager
    return ReviewerTaskManager.bulk_revoke(
        db, payload.get('taskIds', []), current_user.id, payload.get('reason', '')
    )


@router.post('/admin/qc-tasks/bulk-reassign')
def admin_bulk_reassign(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    from app.services.reviewer_task_manager import ReviewerTaskManager
    return ReviewerTaskManager.bulk_reassign(
        db, payload.get('taskIds', []), payload.get('toReviewerId', ''), current_user.id, payload.get('reason', '')
    )
