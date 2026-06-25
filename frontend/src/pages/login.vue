<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const username = ref('')
const password = ref('')
const loading = ref(false)

const extractDetail = (err: unknown, fallback: string) => {
  if (!(err instanceof Error)) return fallback
  try {
    const parsed = JSON.parse(err.message) as { detail?: string }
    return parsed.detail || err.message || fallback
  } catch {
    return err.message || fallback
  }
}

const login = async () => {
  if (!username.value.trim() || !password.value) {
    ElMessage.warning('请输入账号和密码')
    return
  }
  loading.value = true
  try {
    await session.signIn(username.value.trim(), password.value)
    ElMessage.success(`已进入系统：${session.user?.name ?? username.value}`)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'
    router.push(redirect)
  } catch (error) {
    ElMessage.error(extractDetail(error, '登录失败'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-visual">
      <el-tag type="primary" effect="dark">Robot Data QC V1.0</el-tag>
      <h1>公司内网可用的机器人采集数据质检平台</h1>
      <p>集中管理 MinIO 采集数据，支持账号权限、任务派发、人工质检、结果留痕与批次统计。</p>
      <div class="login-feature-grid">
        <div><strong>Processed 数据入库</strong><span>telemetry.npz + 三路视频 + 元数据</span></div>
        <div><strong>人工 QC 工作流</strong><span>视频、时间轴、L3 指标、原因码</span></div>
        <div><strong>审计追溯</strong><span>revision 历史与 audit_event 留痕</span></div>
      </div>
    </div>
    <div class="login-card">
      <div class="login-brand">Robot QC</div>
      <h1>登录质检平台</h1>
      <p>账号由管理员显式创建，密码仅保存哈希，按角色限制访问权限。</p>
      <el-form label-position="top" class="login-form" @submit.prevent="login">
        <el-form-item label="账号">
          <el-input v-model="username" size="large" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="password" type="password" size="large" show-password autocomplete="current-password" />
        </el-form-item>
        <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="login">进入系统</el-button>
      </el-form>
    </div>
  </div>
</template>
