from pydantic import BaseModel


class UserProfileSchema(BaseModel):
    id: str
    name: str
    role: str
    avatar: str


class AccountSchema(BaseModel):
    id: str
    username: str
    name: str
    role: str
    avatar: str
    isActive: bool
    passwordChangedAt: str | None


class AccountListPayloadSchema(BaseModel):
    accounts: list[AccountSchema]


class CreateAccountRequest(BaseModel):
    username: str
    name: str
    password: str
    role: str


class ResetPasswordRequest(BaseModel):
    password: str


class UpdateAccountStatusRequest(BaseModel):
    isActive: bool


class AuthLoginRequest(BaseModel):
    username: str
    password: str


class SessionPayloadSchema(BaseModel):
    user: UserProfileSchema


class LoginResponseSchema(BaseModel):
    user: UserProfileSchema
    session: SessionPayloadSchema


class TaskTypeSchema(BaseModel):
    id: str
    name: str
    description: str
    isActive: bool
    totalBatches: int
    totalEpisodes: int


class TaskTypeCreateRequest(BaseModel):
    name: str
    description: str = ''


class TaskTypeUpdateRequest(BaseModel):
    name: str
    description: str = ''


class TaskTypeBatchOperationRequest(BaseModel):
    batchIds: list[str]


class TaskTypeDetailPayloadSchema(BaseModel):
    taskType: TaskTypeSchema
    batches: list['BatchSummarySchema']


class BatchTaskTypeUpdateRequest(BaseModel):
    taskTypeId: str


class BatchSummarySchema(BaseModel):
    id: str
    taskTypeId: str
    name: str
    importedAt: str
    episodeCount: int
    sampledEpisodeCount: int
    completedSampleCount: int
    sampleCoverageRate: int
    sampleReviewCompletionRate: int
    dispatchMode: str
    samplingRatio: int
    qcStatus: str
    passRate: float
    topReason: str
    bucket: str
    storagePrefix: str


class EpisodeRowSchema(BaseModel):
    id: str
    batchId: str
    batchName: str
    taskName: str
    durationSec: float
    frameCount: int
    fps: float | None = None
    qcStatus: str
    qcResult: str
    reviewer: str
    reasonCode: str
    updatedAt: str


class ReviewLockSchema(BaseModel):
    isLocked: bool
    isMine: bool
    ownerUserId: str
    ownerName: str
    acquiredAt: str | None
    expiresAt: str | None
    version: int


class QcTaskSchema(BaseModel):
    id: str
    episodeId: str
    batchId: str
    batchName: str
    taskName: str
    assignee: str
    status: str
    priority: str
    dispatchMode: str
    samplingRatio: int
    createdAt: str
    reviewLock: ReviewLockSchema


class DispatchPreviewSchema(BaseModel):
    batchId: str
    candidateEpisodeCount: int
    sampledEpisodeCount: int
    unsampledEpisodeCount: int
    createdTaskCount: int
    assignedTaskCount: int
    inReviewTaskCount: int
    doneTaskCount: int
    dispatchMode: str
    samplingRatio: int


class MetricCardSchema(BaseModel):
    key: str
    label: str
    value: str
    level: str
    description: str


class ManualQcMediaSchema(BaseModel):
    objectId: str
    role: str
    label: str
    variant: str
    slot: str
    mimeType: str
    previewUrl: str
    previewExpiresAt: str | None
    refreshable: bool
    downloadable: bool
    sortOrder: int


class TimelineSegmentSchema(BaseModel):
    start: int
    end: int
    level: str
    label: str


class AuditRecordSchema(BaseModel):
    id: str
    operator: str
    action: str
    target: str
    time: str
    detail: str


class ReasonStatSchema(BaseModel):
    reason: str
    count: int
    ratio: int
    category: str


class ReviewerWorkloadSchema(BaseModel):
    name: str
    assigned: int
    done: int
    passRate: float
    avgMinutes: float


class IngestJobSchema(BaseModel):
    id: str
    bucket: str
    scope: str
    status: str
    progress: int
    confirmedLists: int
    totalEpisodes: int
    newEpisodes: int
    detail: str
    startedAt: str
    finishedAt: str | None


class IngestScanRequest(BaseModel):
    bucket: str
    scope: str = 'full'


class QcRevisionSchema(BaseModel):
    episodeId: str
    batchId: str
    batchName: str
    revisionNo: int
    result: str
    primaryReason: str
    operator: str
    time: str
    note: str


class HistoryReportSummarySchema(BaseModel):
    batchCount: int
    episodeCount: int
    sampledEpisodeCount: int
    completedSampleCount: int
    failEpisodeCount: int
    passEpisodeCount: int
    passRate: float
    auditEventCount: int
    revisionCount: int


class HistoryReportReviewerSchema(BaseModel):
    name: str
    assigned: int
    done: int
    passRate: float


class HistoryBatchReportSchema(BaseModel):
    batchId: str
    batchName: str
    importedAt: str
    qcStatus: str
    dispatchMode: str
    samplingRatio: int
    episodeCount: int
    sampledEpisodeCount: int
    completedSampleCount: int
    failEpisodeCount: int
    passEpisodeCount: int
    passRate: float
    topReason: str
    reviewerCount: int
    auditEventCount: int
    revisionCount: int
    latestActivityAt: str | None


class HistoryReportPayloadSchema(BaseModel):
    generatedAt: str
    selectedBatchId: str
    summary: HistoryReportSummarySchema
    batchReports: list[HistoryBatchReportSchema]
    topReasons: list[ReasonStatSchema]
    reviewers: list[HistoryReportReviewerSchema]
    recentEpisodes: list[EpisodeRowSchema]
    recentRevisions: list[QcRevisionSchema]
    recentAuditRecords: list[AuditRecordSchema]


class HistoryExportPayloadSchema(BaseModel):
    generatedAt: str
    scope: str
    selectedBatchId: str
    summary: HistoryReportSummarySchema
    batchReports: list[HistoryBatchReportSchema]
    episodes: list[EpisodeRowSchema]
    qcRevisions: list[QcRevisionSchema]
    auditRecords: list[AuditRecordSchema]


class ManualQcContextSchema(BaseModel):
    episode: EpisodeRowSchema
    metrics: list[MetricCardSchema]
    timelineSegments: list[TimelineSegmentSchema]
    revisions: list[QcRevisionSchema]
    reviewLock: ReviewLockSchema
    media: list[ManualQcMediaSchema]


class ManualQcMediaRefreshRequestSchema(BaseModel):
    objectIds: list[str]


class ManualQcMediaRefreshItemSchema(BaseModel):
    objectId: str
    previewUrl: str
    previewExpiresAt: str | None
    refreshable: bool


class ManualQcMediaRefreshResponseSchema(BaseModel):
    media: list[ManualQcMediaRefreshItemSchema]


class DashboardPayloadSchema(BaseModel):
    currentUser: UserProfileSchema
    taskTypes: list[TaskTypeSchema]
    batches: list[BatchSummarySchema]
    qcTasks: list[QcTaskSchema]
    reasonStats: list[ReasonStatSchema]
    reviewerWorkloads: list[ReviewerWorkloadSchema]
    ingestJobs: list[IngestJobSchema]


class DatabasePayloadSchema(BaseModel):
    episodes: list[EpisodeRowSchema]
    batches: list[BatchSummarySchema]
    taskTypes: list[TaskTypeSchema]
    reasonStats: list[ReasonStatSchema]
    ingestJobs: list[IngestJobSchema]
    totalEpisodes: int
    page: int
    pageSize: int


TaskTypeDetailPayloadSchema.model_rebuild()
TaskTypeBatchOperationRequest.model_rebuild()


class TaskPoolPayloadSchema(BaseModel):
    batches: list[BatchSummarySchema]
    dispatchPreviews: list[DispatchPreviewSchema]
    qcTasks: list[QcTaskSchema]
    reviewerWorkloads: list[ReviewerWorkloadSchema]


class HistoryPayloadSchema(BaseModel):
    auditRecords: list[AuditRecordSchema]
    qcRevisions: list[QcRevisionSchema]
    episodes: list[EpisodeRowSchema]
    batches: list[BatchSummarySchema]


class HomePayloadSchema(BaseModel):
    dashboard: DashboardPayloadSchema
    database: DatabasePayloadSchema
    taskPool: TaskPoolPayloadSchema
    history: HistoryPayloadSchema


class DispatchPlanRequest(BaseModel):
    dispatchMode: str
    samplingRatio: int = 25
    note: str = ''


class AssignTaskRequest(BaseModel):
    assignee: str


class ManualQcClaimResponseSchema(BaseModel):
    status: str
    reviewLock: ReviewLockSchema


class ManualQcSubmitRequest(BaseModel):
    result: str
    primaryReason: str = ''
    note: str = ''
    version: int
