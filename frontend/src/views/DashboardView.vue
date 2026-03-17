<template>
  <div class="page-container" id="dashboard-page">
    <div class="page-header fade-in-up">
      <h1 style="font-size:1.6rem;font-weight:700;">服务器列表</h1>
      <p style="color:var(--text-secondary);margin-top:4px;">选择服务器并验证凭证后即可创建任务</p>
    </div>

    <div class="servers-grid" style="margin-top:24px;">
      <div v-for="s in servers" :key="s.id" class="glass-card server-card fade-in-up" :id="'server-'+s.id">
        <div class="server-header">
          <div class="server-status" :class="'status-' + s.status"></div>
          <h3>{{ s.name }}</h3>
        </div>
        <div class="server-info">
          <span style="color:var(--text-secondary);">{{ s.host }}:{{ s.ssh_port }}</span>
          <span v-if="s.has_ones_ai" class="badge badge-success">ones-AI ✓</span>
          <span v-else class="badge badge-warning">未安装</span>
        </div>
        <p v-if="s.description" style="color:var(--text-muted);font-size:0.85rem;margin:8px 0;">{{ s.description }}</p>

        <div class="server-actions" style="margin-top:16px;">
          <template v-if="s.has_my_credential">
            <el-button type="primary" size="small" @click="goToTask(s)" id="'go-task-'+s.id">
              <el-icon><Plus /></el-icon> 创建任务
            </el-button>
            <el-button size="small" @click="showCredentials(s)" plain>凭证管理</el-button>
          </template>
          <template v-else>
            <el-button type="warning" size="small" @click="openVerify(s)" id="'verify-'+s.id">
              <el-icon><Lock /></el-icon> 验证凭证
            </el-button>
          </template>
        </div>
      </div>
    </div>

    <!-- 最近任务 -->
    <div style="margin-top:40px;" class="fade-in-up">
      <h2 style="font-size:1.2rem;margin-bottom:16px;">最近任务</h2>
      <div v-if="tasks.length === 0" style="color:var(--text-muted);text-align:center;padding:40px;">暂无任务</div>
      <div v-for="t in tasks" :key="t.id" class="glass-card task-row" @click="$router.push('/tasks/'+t.id)"
           style="cursor:pointer;margin-bottom:8px;padding:16px;display:flex;justify-content:space-between;align-items:center;">
        <div>
          <span style="font-weight:600;">#{{ t.id }}</span>
          <span style="margin-left:12px;color:var(--text-secondary);">{{ t.server_name }}</span>
          <span :class="'badge badge-' + statusColor(t.status)" style="margin-left:12px;">{{ t.status }}</span>
        </div>
        <div style="color:var(--text-muted);font-size:0.85rem;">
          {{ t.ticket_count }} 个工单 · {{ t.submitted_at?.substring(0,16) }}
        </div>
      </div>
    </div>

    <!-- 凭证验证弹窗 -->
    <el-dialog v-model="verifyDialog" title="验证服务器凭证" width="440px" :close-on-click-modal="false" id="verify-dialog">
      <p style="color:var(--text-secondary);margin-bottom:20px;font-size:0.9rem;">
        请输入 <strong style="color:var(--text-primary);">{{ verifyServer?.name }}</strong> 的 SSH 登录凭证
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
        <el-button @click="verifyDialog=false">取消</el-button>
        <el-button type="primary" :loading="verifying" @click="doVerify" id="cred-submit">
          {{ verifying ? '验证中...' : '验证并绑定' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const servers = ref([])
const tasks = ref([])
const verifyDialog = ref(false)
const verifyServer = ref(null)
const verifying = ref(false)
const credForm = reactive({ ssh_username: '', ssh_password: '', alias: '' })

onMounted(async () => {
  try {
    servers.value = await api.getServers()
    const data = await api.getTasks({ page: 1, page_size: 10 })
    tasks.value = data
  } catch (e) { console.warn('Dashboard 数据加载失败:', e) }
})

function statusColor(s) {
  return { pending: 'info', running: 'warning', completed: 'success', failed: 'danger', cancelled: 'info' }[s] || 'info'
}

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

function showCredentials(s) { /* 可扩展为凭证管理弹窗 */ }
</script>

<style scoped>
.page-header { padding-bottom: 8px; border-bottom: 1px solid var(--border-color); }
.servers-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px; }
.server-card { transition: all 0.3s; }
.server-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.server-header h3 { font-size: 1.05rem; font-weight: 600; }
.server-status { width: 10px; height: 10px; border-radius: 50%; }
.status-online { background: var(--success); box-shadow: 0 0 6px var(--success); }
.status-offline { background: var(--danger); }
.status-unknown { background: var(--text-muted); }
.server-info { display: flex; gap: 12px; align-items: center; font-size: 0.9rem; }
</style>
