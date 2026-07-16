<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import AppLayout from '../components/AppLayout.vue'
import { fetchDataAssetBatches, fetchDataAssetSummary, fetchDataAssetTasks, fetchDatabase, rebuildDataAssets, scanDatabase, type DatabasePayload } from '../api/client'
import { useSessionStore } from '../stores/session'
import type { BatchSummary, DataAssetBatchRow, DataAssetSummary, DataAssetTaskRow } from '../types/qc'
import { reasonLabel } from '../utils/reasonLabels'

const session = useSessionStore()

const payload = ref<DatabasePayload | null>(null)
const summary = ref<DataAssetSummary | null>(null)
const batchAssetItems = ref<DataAssetBatchRow[]>([])
const batchAssetTotal = ref(0)
const activeBatchAsset = ref<DataAssetBatchRow | null>(null)
const taskAssetItems = ref<DataAssetTaskRow[]>([])
const taskAssetTotal = ref(0)
const activeTaskAsset = ref<DataAssetTaskRow | null>(null)

const databaseLoading = ref(true)
const assetLoading = ref(true)
const databaseError = ref('')
const summaryError = ref('')
const batchAssetError = ref('')
const taskAssetError = ref('')
const scanning = ref(false)
const rebuilding = ref(false)
const batchAssetDrawerVisible = ref(false)
const taskAssetDrawerVisible = ref(false)

const episodeKeyword = ref('')
const batchAssetKeyword = ref('')
const taskAssetKeyword = ref('')
const status = ref('')
const result = ref('')
const batch = ref('')
const page = ref(1)
const pageSize = ref(100)

const batchAssetPage = ref(1)
const batchAssetPageSize = ref(20)
const batchAssetTaskTypeId = ref('')
const batchAssetDecision = ref('')
const batchAssetQcStatus = ref('')

const taskAssetPage = ref(1)
const taskAssetPageSize = ref(20)
const taskAssetIncludeInactive = ref(false)
const taskAssetStaleOnly = ref(false)

let episodeKeywordTimer: ReturnType<typeof setTimeout> | null = null
let batchAssetKeywordTimer: ReturnType<typeof setTimeout> | null = null
let taskAssetKeywordTimer: ReturnType<typeof setTimeout> | null = null

const scanForm = reactive({
  bucket: 'yaocao',
  scope: 'full'
})

const canScanDatabase = computed(() => ['admin', 'qc_manager'].includes(session.user?.role ?? 'viewer'))

const formatError = (err: unknown, fallback: string) => {
  if (!(err instanceof Error)) return fallback
  try {
    const parsed = JSON.parse(err.message) as { detail?: string }
    return parsed.detail || fallback
  } catch {
    return err.message || fallback
  }
}

const loadDatabaseOnly = async () => {
  databaseLoading.value = true
  databaseError.value = ''
  try {
    payload.value = await fetchDatabase({
      page: page.value,
      pageSize: pageSize.value,
      keyword: episodeKeyword.value.trim(),
      batchId: batch.value,
      qcStatus: status.value,
      qcResult: result.value,
    })
  } catch (err) {
    databaseError.value = formatError(err, '加载 Episode 数据总库失败')
  } finally {
    databaseLoading.value = false
  }
}

const loadDataAssets = async () => {
  assetLoading.value = true
  summaryError.value = ''
  batchAssetError.value = ''
  taskAssetError.value = ''

  const [summaryResult, batchesResult, tasksResult] = await Promise.allSettled([
    fetchDataAssetSummary(),
    fetchDataAssetBatches({
      page: batchAssetPage.value,
      pageSize: batchAssetPageSize.value,
      keyword: batchAssetKeyword.value.trim(),
      taskTypeId: batchAssetTaskTypeId.value,
      batchDecision: batchAssetDecision.value,
      qcStatus: batchAssetQcStatus.value,
    }),
    fetchDataAssetTasks({
      page: taskAssetPage.value,
      pageSize: taskAssetPageSize.value,
      keyword: taskAssetKeyword.value.trim(),
      includeInactive: taskAssetIncludeInactive.value,
      staleOnly: taskAssetStaleOnly.value,
      sortBy: 'taskTypeName',
      sortOrder: 'asc',
    }),
  ])

  if (summaryResult.status === 'fulfilled') {
    summary.value = summaryResult.value
  } else {
    summary.value = null
    summaryError.value = formatError(summaryResult.reason, '加载数据资产概览失败')
  }

  if (batchesResult.status === 'fulfilled') {
    batchAssetItems.value = batchesResult.value.items
    batchAssetTotal.value = batchesResult.value.total
  } else {
    batchAssetItems.value = []
    batchAssetTotal.value = 0
    batchAssetError.value = formatError(batchesResult.reason, '加载批次数据资产失败')
  }

  if (tasksResult.status === 'fulfilled') {
    taskAssetItems.value = tasksResult.value.items
    taskAssetTotal.value = tasksResult.value.total
  } else {
    taskAssetItems.value = []
    taskAssetTotal.value = 0
    taskAssetError.value = formatError(tasksResult.reason, '加载任务数据资产失败')
  }

  assetLoading.value = false
}

const loadPage = async () => {
  await Promise.all([loadDatabaseOnly(), loadDataAssets()])
}

const submitScan = async () => {
  scanning.value = true
  try {
    const job = await scanDatabase({
      bucket: scanForm.bucket.trim(),
      scope: scanForm.scope,
    })
    ElMessage.success(`扫描完成：${job.detail}`)
    await loadPage()
  } catch (err) {
    ElMessage.error(formatError(err, '扫描入库失败'))
  } finally {
    scanning.value = false
  }
}

const rebuildAssets = async () => {
  rebuilding.value = true
  try {
    const rebuildResult = await rebuildDataAssets('all')
    ElMessage.success(`资产画像已重建：批次 ${rebuildResult.rebuiltBatchCount}，任务 ${rebuildResult.rebuiltTaskCount}`)
    await loadDataAssets()
  } catch (err) {
    ElMessage.error(formatError(err, '重建资产画像失败'))
  } finally {
    rebuilding.value = false
  }
}

const applyEpisodeBatchFilter = (batchId: string) => {
  batch.value = batchId
  if (page.value !== 1) {
    page.value = 1
  }
}

const clearEpisodeBatchFilter = () => {
  if (!batch.value) return
  batch.value = ''
  if (page.value !== 1) {
    page.value = 1
  }
}

const openBatchAssetDrawer = (row: DataAssetBatchRow) => {
  activeBatchAsset.value = row
  batchAssetDrawerVisible.value = true
}

const openTaskAssetDrawer = (row: DataAssetTaskRow) => {
  activeTaskAsset.value = row
  taskAssetDrawerVisible.value = true
}

const applyTaskToBatchFilter = (taskTypeId: string) => {
  batchAssetTaskTypeId.value = taskTypeId
  if (batchAssetPage.value !== 1) {
    batchAssetPage.value = 1
  }
}

const clearTaskBatchFilter = () => {
  if (!batchAssetTaskTypeId.value) return
  batchAssetTaskTypeId.value = ''
  if (batchAssetPage.value !== 1) {
    batchAssetPage.value = 1
  }
}

const drillTaskToBatches = (row: DataAssetTaskRow) => {
  applyTaskToBatchFilter(row.taskTypeId)
}

const drillTaskToEpisodes = (row: DataAssetTaskRow) => {
  applyTaskToBatchFilter(row.taskTypeId)
  // Episode list still filters by batch; clear batch and keep task context on batch panel.
  if (batch.value) {
    batch.value = ''
    if (page.value !== 1) page.value = 1
  }
}

onMounted(() => {
  void loadPage()
})

onBeforeUnmount(() => {
  if (episodeKeywordTimer) clearTimeout(episodeKeywordTimer)
  if (batchAssetKeywordTimer) clearTimeout(batchAssetKeywordTimer)
  if (taskAssetKeywordTimer) clearTimeout(taskAssetKeywordTimer)
})

watch([batch, status, result, pageSize], () => {
  if (page.value !== 1) {
    page.value = 1
    return
  }
  void loadDatabaseOnly()
})

watch(page, () => {
  void loadDatabaseOnly()
})

watch(episodeKeyword, () => {
  if (episodeKeywordTimer) clearTimeout(episodeKeywordTimer)
  episodeKeywordTimer = setTimeout(() => {
    if (page.value !== 1) {
      page.value = 1
      return
    }
    void loadDatabaseOnly()
  }, 250)
})

watch([batchAssetTaskTypeId, batchAssetDecision, batchAssetQcStatus, batchAssetPageSize], () => {
  if (batchAssetPage.value !== 1) {
    batchAssetPage.value = 1
    return
  }
  void loadDataAssets()
})

watch(batchAssetPage, () => {
  void loadDataAssets()
})

watch(batchAssetKeyword, () => {
  if (batchAssetKeywordTimer) clearTimeout(batchAssetKeywordTimer)
  batchAssetKeywordTimer = setTimeout(() => {
    if (batchAssetPage.value !== 1) {
      batchAssetPage.value = 1
      return
    }
    void loadDataAssets()
  }, 250)
})

watch([taskAssetIncludeInactive, taskAssetStaleOnly, taskAssetPageSize], () => {
  if (taskAssetPage.value !== 1) {
    taskAssetPage.value = 1
    return
  }
  void loadDataAssets()
})

watch(taskAssetPage, () => {
  void loadDataAssets()
})

watch(taskAssetKeyword, () => {
  if (taskAssetKeywordTimer) clearTimeout(taskAssetKeywordTimer)
  taskAssetKeywordTimer = setTimeout(() => {
    if (taskAssetPage.value !== 1) {
      taskAssetPage.value = 1
      return
    }
    void loadDataAssets()
  }, 250)
})

const episodes = computed(() => payload.value?.episodes ?? [])
const batches = computed(() => payload.value?.batches ?? [])
const taskTypes = computed(() => payload.value?.taskTypes ?? [])
const ingestJobs = computed(() => payload.value?.ingestJobs ?? [])
const totalEpisodes = computed(() => payload.value?.totalEpisodes ?? 0)

const statisticsScopeLabel = computed(() => {
  if (!summary.value?.statisticsScope) return 'active list / active batch / indexed episodes'
  if (summary.value.statisticsScope === 'active_list_active_batch_indexed_episodes') {
    return 'active list / active batch / indexed episodes'
  }
  return summary.value.statisticsScope
})

const summaryFreshnessText = computed(() => {
  if (!summary.value) return '批次级投影未加载'
  const freshness = summary.value.freshness
  if (!freshness.oldestRefreshedAt && !freshness.newestRefreshedAt) return '批次级投影尚未刷新'
  if (freshness.oldestRefreshedAt === freshness.newestRefreshedAt) return `最近刷新 ${freshness.newestRefreshedAt}`
  return `刷新窗口 ${freshness.oldestRefreshedAt} ~ ${freshness.newestRefreshedAt}`
})

const selectedBatchName = computed(() => {
  if (!batch.value) return ''
  const fromDatabase = batches.value.find((item: BatchSummary) => item.id === batch.value)
  if (fromDatabase) return fromDatabase.name
  const fromAssets = batchAssetItems.value.find((item) => item.batchId === batch.value)
  return fromAssets?.batchName ?? batch.value
})

const activeBatchCoverage = computed(() => {
  if (!activeBatchAsset.value) return { duration: '-', frames: '-' }
  return {
    duration: `${activeBatchAsset.value.durationCoveredEpisodeCount} / ${activeBatchAsset.value.episodeCount}`,
    frames: `${activeBatchAsset.value.frameCoveredEpisodeCount} / ${activeBatchAsset.value.episodeCount}`,
  }
})

const activeBatchFailureRateText = computed(() => {
  if (!activeBatchAsset.value) return '待判定'
  return formatPercent(activeBatchAsset.value.failureRate)
})

const activeBatchRejectThresholdText = computed(() => {
  if (!activeBatchAsset.value) return '待配置'
  return formatPercent(activeBatchAsset.value.rejectThreshold)
})

const assetMetricText = (value: number | null | undefined, formatter: (val: number) => string = (val) => String(val)) => {
  if (summaryError.value || value === null || value === undefined) return '—'
  return formatter(value)
}

const formatDurationHours = (seconds: number) => `${(seconds / 3600).toFixed(1)} 小时`
const formatInteger = (value: number) => new Intl.NumberFormat('zh-CN').format(value)
const formatPercent = (value: number | null | undefined) => {
  if (value === null || value === undefined) return '待判定'
  return `${(value * 100).toFixed(1)}%`
}

const decisionLabel = (value: string) => {
  if (value === 'ACCEPTED') return '批次可用'
  if (value === 'REJECTED') return '批次驳回'
  return '待判定'
}

const decisionTagType = (value: string) => {
  if (value === 'ACCEPTED') return 'success'
  if (value === 'REJECTED') return 'danger'
  return 'info'
}

const qcStatusLabel = (value: string) => {
  if (value === 'assigned') return '已派发'
  if (value === 'in_review') return '审核中'
  if (value === 'done') return '已完成'
  if (value === 'blocked') return '阻塞'
  return '未派发'
}

const qcStatusTagType = (value: string) => {
  if (value === 'done') return 'success'
  if (value === 'in_review') return 'warning'
  if (value === 'blocked') return 'danger'
  if (value === 'assigned') return ''
  return 'info'
}

const reviewedText = (row: DataAssetBatchRow) => `${row.reviewedCount} / ${row.episodeCount}`
const rateText = (value: number | null | undefined) => {
  if (value === null || value === undefined) return '—'
  return `${(value * 100).toFixed(1)}%`
}
const selectedTaskName = computed(() => {
  if (!batchAssetTaskTypeId.value) return ''
  const fromTasks = taskAssetItems.value.find((item) => item.taskTypeId === batchAssetTaskTypeId.value)
  if (fromTasks) return fromTasks.taskTypeName
  const fromTypes = taskTypes.value.find((item) => item.id === batchAssetTaskTypeId.value)
  return fromTypes?.name ?? batchAssetTaskTypeId.value
})
const ingestStatusType = (statusValue: string) => {
  if (statusValue === 'done') return 'success'
  if (statusValue === 'failed') return 'danger'
  if (statusValue === 'scanning') return 'warning'
  return 'info'
}

const durationCoverageText = computed(() => {
  if (!summary.value || summaryError.value) return '覆盖数据暂不可用'
  return `${summary.value.durationCoveredEpisodeCount} / ${summary.value.episodeCount}，缺失 ${summary.value.durationMissingEpisodeCount}`
})

const frameCoverageText = computed(() => {
  if (!summary.value || summaryError.value) return '覆盖数据暂不可用'
  return `${summary.value.frameCoveredEpisodeCount} / ${summary.value.episodeCount}，缺失 ${summary.value.frameMissingEpisodeCount}`
})
</script>

<template>
  <AppLayout>
    <div class="page-stack">
      <section class="page-title-row database-hero">
        <div>
          <el-tag type="success" effect="light">Indexed Data Catalog</el-tag>
          <h1>数据总库</h1>
          <p>按 Episode、批次、任务三级资产视角查看采集数据规模、覆盖率、质检进度与最终可用性。</p>
        </div>
        <div class="toolbar-actions">
          <el-button v-if="canScanDatabase" plain :loading="rebuilding" @click="rebuildAssets">重建资产画像</el-button>
          <el-tag type="info" effect="light">{{ statisticsScopeLabel }}</el-tag>
        </div>
      </section>

      <el-alert v-if="databaseError" type="error" :closable="false" :title="databaseError" />
      <el-alert v-if="summaryError" type="warning" :closable="false" :title="summaryError" />
      <el-alert v-if="batchAssetError" type="warning" :closable="false" :title="batchAssetError" />
      <el-alert v-if="taskAssetError" type="warning" :closable="false" :title="taskAssetError" />

      <section class="stats-grid" v-loading="assetLoading">
        <el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-blue">
          <span>已索引 Episodes</span>
          <strong>{{ assetMetricText(summary?.episodeCount, formatInteger) }}</strong>
          <small>{{ summaryError ? '数据资产接口异常，未回退到筛选结果' : statisticsScopeLabel }}</small>
        </el-card>
        <el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-green">
          <span>数据总时长</span>
          <strong>{{ assetMetricText(summary?.totalDurationSec !== undefined ? Math.round(summary.totalDurationSec) : undefined, formatInteger) }}</strong>
          <small>{{ summaryError ? '总时长暂不可用' : `${formatDurationHours(summary?.totalDurationSec ?? 0)}，覆盖 ${durationCoverageText}` }}</small>
        </el-card>
        <el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-orange">
          <span>数据总帧数</span>
          <strong>{{ assetMetricText(summary?.totalFrameCount, formatInteger) }}</strong>
          <small>{{ summaryError ? '总帧数暂不可用' : `已解析有效帧，覆盖 ${frameCoverageText}` }}</small>
        </el-card>
        <el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-purple">
          <span>任务类型</span>
          <strong>{{ assetMetricText(summary?.taskTypeCount, formatInteger) }}</strong>
          <small>{{ summaryError ? '任务类型统计暂不可用' : statisticsScopeLabel }}</small>
        </el-card>
        <el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-blue">
          <span>失败原因种类</span>
          <strong>{{ assetMetricText(summary?.failureReasonCount, formatInteger) }}</strong>
          <small>{{ summaryError ? '失败原因统计暂不可用' : '已出现的失败原因编码' }}</small>
        </el-card>
        <el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-green">
          <span>批次数量</span>
          <strong>{{ assetMetricText(summary?.batchCount, formatInteger) }}</strong>
          <small>{{ summaryError ? '批次统计暂不可用' : `${summaryFreshnessText}，stale ${summary?.freshness?.staleBatchCount ?? 0}` }}</small>
        </el-card>
      </section>

      <el-row :gutter="18">
        <el-col v-if="canScanDatabase" :span="9">
          <el-card shadow="never" class="qc-card filter-card">
            <template #header>扫描 MinIO</template>
            <div class="filter-grid">
              <el-input v-model="scanForm.bucket" placeholder="输入 MinIO bucket 名称" class="qc-input" clearable />
              <el-select v-model="scanForm.scope" class="qc-select" placeholder="扫描范围">
                <el-option label="全量扫描" value="full" />
              </el-select>
              <el-button type="primary" :loading="scanning" @click="submitScan">扫描入库</el-button>
            </div>
            <div class="hint-text">
              当前扫描直接面向 MinIO 数据湖，默认 bucket 为
              <code>yaocao</code>
              ，scope 目前保留
              <code>full</code>
              全量扫描语义。
            </div>
          </el-card>
        </el-col>
        <el-col :span="canScanDatabase ? 15 : 24">
          <el-card shadow="never" class="qc-card" v-loading="databaseLoading">
            <template #header>最近扫描任务</template>
            <el-table :data="ingestJobs" stripe class="qc-table" height="240">
              <el-table-column prop="bucket" label="Bucket" min-width="150" />
              <el-table-column prop="scope" label="范围" width="110" />
              <el-table-column label="状态" width="110">
                <template #default="{ row }">
                  <el-tag :type="ingestStatusType(row.status)">{{ row.status }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="confirmedLists" label="列表" width="80" />
              <el-table-column prop="totalEpisodes" label="Episodes" width="90" />
              <el-table-column prop="newEpisodes" label="新增" width="80" />
              <el-table-column prop="detail" label="详情" min-width="180" show-overflow-tooltip />
              <el-table-column prop="startedAt" label="开始时间" width="160" />
            </el-table>
          </el-card>
        </el-col>
      </el-row>

      <el-card shadow="never" class="qc-card filter-card">
        <div class="filter-grid">
          <el-input v-model="episodeKeyword" placeholder="搜索 episode / batch / reason / reviewer" class="qc-input" clearable />
          <el-select v-model="batch" placeholder="批次" class="qc-select" clearable filterable>
            <el-option v-for="item in batches" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
          <el-select v-model="status" placeholder="QC 状态" class="qc-select" clearable filterable>
            <el-option label="未派发" value="new" />
            <el-option label="已派发" value="assigned" />
            <el-option label="审核中" value="in_review" />
            <el-option label="已完成" value="done" />
          </el-select>
          <el-select v-model="result" placeholder="最终状态" class="qc-select" clearable filterable>
            <el-option label="可用于训练" value="QUALIFIED" />
            <el-option label="不可用于训练" value="UNQUALIFIED" />
            <el-option label="待最终判定" value="PENDING" />
          </el-select>
        </div>
      </el-card>

      <el-card shadow="never" class="qc-card episode-table-card" v-loading="databaseLoading">
        <template #header>
          <div class="card-header-with-meta">
            <div>
              <strong>Episode 数据资产</strong>
              <div class="table-subtitle">保留现有 Episode 列表、分页、筛选和查看能力</div>
            </div>
            <div v-if="batch" class="active-filter-bar">
              <span>当前批次：{{ selectedBatchName }}</span>
              <el-button link type="primary" @click="clearEpisodeBatchFilter">清除筛选</el-button>
            </div>
          </div>
        </template>
        <el-table :data="episodes" stripe height="620" class="qc-table" scrollbar-always-on>
          <el-table-column prop="id" label="Episode" min-width="150" fixed />
          <el-table-column prop="taskName" label="任务类型" min-width="160" />
          <el-table-column prop="batchName" label="批次" min-width="180" />
          <el-table-column prop="durationSec" label="时长(s)" width="100" />
          <el-table-column prop="frameCount" label="帧数" width="100" />
          <el-table-column label="最终状态" width="120">
            <template #default="{ row }">
              <el-tag v-if="row.finalDatasetStatus === 'QUALIFIED'" type="success">合格</el-tag>
              <el-tag v-else-if="row.finalDatasetStatus === 'UNQUALIFIED'" type="danger">不合格</el-tag>
              <el-tag v-else type="info">待定</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="判定来源" min-width="150">
            <template #default="{ row }">
              <span v-if="row.finalDecisionSource === 'MANUAL_PASS'">人工合格</span>
              <span v-else-if="row.finalDecisionSource === 'MANUAL_FAIL'">人工不合格</span>
              <span v-else-if="row.finalDecisionSource === 'BATCH_ACCEPT_INFERRED_PASS'">批次接受后推断合格</span>
              <span v-else-if="row.finalDecisionSource === 'BATCH_REJECT_PROPAGATED_FAIL'">批次驳回后推断不合格</span>
              <span v-else-if="row.finalDecisionSource === 'BATCH_REJECT_OVERRIDE_MANUAL_PASS'">人工合格但随批次驳回</span>
              <span v-else-if="row.finalDecisionSource === 'PENDING_NOT_ADJUDICATED'">待批次判定</span>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="人工质检" width="100">
            <template #default="{ row }">
              <el-tag v-if="row.qcResult === 'pass'" type="success" size="small">通过</el-tag>
              <el-tag v-else-if="row.qcResult === 'fail'" type="danger" size="small">不通过</el-tag>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column label="原因码" min-width="160">
            <template #default="{ row }">{{ reasonLabel(row.reasonCode) }}</template>
          </el-table-column>
          <el-table-column prop="reviewer" label="审核员" width="120" />
          <el-table-column prop="updatedAt" label="更新时间" min-width="160" />
          <el-table-column label="操作" width="240" fixed="right">
            <template #default="{ row }">
              <router-link :to="`/manual-qc/${row.id}`"><el-button link type="primary">进入质检</el-button></router-link>
              <router-link to="/qc-history"><el-button link>历史审计</el-button></router-link>
            </template>
          </el-table-column>
        </el-table>
        <div class="database-pagination-row">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            background
            layout="total, sizes, prev, pager, next"
            :total="totalEpisodes"
            :page-sizes="[50, 100, 200]"
          />
        </div>
      </el-card>


      <el-card shadow="never" class="qc-card episode-table-card" v-loading="assetLoading">
        <template #header>
          <div class="card-header-with-meta">
            <div>
              <strong>任务数据资产</strong>
              <div class="table-subtitle">按任务汇总批次数、Episode 数、最终可用性与人工质检进度</div>
            </div>
            <div v-if="batchAssetTaskTypeId" class="active-filter-bar">
              <span>当前任务筛选：{{ selectedTaskName }}</span>
              <el-button link type="primary" @click="clearTaskBatchFilter">清除任务筛选</el-button>
            </div>
          </div>
        </template>
        <div class="filter-grid batch-filter-grid">
          <el-input v-model="taskAssetKeyword" placeholder="搜索任务名称 / task type id" class="qc-input" clearable />
          <el-select v-model="taskAssetIncludeInactive" placeholder="是否包含停用任务" class="qc-select">
            <el-option label="仅活跃任务（含待分类）" :value="false" />
            <el-option label="包含停用任务" :value="true" />
          </el-select>
          <el-select v-model="taskAssetStaleOnly" placeholder="刷新状态" class="qc-select">
            <el-option label="全部任务" :value="false" />
            <el-option label="仅 stale" :value="true" />
          </el-select>
        </div>
        <el-table :data="taskAssetItems" stripe class="qc-table" height="420" scrollbar-always-on>
          <el-table-column label="任务名称" min-width="180">
            <template #default="{ row }">
              <el-button link type="primary" class="batch-name-button" @click="drillTaskToBatches(row)">{{ row.taskTypeName }}</el-button>
            </template>
          </el-table-column>
          <el-table-column prop="batchCount" label="批次数" width="90" />
          <el-table-column prop="episodeCount" label="Episode 数" width="110" />
          <el-table-column label="最终可用" width="100">
            <template #default="{ row }">{{ row.qualifiedCount }}</template>
          </el-table-column>
          <el-table-column label="最终不可用" width="110">
            <template #default="{ row }">{{ row.unqualifiedCount }}</template>
          </el-table-column>
          <el-table-column label="待裁定" width="90">
            <template #default="{ row }">{{ row.pendingDatasetCount }}</template>
          </el-table-column>
          <el-table-column label="最终可用率" width="110">
            <template #default="{ row }">{{ rateText(row.finalQualifiedRate) }}</template>
          </el-table-column>
          <el-table-column label="人工已质检" width="110">
            <template #default="{ row }">{{ row.reviewedCount }} / {{ row.episodeCount }}</template>
          </el-table-column>
          <el-table-column label="人工通过率" width="110">
            <template #default="{ row }">{{ rateText(row.manualPassRate) }}</template>
          </el-table-column>
          <el-table-column label="总时长" min-width="140">
            <template #default="{ row }">
              <div>{{ formatInteger(Math.round(row.totalDurationSec)) }} 秒</div>
              <small class="table-meta">覆盖 {{ row.durationCoveredEpisodeCount }} / {{ row.episodeCount }}</small>
            </template>
          </el-table-column>
          <el-table-column label="总帧数" min-width="140">
            <template #default="{ row }">
              <div>{{ formatInteger(row.totalFrameCount) }}</div>
              <small class="table-meta">覆盖 {{ row.frameCoveredEpisodeCount }} / {{ row.episodeCount }}</small>
            </template>
          </el-table-column>
          <el-table-column label="刷新状态" width="110">
            <template #default="{ row }">
              <el-tag :type="row.stale ? 'warning' : 'success'">{{ row.stale ? 'stale' : 'fresh' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="refreshedAt" label="更新时间" min-width="160">
            <template #default="{ row }">{{ row.refreshedAt || '尚未刷新' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <div class="batch-row-actions">
                <el-button link type="primary" @click="drillTaskToBatches(row)">查看批次</el-button>
                <el-button link @click="openTaskAssetDrawer(row)">查看画像</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <div class="database-pagination-row">
          <el-pagination
            v-model:current-page="taskAssetPage"
            v-model:page-size="taskAssetPageSize"
            background
            layout="total, sizes, prev, pager, next"
            :total="taskAssetTotal"
            :page-sizes="[10, 20, 50]"
          />
        </div>
      </el-card>

      <el-card shadow="never" class="qc-card episode-table-card" v-loading="assetLoading">
        <template #header>
          <div class="card-header-with-meta">
            <div>
              <strong>批次数据资产</strong>
              <div class="table-subtitle">按批次查看数据规模、质检进度和最终可用状态</div>
            </div>
            <div v-if="batchAssetTaskTypeId" class="active-filter-bar">
              <span>当前任务：{{ selectedTaskName }}</span>
              <el-button link type="primary" @click="clearTaskBatchFilter">清除任务筛选</el-button>
            </div>
          </div>
        </template>
        <div class="filter-grid batch-filter-grid">
          <el-input v-model="batchAssetKeyword" placeholder="搜索批次名称 / task type / batch id" class="qc-input" clearable />
          <el-select v-model="batchAssetTaskTypeId" placeholder="任务类型" class="qc-select" clearable filterable>
            <el-option v-for="item in taskTypes" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
          <el-select v-model="batchAssetDecision" placeholder="最终判定" class="qc-select" clearable filterable>
            <el-option label="待判定" value="PENDING" />
            <el-option label="已接受" value="ACCEPTED" />
            <el-option label="已驳回" value="REJECTED" />
          </el-select>
          <el-select v-model="batchAssetQcStatus" placeholder="流程状态" class="qc-select" clearable filterable>
            <el-option label="未派发" value="new" />
            <el-option label="已派发" value="assigned" />
            <el-option label="审核中" value="in_review" />
            <el-option label="已完成" value="done" />
          </el-select>
        </div>
        <el-table :data="batchAssetItems" stripe class="qc-table" height="420" scrollbar-always-on>
          <el-table-column label="批次名称" min-width="200">
            <template #default="{ row }">
              <el-button link type="primary" class="batch-name-button" @click="applyEpisodeBatchFilter(row.batchId)">{{ row.batchName }}</el-button>
            </template>
          </el-table-column>
          <el-table-column prop="taskTypeName" label="任务类型" min-width="160" />
          <el-table-column prop="episodeCount" label="Episode 数量" width="110" />
          <el-table-column label="总时长" min-width="150">
            <template #default="{ row }">
              <div>{{ formatInteger(Math.round(row.totalDurationSec)) }} 秒</div>
              <small class="table-meta">覆盖 {{ row.durationCoveredEpisodeCount }} / {{ row.episodeCount }}</small>
            </template>
          </el-table-column>
          <el-table-column label="总帧数" min-width="150">
            <template #default="{ row }">
              <div>{{ formatInteger(row.totalFrameCount) }}</div>
              <small class="table-meta">覆盖 {{ row.frameCoveredEpisodeCount }} / {{ row.episodeCount }}</small>
            </template>
          </el-table-column>
          <el-table-column label="QC 进度" width="120">
            <template #default="{ row }">{{ reviewedText(row) }}</template>
          </el-table-column>
          <el-table-column label="最终判定" width="120">
            <template #default="{ row }">
              <el-tag :type="decisionTagType(row.batchDecision)">{{ row.batchDecision }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="流程状态" width="120">
            <template #default="{ row }">
              <el-tag :type="qcStatusTagType(row.qcStatus)">{{ qcStatusLabel(row.qcStatus) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="updatedAt" label="更新时间" min-width="160">
            <template #default="{ row }">{{ row.updatedAt || '未产生 Episode 更新时间' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="170" fixed="right">
            <template #default="{ row }">
              <div class="batch-row-actions">
                <el-button link type="primary" @click="applyEpisodeBatchFilter(row.batchId)">查看 Episode</el-button>
                <el-button link @click="openBatchAssetDrawer(row)">查看画像</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <div class="database-pagination-row">
          <el-pagination
            v-model:current-page="batchAssetPage"
            v-model:page-size="batchAssetPageSize"
            background
            layout="total, sizes, prev, pager, next"
            :total="batchAssetTotal"
            :page-sizes="[10, 20, 50]"
          />
        </div>
      </el-card>
    </div>

    <el-drawer v-model="batchAssetDrawerVisible" :with-header="false" size="540px">
      <div v-if="activeBatchAsset" class="batch-drawer">
        <div class="batch-drawer-header">
          <div>
            <el-tag type="info" effect="light">批次画像</el-tag>
            <h2>{{ activeBatchAsset.batchName }}</h2>
            <p>批次基础信息、数据规模、质检覆盖和最终判定都在这里闭环查看。</p>
          </div>
          <div class="toolbar-actions">
            <el-button plain @click="applyEpisodeBatchFilter(activeBatchAsset.batchId)">筛选 Episode</el-button>
          </div>
        </div>

        <div class="batch-drawer-grid">
          <div class="drawer-metric">
            <span>任务类型</span>
            <strong>{{ activeBatchAsset.taskTypeName }}</strong>
          </div>
          <div class="drawer-metric">
            <span>流程状态</span>
            <strong>{{ qcStatusLabel(activeBatchAsset.qcStatus) }}</strong>
          </div>
          <div class="drawer-metric">
            <span>最终判定</span>
            <strong>{{ decisionLabel(activeBatchAsset.batchDecision) }}</strong>
          </div>
          <div class="drawer-metric">
            <span>Episode 总数</span>
            <strong>{{ formatInteger(activeBatchAsset.episodeCount) }}</strong>
          </div>
          <div class="drawer-metric">
            <span>总时长</span>
            <strong>{{ formatInteger(Math.round(activeBatchAsset.totalDurationSec)) }} 秒</strong>
          </div>
          <div class="drawer-metric">
            <span>总帧数</span>
            <strong>{{ formatInteger(activeBatchAsset.totalFrameCount) }}</strong>
          </div>
          <div class="drawer-metric">
            <span>时长覆盖</span>
            <strong>{{ activeBatchCoverage.duration }}</strong>
          </div>
          <div class="drawer-metric">
            <span>帧数覆盖</span>
            <strong>{{ activeBatchCoverage.frames }}</strong>
          </div>
          <div class="drawer-metric">
            <span>已质检数</span>
            <strong>{{ activeBatchAsset.reviewedCount }}</strong>
          </div>
          <div class="drawer-metric">
            <span>人工通过数</span>
            <strong>{{ activeBatchAsset.manualPassCount }}</strong>
          </div>
          <div class="drawer-metric">
            <span>人工失败数</span>
            <strong>{{ activeBatchAsset.manualFailCount }}</strong>
          </div>
          <div class="drawer-metric">
            <span>待判定数</span>
            <strong>{{ activeBatchAsset.pendingDatasetCount }}</strong>
          </div>
          <div class="drawer-metric">
            <span>QUALIFIED</span>
            <strong>{{ activeBatchAsset.qualifiedCount }}</strong>
          </div>
          <div class="drawer-metric">
            <span>UNQUALIFIED</span>
            <strong>{{ activeBatchAsset.unqualifiedCount }}</strong>
          </div>
          <div class="drawer-metric">
            <span>失败率</span>
            <strong>{{ activeBatchFailureRateText }}</strong>
          </div>
          <div class="drawer-metric">
            <span>驳回阈值</span>
            <strong>{{ activeBatchRejectThresholdText }}</strong>
          </div>
        </div>

        <div class="drawer-section">
          <div class="drawer-section-title">时间信息</div>
          <div class="drawer-kv-list">
            <div class="drawer-kv-item"><span>创建时间</span><strong>{{ activeBatchAsset.createdAt }}</strong></div>
            <div class="drawer-kv-item"><span>最近 Episode 更新时间</span><strong>{{ activeBatchAsset.updatedAt || '未产生更新时间' }}</strong></div>
            <div class="drawer-kv-item"><span>批次判定时间</span><strong>{{ activeBatchAsset.adjudicatedAt || '尚未判定' }}</strong></div>
            <div class="drawer-kv-item"><span>投影刷新时间</span><strong>{{ activeBatchAsset.refreshedAt || '尚未刷新' }}</strong></div>
          </div>
        </div>

        <div class="drawer-section">
          <div class="drawer-section-title">判定说明</div>
          <div class="drawer-notes">
            {{ activeBatchAsset.batchDecisionReason || '当前批次尚无判定说明。' }}
          </div>
        </div>
      </div>
    </el-drawer>

    <el-drawer v-model="taskAssetDrawerVisible" :with-header="false" size="540px">
      <div v-if="activeTaskAsset" class="batch-drawer">
        <div class="batch-drawer-header">
          <div>
            <el-tag type="info" effect="light">任务画像</el-tag>
            <h2>{{ activeTaskAsset.taskTypeName }}</h2>
            <p>任务级资产规模、最终可用性与人工质检进度在这里闭环查看。</p>
          </div>
          <div class="toolbar-actions">
            <el-button plain @click="drillTaskToBatches(activeTaskAsset)">筛选批次</el-button>
          </div>
        </div>

        <div class="batch-drawer-grid">
          <div class="drawer-metric"><span>批次数</span><strong>{{ formatInteger(activeTaskAsset.batchCount) }}</strong></div>
          <div class="drawer-metric"><span>Episode 数</span><strong>{{ formatInteger(activeTaskAsset.episodeCount) }}</strong></div>
          <div class="drawer-metric"><span>最终可用</span><strong>{{ formatInteger(activeTaskAsset.qualifiedCount) }}</strong></div>
          <div class="drawer-metric"><span>最终不可用</span><strong>{{ formatInteger(activeTaskAsset.unqualifiedCount) }}</strong></div>
          <div class="drawer-metric"><span>待裁定</span><strong>{{ formatInteger(activeTaskAsset.pendingDatasetCount) }}</strong></div>
          <div class="drawer-metric"><span>最终可用率</span><strong>{{ rateText(activeTaskAsset.finalQualifiedRate) }}</strong></div>
          <div class="drawer-metric"><span>人工已质检</span><strong>{{ activeTaskAsset.reviewedCount }} / {{ activeTaskAsset.episodeCount }}</strong></div>
          <div class="drawer-metric"><span>人工通过率</span><strong>{{ rateText(activeTaskAsset.manualPassRate) }}</strong></div>
          <div class="drawer-metric"><span>总时长</span><strong>{{ formatInteger(Math.round(activeTaskAsset.totalDurationSec)) }} 秒</strong></div>
          <div class="drawer-metric"><span>总帧数</span><strong>{{ formatInteger(activeTaskAsset.totalFrameCount) }}</strong></div>
          <div class="drawer-metric"><span>时长覆盖率</span><strong>{{ rateText(activeTaskAsset.durationCoverageRate) }}</strong></div>
          <div class="drawer-metric"><span>帧数覆盖率</span><strong>{{ rateText(activeTaskAsset.frameCoverageRate) }}</strong></div>
          <div class="drawer-metric"><span>已接受批次</span><strong>{{ activeTaskAsset.acceptedBatchCount }}</strong></div>
          <div class="drawer-metric"><span>已驳回批次</span><strong>{{ activeTaskAsset.rejectedBatchCount }}</strong></div>
          <div class="drawer-metric"><span>待判定批次</span><strong>{{ activeTaskAsset.pendingBatchCount }}</strong></div>
          <div class="drawer-metric"><span>刷新状态</span><strong>{{ activeTaskAsset.stale ? 'stale' : 'fresh' }}</strong></div>
        </div>

        <div class="drawer-section">
          <div class="drawer-section-title">时间与版本</div>
          <div class="drawer-kv-list">
            <div class="drawer-kv-item"><span>投影刷新时间</span><strong>{{ activeTaskAsset.refreshedAt || '尚未刷新' }}</strong></div>
            <div class="drawer-kv-item"><span>计算版本</span><strong>{{ activeTaskAsset.calculationVersion }}</strong></div>
            <div class="drawer-kv-item"><span>source watermark</span><strong>{{ activeTaskAsset.sourceWatermark || '-' }}</strong></div>
            <div class="drawer-kv-item"><span>job 状态</span><strong>{{ activeTaskAsset.jobStatus || '-' }}</strong></div>
          </div>
        </div>
      </div>
    </el-drawer>
  </AppLayout>
</template>

<style scoped>
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 18px;
}

.hint-text {
  margin-top: 10px;
  color: #909399;
  font-size: 13px;
  line-height: 1.6;
}

.database-pagination-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.filter-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.batch-filter-grid {
  margin-bottom: 16px;
}

.card-header-with-meta {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.table-subtitle {
  margin-top: 6px;
  color: #64748b;
  font-size: 13px;
}

.active-filter-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #475569;
  font-size: 13px;
}

.table-meta {
  color: #94a3b8;
  font-size: 12px;
}

.batch-name-button {
  padding: 0;
  font-weight: 600;
}

.batch-row-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  line-height: 1.2;
}

.episode-table-card :deep(.el-scrollbar__bar.is-vertical) {
  opacity: 1;
  right: 4px;
  width: 10px;
}

.episode-table-card :deep(.el-scrollbar__thumb) {
  background-color: #4b5563;
}

.episode-table-card :deep(.el-scrollbar__thumb:hover) {
  background-color: #374151;
}

.batch-drawer {
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.batch-drawer-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.batch-drawer-header h2 {
  margin: 10px 0 8px;
  color: #0f172a;
  font-size: 24px;
  line-height: 1.15;
}

.batch-drawer-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.drawer-metric {
  padding: 14px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  background: #f8fafc;
}

.drawer-metric span {
  display: block;
  color: #64748b;
  font-size: 12px;
}

.drawer-metric strong {
  display: block;
  margin-top: 8px;
  color: #0f172a;
  font-size: 18px;
  line-height: 1.3;
}

.drawer-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.drawer-section-title {
  color: #0f172a;
  font-size: 15px;
  font-weight: 700;
}

.drawer-kv-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.drawer-kv-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e2e8f0;
}

.drawer-kv-item span {
  color: #64748b;
  font-size: 13px;
}

.drawer-kv-item strong {
  color: #0f172a;
  font-size: 13px;
  text-align: right;
}

.drawer-notes {
  padding: 14px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  background: #f8fafc;
  color: #334155;
  font-size: 13px;
  line-height: 1.7;
}
</style>
