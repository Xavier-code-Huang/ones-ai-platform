<template>
  <div class="page-container" id="task-create-page">
    <!-- 页面头部 -->
    <div class="page-header fade-in-up">
      <div class="header-row">
        <div>
          <h1>📋 创建新任务</h1>
          <p class="header-sub">配置执行环境 → 填写工单 → 提交到 AI 处理管线</p>
        </div>
        <el-tag v-if="validCount > 0" type="primary" effect="dark" size="large" round>
          {{ validCount }} 个工单就绪
        </el-tag>
      </div>
    </div>

    <!-- 步骤区域 -->
    <div class="task-form-layout fade-in-up">

      <!-- ========== 区块 1: 执行环境 ========== -->
      <div class="form-section">
        <div class="section-header">
          <span class="section-icon">🖥️</span>
          <div>
            <h2 class="section-title">执行环境</h2>
            <p class="section-desc">选择目标服务器、SSH 凭证和 Agent 目录</p>
          </div>
        </div>

        <div class="form-grid-3">
          <!-- 服务器 -->
          <div class="form-field">
            <label class="field-label">目标服务器 <span class="required">*</span></label>
            <el-select v-model="form.server_id" placeholder="选择服务器" @change="loadCredentials" id="select-server" class="w-full">
              <el-option v-for="s in servers" :key="s.id" :value="s.id" :disabled="!s.has_my_credential">
                <div class="server-option">
                  <span class="server-status" :class="{ online: s.status === 'online' }"></span>
                  <span>{{ s.name }}</span>
                  <span class="server-host">{{ s.host }}</span>
                </div>
              </el-option>
            </el-select>
          </div>

          <!-- SSH 凭证 -->
          <div class="form-field">
            <label class="field-label">SSH 凭证 <span class="required">*</span></label>
            <el-select v-model="form.credential_id" placeholder="选择凭证" @change="loadAgentDir" id="select-credential" class="w-full"
                       :disabled="!form.server_id">
              <el-option v-for="c in credentials" :key="c.id" :value="c.id"
                         :label="c.ssh_username + (c.alias ? ' — '+c.alias : '')" />
            </el-select>
          </div>

          <!-- 任务模式 -->
          <div class="form-field">
            <label class="field-label">任务模式</label>
            <el-segmented v-model="form.task_mode" :options="modeOptions" id="task-mode-select" />
            <p class="field-hint">{{ modeHints[form.task_mode] }}</p>
          </div>
        </div>

        <!-- Agent 目录 -->
        <div class="form-field" style="margin-top:16px;">
          <label class="field-label">Agent-Teams 目录 <span class="required">*</span></label>
          <div class="agent-dir-wrap">
            <el-input v-model="form.agent_dir" placeholder="如 /home/disk3/user/Lango-Agent-Teams"
                      :class="{'input-error': submitted && !form.agent_dir}" />
            <el-tooltip v-if="agentDirMemory" content="重置为上次记忆的目录" placement="top">
              <button type="button" class="agent-dir-reset"
                      @click="form.agent_dir = agentDirMemory"
                      aria-label="重置">
                <el-icon><RefreshRight /></el-icon>
                <span>重置</span>
              </button>
            </el-tooltip>
          </div>
          <div v-if="agentDirError" class="path-error">{{ agentDirError }}</div>
          <div v-if="agentDirLoaded" class="field-hint" style="color:var(--success);">
            ✅ 已自动读取上次目录
          </div>
        </div>
      </div>

      <!-- ========== 区块 1.5: AI 引擎 ========== -->
      <div class="form-section" v-if="multiEngineEnabled">
        <div class="section-header">
          <span class="section-icon">🤖</span>
          <div>
            <h2 class="section-title">AI 引擎</h2>
            <p class="section-desc">选择 AI 引擎和模型，GLM 为默认引擎</p>
          </div>
        </div>

        <div class="form-grid-3">
          <!-- Provider 选择 -->
          <div class="form-field">
            <label class="field-label">引擎 <span class="required">*</span></label>
            <el-select v-model="form.engine_type" placeholder="选择引擎" @change="onEngineChange" class="w-full">
              <el-option v-for="e in engineOptions" :key="e.value" :value="e.value" :label="e.label" />
            </el-select>
          </div>

          <!-- 模型选择 -->
          <div class="form-field">
            <label class="field-label">模型</label>
            <el-select
              v-if="!modelManualMode"
              v-model="form.model_name"
              placeholder="选择模型"
              :loading="modelsLoading"
              class="w-full"
            >
              <el-option v-for="m in currentModels" :key="m.model_id" :value="m.model_id" :label="m.display_name" />
            </el-select>
            <el-input
              v-else
              v-model="form.model_name"
              placeholder="手动输入模型名称（如 claude-sonnet-4-20250514）"
              class="w-full"
            />
            <div v-if="modelLoadError" class="field-hint" style="color:var(--danger);">
              ⚠️ 模型列表加载失败，已切换为手动输入
            </div>
          </div>

          <!-- Key 选择器（非 GLM 时展示） -->
          <div class="form-field" v-if="form.engine_type !== 'glm'">
            <label class="field-label">API Key <span class="required">*</span></label>
            <el-select
              v-if="userKeys.length > 0"
              v-model="form.api_key_id"
              placeholder="选择 API Key"
              :loading="keysLoading"
              class="w-full"
            >
              <el-option v-for="k in userKeys" :key="k.id" :value="k.id"
                         :label="(k.label ? k.label + ' — ' : '') + k.key_preview" />
            </el-select>
            <div v-else-if="!keysLoading" class="no-key-hint">
              <span>未配置 {{ engineLabel }} 的 API Key</span>
              <router-link to="/settings/api-keys" class="key-link">前往设置 →</router-link>
            </div>
          </div>
        </div>
      </div>

      <!-- ========== 区块 2: 工单列表 ========== -->
      <div class="form-section">
        <div class="section-header">
          <span class="section-icon">📝</span>
          <div style="flex:1;">
            <h2 class="section-title">工单列表</h2>
            <p class="section-desc">添加待处理的 ONES 工单，支持拖拽调整顺序</p>
          </div>
          <div class="ticket-actions">
            <el-button size="small" @click="addRow" id="add-row-btn">
              <el-icon><Plus /></el-icon> 添加工单
            </el-button>
          </div>
        </div>

        <!-- 工单卡片列表（支持拖拽） -->
        <div class="ticket-list" ref="ticketListRef">
          <div
            v-for="(t, i) in form.tickets" :key="t._key"
            class="ticket-card"
            :class="{ 'is-dragging': dragIdx === i }"
            draggable="true"
            @dragstart="onDragStart(i, $event)"
            @dragover.prevent="onDragOver(i, $event)"
            @dragend="onDragEnd"
          >
            <!-- 拖拽手柄 + 序号 -->
            <div class="ticket-handle" title="拖拽排序">
              <span class="drag-icon">⠿</span>
              <span class="ticket-seq">#{{ i + 1 }}</span>
            </div>

            <!-- 工单主区域 -->
            <div class="ticket-body">
              <!-- 第一行：工单号 + 代码路径 -->
              <div class="ticket-row-main">
                <div class="ticket-id-field">
                  <label class="mini-label">工单号 <span class="required">*</span></label>
                  <el-input v-model="t.ticket_id" placeholder="ONES-123456" size="default"
                            @blur="onTicketBlur(t, i)"
                            :class="{'input-error': submitted && !t.ticket_id}">
                    <template #prefix>
                      <span class="ticket-prefix">🎫</span>
                    </template>
                  </el-input>
                  <div v-if="t._previewTitle" class="preview-title">📌 {{ t._previewTitle }}</div>
                </div>
                <div class="ticket-code-field">
                  <label class="mini-label">代码路径 <span class="required">*</span></label>
                  <CodePathSelect
                    v-model="t.code_directory"
                    :server-id="form.server_id || 0"
                  />
                </div>
              </div>

              <!-- 第二行：提示词 -->
              <div class="ticket-note-row">
                <div class="note-header">
                  <label class="mini-label">提示词 <span class="optional">(选填)</span></label>
                  <el-button
                    v-if="t.ticket_id && form.server_id && form.credential_id"
                    size="small" text type="primary"
                    :loading="t._previewLoading"
                    @click="triggerPreview(t, i)"
                    class="ai-preview-btn"
                  >
                    🤖 AI 预分析
                  </el-button>
                </div>
                <div v-if="t._previewLoading" class="preview-loading">
                  <span class="loading-dot"></span> AI 正在分析工单，生成提示词中...
                </div>
                <el-input v-model="t.note" type="textarea" :rows="2"
                          :placeholder="t._previewLoading ? 'AI 正在生成提示词...' : '描述问题详情、修复思路、特殊要求等'"
                          resize="vertical" />
              </div>

              <!-- 第三行：额外挂载（可折叠） -->
              <div class="extra-mounts-section">
                <div class="extra-mounts-toggle" @click="t._showMounts = !t._showMounts">
                  <el-icon style="font-size:12px;transition:transform 0.2s;" :style="{ transform: t._showMounts ? 'rotate(90deg)' : '' }">
                    <ArrowRight />
                  </el-icon>
                  <span>额外挂载路径</span>
                  <span v-if="t.extra_mounts?.filter(Boolean).length" class="mount-count">{{ t.extra_mounts.filter(Boolean).length }}</span>
                </div>
                <div v-if="t._showMounts" class="extra-mounts-list">
                  <div v-for="(m, mi) in t.extra_mounts" :key="mi" class="mount-item">
                    <el-input v-model="t.extra_mounts[mi]" placeholder="如 /home/disk4/user/project" size="small"
                              @blur="validateMountPath(i, mi)" :class="{'input-error': m && mountErrors[i+'_'+mi]}" />
                    <span v-if="mountErrors[i+'_'+mi]" class="path-error-inline">{{ mountErrors[i+'_'+mi] }}</span>
                    <el-button size="small" type="danger" text circle @click="t.extra_mounts.splice(mi, 1)">
                      <el-icon><Close /></el-icon>
                    </el-button>
                  </div>
                  <el-button size="small" text @click="addMount(t)" style="margin-top:4px;">
                    <el-icon><Plus /></el-icon> 添加路径
                  </el-button>
                </div>
              </div>
            </div>

            <!-- 删除按钮 -->
            <div class="ticket-remove">
              <el-button size="small" type="danger" text circle @click="removeRow(i)" :disabled="form.tickets.length <= 1">
                <el-icon><Close /></el-icon>
              </el-button>
            </div>
          </div>
        </div>

        <!-- 拖拽提示 -->
        <div v-if="form.tickets.length > 1" class="drag-hint">
          💡 拖拽 <b>⠿</b> 手柄可调整工单执行顺序
        </div>
      </div>

      <!-- ========== 提交区域 ========== -->
      <div class="submit-section">
        <el-button @click="$router.push('/')" size="large">取消</el-button>
        <el-button type="primary" size="large" :loading="submitting" @click="showPreview"
                   :disabled="form.tickets.length===0" id="preview-btn">
          🚀 预览并提交 ({{ validCount }} 个工单)
        </el-button>
      </div>
    </div>

    <!-- 预览确认弹窗 -->
    <el-dialog v-model="previewDialog" title="🚀 任务预览确认" width="780px" id="preview-dialog"
               :close-on-click-modal="false" top="8vh">
      <div class="preview-content">
        <div class="preview-env">
          <div class="preview-env-item">
            <span class="preview-label">服务器</span>
            <span>{{ selectedServer?.name }} ({{ selectedServer?.host }})</span>
          </div>
          <div class="preview-env-item">
            <span class="preview-label">SSH 凭证</span>
            <span>{{ selectedCred?.ssh_username }}</span>
          </div>
          <div class="preview-env-item">
            <span class="preview-label">Agent 目录</span>
            <span class="mono">{{ form.agent_dir }}</span>
          </div>
          <div class="preview-env-item">
            <span class="preview-label">任务模式</span>
            <el-tag size="small" type="info">{{ form.task_mode }}</el-tag>
          </div>
          <div class="preview-env-item">
            <span class="preview-label">AI 引擎</span>
            <el-tag size="small" type="success">{{ engineLabel }}</el-tag>
          </div>
          <div class="preview-env-item">
            <span class="preview-label">模型</span>
            <span class="mono">{{ form.model_name || '默认' }}</span>
          </div>
        </div>
        <el-table :data="previewTickets" border size="small" style="width:100%;margin-top:16px;">
          <el-table-column type="index" label="#" width="50" />
          <el-table-column prop="ticket_id" label="工单号" width="140" />
          <el-table-column prop="code_directory" label="代码路径" />
          <el-table-column prop="note" label="提示词" show-overflow-tooltip />
          <el-table-column label="额外挂载" width="100">
            <template #default="scope">
              <span v-if="scope.row.extra_mounts?.length">{{ scope.row.extra_mounts.length }} 个</span>
              <span v-else style="color:var(--text-muted);">—</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <template #footer>
        <el-button @click="previewDialog=false">返回修改</el-button>
        <el-button type="primary" :loading="submitting" @click="submitTask" id="submit-task-btn">确认提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { RefreshRight, Plus, Close, ArrowRight } from '@element-plus/icons-vue'
import api from '../api'
import { ElMessage } from 'element-plus'
import CodePathSelect from '../components/CodePathSelect.vue'

const route = useRoute()
const router = useRouter()
const servers = ref([])
const credentials = ref([])
const previewDialog = ref(false)
const submitting = ref(false)
const submitted = ref(false)
const mountErrors = reactive({})
const agentDirMemory = ref('')
const agentDirLoaded = ref(false)
const ticketListRef = ref(null)

// 拖拽状态
const dragIdx = ref(-1)

// ---- 功能开关 ----
const multiEngineEnabled = ref(false)

// ---- 引擎/模型/Key 状态 ----
const engineOptions = [
  { value: 'glm', label: 'GLM (智谱)' },
  { value: 'anthropic', label: 'Anthropic Claude' },
  { value: 'openai', label: 'OpenAI Codex' },
]
const modelsLoading = ref(false)
const modelLoadError = ref(false)
const modelManualMode = ref(false)
const currentModels = ref([])
const keysLoading = ref(false)
const userKeys = ref([])

// 组件级缓存：同一页面会话内切回同一 Provider 不重复请求
const modelsCache = reactive({})  // { provider: [models] }
const keysCache = reactive({})    // { provider: [keys] }

const engineLabel = computed(() => {
  const opt = engineOptions.find(e => e.value === form.engine_type)
  return opt ? opt.label : form.engine_type
})

let _keyCounter = 1
function genKey() { return _keyCounter++ }

// ---- 路径校验 ----
const BLOCKED_PATHS = ['/', '/etc', '/sys', '/proc', '/dev', '/boot', '/root',
  '/var', '/usr', '/sbin', '/bin', '/lib', '/lib64', '/run', '/tmp']

function validatePath(path) {
  if (!path) return null
  const p = path.replace(/\/+$/, '')
  if (!p.startsWith('/')) return '必须为绝对路径'
  if (BLOCKED_PATHS.includes(p)) return '不允许挂载系统敏感路径: ' + p
  if (p.split('/').filter(Boolean).length < 2) return '路径层级过浅，至少需要 2 级目录'
  return null
}

const agentDirError = computed(() => validatePath(form.agent_dir))

function validateMountPath(ticketIdx, mi) {
  const key = ticketIdx + '_' + mi
  const ticket = form.tickets[ticketIdx]
  const err = validatePath(ticket.extra_mounts[mi])
  if (err) mountErrors[key] = err
  else delete mountErrors[key]
}

const modeOptions = [
  { label: '🔧 修复', value: 'fix' },
  { label: '🔍 分析', value: 'analysis' },
  { label: '🤖 自动', value: 'auto' },
]

const modeHints = {
  fix: '必须修改代码，禁止只输出分析报告',
  analysis: '只分析不改代码，输出分析报告和方案',
  auto: 'AI 自行判断，能修的直接修，不确定的给方案'
}

const form = reactive({
  server_id: null,
  credential_id: null,
  agent_dir: '',
  task_mode: 'fix',
  engine_type: 'glm',
  model_name: '',
  api_key_id: null,
  tickets: [
    { ticket_id: '', code_directory: '', note: '', extra_mounts: [], _showMounts: false, _key: genKey() }
  ]
})

const selectedServer = computed(() => servers.value.find(s => s.id === form.server_id))
const selectedCred = computed(() => credentials.value.find(c => c.id === form.credential_id))
const validTickets = computed(() => form.tickets.filter(t => t.ticket_id && t.code_directory))
const validCount = computed(() => validTickets.value.length)

const previewTickets = computed(() =>
  validTickets.value.map(t => ({
    ticket_id: t.ticket_id,
    code_directory: t.code_directory,
    note: t.note,
    extra_mounts: (t.extra_mounts || []).filter(Boolean),
  }))
)

onMounted(async () => {
  // 加载功能开关
  try {
    const flags = await api.getFeatureFlags()
    multiEngineEnabled.value = flags.multi_engine_enabled === true
  } catch (_) { /* 静默 */ }

  servers.value = (await api.getServers()).filter(s => s.has_my_credential)
  if (route.params.serverId) {
    form.server_id = parseInt(route.params.serverId)
    await loadCredentials()
  }
  // 默认加载 GLM 模型列表
  await loadModels('glm')
})

async function loadCredentials() {
  if (!form.server_id) return
  agentDirLoaded.value = false
  agentDirMemory.value = ''
  credentials.value = await api.getCredentials(form.server_id)
  if (credentials.value.length === 1) {
    form.credential_id = credentials.value[0].id
    await loadAgentDir()
  }
}

async function loadAgentDir() {
  if (!form.server_id || !form.credential_id) return
  try {
    const res = await api.getAgentDir(form.server_id, form.credential_id)
    if (res.agent_dir) {
      form.agent_dir = res.agent_dir
      agentDirMemory.value = res.agent_dir
      agentDirLoaded.value = true
    }
  } catch (e) { /* 静默 */ }
}

// ---- 引擎/模型/Key 逻辑 ----
async function onEngineChange() {
  form.model_name = ''
  form.api_key_id = null
  modelLoadError.value = false
  modelManualMode.value = false
  await loadModels(form.engine_type)
  if (form.engine_type !== 'glm') {
    await loadUserKeys(form.engine_type)
  } else {
    userKeys.value = []
  }
}

async function loadModels(provider) {
  // 组件级缓存命中
  if (modelsCache[provider]) {
    currentModels.value = modelsCache[provider]
    autoSelectDefaultModel()
    return
  }
  modelsLoading.value = true
  modelLoadError.value = false
  modelManualMode.value = false
  try {
    const res = await api.getProviderModelsByProvider(provider)
    const models = res.models || res || []
    modelsCache[provider] = models
    currentModels.value = models
    autoSelectDefaultModel()
  } catch (e) {
    modelLoadError.value = true
    modelManualMode.value = true
    currentModels.value = []
  } finally {
    modelsLoading.value = false
  }
}

function autoSelectDefaultModel() {
  if (currentModels.value.length === 0) return
  const def = currentModels.value.find(m => m.is_default)
  form.model_name = def ? def.model_id : currentModels.value[0].model_id
}

async function loadUserKeys(provider) {
  // 组件级缓存命中
  if (keysCache[provider]) {
    userKeys.value = keysCache[provider]
    autoSelectDefaultKey()
    return
  }
  keysLoading.value = true
  try {
    const keys = await api.listUserKeys(provider)
    const list = keys.keys || keys || []
    keysCache[provider] = list
    userKeys.value = list
    autoSelectDefaultKey()
  } catch (e) {
    userKeys.value = []
  } finally {
    keysLoading.value = false
  }
}

function autoSelectDefaultKey() {
  if (userKeys.value.length === 0) { form.api_key_id = null; return }
  const def = userKeys.value.find(k => k.is_default)
  form.api_key_id = def ? def.id : userKeys.value[0].id
}

// ---- 工单操作 ----
function addRow() {
  form.tickets.push({ ticket_id: '', code_directory: '', note: '', extra_mounts: [], _showMounts: false, _key: genKey() })
}

function removeRow(idx) {
  if (form.tickets.length <= 1) return
  form.tickets.splice(idx, 1)
}

function addMount(ticket) {
  if (!ticket.extra_mounts) ticket.extra_mounts = []
  ticket.extra_mounts.push('')
}

// ---- 拖拽排序 ----
function onDragStart(idx, e) {
  dragIdx.value = idx
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', idx)
}

function onDragOver(idx, e) {
  if (dragIdx.value === -1 || dragIdx.value === idx) return
  const dragged = form.tickets.splice(dragIdx.value, 1)[0]
  form.tickets.splice(idx, 0, dragged)
  dragIdx.value = idx
}

function onDragEnd() {
  dragIdx.value = -1
}

// ---- 工单号处理 ----
function cleanTicketId(ticket) {
  if (!ticket.ticket_id) return
  const raw = ticket.ticket_id.trim()
  if (/[,\s，、;；]/.test(raw)) {
    const ids = raw.split(/[,\s，、;；]+/).filter(Boolean)
    ticket.ticket_id = ids[0]
    if (ids.length > 1) {
      // 自动拆分多个工单号
      for (let k = 1; k < ids.length; k++) {
        form.tickets.push({ ticket_id: ids[k], code_directory: ticket.code_directory, note: '', extra_mounts: [], _showMounts: false, _key: genKey() })
      }
      ElMessage.success(`检测到多个工单号，已自动拆分为 ${ids.length} 行`)
    }
  }
}

// AI 预分析：blur 自动触发
async function onTicketBlur(ticket, idx) {
  cleanTicketId(ticket)
}

// AI 预分析：点击按钮手动触发
async function triggerPreview(ticket, idx) {
  if (!ticket.ticket_id) return
  if (!form.server_id || !form.credential_id) return ElMessage.warning('请先选择服务器和凭证')
  if (ticket._lastPreviewId === ticket.ticket_id && ticket._previewTitle) return

  ticket._previewLoading = true
  ticket._lastPreviewId = ticket.ticket_id

  try {
    const results = await api.previewTickets({
      tickets: [{ ticket_id: ticket.ticket_id, code_directory: ticket.code_directory || '' }],
      server_id: form.server_id,
      credential_id: form.credential_id,
    })

    if (results && results.length > 0) {
      const r = results[0]
      ticket._previewTitle = r.title || ''
      if (r.suggested_prompt) {
        ticket.note = r.suggested_prompt
        ticket._aiGenerated = true
        ticket._suggestedAgent = r.suggested_agent || ''
        ElMessage.success(`工单 ${ticket.ticket_id} 已生成 AI 提示词`)
      } else if (r.error) {
        ElMessage.warning(`预分析: ${r.error}`)
      }
    }
  } catch (e) {
    ElMessage.warning('AI 预分析失败: ' + (e.message || '未知错误'))
  } finally {
    ticket._previewLoading = false
  }
}

// ---- 提交 ----
function showPreview() {
  submitted.value = true
  if (!form.server_id || !form.credential_id) return ElMessage.warning('请选择服务器和账号')
  if (!form.agent_dir) return ElMessage.warning('请填写 Agent Teams 目录')

  const adErr = validatePath(form.agent_dir)
  if (adErr) return ElMessage.warning('Agent 目录: ' + adErr)

  // 非 GLM 引擎需要选择 API Key
  if (form.engine_type !== 'glm' && !form.api_key_id) {
    return ElMessage.warning(`请先配置 ${engineLabel.value} 的 API Key`)
  }

  for (const t of form.tickets) {
    if (t.ticket_id && /[,\s，、;；]/.test(t.ticket_id.trim())) {
      return ElMessage.warning('每行只能填写一个工单号')
    }
  }

  const invalid = form.tickets.filter(t => t.ticket_id && !t.code_directory)
  if (invalid.length > 0) return ElMessage.warning(`${invalid.length} 个工单缺少代码位置`)
  if (validCount.value === 0) return ElMessage.warning('请至少填写一个完整的工单')

  const hasPathErr = Object.keys(mountErrors).length > 0
  if (hasPathErr) return ElMessage.warning('存在无效的额外挂载路径，请修正')

  previewDialog.value = true
}

async function submitTask() {
  submitting.value = true
  try {
    const payload = {
      server_id: form.server_id,
      credential_id: form.credential_id,
      agent_dir: form.agent_dir,
      task_mode: form.task_mode,
      engine_type: form.engine_type,
      model_name: form.model_name,
      ...(form.engine_type !== 'glm' && form.api_key_id ? { api_key_id: form.api_key_id } : {}),
      tickets: previewTickets.value,
    }
    const task = await api.createTask(payload)
    try {
      await api.saveAgentDir(form.server_id, {
        credential_id: form.credential_id,
        agent_dir: form.agent_dir,
      })
    } catch (e) { /* 静默 */ }
    ElMessage.success('任务已提交！')
    previewDialog.value = false
    router.push(`/tasks/${task.id}`)
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '提交失败')
  } finally { submitting.value = false }
}
</script>

<style scoped>
/* ===== 布局 ===== */
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-sub {
  color: var(--text-muted);
  font-size: 0.85rem;
  margin-top: 4px;
}

.task-form-layout {
  max-width: 1000px;
  margin-top: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ===== 区块 ===== */
.form-section {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  box-shadow: var(--shadow);
}

.section-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 20px;
}

.section-icon {
  font-size: 1.6rem;
  line-height: 1;
  flex-shrink: 0;
  margin-top: 2px;
}

.section-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.section-desc {
  font-size: 0.78rem;
  color: var(--text-muted);
  margin: 2px 0 0;
}

/* ===== 表单网格 ===== */
.form-grid-3 {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 16px;
}

@media (max-width: 768px) {
  .form-grid-3 { grid-template-columns: 1fr; }
}

.form-field { display: flex; flex-direction: column; }
.w-full { width: 100%; }

.field-label {
  display: block;
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin-bottom: 6px;
  font-weight: 500;
}

.field-hint {
  font-size: 0.72rem;
  color: var(--text-muted);
  margin-top: 4px;
}

.required { color: var(--danger); font-weight: 600; }
.optional { color: var(--text-muted); font-weight: 400; font-size: 0.75rem; }
.mono { font-family: var(--font-mono, monospace); font-size: 0.85rem; }

/* 服务器下拉选项 */
.server-option {
  display: flex;
  align-items: center;
  gap: 8px;
}
.server-status {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--text-muted);
  flex-shrink: 0;
}
.server-status.online { background: var(--success); }
.server-host {
  color: var(--text-muted);
  font-size: 0.78rem;
  margin-left: auto;
  font-family: var(--font-mono, monospace);
}

/* ===== 工单卡片 ===== */
.ticket-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.ticket-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ticket-card {
  display: flex;
  gap: 12px;
  background: var(--bg-body);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm, 8px);
  padding: 16px;
  transition: all 0.2s var(--ease, ease);
  cursor: default;
}

.ticket-card:hover {
  border-color: var(--accent-light);
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}

.ticket-card.is-dragging {
  opacity: 0.5;
  border-color: var(--accent);
  box-shadow: 0 4px 16px rgba(30, 64, 175, 0.12);
}

.ticket-handle {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 4px 4px 0;
  cursor: grab;
  flex-shrink: 0;
}

.ticket-handle:active { cursor: grabbing; }

.drag-icon {
  font-size: 1.2rem;
  color: var(--text-muted);
  line-height: 1;
  letter-spacing: 1px;
}

.ticket-seq {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-muted);
}

.ticket-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 12px; }

.ticket-row-main {
  display: flex;
  gap: 12px;
}

.ticket-id-field { width: 200px; flex-shrink: 0; }
.ticket-code-field { flex: 1; min-width: 0; }

.mini-label {
  display: block;
  font-size: 0.72rem;
  color: var(--text-muted);
  margin-bottom: 4px;
  font-weight: 500;
}

.ticket-prefix { font-size: 0.85rem; }

.ticket-remove {
  display: flex;
  align-items: flex-start;
  padding-top: 20px;
  flex-shrink: 0;
}

/* AI 预分析 */
.note-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.ai-preview-btn {
  font-size: 0.78rem !important;
}

.preview-title {
  font-size: 0.72rem;
  color: var(--accent);
  margin-top: 4px;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-loading {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.76rem;
  color: var(--accent-light);
  margin-bottom: 6px;
  animation: breathe 2s ease-in-out infinite;
}

@keyframes breathe {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.loading-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--accent-light);
  animation: breathe 1s ease-in-out infinite;
}

/* 额外挂载 */
.extra-mounts-section { padding-top: 4px; }
.extra-mounts-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.72rem;
  color: var(--text-muted);
  cursor: pointer;
  padding: 2px 0;
  user-select: none;
}
.extra-mounts-toggle:hover { color: var(--accent); }
.mount-count {
  background: var(--accent);
  color: #fff;
  border-radius: 8px;
  padding: 0 6px;
  font-size: 0.65rem;
  margin-left: 4px;
}
.extra-mounts-list { padding: 6px 0 2px; }
.mount-item { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.mount-item .el-input { max-width: 400px; }
.path-error { color: var(--danger); font-size: 0.72rem; margin-top: 4px; }
.path-error-inline { color: var(--danger); font-size: 0.68rem; white-space: nowrap; }
.input-error :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px var(--danger) inset !important; }

/* 拖拽提示 */
.drag-hint {
  text-align: center;
  font-size: 0.72rem;
  color: var(--text-muted);
  margin-top: 8px;
}

/* ===== 提交区域 ===== */
.submit-section {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 20px 24px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}

/* ===== 预览弹窗 ===== */
.preview-content {}
.preview-env {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 24px;
  padding: 12px 16px;
  background: var(--bg-body);
  border-radius: var(--radius-sm, 8px);
  border: 1px solid var(--border);
}
.preview-env-item { display: flex; align-items: center; gap: 8px; font-size: 0.85rem; }
.preview-label {
  font-size: 0.76rem;
  color: var(--text-muted);
  min-width: 60px;
  flex-shrink: 0;
}

/* ===== 响应式 ===== */
@media (max-width: 640px) {
  .ticket-row-main { flex-direction: column; }
  .ticket-id-field { width: 100%; }
  .ticket-handle { display: none; }
  .preview-env { grid-template-columns: 1fr; }
}

/* ===== 引擎/Key 提示 ===== */
.no-key-hint {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.8rem;
  color: var(--text-muted);
  padding: 8px 12px;
  background: var(--bg-body);
  border: 1px dashed var(--border);
  border-radius: var(--radius-sm, 8px);
}
.key-link {
  color: var(--accent);
  font-size: 0.78rem;
  text-decoration: none;
}
.key-link:hover {
  text-decoration: underline;
}

/* ===== Agent-Teams 目录 + 重置按钮 ===== */
.agent-dir-wrap {
  display: flex;
  align-items: stretch;
  gap: 8px;
}
.agent-dir-wrap :deep(.el-input) {
  flex: 1;
}
.agent-dir-reset {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0 14px;
  height: 32px;
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--accent);
  background: var(--accent-bg);
  border: 1px solid var(--accent-border);
  border-radius: var(--radius-sm, 8px);
  cursor: pointer;
  transition: all 0.18s ease;
  outline: none;
  box-shadow: var(--shadow-xs, 0 1px 2px rgba(0,0,0,0.04));
}
.agent-dir-reset:hover {
  color: #fff;
  background: var(--accent);
  border-color: var(--accent);
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm, 0 2px 6px rgba(51,65,85,0.18));
}
.agent-dir-reset:active {
  transform: translateY(0);
  box-shadow: none;
}
.agent-dir-reset:focus-visible {
  box-shadow: 0 0 0 3px rgba(51, 65, 85, 0.18);
}
.agent-dir-reset .el-icon {
  font-size: 14px;
  transition: transform 0.3s ease;
}
.agent-dir-reset:hover .el-icon {
  transform: rotate(-90deg);
}
</style>
