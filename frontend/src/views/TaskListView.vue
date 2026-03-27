<template>
  <div class="page-container" id="task-list-page">
    <div class="page-header fade-in-up">
      <h1>📋 任务列表</h1>
      <p>查看和管理您的所有工单任务</p>
    </div>

    <!-- 筛选栏 -->
    <div class="glass-card fade-in-up" style="margin-top:20px;padding:16px 20px !important;">
      <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
        <el-radio-group v-model="statusFilter" size="default" @change="loadTasks">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="running">执行中</el-radio-button>
          <el-radio-button value="pending">排队中</el-radio-button>
          <el-radio-button value="completed">已完成</el-radio-button>
          <el-radio-button value="failed">失败</el-radio-button>
        </el-radio-group>
        <div style="margin-left:auto;color:var(--text-muted);font-size:0.85rem;">
          共 {{ total }} 条记录
        </div>
      </div>
    </div>

    <!-- 任务列表 -->
    <div style="margin-top:16px;">
      <div v-if="loading" style="text-align:center;padding:60px 0;color:var(--text-muted);">
        加载中...
      </div>
      <div v-else-if="tasks.length === 0" class="empty-state">
        <div class="empty-icon">📭</div>
        <p>暂无任务记录</p>
        <el-button type="primary" @click="$router.push('/tasks/new')" round style="margin-top:12px;">
          创建新任务
        </el-button>
      </div>
      <template v-else>
        <div v-for="(t, idx) in tasks" :key="t.id" class="task-row glass-card fade-in-up"
             @click="$router.push('/tasks/'+t.id)"
             :style="{ animationDelay: (idx * 0.03) + 's' }">
          <div class="task-row-left">
            <span class="task-id">#{{ t.id }}</span>
            <span class="task-server">{{ t.server_name }}</span>
            <span :class="'badge badge-' + statusColor(t.status)">{{ statusLabel(t.status) }}</span>
          </div>
          <div class="task-row-right">
            <span class="task-stats">
              <template v-if="t.status === 'completed' || t.status === 'failed'">
                <span style="color:var(--success);">✅{{ t.success_count }}</span>
                <span v-if="t.failed_count" style="color:var(--danger);margin-left:6px;">❌{{ t.failed_count }}</span>
              </template>
              <template v-else>
                {{ t.ticket_count }} 个工单
              </template>
            </span>
            <span class="task-mode-badge" v-if="t.task_mode">{{ modeLabels[t.task_mode] || t.task_mode }}</span>
            <span class="task-time">{{ formatTime(t.submitted_at) }}</span>
            <el-icon class="task-arrow"><ArrowRight /></el-icon>
          </div>
        </div>

        <!-- 分页 -->
        <div style="display:flex;justify-content:center;margin-top:24px;">
          <el-pagination
            v-model:current-page="page"
            :page-size="pageSize"
            :total="total"
            layout="prev, pager, next"
            @current-change="loadTasks"
            background
          />
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'

const tasks = ref([])
const loading = ref(true)
const statusFilter = ref('')
const page = ref(1)
const pageSize = 20
const total = ref(0)

const modeLabels = { fix: '🔧 修复', analysis: '🔍 分析', auto: '🤖 自动' }

function statusColor(s) {
  return { pending: 'info', running: 'warning', completed: 'success', failed: 'danger', cancelled: 'info' }[s] || 'info'
}
function statusLabel(s) {
  return { pending: '排队中', running: '执行中', completed: '已完成', failed: '失败', cancelled: '已取消' }[s] || s
}
function formatTime(t) {
  if (!t) return ''
  const d = new Date(t)
  const now = new Date()
  const diff = (now - d) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return Math.floor(diff / 60) + ' 分钟前'
  if (diff < 86400) return Math.floor(diff / 3600) + ' 小时前'
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function loadTasks() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize }
    if (statusFilter.value) params.status = statusFilter.value
    const data = await api.getTasks(params)
    tasks.value = data
    // 后端目前不返回 total，用列表长度估算
    total.value = data.length < pageSize ? (page.value - 1) * pageSize + data.length : page.value * pageSize + 1
  } catch (e) {
    console.warn('任务列表加载失败:', e)
  } finally {
    loading.value = false
  }
}

onMounted(loadTasks)
</script>

<style scoped>
.task-row {
  cursor: pointer;
  margin-bottom: 8px;
  padding: 16px 20px !important;
  display: flex;
  justify-content: space-between;
  align-items: center;
  transition: border-color 0.2s, transform 0.15s;
}
.task-row:hover {
  border-color: var(--border-hover);
  box-shadow: var(--shadow);
  transform: translateY(-1px);
}
.task-row-left { display: flex; align-items: center; gap: 12px; }
.task-id {
  font-weight: 700; font-size: 1rem;
  color: var(--accent);
  font-family: var(--font-mono);
  min-width: 48px;
}
.task-server { color: var(--text-secondary); font-size: 0.9rem; }
.task-row-right { display: flex; align-items: center; gap: 16px; }
.task-stats { color: var(--text-secondary); font-size: 0.85rem; }
.task-mode-badge {
  font-size: 0.75rem;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--accent-bg);
  color: var(--accent);
}
.task-time { color: var(--text-muted); font-size: 0.82rem; min-width: 80px; text-align: right; }
.task-arrow { color: var(--text-muted); transition: all 0.2s var(--ease); }
.task-row:hover .task-arrow { transform: translateX(3px); color: var(--accent); }

.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-muted);
}
.empty-icon { font-size: 3rem; margin-bottom: 12px; opacity: 0.6; }
.empty-state p { font-size: 1rem; color: var(--text-secondary); margin-bottom: 4px; }
</style>
