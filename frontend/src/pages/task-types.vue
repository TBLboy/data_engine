<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '../components/AppLayout.vue'
import {
  attachBatchesToTaskType,
  createTaskType,
  deleteTaskType,
  detachBatchFromTaskType,
  fetchBatchesByTaskType,
  fetchTaskTypeDetail,
  fetchTaskTypes,
  updateTaskType,
  type TaskTypeCreateRequest,
  type TaskTypeDetailResponse,
  type TaskTypeUpdateRequest
} from '../api/client'
import type { BatchSummary, TaskType, TaskTypeArmMode } from '../types/qc'

const taskTypes = ref<TaskType[]>([])
const selectedTaskTypeId = ref('task_type:unclassified')
const detail = ref<TaskTypeDetailResponse | null>(null)
const unclassifiedBatches = ref<BatchSummary[]>([])
const loading = ref(true)
const detailLoading = ref(false)
const poolLoading = ref(false)
const saving = ref(false)
const error = ref('')

const createDialogVisible = ref(false)
const editDialogVisible = ref(false)
const attachDialogVisible = ref(false)

const selectedCandidateBatchIds = ref<string[]>([])
const detachingBatchId = ref('')
const keyword = ref('')

const createForm = reactive<TaskTypeCreateRequest>({
  name: '',
  description: '',
  armMode: 'both_arms'
})

const editForm = reactive<TaskTypeUpdateRequest>({
  name: '',
  description: '',
  armMode: 'both_arms'
})

const armModeLabelMap: Record<TaskTypeArmMode, string> = {
  both_arms: '双臂',
  left_arm: '左臂',
  right_arm: '右臂'
}

const selectedTaskType = computed(() => taskTypes.value.find((item) => item.id === selectedTaskTypeId.value) ?? null)
const canEditSelected = computed(() => selectedTaskType.value?.id !== 'task_type:unclassified')
const selectedBatches = computed(() => detail.value?.batches ?? [])
const selectedBatchCount = computed(() => selectedBatches.value.length)
const activeTaskTypeCount = computed(() => taskTypes.value.filter((item) => item.isActive).length)

const filteredTaskTypes = computed(() => {
  if (!keyword.value.trim()) return taskTypes.value
  const k = keyword.value.trim().toLowerCase()
  return taskTypes.value.filter((item) =>
    item.name.toLowerCase().includes(k) || item.description.toLowerCase().includes(k)
  )
})

const loadTaskTypes = async () => {
  taskTypes.value = await fetchTaskTypes()
  if (!taskTypes.value.find((item) => item.id === selectedTaskTypeId.value)) {
    selectedTaskTypeId.value = taskTypes.value[0]?.id ?? 'task_type:unclassified'
  }
}

const loadSelectedDetail = async () => {
  if (!selectedTaskTypeId.value) {
    detail.value = null
    return
  }
  detailLoading.value = true
  try {
    detail.value = await fetchTaskTypeDetail(selectedTaskTypeId.value)
  } finally {
    detailLoading.value = false
  }
}

const loadUnclassifiedPool = async () => {
  poolLoading.value = true
  try {
    unclassifiedBatches.value = await fetchBatchesByTaskType('task_type:unclassified')
  } finally {
    poolLoading.value = false
  }
}

const refreshPage = async () => {
  loading.value = true
  error.value = ''
  try {
    await loadTaskTypes()
    await Promise.all([loadSelectedDetail(), loadUnclassifiedPool()])
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载任务类型管理失败'
  } finally {
    loading.value = false
  }
}

onMounted(refreshPage)

watch(selectedTaskTypeId, async () => {
  await loadSelectedDetail()
})

const openCreateDialog = () => {
  createForm.name = ''
  createForm.description = ''
  createForm.armMode = 'both_arms'
  createDialogVisible.value = true
}

const submitCreateTaskType = async () => {
  saving.value = true
  try {
    const created = await createTaskType({
      name: createForm.name.trim(),
      description: (createForm.description ?? '').trim(),
      armMode: createForm.armMode ?? 'both_arms'
    })
    ElMessage.success('任务类型已创建')
    createDialogVisible.value = false
    await loadTaskTypes()
    selectedTaskTypeId.value = created.id
    await Promise.all([loadSelectedDetail(), loadUnclassifiedPool()])
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '创建任务类型失败')
  } finally {
    saving.value = false
  }
}

const openEditDialog = () => {
  if (!selectedTaskType.value || !canEditSelected.value) return
  editForm.name = selectedTaskType.value.name
  editForm.description = selectedTaskType.value.description
  editForm.armMode = selectedTaskType.value.armMode
  editDialogVisible.value = true
}

const submitEditTaskType = async () => {
  if (!selectedTaskType.value) return
  saving.value = true
  try {
    await updateTaskType(selectedTaskType.value.id, {
      name: editForm.name.trim(),
      description: (editForm.description ?? '').trim(),
      armMode: editForm.armMode ?? 'both_arms'
    })
    ElMessage.success('任务类型已更新')
    editDialogVisible.value = false
    await Promise.all([loadTaskTypes(), loadSelectedDetail(), loadUnclassifiedPool()])
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '更新任务类型失败')
  } finally {
    saving.value = false
  }
}

const confirmDeleteTaskType = async () => {
  if (!selectedTaskType.value || !canEditSelected.value) return
  try {
    await ElMessageBox.confirm(
      `停用后，该任务类型下的 ${selectedBatchCount.value} 个批次会自动回到“待分类”，是否继续？`,
      '停用任务类型',
      { type: 'warning' }
    )
  } catch {
    return
  }

  saving.value = true
  try {
    await deleteTaskType(selectedTaskType.value.id)
    ElMessage.success('任务类型已停用，关联批次已回到待分类')
    selectedTaskTypeId.value = 'task_type:unclassified'
    await Promise.all([loadTaskTypes(), loadSelectedDetail(), loadUnclassifiedPool()])
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '停用任务类型失败')
  } finally {
    saving.value = false
  }
}

const openAttachDialog = async () => {
  selectedCandidateBatchIds.value = []
  attachDialogVisible.value = true
  await loadUnclassifiedPool()
}

const submitAttachBatches = async () => {
  if (!selectedTaskType.value || !selectedCandidateBatchIds.value.length) {
    ElMessage.warning('请选择至少一个待分类批次')
    return
  }
  saving.value = true
  try {
    detail.value = await attachBatchesToTaskType(selectedTaskType.value.id, {
      batchIds: selectedCandidateBatchIds.value
    })
    ElMessage.success('批次已加入当前任务类型')
    attachDialogVisible.value = false
    selectedCandidateBatchIds.value = []
    await Promise.all([loadTaskTypes(), loadUnclassifiedPool()])
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '加入批次失败')
  } finally {
    saving.value = false
  }
}

const detachBatch = async (batch: BatchSummary) => {
  if (!selectedTaskType.value || !canEditSelected.value) return
  detachingBatchId.value = batch.id
  try {
    detail.value = await detachBatchFromTaskType(selectedTaskType.value.id, batch.id)
    ElMessage.success(`批次 ${batch.name} 已回到待分类`)
    await Promise.all([loadTaskTypes(), loadUnclassifiedPool()])
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '移出批次失败')
  } finally {
    detachingBatchId.value = ''
  }
}
</script>

<template>
  <AppLayout>
    <div class="page-stack">
      <section class="page-title-row database-hero">
        <div>
          <el-tag type="warning" effect="light">Task Type Management</el-tag>
          <h1>任务类型管理</h1>
          <p>由管理员和质检主管维护任务类型目录，把待分类批次加入正式任务类型，或把错误归类的批次回收到待分类。</p>
        </div>
        <div class="toolbar-actions">
          <el-button type="primary" @click="openCreateDialog">新建任务类型</el-button>
          <el-button :disabled="!canEditSelected" @click="openEditDialog">编辑</el-button>
          <el-button :disabled="!canEditSelected" @click="confirmDeleteTaskType">停用</el-button>
        </div>
      </section>

      <el-alert v-if="error" type="error" :closable="false" :title="error" />

      <el-row :gutter="18" v-loading="loading">
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-blue"><span>任务类型数</span><strong>{{ taskTypes.length }}</strong><small>含系统保底待分类</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-green"><span>启用中</span><strong>{{ activeTaskTypeCount }}</strong><small>可继续承接批次</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-orange"><span>待分类批次</span><strong>{{ unclassifiedBatches.length }}</strong><small>等待人工归类</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-purple"><span>当前任务批次</span><strong>{{ selectedBatchCount }}</strong><small>{{ selectedTaskType?.name ?? '未选择' }}</small></el-card></el-col>
      </el-row>

      <el-row :gutter="18">
        <el-col :span="7">
          <el-card shadow="never" class="qc-card" v-loading="loading">
            <template #header>
              <div class="card-header"><span>任务类型列表</span><el-tag type="info">左选右管</el-tag></div>
            </template>
            <el-input v-model="keyword" placeholder="搜索任务类型名称或描述" clearable size="small" class="qc-input" style="margin-bottom: 12px;" />
            <div class="task-type-scroll">
              <el-radio-group v-model="selectedTaskTypeId" class="task-type-list">
                <div v-for="item in filteredTaskTypes" :key="item.id" class="task-type-item">
                <el-radio :value="item.id">
                  <div class="task-type-copy">
                    <strong>{{ item.name }}</strong>
                    <span>{{ item.totalBatches }} 批次 · {{ item.totalEpisodes }} episodes</span>
                  </div>
                </el-radio>
                <el-tag :type="item.id === 'task_type:unclassified' ? 'warning' : (item.isActive ? 'success' : 'info')" size="small">
                  {{ item.id === 'task_type:unclassified' ? '系统保底' : (item.isActive ? '启用中' : '已停用') }}
                </el-tag>
              </div>
            </el-radio-group>
            </div>
          </el-card>
        </el-col>

        <el-col :span="17">
          <el-card shadow="never" class="qc-card" v-loading="detailLoading">
            <template #header>
              <div class="card-header">
                <span>{{ selectedTaskType?.name ?? '任务类型详情' }}</span>
                <div class="toolbar-actions">
                  <el-button type="primary" :disabled="!canEditSelected" @click="openAttachDialog">从待分类加入批次</el-button>
                  <el-tag type="info" effect="light">删除批次 = 回到待分类</el-tag>
                </div>
              </div>
            </template>
            <el-descriptions :column="2" border>
              <el-descriptions-item label="名称">{{ selectedTaskType?.name ?? '-' }}</el-descriptions-item>
              <el-descriptions-item label="状态">{{ selectedTaskType?.id === 'task_type:unclassified' ? '系统保底' : (selectedTaskType?.isActive ? '启用中' : '已停用') }}</el-descriptions-item>
              <el-descriptions-item label="描述">{{ selectedTaskType?.description ?? '-' }}</el-descriptions-item>
              <el-descriptions-item label="手臂模式">{{ selectedTaskType ? armModeLabelMap[selectedTaskType.armMode] : '-' }}</el-descriptions-item>
              <el-descriptions-item label="批次数">{{ selectedTaskType?.totalBatches ?? 0 }}</el-descriptions-item>
            </el-descriptions>

            <el-table :data="selectedBatches" stripe class="qc-table" height="500" style="margin-top: 18px;">
              <el-table-column prop="name" label="批次" min-width="220" />
              <el-table-column prop="episodeCount" label="Episodes" width="90" />
              <el-table-column prop="sampledEpisodeCount" label="已抽样" width="90" />
              <el-table-column prop="completedSampleCount" label="已完成" width="90" />
              <el-table-column prop="qcStatus" label="状态" width="100" />
              <el-table-column prop="importedAt" label="导入时间" width="160" />
              <el-table-column label="操作" width="180" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" :disabled="!canEditSelected" :loading="detachingBatchId === row.id" @click="detachBatch(row)">移出到待分类</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <el-dialog v-model="createDialogVisible" title="新建任务类型" width="460px" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="名称">
          <el-input v-model="createForm.name" maxlength="18" show-word-limit />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="手臂模式">
          <el-radio-group v-model="createForm.armMode">
            <el-radio value="both_arms">双臂</el-radio>
            <el-radio value="left_arm">左臂</el-radio>
            <el-radio value="right_arm">右臂</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-actions">
          <el-button @click="createDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="submitCreateTaskType">创建</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="editDialogVisible" title="编辑任务类型" width="460px" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="名称">
          <el-input v-model="editForm.name" maxlength="18" show-word-limit />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="手臂模式">
          <el-radio-group v-model="editForm.armMode">
            <el-radio value="both_arms">双臂</el-radio>
            <el-radio value="left_arm">左臂</el-radio>
            <el-radio value="right_arm">右臂</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-actions">
          <el-button @click="editDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="submitEditTaskType">保存</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="attachDialogVisible" title="从待分类加入批次" width="720px" destroy-on-close>
      <el-table :data="unclassifiedBatches" class="qc-table" height="420" @selection-change="(rows: BatchSummary[]) => { selectedCandidateBatchIds = rows.map((row) => row.id) }">
        <el-table-column type="selection" width="48" />
        <el-table-column prop="name" label="批次" min-width="260" />
        <el-table-column prop="episodeCount" label="Episodes" width="90" />
        <el-table-column prop="importedAt" label="导入时间" width="160" />
      </el-table>
      <template #footer>
        <div class="dialog-actions">
          <el-button @click="attachDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="submitAttachBatches">加入当前任务类型</el-button>
        </div>
      </template>
    </el-dialog>
  </AppLayout>
</template>

<style scoped>
.task-type-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

.task-type-scroll {
  max-height: 480px;
  overflow-y: auto;
  padding-right: 4px;
}

.task-type-scroll::-webkit-scrollbar {
  width: 6px;
}

.task-type-scroll::-webkit-scrollbar-thumb {
  background: #94a3b8;
  border-radius: 3px;
}

.task-type-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.task-type-item {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 14px;
}

.task-type-copy {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.task-type-copy span {
  color: #64748b;
  font-size: 12px;
}

:deep(.el-table-column--selection .el-checkbox__inner) {
  border-color: #111827;
}

.task-type-item :deep(.el-radio) {
  flex: 1;
  min-width: 0;
}

.task-type-item :deep(.el-radio__label) {
  width: 100%;
}
</style>
