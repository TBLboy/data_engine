import type {
  Account,
  AuditRecord,
  BatchSummary,
  BugReport,
  BugReportListPayload,
  DatasetBatchRow,
  DatasetEpisodeListPayload,
  DatasetTaskSummary,
  DataAssetBatchListPayload,
  DataAssetSummary,
  DataAssetTaskDetail,
  DataAssetTaskListPayload,
  DispatchPreview,
  EpisodeRow,
  HistoryExportPayload,
  HistoryReportPayload,
  IngestJob,
  L3V2Report,
  ManualQcMedia,
  ManualQcSubmitResponse,
  QcRevision,
  QcTask,
  ReviewLock,
  ReasonStat,
  ReviewerDashboardPayload,
  ReviewerWorkload,
  TaskType,
  TaskTypeDetailPayload,
  UserProfile,
  AiExplainRequest,
  AiExplainResponse,
  AiChatRequest,
  AiChatResponse,
  AiConversationDetail,
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
  dispatchPreviews: DispatchPreview[]
  reasonStats: ReasonStat[]
  reviewerWorkloads: ReviewerWorkload[]
  reviewerAccounts: UserProfile[]
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

export interface DataAssetBatchQuery {
  page?: number
  pageSize?: number
  keyword?: string
  taskTypeId?: string
  batchDecision?: string
  qcStatus?: string
}

export interface DataAssetTaskQuery {
  page?: number
  pageSize?: number
  keyword?: string
  taskTypeId?: string
  includeInactive?: boolean
  staleOnly?: boolean
  sortBy?: string
  sortOrder?: string
}

export interface IngestScanRequest {
  bucket: string
  scope: string
}

export interface TaskTypeCreateRequest {
  name: string
  description?: string
  armMode?: 'both_arms' | 'left_arm' | 'right_arm'
}

export interface TaskTypeUpdateRequest {
  name: string
  description?: string
  armMode?: 'both_arms' | 'left_arm' | 'right_arm'
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
  reviewerAccounts: UserProfile[]
}

export interface HistoryPayload {
  auditRecords: AuditRecord[]
  auditTotal: number
  qcRevisions: QcRevision[]
  revisionTotal: number
  episodes: EpisodeRow[]
  batches: BatchSummary[]
}

export interface ManualQcContext {
  episode: EpisodeRow
  l3V2: L3V2Report | null
  revisions: QcRevision[]
  reviewLock: ReviewLock
  media: ManualQcMedia[]
  taskStatus: string | null
  viewMode: 'active' | 'history'
  canClaim: boolean
  canSubmit: boolean
}

export interface ReviewerCurrentTasksPayload {
  items: QcTask[]
  total: number
  page: number
  pageSize: number
}

export interface ReviewerHistoryTaskItem {
  episodeId: string
  batchId: string
  batchName: string
  taskName: string
  result: string
  primaryReason: string
  revisionNo: number
  operator: string
  time: string
  note: string
  currentTaskStatus: string | null
  currentTaskAssignee: string | null
  hasPendingRequest: boolean
}

export interface ReviewerHistoryTasksPayload {
  items: ReviewerHistoryTaskItem[]
  total: number
  page: number
  pageSize: number
}

export interface RereviewRequestItem {
  id: string
  episodeId: string
  batchId: string
  batchName: string
  taskId: string
  requesterUserId: string
  requesterName: string
  reason: string
  status: string
  approverUserId: string | null
  approverName: string | null
  decisionNote: string
  createdAt: string
  decidedAt: string | null
}

export interface RereviewRequestListPayload {
  items: RereviewRequestItem[]
  total: number
  page: number
  pageSize: number
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

export interface BatchDispatchAssignReviewer {
  reviewerId: string
  count: number
}

export interface BatchDispatchAssignRequest {
  mode: 'even' | 'custom_counts'
  reviewerIds: string[]
  reviewers: BatchDispatchAssignReviewer[]
}

export interface ManualQcSubmitRequest {
  result: 'pass' | 'fail'
  primaryReason: string
  note: string
  version: number
}

export interface CreateBugReportRequest {
  description: string
  imageFiles?: File[]
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

export async function fetchDataAssetSummary() {
  return request<DataAssetSummary>('/data-assets/summary')
}

export async function fetchDataAssetBatches(query: DataAssetBatchQuery = {}) {
  const params = new URLSearchParams()
  if (query.page) params.set('page', String(query.page))
  if (query.pageSize) params.set('page_size', String(query.pageSize))
  if (query.keyword) params.set('keyword', query.keyword)
  if (query.taskTypeId) params.set('task_type_id', query.taskTypeId)
  if (query.batchDecision) params.set('batch_decision', query.batchDecision)
  if (query.qcStatus) params.set('qc_status', query.qcStatus)
  const suffix = params.size ? `?${params.toString()}` : ''
  return request<DataAssetBatchListPayload>(`/data-assets/batches${suffix}`)
}

export async function fetchDataAssetTasks(query: DataAssetTaskQuery = {}) {
  const params = new URLSearchParams()
  if (query.page) params.set('page', String(query.page))
  if (query.pageSize) params.set('page_size', String(query.pageSize))
  if (query.keyword) params.set('keyword', query.keyword)
  if (query.taskTypeId) params.set('task_type_id', query.taskTypeId)
  if (query.includeInactive) params.set('include_inactive', 'true')
  if (query.staleOnly) params.set('stale_only', 'true')
  if (query.sortBy) params.set('sort_by', query.sortBy)
  if (query.sortOrder) params.set('sort_order', query.sortOrder)
  const suffix = params.size ? `?${params.toString()}` : ''
  return request<DataAssetTaskListPayload>(`/data-assets/tasks${suffix}`)
}

export async function fetchDataAssetTaskDetail(taskTypeId: string) {
  return request<DataAssetTaskDetail>(`/data-assets/tasks/${encodeURIComponent(taskTypeId)}`)
}

export async function rebuildDataAssets(scope: 'batch' | 'task' | 'all' = 'all') {
  return request<{ success: boolean; scope: string; rebuiltBatchCount: number; rebuiltTaskCount: number }>(`/data-assets/rebuild?scope=${scope}`, {
    method: 'POST'
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

export async function fetchReviewerDashboard() {
  return request<ReviewerDashboardPayload>('/reviewer/dashboard')
}

export async function fetchTaskPool() {
  return request<TaskPoolPayload>('/task-pool')
}

export async function fetchReviewerCurrentTasks(page = 1, pageSize = 10) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  return request<ReviewerCurrentTasksPayload>(`/reviewer/tasks/current?${params.toString()}`)
}

export async function fetchReviewerHistoryTasks(page = 1, pageSize = 10) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  return request<ReviewerHistoryTasksPayload>(`/reviewer/tasks/history?${params.toString()}`)
}

export async function createRereviewRequest(episodeId: string, reason: string) {
  return request<RereviewRequestItem>(`/qc/episodes/${episodeId}/rereview-request`, {
    method: 'POST',
    body: JSON.stringify({ reason })
  })
}

export async function fetchRereviewRequests(page = 1, pageSize = 20, statusFilter = 'pending') {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize), status: statusFilter })
  return request<RereviewRequestListPayload>(`/admin/rereview-requests?${params.toString()}`)
}

export async function approveRereviewRequest(requestId: string, note = '') {
  return request<RereviewRequestItem>(`/admin/rereview-requests/${requestId}/approve`, {
    method: 'POST',
    body: JSON.stringify({ note })
  })
}

export async function rejectRereviewRequest(requestId: string, note = '') {
  return request<RereviewRequestItem>(`/admin/rereview-requests/${requestId}/reject`, {
    method: 'POST',
    body: JSON.stringify({ note })
  })
}

export async function fetchHistory(
  revisionPage = 1, revisionPageSize = 20,
  auditPage = 1, auditPageSize = 50
) {
  const params = new URLSearchParams({
    revision_page: String(revisionPage),
    revision_page_size: String(revisionPageSize),
    audit_page: String(auditPage),
    audit_page_size: String(auditPageSize),
  })
  return request<HistoryPayload>(`/qc-history?${params.toString()}`)
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

export async function assignBatchTasks(batchId: string, payload: BatchDispatchAssignRequest) {
  return request<DispatchPreview>(`/qc/batches/${batchId}/dispatch-assign`, {
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
  return request<ManualQcSubmitResponse>(`/qc/manual/${episodeId}`, {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export async function createBugReport(payload: CreateBugReportRequest) {
  const formData = new FormData()
  formData.set('description', payload.description)
  if (payload.imageFiles?.length) {
    for (const file of payload.imageFiles) formData.append('images', file)
  }
  return request<BugReport>('/bug-reports', {
    method: 'POST',
    body: formData
  })
}

export async function fetchBugReports() {
  return request<BugReportListPayload>('/bug-reports')
}

export async function updateBugReportStatus(reportId: string, status: BugReport['status']) {
  return request<BugReport>(`/bug-reports/${reportId}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status })
  })
}

export async function deleteBugReport(reportId: string) {
  return request<void>(`/bug-reports/${reportId}`, {
    method: 'DELETE'
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

// Telemetry curve data
export interface TelemetryCurve {
  timestamps: number[]
  armDims: number; handDims: number
  armLeftDof: number; armRightDof: number
  handLeftDof: number; handRightDof: number
  qposArm: number[][]; qposHand: number[][]
  actionsArm: number[][]; actionsHand: number[][]
  qvelArm: number[][]; qvelHand: number[][]
  effortArm: number[][]; effortHand: number[][]
}

export async function fetchTelemetryCurve(episodeId: string) {
  return request<TelemetryCurve>(`/episodes/${episodeId}/telemetry-curve`)
}

// L3 v2 parameters
export type L3V2Params = Record<string, number>

export async function fetchL3V2Params() {
  return request<L3V2Params>('/admin/l3-v2-params')
}

export async function updateL3V2Params(params: L3V2Params) {
  return request<{ success: boolean; message: string }>('/admin/l3-v2-params', {
    method: 'PUT',
    body: JSON.stringify(params)
  })
}

// General configuration
export type GeneralConfig = Record<string, number | string>

export async function fetchGeneralConfig() {
  return request<GeneralConfig>('/admin/general-config')
}

export async function updateGeneralConfig(params: GeneralConfig) {
  return request<{ success: boolean; message: string }>('/admin/general-config', {
    method: 'PUT',
    body: JSON.stringify(params)
  })
}

// Dataset management
export async function fetchDatasetTasks() {
  return request<TaskType[]>('/dataset/tasks')
}

export async function fetchDatasetTaskSummary(taskTypeId: string) {
  return request<DatasetTaskSummary>(`/dataset/tasks/${taskTypeId}/summary`)
}

export async function fetchDatasetTaskBatches(taskTypeId: string) {
  return request<DatasetBatchRow[]>(`/dataset/tasks/${taskTypeId}/batches`)
}

export async function recomputeTaskBatchDecisions(taskTypeId: string) {
  return request<{
    success: boolean
    taskTypeId: string
    taskName: string
    refreshedBatchCount: number
    acceptedBatchCount: number
    rejectedBatchCount: number
    pendingBatchCount: number
  }>(`/dataset/tasks/${taskTypeId}/recompute-decisions`, {
    method: 'POST'
  })
}

export async function fetchDatasetTaskEpisodes(
  taskTypeId: string,
  params: {
    status?: string
    batchId?: string
    finalDecisionSource?: string
    manualQcStatus?: string
    page?: number
    pageSize?: number
  } = {}
) {
  const searchParams = new URLSearchParams()
  if (params.status) searchParams.set('status', params.status)
  if (params.batchId) searchParams.set('batch_id', params.batchId)
  if (params.finalDecisionSource) searchParams.set('final_decision_source', params.finalDecisionSource)
  if (params.manualQcStatus) searchParams.set('manual_qc_status', params.manualQcStatus)
  if (params.page) searchParams.set('page', String(params.page))
  if (params.pageSize) searchParams.set('page_size', String(params.pageSize))
  const qs = searchParams.toString()
  return request<DatasetEpisodeListPayload>(`/dataset/tasks/${taskTypeId}/episodes${qs ? `?${qs}` : ''}`)
}

export function datasetExportUrl(taskTypeId: string) {
  return `${API_BASE}/dataset/tasks/${taskTypeId}/exports`
}

export async function exportDatasetEpisodes(taskTypeId: string, format: string = 'csv', batchIds?: string[]) {
  const body: Record<string, unknown> = { format }
  if (batchIds && batchIds.length) {
    body.batchIds = batchIds
  }
  const response = await fetch(datasetExportUrl(taskTypeId), {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
  if (!response.ok) {
    throw new ApiError(response.status, await response.text())
  }
  return response
}

export async function recomputeBatchDecision(batchId: string) {
  return request<{ success: boolean; batchDecision: string; failureRate: number; reason: string }>(
    `/batches/${batchId}/recompute-decision`,
    { method: 'POST' }
  )
}

// v1.2: Export history
export async function fetchExportHistory(taskTypeId?: string) {
  const qs = taskTypeId ? `?task_type_id=${taskTypeId}` : ''
  return request<import('../types/qc').DatasetExportJob[]>(`/dataset/exports${qs}`)
}

// v1.2: Reviewer task manager
export async function fetchReviewerTasks(reviewerId: string, reviewerName?: string, status?: string) {
  const params = new URLSearchParams()
  if (reviewerName) params.set('name', reviewerName)
  if (status) params.set('status', status)
  const qs = params.toString()
  return request<import('../types/qc').ReviewerTask[]>(`/admin/reviewers/${reviewerId}/tasks${qs ? `?${qs}` : ''}`)
}

export async function revokeTask(taskId: string, reason: string = '') {
  return request<{ success: boolean }>(`/admin/qc-tasks/${taskId}/revoke`, {
    method: 'POST',
    body: JSON.stringify({ reason })
  })
}

export async function reassignTask(taskId: string, toReviewerId: string, reason: string = '') {
  return request<{ success: boolean }>(`/admin/qc-tasks/${taskId}/reassign`, {
    method: 'POST',
    body: JSON.stringify({ toReviewerId, reason })
  })
}

export async function releaseTask(taskId: string, reason: string = '') {
  return request<{ success: boolean }>(`/admin/qc-tasks/${taskId}/release`, {
    method: 'POST',
    body: JSON.stringify({ reason })
  })
}

export async function bulkRevokeTasks(taskIds: string[], reason: string = '') {
  return request<{ success: boolean; results: any[] }>('/admin/qc-tasks/bulk-revoke', {
    method: 'POST',
    body: JSON.stringify({ taskIds, reason })
  })
}

export async function bulkReassignTasks(taskIds: string[], toReviewerId: string, reason: string = '') {
  return request<{ success: boolean; results: any[] }>('/admin/qc-tasks/bulk-reassign', {
    method: 'POST',
    body: JSON.stringify({ taskIds, toReviewerId, reason })
  })
}

export async function fetchAiExplain(payload: AiExplainRequest) {
  return request<AiExplainResponse>('/ai/explain', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

// AI Assistant Phase 1
export async function fetchOrCreateConversation(episodeId: string, title?: string) {
  return request<AiConversationDetail>('/ai-assistant/conversations', {
    method: 'POST',
    body: JSON.stringify({ episodeId, title })
  })
}

export async function fetchConversationMessages(conversationId: string) {
  return request<AiConversationDetail>(`/ai-assistant/conversations/${conversationId}/messages`)
}

export async function postChatMessage(payload: AiChatRequest) {
  return request<AiChatResponse>('/ai-assistant/chat', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

/** 快速检测 AI 模型服务是否可达 */
export async function checkAiHealth() {
  return request<{ ok: boolean; detail?: string; models?: number }>('/ai-assistant/health')
}

/** SSE 流式 chat，返回 async generator。每个 yield 是一个 SSE 事件 { event, data } */
export async function* postChatStream(payload: AiChatRequest) {
  const resp = await fetch(`${API_BASE}/ai-assistant/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!resp.ok) {
    throw new ApiError(resp.status, await resp.text())
  }

  const reader = resp.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      let eventType = ''
      let eventData = ''

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          eventData = line.slice(6)
        } else if (line === '' && eventType) {
          // 空行 = 事件结束
          try {
            yield { event: eventType, data: JSON.parse(eventData) }
          } catch {
            yield { event: eventType, data: eventData }
          }
          eventType = ''
          eventData = ''
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

// --- notifications ---

export interface NotificationCounts {
    bugCount: number
    rereviewCount: number
}

export function fetchNotifications(): Promise<NotificationCounts> {
    return request<NotificationCounts>('/notifications')
}
