<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '../components/AppLayout.vue'
import { approveRereviewRequest, fetchRereviewRequests, rejectRereviewRequest, type RereviewRequestItem } from '../api/client'

const items = ref<RereviewRequestItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const error = ref('')
const statusFilter = ref<'pending' | 'all'>('pending')

const load = async () => {
  loading.value = true
  error.value = ''
  try {
    const data = await fetchRereviewRequests(page.value, pageSize, statusFilter.value)
    items.value = data.items
    total.value = data.total
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载审批列表失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)

const approve = async (req: RereviewRequestItem) => {
  try {
    await ElMessageBox.prompt('可填写审批备注', '批准重新质检', {
      confirmButtonText: '批准',
      cancelButtonText: '取消',
      inputType: 'textarea',
      inputPlaceholder: '备注（可选）',
    }).then(async ({ value }) => {
      await approveRereviewRequest(req.id, value || '')
      ElMessage.success(`已通过 ${req.requesterName} 的重新质检申请`)
      await load()
    }).catch(() => {})
  } catch (err: any) {
    ElMessage.error(err instanceof Error ? err.message : '操作失败')
  }
}

const reject = async (req: RereviewRequestItem) => {
  try {
    await ElMessageBox.prompt('请填写拒绝原因', '拒绝重新质检', {
      confirmButtonText: '拒绝',
      cancelButtonText: '取消',
      inputType: 'textarea',
      inputPlaceholder: '拒绝原因',
      inputValidator: (value: string) => {
        if (!value || !value.trim()) return '拒绝原因不能为空'
        return true
      },
    }).then(async ({ value }) => {
      await rejectRereviewRequest(req.id, value)
      ElMessage.success('已拒绝该申请')
      await load()
    }).catch(() => {})
  } catch (err: any) {
    ElMessage.error(err instanceof Error ? err.message : '操作失败')
  }
}

const handlePageChange = async (p: number) => {
  page.value = p
  await load()
}

const resultTag = (result: string) => {
  if (result === 'pending') return 'warning'
  if (result === 'approved') return 'success'
  if (result === 'rejected') return 'danger'
  return 'info'
}
</script>

<template>
  <AppLayout>
    <div class="page-stack">
      <section class="page-title-row database-hero">
        <div>
          <el-tag type="warning" effect="light">Re-Review Approvals</el-tag>
          <h1>重新质检审批</h1>
          <p>审核员提交的重新质检申请，批准后将任务重新分配回申请人当前任务池。</p>
        </div>
      </section>

      <el-alert v-if="error" type="error" :closable="false" :title="error" />

      <el-row :gutter="18" style="margin-bottom: 18px">
        <el-col :span="24">
          <el-radio-group v-model="statusFilter" size="small" @change="load">
            <el-radio-button value="pending">待审批</el-radio-button>
            <el-radio-button value="all">全部</el-radio-button>
          </el-radio-group>
        </el-col>
      </el-row>

      <el-card shadow="never" class="qc-card" v-loading="loading">
        <template #header>
          <div class="card-header"><span>审批列表</span><el-tag type="info">{{ total }} 条</el-tag></div>
        </template>
        <el-table :data="items" stripe height="480" class="qc-table" scrollbar-always-on>
          <el-table-column prop="requesterName" label="申请人" width="120" />
          <el-table-column prop="episodeId" label="Episode" min-width="160" />
          <el-table-column prop="batchName" label="批次" min-width="180" />
          <el-table-column prop="reason" label="申请原因" min-width="200" />
          <el-table-column label="状态" width="100">
            <template #default="{ row }"><el-tag :type="resultTag(row.status)">{{ row.status === 'pending' ? '待审批' : row.status === 'approved' ? '已批准' : '已拒绝' }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="createdAt" label="申请时间" width="170" />
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <template v-if="row.status === 'pending'">
                <el-button link type="primary" @click="approve(row)">批准</el-button>
                <el-button link type="danger" @click="reject(row)">拒绝</el-button>
              </template>
              <span v-else style="color: #909399; font-size: 13px;">{{ row.approverName }} · {{ row.decidedAt }}</span>
            </template>
          </el-table-column>
        </el-table>
        <div style="display:flex; justify-content:center; margin-top:12px">
          <el-pagination
            v-if="total > pageSize"
            :current-page="page"
            :page-size="pageSize"
            :total="total"
            layout="prev, pager, next"
            size="small"
            @current-change="handlePageChange"
          />
        </div>
      </el-card>
    </div>
  </AppLayout>
</template>
