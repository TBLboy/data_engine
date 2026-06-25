<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '../components/AppLayout.vue'
import { assignBatchTasks, fetchDashboard, submitDispatchPlan, type DashboardPayload } from '../api/client'
import type { BatchDispatchAssignRequest, DispatchMode } from '../types/qc'

const payload = ref<DashboardPayload | null>(null)
const loading = ref(true)
const error = ref('')
const selectedTaskType = ref('')
const selectedBatchId = ref('')
const savingDispatchPlan = ref(false)
const savingAssignments = ref(false)

const dispatchForm = reactive({
  dispatchMode: 'sampled' as DispatchMode,
  samplingRatio: 25,
  note: ''
})

const assignMode = ref<'even' | 'custom_counts'>('even')
const selectedReviewerIds = ref<string[]>([])
const customAssignmentCounts = ref<Record<string, number>>({})

const loadDashboard = async () => {
  loading.value = true
  error.value = ''
  try {
    const data = await fetchDashboard()
    payload.value = data
    if (!selectedTaskType.value && data.taskTypes.length) {
      const withWork = data.taskTypes.find((item) => (item.totalBatches ?? 0) > 0)
      selectedTaskType.value = (withWork ?? data.taskTypes[0]).id
    }
    if (!selectedBatchId.value && data.batches.length) {
      selectedBatchId.value = data.batches[0].id
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载工作台失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadDashboard)

const taskTypes = computed(() => payload.value?.taskTypes ?? [])
const batches = computed(() => payload.value?.batches ?? [])
const qcTasks = computed(() => payload.value?.qcTasks ?? [])
const dispatchPreviews = computed(() => payload.value?.dispatchPreviews ?? [])
const reasonStats = computed(() => payload.value?.reasonStats ?? [])
const reviewerWorkloads = computed(() => payload.value?.reviewerWorkloads ?? [])
const reviewerAccounts = computed(() => payload.value?.reviewerAccounts ?? [])
const currentBatches = computed(() => batches.value.filter((batch) => batch.taskTypeId === selectedTaskType.value))
const batchIdsInTaskType = computed(() => new Set(currentBatches.value.map((batch) => batch.id)))
const filteredDispatchPreviews = computed(() => dispatchPreviews.value.filter((preview) => batchIdsInTaskType.value.has(preview.batchId)))
const filteredQcTasks = computed(() => qcTasks.value.filter((task) => batchIdsInTaskType.value.has(task.batchId)))
const totalEpisodes = computed(() => currentBatches.value.reduce((sum, batch) => sum + batch.episodeCount, 0))
const totalSampled = computed(() => currentBatches.value.reduce((sum, batch) => sum + batch.sampledEpisodeCount, 0))
const totalCompleted = computed(() => currentBatches.value.reduce((sum, batch) => sum + batch.completedSampleCount, 0))
const avgCoverage = computed(() => {
  if (!totalEpisodes.value) return 0
  return Math.round((totalSampled.value / totalEpisodes.value) * 100)
})
const avgPassRate = computed(() => {
  const done = currentBatches.value.filter((batch) => batch.completedSampleCount > 0)
  if (!done.length) return 0
  return Math.round(done.reduce((sum, batch) => sum + batch.passRate, 0) / done.length)
})

const selectedBatch = computed(() => currentBatches.value.find((batch) => batch.id === selectedBatchId.value) ?? currentBatches.value[0] ?? null)
const selectedDispatchPreview = computed(() => filteredDispatchPreviews.value.find((preview) => preview.batchId === selectedBatch.value?.id) ?? null)

const currentTodoCount = computed(() => filteredQcTasks.value.filter((task) => task.status !== 'done').length)
const highPriorityCount = computed(() => filteredQcTasks.value.filter((task) => task.priority === 'high' && task.status !== 'done').length)

const canAssignSelectedBatch = computed(() => Boolean(selectedBatch.value && selectedDispatchPreview.value?.pendingAssignCount))
const customAssignmentTotal = computed(() => selectedReviewerIds.value.reduce((sum, reviewerId) => sum + (customAssignmentCounts.value[reviewerId] || 0), 0))

const syncBatchForms = () => {
  if (!selectedBatch.value) return
  dispatchForm.dispatchMode = selectedBatch.value.dispatchMode
  dispatchForm.samplingRatio = selectedBatch.value.samplingRatio
  dispatchForm.note = ''
  selectedReviewerIds.value = []
  customAssignmentCounts.value = {}
}

const onTaskTypeChange = () => {
  const nextBatch = currentBatches.value[0]
  selectedBatchId.value = nextBatch?.id ?? ''
  syncBatchForms()
}

const onBatchChange = () => {
  syncBatchForms()
}

const syncCustomAssignmentCounts = () => {
  const next: Record<string, number> = {}
  for (const reviewerId of selectedReviewerIds.value) {
    next[reviewerId] = customAssignmentCounts.value[reviewerId] || 0
  }
  customAssignmentCounts.value = next
}

const dispatchTag = (mode: DispatchMode) => (mode === 'full' ? 'success' : 'warning')
const dispatchLabel = (mode: DispatchMode, ratio: number) => mode === 'full' ? '全量' : `抽检 ${ratio}%`
const statusType = (status: string) => {
  if (status === 'done') return 'success'
  if (status === 'in_review') return 'warning'
  return 'info'
}

const applyDispatchPlan = async () => {
  if (!selectedBatch.value) return
  const modeLabel = dispatchForm.dispatchMode === 'full'
    ? '全量派发（整批）'
    : `按 ${dispatchForm.samplingRatio}% 抽检`
  try {
    await ElMessageBox.confirm(
      `将对批次「${selectedBatch.value.name}」${modeLabel}生成待派发任务，确认继续？`,
      '确认生成派发',
      { confirmButtonText: '确认生成', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  savingDispatchPlan.value = true
  try {
    await submitDispatchPlan(selectedBatch.value.id, {
      dispatchMode: dispatchForm.dispatchMode,
      samplingRatio: dispatchForm.samplingRatio,
      note: dispatchForm.note.trim()
    })
    ElMessage.success('待派发任务池已更新')
    await loadDashboard()
    selectedBatchId.value = selectedBatch.value.id
    syncBatchForms()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '生成待派发任务失败')
  } finally {
    savingDispatchPlan.value = false
  }
}

const applyBatchAssignment = async () => {
  if (!selectedBatch.value) return
  if (!selectedReviewerIds.value.length) {
    ElMessage.warning('请先选择至少一个审核员')
    return
  }

  const payload: BatchDispatchAssignRequest = {
    mode: assignMode.value,
    reviewerIds: selectedReviewerIds.value,
    reviewers: selectedReviewerIds.value.map((reviewerId) => ({
      reviewerId,
      count: customAssignmentCounts.value[reviewerId] || 0,
    }))
  }

  if (assignMode.value === 'custom_counts' && customAssignmentTotal.value !== (selectedDispatchPreview.value?.pendingAssignCount ?? 0)) {
    ElMessage.warning('自定义派发条数之和必须等于待派发任务数')
    return
  }

  savingAssignments.value = true
  try {
    await assignBatchTasks(selectedBatch.value.id, payload)
    ElMessage.success('批量派发已完成')
    await loadDashboard()
    selectedBatchId.value = selectedBatch.value.id
    syncBatchForms()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '批量派发失败')
  } finally {
    savingAssignments.value = false
  }
}
</script>

<template>
  <AppLayout>
    <div class="page-stack">
      <section class="boss-hero">
        <div class="hero-copy">
          <el-tag type="primary" effect="dark">V1.0 Manual QC Platform</el-tag>
          <h1>机器人采集数据质检运营中心</h1>
          <p>从 MinIO 数据湖扫描入库、批次管理、任务生成、批量派发、人工 QC、结果留痕到批次统计，形成公司内网可落地的完整闭环。</p>
          <div class="hero-badges">
            <span>LAN 内网部署</span>
            <span>PostgreSQL 业务数据</span>
            <span>MinIO 对象存储</span>
            <span>多人账号协作</span>
          </div>
        </div>
        <div class="hero-command-card">
          <div class="command-title">今日派发指挥板</div>
          <div class="command-number">{{ currentTodoCount }}</div>
          <div class="command-subtitle">当前任务类型下仍待处理任务</div>
          <el-progress class="qc-progress" :percentage="totalSampled ? Math.round((totalCompleted / totalSampled) * 100) : 0" :stroke-width="12" />
          <div class="hero-actions command-actions">
            <el-select v-model="selectedTaskType" filterable class="qc-select" size="large" style="width: 260px" :loading="loading" @change="onTaskTypeChange">
              <el-option v-for="item in taskTypes" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
            <router-link v-if="filteredQcTasks[0]" :to="`/manual-qc/${filteredQcTasks[0].episodeId}`"><el-button type="primary" size="large">进入 QC 工作台</el-button></router-link>
          </div>
        </div>
      </section>

      <el-alert v-if="error" type="error" :closable="false" :title="error" />

      <el-row :gutter="18" v-loading="loading">
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-blue"><span>候选总量</span><strong>{{ totalEpisodes }}</strong><small>待抽检 / 已入库</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-orange"><span>已抽中样本</span><strong>{{ totalSampled }}</strong><small>抽检覆盖率 {{ avgCoverage }}%</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-green"><span>样本完成率</span><strong>{{ avgPassRate }}%</strong><small>基于已完成样本 pass rate</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-purple"><span>待处理任务</span><strong>{{ currentTodoCount }}</strong><small>高优先级 {{ highPriorityCount }} 条</small></el-card></el-col>
      </el-row>

      <el-row :gutter="18">
        <el-col :span="16">
          <el-card shadow="never" class="qc-card" v-loading="loading">
            <template #header>
              <div class="card-header"><span>批次派发总览</span><router-link to="/database"><el-button plain>查看数据总库</el-button></router-link></div>
            </template>
            <el-table class="qc-table dispatch-overview-table" :data="currentBatches" stripe row-key="id" highlight-current-row :current-row-key="selectedBatchId" @row-click="(row: { id: string }) => { selectedBatchId = row.id; onBatchChange() }">
              <el-table-column prop="name" label="批次" min-width="190" />
              <el-table-column prop="episodeCount" label="总量" width="70" />
              <el-table-column label="派发模式" width="110">
                <template #default="{ row }"><el-tag :type="dispatchTag(row.dispatchMode)" size="small">{{ dispatchLabel(row.dispatchMode, row.samplingRatio) }}</el-tag></template>
              </el-table-column>
              <el-table-column label="待派发" width="90">
                <template #default="{ row }"><strong>{{ filteredDispatchPreviews.find((preview) => preview.batchId === row.id)?.pendingAssignCount ?? 0 }}</strong></template>
              </el-table-column>
              <el-table-column label="已派发" width="90">
                <template #default="{ row }"><strong>{{ filteredDispatchPreviews.find((preview) => preview.batchId === row.id)?.assignedTaskCount ?? 0 }}</strong></template>
              </el-table-column>
              <el-table-column label="进行中" width="90">
                <template #default="{ row }"><strong>{{ filteredDispatchPreviews.find((preview) => preview.batchId === row.id)?.inReviewTaskCount ?? 0 }}</strong></template>
              </el-table-column>
              <el-table-column label="已完成" width="90">
                <template #default="{ row }"><strong>{{ filteredDispatchPreviews.find((preview) => preview.batchId === row.id)?.doneTaskCount ?? 0 }}</strong></template>
              </el-table-column>
              <el-table-column label="样本完成" min-width="180">
                <template #default="{ row }">
                  <span style="margin-right:8px">{{ row.completedSampleCount }}/{{ row.sampledEpisodeCount }}</span>
                  <el-progress :percentage="row.sampleReviewCompletionRate" :stroke-width="7" />
                </template>
              </el-table-column>
              <el-table-column label="状态" width="100">
                <template #default="{ row }"><el-tag :type="statusType(row.qcStatus)">{{ row.qcStatus }}</el-tag></template>
              </el-table-column>
              <el-table-column prop="topReason" label="Top失败原因" min-width="150" />
            </el-table>
          </el-card>
        </el-col>

        <el-col :span="8">
          <el-card shadow="never" class="qc-card dispatch-card" v-loading="loading">
            <template #header>派发工作区</template>
            <div class="dispatch-panel" v-if="selectedBatch && selectedDispatchPreview">
              <div class="rule-item"><strong>当前批次</strong><span>{{ selectedBatch.name }}</span></div>
              <div class="rule-item"><strong>活跃派发版本</strong><span>#{{ selectedDispatchPreview.activeDispatchGeneration }}</span></div>
              <div class="rule-item"><strong>待派发</strong><span :style="selectedDispatchPreview.pendingAssignCount ? 'color:#e6a23c;font-weight:700' : ''">{{ selectedDispatchPreview.pendingAssignCount }} 条</span></div>
              <div class="rule-item" v-if="selectedDispatchPreview.unsampledEpisodeCount > 0"><strong>未纳入派发</strong><span style="color:#e6a23c;font-weight:700">{{ selectedDispatchPreview.unsampledEpisodeCount }} 集</span></div>
              <div class="rule-item"><strong>已退役旧任务</strong><span>{{ selectedDispatchPreview.supersededTaskCount }} 条</span></div>

              <el-divider />

              <div class="field-label">生成待派发任务</div>
              <el-radio-group v-model="dispatchForm.dispatchMode">
                <el-radio value="sampled">百分比抽检</el-radio>
                <el-radio value="full">全量派发</el-radio>
              </el-radio-group>
              <el-input-number v-show="dispatchForm.dispatchMode === 'sampled'" v-model="dispatchForm.samplingRatio" :min="5" :max="100" :step="5" size="small" style="width: 140px; margin-top: 12px;" />
              <el-input v-model="dispatchForm.note" placeholder="生成备注（可选）" size="small" style="margin-top: 12px;" />
              <el-button type="primary" :loading="savingDispatchPlan" style="margin-top: 12px;" @click="applyDispatchPlan">生成待派发任务</el-button>

              <el-divider />

              <div class="field-label">批量派发</div>
              <el-select v-model="selectedReviewerIds" multiple class="qc-select" filterable placeholder="选择审核员" style="width: 100%;" @change="syncCustomAssignmentCounts">
                <el-option v-for="reviewer in reviewerAccounts" :key="reviewer.id" :label="reviewer.name" :value="reviewer.id" />
              </el-select>

              <el-radio-group v-model="assignMode" style="margin-top: 12px;">
                <el-radio value="even">平均派发</el-radio>
                <el-radio value="custom_counts">指定每人条数</el-radio>
              </el-radio-group>

              <div v-if="assignMode === 'custom_counts'" class="custom-assign-list">
                <div v-for="reviewer in reviewerAccounts.filter((item) => selectedReviewerIds.includes(item.id))" :key="reviewer.id" class="custom-assign-row">
                  <span>{{ reviewer.name }}</span>
                  <el-input-number v-model="customAssignmentCounts[reviewer.id]" :min="0" :max="selectedDispatchPreview.pendingAssignCount" size="small" />
                </div>
                <small>当前合计 {{ customAssignmentTotal }} / {{ selectedDispatchPreview.pendingAssignCount }}</small>
              </div>

              <el-button type="primary" :disabled="!canAssignSelectedBatch" :loading="savingAssignments" style="margin-top: 12px;" @click="applyBatchAssignment">确认派发</el-button>
            </div>
            <el-empty v-else description="当前任务类型下暂无可派发批次" />
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="18">
        <el-col :span="8">
          <el-card shadow="never" class="qc-card" v-loading="loading">
            <template #header>审核员工作量</template>
            <div v-for="reviewer in reviewerWorkloads" :key="reviewer.name" class="reviewer-row">
              <div><strong>{{ reviewer.name }}</strong><span>平均 {{ reviewer.avgMinutes }} min / episode</span></div>
              <el-progress class="qc-progress" :percentage="reviewer.assigned + reviewer.done ? Math.round((reviewer.done / (reviewer.assigned + reviewer.done)) * 100) : 0" />
              <b>{{ reviewer.done }}/{{ reviewer.assigned + reviewer.done }}</b>
            </div>
          </el-card>
        </el-col>

        <el-col :span="8">
          <el-card shadow="never" class="qc-card reason-card" v-loading="loading">
            <template #header>失败原因 Top 统计</template>
            <div v-for="item in reasonStats" :key="item.reason" class="reason-row">
              <div class="reason-info"><strong>{{ item.reason }}</strong><span>{{ item.category }} · {{ item.count }} 条</span></div>
              <div class="reason-bar"><i :style="{ width: `${item.ratio}%` }" /></div>
              <b>{{ item.ratio }}%</b>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </AppLayout>
</template>
