<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import AppLayout from '../components/AppLayout.vue'
import {
  fetchHistory,
  fetchHistoryExport,
  fetchHistoryReport,
  type HistoryPayload
} from '../api/client'
import { useSessionStore } from '../stores/session'
import type { HistoryReportPayload } from '../types/qc'
import { reasonLabel } from '../utils/reasonLabels'

const session = useSessionStore()
const payload = ref<HistoryPayload | null>(null)
const reportPayload = ref<HistoryReportPayload | null>(null)
const loading = ref(true)
const reportLoading = ref(false)
const exportLoading = ref(false)
const error = ref('')
const reportError = ref('')
const keyword = ref('')
const selectedBatchId = ref('all')

const revisionPage = ref(1)
const revisionPageSize = 20
const auditPage = ref(1)
const auditPageSize = 50
const revisionScrollRef = ref<HTMLElement | null>(null)
const auditTableRef = ref<any>(null)

const canManageReports = computed(() => ['admin', 'qc_manager'].includes(session.user?.role ?? 'viewer'))

const loadHistory = async () => {
  loading.value = true
  error.value = ''
  try {
    payload.value = await fetchHistory(revisionPage.value, revisionPageSize, auditPage.value, auditPageSize)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载历史与审计失败'
  } finally {
    loading.value = false
  }
}

const onRevisionPageChange = async (page: number) => {
  revisionPage.value = page
  await loadHistory()
  await nextTick()
  revisionScrollRef.value?.scrollTo({ top: 0, behavior: 'instant' })
}

const onAuditPageChange = async (page: number) => {
  auditPage.value = page
  await loadHistory()
  await nextTick()
  auditTableRef.value?.setScrollTop(0)
}

const loadReport = async () => {
  if (!canManageReports.value) {
    reportPayload.value = null
    reportError.value = ''
    return
  }

  reportLoading.value = true
  reportError.value = ''
  try {
    reportPayload.value = await fetchHistoryReport(selectedBatchId.value)
  } catch (err) {
    reportError.value = err instanceof Error ? err.message : '加载历史报告失败'
  } finally {
    reportLoading.value = false
  }
}

const refreshPage = async () => {
  await loadHistory()
  if (!selectedBatchId.value) {
    selectedBatchId.value = 'all'
  }
  // 报告在后台加载，不阻塞主页面渲染
  loadReport()
}

onMounted(refreshPage)

const batches = computed(() => payload.value?.batches ?? [])
const batchOptions = computed(() => [{ id: 'all', name: '全部批次' }, ...batches.value.map((batch) => ({ id: batch.id, name: batch.name }))])
const episodes = computed(() => {
  const items = payload.value?.episodes ?? []
  if (selectedBatchId.value === 'all') return items
  return items.filter((item) => item.batchId === selectedBatchId.value)
})
const qcRevisions = computed(() => {
  const items = payload.value?.qcRevisions ?? []
  if (selectedBatchId.value === 'all') return items
  return items.filter((item) => item.batchId === selectedBatchId.value)
})
const auditRecords = computed(() => {
  const items = payload.value?.auditRecords ?? []
  if (selectedBatchId.value === 'all') return items
  const episodeIds = new Set(episodes.value.map((item) => item.id))
  return items.filter((item) => item.target === selectedBatchId.value || episodeIds.has(item.target))
})
const filteredAuditRecords = computed(() => auditRecords.value.filter((item) => {
  if (!keyword.value) return true
  const text = `${item.operator}${item.target}${item.action}${item.detail}`.toLowerCase()
  return text.includes(keyword.value.toLowerCase())
}))
const filteredRevisions = computed(() => qcRevisions.value.filter((item) => {
  if (!keyword.value) return true
  const text = `${item.operator}${item.episodeId}${item.primaryReason}${item.note}${item.batchName}`.toLowerCase()
  return text.includes(keyword.value.toLowerCase())
}))
const selectedBatchLabel = computed(() => batchOptions.value.find((item) => item.id === selectedBatchId.value)?.name ?? '全部批次')
const summary = computed(() => reportPayload.value?.summary)
const batchReports = computed(() => reportPayload.value?.batchReports ?? [])
const topReasons = computed(() => reportPayload.value?.topReasons ?? [])
const reviewers = computed(() => reportPayload.value?.reviewers ?? [])
const recentEpisodes = computed(() => reportPayload.value?.recentEpisodes ?? episodes.value.slice(0, 20))
const passRateText = computed(() => `${summary.value?.passRate ?? 0}%`)

const handleBatchChange = async () => {
  await loadReport()
}

const downloadExport = async (scope: 'report' | 'episodes' | 'audits') => {
  if (!canManageReports.value) return
  exportLoading.value = true
  try {
    const data = await fetchHistoryExport(selectedBatchId.value, scope)
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    const batchSuffix = selectedBatchId.value === 'all' ? 'all' : selectedBatchId.value
    link.href = url
    link.download = `qc-history-${scope}-${batchSuffix}.json`
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出文件已生成')
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '导出失败')
  } finally {
    exportLoading.value = false
  }
}

const reasonTagType = (category: string) => {
  if (category === 'L4 任务') return 'danger'
  if (category === 'L2 视觉') return 'primary'
  if (category === '动作示范质量') return 'warning'
  if (category === '可学习性') return 'warning'
  if (category === '数据完整性') return 'danger'
  if (category === '执行诊断') return 'info'
  if (category === '系统') return 'info'
  return 'info'
}
</script>

<template>
  <AppLayout>
    <div class="page-stack">
      <section class="page-title-row database-hero">
        <div>
          <el-tag type="primary" effect="light">Traceability & Audit</el-tag>
          <h1>历史与审计</h1>
          <p>按批次汇总 QC 结果、失败原因、审核人表现与关键审计事件，满足复盘、导出和责任追踪。</p>
        </div>
        <div class="toolbar-actions">
          <el-select v-model="selectedBatchId" style="width: 240px" class="qc-select" @change="handleBatchChange">
            <el-option v-for="item in batchOptions" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
          <el-input v-model="keyword" placeholder="搜索 operator / episode / action" class="qc-input" style="width: 320px" />
          <el-button @click="refreshPage">刷新</el-button>
        </div>
      </section>

      <el-alert v-if="error" type="error" :closable="false" :title="error" />
      <el-alert v-else-if="reportError" type="warning" :closable="false" :title="reportError" />
      <el-alert
        v-if="!canManageReports"
        type="info"
        :closable="false"
        title="当前角色仅可查看在线历史与审计明细，批次报告与正式导出仅对管理员和质检主管开放。"
      />

      <el-row :gutter="18" v-loading="loading">
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-blue"><span>审计事件</span><strong>{{ payload?.auditTotal ?? 0 }}</strong><small>{{ selectedBatchLabel }}</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-green"><span>历史 Revision</span><strong>{{ payload?.revisionTotal ?? 0 }}</strong><small>支持按批次筛选</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-orange"><span>Fail 记录</span><strong>{{ summary?.failEpisodeCount ?? episodes.filter((item) => item.qcResult === 'fail').length }}</strong><small>可追溯主原因码</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-purple"><span>通过率</span><strong>{{ passRateText }}</strong><small>{{ summary?.completedSampleCount ?? episodes.filter((item) => item.qcStatus === 'done').length }} 条已完成抽检</small></el-card></el-col>
      </el-row>

      <el-row v-if="canManageReports" :gutter="18">
        <el-col :span="24">
          <el-card shadow="never" class="qc-card" v-loading="reportLoading">
            <template #header>
              <div class="card-header">
                <span>批次报告总览</span>
                <div class="toolbar-actions">
                  <el-button :loading="exportLoading" @click="downloadExport('report')">导出报告 JSON</el-button>
                  <el-button :loading="exportLoading" @click="downloadExport('episodes')">导出 Episode 明细</el-button>
                  <el-button :loading="exportLoading" @click="downloadExport('audits')">导出 Audit 明细</el-button>
                </div>
              </div>
            </template>
            <el-descriptions :column="5" border>
              <el-descriptions-item label="批次数">{{ summary?.batchCount ?? 0 }}</el-descriptions-item>
              <el-descriptions-item label="Episode 总数">{{ summary?.episodeCount ?? 0 }}</el-descriptions-item>
              <el-descriptions-item label="抽检样本">{{ summary?.sampledEpisodeCount ?? 0 }}</el-descriptions-item>
              <el-descriptions-item label="已完成抽检">{{ summary?.completedSampleCount ?? 0 }}</el-descriptions-item>
              <el-descriptions-item label="通过率">{{ passRateText }}</el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-col>
      </el-row>

      <el-row v-if="canManageReports" :gutter="18">
        <el-col :span="24">
          <el-card shadow="never" class="qc-card" v-loading="reportLoading">
            <template #header>批次级汇总报表</template>
            <el-table :data="batchReports" stripe class="qc-table" height="320">
              <el-table-column prop="batchName" label="批次" min-width="220" />
              <el-table-column prop="qcStatus" label="状态" width="110" />
              <el-table-column prop="dispatchMode" label="派发模式" width="110" />
              <el-table-column prop="samplingRatio" label="抽检比例" width="100" />
              <el-table-column prop="episodeCount" label="总数" width="90" />
              <el-table-column prop="completedSampleCount" label="已完成" width="100" />
              <el-table-column prop="passRate" label="通过率" width="100" />
              <el-table-column prop="topReason" label="高频原因" min-width="150" />
              <el-table-column prop="reviewerCount" label="审核人" width="90" />
              <el-table-column prop="auditEventCount" label="审计事件" width="100" />
              <el-table-column prop="latestActivityAt" label="最近活动" min-width="160" />
            </el-table>
          </el-card>
        </el-col>
      </el-row>

      <el-row v-if="canManageReports" :gutter="18">
        <el-col :span="10">
          <el-card shadow="never" class="qc-card" v-loading="reportLoading">
            <template #header>失败原因分布</template>
            <el-table :data="topReasons" stripe class="qc-table" height="300">
              <el-table-column label="原因码" min-width="160">
                <template #default="{ row }">{{ reasonLabel(row.reason) }}</template>
              </el-table-column>
              <el-table-column label="层级" width="110">
                <template #default="{ row }">
                  <el-tag :type="reasonTagType(row.category)">{{ row.category }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="count" label="次数" width="90" />
              <el-table-column prop="ratio" label="占比" width="90">
                <template #default="{ row }">{{ row.ratio }}%</template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
        <el-col :span="14">
          <el-card shadow="never" class="qc-card" v-loading="reportLoading">
            <template #header>审核人工作量与质量</template>
            <el-table :data="reviewers" stripe class="qc-table" height="300">
              <el-table-column prop="name" label="审核人" min-width="140" />
              <el-table-column prop="assigned" label="待处理" width="100" />
              <el-table-column prop="done" label="已完成" width="100" />
              <el-table-column prop="passRate" label="通过率" width="100">
                <template #default="{ row }">{{ row.passRate }}%</template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="18">
        <el-col :span="10">
          <el-card shadow="never" class="qc-card" v-loading="loading">
            <template #header>Revision 时间线</template>
            <div ref="revisionScrollRef" style="max-height: 480px; overflow-y: auto; padding-right: 4px">
              <el-timeline>
                <el-timeline-item v-for="revision in filteredRevisions" :key="`${revision.episodeId}-${revision.revisionNo}-${revision.time}`" :timestamp="revision.time" placement="top">
                  <div class="revision-item audit-revision">
                    <strong>{{ revision.batchName }} / {{ revision.episodeId }}</strong>
                    <span>#{{ revision.revisionNo }} · {{ revision.operator }} · {{ revision.result }} · {{ revision.primaryReason || '-' }}</span>
                    <p>{{ revision.note || '无备注' }}</p>
                  </div>
                </el-timeline-item>
              </el-timeline>
            </div>
            <div style="display:flex; justify-content:center; margin-top:12px">
              <el-pagination
                v-if="(payload?.revisionTotal ?? 0) > revisionPageSize"
                v-model:current-page="revisionPage"
                :page-size="revisionPageSize"
                :total="payload?.revisionTotal ?? 0"
                layout="prev, pager, next"
                size="small"
                @current-change="onRevisionPageChange"
              />
            </div>
          </el-card>
        </el-col>
        <el-col :span="14">
          <el-card shadow="never" class="qc-card" v-loading="loading">
            <template #header>系统审计事件</template>
            <el-table ref="auditTableRef" :data="filteredAuditRecords" stripe class="qc-table" height="480">
              <el-table-column prop="time" label="时间" width="170" />
              <el-table-column prop="operator" label="操作人" width="110" />
              <el-table-column prop="action" label="动作" width="140" />
              <el-table-column prop="target" label="对象" width="170" />
              <el-table-column prop="detail" label="详情" min-width="260" />
            </el-table>
            <div style="display:flex; justify-content:center; margin-top:12px">
              <el-pagination
                v-if="(payload?.auditTotal ?? 0) > auditPageSize"
                v-model:current-page="auditPage"
                :page-size="auditPageSize"
                :total="payload?.auditTotal ?? 0"
                layout="prev, pager, next"
                size="small"
                @current-change="onAuditPageChange"
              />
            </div>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="18">
        <el-col :span="24">
          <el-card shadow="never" class="qc-card" v-loading="loading || reportLoading">
            <template #header>最近 Episode 明细</template>
            <el-table :data="recentEpisodes" stripe class="qc-table" height="320">
              <el-table-column prop="batchName" label="批次" min-width="220" />
              <el-table-column prop="id" label="Episode" min-width="160" />
              <el-table-column prop="reviewer" label="审核人" width="120" />
              <el-table-column prop="qcStatus" label="状态" width="110" />
              <el-table-column prop="qcResult" label="结果" width="100" />
              <el-table-column label="原因码" min-width="160">
                <template #default="{ row }">{{ reasonLabel(row.reasonCode) }}</template>
              </el-table-column>
              <el-table-column prop="updatedAt" label="更新时间" min-width="160" />
            </el-table>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </AppLayout>
</template>
