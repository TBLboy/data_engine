<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppLayout from '../components/AppLayout.vue'
import {
  createAccount,
  fetchAccounts,
  resetAccountPassword,
  updateAccountStatus,
  type AccountListPayload,
  type CreateAccountRequest
} from '../api/client'
import { useSessionStore } from '../stores/session'
import type { Account, UserRole } from '../types/qc'

const session = useSessionStore()
const payload = ref<AccountListPayload | null>(null)
const loading = ref(true)
const saving = ref(false)
const error = ref('')

const createDialogVisible = ref(false)
const resetDialogVisible = ref(false)
const targetAccount = ref<Account | null>(null)
const togglingAccountId = ref('')

const createForm = reactive<CreateAccountRequest>({
  username: '',
  name: '',
  password: '',
  role: 'reviewer'
})

const resetForm = reactive({
  password: ''
})

const roleOptions: Array<{ label: string; value: UserRole }> = [
  { label: '管理员', value: 'admin' },
  { label: '质检主管', value: 'qc_manager' },
  { label: '审核员', value: 'reviewer' },
  { label: '访客', value: 'viewer' }
]

const loadAccounts = async () => {
  loading.value = true
  error.value = ''
  try {
    payload.value = await fetchAccounts()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载账号列表失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadAccounts)

const accounts = computed(() => payload.value?.accounts ?? [])
const isAdmin = computed(() => session.user?.role === 'admin')
const activeCount = computed(() => accounts.value.filter((item) => item.isActive).length)
const inactiveCount = computed(() => accounts.value.filter((item) => !item.isActive).length)
const managerCount = computed(() => accounts.value.filter((item) => item.role === 'admin' || item.role === 'qc_manager').length)
const reviewerCount = computed(() => accounts.value.filter((item) => item.role === 'reviewer').length)

const roleLabel = (role: UserRole) => {
  if (role === 'admin') return '管理员'
  if (role === 'qc_manager') return '质检主管'
  if (role === 'reviewer') return '审核员'
  return '访客'
}

const roleTagType = (role: UserRole) => {
  if (role === 'admin') return 'danger'
  if (role === 'qc_manager') return 'warning'
  if (role === 'reviewer') return 'primary'
  return 'info'
}

const statusTagType = (account: Account) => (account.isActive ? 'success' : 'info')
const isSelf = (account: Account) => account.id === session.user?.id

const resetCreateForm = () => {
  createForm.username = ''
  createForm.name = ''
  createForm.password = ''
  createForm.role = 'reviewer'
}

const openCreateDialog = () => {
  resetCreateForm()
  createDialogVisible.value = true
}

const submitCreateAccount = async () => {
  saving.value = true
  try {
    await createAccount({
      username: createForm.username.trim(),
      name: createForm.name.trim(),
      password: createForm.password,
      role: createForm.role
    })
    ElMessage.success('账号已创建')
    createDialogVisible.value = false
    resetCreateForm()
    await loadAccounts()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '创建账号失败')
  } finally {
    saving.value = false
  }
}

const openResetDialog = (account: Account) => {
  targetAccount.value = account
  resetForm.password = ''
  resetDialogVisible.value = true
}

const submitPasswordReset = async () => {
  if (!targetAccount.value) return
  saving.value = true
  try {
    await resetAccountPassword(targetAccount.value.id, { password: resetForm.password })
    ElMessage.success(`已重置 ${targetAccount.value.name} 的密码`)
    resetDialogVisible.value = false
    resetForm.password = ''
    targetAccount.value = null
    await loadAccounts()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '重置密码失败')
  } finally {
    saving.value = false
  }
}

const toggleAccount = async (account: Account) => {
  const nextStatus = !account.isActive
  const actionLabel = nextStatus ? '启用' : '停用'
  try {
    await ElMessageBox.confirm(
      `${actionLabel}账号后将立即影响其登录与后续操作权限，是否继续？`,
      `${actionLabel}账号`,
      { type: nextStatus ? 'warning' : 'error' }
    )
  } catch {
    return
  }

  togglingAccountId.value = account.id
  try {
    await updateAccountStatus(account.id, { isActive: nextStatus })
    ElMessage.success(`账号已${actionLabel}`)
    await loadAccounts()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : `${actionLabel}账号失败`)
  } finally {
    togglingAccountId.value = ''
  }
}
</script>

<template>
  <AppLayout>
    <div class="page-stack">
      <section class="page-title-row database-hero">
        <div>
          <el-tag type="danger" effect="light">Account & Access Control</el-tag>
          <h1>账号管理</h1>
          <p>管理员创建账号、主管查看账号状态，统一管理登录身份、角色权限和密码生命周期。</p>
        </div>
        <div class="toolbar-actions">
          <el-button v-if="isAdmin" type="primary" @click="openCreateDialog">新建账号</el-button>
          <el-tag v-else type="info" effect="light">仅管理员可修改账号生命周期</el-tag>
        </div>
      </section>

      <el-alert v-if="error" type="error" :closable="false" :title="error" />

      <el-row :gutter="18" v-loading="loading">
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-blue"><span>账号总数</span><strong>{{ accounts.length }}</strong><small>平台可见账号</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-green"><span>启用中</span><strong>{{ activeCount }}</strong><small>允许登录与执行业务</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-orange"><span>已停用</span><strong>{{ inactiveCount }}</strong><small>禁止登录</small></el-card></el-col>
        <el-col :span="6"><el-card shadow="never" class="qc-card qc-stat-card qc-stat-card-purple"><span>主管账号</span><strong>{{ managerCount }}</strong><small>reviewer {{ reviewerCount }} 人</small></el-card></el-col>
      </el-row>

      <el-row :gutter="18">
        <el-col :span="17">
          <el-card shadow="never" class="qc-card" v-loading="loading">
            <template #header>
              <div class="card-header"><span>账号清单</span><el-tag type="success">创建 / 重置密码 / 启停</el-tag></div>
            </template>
            <el-table :data="accounts" stripe class="qc-table" height="520">
              <el-table-column prop="username" label="账号" min-width="140" />
              <el-table-column prop="name" label="姓名" width="120" />
              <el-table-column label="角色" width="120">
                <template #default="{ row }">
                  <el-tag :type="roleTagType(row.role)">{{ roleLabel(row.role) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="110">
                <template #default="{ row }">
                  <el-tag :type="statusTagType(row)">{{ row.isActive ? '启用中' : '已停用' }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="passwordChangedAt" label="密码更新时间" min-width="180">
                <template #default="{ row }">
                  <span>{{ row.passwordChangedAt || '首次创建后未更新' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="标记" width="110">
                <template #default="{ row }">
                  <el-tag v-if="isSelf(row)" type="info" effect="light">当前登录</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="250" fixed="right">
                <template #default="{ row }">
                  <template v-if="isAdmin">
                    <el-button link type="primary" @click="openResetDialog(row)">重置密码</el-button>
                    <el-button
                      link
                      :type="row.isActive ? 'danger' : 'success'"
                      :disabled="isSelf(row) && row.isActive"
                      :loading="togglingAccountId === row.id"
                      @click="toggleAccount(row)"
                    >
                      {{ row.isActive ? '停用' : '启用' }}
                    </el-button>
                  </template>
                  <span v-else style="color:#94a3b8; font-size:13px;">仅查看</span>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>

        <el-col :span="7">
          <el-card shadow="never" class="qc-card assign-rules-card">
            <template #header>管理规则</template>
            <div class="rule-item"><strong>账号创建</strong><span>仅管理员可创建账号，并在创建时指定角色。</span></div>
            <div class="rule-item"><strong>停用保护</strong><span>当前登录账号不可自行停用，避免把自己锁出系统。</span></div>
            <div class="rule-item"><strong>密码生命周期</strong><span>重置密码会刷新密码更新时间，并写入审计事件。</span></div>
            <div class="rule-item"><strong>访问范围</strong><span>主管可查看账号清单，敏感变更仍由管理员执行。</span></div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <el-dialog v-model="createDialogVisible" title="新建账号" width="460px" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="账号">
          <el-input v-model="createForm.username" autocomplete="off" />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="createForm.name" autocomplete="off" />
        </el-form-item>
        <el-form-item label="初始密码">
          <el-input v-model="createForm.password" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="createForm.role" class="qc-select" style="width: 100%">
            <el-option v-for="option in roleOptions" :key="option.value" :label="option.label" :value="option.value" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-actions">
          <el-button @click="createDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="submitCreateAccount">创建</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="resetDialogVisible" title="重置密码" width="420px" destroy-on-close>
      <el-form label-position="top">
        <el-form-item label="账号">
          <el-input :model-value="targetAccount?.username ?? ''" disabled />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="resetForm.password" type="password" show-password autocomplete="new-password" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-actions">
          <el-button @click="resetDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="submitPasswordReset">确认重置</el-button>
        </div>
      </template>
    </el-dialog>
  </AppLayout>
</template>
