<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppLayout from '../components/AppLayout.vue'
import {
  createRereviewRequest,
  fetchReviewerCurrentTasks,
  fetchReviewerHistoryTasks,
  fetchTaskPool,
  type ReviewerCurrentTasksPayload,
  type ReviewerHistoryTasksPayload,
  type TaskPoolPayload
} from '../api/client'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSessionStore } from '../stores/session'

const session = useSessionStore()
const isReviewer = computed(() => session.user?.role === 'reviewer')

const payload = ref<TaskPoolPayload | null>(null)
const loading = ref(true)
const error = ref('')
const selectedBatchId = ref('')

const currentTaskPayload = ref<ReviewerCurrentTasksPayload | null>(null)
const historyTaskPayload = ref<ReviewerHistoryTasksPayload | null>(null)
const currentTaskLoading = ref(false)
const historyTaskLoading = ref(false)
const currentTaskPage = ref(1)
const historyTaskPage = ref(1)
const reviewerPageSize = 10

const pickPreferredBatchId = (data: TaskPoolPayload, currentBatchId: string) => {
  const batchIds = new Set(data.batches.map((batch) => batch.id))
  if (currentBatchId && batchIds.has(currentBatchId)) {
    return currentBatchId
  }
  return data.batches[0]?.id ?? ''
}

const loadReviewerPools = async () => {
  currentTaskLoading.value = true
  historyTaskLoading.value = true
  error.value = ''
  try {
    const [currentData, historyData] = await Promise.all([
      fetchReviewerCurrentTasks(currentTaskPage.value, reviewerPageSize),
      fetchReviewerHistoryTasks(historyTaskPage.value, reviewerPageSize)
    ])
    currentTaskPayload.value = currentData
    historyTaskPayload.value = historyData
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载任务列表失败'
  } finally {
    currentTaskLoading.value = false
    historyTaskLoading.value = false
    loading.value = false
  }
}

const loadTaskPool = async () => {
  loading.value = true
  error.value = ''
  if (isReviewer.value) {
    await loadReviewerPools()
    return
  }
  try {
    const data = await fetchTaskPool()
    payload.value = data
    selectedBatchId.value = pickPreferredBatchId(data, selectedBatchId.value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载任务明细页失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadTaskPool)

const batches = computed(() => payload.value?.batches ?? [])
const dispatchPreviews = computed(() => payload.value?.dispatchPreviews ?? [])
const qcTasks = computed(() => payload.value?.qcTasks ?? [])
const selectedBatch = computed(() => batches.value.find((batch) => batch.id === selectedBatchId.value) ?? batches.value[0])
const dispatchPreview = computed(() => dispatchPreviews.value.find((preview) => preview.batchId === selectedBatch.value?.id) ?? null)
const currentTasks = computed(() => isReviewer.value ? (currentTaskPayload.value?.items ?? []) : qcTasks.value.filter((task) => task.batchId === selectedBatch.value?.id))
const historyTasks = computed(() => historyTaskPayload.value?.items ?? [])

const statusType = (status: string) => {
  if (status === 'new') return 'info'
  if (status === 'assigned') return 'warning'
  if (status === 'in_review') return 'primary'
  return 'success'
}

const dispatchTag = (mode: string) => (mode === 'full' ? 'success' : 'warning')
const activeTaskCount = computed(() => currentTasks.value.filter((task: any) => task.isActive).length)
const supersededTaskCount = computed(() => currentTasks.value.filter((task: any) => !task.isActive).length)
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

const handleCurrentPageChange = async (page: number) => {
  currentTaskPage.value = page
  await loadReviewerPools()
}

const handleHistoryPageChange = async (page: number) => {
  historyTaskPage.value = page
  await loadReviewerPools()
}
const requestingRereview = ref<string | null>(null)

const requestRereview = async (episodeId: string) => {
  try {
    const { value: reason } = await ElMessageBox.prompt('请填写重新质检原因', '申请重新质检', {
      confirmButtonText: '提交申请',
      cancelButtonText: '取消',
      inputType: 'textarea',
      inputPlaceholder: '说明为什么需要重新质检此任务',
      inputValidator: (value: string) => {
        if (!value || !value.trim()) return '原因不能为空'
        return true
      },
    })
    requestingRereview.value = episodeId
    await createRereviewRequest(episodeId, reason)
    ElMessage.success('重新质检申请已提交')
    await loadReviewerPools()
  } catch (err: any) {
    if (err === 'cancel' || err === 'close') return
    ElMessage.error(err instanceof Error ? err.message : '申请失败')
  } finally {
    requestingRereview.value = null
  }
}
</script>

<template>
  <AppLayout>
    <div class="page-stack">
      <section class="page-title-row database-hero">
        <div>
          <el-tag type="warning" effect="light">QC Queue Detail</el-tag>
          <h1>{{ isReviewer ? '我的质检任务' : '人工质检入口' }}</h1>
          <p v-if="!isReviewer">这里仅保留当前批次任务明细、锁状态和进入人工质检入口。任务生成与批量派发已迁移到工作台。</p>
          <p v-else>当前任务与历史任务分离展示，当前池仅保留待处理任务。</p>
        </div>
        <div class="toolbar-actions">
          <template v-if="!isReviewer">
            <el-select v-model="selectedBatchId" filterable class="qc-select batch-select" style="width: 220px" :loading="loading">
              <el-option v-for="b in batches" :key="b.id" :label="b.name" :value="b.id" />
            </el-select>
            <router-link to="/dashboard"><el-button type="primary" plain class="qc-btn-plain">返回工作台派发</el-button></router-link>
          </template>
          <template v-else>
            <router-link to="/reviewer"><el-button plain>返回个人看板</el-button></router-link>
          </template>
        </div>
      </section>

      <el-alert v-if="error" type="error" :closable="false" :title="error" />

      <el-row :gutter="18" v-loading="loading" class="task-pool-summary-row">
        <template v-if="!isReviewer">
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-blue task-pool-stat-card"><span>当前活跃任务</span><strong>{{ activeTaskCount }}</strong><small>当前派发版本</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-orange task-pool-stat-card"><span>待派发</span><strong>{{ dispatchPreview?.pendingAssignCount ?? 0 }}</strong><small>pending_assign</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-purple task-pool-stat-card"><span>进行中</span><strong>{{ dispatchPreview?.inReviewTaskCount ?? 0 }}</strong><small>active review lock</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-green task-pool-stat-card"><span>已退役旧任务</span><strong>{{ supersededTaskCount }}</strong><small>superseded</small></el-card></el-col>
        </template>
        <template v-else>
        <el-col :span="8"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-blue task-pool-stat-card"><span>当前任务</span><strong>{{ currentTaskPayload?.total ?? 0 }}</strong><small>assigned / in_review</small></el-card></el-col>
        <el-col :span="8"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-green task-pool-stat-card"><span>历史任务</span><strong>{{ historyTaskPayload?.total ?? 0 }}</strong><small>done history</small></el-card></el-col>
        <el-col :span="8"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-orange task-pool-stat-card"><span>进行中</span><strong>{{ currentTasks.filter((t: any) => t.reviewLock?.isLocked).length }}</strong><small>锁定中</small></el-card></el-col>
        </template>
      </el-row>

      <template v-if="!isReviewer">
        <el-card shadow="never" class="qc-card task-pool-table-card" v-loading="loading">
          <template #header>
            <div class="card-header"><span>QC 任务明细</span><el-tag type="success">只读排障与进入质检</el-tag></div>
          </template>
          <el-table :data="currentTasks" stripe height="520" class="qc-table" scrollbar-always-on>
            <el-table-column prop="id" label="任务ID" width="150" />
            <el-table-column prop="episodeId" label="Episode" min-width="150" />
            <el-table-column prop="taskName" label="任务类型" min-width="150" />
            <el-table-column prop="batchName" label="批次" min-width="180" />
            <el-table-column label="派发版本" width="100"><template #default="{ row }">#{{ row.dispatchGeneration }}</template></el-table-column>
            <el-table-column label="活跃" width="90"><template #default="{ row }"><el-tag :type="row.isActive ? 'success' : 'info'">{{ row.isActive ? 'active' : 'superseded' }}</el-tag></template></el-table-column>
            <el-table-column label="派发模式" width="110"><template #default="{ row }"><el-tag :type="dispatchTag(row.dispatchMode)" size="small">{{ row.dispatchMode === 'full' ? '全量' : `抽检 ${row.samplingRatio}%` }}</el-tag></template></el-table-column>
            <el-table-column prop="assignee" label="审核员" width="120" />
            <el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="statusType(row.status)">{{ row.status }}</el-tag></template></el-table-column>
            <el-table-column label="审核锁" min-width="180">
              <template #default="{ row }">
                <div style="display:flex; flex-direction:column; gap:4px; line-height:1.2;">
                  <el-tag :type="lockTagType(row)" size="small">{{ lockLabel(row) }}</el-tag>
                  <span v-if="row.reviewLock.expiresAt" style="font-size:12px; color:#909399;">到期 {{ row.reviewLock.expiresAt }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="createdAt" label="创建时间" width="160" />
            <el-table-column label="操作" width="180" fixed="right"><template #default="{ row }"><router-link :to="`/manual-qc/${row.episodeId}`"><el-button link type="primary">进入质检</el-button></router-link></template></el-table-column>
          </el-table>
        </el-card>
      </template>

      <template v-else>
        <el-card shadow="never" class="qc-card task-pool-table-card" v-loading="currentTaskLoading">
          <template #header>
            <div class="card-header"><span>我的任务清单</span><el-tag type="success">当前可处理任务</el-tag></div>
          </template>
          <el-table :data="currentTasks" stripe height="320" class="qc-table" scrollbar-always-on>
            <el-table-column prop="episodeId" label="Episode" min-width="150" />
            <el-table-column prop="taskName" label="任务类型" min-width="150" />
            <el-table-column prop="batchName" label="批次" min-width="180" />
            <el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="statusType(row.status)">{{ row.status }}</el-tag></template></el-table-column>
            <el-table-column label="审核锁" min-width="180"><template #default="{ row }"><el-tag :type="lockTagType(row)" size="small">{{ lockLabel(row) }}</el-tag></template></el-table-column>
            <el-table-column prop="createdAt" label="创建时间" width="160" />
            <el-table-column label="操作" width="140" fixed="right"><template #default="{ row }"><router-link :to="`/manual-qc/${row.episodeId}`"><el-button link type="primary">进入质检</el-button></router-link></template></el-table-column>
          </el-table>
          <div style="display:flex; justify-content:center; margin-top:12px">
            <el-pagination
              v-if="(currentTaskPayload?.total ?? 0) > reviewerPageSize"
              :current-page="currentTaskPage"
              :page-size="reviewerPageSize"
              :total="currentTaskPayload?.total ?? 0"
              layout="prev, pager, next"
              size="small"
              @current-change="handleCurrentPageChange"
            />
          </div>
        </el-card>

        <el-card shadow="never" class="qc-card task-pool-table-card" v-loading="historyTaskLoading">
          <template #header>
            <div class="card-header"><span>历史任务清单</span><el-tag type="info">已完成历史记录</el-tag></div>
          </template>
          <el-table :data="historyTasks" stripe height="320" class="qc-table" scrollbar-always-on>
            <el-table-column prop="episodeId" label="Episode" min-width="150" />
            <el-table-column prop="taskName" label="任务类型" min-width="150" />
            <el-table-column prop="batchName" label="批次" min-width="180" />
            <el-table-column prop="result" label="结果" width="100" />
            <el-table-column prop="primaryReason" label="原因码" min-width="150" />
            <el-table-column prop="operator" label="审核人" width="120" />
            <el-table-column prop="time" label="完成时间" width="170" />
            <el-table-column label="操作" width="260" fixed="right">
              <template #default="{ row }">
                <router-link :to="`/manual-qc/${row.episodeId}`"><el-button link type="primary">进入质检</el-button></router-link>
                <el-button
                  link
                  type="warning"
                  :loading="requestingRereview === row.episodeId"
                  :disabled="row.hasPendingRequest || (row.currentTaskStatus === 'done' && row.currentTaskAssignee !== session.user?.name)"
                  @click="requestRereview(row.episodeId)"
                >{{ row.hasPendingRequest ? '审批中' : '申请重新质检' }}</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div style="display:flex; justify-content:center; margin-top:12px">
            <el-pagination
              v-if="(historyTaskPayload?.total ?? 0) > reviewerPageSize"
              :current-page="historyTaskPage"
              :page-size="reviewerPageSize"
              :total="historyTaskPayload?.total ?? 0"
              layout="prev, pager, next"
              size="small"
              @current-change="handleHistoryPageChange"
            />
          </div>
        </el-card>
      </template>
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
</style>
