import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', name: 'Login', component: () => import('../views/LoginView.vue'), meta: { guest: true } },
  { path: '/', name: 'Dashboard', component: () => import('../views/DashboardView.vue'), meta: { auth: true } },
  { path: '/tasks/new/:serverId?', name: 'NewTask', component: () => import('../views/TaskView.vue'), meta: { auth: true } },
  { path: '/tasks/:id', name: 'TaskDetail', component: () => import('../views/TaskDetailView.vue'), meta: { auth: true } },
  { path: '/admin', name: 'Admin', component: () => import('../views/AdminView.vue'), meta: { auth: true, admin: true } },
  { path: '/admin/trends', name: 'AdminTrend', component: () => import('../views/AdminTrend.vue'), meta: { auth: true, admin: true } },
  { path: '/admin/users', name: 'AdminUsers', component: () => import('../views/AdminUsers.vue'), meta: { auth: true, admin: true } },
  { path: '/admin/users/:id', name: 'AdminUserDetail', component: () => import('../views/AdminUserDetail.vue'), meta: { auth: true, admin: true } },
  { path: '/admin/eval', name: 'AdminEval', component: () => import('../views/AdminEval.vue'), meta: { auth: true, admin: true } },
  { path: '/admin/configs', name: 'AdminConfigs', component: () => import('../views/AdminConfigs.vue'), meta: { auth: true, admin: true } },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  const user = JSON.parse(localStorage.getItem('user') || '{}')

  if (to.meta.auth && !token) return next('/login')
  if (to.meta.admin && user.role !== 'admin') return next('/')
  if (to.meta.guest && token) return next('/')
  next()
})

export default router
