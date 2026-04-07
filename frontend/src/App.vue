<template>
  <div class="app">
    <template v-if="isLoggedIn">
      <aside class="app-sidebar" id="app-sidebar">
        <div class="sidebar-logo">
          <div class="logo-icon">⚡</div>
          <span>ones-AI</span>
        </div>
        <nav>
          <div class="nav-section">工作台</div>
          <router-link to="/" class="nav-item" :class="{ active: $route.path === '/' }">
            <el-icon><Monitor /></el-icon> 服务器
          </router-link>
          <router-link to="/tasks/new" class="nav-item" :class="{ active: $route.path.startsWith('/tasks/new') }">
            <el-icon><Plus /></el-icon> 新建任务
          </router-link>
          <router-link to="/tasks" class="nav-item" :class="{ active: $route.path === '/tasks' }">
            <el-icon><List /></el-icon> 任务列表
          </router-link>
          <template v-if="isAdmin">
            <div class="nav-section">管理</div>
            <router-link to="/admin" class="nav-item" :class="{ active: $route.path === '/admin' }">
              <el-icon><DataLine /></el-icon> 数据总览
            </router-link>
            <router-link to="/admin/trends" class="nav-item" :class="{ active: $route.path === '/admin/trends' }">
              <el-icon><TrendCharts /></el-icon> 趋势分析
            </router-link>
            <router-link to="/admin/users" class="nav-item" :class="{ active: $route.path.startsWith('/admin/users') }">
              <el-icon><User /></el-icon> 用户明细
            </router-link>
            <router-link to="/admin/external" class="nav-item" :class="{ active: $route.path.startsWith('/admin/external') }">
              <el-icon><Connection /></el-icon> 外部团队
            </router-link>
            <router-link to="/admin/eval" class="nav-item" :class="{ active: $route.path === '/admin/eval' }">
              <el-icon><Star /></el-icon> 评价分析
            </router-link>
            <router-link to="/admin/accuracy" class="nav-item" :class="{ active: $route.path === '/admin/accuracy' }">
              <el-icon><Aim /></el-icon> 准确度评测
            </router-link>
            <router-link to="/admin/configs" class="nav-item" :class="{ active: $route.path === '/admin/configs' }">
              <el-icon><Setting /></el-icon> 服务配置
            </router-link>
            <router-link to="/admin/servers" class="nav-item" :class="{ active: $route.path === '/admin/servers' }">
              <el-icon><Monitor /></el-icon> 服务器管理
            </router-link>
          </template>
        </nav>

        <div class="sidebar-footer">
          <div class="sidebar-user">
            <div class="sidebar-avatar">{{ (user.display_name || user.ones_email || '?')[0] }}</div>
            <div class="sidebar-user-info">
              <div class="sidebar-user-name">{{ user.display_name || user.ones_email }}</div>
              <div class="sidebar-user-role">{{ isAdmin ? '管理员' : '用户' }}</div>
            </div>
          </div>
          <el-button size="small" @click="logout" type="info" plain style="width:100%;margin-top:10px;border-color:rgba(255,255,255,0.1);color:rgba(255,255,255,0.5);">退出登录</el-button>
        </div>
      </aside>
      <main class="app-main">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </template>
    <template v-else>
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'

const authStore = useAuthStore()
const router = useRouter()
const isLoggedIn = computed(() => authStore.isLoggedIn)
const isAdmin = computed(() => authStore.isAdmin)
const user = computed(() => authStore.user)

function logout() {
  authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.sidebar-footer {
  position: absolute;
  bottom: 0; left: 0; right: 0;
  padding: 16px 20px 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}
.sidebar-user {
  display: flex;
  align-items: center;
  gap: 10px;
}
.sidebar-avatar {
  width: 32px; height: 32px;
  border-radius: 8px;
  background: rgba(59, 130, 246, 0.15);
  color: #60a5fa;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700;
  font-size: 0.85rem;
}
.sidebar-user-info {
  flex: 1;
  min-width: 0;
}
.sidebar-user-name {
  font-size: 0.82rem;
  color: rgba(255, 255, 255, 0.75);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sidebar-user-role {
  font-size: 0.68rem;
  color: rgba(255, 255, 255, 0.3);
  margin-top: 1px;
}
</style>
