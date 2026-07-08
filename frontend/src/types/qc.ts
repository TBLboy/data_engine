export type QcStatus = 'new' | 'assigned' | 'in_review' | 'done' | 'blocked'
export type QcResult = 'pass' | 'fail' | 'pending'
export type UserRole = 'admin' | 'qc_manager' | 'reviewer' | 'viewer'
export type DispatchMode = 'sampled' | 'full'

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
  status: 'scanning' | 'classifying' | 'done' | 'failed'
  progress: number
  confirmedLists: number
  totalEpisodes: number
  newEpisodes: number
  detail: string
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
