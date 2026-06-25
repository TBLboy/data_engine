<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppLayout from '../components/AppLayout.vue'
import { fetchReviewerDashboard } from '../api/client'
import type { ReviewerDashboardPayload } from '../types/qc'
import { useSessionStore } from '../stores/session'

const router = useRouter()
const session = useSessionStore()
const payload = ref<ReviewerDashboardPayload | null>(null)
const loading = ref(true)

onMounted(async () => {
  try {
    payload.value = await fetchReviewerDashboard()
  } catch {
    // silently fallback
  } finally {
    loading.value = false
  }
})

const stats = computed(() => payload.value?.stats)
const batchGroups = computed(() => payload.value?.batchGroups ?? [])
const nextTask = computed(() => payload.value?.nextTask)

const startQc = () => {
  if (nextTask.value) {
    router.push(`/manual-qc/${nextTask.value.episodeId}?pipeline=1`)
  }
}
</script>

<template>
  <AppLayout>
    <div class="page-stack">
      <section class="page-title-row">
        <div>
          <el-tag type="success" effect="light">Reviewer Workspace</el-tag>
          <h1>QC 个人看板</h1>
          <p>你好，{{ session.user?.name ?? '审核员' }}。今日已完成 {{ stats?.doneTodayCount ?? 0 }} 条任务。</p>
        </div>
        <div class="toolbar-actions">
          <el-button type="primary" size="large" :disabled="!nextTask" :loading="loading" @click="startQc">
            {{ nextTask ? '开始质检' : '暂无待质检任务' }}
          </el-button>
          <router-link to="/task-pool"><el-button plain>查看全部任务</el-button></router-link>
        </div>
      </section>

      <el-row :gutter="18" v-loading="loading">
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-blue"><span>待质检</span><strong>{{ stats?.pendingCount ?? 0 }}</strong><small>已分配待处理</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-orange"><span>进行中</span><strong>{{ stats?.inReviewCount ?? 0 }}</strong><small>已认领审核中</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-green"><span>今日完成</span><strong>{{ stats?.doneTodayCount ?? 0 }}</strong><small>今日已提交</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-purple"><span>总计分配</span><strong>{{ stats?.totalAssignedCount ?? 0 }}</strong><small>全部活跃任务</small></el-card></el-col>
      </el-row>

      <el-card shadow="never" class="qc-card" v-loading="loading">
        <template #header><div class="card-header"><span>按批次分组</span><el-tag type="info">我的任务分布</el-tag></div></template>
        <el-table :data="batchGroups" stripe>
          <el-table-column prop="batchName" label="批次" min-width="260" />
          <el-table-column label="待质检" width="100"><template #default="{ row }"><strong>{{ row.pendingCount }}</strong></template></el-table-column>
          <el-table-column label="已完成" width="100"><template #default="{ row }"><strong>{{ row.doneCount }}</strong></template></el-table-column>
          <el-table-column label="进度" min-width="200">
            <template #default="{ row }">
              <span style="margin-right:8px">{{ row.doneCount }}/{{ row.totalCount }}</span>
              <el-progress :percentage="row.totalCount ? Math.round((row.doneCount / row.totalCount) * 100) : 0" :stroke-width="7" />
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!batchGroups.length && !loading" description="暂无分配到你的任务" />
      </el-card>
    </div>
  </AppLayout>
</template>
