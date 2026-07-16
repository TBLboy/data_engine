from __future__ import annotations

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
    armMode: str
    isActive: bool
    totalBatches: int
    totalEpisodes: int


class TaskTypeCreateRequest(BaseModel):
    name: str
    description: str = ''
    armMode: str = 'both_arms'


class TaskTypeUpdateRequest(BaseModel):
    name: str
    description: str = ''
    armMode: str = 'both_arms'


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
    finalDatasetStatus: str = 'PENDING'
    finalDecisionSource: str = ''


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
    dispatchGeneration: int
    isActive: bool
    assignmentMode: str
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
    supersededTaskCount: int
    pendingAssignCount: int
    dispatchMode: str
    samplingRatio: int
    activeDispatchGeneration: int


class L3V2MetricResultSchema(BaseModel):
    metricId: str
    name: str
    qualityDimension: str
    evidenceId: str
    value: float
    valueText: str
    unit: str
    score: float
    level: str
    description: str
    confidence: float = 1.0
    weight: float = 1.0


class L3V2EvidenceGroupSchema(BaseModel):
    evidenceId: str
    label: str
    qualityDimension: str
    score: float
    level: str
    confidence: float
    summary: str
    metrics: list[L3V2MetricResultSchema]
    weight: float = 1.0


class L3V2QualityDimensionSchema(BaseModel):
    dimensionId: str
    label: str
    labelZh: str
    score: float
    level: str
    weight: float
    summary: str
    evidenceGroups: list[L3V2EvidenceGroupSchema]


class L3V2TimelineSegmentSchema(BaseModel):
    start: float
    end: float
    startSec: float
    endSec: float
    level: str
    label: str
    sourceMetricId: str
    sourceEvidenceId: str
    qualityDimension: str
    rawValue: float | None = None
    threshold: float | None = None
    confidence: float = 1.0


class L3V2TelemetryProfileSchema(BaseModel):
    frameCount: int
    durationSec: float
    fps: float
    armDims: int
    handDims: int
    armDimIndices: list[int]
    handDimIndices: list[int]


class L3V2ReportSchema(BaseModel):
    version: str
    trainingQualityScore: float
    trainingQualityLevel: str
    scoreLabel: str
    qualityDimensions: list[L3V2QualityDimensionSchema]
    metricResults: list[L3V2MetricResultSchema]
    diagnosticMetrics: list[L3V2MetricResultSchema]
    timelineSegments: list[L3V2TimelineSegmentSchema]
    telemetryProfile: L3V2TelemetryProfileSchema
    summary: str


class ManualQcContextSchema(BaseModel):
    episode: EpisodeRowSchema
    l3V2: L3V2ReportSchema | None = None
    revisions: list[QcRevisionSchema]
    reviewLock: ReviewLockSchema
    media: list[ManualQcMediaSchema]
    taskStatus: str | None = None
    viewMode: str = 'active'
    canClaim: bool = False
    canSubmit: bool = False


class ReviewerCurrentTasksPayloadSchema(BaseModel):
    items: list[QcTaskSchema]
    total: int
    page: int
    pageSize: int


class ReviewerHistoryTaskItemSchema(BaseModel):
    episodeId: str
    batchId: str
    batchName: str
    taskName: str
    result: str
    primaryReason: str
    revisionNo: int
    operator: str
    time: str
    note: str
    currentTaskStatus: str | None = None
    currentTaskAssignee: str | None = None
    hasPendingRequest: bool = False


class ReviewerHistoryTasksPayloadSchema(BaseModel):
    items: list[ReviewerHistoryTaskItemSchema]
    total: int
    page: int
    pageSize: int


class RereviewRequestCreateSchema(BaseModel):
    reason: str


class RereviewRequestDecisionSchema(BaseModel):
    note: str = ''


class RereviewRequestItemSchema(BaseModel):
    id: str
    episodeId: str
    batchId: str
    batchName: str
    taskId: str
    requesterUserId: str
    requesterName: str
    reason: str
    status: str
    approverUserId: str | None = None
    approverName: str | None = None
    decisionNote: str = ''
    createdAt: str
    decidedAt: str | None = None


class RereviewRequestListPayloadSchema(BaseModel):
    items: list[RereviewRequestItemSchema]
    total: int
    page: int
    pageSize: int


class AuditRecordSchema(BaseModel):
    id: str
    operator: str
    action: str
    target: str
    time: str
    detail: str
    eventType: str | None = None
    severity: str | None = None
    operatorId: str | None = None
    ipAddress: str | None = None
    userAgent: str | None = None
    durationMs: int | None = None


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
    dispatchPreviews: list[DispatchPreviewSchema]
    reasonStats: list[ReasonStatSchema]
    reviewerWorkloads: list[ReviewerWorkloadSchema]
    reviewerAccounts: list[UserProfileSchema]
    ingestJobs: list[IngestJobSchema]


class DataAssetFreshnessSchema(BaseModel):
    oldestRefreshedAt: str | None
    newestRefreshedAt: str | None
    staleBatchCount: int
    calculationVersion: str


class DataAssetSummarySchema(BaseModel):
    episodeCount: int
    batchCount: int
    taskTypeCount: int
    failureReasonCount: int
    totalDurationSec: float
    totalFrameCount: int
    durationCoveredEpisodeCount: int
    durationMissingEpisodeCount: int
    frameCoveredEpisodeCount: int
    frameMissingEpisodeCount: int
    statisticsScope: str
    freshness: DataAssetFreshnessSchema


class DataAssetBatchRowSchema(BaseModel):
    batchId: str
    batchName: str
    taskTypeId: str
    taskTypeName: str
    episodeCount: int
    totalDurationSec: float
    durationCoveredEpisodeCount: int
    totalFrameCount: int
    frameCoveredEpisodeCount: int
    reviewedCount: int
    qualifiedCount: int
    unqualifiedCount: int
    manualPassCount: int
    manualFailCount: int
    pendingDatasetCount: int
    failureRate: float | None
    rejectThreshold: float
    qcStatus: str
    batchDecision: str
    batchDecisionReason: str
    createdAt: str
    adjudicatedAt: str | None
    updatedAt: str | None
    refreshedAt: str | None


class DataAssetBatchListSchema(BaseModel):
    items: list[DataAssetBatchRowSchema]
    page: int
    pageSize: int
    total: int


class DataAssetTaskRowSchema(BaseModel):
    taskTypeId: str
    taskTypeName: str
    isActive: bool
    batchCount: int
    episodeCount: int
    reviewedCount: int
    notReviewedCount: int
    manualPassCount: int
    manualFailCount: int
    manualPassRate: float | None
    manualReviewProgress: float | None
    qualifiedCount: int
    unqualifiedCount: int
    pendingDatasetCount: int
    finalQualifiedRate: float | None
    finalAdjudicationProgress: float | None
    totalDurationSec: float
    durationCoveredEpisodeCount: int
    durationMissingEpisodeCount: int
    durationCoverageRate: float | None
    totalFrameCount: int
    frameCoveredEpisodeCount: int
    frameMissingEpisodeCount: int
    frameCoverageRate: float | None
    sampledEpisodeCount: int
    acceptedBatchCount: int
    rejectedBatchCount: int
    pendingBatchCount: int
    sourceBatchCount: int
    sourceWatermark: str
    calculationVersion: str
    refreshedAt: str | None
    stale: bool
    jobStatus: str


class DataAssetTaskListSchema(BaseModel):
    items: list[DataAssetTaskRowSchema]
    page: int
    pageSize: int
    total: int


class DataAssetTaskDetailSchema(DataAssetTaskRowSchema):
    taskDescription: str
    armMode: str
    topBatches: list[DataAssetBatchRowSchema]
    topBatchTotal: int


class DataAssetRebuildRequest(BaseModel):
    scope: str = 'all'
    taskTypeIds: list[str] | None = None
    force: bool = False


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
    reviewerAccounts: list[UserProfileSchema]


class HistoryPayloadSchema(BaseModel):
    auditRecords: list[AuditRecordSchema]
    auditTotal: int = 0
    qcRevisions: list[QcRevisionSchema]
    revisionTotal: int = 0
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


class BatchDispatchAssignReviewerSchema(BaseModel):
    reviewerId: str
    count: int = 0


class BatchDispatchAssignRequest(BaseModel):
    mode: str
    reviewerIds: list[str]
    reviewers: list[BatchDispatchAssignReviewerSchema] = []


class ManualQcClaimResponseSchema(BaseModel):
    status: str
    reviewLock: ReviewLockSchema


class BugReportSchema(BaseModel):
    id: str
    description: str
    status: str
    imageUrls: list[str]
    reporterUserId: str
    reporterName: str
    createdAt: str
    updatedAt: str


class BugReportListPayloadSchema(BaseModel):
    items: list[BugReportSchema]


class BugReportStatusUpdateRequest(BaseModel):
    status: str


class ManualQcSubmitRequest(BaseModel):
    result: str
    primaryReason: str = ''
    note: str = ''
    version: int


class ManualQcSubmitResponseSchema(BaseModel):
    success: bool
    message: str
    remainingCount: int = 0
    nextEpisodeId: str | None = None


class ReviewerDashboardStatsSchema(BaseModel):
    pendingCount: int = 0
    inReviewCount: int = 0
    doneTodayCount: int = 0
    totalAssignedCount: int = 0


class ReviewerBatchGroupSchema(BaseModel):
    batchId: str
    batchName: str
    pendingCount: int = 0
    doneCount: int = 0
    totalCount: int = 0


class ReviewerNextTaskSchema(BaseModel):
    taskId: str
    episodeId: str
    batchName: str


class ReviewerDashboardPayloadSchema(BaseModel):
    stats: ReviewerDashboardStatsSchema
    batchGroups: list[ReviewerBatchGroupSchema]
    nextTask: ReviewerNextTaskSchema | None = None
