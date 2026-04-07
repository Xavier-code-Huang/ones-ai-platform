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
        <div class="mini-stat-icon" style="background:var(--accent-bg);color:var(--accent);">⏱️</div>
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
                   :color="[{color:'#3b82f6',percentage:30},{color:'#1e40af',percentage:70},{color:'#22c55e',percentage:100}]" />
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px;">
        <p style="color:var(--text-muted);font-size:0.82rem;margin:0;">任务正在执行中，请耐心等待或选择下方工单进行干预...</p>
      </div>
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

    <!-- 双栏布局：工单列表 + 阶段时间线 -->
    <div style="margin-top:28px;">
      <h2 class="section-title fade-in-up">
        <span class="section-icon">🎯</span> 工单处理结果
      </h2>
      <div class="dual-panel">
        <!-- 左栏: 工单卡片列表 -->
        <div class="panel-left">
          <TicketCard
            v-for="t in task.tickets || []"
            :key="t.id"
            :ticket-id="t.ticket_id"
            :ticket-db-id="t.id"
            :status="t.status"
            :conclusion="t.result_conclusion || ''"
            :duration="t.duration || 0"
            :is-active="selectedTicketId === t.id"
            @select="selectTicket"
            @edit="openEditTicket"
            style="margin-bottom:8px;"
          />
          <div v-if="!task.tickets?.length" style="padding:24px;text-align:center;color:var(--text-muted);font-size:13px;">
            暂无工单数据
          </div>
        </div>

        <!-- 右栏: 阶段时间线 + 工单详情 -->
        <div class="panel-right">
          <!-- 阶段时间线 -->
          <div class="glass-card" style="padding:16px 18px;margin-bottom:14px;">
            <div style="font-size:13px;font-weight:600;margin-bottom:10px;display:flex;align-items:center;gap:6px;">
              ⏱️ 处理阶段
              <span v-if="selectedTicket" style="color:var(--text-muted);font-weight:400;">- {{ selectedTicket.ticket_id }}</span>
            </div>
            <PhaseTimeline :phases="currentPhases" />
          </div>

          <!-- 工单详情（当前选中的工单） -->
          <template v-if="selectedTicket">
            <div class="glass-card ticket-result-card fade-in-up" style="margin-bottom:14px;">
              <!-- 头部: 工单号 + 标题 + 状态 -->
              <div class="ticket-header">
                <div class="ticket-info">
                  <span class="ticket-num">{{ selectedTicket.ticket_id }}</span>
                  <span v-if="selectedTicket.ticket_title" class="ticket-title">{{ selectedTicket.ticket_title }}</span>
                  <span :class="'badge badge-'+statusColor(selectedTicket.status)">{{ statusLabel(selectedTicket.status) }}</span>
                  <span v-if="selectedTicket.duration" class="ticket-duration">{{ selectedTicket.duration.toFixed(0) }}s</span>
                </div>
                <!-- 容器控制按钮 -->
                <div v-if="['running', 'completed', 'failed', 'cancelled'].includes(task.status)" class="container-controls" style="margin-left:auto;">
                  <!-- 场景A: 任务执行中，但还没拿到容器名 -->
                  <el-button v-if="task.status === 'running' && !currentContainerName" size="small" type="info" round disabled>
                    ⏳ 容器准备中
                  </el-button>
                  <!-- 场景B: 任务执行中，且已拿到任务容器名 (观测模式) -->
                  <el-button v-else-if="task.status === 'running' && currentContainerName" size="small" type="primary" round @click="toggleTerminal">
                    🖥️ {{ showTerminal ? '收起终端' : '观测容器' }}
                  </el-button>
                  <!-- 场景C: 任务已结束 → 历史回放按钮 -->
                  <el-button v-else-if="task.status !== 'running'" size="small" :type="showTerminal ? 'info' : 'primary'" round @click="toggleReplay" :loading="replayLoading">
                    📼 {{ showTerminal ? '收起回放' : '历史回放' }}
                  </el-button>
                  <!-- 场景D: 唤醒干预环境（移到回放按钮旁边） -->
                  <el-button v-if="task.status !== 'running' && !isInterveneContainer && !showTerminal" size="small" type="warning" round @click="startContainer" :loading="startingContainer" style="margin-left:6px;">
                    📦 唤醒干预
                  </el-button>
                  <!-- 场景E: 有干预容器正在运行 -->
                  <el-button v-if="task.status !== 'running' && isInterveneContainer && containerStatus === 'running'" size="small" type="success" round @click="toggleTerminal" style="margin-left:6px;">
                    ⌨️ {{ showTerminal && terminalMode === 'live' ? '收起干预' : '进入干预' }}
                  </el-button>
                  <!-- 场景F: 有干预容器但休眠 -->
                  <el-button v-if="task.status !== 'running' && isInterveneContainer && containerStatus !== 'running'" size="small" type="warning" round @click="startContainer" :loading="startingContainer" style="margin-left:6px;">
                    ⚡ 恢复干预
                  </el-button>
                </div>
                
                <!-- 评价按钮 -->
                <div v-if="selectedTicket.status==='completed' || selectedTicket.status==='failed'" class="eval-btns" style="margin-left:12px;">
                  <template v-if="selectedTicket.evaluation">
                    <span :class="selectedTicket.evaluation.passed ? 'badge badge-success' : 'badge badge-danger'" style="padding:4px 12px;">
                      {{ selectedTicket.evaluation.passed ? '✅ 已通过' : '❌ 未通过' }}
                    </span>
                    <el-button size="small" type="warning" @click="openRework(selectedTicket)" round style="margin-left:8px;">
                      🔄 打回
                    </el-button>
                  </template>
                  <template v-else>
                    <el-button size="small" type="success" @click="evaluate(selectedTicket, true)" circle>
                      <el-icon><Check /></el-icon>
                    </el-button>
                    <el-button size="small" type="danger" @click="evaluate(selectedTicket, false)" circle>
                      <el-icon><Close /></el-icon>
                    </el-button>
                    <el-button size="small" type="warning" @click="openRework(selectedTicket)" round style="margin-left:8px;">
                      🔄 打回
                    </el-button>
                  </template>
                </div>
              </div>

              <!-- Web Terminal 容器面板（支持 live / replay 模式） -->
              <WebTerminal
                ref="webTerminalRef"
                :ticket-db-id="selectedTicket.id"
                :ticket-id-str="selectedTicket.ticket_id"
                :visible="showTerminal"
                :server-info="task.server_name || ''"
                :auto-resume="true"
                :mode="terminalMode"
                :replay-logs="replayLogs"
                class="fade-in-down"
                style="margin: 12px 0 16px 0;"
              />

              <!-- AI 结论 -->
              <div v-if="selectedTicket.result_conclusion" class="conclusion-bar">
                <span class="conclusion-label">🤖 AI 结论</span>
                <span v-html="renderMd(selectedTicket.result_conclusion)"></span>
              </div>

              <!-- AI 处理详情 -->
              <div v-if="selectedTicket.result_analysis" class="analysis-section">
                <div class="analysis-toggle" @click="selectedTicket._showAnalysis = !selectedTicket._showAnalysis">
                  <span class="toggle-icon">{{ selectedTicket._showAnalysis ? '▼' : '▶' }}</span>
                  <span class="toggle-label">AI 处理详情</span>
                  <span class="toggle-hint" v-if="!selectedTicket._showAnalysis">点击展开查看分析过程</span>
                </div>
                <div v-if="selectedTicket._showAnalysis" class="analysis-content" v-html="renderMd(selectedTicket.result_analysis)"></div>
              </div>

              <!-- 补充说明 -->
              <p v-if="selectedTicket.note" class="ticket-note">💬 {{ selectedTicket.note }}</p>

              <!-- 分析摘要 -->
              <div v-if="selectedTicket.result_summary && !selectedTicket.result_analysis" class="ticket-summary" v-html="renderMd(selectedTicket.result_summary)"></div>

              <!-- 错误信息 -->
              <div v-if="selectedTicket.error_message" class="ticket-error">
                <el-icon><Warning /></el-icon> {{ selectedTicket.error_message }}
              </div>

              <!-- 操作按钮 -->
              <div class="ticket-actions" v-if="selectedTicket.result_report || selectedTicket.report_path">
                <el-button v-if="selectedTicket.result_report" size="small" type="primary" @click="viewReport(selectedTicket)" round>
                  📄 查看详细报告
                </el-button>
                <span v-else-if="selectedTicket.report_path" class="report-path-hint">
                  ⚠️ 报告路径: {{ selectedTicket.report_path }}（未能获取内容）
                </span>
              </div>

              <!-- 内嵌报告 -->
              <div v-if="selectedTicket._showReport && selectedTicket.result_report" class="report-inline" v-html="renderMd(selectedTicket.result_report)"></div>
            </div>
          </template>
          <div v-else class="glass-card" style="padding:32px;text-align:center;color:var(--text-muted);font-size:13px;">
            ← 点击左侧工单查看处理详情
          </div>
        </div>
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

    <!-- 编辑工单弹窗 -->
    <el-dialog v-model="editDialogVisible" title="✏️ 编辑工单" width="500px" top="20vh">
      <div v-if="editTicket" style="display:flex;flex-direction:column;gap:16px;">
        <div>
          <label style="font-size:13px;font-weight:600;margin-bottom:6px;display:block;">工单号</label>
          <el-input :model-value="editTicket.ticket_id" disabled />
        </div>
        <div>
          <label style="font-size:13px;font-weight:600;margin-bottom:6px;display:block;">代码路径</label>
          <el-input v-model="editForm.code_directory" placeholder="代码目录绝对路径" />
        </div>
        <div>
          <label style="font-size:13px;font-weight:600;margin-bottom:6px;display:block;">补充说明</label>
          <el-input v-model="editForm.note" type="textarea" :rows="3" placeholder="对此工单的补充说明" />
        </div>
      </div>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitEditTicket" :loading="editSubmitting">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { marked } from 'marked'
import PhaseTimeline from '../components/PhaseTimeline.vue'
import TicketCard from '../components/TicketCard.vue'
import WebTerminal from '../components/WebTerminal.vue'

const route = useRoute()
const task = ref({})
const logLines = ref([])
const logContainer = ref(null)
const autoScroll = ref(true)
const showLog = ref(false)
const logLoading = ref(false)
let ws = null
let refreshInterval = null
let _unmounted = false

// Web Terminal 控制
const showTerminal = ref(false)
const containerStatus = ref(null) // running, exited, not_bound, not_found, error
const currentContainerName = ref('')
const isInterveneContainer = computed(() => currentContainerName.value.includes('intervene'))
const startingContainer = ref(false)
const webTerminalRef = ref(null)

// 回放模式
const terminalMode = ref('live')  // 'live' | 'replay'
const replayLogs = ref([])
const replayLoading = ref(false)

const progress = ref(0)
const reportDialogVisible = ref(false)
const reportContent = ref('')
const reportLoading = ref(false)

// 双栏状态
const selectedTicketId = ref(null)
const ticketPhasesMap = ref({}) // { ticketDbId: [phase1, phase2, ...] }

const selectedTicket = computed(() => {
  return (task.value.tickets || []).find(t => t.id === selectedTicketId.value) || null
})

const currentPhases = computed(() => {
  return ticketPhasesMap.value[selectedTicketId.value] || []
})

function selectTicket(ticketDbId) {
  selectedTicketId.value = ticketDbId
  // 如果还没加载过 phase，从 API 拉取
  if (!ticketPhasesMap.value[ticketDbId]) {
    loadTicketPhases(ticketDbId)
  }
}

async function loadTicketPhases(ticketDbId) {
  try {
    const res = await api.getTicketPhases(route.params.id, ticketDbId)
    ticketPhasesMap.value[ticketDbId] = res.phases || []
  } catch (e) {
    // 旧任务无 phase 数据，兼容处理
    ticketPhasesMap.value[ticketDbId] = []
  }
}

function toggleTerminal() {
  terminalMode.value = 'live'
  showTerminal.value = !showTerminal.value
}

async function toggleReplay() {
  if (showTerminal.value && terminalMode.value === 'replay') {
    // 收起回放
    showTerminal.value = false
    return
  }
  // 加载日志并开始回放
  replayLoading.value = true
  try {
    const taskId = route.params.id
    const ticketDbId = selectedTicketId.value
    const data = await api.getTicketTerminalLogs(taskId, ticketDbId)
    if (data.logs && data.logs.length) {
      replayLogs.value = data.logs
      terminalMode.value = 'replay'
      showTerminal.value = true
    } else {
      ElMessage.info('暂无该工单的执行日志')
    }
  } catch (e) {
    ElMessage.error('加载日志失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    replayLoading.value = false
  }
}

// 查询容器状态
async function fetchContainerStatus(ticketDbId) {
  if (!ticketDbId) return
  containerStatus.value = null
  try {
    const res = await api.getContainerStatus(route.params.id, ticketDbId)
    containerStatus.value = res.status
    currentContainerName.value = res.container_name || ''
    if (res.status === 'running') {
      // 若是正在执行的任务且刚选中工单默认打开终端的话可在此配置
      if (task.value.status === 'running' && !showTerminal.value && !isInterveneContainer.value) {
        showTerminal.value = true
      }
    } else {
      showTerminal.value = false
    }
  } catch (e) {
    console.error("查询容器状态失败", e)
    containerStatus.value = 'error'
  }
}

// 一键唤醒(启动)容器
async function startContainer() {
  startingContainer.value = true
  try {
    const res = await api.startContainer(route.params.id, selectedTicketId.value)
    const data = res.data || res
    if (data.created) {
      // 新建的干预容器
      const ticket = (task.value.tickets || []).find(t => t.id === selectedTicketId.value)
      const ticketId = ticket?.ticket_id || ''
      ElMessage({
        type: 'success',
        message: `干预容器已创建 (${data.container_name})，终端已打开`,
        duration: 5000,
      })
      // 提示报告位置
      if (ticketId) {
        setTimeout(() => {
          ElMessage({
            type: 'info',
            message: `💡 可在 claude 中引用: ~/*/workspace/doc/${ticketId}/report/1.md`,
            duration: 10000,
          })
        }, 1500)
      }
    } else {
      ElMessage.success(data.message || "容器唤醒成功")
    }
    // 刷新容器状态并打开终端
    containerStatus.value = 'running'
    showTerminal.value = true
    // 重新获取容器状态以更新容器名
    await fetchContainerStatus(selectedTicketId.value)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "容器唤醒失败")
  } finally {
    startingContainer.value = false
  }
}

// 监听工单切换
watch(selectedTicketId, (newId) => {
  if (newId) {
    showTerminal.value = false // 切换时先折叠终端
    fetchContainerStatus(newId)
  }
})

// 编辑工单
const editDialogVisible = ref(false)
const editTicket = ref(null)
const editForm = ref({ note: '', code_directory: '' })
const editSubmitting = ref(false)

function openEditTicket(ticketDbId) {
  const t = (task.value.tickets || []).find(x => x.id === ticketDbId)
  if (!t || t.status !== 'pending') return ElMessage.warning('只能编辑排队中的工单')
  editTicket.value = t
  editForm.value = { note: t.note || '', code_directory: t.code_directory || '' }
  editDialogVisible.value = true
}

async function submitEditTicket() {
  editSubmitting.value = true
  try {
    await api.editTicket(route.params.id, editTicket.value.id, editForm.value)
    ElMessage.success('工单已更新')
    editDialogVisible.value = false
    await loadTask()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '更新失败')
  } finally {
    editSubmitting.value = false
  }
}

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
  try { return marked.parse(safe) || safe } catch { return safe }
}

async function loadTask() {
  const data = await api.getTask(route.params.id)
  // 保留已展开的折叠状态（防止 WS progress 刷新导致折叠）
  const oldTickets = task.value?.tickets || []
  const expandedMap = {}
  oldTickets.forEach(t => {
    if (t._showAnalysis || t._showReport) expandedMap[t.id] = { a: t._showAnalysis, r: t._showReport }
  })
  if (data.tickets) {
    data.tickets.forEach(t => {
      const prev = expandedMap[t.id]
      t._showAnalysis = prev?.a || false
      t._showReport = prev?.r || false
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

let _progressTimer = null
function connectWs() {
  const taskId = route.params.id
  if (!taskId || taskId === 'undefined' || _unmounted) return
  const token = localStorage.getItem('token')
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws = new WebSocket(`${proto}//${location.host}/ws/tasks/${taskId}/logs?token=${token}`)
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data)
    if (msg.type === 'log') {
      logLines.value.push({ content: msg.content, type: msg.log_type || 'stdout', phase: msg.phase_name || '' })
      if (autoScroll.value) nextTick(() => { if (logContainer.value) logContainer.value.scrollTop = logContainer.value.scrollHeight })
    } else if (msg.type === 'phase_change') {
      // 更新本地 phase 缓存
      const dbId = msg.ticket_db_id
      if (!ticketPhasesMap.value[dbId]) ticketPhasesMap.value[dbId] = []
      const phases = ticketPhasesMap.value[dbId]
      const idx = phases.findIndex(p => p.phase_name === msg.phase)
      if (idx >= 0) {
        phases[idx] = { ...phases[idx], status: msg.status, message: msg.message }
      } else {
        phases.push({ phase_name: msg.phase, phase_label: msg.phase_label, icon: msg.phase_icon, status: msg.status, message: msg.message })
      }
      ticketPhasesMap.value = { ...ticketPhasesMap.value } // 触发响应
      // 自动选中第一个 running 的工单
      if (!selectedTicketId.value) selectedTicketId.value = dbId
    } else if (msg.type === 'phases_snapshot') {
      ticketPhasesMap.value[msg.ticket_db_id] = msg.phases || []
      ticketPhasesMap.value = { ...ticketPhasesMap.value }
    } else if (msg.type === 'container_bound') {
      if (msg.ticket_db_id === selectedTicketId.value) {
        currentContainerName.value = msg.container_name
        containerStatus.value = 'running'
        if (!showTerminal.value && !isInterveneContainer.value) {
          showTerminal.value = true
        }
      }
    } else if (msg.type === 'complete') {
      loadTask()
      fetchContainerStatus(selectedTicketId.value)
    } else if (msg.type === 'progress') {
      if (_progressTimer) clearTimeout(_progressTimer)
      _progressTimer = setTimeout(() => {
        loadTask()
        if (selectedTicketId.value) fetchContainerStatus(selectedTicketId.value)
      }, 3000)
    }
  }
  ws.onclose = () => { setTimeout(() => { if (!_unmounted && task.value.status === 'running') connectWs() }, 2000) }
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
  _unmounted = true
  if (ws) ws.close()
  if (refreshInterval) clearInterval(refreshInterval)
  if (_progressTimer) clearTimeout(_progressTimer)
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
  background: linear-gradient(90deg, rgba(59,130,246,0.08), transparent);
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
  font-size: 15px;
  line-height: 1.75;
  padding: 12px 16px;
  color: #1e293b;
}
/* 使用 :deep() 穿透 scoped 限制，作用于 v-html 渲染的 markdown 内容 */
.report-content :deep(*) {
  color: #1e293b;
}
.report-content :deep(h1) {
  font-size: 22px;
  margin-top: 24px;
  margin-bottom: 12px;
  color: #0f172a !important;
  font-weight: 700;
}
.report-content :deep(h2) {
  font-size: 19px;
  margin-top: 20px;
  margin-bottom: 10px;
  color: #0f172a !important;
  font-weight: 600;
}
.report-content :deep(h3) {
  font-size: 16px;
  margin-top: 16px;
  margin-bottom: 8px;
  color: #1e293b !important;
  font-weight: 600;
}
.report-content :deep(h4),
.report-content :deep(h5),
.report-content :deep(h6) {
  color: #1e293b !important;
  font-weight: 600;
}
.report-content :deep(p) {
  margin: 8px 0;
  color: #1e293b !important;
}
.report-content :deep(ul),
.report-content :deep(ol) {
  margin: 8px 0;
  padding-left: 24px;
  color: #1e293b !important;
}
.report-content :deep(li) {
  margin: 4px 0;
  color: #1e293b !important;
}
.report-content :deep(strong) {
  color: #0f172a !important;
  font-weight: 700;
}
.report-content :deep(em) {
  color: #334155 !important;
}
.report-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 14px 0;
  font-size: 14px;
}
.report-content :deep(th),
.report-content :deep(td) {
  padding: 10px 14px;
  border: 1px solid #e2e8f0;
  text-align: left;
  color: #1e293b !important;
}
.report-content :deep(th) {
  background: #f8fafc;
  font-weight: 600;
  color: #0f172a !important;
}
.report-content :deep(code) {
  background: #f1f5f9;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 13px;
  color: #334155 !important;
}
.report-content :deep(pre) {
  background: #f1f5f9;
  padding: 14px;
  border-radius: 8px;
  overflow-x: auto;
  border: 1px solid #e2e8f0;
  font-size: 13px;
  line-height: 1.6;
  color: #334155 !important;
}
.report-content :deep(a) {
  color: #2563eb !important;
  text-decoration: underline;
}

@keyframes pulse-glow {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* 双栏布局 */
.dual-panel {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 16px;
  align-items: start;
}
.panel-left {
  max-height: calc(100vh - 300px);
  overflow-y: auto;
  padding-right: 4px;
}
.panel-left::-webkit-scrollbar { width: 4px; }
.panel-left::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
.panel-right {
  min-width: 0;
}

@media (max-width: 768px) {
  .stats-row { grid-template-columns: repeat(2, 1fr); }
  .detail-header { flex-direction: column; gap: 12px; align-items: flex-start; }
  .dual-panel { grid-template-columns: 1fr; }
  .panel-left { max-height: none; }
}

/* 日志行分类 — 固定浅色（深色背景终端） */
.log-line {
  padding: 2px 0;
  font-family: var(--font-mono);
  font-size: 0.82rem;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  color: #e2e8f0;
}
.log-system { color: #38bdf8; }
.log-stderr { color: #fb7185; }
.log-stdout { color: #e2e8f0; }
.log-tag {
  display: inline-block;
  padding: 0 5px;
  border-radius: 3px;
  font-size: 0.7rem;
  font-weight: 700;
  margin-right: 6px;
  vertical-align: middle;
}
.log-tag.system { background: rgba(56, 189, 248, 0.15); color: #38bdf8; }
.log-tag.stderr { background: rgba(251, 113, 133, 0.15); color: #fb7185; }
</style>
