import { createRouter, createWebHistory } from 'vue-router'
import { useSessionStore } from '../stores/session'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/login', name: 'login', component: () => import('../pages/login.vue'), meta: { public: true } },
    { path: '/dashboard', name: 'dashboard', component: () => import('../pages/dashboard.vue') },
    { path: '/database', name: 'database', component: () => import('../pages/database-view.vue') },
    { path: '/manual-qc/:id', name: 'manual-qc', component: () => import('../pages/manual-qc.vue') },
    { path: '/task-pool', name: 'task-pool', component: () => import('../pages/task-pool.vue') },
    { path: '/qc-history', name: 'qc-history', component: () => import('../pages/qc-history.vue') },
    { path: '/accounts', name: 'accounts', component: () => import('../pages/accounts.vue'), meta: { roles: ['admin', 'qc_manager'] } }
  ]
})

router.beforeEach(async (to) => {
  const session = useSessionStore()

  if (!session.initialized) {
    await session.bootstrap()
  }

  if (to.meta.public) {
    if (session.isAuthenticated) {
      return '/dashboard'
    }
    return true
  }

  if (!session.isAuthenticated) {
    return {
      path: '/login',
      query: { redirect: to.fullPath }
    }
  }

  const allowedRoles = Array.isArray(to.meta.roles) ? to.meta.roles : []
  if (allowedRoles.length && !allowedRoles.includes(session.user?.role ?? 'viewer')) {
    return '/dashboard'
  }

  return true
})

export default router
