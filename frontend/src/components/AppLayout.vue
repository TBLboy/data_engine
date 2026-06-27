<script setup lang="ts">
import {
  Files,
  Finished,
  Monitor,
  Setting,
  VideoCamera,
  CollectionTag
} from '@element-plus/icons-vue'
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

const menuItems = [
  { path: '/dashboard', label: '工作台', icon: Monitor, roles: ['admin', 'qc_manager', 'viewer'] },
  { path: '/reviewer', label: '个人看板', icon: Monitor, roles: ['reviewer'] },
  { path: '/database', label: '数据总库', icon: Files, roles: ['admin', 'qc_manager'] },
  { path: '/task-types', label: '任务类型管理', icon: CollectionTag, roles: ['admin', 'qc_manager'] },
  { path: '/task-pool', label: '人工质检入口', icon: VideoCamera },
  { path: '/qc-history', label: '历史审计', icon: Finished, roles: ['admin', 'qc_manager'] },
  { path: '/accounts', label: '账号管理', icon: Setting, roles: ['admin', 'qc_manager'] }
]

const isAdmin = computed(() => session.user?.role === 'admin')

const visibleMenuItems = computed(() => menuItems.filter((item) => !item.roles || item.roles.includes(session.user?.role ?? 'viewer')))

const activeMenu = computed(() => {
  if (route.path.startsWith('/manual-qc')) return '/task-pool'
  return route.path
})

const logout = async () => {
  try {
    await session.signOut()
    router.push('/login')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '退出登录失败')
  }
}
</script>

<template>
  <el-container class="app-shell">
    <el-aside width="248px" class="sidebar">
      <div class="brand">
        <div class="brand-mark">QC</div>
        <div>
          <div class="brand-title">灵机启物</div>
          <div class="brand-subtitle">机器人数采质检平台</div>
        </div>
      </div>

      <el-menu :default-active="activeMenu" class="side-menu" router>
        <el-menu-item v-for="item in visibleMenuItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>

      <div v-if="isAdmin" class="settings-entry" @click="router.push('/settings')">
        <el-icon><Setting /></el-icon>
        <span>设置</span>
      </div>

      <div class="storage-card">
        <div class="storage-title">MinIO 对象存储</div>
        <div class="storage-path">默认 bucket: yaocao</div>
        <el-tag type="success" effect="light">业务数据由后端统一索引</el-tag>
        <div class="storage-meta">对象访问与扫描范围以服务端 MinIO 配置为准</div>
      </div>
    </el-aside>

    <el-container>
      <el-header class="topbar">
        <div>
          <div class="topbar-title">灵机启物机器人数采质检平台</div>
          <div class="topbar-subtitle">入库、派发、人工 QC、审计与批次统计闭环</div>
        </div>
        <div class="topbar-actions">
          <el-tag type="success" effect="light">LAN 内网访问</el-tag>
          <el-button v-if="session.user?.role !== 'reviewer'" type="primary" plain class="qc-btn-plain" @click="router.push('/dashboard')">任务派发</el-button>
          <el-button plain @click="logout">退出登录</el-button>
          <el-avatar>{{ session.user?.avatar ?? '?' }}</el-avatar>
          <div class="user-meta">
            <div>{{ session.user?.name ?? '未登录' }}</div>
            <span>{{ session.user?.role ?? '-' }}</span>
          </div>
        </div>
      </el-header>

      <el-main class="main-view">
        <slot />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.settings-entry {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 46px;
  margin: 6px 8px;
  padding: 0 20px;
  border-radius: 12px;
  color: #cbd5e1;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.settings-entry:hover {
  color: #fff;
  background: rgba(37, 99, 235, 0.22);
}
</style>
