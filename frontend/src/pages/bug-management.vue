<script setup lang="ts">
import { Delete, Tools } from '@element-plus/icons-vue'
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '../components/AppLayout.vue'
import { deleteBugReport, fetchBugReports, updateBugReportStatus } from '../api/client'
import type { BugReport } from '../types/qc'

const loading = ref(false)
const items = ref<BugReport[]>([])

const load = async () => {
  loading.value = true
  try {
    const payload = await fetchBugReports()
    items.value = payload.items
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '加载 BUG 列表失败')
  } finally {
    loading.value = false
  }
}

const markFixed = async (item: BugReport) => {
  try {
    const updated = await updateBugReportStatus(item.id, 'fixed')
    items.value = items.value.map((row) => row.id === item.id ? updated : row)
    ElMessage.success('已标记为已修复')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '更新 BUG 状态失败')
  }
}

const reopen = async (item: BugReport) => {
  try {
    const updated = await updateBugReportStatus(item.id, 'open')
    items.value = items.value.map((row) => row.id === item.id ? updated : row)
    ElMessage.success('已重新打开 BUG')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '更新 BUG 状态失败')
  }
}

const remove = async (item: BugReport) => {
  try {
    await ElMessageBox.confirm(`确认删除 BUG「${item.id}」吗？`, '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await deleteBugReport(item.id)
    items.value = items.value.filter((row) => row.id !== item.id)
    ElMessage.success('BUG 记录已删除')
  } catch (error) {
    if (error === 'cancel') return
    ElMessage.error(error instanceof Error ? error.message : '删除 BUG 失败')
  }
}

onMounted(load)
</script>

<template>
  <AppLayout>
    <div class="page-header">
      <div>
        <div class="page-title">BUG管理</div>
        <div class="page-subtitle">集中查看用户提交的问题反馈，并进行状态维护。</div>
      </div>
    </div>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="items" stripe>
        <el-table-column prop="createdAt" label="提交时间" width="150" />
        <el-table-column prop="reporterName" label="提交人" width="120" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="row.status === 'fixed' ? 'success' : 'warning'">
              {{ row.status === 'fixed' ? '已修复' : '待处理' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="描述" min-width="320">
          <template #default="{ row }">
            <div class="bug-description">{{ row.description || '（无文字描述）' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="截图" width="140">
          <template #default="{ row }">
            <template v-if="row.imageUrls?.length">
              <a v-for="(url, idx) in row.imageUrls" :key="url" :href="url" target="_blank" rel="noreferrer" class="image-link">{{ idx > 0 ? ' ' : '' }}图{{ idx + 1 }}</a>
            </template>
            <span v-else class="empty-text">无截图</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <div class="table-actions">
              <el-button
                v-if="row.status !== 'fixed'"
                type="success"
                size="small"
                :icon="Tools"
                @click="markFixed(row)"
              >
                标记已修复
              </el-button>
              <el-button
                v-else
                size="small"
                @click="reopen(row)"
              >
                重新打开
              </el-button>
              <el-button
                type="danger"
                plain
                size="small"
                :icon="Delete"
                @click="remove(row)"
              >
                删除
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </AppLayout>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-title {
  font-size: 22px;
  font-weight: 600;
  color: #0f172a;
}

.page-subtitle {
  margin-top: 6px;
  color: #64748b;
}

.bug-description {
  white-space: pre-wrap;
  line-height: 1.6;
  color: #334155;
}

.table-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.image-link {
  color: #2563eb;
  text-decoration: none;
}

.image-link:hover {
  text-decoration: underline;
}

.empty-text {
  color: #94a3b8;
}
</style>
