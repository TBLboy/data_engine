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

export interface TaskType {
  id: string
  name: string
  description: string
  totalBatches: number
  totalEpisodes: number
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
  storagePath: string
}

export interface EpisodeRow {
  id: string
  batchId: string
  batchName: string
  taskName: string
  durationSec: number
  frameCount: number
  qcStatus: QcStatus
  qcResult: QcResult
  reviewer: string
  reasonCode: string
  updatedAt: string
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
  dispatchMode: DispatchMode
  samplingRatio: number
}

export interface MetricCard {
  key: string
  label: string
  value: string
  level: 'good' | 'warn' | 'bad'
  description: string
}

export interface TimelineSegment {
  start: number
  end: number
  level: 'warn' | 'bad'
  label: string
}

export interface AuditRecord {
  id: string
  operator: string
  action: string
  target: string
  time: string
  detail: string
}

export interface ReasonStat {
  reason: string
  count: number
  ratio: number
  category: 'L2' | 'L3' | 'L4' | 'System'
}

export interface ReviewerWorkload {
  name: string
  assigned: number
  done: number
  passRate: number
  avgMinutes: number
}

export interface IngestJob {
  id: string
  batchId: string
  batchName: string
  sourcePath: string
  status: 'scanning' | 'converted' | 'indexed' | 'failed'
  progress: number
  episodes: number
  importedEpisodes: number
  skippedEpisodes: number
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
