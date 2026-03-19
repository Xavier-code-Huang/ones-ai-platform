<template>
  <div class="page-container" id="dashboard-page">
    <!-- 欢迎横幅 -->
    <div class="welcome-banner fade-in-up">
      <div class="welcome-content">
        <div class="welcome-text">
          <h1>{{ greeting }}，{{ displayName }}</h1>
          <p>AI 驱动的 ONES 工单自动处理平台</p>
        </div>
        <div class="welcome-stats">
          <div class="quick-stat">
            <span class="quick-stat-num">{{ servers.length }}</span>
            <span class="quick-stat-label">可用服务器</span>
          </div>
          <div class="quick-stat-divider"></div>
          <div class="quick-stat">
            <span class="quick-stat-num">{{ readyServers }}</span>
            <span class="quick-stat-label">已绑定凭证</span>
          </div>
          <div class="quick-stat-divider"></div>
          <div class="quick-stat">
            <span class="quick-stat-num">{{ tasks.length }}</span>
            <span class="quick-stat-label">历史任务</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 服务器列表 -->
    <div style="margin-top:32px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
        <h2 class="section-title fade-in-up">
          <span class="section-icon">🖥️</span> 服务器列表
        </h2>
      </div>
      <div class="servers-grid">
        <div v-for="(s, idx) in servers" :key="s.id" class="server-card glass-card fade-in-up"
             :style="{ animationDelay: (idx * 0.05) + 's' }" :id="'server-'+s.id">
          <div class="server-card-top">
            <div class="server-status-dot" :class="'dot-' + s.status"></div>
            <h3>{{ s.name }}</h3>
            <span v-if="s.has_ones_ai" class="badge badge-success" style="margin-left:auto;">ones-AI ✓</span>
            <span v-else class="badge badge-warning" style="margin-left:auto;">未安装</span>
          </div>
          <div class="server-meta">
            <span class="server-host">{{ s.host }}:{{ s.ssh_port }}</span>
          </div>
          <p v-if="s.description" class="server-desc">{{ s.description }}</p>
          <div class="server-actions">
            <template v-if="s.has_my_credential">
              <el-button type="primary" size="default" @click="goToTask(s)" :id="'go-task-'+s.id" round>
                <el-icon><Plus /></el-icon> 创建任务
              </el-button>
              <el-button size="default" @click="showCredentials(s)" plain round>凭证管理</el-button>
            </template>
            <template v-else>
              <el-button type="warning" size="default" @click="openVerify(s)" :id="'verify-'+s.id" round>
                <el-icon><Lock /></el-icon> 验证凭证
              </el-button>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- 最近任务 -->
    <div style="margin-top:44px;" class="fade-in-up">
      <h2 class="section-title">
        <span class="section-icon">📋</span> 最近任务
      </h2>
      <div v-if="tasks.length === 0" class="empty-state">
        <div class="empty-icon">🚀</div>
        <p>暂无任务记录</p>
        <span>选择服务器并创建你的第一个工单任务</span>
      </div>
      <div v-for="(t, idx) in tasks" :key="t.id" class="task-row glass-card fade-in-up"
           @click="$router.push('/tasks/'+t.id)"
           :style="{ animationDelay: (idx * 0.04) + 's' }">
        <div class="task-row-left">
          <span class="task-id">#{{ t.id }}</span>
          <span class="task-server">{{ t.server_name }}</span>
          <span :class="'badge badge-' + statusColor(t.status)">{{ statusLabel(t.status) }}</span>
        </div>
        <div class="task-row-right">
          <span class="task-tickets">{{ t.ticket_count }} 个工单</span>
          <span class="task-time">{{ formatTime(t.submitted_at) }}</span>
          <el-icon class="task-arrow"><ArrowRight /></el-icon>
        </div>
      </div>
    </div>

    <!-- 凭证验证弹窗 -->
    <el-dialog v-model="verifyDialog" title="验证服务器凭证" width="460px" :close-on-click-modal="false" id="verify-dialog">
      <p style="color:var(--text-secondary);margin-bottom:20px;font-size:0.9rem;">
        请输入 <strong style="color:var(--accent-light);">{{ verifyServer?.name }}</strong> 的 SSH 登录凭证
      </p>
      <el-form :model="credForm" label-width="80px" label-position="left" autocomplete="off">
        <el-form-item label="用户名">
          <el-input v-model="credForm.ssh_username" placeholder="SSH 用户名" id="cred-username"
                    autocomplete="off" name="ssh-user-new" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="credForm.ssh_password" type="password" placeholder="SSH 密码"
                    show-password id="cred-password" autocomplete="new-password" name="ssh-pass-new" />
        </el-form-item>
        <el-form-item label="别名">
          <el-input v-model="credForm.alias" placeholder="可选，便于区分多组凭证" autocomplete="off" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="verifyDialog=false" round>取消</el-button>
        <el-button type="primary" :loading="verifying" @click="doVerify" id="cred-submit" round>
          {{ verifying ? '验证中...' : '验证并绑定' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 凭证管理弹窗 -->
    <el-dialog v-model="credMgrDialog" title="凭证管理" width="520px" :close-on-click-modal="false" id="cred-mgr-dialog">
      <p style="color:var(--text-secondary);margin-bottom:16px;font-size:0.9rem;">
        <strong style="color:var(--accent-light);">{{ credMgrServer?.name }}</strong>
        <span style="margin-left:8px;font-family:var(--font-mono);font-size:0.82rem;color:var(--text-muted);">{{ credMgrServer?.host }}</span>
      </p>

      <!-- 已有凭证列表 -->
      <div v-if="credList.length > 0" class="cred-list">
        <div v-for="c in credList" :key="c.id" class="cred-item">
          <div class="cred-info">
            <span class="cred-username">{{ c.ssh_username }}</span>
            <span v-if="c.alias" class="cred-alias">{{ c.alias }}</span>
            <span class="cred-status" :class="c.is_verified ? 'verified' : 'unverified'">
              {{ c.is_verified ? '已验证' : '未验证' }}
            </span>
            <span v-if="c.verified_at" class="cred-time">{{ formatCredTime(c.verified_at) }}</span>
          </div>
          <el-popconfirm title="确定删除此凭证？" confirm-button-text="删除" cancel-button-text="取消"
                         @confirm="deleteCred(c)">
            <template #reference>
              <el-button type="danger" size="small" plain round :loading="c._deleting">删除</el-button>
            </template>
          </el-popconfirm>
        </div>
      </div>
      <div v-else class="cred-empty">
        <span>暂无凭证，请点击下方按钮添加</span>
      </div>

      <template #footer>
        <el-button @click="credMgrDialog=false" round>关闭</el-button>
        <el-button type="primary" @click="addNewCred" round>
          <el-icon><Plus /></el-icon> 添加凭证
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import api from '../api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()
const servers = ref([])
const tasks = ref([])
const verifyDialog = ref(false)
const verifyServer = ref(null)
const verifying = ref(false)
const credForm = reactive({ ssh_username: '', ssh_password: '', alias: '' })

const displayName = computed(() => {
  const u = authStore.user
  if (!u) return ''
  return u.display_name || u.ones_email?.split('@')[0] || '用户'
})

const readyServers = computed(() => servers.value.filter(s => s.has_my_credential).length)

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

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

onMounted(async () => {
  try {
    servers.value = await api.getServers()
    const data = await api.getTasks({ page: 1, page_size: 10 })
    tasks.value = data
  } catch (e) { console.warn('Dashboard 数据加载失败:', e) }
})

function goToTask(s) { router.push(`/tasks/new/${s.id}`) }

function openVerify(s) {
  verifyServer.value = s
  credForm.ssh_username = ''
  credForm.ssh_password = ''
  credForm.alias = ''
  verifyDialog.value = true
}

async function doVerify() {
  if (!credForm.ssh_username || !credForm.ssh_password) return ElMessage.warning('请填写账号密码')
  verifying.value = true
  try {
    await api.verifyCredential(verifyServer.value.id, credForm)
    ElMessage.success('🎉 登录成功！凭证已绑定')
    verifyDialog.value = false
    servers.value = await api.getServers()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '验证失败')
  } finally { verifying.value = false }
}

const credMgrDialog = ref(false)
const credMgrServer = ref(null)
const credList = ref([])

async function showCredentials(s) {
  credMgrServer.value = s
  credList.value = []
  credMgrDialog.value = true
  try {
    const data = await api.getCredentials(s.id)
    credList.value = data.map(c => ({ ...c, _deleting: false }))
  } catch (e) {
    ElMessage.error('获取凭证失败')
  }
}

async function deleteCred(c) {
  c._deleting = true
  try {
    await api.deleteCredential(credMgrServer.value.id, c.id)
    credList.value = credList.value.filter(x => x.id !== c.id)
    ElMessage.success('凭证已删除')
    servers.value = await api.getServers()
  } catch (e) {
    ElMessage.error('删除失败')
  } finally { c._deleting = false }
}

function addNewCred() {
  credMgrDialog.value = false
  openVerify(credMgrServer.value)
}

function formatCredTime(t) {
  if (!t) return ''
  const d = new Date(t)
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
/* 欢迎横幅 */
.welcome-banner {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.12) 0%, rgba(59, 130, 246, 0.08) 50%, rgba(168, 85, 247, 0.06) 100%);
  border: 1px solid rgba(99, 102, 241, 0.15);
  border-radius: var(--radius-lg);
  padding: 32px 36px;
  position: relative;
  overflow: hidden;
}
.welcome-banner::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(99, 102, 241, 0.3), rgba(168, 85, 247, 0.2), transparent);
}
.welcome-banner::after {
  content: '';
  position: absolute;
  top: -50%; right: -10%;
  width: 300px; height: 300px;
  background: radial-gradient(circle, rgba(99, 102, 241, 0.08) 0%, transparent 70%);
  pointer-events: none;
}
.welcome-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  position: relative;
  z-index: 1;
}
.welcome-text h1 {
  font-size: 1.5rem;
  font-weight: 700;
  background: linear-gradient(135deg, var(--text-primary), var(--accent-light));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.welcome-text p {
  color: var(--text-secondary);
  margin-top: 6px;
  font-size: 0.9rem;
}
.welcome-stats {
  display: flex;
  align-items: center;
  gap: 20px;
}
.quick-stat { text-align: center; }
.quick-stat-num {
  display: block;
  font-size: 1.8rem;
  font-weight: 800;
  background: var(--accent-gradient);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  line-height: 1.1;
}
.quick-stat-label {
  display: block;
  font-size: 0.72rem;
  color: var(--text-muted);
  margin-top: 4px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
}
.quick-stat-divider {
  width: 1px;
  height: 36px;
  background: var(--border);
}

/* 区块标题 */
.section-title {
  font-size: 1.15rem;
  font-weight: 700;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.section-icon { font-size: 1.1rem; }

/* 服务器网格 */
.servers-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}
.server-card { cursor: default; }
.server-card-top {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.server-card-top h3 { font-size: 1.05rem; font-weight: 700; }
.server-status-dot {
  width: 10px; height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot-online { background: var(--success); box-shadow: 0 0 8px rgba(34, 197, 94, 0.4); }
.dot-offline { background: var(--danger); box-shadow: 0 0 8px rgba(239, 68, 68, 0.3); }
.dot-unknown { background: var(--text-muted); }
.server-meta { font-size: 0.88rem; }
.server-host { color: var(--text-secondary); font-family: var(--font-mono); font-size: 0.82rem; }
.server-desc { color: var(--text-muted); font-size: 0.82rem; margin: 8px 0 0; line-height: 1.5; }
.server-actions { margin-top: 16px; display: flex; gap: 8px; }

/* 任务行 */
.task-row {
  cursor: pointer;
  margin-bottom: 8px;
  padding: 16px 20px !important;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.task-row:hover { border-color: var(--border-active); }
.task-row-left { display: flex; align-items: center; gap: 12px; }
.task-id { font-weight: 700; font-size: 1rem; color: var(--accent-light); font-family: var(--font-mono); }
.task-server { color: var(--text-secondary); font-size: 0.9rem; }
.task-row-right { display: flex; align-items: center; gap: 16px; }
.task-tickets { color: var(--text-secondary); font-size: 0.85rem; }
.task-time { color: var(--text-muted); font-size: 0.82rem; }
.task-arrow { color: var(--text-muted); transition: transform 0.2s; }
.task-row:hover .task-arrow { transform: translateX(3px); color: var(--accent-light); }

/* 空状态 */
.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-muted);
}
.empty-icon { font-size: 3rem; margin-bottom: 12px; opacity: 0.6; }
.empty-state p { font-size: 1rem; color: var(--text-secondary); margin-bottom: 4px; }
.empty-state span { font-size: 0.85rem; }

@media (max-width: 768px) {
  .welcome-content { flex-direction: column; gap: 20px; text-align: center; }
  .servers-grid { grid-template-columns: 1fr; }
}

/* 凭证管理弹窗 */
.cred-list { display: flex; flex-direction: column; gap: 10px; }
.cred-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px;
  background: rgba(255,255,255,0.03);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  transition: border-color 0.2s;
}
.cred-item:hover { border-color: var(--border-active); }
.cred-info { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.cred-username {
  font-weight: 700; font-size: 0.95rem;
  font-family: var(--font-mono);
  color: var(--text-primary);
}
.cred-alias {
  font-size: 0.82rem; color: var(--text-muted);
  background: rgba(99,102,241,0.1);
  padding: 2px 8px; border-radius: 10px;
}
.cred-status {
  font-size: 0.75rem; padding: 2px 8px; border-radius: 10px; font-weight: 600;
}
.cred-status.verified { color: var(--success); background: rgba(34,197,94,0.1); }
.cred-status.unverified { color: var(--warning); background: rgba(245,158,11,0.1); }
.cred-time { font-size: 0.78rem; color: var(--text-muted); }
.cred-empty {
  text-align: center; padding: 32px 16px;
  color: var(--text-muted); font-size: 0.9rem;
}
</style>
