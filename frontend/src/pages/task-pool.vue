<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import AppLayout from '../components/AppLayout.vue'
import { assignTask, fetchTaskPool, submitDispatchPlan, type TaskPoolPayload } from '../api/client'
import type { DispatchMode } from '../types/qc'

const payload = ref<TaskPoolPayload | null>(null)
const loading = ref(true)
const error = ref('')
const selectedBatchId = ref('')
const assigningTaskId = ref('')

const form = reactive({
  dispatchMode: 'sampled' as DispatchMode,
  samplingRatio: 25,
  note: ''
})

const assigneeDrafts = ref<Record<string, string>>({})

const pickPreferredBatchId = (data: TaskPoolPayload, currentBatchId: string) => {
  const batchIds = new Set(data.batches.map((batch) => batch.id))
  if (currentBatchId && batchIds.has(currentBatchId)) {
    return currentBatchId
  }

  const actionableBatchIds = new Set(
    data.dispatchPreviews
      .filter((preview) => preview.candidateEpisodeCount > 0 || preview.createdTaskCount > 0 || preview.assignedTaskCount > 0 || preview.inReviewTaskCount > 0 || preview.doneTaskCount > 0)
      .map((preview) => preview.batchId)
  )

  return data.batches.find((batch) => actionableBatchIds.has(batch.id))?.id ?? data.batches[0]?.id ?? ''
}

const loadTaskPool = async () => {
  loading.value = true
  error.value = ''
  try {
    const data = await fetchTaskPool()
    payload.value = data
    selectedBatchId.value = pickPreferredBatchId(data, selectedBatchId.value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载任务派发中心失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadTaskPool)

const batches = computed(() => payload.value?.batches ?? [])
const dispatchPreviews = computed(() => payload.value?.dispatchPreviews ?? [])
const qcTasks = computed(() => payload.value?.qcTasks ?? [])
const reviewerWorkloads = computed(() => payload.value?.reviewerWorkloads ?? [])
const reviewerAccounts = computed(() => payload.value?.reviewerAccounts ?? [])
const selectedBatch = computed(() => batches.value.find((batch) => batch.id === selectedBatchId.value) ?? batches.value[0])
const dispatchPreview = computed(() => dispatchPreviews.value.find((preview) => preview.batchId === selectedBatch.value?.id) ?? dispatchPreviews.value[0])
const currentTasks = computed(() => qcTasks.value.filter((task) => task.batchId === selectedBatch.value?.id))

watch(selectedBatch, (batch) => {
  if (!batch) return
  form.dispatchMode = batch.dispatchMode
  form.samplingRatio = batch.samplingRatio
}, { immediate: true })

const statusType = (status: string) => {
  if (status === 'new') return 'info'
  if (status === 'assigned') return 'warning'
  if (status === 'in_review') return 'primary'
  return 'success'
}

const dispatchTag = (mode: DispatchMode) => (mode === 'full' ? 'success' : 'warning')
const candidateCount = computed(() => dispatchPreview.value?.candidateEpisodeCount ?? 0)
const sampledCount = computed(() => dispatchPreview.value?.sampledEpisodeCount ?? 0)
const unsampledCount = computed(() => dispatchPreview.value?.unsampledEpisodeCount ?? 0)
const taskSummary = computed(() => ({
  created: dispatchPreview.value?.createdTaskCount ?? 0,
  assigned: dispatchPreview.value?.assignedTaskCount ?? 0,
  inReview: dispatchPreview.value?.inReviewTaskCount ?? 0,
  done: dispatchPreview.value?.doneTaskCount ?? 0
}))
const reviewerOptions = computed(() => reviewerAccounts.value.map((item) => item.name))
const queueSummary = computed(() => {
  const summary = { pending: 0, assigned: 0, inReviewLocked: 0, done: 0, availableAssigned: 0 }
  for (const task of currentTasks.value) {
    if (task.status === 'new') summary.pending += 1
    if (task.status === 'assigned') {
      summary.assigned += 1
      if (!task.reviewLock.isLocked) summary.availableAssigned += 1
    }
    if (task.status === 'done') summary.done += 1
    if (task.reviewLock.isLocked) summary.inReviewLocked += 1
  }
  return summary
})
const lockedTaskCount = computed(() => queueSummary.value.inReviewLocked)
const availableTaskCount = computed(() => queueSummary.value.availableAssigned)
const lockTagType = (task: TaskPoolPayload['qcTasks'][number]) => {
  if (task.reviewLock.isMine) return 'success'
  if (task.reviewLock.isLocked) return 'danger'
  return 'info'
}
const lockLabel = (task: TaskPoolPayload['qcTasks'][number]) => {
  if (task.reviewLock.isMine) return '我在审核'
  if (task.reviewLock.isLocked) return `锁定: ${task.reviewLock.ownerName || '其他审核员'}`
  return '待认领'
}

const applyDispatch = async () => {
  if (!selectedBatchId.value) return
  try {
    await submitDispatchPlan(selectedBatchId.value, {
      dispatchMode: form.dispatchMode,
      samplingRatio: form.samplingRatio,
      note: form.note
    })
    ElMessage.success('派发计划已更新')
    form.note = ''
    await loadTaskPool()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '更新派发计划失败')
  }
}

const reassignTask = async (taskId: string) => {
  const assignee = assigneeDrafts.value[taskId]
  if (!assignee) {
    ElMessage.warning('请选择审核员')
    return
  }
  assigningTaskId.value = taskId
  try {
    await assignTask(taskId, assignee)
    ElMessage.success('任务已派发')
    await loadTaskPool()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '派发任务失败')
  } finally {
    assigningTaskId.value = ''
  }
}
</script>

<template>
  <AppLayout>
    <div class="page-stack">
      <section class="page-title-row database-hero">
        <div>
          <el-tag type="warning" effect="light">QC Assignment Center</el-tag>
          <h1>任务派发中心</h1>
          <p>主管选择批次后可查看候选池、设置抽检比例或切换全量派发，再按审核员批量分配已生成的任务。</p>
        </div>
        <div class="toolbar-actions">
          <el-select v-model="selectedBatchId" filterable style="width: 220px" :loading="loading">
            <el-option v-for="b in batches" :key="b.id" :label="b.name" :value="b.id" />
          </el-select>
          <router-link v-if="currentTasks[0]" :to="`/manual-qc/${currentTasks[0].episodeId}`"><el-button>预览 QC 工作台</el-button></router-link>
        </div>
      </section>

      <el-alert v-if="error" type="error" :closable="false" :title="error" />

      <el-card shadow="never" class="product-card" v-loading="loading">
        <template #header>
          <div class="card-header"><span>派发计划 — 候选池预览</span><el-tag :type="dispatchPreview?.dispatchMode === 'full' ? 'success' : 'warning'" size="small">{{ dispatchPreview?.dispatchMode === 'full' ? '当前全量' : `当前抽检 ${dispatchPreview?.samplingRatio ?? 0}%` }}</el-tag></div>
        </template>
        <el-row :gutter="18">
          <el-col :span="6"><div class="stat-card accent-blue"><span>候选总量</span><strong>{{ candidateCount }}</strong><small>已索引 MinIO episode</small></div></el-col>
          <el-col :span="6"><div class="stat-card accent-orange"><span>已抽中样本</span><strong>{{ sampledCount }}</strong><small>已生成 {{ taskSummary.created }} 条任务</small></div></el-col>
          <el-col :span="6"><div class="stat-card accent-purple"><span>未抽中</span><strong>{{ unsampledCount }}</strong><small>等待补派或全量展开</small></div></el-col>
          <el-col :span="6"><div class="stat-card accent-green"><span>样本进度</span><strong>{{ taskSummary.done }}/{{ taskSummary.created }}</strong><small>assigned {{ taskSummary.assigned }} · in_review {{ taskSummary.inReview }}</small></div></el-col>
        </el-row>

        <div style="margin-top:18px; display:flex; gap:12px; align-items:flex-end; flex-wrap:wrap">
          <el-radio-group v-model="form.dispatchMode">
            <el-radio value="sampled">百分比抽检</el-radio>
            <el-radio value="full">全量派发</el-radio>
          </el-radio-group>
          <el-input-number v-if="form.dispatchMode === 'sampled'" v-model="form.samplingRatio" :min="5" :max="100" :step="5" size="small" style="width:130px" />
          <span v-if="form.dispatchMode === 'sampled'" style="color:#909399;font-size:13px">% 抽检比例（约 {{ Math.round(candidateCount * form.samplingRatio / 100) }} 条）</span>
          <span v-else style="color:#e6a23c;font-size:13px">全量派发将为全部 {{ candidateCount }} 条 episode 生成任务</span>
          <el-input v-model="form.note" placeholder="备注（可选）" size="small" style="width:200px" />
          <el-button type="primary" @click="applyDispatch">确认并生成派发任务</el-button>
        </div>
      </el-card>

      <el-row :gutter="18" v-loading="loading" class="task-pool-summary-row">
        <el-col :span="6"><el-card shadow="never" class="stat-card accent-blue task-pool-stat-card"><span>待派发</span><strong>{{ queueSummary.pending }}</strong><small>pending_assign</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="stat-card accent-orange task-pool-stat-card"><span>已派发</span><strong>{{ queueSummary.assigned }}</strong><small>available {{ availableTaskCount }}</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="stat-card accent-purple task-pool-stat-card"><span>审核锁激活</span><strong>{{ lockedTaskCount }}</strong><small>active review lock</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="stat-card accent-green task-pool-stat-card"><span>已完成</span><strong>{{ queueSummary.done }}</strong><small>revision 已写入</small></el-card></el-col>
      </el-row>

      <el-row :gutter="18">
        <el-col :span="16">
          <el-card shadow="never" class="product-card task-pool-table-card" v-loading="loading">
            <template #header>
              <div class="card-header"><span>QC 任务队列</span><el-tag type="success">支持派发与进入质检</el-tag></div>
            </template>
            <el-table :data="currentTasks" stripe height="460" scrollbar-always-on>
              <el-table-column prop="id" label="任务ID" width="110" />
              <el-table-column prop="episodeId" label="Episode" min-width="150" />
              <el-table-column prop="taskName" label="任务类型" min-width="150" />
              <el-table-column prop="batchName" label="批次" min-width="180" />
              <el-table-column prop="assignee" label="审核员" width="100" />
              <el-table-column label="派发到" width="200">
                <template #default="{ row }">
                  <el-select v-model="assigneeDrafts[row.id]" placeholder="选择审核员" size="small" style="width:170px">
                    <el-option v-for="name in reviewerOptions" :key="name" :label="name" :value="name" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="派发模式" width="100">
                <template #default="{ row }"><el-tag :type="dispatchTag(row.dispatchMode)" size="small">{{ row.dispatchMode === 'full' ? '全量' : `抽检 ${row.samplingRatio}%` }}</el-tag></template>
              </el-table-column>
              <el-table-column label="优先级" width="90">
                <template #default="{ row }"><el-tag :type="row.priority === 'high' ? 'danger' : 'info'">{{ row.priority }}</el-tag></template>
              </el-table-column>
              <el-table-column label="状态" width="110">
                <template #default="{ row }"><el-tag :type="statusType(row.status)">{{ row.status }}</el-tag></template>
              </el-table-column>
              <el-table-column label="审核锁" min-width="180">
                <template #default="{ row }">
                  <div style="display:flex; flex-direction:column; gap:4px; line-height:1.2;">
                    <el-tag :type="lockTagType(row)" size="small">{{ lockLabel(row) }}</el-tag>
                    <span v-if="row.reviewLock.expiresAt" style="font-size:12px; color:#909399;">到期 {{ row.reviewLock.expiresAt }}</span>
                    <span v-else style="font-size:12px; color:#909399;">未认领</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="createdAt" label="创建时间" width="160" />
              <el-table-column label="操作" width="200" fixed="right">
                <template #default="{ row }">
                  <router-link :to="`/manual-qc/${row.episodeId}`"><el-button link type="primary">进入质检</el-button></router-link>
                  <el-button link :disabled="row.reviewLock.isLocked" :loading="assigningTaskId === row.id" @click="reassignTask(row.id)">派发</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>

        <el-col :span="8">
          <el-card shadow="never" class="product-card" v-loading="loading">
            <template #header>审核员负载均衡</template>
            <div v-for="reviewer in reviewerWorkloads" :key="reviewer.name" class="reviewer-row rich-reviewer">
              <div class="ingest-head"><strong>{{ reviewer.name }}</strong><el-tag size="small">通过率 {{ reviewer.passRate }}%</el-tag></div>
              <el-progress :percentage="reviewer.assigned + reviewer.done ? Math.round((reviewer.done / (reviewer.assigned + reviewer.done)) * 100) : 0" />
              <span>{{ reviewer.done }}/{{ reviewer.assigned + reviewer.done }} 已完成 · 平均 {{ reviewer.avgMinutes }} min/条</span>
            </div>
          </el-card>

          <el-card shadow="never" class="product-card assign-rules-card">
            <template #header>派发规则</template>
            <div class="rule-item"><strong>默认抽检</strong><span>新 batch 默认百分比抽检，主管可切换为全量派发</span></div>
            <div class="rule-item"><strong>候选池</strong><span>未抽中 episode 保持候选状态，可后续补派</span></div>
            <div class="rule-item"><strong>审计留痕</strong><span>派发模式、抽检比例、补派动作全部写入 audit_event</span></div>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </AppLayout>
</template>

<style scoped>
.task-pool-summary-row {
  overflow: visible;
}

.task-pool-stat-card {
  min-height: 132px;
}

.task-pool-stat-card :deep(.el-card__body) {
  overflow: hidden;
}

.task-pool-table-card :deep(.el-scrollbar__bar.is-vertical),
.task-pool-table-card :deep(.el-scrollbar__bar.is-horizontal) {
  opacity: 1;
}

.task-pool-table-card :deep(.el-scrollbar__thumb) {
  background-color: #4b5563;
}

.task-pool-table-card :deep(.el-scrollbar__thumb:hover) {
  background-color: #374151;
}
</style>
