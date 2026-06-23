<script setup lang="ts">
import {
  Files,
  Finished,
  Monitor,
  Setting,
  VideoCamera
} from '@element-plus/icons-vue'
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

const menuItems = [
  { path: '/dashboard', label: '工作台', icon: Monitor },
  { path: '/database', label: '数据总库', icon: Files },
  { path: '/task-pool', label: '人工质检与派发', icon: VideoCamera },
  { path: '/qc-history', label: '历史审计', icon: Finished },
  { path: '/accounts', label: '账号管理', icon: Setting, roles: ['admin', 'qc_manager'] }
]

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
          <div class="brand-title">Robot QC</div>
          <div class="brand-subtitle">V1.0 人工质检平台</div>
        </div>
      </div>

      <el-menu :default-active="activeMenu" class="side-menu" router>
        <el-menu-item v-for="item in visibleMenuItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>

      <div class="storage-card">
        <div class="storage-title">本地中心主机</div>
        <div class="storage-path">/data/collection_data</div>
        <el-tag type="success" effect="light">业务数据由后端统一索引</el-tag>
        <div class="storage-meta">文件存储路径与扫描白名单以服务端配置为准</div>
      </div>
    </el-aside>

    <el-container>
      <el-header class="topbar">
        <div>
          <div class="topbar-title">机器人采集数据质检系统</div>
          <div class="topbar-subtitle">入库、派发、人工 QC、审计与批次统计闭环</div>
        </div>
        <div class="topbar-actions">
          <el-tag type="success" effect="light">LAN 内网访问</el-tag>
          <el-button type="primary" plain @click="router.push('/task-pool')">派发任务</el-button>
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
