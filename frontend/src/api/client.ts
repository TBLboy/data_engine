import type {
  Account,
  AuditRecord,
  BatchSummary,
  DispatchPreview,
  EpisodeRow,
  HistoryExportPayload,
  HistoryReportPayload,
  IngestJob,
  MetricCard,
  QcRevision,
  QcTask,
  ReviewLock,
  ReasonStat,
  ReviewerWorkload,
  TaskType,
  TimelineSegment,
  UserProfile
} from '../types/qc'

const API_BASE = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') || '/api'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers ?? undefined)

  if (init?.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    ...init,
    headers
  })

  if (!response.ok) {
    const message = await response.text()
    throw new ApiError(response.status, message || `Request failed: ${response.status}`)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

export interface SessionPayload {
  user: UserProfile
}

export interface AccountListPayload {
  accounts: Account[]
}

export interface CreateAccountRequest {
  username: string
  name: string
  password: string
  role: 'admin' | 'qc_manager' | 'reviewer' | 'viewer'
}

export interface ResetPasswordRequest {
  password: string
}

export interface UpdateAccountStatusRequest {
  isActive: boolean
}

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  user: UserProfile
  session: SessionPayload
}

export interface DashboardPayload {
  currentUser: UserProfile
  taskTypes: TaskType[]
  batches: BatchSummary[]
  qcTasks: QcTask[]
  reasonStats: ReasonStat[]
  reviewerWorkloads: ReviewerWorkload[]
  ingestJobs: IngestJob[]
}

export interface DatabasePayload {
  episodes: EpisodeRow[]
  batches: BatchSummary[]
  taskTypes: TaskType[]
  reasonStats: ReasonStat[]
  ingestJobs: IngestJob[]
}

export interface IngestScanRequest {
  bucket: string
  scope: string
}

export interface TaskPoolPayload {
  batches: BatchSummary[]
  dispatchPreviews: DispatchPreview[]
  qcTasks: QcTask[]
  reviewerWorkloads: ReviewerWorkload[]
}

export interface HistoryPayload {
  auditRecords: AuditRecord[]
  qcRevisions: QcRevision[]
  episodes: EpisodeRow[]
  batches: BatchSummary[]
}

export interface ManualQcContext {
  episode: EpisodeRow
  metrics: MetricCard[]
  timelineSegments: TimelineSegment[]
  revisions: QcRevision[]
  reviewLock: ReviewLock
}

export interface ManualQcClaimResponse {
  status: 'claimed' | 'released'
  reviewLock: ReviewLock
}

export interface HomePayload {
  dashboard: DashboardPayload
  database: DatabasePayload
  taskPool: TaskPoolPayload
  history: HistoryPayload
}

export interface DispatchPlanRequest {
  dispatchMode: 'sampled' | 'full'
  samplingRatio: number
  note: string
}

export interface ManualQcSubmitRequest {
  result: 'pass' | 'fail'
  primaryReason: string
  note: string
  version: number
}

export async function login(payload: LoginRequest) {
  return request<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export async function logout() {
  return request<void>('/auth/logout', {
    method: 'POST'
  })
}

export async function fetchSession() {
  return request<SessionPayload>('/auth/session')
}

export async function fetchAccounts() {
  return request<AccountListPayload>('/accounts')
}

export async function createAccount(payload: CreateAccountRequest) {
  return request<Account>('/accounts', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export async function resetAccountPassword(userId: string, payload: ResetPasswordRequest) {
  return request<Account>(`/accounts/${userId}/reset-password`, {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export async function updateAccountStatus(userId: string, payload: UpdateAccountStatusRequest) {
  return request<Account>(`/accounts/${userId}/status`, {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export async function fetchBootstrap() {
  return request<HomePayload>('/bootstrap')
}

export async function fetchDashboard() {
  return request<DashboardPayload>('/dashboard')
}

export async function fetchDatabase() {
  return request<DatabasePayload>('/database')
}

export async function scanDatabase(payload: IngestScanRequest) {
  return request<IngestJob>('/database/scan', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export async function fetchTaskPool() {
  return request<TaskPoolPayload>('/task-pool')
}

export async function fetchHistory() {
  return request<HistoryPayload>('/qc-history')
}

export async function fetchHistoryReport(batchId = 'all') {
  const params = new URLSearchParams({ batch_id: batchId })
  return request<HistoryReportPayload>(`/qc-history/report?${params.toString()}`)
}

export async function fetchHistoryExport(batchId = 'all', scope: 'report' | 'episodes' | 'audits' = 'report') {
  const params = new URLSearchParams({ batch_id: batchId, scope })
  return request<HistoryExportPayload>(`/qc-history/export?${params.toString()}`)
}

export async function fetchManualQcContext(episodeId: string) {
  return request<ManualQcContext>(`/episodes/${episodeId}/qc-context`)
}

export async function fetchDispatchPreview(batchId: string) {
  return request<DispatchPreview>(`/qc/batches/${batchId}/dispatch-preview`)
}

export async function submitDispatchPlan(batchId: string, payload: DispatchPlanRequest) {
  return request<DispatchPreview>(`/qc/batches/${batchId}/dispatch-plan`, {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export async function assignTask(taskId: string, assignee: string) {
  return request<QcTask>(`/qc/tasks/${taskId}/assign`, {
    method: 'POST',
    body: JSON.stringify({ assignee })
  })
}

export async function submitManualQc(episodeId: string, payload: ManualQcSubmitRequest) {
  return request<{ status: string }>(`/qc/manual/${episodeId}`, {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export async function claimManualQc(episodeId: string) {
  return request<ManualQcClaimResponse>(`/qc/manual/${episodeId}/claim`, {
    method: 'POST'
  })
}

export async function releaseManualQc(episodeId: string) {
  return request<ManualQcClaimResponse>(`/qc/manual/${episodeId}/release`, {
    method: 'POST'
  })
}
