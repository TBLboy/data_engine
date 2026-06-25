<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppLayout from '../components/AppLayout.vue'
import { fetchTaskPool, type TaskPoolPayload } from '../api/client'

const payload = ref<TaskPoolPayload | null>(null)
const loading = ref(true)
const error = ref('')
const selectedBatchId = ref('')

const pickPreferredBatchId = (data: TaskPoolPayload, currentBatchId: string) => {
  const batchIds = new Set(data.batches.map((batch) => batch.id))
  if (currentBatchId && batchIds.has(currentBatchId)) {
    return currentBatchId
  }
  return data.batches[0]?.id ?? ''
}

const loadTaskPool = async () => {
  loading.value = true
  error.value = ''
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
const currentTasks = computed(() => qcTasks.value.filter((task) => task.batchId === selectedBatch.value?.id))

const statusType = (status: string) => {
  if (status === 'new') return 'info'
  if (status === 'assigned') return 'warning'
  if (status === 'in_review') return 'primary'
  return 'success'
}

const dispatchTag = (mode: string) => (mode === 'full' ? 'success' : 'warning')
const activeTaskCount = computed(() => currentTasks.value.filter((task) => task.isActive).length)
const supersededTaskCount = computed(() => currentTasks.value.filter((task) => !task.isActive).length)
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
</script>

<template>
  <AppLayout>
    <div class="page-stack">
      <section class="page-title-row database-hero">
        <div>
          <el-tag type="warning" effect="light">QC Queue Detail</el-tag>
          <h1>任务明细中心</h1>
          <p>这里仅保留当前批次任务明细、锁状态和进入人工质检入口。任务生成与批量派发已迁移到工作台。</p>
        </div>
        <div class="toolbar-actions">
          <el-select v-model="selectedBatchId" filterable style="width: 220px" :loading="loading">
            <el-option v-for="b in batches" :key="b.id" :label="b.name" :value="b.id" />
          </el-select>
          <router-link to="/dashboard"><el-button type="primary" plain>返回工作台派发</el-button></router-link>
        </div>
      </section>

      <el-alert v-if="error" type="error" :closable="false" :title="error" />

      <el-row :gutter="18" v-loading="loading" class="task-pool-summary-row">
        <el-col :span="6"><el-card shadow="never" class="stat-card accent-blue task-pool-stat-card"><span>当前活跃任务</span><strong>{{ activeTaskCount }}</strong><small>当前派发版本</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="stat-card accent-orange task-pool-stat-card"><span>待派发</span><strong>{{ dispatchPreview?.pendingAssignCount ?? 0 }}</strong><small>pending_assign</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="stat-card accent-purple task-pool-stat-card"><span>进行中</span><strong>{{ dispatchPreview?.inReviewTaskCount ?? 0 }}</strong><small>active review lock</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="stat-card accent-green task-pool-stat-card"><span>已退役旧任务</span><strong>{{ supersededTaskCount }}</strong><small>superseded</small></el-card></el-col>
      </el-row>

      <el-card shadow="never" class="product-card task-pool-table-card" v-loading="loading">
        <template #header>
          <div class="card-header"><span>QC 任务明细</span><el-tag type="success">只读排障与进入质检</el-tag></div>
        </template>
        <el-table :data="currentTasks" stripe height="520" scrollbar-always-on>
          <el-table-column prop="id" label="任务ID" width="150" />
          <el-table-column prop="episodeId" label="Episode" min-width="150" />
          <el-table-column prop="taskName" label="任务类型" min-width="150" />
          <el-table-column prop="batchName" label="批次" min-width="180" />
          <el-table-column label="派发版本" width="100">
            <template #default="{ row }">#{{ row.dispatchGeneration }}</template>
          </el-table-column>
          <el-table-column label="活跃" width="90">
            <template #default="{ row }"><el-tag :type="row.isActive ? 'success' : 'info'">{{ row.isActive ? 'active' : 'superseded' }}</el-tag></template>
          </el-table-column>
          <el-table-column label="派发模式" width="110">
            <template #default="{ row }"><el-tag :type="dispatchTag(row.dispatchMode)" size="small">{{ row.dispatchMode === 'full' ? '全量' : `抽检 ${row.samplingRatio}%` }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="assignee" label="审核员" width="120" />
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
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <router-link :to="`/manual-qc/${row.episodeId}`"><el-button link type="primary">进入质检</el-button></router-link>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
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
