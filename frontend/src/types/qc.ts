export type QcStatus = 'new' | 'assigned' | 'in_review' | 'done' | 'blocked'
export type QcResult = 'pass' | 'fail' | 'pending'
export type UserRole = 'admin' | 'qc_manager' | 'reviewer' | 'viewer'
export type DispatchMode = 'sampled' | 'full'
export type AnnotationWorkStatus = 'pending' | 'assigned' | 'in_progress' | 'completed' | 'invalidated'
export type AnnotationTaskOutcome =
  | 'completed_normally'
  | 'completed_with_retry'
  | 'partially_completed'
  | 'failed'
  | 'uncertain'
export type SubGoalInstanceStatus =
  | 'observed'
  | 'failed'
  | 'skipped'
  | 'not_observed'
  | 'not_applicable'
  | 'uncertain'

export interface UserProfile {
  id: string
  name: string
  role: UserRole
  avatar: string
}

export interface Account {
  id: string
  username: string
  name: string
  role: UserRole
  avatar: string
  isActive: boolean
  passwordChangedAt: string | null
}

export interface BugReport {
  id: string
  description: string
  status: 'open' | 'fixed'
  imageUrls: string[]
  reporterUserId: string
  reporterName: string
  createdAt: string
  updatedAt: string
}

export interface BugReportListPayload {
  items: BugReport[]
}

export type TaskTypeArmMode = 'both_arms' | 'left_arm' | 'right_arm'

export interface TaskType {
  id: string
  name: string
  description: string
  armMode: TaskTypeArmMode
  isActive: boolean
  totalBatches: number
  totalEpisodes: number
}

export interface TaskTypeDetailPayload {
  taskType: TaskType
  batches: BatchSummary[]
}

export interface BatchSummary {
  id: string
  taskTypeId: string
  name: string
  importedAt: string
  episodeCount: number
  sampledEpisodeCount: number
  completedSampleCount: number
  sampleCoverageRate: number
  sampleReviewCompletionRate: number
  dispatchMode: DispatchMode
  samplingRatio: number
  qcStatus: QcStatus
  passRate: number
  topReason: string
  bucket: string
  storagePrefix: string
}

export interface EpisodeRow {
  id: string
  batchId: string
  batchName: string
  taskName: string
  durationSec: number
  frameCount: number
  fps?: number | null
  qcStatus: QcStatus
  qcResult: QcResult
  reviewer: string
  reasonCode: string
  updatedAt: string
  finalDatasetStatus: string
  finalDecisionSource: string
}

export interface ReviewLock {
  isLocked: boolean
  isMine: boolean
  ownerUserId: string
  ownerName: string
  acquiredAt: string | null
  expiresAt: string | null
  version: number
}

export interface QcTask {
  id: string
  episodeId: string
  batchId: string
  batchName: string
  taskName: string
  assignee: string
  status: QcStatus
  priority: 'normal' | 'high'
  dispatchMode: DispatchMode
  samplingRatio: number
  dispatchGeneration: number
  isActive: boolean
  assignmentMode: string
  createdAt: string
  reviewLock: ReviewLock
}

export interface SubGoalDefinition {
  id?: string
  sequenceNo: number
  code: string
  nameEn: string
  nameZh: string
  description: string
  actionVerb: string
  isRequired: boolean
  isConditional: boolean
  maxOccurrences: number | null
  objectRoleHints: Record<string, unknown>
}

export interface AnnotationSchema {
  id: string
  taskTypeId: string
  versionNo: number
  status: 'draft' | 'published' | 'retired'
  contentHash: string
  definitions: SubGoalDefinition[]
  createdAt: string
  publishedAt: string | null
}

export interface AnnotationOccurrence {
  id?: number
  definitionId: string
  definitionCode?: string
  definitionNameEn?: string
  occurrenceNo: number
  status: SubGoalInstanceStatus
  startStep: number | null
  endStepExclusive: number | null
  representativeStep: number | null
  failureReason: string | null
  notes: string | null
  source?: string
}

export interface AnnotationDraft {
  canonicalInstructionEn: string
  canonicalInstructionZh: string | null
  instructionVariantsEn: string[]
  episodeSummary: string | null
  objects: unknown[]
  taskOutcome: AnnotationTaskOutcome | null
  failureSubGoalInstanceId: number | null
  lastSuccessfulSubGoalInstanceId: number | null
  failureReason: string | null
  annotationNotes: string | null
  annotationSchemaVersion: string
  occurrences: AnnotationOccurrence[]
}

export interface AnnotationTask {
  id: string
  episodeId: string
  batchId: string
  batchName: string
  taskTypeId: string
  taskTypeName: string
  workStatus: AnnotationWorkStatus
  assignedTo: string | null
  assignedName: string | null
  assignedAt: string | null
  publicClaimEnabled: boolean
  lockOwner: string | null
  lockExpiresAt: string | null
  currentRevisionNo: number
  rowVersion: number
  initialSource: string
  frameCount: number
  durationSec: number
  finalDatasetStatus: string
  schema: AnnotationSchema | null
  draft: AnnotationDraft | null
  createdAt: string
  updatedAt: string
}

export interface AnnotationTaskListPayload {
  items: AnnotationTask[]
  page: number
  pageSize: number
  total: number
}

export interface AnnotationEligibility {
  eligibleCount: number
  taskCount: number
  unannotatedCount: number
}

export interface AnnotationStatistics {
  total: number
  completed: number
  completionRate: number
  byStatus: Record<string, number>
  byReviewer: Array<{ reviewerId: string; count: number }>
}

export interface DispatchPreview {
  batchId: string
  candidateEpisodeCount: number
  sampledEpisodeCount: number
  unsampledEpisodeCount: number
  createdTaskCount: number
  assignedTaskCount: number
  inReviewTaskCount: number
  doneTaskCount: number
  supersededTaskCount: number
  pendingAssignCount: number
  dispatchMode: DispatchMode
  samplingRatio: number
  activeDispatchGeneration: number
}

export interface L3V2MetricResult {
  metricId: string
  name: string
  qualityDimension: string
  evidenceId: string
  value: number
  valueText: string
  unit: string
  score: number
  level: 'good' | 'warn' | 'bad'
  description: string
  confidence: number
  weight: number
}

export interface L3V2EvidenceGroup {
  evidenceId: string
  label: string
  qualityDimension: string
  score: number
  level: 'good' | 'warn' | 'bad'
  confidence: number
  summary: string
  metrics: L3V2MetricResult[]
  weight: number
}

export interface L3V2QualityDimension {
  dimensionId: string
  label: string
  labelZh: string
  score: number
  level: 'good' | 'warn' | 'bad'
  weight: number
  summary: string
  evidenceGroups: L3V2EvidenceGroup[]
}

export interface L3V2TimelineSegment {
  start: number
  end: number
  startSec: number
  endSec: number
  level: 'good' | 'warn' | 'bad'
  label: string
  sourceMetricId: string
  sourceEvidenceId: string
  qualityDimension: string
  rawValue: number | null
  threshold: number | null
  confidence: number
}

export interface L3V2TelemetryProfile {
  frameCount: number
  durationSec: number
  fps: number
  armDims: number
  handDims: number
  armDimIndices: number[]
  handDimIndices: number[]
}

export interface L3V2Report {
  version: string
  trainingQualityScore: number
  trainingQualityLevel: 'good' | 'warn' | 'bad'
  scoreLabel: string
  qualityDimensions: L3V2QualityDimension[]
  metricResults: L3V2MetricResult[]
  diagnosticMetrics: L3V2MetricResult[]
  timelineSegments: L3V2TimelineSegment[]
  telemetryProfile: L3V2TelemetryProfile
  summary: string
}

export interface ManualQcMedia {
  objectId: string
  role: string
  label: string
  variant: string
  slot: string
  mimeType: string
  previewUrl: string
  previewExpiresAt: string | null
  refreshable: boolean
  downloadable: boolean
  sortOrder: number
}

export interface AuditRecord {
  id: string
  operator: string
  action: string
  target: string
  time: string
  detail: string
  eventType?: string
  severity?: string
  operatorId?: string
  ipAddress?: string
  userAgent?: string
  durationMs?: number
}

export interface ReasonStat {
  reason: string
  count: number
  ratio: number
  category: string
}

export interface DataAssetSummary {
  episodeCount: number
  batchCount: number
  taskTypeCount: number
  failureReasonCount: number
  totalDurationSec: number
  totalFrameCount: number
  durationCoveredEpisodeCount: number
  durationMissingEpisodeCount: number
  frameCoveredEpisodeCount: number
  frameMissingEpisodeCount: number
  statisticsScope: string
  freshness: {
    oldestRefreshedAt: string | null
    newestRefreshedAt: string | null
    staleBatchCount: number
    calculationVersion: string
  }
}

export interface DataAssetBatchRow {
  batchId: string
  batchName: string
  taskTypeId: string
  taskTypeName: string
  episodeCount: number
  totalDurationSec: number
  durationCoveredEpisodeCount: number
  totalFrameCount: number
  frameCoveredEpisodeCount: number
  reviewedCount: number
  qualifiedCount: number
  unqualifiedCount: number
  manualPassCount: number
  manualFailCount: number
  pendingDatasetCount: number
  failureRate: number | null
  rejectThreshold: number
  qcStatus: string
  batchDecision: string
  batchDecisionReason: string
  createdAt: string
  adjudicatedAt: string | null
  updatedAt: string | null
  refreshedAt: string | null
}

export interface DataAssetBatchListPayload {
  items: DataAssetBatchRow[]
  page: number
  pageSize: number
  total: number
}


export interface DataAssetTaskRow {
  taskTypeId: string
  taskTypeName: string
  isActive: boolean
  batchCount: number
  episodeCount: number
  reviewedCount: number
  notReviewedCount: number
  manualPassCount: number
  manualFailCount: number
  manualPassRate: number | null
  manualReviewProgress: number | null
  qualifiedCount: number
  unqualifiedCount: number
  pendingDatasetCount: number
  finalQualifiedRate: number | null
  finalAdjudicationProgress: number | null
  totalDurationSec: number
  durationCoveredEpisodeCount: number
  durationMissingEpisodeCount: number
  durationCoverageRate: number | null
  totalFrameCount: number
  frameCoveredEpisodeCount: number
  frameMissingEpisodeCount: number
  frameCoverageRate: number | null
  sampledEpisodeCount: number
  acceptedBatchCount: number
  rejectedBatchCount: number
  pendingBatchCount: number
  sourceBatchCount: number
  sourceWatermark: string
  calculationVersion: string
  refreshedAt: string | null
  stale: boolean
  jobStatus: string
}

export interface DataAssetTaskListPayload {
  items: DataAssetTaskRow[]
  page: number
  pageSize: number
  total: number
}

export interface DataAssetTaskDetail extends DataAssetTaskRow {
  taskDescription: string
  armMode: string
  topBatches: DataAssetBatchRow[]
  topBatchTotal: number
}

export interface ReviewerWorkload {
  name: string
  assigned: number
  done: number
  passRate: number
  avgMinutes: number
}

export interface BatchDispatchAssignReviewer {
  reviewerId: string
  count: number
}

export interface BatchDispatchAssignRequest {
  mode: 'even' | 'custom_counts'
  reviewerIds: string[]
  reviewers: BatchDispatchAssignReviewer[]
}

export interface TaskPoolPayload {
  batches: BatchSummary[]
  dispatchPreviews: DispatchPreview[]
  qcTasks: QcTask[]
  reviewerWorkloads: ReviewerWorkload[]
  reviewerAccounts: UserProfile[]
}

export interface IngestJob {
  id: string
  bucket: string
  scope: string
  mode?: string
  status: 'scanning' | 'classifying' | 'done' | 'failed' | 'queued' | 'discovering' | 'running' | 'cancelling' | 'succeeded' | 'partially_failed' | 'cancelled'
  progress: number
  totalShards?: number
  succeededShards?: number
  runningShards?: number
  failedShards?: number
  skippedShards?: number
  confirmedLists: number
  totalEpisodes: number
  newEpisodes: number
  detail: string
  errorSummary?: string
  triggerSource?: string
  cancelRequestedAt?: string | null
  startedAt: string
  finishedAt: string | null
}

export interface QcRevision {
  episodeId: string
  batchId: string
  batchName: string
  revisionNo: number
  result: QcResult
  primaryReason: string
  operator: string
  time: string
  note: string
}

export interface HistoryReportSummary {
  batchCount: number
  episodeCount: number
  sampledEpisodeCount: number
  completedSampleCount: number
  failEpisodeCount: number
  passEpisodeCount: number
  passRate: number
  auditEventCount: number
  revisionCount: number
}

export interface HistoryReportReviewer {
  name: string
  assigned: number
  done: number
  passRate: number
}

export interface HistoryBatchReport {
  batchId: string
  batchName: string
  importedAt: string
  qcStatus: QcStatus
  dispatchMode: DispatchMode
  samplingRatio: number
  episodeCount: number
  sampledEpisodeCount: number
  completedSampleCount: number
  failEpisodeCount: number
  passEpisodeCount: number
  passRate: number
  topReason: string
  reviewerCount: number
  auditEventCount: number
  revisionCount: number
  latestActivityAt: string | null
}

export interface HistoryReportPayload {
  generatedAt: string
  selectedBatchId: string
  summary: HistoryReportSummary
  batchReports: HistoryBatchReport[]
  topReasons: ReasonStat[]
  reviewers: HistoryReportReviewer[]
  recentEpisodes: EpisodeRow[]
  recentRevisions: QcRevision[]
  recentAuditRecords: AuditRecord[]
}

export interface HistoryExportPayload {
  generatedAt: string
  scope: 'report' | 'episodes' | 'audits'
  selectedBatchId: string
  summary: HistoryReportSummary
  batchReports: HistoryBatchReport[]
  episodes: EpisodeRow[]
  qcRevisions: QcRevision[]
  auditRecords: AuditRecord[]
}

export interface ReviewerStats {
  pendingCount: number
  inReviewCount: number
  doneTodayCount: number
  totalAssignedCount: number
}

export interface ReviewerBatchGroup {
  batchId: string
  batchName: string
  pendingCount: number
  doneCount: number
  totalCount: number
}

export interface ReviewerNextTask {
  taskId: string
  episodeId: string
  batchName: string
}

export interface ReviewerDashboardPayload {
  stats: ReviewerStats
  batchGroups: ReviewerBatchGroup[]
  nextTask: ReviewerNextTask | null
}

export interface ManualQcSubmitResponse {
  success: boolean
  message: string
  remainingCount: number
  nextEpisodeId: string | null
}

// Dataset management types
export interface DatasetTaskSummary {
  taskId: string
  taskName: string
  qualifiedEpisodeCount: number
  totalEpisodeCount: number
  batchCount: number
  acceptedBatchCount: number
  rejectedBatchCount: number
  pendingBatchCount: number
  manualPassCount: number
  manualFailCount: number
  inferredPassCount: number
  propagatedFailCount: number
  overrideManualPassFailCount: number
  exportableEpisodeCount: number
  annotationCompletedEpisodeCount: number
  annotationPendingEpisodeCount: number
  annotationCoverageRate: number | null
}

export interface DatasetBatchRow {
  batchId: string
  batchName: string
  totalCount: number
  sampledCount: number
  reviewedCount: number
  manualFailCount: number
  manualPassCount: number
  failureRate: number | null
  batchDecision: string
  batchDecisionReason: string
  adjudicatedAt: string | null
  availableEpisodeCount: number
}

export interface DatasetEpisodeRow {
  episodeId: string
  taskName: string
  batchId: string
  batchName: string
  finalDatasetStatus: string
  finalDecisionSource: string
  manualQcStatus: string
  durationSec: number
  frameCount: number
  reasonCode: string
  finalDecidedAt: string | null
  annotationCompleted: boolean
  annotationStatus: string
}

export interface DatasetEpisodeListPayload {
  items: DatasetEpisodeRow[]
  total: number
  page: number
  pageSize: number
}

// Export history
export interface DatasetExportJob {
  id: number
  taskTypeId: string
  exportFormat: string
  episodeCount: number
  filters: {
    qualificationGate?: string[]
    taskTypeId?: string
    batchIds?: string[]
    episodeCount?: number
    annotationRevisionSnapshots?: Array<{
      episode_id: string
      annotation_task_id: string
      annotation_revision_id: number
      annotation_revision_no: number
      annotation_revision_hash: string
      annotation_schema_id: string
      annotation_schema_version: number
      annotation_schema_hash: string
    }>
  }
  createdBy: string | null
  createdAt: string | null
}

// Reviewer task manager
export interface ReviewerTask {
  taskId: string
  episodeId: string
  batchId: string
  batchName: string
  taskName: string
  status: string
  assignee: string
  createdAt: string | null
  lockAcquiredAt: string | null
}

// AI QC Explain
export interface AiExplainRequest {
  episodeId?: string
  qMotionScore: number
  qMotionLevel: string
  weightedScoreBeforeCap?: number | null
  metrics: any[]
  timelineSegments?: any[]
  userPrompt?: string
}

export interface AiExplainResponse {
  enabled: boolean
  source: string
  model: string | null
  latencyMs: number
  explanation: string
  fallbackUsed: boolean
  mentionedMetricIds: string[]
  warnings: string[]
}

// AI Assistant Phase 1: Conversations + Chat
export interface PageState {
  selectedMetricId?: string
  currentVideoTimeSec?: number | null
  selectedTimelineSegmentId?: string
  visibleChart?: string
  openedMetricPanel?: string
}

export interface AiChatRequest {
  conversationId?: string
  episodeId?: string
  message: string
  pageState?: PageState | null
  qMotionScore?: number | null
  qMotionLevel?: string | null
  weightedScoreBeforeCap?: number | null
  metrics?: any[]
  timelineSegments?: any[]
  stream?: boolean
}

export interface AiMessageItem {
  id: string
  role: string
  content: string
  provider?: string | null
  model?: string | null
  latencyMs?: number | null
  createdAt?: string | null
}

export interface AiConversationDetail {
  conversationId: string
  episodeId: string
  title?: string | null
  status: string
  messages: AiMessageItem[]
}

export interface AiChatResponse {
  messageId: string
  conversationId: string
  status: string
  answer: string
  source: string
  model?: string | null
  latencyMs: number
  fallbackUsed: boolean
  warnings: string[]
}
