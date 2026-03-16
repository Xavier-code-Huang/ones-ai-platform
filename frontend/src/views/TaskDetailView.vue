<template>
  <div class="page-container" id="task-detail-page">
    <div class="fade-in-up" style="display:flex;justify-content:space-between;align-items:center;">
      <div>
        <h1 style="font-size:1.6rem;">#{{ task.id }} 任务详情</h1>
        <p style="color:var(--text-secondary);margin-top:4px;">{{ task.server_name }} · {{ task.submitted_at?.substring(0,16) }}</p>
      </div>
      <span :class="'badge badge-' + statusColor(task.status)" style="font-size:0.9rem;padding:6px 16px;">{{ statusLabel(task.status) }}</span>
    </div>

    <!-- 进度条 -->
    <div class="glass-card fade-in-up" style="margin-top:20px;padding:16px;">
      <el-progress :percentage="progress" :status="task.status==='completed'?'success':(task.status==='failed'?'exception':undefined)"
                   :stroke-width="8" style="margin-bottom:8px;" />
      <div style="display:flex;gap:24px;font-size:0.85rem;color:var(--text-secondary);">
        <span>工单: {{ task.ticket_count }}</span>
        <span style="color:var(--success);">成功: {{ task.success_count }}</span>
        <span style="color:var(--danger);">失败: {{ task.failed_count }}</span>
        <span>耗时: {{ task.total_duration?.toFixed(0) }}s</span>
      </div>
    </div>

    <!-- 日志查看器 -->
    <div v-if="task.status==='running' || showLog" class="glass-card fade-in-up" style="margin-top:16px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <h3>执行日志</h3>
        <el-button size="small" @click="autoScroll=!autoScroll" :type="autoScroll?'primary':'default'" text>
          {{ autoScroll ? '自动滚动 ON' : '自动滚动 OFF' }}
        </el-button>
      </div>
      <div ref="logContainer" class="log-viewer" id="log-viewer">
        <div v-for="(line, i) in logLines" :key="i">{{ line }}</div>
      </div>
    </div>
    <el-button v-if="task.status!=='running' && !showLog" size="small" @click="showLog=true;loadLogs()"
               style="margin-top:8px;" text type="primary">📄 查看执行日志</el-button>

    <!-- 工单结果列表 -->
    <div style="margin-top:24px;">
      <h2 class="fade-in-up" style="font-size:1.2rem;margin-bottom:12px;">工单结果</h2>
      <div v-for="t in task.tickets||[]" :key="t.id" class="glass-card fade-in-up" style="margin-bottom:12px;padding:16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <div>
            <span style="font-weight:600;color:var(--accent-blue);font-size:1.05rem;">{{ t.ticket_id }}</span>
            <span :class="'badge badge-'+statusColor(t.status)" style="margin-left:12px;">{{ t.status }}</span>
            <span v-if="t.duration" style="color:var(--text-muted);margin-left:12px;font-size:0.85rem;">{{ t.duration.toFixed(0) }}s</span>
          </div>
          <!-- 评价按钮 [FR-008] -->
          <div v-if="t.status==='completed' || t.status==='failed'" style="display:flex;gap:8px;">
            <template v-if="t.evaluation">
              <span :class="t.evaluation.passed ? 'badge badge-success' : 'badge badge-danger'">
                {{ t.evaluation.passed ? '✅ 已通过' : '❌ 未通过' }}
              </span>
            </template>
            <template v-else>
              <el-button size="small" type="success" @click="evaluate(t, true)" circle><el-icon><Check /></el-icon></el-button>
              <el-button size="small" type="danger" @click="evaluate(t, false)" circle><el-icon><Close /></el-icon></el-button>
            </template>
          </div>
        </div>
        <p v-if="t.note" style="color:var(--text-secondary);margin-top:8px;font-size:0.9rem;">💬 {{ t.note }}</p>
        <p v-if="t.result_summary" style="margin-top:8px;font-size:0.9rem;">{{ t.result_summary }}</p>
        <p v-if="t.error_message" style="color:var(--danger);margin-top:8px;font-size:0.9rem;">{{ t.error_message }}</p>
        <div v-if="t.result_report" style="margin-top:12px;padding:12px;background:var(--bg-secondary);border-radius:var(--radius-sm);font-size:0.85rem;" v-html="renderMd(t.result_report)"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const task = ref({})
const logLines = ref([])
const logContainer = ref(null)
const autoScroll = ref(true)
const showLog = ref(false)
let ws = null
let refreshInterval = null

const progress = ref(0)

function statusColor(s) {
  return { pending:'info', running:'warning', completed:'success', failed:'danger', cancelled:'info' }[s] || 'info'
}
function statusLabel(s) {
  return { pending:'排队中', running:'执行中', completed:'已完成', failed:'失败', cancelled:'已取消' }[s] || s
}
function renderMd(text) {
  try { return window.marked?.parse(text) || text } catch { return text }
}

async function loadTask() {
  const data = await api.getTask(route.params.id)
  task.value = data
  const total = data.ticket_count || 1
  progress.value = Math.round(((data.success_count + data.failed_count) / total) * 100)
}

async function loadLogs() {
  // 从全量数据切换时不需额外加载
}

function connectWs() {
  const token = localStorage.getItem('token')
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws = new WebSocket(`${proto}//${location.host}/ws/tasks/${route.params.id}/logs?token=${token}`)
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data)
    if (msg.type === 'log') {
      logLines.value.push(msg.content)
      if (autoScroll.value) nextTick(() => { if (logContainer.value) logContainer.value.scrollTop = logContainer.value.scrollHeight })
    } else if (msg.type === 'complete') {
      loadTask()
    } else if (msg.type === 'progress') {
      loadTask()
    }
  }
  ws.onclose = () => { setTimeout(() => { if (task.value.status === 'running') connectWs() }, 2000) }
}

async function evaluate(ticket, passed) {
  if (!passed) {
    const { value } = await ElMessageBox.prompt('请输入不通过的原因（可选）', '评价', { confirmButtonText: '提交', cancelButtonText: '取消' })
    try {
      await api.submitEval({ task_ticket_id: ticket.id, passed: false, reason: value || '' })
      ElMessage.success('评价已提交')
      await loadTask()
    } catch (err) { ElMessage.error(err.response?.data?.detail || '评价失败') }
  } else {
    await api.submitEval({ task_ticket_id: ticket.id, passed: true })
    ElMessage.success('评价已提交')
    await loadTask()
  }
}

onMounted(async () => {
  await loadTask()
  if (task.value.status === 'running') { showLog.value = true; connectWs() }
  refreshInterval = setInterval(async () => { if (task.value.status === 'running') await loadTask() }, 5000)
})

onUnmounted(() => {
  if (ws) ws.close()
  if (refreshInterval) clearInterval(refreshInterval)
})
</script>
