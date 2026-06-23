from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_session_token, hash_password, verify_password, verify_session_token
from app.models import AuditEvent, Batch, Episode, EpisodeInventory, EpisodeObject, ListRecord, QcReviewRevision, QcTask, ScanJob, User
from app.schemas.qc import (
    AccountListPayloadSchema,
    AccountSchema,
    AssignTaskRequest,
    AuthLoginRequest,
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
    QcTaskSchema,
    ResetPasswordRequest,
    SessionPayloadSchema,
    TaskPoolPayloadSchema,
    UpdateAccountStatusRequest,
)
from app.services.authz import require_roles
from app.services.minio_client import get_minio_service
from app.services.payloads import (
    build_history_export_payload,
    build_history_report_payload,
    dashboard_payload,
    database_payload,
    dispatch_preview_payload,
    history_payload,
    home_payload,
    manual_qc_context_payload,
    review_lock_payload,
    serialize_account,
    serialize_ingest_job,
    serialize_task,
    serialize_user,
    sync_batch_metrics,
    task_pool_payload,
)
from app.services.scan_queue import process_scan_job

router = APIRouter(prefix='/api', tags=['qc'])
settings = get_settings()


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


def _ensure_task_claimable(task: QcTask, current_user: User) -> None:
    active_owner = _active_lock_owner(task)
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


def set_session_cookie(response: Response, user_id: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=create_session_token(user_id),
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
    return user


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

    set_session_cookie(response, user.id)
    session_payload = {'user': serialize_user(user)}
    return {
        'user': session_payload['user'],
        'session': session_payload,
    }


@router.post('/auth/logout', status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
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


@router.get('/database', response_model=DatabasePayloadSchema)
def database(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return database_payload(db)


@router.post('/database/scan', response_model=IngestJobSchema)
def scan_database(
    payload: IngestScanRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, 'admin', 'qc_manager')
    bucket = payload.bucket.strip()
    if not bucket:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='bucket 不能为空')

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

    background_tasks.add_task(
        process_scan_job,
        scan_job.id,
        current_user.id,
    )
    return serialize_ingest_job(scan_job)


@router.get('/task-pool', response_model=TaskPoolPayloadSchema)
def task_pool(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return task_pool_payload(db, current_user)


@router.get('/qc-history', response_model=HistoryPayloadSchema)
def qc_history(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return history_payload(db)


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
    return dispatch_preview_payload(db, batch_id)


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

    batch.dispatch_mode = payload.dispatchMode
    batch.sampling_ratio = 100 if payload.dispatchMode == 'full' else payload.samplingRatio

    episodes = db.query(Episode).filter(Episode.batch_id == batch_id).order_by(Episode.id).all()
    target_count = batch.episode_count if payload.dispatchMode == 'full' else max(1, round(batch.episode_count * batch.sampling_ratio / 100))
    target_episode_ids = {episode.id for episode in episodes[:target_count]}
    sampled_episode_ids = {
        item.episode_id
        for item in db.query(QcTask).filter(QcTask.batch_id == batch_id).all()
    }

    for episode in episodes:
        episode.sampled_for_qc = 1 if episode.id in target_episode_ids else 0
        if episode.id not in target_episode_ids:
            continue
        if episode.id in sampled_episode_ids:
            continue
        task_id = f'task_{batch_id[-3:]}_{len(sampled_episode_ids) + 1:03d}'
        sampled_episode_ids.add(episode.id)
        db.add(QcTask(
            id=task_id,
            episode_id=episode.id,
            batch_id=batch.id,
            batch_name=batch.name,
            task_name=episode.task_name,
            assignee='未派发',
            status='new',
            priority='high' if len(sampled_episode_ids) == 1 else 'normal',
            dispatch_mode=batch.dispatch_mode,
            sampling_ratio=batch.sampling_ratio,
            created_at=datetime.utcnow(),
        ))

    sync_batch_metrics(db, batch)
    db.add(AuditEvent(
        id=f'audit_dispatch_{batch_id}_{int(datetime.utcnow().timestamp())}',
        operator=current_user.name,
        action='更新派发计划',
        target=batch_id,
        detail=f'{payload.dispatchMode}:{batch.sampling_ratio}% {payload.note}'.strip(),
        time=datetime.utcnow(),
    ))
    db.commit()
    db.refresh(batch)
    return dispatch_preview_payload(db, batch_id)


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

    task = db.query(QcTask).filter(QcTask.episode_id == episode_id).first()
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

    task = db.query(QcTask).filter(QcTask.episode_id == episode_id).first()
    if not task:
        raise HTTPException(status_code=404, detail='Qc task not found')

    active_owner = _active_lock_owner(task)
    if active_owner and active_owner != current_user.id:
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

    task = db.query(QcTask).filter(QcTask.episode_id == episode_id).first()
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

    if task:
        task.status = 'done'
        task.assignee = current_user.name
        task.version += 1
        _clear_task_lock(task)
        batch = db.query(Batch).filter(Batch.id == task.batch_id).one()
    else:
        batch = db.query(Batch).filter(Batch.id == episode.batch_id).one()

    revision_count = db.query(QcReviewRevision).filter(QcReviewRevision.episode_id == episode_id).count()
    db.add(QcReviewRevision(
        episode_id=episode_id,
        revision_no=revision_count + 1,
        result=payload.result,
        primary_reason=payload.primaryReason or '-',
        operator=current_user.name,
        note=payload.note,
        time=now,
    ))
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
    return {'status': 'ok'}
