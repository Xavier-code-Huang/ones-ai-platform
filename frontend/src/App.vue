<template>
  <div class="app">
    <template v-if="isLoggedIn">
      <aside class="app-sidebar" id="app-sidebar">
        <div class="sidebar-logo">🤖 ones-AI</div>
        <nav>
          <div class="nav-section">工作台</div>
          <router-link to="/" class="nav-item" :class="{ active: $route.path === '/' }">
            <el-icon><Monitor /></el-icon> 服务器
          </router-link>
          <router-link to="/tasks/new" class="nav-item" :class="{ active: $route.path.startsWith('/tasks/new') }">
            <el-icon><Plus /></el-icon> 新建任务
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
            <router-link to="/admin/eval" class="nav-item" :class="{ active: $route.path === '/admin/eval' }">
              <el-icon><Star /></el-icon> 评价分析
            </router-link>
            <router-link to="/admin/configs" class="nav-item" :class="{ active: $route.path === '/admin/configs' }">
              <el-icon><Setting /></el-icon> 服务配置
            </router-link>
          </template>
        </nav>

        <div style="position:absolute;bottom:20px;left:0;right:0;padding:0 20px;">
          <div style="font-size:0.8rem;color:var(--text-muted);margin-bottom:8px;">
            {{ user.display_name || user.ones_email }}
          </div>
          <el-button size="small" @click="logout" type="info" plain style="width:100%;">退出登录</el-button>
        </div>
      </aside>
      <main class="app-main">
        <router-view />
      </main>
    </template>
    <template v-else>
      <router-view />
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
