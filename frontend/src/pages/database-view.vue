<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import AppLayout from '../components/AppLayout.vue'
import { fetchDatabase, scanDatabase, type DatabasePayload } from '../api/client'
import { useSessionStore } from '../stores/session'

const session = useSessionStore()
const payload = ref<DatabasePayload | null>(null)
const loading = ref(true)
const error = ref('')
const scanning = ref(false)
const keyword = ref('')
const status = ref('')
const result = ref('')
const batch = ref('')
const page = ref(1)
const pageSize = ref(100)
let keywordTimer: ReturnType<typeof setTimeout> | null = null

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

const loadDatabase = async () => {
  loading.value = true
  error.value = ''
  try {
    payload.value = await fetchDatabase({
      page: page.value,
      pageSize: pageSize.value,
      keyword: keyword.value.trim(),
      batchId: batch.value,
      qcStatus: status.value,
      qcResult: result.value
    })
  } catch (err) {
    error.value = formatError(err, '加载数据总库失败')
  } finally {
    loading.value = false
  }
}

const reloadFromFirstPage = async () => {
  page.value = 1
  await loadDatabase()
}

const submitScan = async () => {
  scanning.value = true
  try {
    const job = await scanDatabase({
      bucket: scanForm.bucket.trim(),
      scope: scanForm.scope
    })
    ElMessage.success(`扫描完成：${job.detail}`)
    await loadDatabase()
  } catch (err) {
    ElMessage.error(formatError(err, '扫描入库失败'))
  } finally {
    scanning.value = false
  }
}

onMounted(loadDatabase)

watch([batch, status, result, pageSize], async () => {
  await reloadFromFirstPage()
})

watch(page, async () => {
  await loadDatabase()
})

watch(keyword, () => {
  if (keywordTimer) clearTimeout(keywordTimer)
  keywordTimer = setTimeout(() => {
    void reloadFromFirstPage()
  }, 250)
})

const episodes = computed(() => payload.value?.episodes ?? [])
const batches = computed(() => payload.value?.batches ?? [])
const taskTypes = computed(() => payload.value?.taskTypes ?? [])
const reasonStats = computed(() => payload.value?.reasonStats ?? [])
const ingestJobs = computed(() => payload.value?.ingestJobs ?? [])
const totalEpisodes = computed(() => payload.value?.totalEpisodes ?? 0)

const ingestStatusType = (statusValue: string) => {
  if (statusValue === 'done') return 'success'
  if (statusValue === 'failed') return 'danger'
  if (statusValue === 'scanning') return 'warning'
  return 'info'
}
</script>

<template>
  <AppLayout>
    <div class="page-stack">
      <section class="page-title-row database-hero">
        <div>
          <el-tag type="success" effect="light">Indexed Data Catalog</el-tag>
          <h1>数据总库</h1>
          <p>按任务、批次、QC 状态、审核员和原因码检索全部采集数据，并直接触发 MinIO 数据湖扫描入库。</p>
        </div>
        <div class="toolbar-actions">
          <el-tag type="info" effect="light">导出能力暂未交付</el-tag>
        </div>
      </section>

      <el-alert v-if="error" type="error" :closable="false" :title="error" />

      <el-row :gutter="18" v-loading="loading">
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-blue"><span>已索引 Episodes</span><strong>{{ totalEpisodes }}</strong><small>MinIO episode 样本</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-green"><span>任务类型</span><strong>{{ taskTypes.length }}</strong><small>支持动态扫描</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-orange"><span>失败原因种类</span><strong>{{ reasonStats.length }}</strong><small>L2/L3/L4/System</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-purple"><span>批次数量</span><strong>{{ batches.length }}</strong><small>一次扫描形成一个批次</small></el-card></el-col>
      </el-row>

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
            <div style="margin-top: 10px; color: #909399; font-size: 13px; line-height: 1.6;">
              当前扫描直接面向 MinIO 数据湖，默认 bucket 为
              <code>yaocao</code>
              ，scope 目前保留
              <code>full</code>
              全量扫描语义。
            </div>
          </el-card>
        </el-col>
        <el-col :span="canScanDatabase ? 15 : 24">
          <el-card shadow="never" class="qc-card" v-loading="loading">
            <template #header>最近扫描任务</template>
            <el-table :data="ingestJobs" stripe class="qc-table" height="240">
              <el-table-column prop="bucket" label="Bucket" min-width="150" />
              <el-table-column prop="scope" label="范围" width="110" />
              <el-table-column label="状态" width="110">
                <template #default="{ row }"><el-tag :type="ingestStatusType(row.status)">{{ row.status }}</el-tag></template>
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
          <el-input v-model="keyword" placeholder="搜索 episode / batch / reason / reviewer" class="qc-input" clearable />
          <el-select v-model="batch" placeholder="批次" class="qc-select" clearable filterable>
            <el-option v-for="item in batches" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
          <el-select v-model="status" placeholder="QC 状态" class="qc-select" clearable filterable>
            <el-option label="未派发" value="new" /><el-option label="已派发" value="assigned" /><el-option label="审核中" value="in_review" /><el-option label="已完成" value="done" />
          </el-select>
          <el-select v-model="result" placeholder="最终状态" class="qc-select" clearable filterable>
            <el-option label="可用于训练" value="QUALIFIED" /><el-option label="不可用于训练" value="UNQUALIFIED" /><el-option label="待最终判定" value="PENDING" />
          </el-select>
        </div>
      </el-card>

      <el-card shadow="never" class="qc-card episode-table-card" v-loading="loading">
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
            <el-table-column label="判定来源" min-width="140">
              <template #default="{ row }">
                <span v-if="row.finalDecisionSource === 'MANUAL_PASS'">人工合格</span>
                <span v-else-if="row.finalDecisionSource === 'MANUAL_FAIL'">人工不合格</span>
                <span v-else-if="row.finalDecisionSource === 'BATCH_ACCEPT_INFERRED_PASS'">自动合格</span>
                <span v-else-if="row.finalDecisionSource === 'BATCH_REJECT_PROPAGATED_FAIL'">自动不合格</span>
                <span v-else-if="row.finalDecisionSource === 'BATCH_REJECT_OVERRIDE_MANUAL_PASS'">人工合格(批次驳回)</span>
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
            <el-table-column prop="reasonCode" label="原因码" min-width="160" />
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
    </div>
  </AppLayout>
</template>

<style scoped>
.database-pagination-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
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
</style>
