<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppLayout from '../components/AppLayout.vue'
import { fetchDashboard, type DashboardPayload } from '../api/client'
import type { DispatchMode } from '../types/qc'

const payload = ref<DashboardPayload | null>(null)
const loading = ref(true)
const error = ref('')
const selectedTaskType = ref('')

const loadDashboard = async () => {
  loading.value = true
  error.value = ''
  try {
    const data = await fetchDashboard()
    payload.value = data
    if (!selectedTaskType.value && data.taskTypes.length) {
      selectedTaskType.value = data.taskTypes[0].id
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
const reasonStats = computed(() => payload.value?.reasonStats ?? [])
const reviewerWorkloads = computed(() => payload.value?.reviewerWorkloads ?? [])
const ingestJobs = computed(() => payload.value?.ingestJobs ?? [])

const currentBatches = computed(() => batches.value.filter((batch) => batch.taskTypeId === selectedTaskType.value))
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

const dispatchTag = (mode: DispatchMode) => (mode === 'full' ? 'success' : 'warning')
const dispatchLabel = (mode: DispatchMode, ratio: number) => mode === 'full' ? '全量' : `抽检 ${ratio}%`
const statusType = (status: string) => {
  if (status === 'done') return 'success'
  if (status === 'in_review') return 'warning'
  return 'info'
}
</script>

<template>
  <AppLayout>
    <div class="page-stack">
      <section class="boss-hero">
        <div class="hero-copy">
          <el-tag type="primary" effect="dark">V1.0 Manual QC Platform</el-tag>
          <h1>机器人采集数据质检运营中心</h1>
          <p>从本地数据入库、批次管理、抽检派发、人工 QC、结果留痕到批次统计，形成公司内网可落地的完整闭环。</p>
          <div class="hero-badges">
            <span>本地中心主机部署</span>
            <span>PostgreSQL 业务数据</span>
            <span>视频/telemetry 本地文件存储</span>
            <span>多人账号协作</span>
          </div>
        </div>
        <div class="hero-command-card">
          <div class="command-title">今日质检指挥板</div>
          <div class="command-number">{{ totalCompleted }}/{{ totalSampled }}</div>
          <div class="command-subtitle">已完成样本 / 已抽中样本</div>
          <el-progress :percentage="totalSampled ? Math.round((totalCompleted / totalSampled) * 100) : 0" :stroke-width="12" />
          <div class="hero-actions command-actions">
            <el-select v-model="selectedTaskType" filterable size="large" style="width: 260px" :loading="loading">
              <el-option v-for="item in taskTypes" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
            <router-link v-if="qcTasks[0]" :to="`/manual-qc/${qcTasks[0].episodeId}`"><el-button type="primary" size="large">进入 QC 工作台</el-button></router-link>
          </div>
        </div>
      </section>

      <el-alert v-if="error" type="error" :closable="false" :title="error" />

      <el-row :gutter="18" v-loading="loading">
        <el-col :span="6"><el-card shadow="never" class="stat-card accent-blue"><span>候选总量</span><strong>{{ totalEpisodes }}</strong><small>待抽检 / 已入库</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="stat-card accent-orange"><span>已抽中样本</span><strong>{{ totalSampled }}</strong><small>抽检覆盖率 {{ avgCoverage }}%</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="stat-card accent-green"><span>样本完成率</span><strong>{{ avgPassRate }}%</strong><small>基于已完成样本 pass rate</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="stat-card accent-purple"><span>我的待办</span><strong>{{ qcTasks.length }}</strong><small>高优先级 {{ qcTasks.filter((task) => task.priority === 'high').length }} 条</small></el-card></el-col>
      </el-row>

      <el-row :gutter="18">
        <el-col :span="15">
          <el-card shadow="never" class="product-card" v-loading="loading">
            <template #header>
              <div class="card-header"><span>批次进度总览</span><router-link to="/task-pool"><el-button type="primary" plain>进入任务派发</el-button></router-link></div>
            </template>
            <el-table :data="currentBatches" stripe>
              <el-table-column prop="name" label="批次" min-width="190" />
              <el-table-column prop="episodeCount" label="总量" width="70" />
              <el-table-column label="派发模式" width="110">
                <template #default="{ row }"><el-tag :type="dispatchTag(row.dispatchMode)" size="small">{{ dispatchLabel(row.dispatchMode, row.samplingRatio) }}</el-tag></template>
              </el-table-column>
              <el-table-column label="抽检覆盖率" width="110">
                <template #default="{ row }"><strong>{{ row.sampleCoverageRate }}%</strong></template>
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
              <el-table-column label="通过率" width="80">
                <template #default="{ row }"><strong>{{ row.passRate }}%</strong></template>
              </el-table-column>
              <el-table-column prop="topReason" label="Top失败原因" min-width="150" />
              <el-table-column label="操作" width="220">
                <template #default>
                  <router-link :to="`/task-pool`"><el-button link type="primary">任务派发</el-button></router-link>
                  <router-link to="/database"><el-button link>查看数据</el-button></router-link>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>

        <el-col :span="9">
          <el-card shadow="never" class="product-card reason-card" v-loading="loading">
            <template #header>失败原因 Top 统计</template>
            <div v-for="item in reasonStats" :key="item.reason" class="reason-row">
              <div class="reason-info"><strong>{{ item.reason }}</strong><span>{{ item.category }} · {{ item.count }} 条</span></div>
              <div class="reason-bar"><i :style="{ width: `${item.ratio}%` }" /></div>
              <b>{{ item.ratio }}%</b>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="18">
        <el-col :span="8">
          <el-card shadow="never" class="product-card" v-loading="loading">
            <template #header>审核员工作量</template>
            <div v-for="reviewer in reviewerWorkloads" :key="reviewer.name" class="reviewer-row">
              <div><strong>{{ reviewer.name }}</strong><span>平均 {{ reviewer.avgMinutes }} min / episode</span></div>
              <el-progress :percentage="reviewer.assigned + reviewer.done ? Math.round((reviewer.done / (reviewer.assigned + reviewer.done)) * 100) : 0" />
              <b>{{ reviewer.done }}/{{ reviewer.assigned + reviewer.done }}</b>
            </div>
          </el-card>
        </el-col>

        <el-col :span="8">
          <el-card shadow="never" class="product-card todo-card" v-loading="loading">
            <template #header>审核员待办</template>
            <div v-for="task in qcTasks" :key="task.id" class="task-item rich">
              <div><strong>{{ task.episodeId }}</strong><span>{{ task.batchName }} · {{ task.assignee }}</span></div>
              <el-tag :type="task.priority === 'high' ? 'danger' : 'info'">{{ task.priority }}</el-tag>
            </div>
          </el-card>
        </el-col>

        <el-col :span="8">
          <el-card shadow="never" class="product-card" v-loading="loading">
            <template #header>入库与转换任务</template>
            <div v-for="job in ingestJobs" :key="job.id" class="ingest-row">
              <div class="ingest-head"><strong>{{ job.batchName }}</strong><el-tag size="small">{{ job.status }}</el-tag></div>
              <el-progress :percentage="job.progress" />
              <span>{{ job.episodes }} episodes · {{ job.startedAt }}</span>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </AppLayout>
</template>
