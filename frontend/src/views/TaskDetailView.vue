<template>
  <div class="page-container" id="task-detail-page">
    <!-- 头部 -->
    <div class="detail-header fade-in-up">
      <div class="detail-header-left">
        <el-button text @click="$router.push('/')" style="margin-right:8px;color:var(--text-muted);">
          <el-icon><ArrowLeft /></el-icon>
        </el-button>
        <div>
          <h1>任务 <span class="task-id-highlight">#{{ task.id }}</span></h1>
          <p class="detail-sub">{{ task.server_name }} · {{ task.submitted_at?.substring(0,16) }}</p>
        </div>
      </div>
      <span :class="'status-pill status-' + task.status">
        <span class="status-dot"></span>
        {{ statusLabel(task.status) }}
      </span>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-row fade-in-up" style="margin-top:20px;">
      <div class="mini-stat">
        <div class="mini-stat-icon" style="background:var(--info-bg);color:var(--info);">📋</div>
        <div>
          <span class="mini-stat-num">{{ task.ticket_count || 0 }}</span>
          <span class="mini-stat-label">工单总数</span>
        </div>
      </div>
      <div class="mini-stat">
        <div class="mini-stat-icon" style="background:var(--success-bg);color:var(--success);">✅</div>
        <div>
          <span class="mini-stat-num" style="color:var(--success);">{{ task.success_count || 0 }}</span>
          <span class="mini-stat-label">成功</span>
        </div>
      </div>
      <div class="mini-stat">
        <div class="mini-stat-icon" style="background:var(--danger-bg);color:var(--danger);">❌</div>
        <div>
          <span class="mini-stat-num" style="color:var(--danger);">{{ task.failed_count || 0 }}</span>
          <span class="mini-stat-label">失败</span>
        </div>
      </div>
      <div class="mini-stat">
        <div class="mini-stat-icon" style="background:rgba(99,102,241,0.1);color:var(--accent-indigo);">⏱️</div>
        <div>
          <span class="mini-stat-num">{{ task.total_duration?.toFixed(0) || 0 }}s</span>
          <span class="mini-stat-label">总耗时</span>
        </div>
      </div>
    </div>

    <!-- 进度条 -->
    <div class="glass-card fade-in-up" style="margin-top:16px;padding:16px 20px;" v-if="task.status==='running'">
      <el-progress :percentage="progress"
                   :stroke-width="8"
                   :color="[{color:'#3b82f6',percentage:30},{color:'#6366f1',percentage:70},{color:'#22c55e',percentage:100}]" />
      <p style="color:var(--text-muted);font-size:0.82rem;margin-top:8px;">任务正在执行中，请稍候...</p>
    </div>

    <!-- 日志查看器 -->
    <div v-if="showLog" class="glass-card fade-in-up" style="margin-top:16px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
        <h3 style="font-size:1rem;font-weight:600;">📄 执行日志 <span v-if="logLoading" style="font-size:0.8rem;color:var(--text-muted);">(加载中...)</span></h3>
        <div style="display:flex;gap:8px;">
          <el-button size="small" @click="autoScroll=!autoScroll" :type="autoScroll?'primary':'default'" text round>
            {{ autoScroll ? '自动滚动 ON' : '自动滚动 OFF' }}
          </el-button>
          <el-button size="small" @click="showLog=false" text round>收起</el-button>
        </div>
      </div>
      <div ref="logContainer" class="log-viewer" id="log-viewer">
        <div v-for="(line, i) in logLines" :key="i" :class="'log-line log-' + (line.type || 'stdout')">
          <span v-if="line.type === 'system'" class="log-tag system">SYS</span>
          <span v-else-if="line.type === 'stderr'" class="log-tag stderr">ERR</span>
          {{ line.content || line }}
        </div>
        <div v-if="!logLines.length && !logLoading" style="color:var(--text-muted);padding:12px;">暂无日志</div>
      </div>
    </div>
    <el-button v-if="!showLog" size="small" @click="showLog=true;loadLogs()"
               style="margin-top:10px;" text type="primary" round>📄 查看执行日志</el-button>

    <!-- 工单结果列表 -->
    <div style="margin-top:28px;">
      <h2 class="section-title fade-in-up">
        <span class="section-icon">🎯</span> 工单处理结果
      </h2>
      <div v-for="(t, idx) in task.tickets||[]" :key="t.id"
           class="glass-card ticket-result-card fade-in-up"
           :style="{ animationDelay: (idx * 0.06) + 's', marginBottom: '14px' }">
        <!-- 头部: 工单号 + 标题 + 状态 -->
        <div class="ticket-header">
          <div class="ticket-info">
            <span class="ticket-num">{{ t.ticket_id }}</span>
            <span v-if="t.ticket_title" class="ticket-title">{{ t.ticket_title }}</span>
            <span :class="'badge badge-'+statusColor(t.status)">{{ statusLabel(t.status) }}</span>
            <span v-if="t.duration" class="ticket-duration">{{ t.duration.toFixed(0) }}s</span>
          </div>
          <!-- 评价按钮 -->
          <div v-if="t.status==='completed' || t.status==='failed'" class="eval-btns">
            <template v-if="t.evaluation">
              <span :class="t.evaluation.passed ? 'badge badge-success' : 'badge badge-danger'" style="padding:4px 12px;">
                {{ t.evaluation.passed ? '✅ 已通过' : '❌ 未通过' }}
              </span>
              <el-button size="small" type="warning" @click="openRework(t)" round style="margin-left:8px;">
                🔄 打回重做
              </el-button>
            </template>
            <template v-else>
              <el-button size="small" type="success" @click="evaluate(t, true)" circle>
                <el-icon><Check /></el-icon>
              </el-button>
              <el-button size="small" type="danger" @click="evaluate(t, false)" circle>
                <el-icon><Close /></el-icon>
              </el-button>
              <el-button size="small" type="warning" @click="openRework(t)" round style="margin-left:8px;">
                🔄 打回重做
              </el-button>
            </template>
          </div>
        </div>

        <!-- AI 结论 -->
        <div v-if="t.result_conclusion" class="conclusion-bar">
          <span class="conclusion-label">🤖 AI 结论</span>
          {{ t.result_conclusion }}
        </div>

        <!-- [FR-020] AI 处理详情（折叠区域） -->
        <div v-if="t.result_analysis" class="analysis-section">
          <div class="analysis-toggle" @click="t._showAnalysis = !t._showAnalysis">
            <span class="toggle-icon">{{ t._showAnalysis ? '▼' : '▶' }}</span>
            <span class="toggle-label">AI 处理详情</span>
            <span class="toggle-hint" v-if="!t._showAnalysis">点击展开查看分析过程</span>
          </div>
          <div v-if="t._showAnalysis" class="analysis-content" v-html="renderMd(t.result_analysis)"></div>
        </div>

        <!-- 补充说明 -->
        <p v-if="t.note" class="ticket-note">💬 {{ t.note }}</p>

        <!-- 分析摘要 -->
        <div v-if="t.result_summary && !t.result_analysis" class="ticket-summary">
          {{ t.result_summary }}
        </div>

        <!-- 错误信息 -->
        <div v-if="t.error_message" class="ticket-error">
          <el-icon><Warning /></el-icon> {{ t.error_message }}
        </div>

        <!-- 操作按钮 -->
        <div class="ticket-actions" v-if="t.result_report || t.report_path">
          <el-button v-if="t.result_report" size="small" type="primary" @click="viewReport(t)" round>
            📄 查看详细报告
          </el-button>
          <span v-else-if="t.report_path" class="report-path-hint">
            ⚠️ 报告路径: {{ t.report_path }}（未能获取内容）
          </span>
        </div>

        <!-- 内嵌报告 -->
        <div v-if="t._showReport && t.result_report" class="report-inline" v-html="renderMd(t.result_report)"></div>
      </div>
    </div>

    <!-- 报告弹窗 -->
    <el-dialog v-model="reportDialogVisible" title="📋 完整分析报告" width="75%" :close-on-click-modal="true" top="5vh">
      <div v-if="reportLoading" style="text-align:center;padding:40px;color:var(--text-muted);">
        <el-icon class="is-loading" :size="24"><Loading /></el-icon>
        <p style="margin-top:8px;">加载报告中...</p>
      </div>
      <div v-else-if="reportContent" class="report-content" v-html="renderMd(reportContent)"></div>
      <div v-else style="text-align:center;color:var(--text-muted);padding:40px;">暂无报告内容</div>
    </el-dialog>

    <!-- 打回重做弹窗 -->
    <el-dialog v-model="reworkDialogVisible" title="🔄 打回重做" width="600px" top="20vh">
      <div v-if="reworkTicket" style="margin-bottom:16px;">
        <p style="color:var(--text-muted);margin-bottom:8px;">工单：<strong>{{ reworkTicket.ticket_id }}</strong></p>
        <p v-if="reworkTicket.result_summary" style="color:var(--text-muted);font-size:0.85rem;margin-bottom:12px;">
          上次结果：{{ reworkTicket.result_summary }}
        </p>
        <el-input v-model="reworkFeedback" type="textarea" :rows="5"
                  placeholder="请输入追加要求，例如：请直接修改代码，不要只给方案" />
      </div>
      <template #footer>
        <el-button @click="reworkDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitRework" :loading="reworkSubmitting">提交重做</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const task = ref({})
const logLines = ref([])
const logContainer = ref(null)
const autoScroll = ref(true)
const showLog = ref(false)
const logLoading = ref(false)
let ws = null
let refreshInterval = null

const progress = ref(0)
const reportDialogVisible = ref(false)
const reportContent = ref('')
const reportLoading = ref(false)

function statusColor(s) {
  return { pending:'info', running:'warning', completed:'success', failed:'danger', cancelled:'info' }[s] || 'info'
}
function statusLabel(s) {
  return { pending:'排队中', running:'执行中', completed:'已完成', failed:'失败', cancelled:'已取消' }[s] || s
}
function renderMd(text) {
  const safe = text.replace(/<script[\s\S]*?<\/script>/gi, '')
                    .replace(/<iframe[\s\S]*?<\/iframe>/gi, '')
                    .replace(/on\w+\s*=\s*["'][^"']*["']/gi, '')
  try { return window.marked?.parse(safe) || safe } catch { return safe }
}

async function loadTask() {
  const data = await api.getTask(route.params.id)
  // 为每个 ticket 初始化折叠状态（确保 Vue 响应式）
  if (data.tickets) {
    data.tickets.forEach(t => {
      t._showAnalysis = false
      t._showReport = false
    })
  }
  task.value = data
  const total = data.ticket_count || 1
  progress.value = Math.round(((data.success_count + data.failed_count) / total) * 100)
}

async function loadLogs() {
  if (logLines.value.length > 0) return  // 已加载过
  logLoading.value = true
  try {
    const data = await api.getTaskLogs(route.params.id)
    if (data.logs && data.logs.length) {
      logLines.value = data.logs.map(l => ({ content: l.content, type: l.log_type }))
      nextTick(() => { if (logContainer.value) logContainer.value.scrollTop = logContainer.value.scrollHeight })
    }
  } catch (err) {
    logLines.value = [{ content: '日志加载失败: ' + (err.response?.data?.detail || err.message), type: 'stderr' }]
  } finally { logLoading.value = false }
}

function connectWs() {
  const token = localStorage.getItem('token')
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws = new WebSocket(`${proto}//${location.host}/ws/tasks/${route.params.id}/logs?token=${token}`)
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data)
    if (msg.type === 'log') {
      logLines.value.push({ content: msg.content, type: msg.log_type || 'stdout' })
      if (autoScroll.value) nextTick(() => { if (logContainer.value) logContainer.value.scrollTop = logContainer.value.scrollHeight })
    } else if (msg.type === 'complete' || msg.type === 'progress') {
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

// 打回重做
const reworkDialogVisible = ref(false)
const reworkTicket = ref(null)
const reworkFeedback = ref('')
const reworkSubmitting = ref(false)

function openRework(ticket) {
  reworkTicket.value = ticket
  reworkFeedback.value = ''
  reworkDialogVisible.value = true
}

async function submitRework() {
  if (!reworkFeedback.value.trim()) return ElMessage.warning('请输入追加要求')
  reworkSubmitting.value = true
  try {
    await api.reworkTicket(route.params.id, reworkTicket.value.id, { feedback: reworkFeedback.value })
    ElMessage.success('已提交重做，任务将重新执行')
    reworkDialogVisible.value = false
    await loadTask()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '提交失败')
  } finally {
    reworkSubmitting.value = false
  }
}

async function viewReport(ticket) {
  if (ticket.result_report) {
    reportContent.value = ticket.result_report
    reportDialogVisible.value = true
    return
  }
  reportLoading.value = true
  reportContent.value = ''
  reportDialogVisible.value = true
  try {
    const data = await api.getTicketReport(route.params.id, ticket.ticket_id)
    reportContent.value = data.report || '暂无报告内容'
  } catch (err) {
    reportContent.value = '加载报告失败: ' + (err.response?.data?.detail || err.message)
  } finally { reportLoading.value = false }
}

onMounted(async () => {
  await loadTask()
  if (task.value.status === 'running') {
    showLog.value = true
    connectWs()
  } else if (task.value.status === 'completed' || task.value.status === 'failed') {
    // 已完成的任务：自动展示日志区域并从 API 加载历史日志
    showLog.value = true
    await loadLogs()
  }
  refreshInterval = setInterval(async () => { if (task.value.status === 'running') await loadTask() }, 5000)
})

onUnmounted(() => {
  if (ws) ws.close()
  if (refreshInterval) clearInterval(refreshInterval)
})
</script>

<style scoped>
.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.detail-header-left { display: flex; align-items: center; gap: 4px; }
.detail-header h1 { font-size: 1.5rem; font-weight: 700; }
.task-id-highlight { color: var(--accent-light); font-family: var(--font-mono); }
.detail-sub { color: var(--text-secondary); font-size: 0.88rem; margin-top: 2px; }

/* 状态胶囊 */
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 18px;
  border-radius: 20px;
  font-size: 0.85rem;
  font-weight: 600;
}
.status-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: currentColor;
}
.status-pending { background: var(--info-bg); color: var(--info); border: 1px solid var(--info-border); }
.status-running { background: var(--warning-bg); color: var(--warning); border: 1px solid var(--warning-border); }
.status-running .status-dot { animation: pulse-glow 1.5s ease-in-out infinite; }
.status-completed { background: var(--success-bg); color: var(--success); border: 1px solid var(--success-border); }
.status-failed { background: var(--danger-bg); color: var(--danger); border: 1px solid var(--danger-border); }

/* 统计行 */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}
.mini-stat {
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius);
  padding: 16px 18px;
  display: flex;
  align-items: center;
  gap: 14px;
  transition: all var(--transition);
}
.mini-stat:hover { border-color: var(--border-hover); }
.mini-stat-icon {
  width: 42px; height: 42px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.2rem;
  flex-shrink: 0;
}
.mini-stat-num {
  display: block;
  font-size: 1.5rem;
  font-weight: 800;
  color: var(--text-primary);
  line-height: 1.1;
}
.mini-stat-label {
  display: block;
  font-size: 0.72rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
  margin-top: 2px;
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

/* 工单结果卡片 */
.ticket-result-card { padding: 20px 22px !important; }
.ticket-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.ticket-info { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.ticket-num {
  font-weight: 700;
  color: var(--accent-blue);
  font-size: 1.05rem;
  font-family: var(--font-mono);
}
.ticket-title {
  color: var(--text-primary);
  font-size: 0.95rem;
  font-weight: 600;
}
.ticket-duration {
  color: var(--text-muted);
  font-size: 0.82rem;
  font-family: var(--font-mono);
}
.eval-btns { display: flex; gap: 6px; }

/* 结论条 */
.conclusion-bar {
  margin-top: 14px;
  padding: 12px 16px;
  background: linear-gradient(90deg, rgba(99,102,241,0.08), transparent);
  border-left: 3px solid var(--accent-indigo);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  font-size: 0.88rem;
  color: var(--text-primary);
  line-height: 1.6;
}
.conclusion-label {
  color: var(--accent-indigo);
  font-weight: 600;
  font-size: 0.8rem;
  margin-right: 6px;
}

.ticket-note {
  color: var(--text-secondary);
  margin-top: 10px;
  font-size: 0.88rem;
}
.ticket-summary {
  margin-top: 10px;
  font-size: 0.88rem;
  color: var(--text-primary);
  line-height: 1.6;
  padding: 10px 14px;
  background: var(--bg-surface);
  border-radius: var(--radius-sm);
}
.ticket-error {
  color: var(--danger);
  margin-top: 10px;
  font-size: 0.88rem;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: var(--danger-bg);
  border-radius: var(--radius-sm);
  border: 1px solid var(--danger-border);
}
/* [FR-020] AI 处理详情折叠区域 */
.analysis-section {
  margin-top: 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.analysis-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  cursor: pointer;
  background: var(--bg-surface);
  transition: background 0.2s;
  user-select: none;
}
.analysis-toggle:hover { background: var(--bg-secondary); }
.toggle-icon {
  font-size: 0.75rem;
  color: var(--accent-indigo);
  transition: transform 0.2s;
  width: 14px;
  text-align: center;
}
.toggle-label {
  font-weight: 600;
  font-size: 0.88rem;
  color: var(--accent-indigo);
}
.toggle-hint {
  font-size: 0.78rem;
  color: var(--text-muted);
  margin-left: auto;
}
.analysis-content {
  padding: 16px 20px;
  font-size: 0.88rem;
  line-height: 1.7;
  max-height: 500px;
  overflow-y: auto;
  border-top: 1px solid var(--border);
  animation: slideDown 0.2s ease;
}
.analysis-content h1, .analysis-content h2, .analysis-content h3 {
  margin-top: 16px;
  margin-bottom: 8px;
  color: var(--text-primary);
}
.analysis-content h1 { font-size: 1.1rem; }
.analysis-content h2 { font-size: 1rem; }
.analysis-content h3 { font-size: 0.95rem; }
.analysis-content table {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
}
.analysis-content th, .analysis-content td {
  padding: 8px 12px;
  border: 1px solid var(--border);
  text-align: left;
}
.analysis-content th { background: var(--bg-secondary); font-weight: 600; }
.analysis-content code {
  background: var(--bg-surface);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 0.85em;
}
.analysis-content pre {
  background: var(--bg-surface);
  padding: 14px;
  border-radius: var(--radius-sm);
  overflow-x: auto;
  border: 1px solid var(--border);
}
.analysis-content ul, .analysis-content ol {
  padding-left: 20px;
  margin: 8px 0;
}
.analysis-content li { margin-bottom: 4px; }

@keyframes slideDown {
  from { opacity: 0; max-height: 0; }
  to { opacity: 1; max-height: 500px; }
}

/* 报告路径提示 */
.report-path-hint {
  font-size: 0.82rem;
  color: var(--text-muted);
  font-style: italic;
}

.ticket-actions { margin-top: 14px; }

.report-inline {
  margin-top: 14px;
  padding: 16px;
  background: var(--bg-surface);
  border-radius: var(--radius-sm);
  font-size: 0.85rem;
  line-height: 1.7;
  max-height: 450px;
  overflow: auto;
  border: 1px solid var(--border);
}

.report-content {
  max-height: 65vh;
  overflow: auto;
  font-size: 0.9rem;
  line-height: 1.8;
  padding: 4px;
}
.report-content h1, .report-content h2, .report-content h3 {
  margin-top: 18px;
  margin-bottom: 8px;
  color: var(--text-primary);
}
.report-content table {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
}
.report-content th, .report-content td {
  padding: 8px 12px;
  border: 1px solid var(--border);
  text-align: left;
}
.report-content th { background: var(--bg-secondary); font-weight: 600; }
.report-content code {
  background: var(--bg-surface);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 0.85em;
}
.report-content pre {
  background: var(--bg-surface);
  padding: 14px;
  border-radius: var(--radius-sm);
  overflow-x: auto;
  border: 1px solid var(--border);
}

@keyframes pulse-glow {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

@media (max-width: 768px) {
  .stats-row { grid-template-columns: repeat(2, 1fr); }
  .detail-header { flex-direction: column; gap: 12px; align-items: flex-start; }
}

/* 日志行分类 */
.log-line {
  padding: 2px 0;
  font-family: var(--font-mono);
  font-size: 0.82rem;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
}
.log-system { color: var(--accent-blue); }
.log-stderr { color: var(--danger); }
.log-stdout { color: var(--text-primary); }
.log-tag {
  display: inline-block;
  padding: 0 5px;
  border-radius: 3px;
  font-size: 0.7rem;
  font-weight: 700;
  margin-right: 6px;
  vertical-align: middle;
}
.log-tag.system { background: rgba(59,130,246,0.15); color: var(--accent-blue); }
.log-tag.stderr { background: var(--danger-bg); color: var(--danger); }
</style>
