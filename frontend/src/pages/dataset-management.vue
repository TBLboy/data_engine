<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import AppLayout from '../components/AppLayout.vue'
import type {
  DatasetTaskSummary,
  DatasetBatchRow,
  DatasetEpisodeRow,
  DatasetExportJob,
  TaskType
} from '../types/qc'
import {
  fetchDatasetTasks,
  fetchDatasetTaskSummary,
  fetchDatasetTaskBatches,
  fetchDatasetTaskEpisodes,
  exportDatasetEpisodes,
  recomputeBatchDecision,
  recomputeTaskBatchDecisions,
  fetchExportHistory,
} from '../api/client'

const tasks = ref<TaskType[]>([])
const selectedTaskId = ref('')
const summary = ref<DatasetTaskSummary | null>(null)
const batches = ref<DatasetBatchRow[]>([])
const episodes = ref<DatasetEpisodeRow[]>([])
const episodeTotal = ref(0)
const episodePage = ref(1)
const episodePageSize = 50
const loading = ref(true)
const exportLoading = ref(false)
const recomputingTask = ref(false)
const selectedBatches = ref<DatasetBatchRow[]>([])
const exportHistory = ref<DatasetExportJob[]>([])

const statusFilter = ref('')
const batchFilter = ref('')
const sourceFilter = ref('')
const manualQcFilter = ref('')

async function loadTasks() {
  loading.value = true
  try {
    tasks.value = await fetchDatasetTasks()
    if (tasks.value.length && !selectedTaskId.value) {
      selectedTaskId.value = tasks.value[0].id
    }
  } finally {
    loading.value = false
  }
}

async function loadData() {
  if (!selectedTaskId.value) return
  loading.value = true
  try {
    const [s, b, h] = await Promise.all([
      fetchDatasetTaskSummary(selectedTaskId.value),
      fetchDatasetTaskBatches(selectedTaskId.value),
      fetchExportHistory(selectedTaskId.value),
    ])
    summary.value = s
    batches.value = b
    exportHistory.value = h
  } catch {
    ElMessage.error('加载数据失败')
  } finally {
    loading.value = false
  }
  await loadEpisodes()
}

async function recomputeCurrentTaskBatches(options: { silent?: boolean } = {}) {
  if (!selectedTaskId.value) return false
  recomputingTask.value = true
  try {
    const result = await recomputeTaskBatchDecisions(selectedTaskId.value)
    if (!options.silent) {
      ElMessage.success(`已自动重判 ${result.refreshedBatchCount} 个批次`)
    }
    return true
  } catch {
    ElMessage.error('自动重判失败')
    return false
  } finally {
    recomputingTask.value = false
  }
}

async function loadTaskDataWithRecompute(options: { silent?: boolean } = {}) {
  if (!selectedTaskId.value) return
  await recomputeCurrentTaskBatches(options)
  await loadData()
}

async function loadEpisodes() {
  if (!selectedTaskId.value) return
  try {
    const result = await fetchDatasetTaskEpisodes(selectedTaskId.value, {
      status: statusFilter.value || undefined,
      batchId: batchFilter.value || undefined,
      finalDecisionSource: sourceFilter.value || undefined,
      manualQcStatus: manualQcFilter.value || undefined,
      page: episodePage.value,
      pageSize: episodePageSize,
    })
    episodes.value = result.items
    episodeTotal.value = result.total
  } catch {
    ElMessage.error('加载 Episode 列表失败')
  }
}

async function onTaskChange() {
  episodePage.value = 1
  selectedBatches.value = []
  await loadTaskDataWithRecompute()
}

async function onFilterChange() {
  episodePage.value = 1
  await loadEpisodes()
}

async function onEpisodePageChange(page: number) {
  episodePage.value = page
  await loadEpisodes()
}

async function doExport(format: string) {
  if (!selectedTaskId.value) return
  exportLoading.value = true
  try {
    const batchIds = selectedBatches.value.length
      ? selectedBatches.value.map(b => b.batchId)
      : undefined
    const resp = await exportDatasetEpisodes(selectedTaskId.value, format, batchIds)
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const ext = format === 'jsonl' ? 'zip' : format
    link.download = `qualified_episodes_${selectedTaskId.value}.${ext}`
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出完成')
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exportLoading.value = false
  }
}

async function doRecompute(batchId: string) {
  try {
    const result = await recomputeBatchDecision(batchId)
    ElMessage.success(`批次 ${batchId} 已重判：${result.batchDecision}，失败率 ${result.failureRate}`)
    await loadData()
  } catch {
    ElMessage.error('重算失败')
  }
}

const decisionTagType = (d: string) => {
  if (d === 'ACCEPTED') return 'success'
  if (d === 'REJECTED') return 'danger'
  return 'info'
}

const decisionLabel = (d: string) => {
  if (d === 'ACCEPTED') return '通过'
  if (d === 'REJECTED') return '驳回'
  return '待定'
}

const statusTagType = (s: string) => {
  if (s === 'QUALIFIED') return 'success'
  if (s === 'UNQUALIFIED') return 'danger'
  return 'info'
}

const statusLabel = (s: string) => {
  if (s === 'QUALIFIED') return '可用于训练'
  if (s === 'UNQUALIFIED') return '不可用于训练'
  return '待最终判定'
}

const annotationStatusLabel = (s: string) => {
  const map: Record<string, string> = {
    not_created: '未创建',
    pending: '待标注',
    assigned: '已分配',
    in_progress: '标注中',
    completed: '已完成',
    invalidated: '已失效',
    revision_missing: 'revision 缺失',
  }
  return map[s] || s
}

const sourceLabel = (s: string) => {
  const map: Record<string, string> = {
    'PENDING_NOT_ADJUDICATED': '批次尚未判定',
    'MANUAL_PASS': '人工判定合格',
    'MANUAL_FAIL': '人工判定不合格',
    'BATCH_ACCEPT_INFERRED_PASS': '批次通过，未抽检推断合格',
    'BATCH_REJECT_PROPAGATED_FAIL': '批次驳回，连带不合格',
    'BATCH_REJECT_OVERRIDE_MANUAL_PASS': '人工合格，但批次驳回',
  }
  return map[s] || s
}

const manualQcLabel = (s: string) => {
  if (s === 'MANUAL_PASS') return '人工合格'
  if (s === 'MANUAL_FAIL') return '人工不合格'
  return '未质检'
}

onMounted(async () => {
  await loadTasks()
  if (selectedTaskId.value) {
    await loadTaskDataWithRecompute({ silent: true })
  }
})
</script>

<template>
  <AppLayout>
    <div class="page-stack">
      <section class="page-title-row">
        <div>
          <el-tag type="success" effect="light">训练数据消费</el-tag>
          <h1>训练数据集管理</h1>
          <p>按任务查看合格数据数量、批次状态、导出合格 episode 元数据清单</p>
        </div>
        <div class="toolbar-actions">
          <el-select v-model="selectedTaskId" style="width: 240px" class="qc-select" @change="onTaskChange">
            <el-option v-for="t in tasks" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
          <el-tag v-if="recomputingTask" type="warning" effect="light">正在自动重判</el-tag>
        </div>
      </section>

      <!-- Stats cards -->
      <el-row :gutter="18" v-loading="loading" v-if="summary">
        <el-col :span="6">
          <el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-green">
            <span>质检合格 / 完成标注</span>
            <strong>{{ summary.qualifiedEpisodeCount }} / {{ summary.annotationCompletedEpisodeCount }}</strong>
            <small v-if="summary.annotationCoverageRate != null" style="display:block;margin-top:6px;color:#909399">
              标注覆盖率 {{ (summary.annotationCoverageRate * 100).toFixed(1) }}%
            </small>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-blue">
            <span>Episode 总数</span>
            <strong>{{ summary.totalEpisodeCount }}</strong>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-orange">
            <span>批次通过 / 驳回</span>
            <strong>{{ summary.acceptedBatchCount }} / {{ summary.rejectedBatchCount }}</strong>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-purple">
            <span>人工不合格 / 合格</span>
            <strong>{{ summary.manualFailCount }} / {{ summary.manualPassCount }}</strong>
          </el-card>
        </el-col>
      </el-row>

      <!-- Decision source breakdown -->
      <el-row :gutter="18" v-loading="loading" v-if="summary">
        <el-col :span="24">
          <el-card shadow="never" class="qc-card">
            <template #header>
              <div class="card-header">
                <span>判定来源分布</span>
                <div class="toolbar-actions">
                  <span v-if="selectedBatches.length" style="color:#909399;font-size:13px;margin-right:8px">已选 {{ selectedBatches.length }} 个批次</span>
                  <el-button :loading="exportLoading" @click="doExport('csv')">导出 CSV</el-button>
                  <el-button :loading="exportLoading" @click="doExport('json')">导出 JSON</el-button>
                  <el-button :loading="exportLoading" type="primary" @click="doExport('jsonl')">导出 JSONL 包</el-button>
                </div>
              </div>
            </template>
            <el-descriptions :column="5" border>
              <el-descriptions-item label="人工判定合格">{{ summary.manualPassCount }}</el-descriptions-item>
              <el-descriptions-item label="人工判定不合格">{{ summary.manualFailCount }}</el-descriptions-item>
              <el-descriptions-item label="推断合格 (未抽检)">{{ summary.inferredPassCount }}</el-descriptions-item>
              <el-descriptions-item label="连带不合格 (批次驳回)">{{ summary.propagatedFailCount }}</el-descriptions-item>
              <el-descriptions-item label="人工合格但批次驳回">{{ summary.overrideManualPassFailCount }}</el-descriptions-item>
              <el-descriptions-item label="已完成标注">{{ summary.annotationCompletedEpisodeCount }}</el-descriptions-item>
              <el-descriptions-item label="待完成标注">{{ summary.annotationPendingEpisodeCount }}</el-descriptions-item>
            </el-descriptions>
            <el-alert
              type="info"
              :closable="false"
              show-icon
              title="导出范围：全部质检合格 Episode。未完成标注的数据仍会导出，并标记 annotationCompleted=false。"
              style="margin-top: 14px"
            />
          </el-card>
        </el-col>
      </el-row>

      <!-- Batch summary table -->
      <el-row :gutter="18" v-loading="loading" v-if="batches.length">
        <el-col :span="24">
          <el-card shadow="never" class="qc-card">
            <template #header>
              <span>批次汇总</span>
              <small style="color: #909399; margin-left: 12px">失败率 = 人工不合格数 / 抽检数</small>
            </template>
            <el-table :data="batches" stripe class="qc-table" height="320" @selection-change="(rows: DatasetBatchRow[]) => selectedBatches = rows">
              <el-table-column type="selection" width="40" />
              <el-table-column prop="batchName" label="批次" min-width="160" />
              <el-table-column prop="totalCount" label="总数" width="80" />
              <el-table-column prop="sampledCount" label="抽检" width="70" />
              <el-table-column prop="reviewedCount" label="已质检" width="70" />
              <el-table-column prop="manualFailCount" label="人工失败" width="80" />
              <el-table-column label="失败率" width="100">
                <template #default="{ row }">
                  {{ row.failureRate != null ? (row.failureRate * 100).toFixed(1) + '%' : '-' }}
                </template>
              </el-table-column>
              <el-table-column label="判定" width="100">
                <template #default="{ row }">
                  <el-tag :type="decisionTagType(row.batchDecision)">{{ decisionLabel(row.batchDecision) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="availableEpisodeCount" label="可用数" width="80" />
              <el-table-column label="操作" width="100">
                <template #default="{ row }">
                  <el-button size="small" text type="primary" @click="doRecompute(row.batchId)">重判</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
      </el-row>

      <!-- Export history -->
      <el-row :gutter="18" v-if="exportHistory.length">
        <el-col :span="24">
          <el-card shadow="never" class="qc-card">
            <template #header><span>导出历史</span></template>
            <el-table :data="exportHistory" stripe class="qc-table" height="200">
              <el-table-column prop="id" label="ID" width="70" />
              <el-table-column prop="exportFormat" label="格式" width="80">
                <template #default="{ row }">
                  <el-tag size="small">{{ row.exportFormat.toUpperCase() }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="episodeCount" label="导出数量" width="100" />
              <el-table-column prop="createdBy" label="导出人" width="120" />
              <el-table-column label="导出时间" min-width="160">
                <template #default="{ row }">{{ row.createdAt || '-' }}</template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
      </el-row>

      <!-- Episode list -->
      <el-row :gutter="18" v-loading="loading">
        <el-col :span="24">
          <el-card shadow="never" class="qc-card">
            <template #header>
              <div class="card-header">
                <span>Episode 列表</span>
                <div class="toolbar-actions">
                  <el-select v-model="statusFilter" placeholder="最终状态" class="qc-select" style="width: 140px" clearable @change="onFilterChange">
                    <el-option label="可用于训练" value="QUALIFIED" />
                    <el-option label="不可用于训练" value="UNQUALIFIED" />
                    <el-option label="待最终判定" value="PENDING" />
                  </el-select>
                  <el-select v-model="sourceFilter" placeholder="判定来源" class="qc-select" style="width: 160px" clearable @change="onFilterChange">
                    <el-option label="人工判定合格" value="MANUAL_PASS" />
                    <el-option label="人工判定不合格" value="MANUAL_FAIL" />
                    <el-option label="批次通过推断合格" value="BATCH_ACCEPT_INFERRED_PASS" />
                    <el-option label="批次驳回连带不合格" value="BATCH_REJECT_PROPAGATED_FAIL" />
                    <el-option label="人工合格但批次驳回" value="BATCH_REJECT_OVERRIDE_MANUAL_PASS" />
                  </el-select>
                  <el-select v-model="manualQcFilter" placeholder="人工质检" class="qc-select" style="width: 120px" clearable @change="onFilterChange">
                    <el-option label="人工合格" value="MANUAL_PASS" />
                    <el-option label="人工不合格" value="MANUAL_FAIL" />
                    <el-option label="未质检" value="NOT_REVIEWED" />
                  </el-select>
                </div>
              </div>
            </template>
            <el-table :data="episodes" stripe class="qc-table" height="400">
              <el-table-column prop="episodeId" label="Episode" min-width="160" />
              <el-table-column prop="batchName" label="批次" min-width="140" />
              <el-table-column label="最终状态" width="140">
                <template #default="{ row }">
                  <el-tag :type="statusTagType(row.finalDatasetStatus)">{{ statusLabel(row.finalDatasetStatus) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="是否完成标注" width="120">
                <template #default="{ row }">
                  <el-tag :type="row.annotationCompleted ? 'success' : 'info'" size="small">
                    {{ row.annotationCompleted ? '是' : '否' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="标注状态" width="120">
                <template #default="{ row }">{{ annotationStatusLabel(row.annotationStatus) }}</template>
              </el-table-column>
              <el-table-column label="判定来源" min-width="180">
                <template #default="{ row }">{{ sourceLabel(row.finalDecisionSource) }}</template>
              </el-table-column>
              <el-table-column label="人工质检" width="100">
                <template #default="{ row }">{{ manualQcLabel(row.manualQcStatus) }}</template>
              </el-table-column>
              <el-table-column prop="durationSec" label="时长 (秒)" width="90" />
              <el-table-column label="最终判定时间" min-width="160">
                <template #default="{ row }">{{ row.finalDecidedAt || '-' }}</template>
              </el-table-column>
            </el-table>
            <div style="display:flex; justify-content:center; margin-top:12px">
              <el-pagination
                v-if="episodeTotal > episodePageSize"
                v-model:current-page="episodePage"
                :page-size="episodePageSize"
                :total="episodeTotal"
                layout="prev, pager, next"
                size="small"
                @current-change="onEpisodePageChange"
              />
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </AppLayout>
</template>
