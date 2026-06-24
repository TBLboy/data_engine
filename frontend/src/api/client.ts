import type {
  Account,
  AuditRecord,
  BatchSummary,
  DispatchPreview,
  EpisodeRow,
  HistoryExportPayload,
  HistoryReportPayload,
  IngestJob,
  ManualQcMedia,
  MetricCard,
  QcRevision,
  QcTask,
  ReviewLock,
  ReasonStat,
  ReviewerWorkload,
  TaskType,
  TaskTypeDetailPayload,
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
  totalEpisodes: number
  page: number
  pageSize: number
}

export interface DatabaseQuery {
  page?: number
  pageSize?: number
  keyword?: string
  batchId?: string
  qcStatus?: string
  qcResult?: string
}

export interface IngestScanRequest {
  bucket: string
  scope: string
}

export interface TaskTypeCreateRequest {
  name: string
  description?: string
}

export interface TaskTypeUpdateRequest {
  name: string
  description?: string
}

export interface TaskTypeBatchOperationRequest {
  batchIds: string[]
}

export interface TaskTypeDetailResponse extends TaskTypeDetailPayload {}

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
  media: ManualQcMedia[]
}

export interface ManualQcMediaRefreshRequest {
  objectIds: string[]
}

export interface ManualQcMediaRefreshItem {
  objectId: string
  previewUrl: string
  previewExpiresAt: string | null
  refreshable: boolean
}

export interface ManualQcMediaRefreshResponse {
  media: ManualQcMediaRefreshItem[]
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

export async function fetchDatabase(query: DatabaseQuery = {}) {
  const params = new URLSearchParams()
  if (query.page) params.set('page', String(query.page))
  if (query.pageSize) params.set('page_size', String(query.pageSize))
  if (query.keyword) params.set('keyword', query.keyword)
  if (query.batchId) params.set('batch_id', query.batchId)
  if (query.qcStatus) params.set('qc_status', query.qcStatus)
  if (query.qcResult) params.set('qc_result', query.qcResult)
  const suffix = params.size ? `?${params.toString()}` : ''
  return request<DatabasePayload>(`/database${suffix}`)
}

export async function scanDatabase(payload: IngestScanRequest) {
  return request<IngestJob>('/database/scan', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export async function fetchTaskTypes() {
  return request<TaskType[]>('/task-types')
}

export async function createTaskType(payload: TaskTypeCreateRequest) {
  return request<TaskType>('/task-types', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export async function updateTaskType(taskTypeId: string, payload: TaskTypeUpdateRequest) {
  return request<TaskType>(`/task-types/${taskTypeId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  })
}

export async function deleteTaskType(taskTypeId: string) {
  return request<TaskType>(`/task-types/${taskTypeId}`, {
    method: 'DELETE'
  })
}

export async function fetchTaskTypeDetail(taskTypeId: string) {
  return request<TaskTypeDetailResponse>(`/task-types/${taskTypeId}/batches`)
}

export async function fetchBatchesByTaskType(taskTypeId = 'task_type:unclassified') {
  const params = new URLSearchParams({ task_type_id: taskTypeId })
  return request<BatchSummary[]>(`/batches?${params.toString()}`)
}

export async function attachBatchesToTaskType(taskTypeId: string, payload: TaskTypeBatchOperationRequest) {
  return request<TaskTypeDetailResponse>(`/task-types/${taskTypeId}/batches:attach`, {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export async function detachBatchFromTaskType(taskTypeId: string, batchId: string) {
  return request<TaskTypeDetailResponse>(`/task-types/${taskTypeId}/batches/${batchId}:detach`, {
    method: 'POST'
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

export async function refreshManualQcMedia(episodeId: string, payload: ManualQcMediaRefreshRequest) {
  return request<ManualQcMediaRefreshResponse>(`/episodes/${episodeId}/media/refresh`, {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export async function downloadManualQcObject(episodeId: string, objectId: string) {
  const response = await fetch(`${API_BASE}/episodes/${episodeId}/objects/${objectId}/download`, {
    credentials: 'include'
  })
  if (!response.ok) {
    const message = await response.text()
    throw new ApiError(response.status, message || `Request failed: ${response.status}`)
  }
  return response.blob()
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
