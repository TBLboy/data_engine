<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '../components/AppLayout.vue'
import {
  acquireAnnotationLock,
  assignAnnotationTask,
  claimAnnotationTask,
  completeAnnotationTask,
  createAnnotationSchema,
  ensureAnnotationTasks,
  fetchAccounts,
  fetchAnnotationEligibility,
  fetchAnnotationSchemas,
  fetchAnnotationStatistics,
  fetchAnnotationTask,
  fetchAnnotationTasks,
  fetchDatasetTasks,
  fetchManualQcContext,
  publishAnnotationSchema,
  releaseAnnotationLock,
  saveAnnotationDraft,
  setAnnotationPublicClaim,
  type AnnotationDraftRequest,
} from '../api/client'
import type {
  AnnotationDraft,
  AnnotationEligibility,
  AnnotationSchema,
  AnnotationStatistics,
  AnnotationTask,
  AnnotationTaskOutcome,
  Account,
  SubGoalInstanceStatus,
  TaskType,
} from '../types/qc'
import { useSessionStore } from '../stores/session'

const session = useSessionStore()
const tasks = ref<AnnotationTask[]>([])
const selectedTaskId = ref('')
const selectedTask = ref<AnnotationTask | null>(null)
const mediaUrl = ref('')
const loading = ref(true)
const detailLoading = ref(false)
const saving = ref(false)
const completing = ref(false)
const error = ref('')
const page = ref(1)
const total = ref(0)
const pageSize = 20
const filterStatus = ref('')
const dirty = ref(false)
const hydratingDraft = ref(false)
const operationLoading = ref(false)
const operationTaskTypeId = ref('')
const taskTypes = ref<TaskType[]>([])
const reviewers = ref<Account[]>([])
const eligibility = ref<AnnotationEligibility | null>(null)
const statistics = ref<AnnotationStatistics | null>(null)
const schemas = ref<AnnotationSchema[]>([])
const ensureLimit = ref(100)
const selectedReviewerId = ref('')
const assignmentNote = ref('')
const schemaDialogVisible = ref(false)
const schemaDefinitionsJson = ref('[\n  {\n    "sequenceNo": 1,\n    "code": "sub_goal",\n    "nameEn": "Sub goal",\n    "nameZh": "子目标",\n    "description": "",\n    "actionVerb": "",\n    "isRequired": true,\n    "isConditional": false,\n    "maxOccurrences": 1,\n    "objectRoleHints": {}\n  }\n]')
let lockTimer: number | null = null

const outcomes: Array<{ value: AnnotationTaskOutcome; label: string }> = [
  { value: 'completed_normally', label: '正常完成' },
  { value: 'completed_with_retry', label: '重试后完成' },
  { value: 'partially_completed', label: '部分完成' },
  { value: 'failed', label: '失败' },
  { value: 'uncertain', label: '无法确定' },
]
const instanceStatuses: Array<{ value: SubGoalInstanceStatus; label: string }> = [
  { value: 'observed', label: '已观察' },
  { value: 'failed', label: '失败' },
  { value: 'skipped', label: '跳过' },
  { value: 'not_observed', label: '未观察到' },
  { value: 'not_applicable', label: '不适用' },
  { value: 'uncertain', label: '不确定' },
]

const blankDraft = (): AnnotationDraft => ({
  canonicalInstructionEn: '',
  canonicalInstructionZh: '',
  instructionVariantsEn: [],
  episodeSummary: '',
  objects: [],
  taskOutcome: null,
  failureSubGoalInstanceId: null,
  lastSuccessfulSubGoalInstanceId: null,
  failureReason: '',
  annotationNotes: '',
  annotationSchemaVersion: '1.0',
  occurrences: [],
})

const draft = reactive<AnnotationDraft>(blankDraft())
const hasLock = computed(() => {
  if (!selectedTask.value) return false
  return selectedTask.value.lockOwner === session.user?.id
})
const canEdit = computed(() => {
  if (!selectedTask.value) return false
  if (!['admin', 'qc_manager', 'reviewer'].includes(session.user?.role ?? '')) return false
  return session.user?.role !== 'reviewer' || hasLock.value
})
const selectedSchema = computed(() => selectedTask.value?.schema)
const isManager = computed(() => ['admin', 'qc_manager'].includes(session.user?.role ?? ''))
const reviewerWorkload = computed(() => new Map(statistics.value?.byReviewer.map((item) => [item.reviewerId, item.count]) ?? []))
const requiredCount = computed(() => selectedSchema.value?.definitions.filter((item) => item.isRequired && !item.isConditional).length ?? 0)
const observedRequiredCount = computed(() => {
  const definitionIds = new Set(draft.occurrences.map((item) => item.definitionId))
  return selectedSchema.value?.definitions.filter((item) => item.isRequired && !item.isConditional && definitionIds.has(item.id ?? '')).length ?? 0
})

watch(draft, () => { if (!hydratingDraft.value) dirty.value = true }, { deep: true })

function copyDraft(source: AnnotationDraft | null): void {
  hydratingDraft.value = true
  const value = source ?? blankDraft()
  draft.canonicalInstructionEn = value.canonicalInstructionEn ?? ''
  draft.canonicalInstructionZh = value.canonicalInstructionZh ?? ''
  draft.instructionVariantsEn = [...(value.instructionVariantsEn ?? [])]
  draft.episodeSummary = value.episodeSummary ?? ''
  draft.objects = [...(value.objects ?? [])]
  draft.taskOutcome = value.taskOutcome
  draft.failureSubGoalInstanceId = value.failureSubGoalInstanceId
  draft.lastSuccessfulSubGoalInstanceId = value.lastSuccessfulSubGoalInstanceId
  draft.failureReason = value.failureReason ?? ''
  draft.annotationNotes = value.annotationNotes ?? ''
  draft.annotationSchemaVersion = value.annotationSchemaVersion || '1.0'
  draft.occurrences = (value.occurrences ?? []).map((item) => ({ ...item }))
  dirty.value = false
  void nextTick(() => { hydratingDraft.value = false })
}

async function loadTasks(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const result = await fetchAnnotationTasks({
      page: page.value,
      pageSize,
      workStatus: filterStatus.value || undefined,
      taskTypeId: isManager.value ? operationTaskTypeId.value || undefined : undefined,
    })
    tasks.value = result.items
    total.value = result.total
    if (!selectedTaskId.value && tasks.value.length) selectedTaskId.value = tasks.value[0].id
    if (selectedTaskId.value && !tasks.value.some((item) => item.id === selectedTaskId.value)) {
      selectedTaskId.value = tasks.value[0]?.id ?? ''
    }
    if (selectedTaskId.value) await openTask(selectedTaskId.value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载标注任务失败'
  } finally {
    loading.value = false
  }
}

async function refreshOperations(): Promise<void> {
  if (!isManager.value || !operationTaskTypeId.value) return
  operationLoading.value = true
  try {
    const [nextEligibility, nextStatistics, nextSchemas] = await Promise.all([
      fetchAnnotationEligibility(operationTaskTypeId.value),
      fetchAnnotationStatistics(operationTaskTypeId.value),
      fetchAnnotationSchemas(operationTaskTypeId.value),
    ])
    eligibility.value = nextEligibility
    statistics.value = nextStatistics
    schemas.value = nextSchemas
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载标注运营数据失败'
  } finally {
    operationLoading.value = false
  }
}

async function loadOperations(): Promise<void> {
  if (!isManager.value) return
  try {
    const [nextTaskTypes, accounts] = await Promise.all([fetchDatasetTasks(), fetchAccounts()])
    taskTypes.value = nextTaskTypes
    reviewers.value = accounts.accounts.filter((account) => account.role === 'reviewer' && account.isActive)
    const taskTypeChanged = !operationTaskTypeId.value
    if (taskTypeChanged) operationTaskTypeId.value = selectedTask.value?.taskTypeId || nextTaskTypes[0]?.id || ''
    if (taskTypeChanged) await changeOperationTaskType()
    else await refreshOperations()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载标注运营配置失败'
  }
}

async function changeOperationTaskType(): Promise<void> {
  page.value = 1
  selectedTaskId.value = ''
  await Promise.all([refreshOperations(), loadTasks()])
}

async function ensureMissingTasks(): Promise<void> {
  if (!operationTaskTypeId.value) return
  operationLoading.value = true
  try {
    const result = await ensureAnnotationTasks({ taskTypeId: operationTaskTypeId.value, limit: ensureLimit.value })
    ElMessage.success(result.createdCount ? `已创建 ${result.createdCount} 个标注任务` : '当前范围没有缺失标注任务')
    await Promise.all([refreshOperations(), loadTasks()])
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '补漏创建标注任务失败')
  } finally {
    operationLoading.value = false
  }
}

async function assignSelectedTask(): Promise<void> {
  if (!selectedTask.value || !selectedReviewerId.value) return
  try {
    const updated = await assignAnnotationTask(selectedTask.value.id, selectedReviewerId.value, assignmentNote.value)
    selectedTask.value = updated
    tasks.value = tasks.value.map((item) => item.id === updated.id ? updated : item)
    assignmentNote.value = ''
    ElMessage.success('标注任务已分配')
    await refreshOperations()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '分配标注任务失败')
  }
}

async function toggleSelectedPublicClaim(): Promise<void> {
  if (!selectedTask.value) return
  try {
    const updated = await setAnnotationPublicClaim(selectedTask.value.id, !selectedTask.value.publicClaimEnabled)
    selectedTask.value = updated
    tasks.value = tasks.value.map((item) => item.id === updated.id ? updated : item)
    ElMessage.success(updated.publicClaimEnabled ? '已开放公共领取' : '已关闭公共领取')
    await refreshOperations()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '设置公共领取失败')
  }
}

async function createSchema(): Promise<void> {
  if (!operationTaskTypeId.value) return
  let definitions: AnnotationSchema['definitions']
  try {
    definitions = JSON.parse(schemaDefinitionsJson.value) as AnnotationSchema['definitions']
    if (!Array.isArray(definitions)) throw new Error('Schema 必须是 Definition 数组')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : 'Schema JSON 格式无效')
    return
  }
  try {
    const schema = await createAnnotationSchema({
      taskTypeId: operationTaskTypeId.value,
      definitions: definitions.map(({ id: _id, ...definition }) => definition),
    })
    schemaDialogVisible.value = false
    ElMessage.success(`已创建 Schema v${schema.versionNo} 草稿`)
    await refreshOperations()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '创建 Schema 失败')
  }
}

async function publishSchema(schema: AnnotationSchema): Promise<void> {
  try {
    await ElMessageBox.confirm(`发布 v${schema.versionNo} 会退休该 TaskType 当前 published Schema，是否继续？`, '发布 Schema', { type: 'warning' })
    await publishAnnotationSchema(schema.id)
    ElMessage.success(`Schema v${schema.versionNo} 已发布`)
    await refreshOperations()
  } catch (err) {
    if (err !== 'cancel') ElMessage.error(err instanceof Error ? err.message : '发布 Schema 失败')
  }
}

async function openTask(taskId: string): Promise<void> {
  selectedTaskId.value = taskId
  detailLoading.value = true
  error.value = ''
  try {
    let task = await fetchAnnotationTask(taskId)
    if (session.user?.role === 'reviewer' && !task.assignedTo) {
      task = await claimAnnotationTask(taskId)
    }
    selectedTask.value = task
    copyDraft(task.draft)
    mediaUrl.value = ''
    try {
      const context = await fetchManualQcContext(task.episodeId)
      mediaUrl.value = context.media.find((item) => item.variant === 'rgb')?.previewUrl || context.media[0]?.previewUrl || ''
    } catch {
      // Annotation remains usable when the optional media preview is unavailable.
    }
    if (session.user?.role !== 'viewer' && task.workStatus !== 'completed') await lockTask()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载标注任务详情失败'
  } finally {
    detailLoading.value = false
  }
}

async function lockTask(): Promise<void> {
  if (!selectedTask.value || session.user?.role === 'viewer') return
  const result = await acquireAnnotationLock(selectedTask.value.id)
  selectedTask.value.lockOwner = result.lockOwner
  selectedTask.value.lockExpiresAt = result.lockExpiresAt
  selectedTask.value.rowVersion = result.rowVersion
  startLockRefresh()
}

function startLockRefresh(): void {
  if (lockTimer !== null) window.clearInterval(lockTimer)
  lockTimer = window.setInterval(async () => {
    if (!selectedTask.value || !hasLock.value) return
    try {
      await lockTask()
    } catch {
      // The save operation will surface an expired or stolen lock explicitly.
    }
  }, 180000)
}

async function unlockTask(): Promise<void> {
  if (!selectedTask.value || !hasLock.value) return
  await releaseAnnotationLock(selectedTask.value.id)
  selectedTask.value.lockOwner = null
  selectedTask.value.lockExpiresAt = null
  startLockRefresh()
}

function markDirty(): void {
  dirty.value = true
}

function addVariant(): void {
  if (draft.instructionVariantsEn.length < 5) draft.instructionVariantsEn.push('')
  markDirty()
}

function addOccurrence(definitionId: string): void {
  const nextNo = draft.occurrences.filter((item) => item.definitionId === definitionId).length + 1
  draft.occurrences.push({
    definitionId,
    occurrenceNo: nextNo,
    status: 'observed',
    startStep: 0,
    endStepExclusive: selectedTask.value?.frameCount || null,
    representativeStep: 0,
    failureReason: '',
    notes: '',
    source: 'human',
  })
  markDirty()
}

function removeOccurrence(index: number): void {
  const removed = draft.occurrences[index]
  draft.occurrences.splice(index, 1)
  if (removed) {
    const sameDefinition = draft.occurrences.filter((item) => item.definitionId === removed.definitionId)
    sameDefinition.forEach((item, itemIndex) => { item.occurrenceNo = itemIndex + 1 })
  }
  markDirty()
}

function definitionLabel(definitionId: string): string {
  const definition = selectedSchema.value?.definitions.find((item) => item.id === definitionId)
  return definition ? `${definition.sequenceNo}. ${definition.nameEn || definition.code}` : definitionId
}

function draftPayload(): AnnotationDraftRequest {
  if (!selectedTask.value) throw new Error('未选择标注任务')
  return {
    rowVersion: selectedTask.value.rowVersion,
    ...draft,
    instructionVariantsEn: draft.instructionVariantsEn.map((item) => item.trim()).filter(Boolean),
    objects: draft.objects,
    occurrences: draft.occurrences,
  }
}

async function saveDraft(showMessage = true): Promise<boolean> {
  if (!selectedTask.value) return false
  saving.value = true
  try {
    const updated = await saveAnnotationDraft(selectedTask.value.id, draftPayload())
    selectedTask.value = updated
    copyDraft(updated.draft)
    tasks.value = tasks.value.map((item) => item.id === updated.id ? updated : item)
    if (showMessage) ElMessage.success('标注草稿已保存')
    return true
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '保存标注草稿失败')
    return false
  } finally {
    saving.value = false
  }
}

async function completeTask(): Promise<void> {
  if (!selectedTask.value) return
  try {
    await ElMessageBox.confirm('完成后将生成不可变 revision，是否继续？', '提交标注', { type: 'warning' })
  } catch {
    return
  }
  completing.value = true
  try {
    if (dirty.value && !(await saveDraft(false))) return
    const result = await completeAnnotationTask(selectedTask.value.id)
    selectedTask.value = result.task
    copyDraft(result.task.draft)
    tasks.value = tasks.value.map((item) => item.id === result.task.id ? result.task : item)
    ElMessage.success(`标注已完成，revision #${result.revisionNo}`)
    await loadTasks()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '完成校验未通过')
  } finally {
    completing.value = false
  }
}

function statusType(status: string): 'success' | 'warning' | 'info' | 'danger' {
  if (status === 'completed') return 'success'
  if (status === 'in_progress') return 'primary' as 'info'
  if (status === 'assigned') return 'warning'
  if (status === 'invalidated') return 'danger'
  return 'info'
}

onMounted(async () => {
  await loadTasks()
  await loadOperations()
})
onBeforeUnmount(() => { if (lockTimer !== null) window.clearInterval(lockTimer) })
</script>

<template>
  <AppLayout>
    <div class="annotation-page">
      <section class="page-title-row annotation-hero">
        <div>
          <el-tag type="primary" effect="light">SUB GOAL ANNOTATION V1</el-tag>
          <h1>数据标注工作台</h1>
          <p>只处理 active scope 内已 QUALIFIED 的 Episode。Schema、occurrence 和 revision 均按服务端规则冻结与校验。</p>
        </div>
        <div class="annotation-hero-meta">
          <span>必需 Sub Goal</span>
          <strong>{{ observedRequiredCount }} / {{ requiredCount }}</strong>
          <small>{{ selectedTask?.taskTypeName || '未选择任务' }}</small>
        </div>
      </section>

      <el-alert v-if="error" type="error" :closable="false" :title="error" />

      <section v-if="isManager" class="annotation-operations" v-loading="operationLoading">
        <el-card shadow="never" class="qc-card operations-overview">
          <div class="operations-title">
            <div>
              <div class="eyebrow">ANNOTATION OPERATIONS</div>
              <h2>标注运营面</h2>
              <p>仅面向当前 TaskType 的 active-scope QUALIFIED 数据。补漏创建不会覆盖已有草稿或 revision。</p>
            </div>
            <el-select v-model="operationTaskTypeId" filterable class="operation-task-type" placeholder="选择 TaskType" @change="changeOperationTaskType">
              <el-option v-for="taskType in taskTypes" :key="taskType.id" :label="taskType.name" :value="taskType.id" />
            </el-select>
          </div>
          <div class="operations-metrics">
            <div><span>可标注</span><strong>{{ eligibility?.eligibleCount ?? '-' }}</strong><small>QUALIFIED active scope</small></div>
            <div><span>已建任务</span><strong>{{ eligibility?.taskCount ?? '-' }}</strong><small>含进行中与完成历史</small></div>
            <div><span>待补漏</span><strong>{{ eligibility?.unannotatedCount ?? '-' }}</strong><small>尚未创建 annotation task</small></div>
            <div><span>已完成</span><strong>{{ statistics?.completed ?? '-' }}</strong><small>完成率 {{ ((statistics?.completionRate ?? 0) * 100).toFixed(1) }}%</small></div>
          </div>
          <div class="operations-actions">
            <el-input-number v-model="ensureLimit" :min="1" :max="1000" controls-position="right" />
            <el-button type="primary" :disabled="!operationTaskTypeId" @click="ensureMissingTasks">补漏创建任务</el-button>
            <el-button @click="refreshOperations">刷新统计</el-button>
            <el-button plain @click="schemaDialogVisible = true">新建 Schema 草稿</el-button>
          </div>
          <div class="schema-list">
            <span class="schema-list-label">Schema 生命周期</span>
            <el-tag v-if="!schemas.length" type="info">暂无 Schema</el-tag>
            <span v-for="schema in schemas" :key="schema.id" class="schema-chip">
              <el-tag :type="schema.status === 'published' ? 'success' : schema.status === 'draft' ? 'warning' : 'info'">v{{ schema.versionNo }} · {{ schema.status }}</el-tag>
              <el-button v-if="schema.status === 'draft'" link type="primary" @click="publishSchema(schema)">发布</el-button>
            </span>
          </div>
        </el-card>
      </section>

      <div class="annotation-layout" v-loading="loading">
        <el-card shadow="never" class="qc-card annotation-task-list">
          <template #header>
            <div class="card-header">
              <span>任务队列 <small>{{ total }}</small></span>
              <el-select v-model="filterStatus" size="small" clearable placeholder="全部状态" style="width: 125px" @change="page = 1; loadTasks()">
                <el-option label="待处理" value="pending" />
                <el-option label="已分配" value="assigned" />
                <el-option label="进行中" value="in_progress" />
                <el-option label="已完成" value="completed" />
              </el-select>
            </div>
          </template>
          <div v-if="!tasks.length" class="empty-state">暂无可处理的标注任务</div>
          <button
            v-for="task in tasks"
            :key="task.id"
            type="button"
            class="annotation-task-item"
            :class="{ active: task.id === selectedTaskId }"
            @click="openTask(task.id)"
          >
            <div class="task-item-main">
              <strong>{{ task.episodeId }}</strong>
              <el-tag size="small" :type="statusType(task.workStatus)">{{ task.workStatus }}</el-tag>
            </div>
            <span>{{ task.taskTypeName }} · {{ task.batchName }}</span>
            <small>revision {{ task.currentRevisionNo }} · {{ task.updatedAt }}</small>
            <el-tag v-if="task.publicClaimEnabled" size="small" type="warning" effect="plain">开放领取</el-tag>
          </button>
          <el-pagination
            v-if="total > pageSize"
            v-model:current-page="page"
            :page-size="pageSize"
            :total="total"
            layout="prev, pager, next"
            small
            @current-change="loadTasks"
          />
        </el-card>

        <el-card shadow="never" class="qc-card annotation-editor" v-loading="detailLoading">
          <template v-if="selectedTask">
            <div class="editor-header">
              <div>
                <div class="eyebrow">{{ selectedTask.taskTypeName }} / {{ selectedTask.batchName }}</div>
                <h2>{{ selectedTask.episodeId }}</h2>
                <p>{{ selectedTask.frameCount }} frames · {{ selectedTask.durationSec.toFixed(2) }} sec · Schema v{{ selectedTask.schema?.versionNo || '-' }}</p>
              </div>
              <div class="editor-actions">
                <el-tag :type="hasLock ? 'success' : selectedTask.lockOwner ? 'danger' : 'info'">
                  {{ hasLock ? '编辑锁属于你' : selectedTask.lockOwner ? '他人编辑中' : '未加锁' }}
                </el-tag>
                <el-button v-if="!hasLock && session.user?.role !== 'viewer'" size="small" @click="lockTask">获取锁</el-button>
                <el-button v-if="hasLock" size="small" @click="unlockTask">释放锁</el-button>
              </div>
            </div>

            <div v-if="isManager" class="manager-task-actions">
              <el-select v-model="selectedReviewerId" filterable clearable placeholder="选择 reviewer 分配" class="manager-reviewer-select">
                <el-option
                  v-for="reviewer in reviewers"
                  :key="reviewer.id"
                  :label="`${reviewer.name} · 当前 ${reviewerWorkload.get(reviewer.id) ?? 0}`"
                  :value="reviewer.id"
                />
              </el-select>
              <el-input v-model="assignmentNote" placeholder="分配备注（可选）" class="manager-assignment-note" />
              <el-button :disabled="!selectedReviewerId || !['pending', 'assigned'].includes(selectedTask.workStatus)" @click="assignSelectedTask">分配</el-button>
              <el-button
                :type="selectedTask.publicClaimEnabled ? 'warning' : 'info'"
                :disabled="selectedTask.workStatus !== 'pending' || !!selectedTask.assignedTo"
                @click="toggleSelectedPublicClaim"
              >{{ selectedTask.publicClaimEnabled ? '关闭公共领取' : '开放公共领取' }}</el-button>
              <small v-if="selectedTask.assignedName">当前归属：{{ selectedTask.assignedName }}</small>
            </div>

            <div v-if="mediaUrl" class="annotation-media">
              <video :src="mediaUrl" controls preload="metadata" />
              <span>可选预览，不改变现有 QC 表单</span>
            </div>
            <el-alert v-if="session.user?.role === 'reviewer' && !canEdit" type="warning" :closable="false" title="请先获取编辑锁，再修改和保存标注" />

            <el-form label-position="top" class="annotation-form" @change="markDirty">
              <div class="form-grid">
                <el-form-item label="Canonical instruction (English)" required>
                  <el-input v-model="draft.canonicalInstructionEn" :disabled="!canEdit" class="qc-input" placeholder="Describe the complete task in canonical English" />
                </el-form-item>
                <el-form-item label="Canonical instruction（中文）">
                  <el-input v-model="draft.canonicalInstructionZh" :disabled="!canEdit" class="qc-input" placeholder="可选" />
                </el-form-item>
              </div>
              <el-form-item label="Episode summary">
                <el-input v-model="draft.episodeSummary" :disabled="!canEdit" type="textarea" :rows="2" class="qc-input" />
              </el-form-item>
              <el-form-item label="Instruction variants（最多 5 条）">
                <div class="variant-list">
                  <div v-for="(_variant, index) in draft.instructionVariantsEn" :key="index" class="variant-row">
                    <el-input v-model="draft.instructionVariantsEn[index]" :disabled="!canEdit" class="qc-input" />
                    <el-button text type="danger" :disabled="!canEdit" @click="draft.instructionVariantsEn.splice(index, 1); markDirty()">删除</el-button>
                  </div>
                  <el-button text type="primary" :disabled="!canEdit || draft.instructionVariantsEn.length >= 5" @click="addVariant">+ 添加变体</el-button>
                </div>
              </el-form-item>

              <div class="section-heading">
                <div><h3>Sub Goal occurrences</h3><p>Definition 来自冻结 Schema；时间范围使用半开区间 [start, end)。</p></div>
                <el-tag type="info">{{ draft.occurrences.length }} occurrences</el-tag>
              </div>
              <div v-for="definition in selectedSchema?.definitions || []" :key="definition.id || definition.code" class="definition-block">
                <div class="definition-heading">
                  <div><strong>{{ definition.sequenceNo }}. {{ definition.nameEn || definition.code }}</strong><span v-if="definition.nameZh"> · {{ definition.nameZh }}</span></div>
                  <el-button size="small" plain :disabled="!canEdit" @click="addOccurrence(definition.id || '')">+ occurrence</el-button>
                </div>
                <p v-if="definition.description" class="definition-description">{{ definition.description }}</p>
                <div v-if="!draft.occurrences.some((item) => item.definitionId === definition.id)" class="definition-empty">尚未记录</div>
                <div v-for="(occurrence, index) in draft.occurrences.filter((item) => item.definitionId === definition.id)" :key="occurrence.id || `${definition.id}-${index}`" class="occurrence-row">
                  <span class="occurrence-no">#{{ occurrence.occurrenceNo }}</span>
                  <el-select v-model="occurrence.status" :disabled="!canEdit" size="small" style="width: 125px" @change="markDirty">
                    <el-option v-for="status in instanceStatuses" :key="status.value" :label="status.label" :value="status.value" />
                  </el-select>
                  <el-input-number v-model="occurrence.startStep" :disabled="!canEdit || ['skipped', 'not_observed', 'not_applicable'].includes(occurrence.status)" :min="0" :max="selectedTask.frameCount" controls-position="right" size="small" />
                  <span class="range-separator">至</span>
                  <el-input-number v-model="occurrence.endStepExclusive" :disabled="!canEdit || ['skipped', 'not_observed', 'not_applicable'].includes(occurrence.status)" :min="0" :max="selectedTask.frameCount" controls-position="right" size="small" />
                  <el-input-number v-model="occurrence.representativeStep" :disabled="!canEdit || ['skipped', 'not_observed', 'not_applicable'].includes(occurrence.status)" :min="0" :max="selectedTask.frameCount" controls-position="right" size="small" />
                  <el-input v-model="occurrence.failureReason" :disabled="!canEdit" size="small" placeholder="失败原因（如适用）" class="qc-input occurrence-note" />
                  <el-button text type="danger" :disabled="!canEdit" @click="removeOccurrence(draft.occurrences.indexOf(occurrence))">移除</el-button>
                </div>
              </div>

              <div class="form-grid">
                <el-form-item label="Task outcome" required>
                  <el-select v-model="draft.taskOutcome" :disabled="!canEdit" class="qc-select" placeholder="选择任务结果">
                    <el-option v-for="outcome in outcomes" :key="outcome.value" :label="outcome.label" :value="outcome.value" />
                  </el-select>
                </el-form-item>
                <el-form-item label="Failure occurrence">
                  <el-select v-model="draft.failureSubGoalInstanceId" :disabled="!canEdit" clearable class="qc-select" placeholder="保存后可选择 occurrence">
                    <el-option v-for="occurrence in draft.occurrences.filter((item) => item.id)" :key="occurrence.id" :label="`${definitionLabel(occurrence.definitionId)} #${occurrence.occurrenceNo}`" :value="occurrence.id" />
                  </el-select>
                </el-form-item>
              </div>
              <el-form-item label="Failure reason">
                <el-input v-model="draft.failureReason" :disabled="!canEdit" type="textarea" :rows="2" class="qc-input" />
              </el-form-item>
              <el-form-item label="Annotation notes">
                <el-input v-model="draft.annotationNotes" :disabled="!canEdit" type="textarea" :rows="2" class="qc-input" />
              </el-form-item>
            </el-form>

            <div class="editor-footer">
              <span v-if="dirty" class="unsaved-label">有未保存修改</span>
              <span v-else class="saved-label">草稿已同步 · row version {{ selectedTask.rowVersion }}</span>
              <div class="editor-actions">
                <el-button :disabled="!canEdit || !dirty" :loading="saving" @click="saveDraft">保存草稿</el-button>
                <el-button type="primary" :disabled="!canEdit || selectedTask.workStatus === 'invalidated'" :loading="completing" @click="completeTask">完成并生成 revision</el-button>
              </div>
            </div>
          </template>
          <div v-else class="empty-editor">从左侧选择一个标注任务开始</div>
        </el-card>
      </div>

      <el-dialog v-model="schemaDialogVisible" title="新建标注 Schema 草稿" width="min(760px, 94vw)">
        <p class="schema-dialog-hint">Definition 使用 JSON 数组。保存后仍为 draft，需在上方生命周期列表显式发布才会用于新任务。</p>
        <el-input v-model="schemaDefinitionsJson" type="textarea" :rows="16" class="schema-json-editor" />
        <template #footer>
          <el-button @click="schemaDialogVisible = false">取消</el-button>
          <el-button type="primary" :disabled="!operationTaskTypeId" @click="createSchema">创建草稿</el-button>
        </template>
      </el-dialog>
    </div>
  </AppLayout>
</template>

<style scoped>
.annotation-page { max-width: 1680px; margin: 0 auto; }
.annotation-operations { margin-bottom: 18px; }
.operations-overview { background: linear-gradient(115deg, #f8fbff, #f6fffb); }
.operations-title, .operations-actions, .operations-metrics, .schema-list, .manager-task-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.operations-title { justify-content: space-between; }
.operations-title h2 { margin: 3px 0; color: #0f172a; font-size: 20px; }
.operations-title p, .schema-dialog-hint { margin: 0; color: #64748b; font-size: 12px; }
.operation-task-type { width: 240px; }
.operations-metrics { margin: 18px 0; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); }
.operations-metrics > div { min-width: 0; padding: 13px 16px; border: 1px solid #dbeafe; border-radius: 12px; background: rgba(255,255,255,.72); }
.operations-metrics span, .operations-metrics small { display: block; color: #64748b; font-size: 12px; }
.operations-metrics strong { display: block; margin: 4px 0; color: #0f766e; font-size: 24px; }
.operations-actions { padding-top: 2px; }
.schema-list { margin-top: 16px; padding-top: 14px; border-top: 1px solid #dbeafe; }
.schema-list-label { color: #475569; font-size: 12px; font-weight: 700; }
.schema-chip { display: inline-flex; align-items: center; gap: 5px; }
.annotation-hero { background: linear-gradient(135deg, #fff 0%, #eef7ff 56%, #effcf8 100%); }
.annotation-hero-meta { min-width: 180px; padding: 18px 22px; border-radius: 18px; background: rgba(255,255,255,.72); text-align: right; }
.annotation-hero-meta span, .annotation-hero-meta small { display: block; color: #64748b; font-size: 12px; }
.annotation-hero-meta strong { display: block; margin: 6px 0; color: #0f766e; font-size: 30px; }
.annotation-layout { display: grid; grid-template-columns: 320px minmax(0, 1fr); gap: 18px; align-items: start; }
.annotation-task-list { min-height: 650px; }
.card-header, .editor-header, .editor-footer, .section-heading, .definition-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.card-header small { color: #94a3b8; font-weight: 500; }
.annotation-task-item { display: block; width: 100%; margin: 0 0 8px; padding: 13px; border: 1px solid #e2e8f0; border-radius: 12px; background: #fff; color: inherit; text-align: left; cursor: pointer; transition: .18s ease; }
.annotation-task-item:hover, .annotation-task-item.active { border-color: #60a5fa; background: #eff6ff; box-shadow: 0 8px 20px rgba(37,99,235,.08); }
.task-item-main { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.annotation-task-item > span, .annotation-task-item > small { display: block; margin-top: 7px; color: #64748b; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.annotation-task-item > .el-tag { margin-top: 8px; }
.editor-header { padding-bottom: 16px; border-bottom: 1px solid #e2e8f0; }
.manager-task-actions { margin: 14px 0; padding: 12px; border: 1px solid #dbeafe; border-radius: 12px; background: #f8fbff; }
.manager-task-actions small { color: #64748b; font-size: 12px; }
.manager-reviewer-select { width: 220px; }
.manager-assignment-note { width: 240px; }
.editor-header h2 { margin: 4px 0; color: #0f172a; font-size: 24px; }
.editor-header p, .eyebrow { color: #64748b; font-size: 12px; }
.eyebrow { font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }
.editor-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.annotation-media { display: flex; align-items: center; gap: 12px; margin: 16px 0; color: #64748b; font-size: 12px; }
.annotation-media video { width: min(480px, 100%); max-height: 240px; border-radius: 12px; background: #0f172a; }
.annotation-form { padding-top: 18px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.variant-list { width: 100%; }
.variant-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.variant-row .el-input { flex: 1; }
.section-heading { margin: 24px 0 12px; padding-top: 18px; border-top: 1px solid #e2e8f0; }
.section-heading h3 { margin: 0 0 4px; color: #0f172a; font-size: 16px; }
.section-heading p, .definition-description { color: #64748b; font-size: 12px; }
.definition-block { margin-bottom: 12px; padding: 13px; border: 1px solid #e2e8f0; border-radius: 12px; background: #f8fafc; }
.definition-heading strong { color: #1e293b; }
.definition-heading span { color: #64748b; font-size: 12px; }
.definition-description { margin: 8px 0; }
.definition-empty { padding: 8px 0; color: #94a3b8; font-size: 12px; }
.occurrence-row { display: flex; align-items: center; gap: 7px; margin-top: 8px; padding: 9px; border-radius: 9px; background: #fff; flex-wrap: wrap; }
.occurrence-no { min-width: 24px; color: #64748b; font-size: 12px; font-weight: 700; }
.range-separator { color: #94a3b8; font-size: 12px; }
.occurrence-note { min-width: 180px; flex: 1; }
.editor-footer { margin-top: 20px; padding-top: 16px; border-top: 1px solid #e2e8f0; }
.unsaved-label { color: #b45309; font-size: 12px; font-weight: 700; }
.saved-label { color: #64748b; font-size: 12px; }
.empty-state, .empty-editor { padding: 55px 18px; color: #94a3b8; text-align: center; }
@media (max-width: 1100px) {
  .annotation-layout { grid-template-columns: 1fr; }
  .annotation-task-list { min-height: 0; }
  .annotation-task-item { display: inline-block; width: calc(50% - 6px); margin-right: 8px; vertical-align: top; }
  .operations-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 700px) {
  .annotation-hero, .editor-header, .editor-footer { align-items: flex-start; flex-direction: column; }
  .annotation-hero-meta { width: 100%; text-align: left; }
  .form-grid { grid-template-columns: 1fr; gap: 0; }
  .annotation-task-item { width: 100%; margin-right: 0; }
  .occurrence-row { align-items: flex-start; }
  .operation-task-type, .manager-reviewer-select, .manager-assignment-note { width: 100%; }
  .operations-metrics { grid-template-columns: 1fr; }
}
</style>
