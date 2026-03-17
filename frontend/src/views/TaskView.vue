<template>
  <div class="page-container" id="task-create-page">
    <div class="page-header fade-in-up">
      <h1>创建工单任务</h1>
      <p>选择服务器和账号，填写工单信息后提交</p>
    </div>

    <div class="glass-card fade-in-up" style="max-width:960px;margin-top:24px;">
      <!-- 服务器和凭证选择 -->
      <div style="display:flex;gap:16px;margin-bottom:28px;">
        <div style="flex:1;">
          <label class="field-label">目标服务器</label>
          <el-select v-model="form.server_id" placeholder="选择服务器" style="width:100%;" @change="loadCredentials" id="select-server">
            <el-option v-for="s in servers" :key="s.id" :label="s.name + ' (' + s.host + ')'" :value="s.id" :disabled="!s.has_my_credential" />
          </el-select>
        </div>
        <div style="flex:1;">
          <label class="field-label">SSH 账号</label>
          <el-select v-model="form.credential_id" placeholder="选择账号" style="width:100%;" id="select-credential">
            <el-option v-for="c in credentials" :key="c.id" :label="c.ssh_username + (c.alias ? ' — '+c.alias : '')" :value="c.id" />
          </el-select>
        </div>
      </div>

      <!-- 工单列表表头 -->
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <h3 style="font-size:1rem;font-weight:600;">工单信息 <span style="color:var(--text-muted);font-weight:400;font-size:0.85rem;">({{ form.tickets.length }} 个)</span></h3>
        <el-button size="small" @click="addRow" id="add-row-btn">
          <el-icon><Plus /></el-icon> 添加一行
        </el-button>
      </div>

      <!-- 表头 -->
      <div class="ticket-table-header">
        <div class="col-seq">#</div>
        <div class="col-ticket">工单号 <span class="required">*</span></div>
        <div class="col-code">代码位置 <span class="required">*</span></div>
        <div class="col-note">补充说明</div>
        <div class="col-action"></div>
      </div>

      <!-- 数据行 -->
      <div v-for="(t, i) in form.tickets" :key="i" class="ticket-table-row" :class="{'row-example': i === 0 && isExample}">
        <div class="col-seq">{{ i + 1 }}</div>
        <div class="col-ticket">
          <el-input v-model="t.ticket_id" placeholder="如 668380" size="default"
                    @focus="clearExample(i)" :class="{'input-error': submitted && !t.ticket_id}" />
        </div>
        <div class="col-code">
          <el-input v-model="t.code_directory" placeholder="如 /home/user/aosp" size="default"
                    @focus="clearExample(i)" :class="{'input-error': submitted && !t.code_directory}" />
        </div>
        <div class="col-note">
          <el-input v-model="t.note" placeholder="选填" size="default" @focus="clearExample(i)" />
        </div>
        <div class="col-action">
          <el-button size="small" type="danger" text circle @click="removeRow(i)" :disabled="form.tickets.length <= 1">
            <el-icon><Close /></el-icon>
          </el-button>
        </div>
      </div>

      <!-- 快捷批量添加 -->
      <div style="margin-top:16px;padding:16px;background:var(--bg-secondary);border-radius:var(--radius-sm);border:1px solid var(--border);">
        <div style="display:flex;gap:12px;align-items:flex-start;">
          <el-input v-model="batchInput" type="textarea" :rows="2" placeholder="批量添加：每行一个工单号，或用逗号分隔&#10;如: 668380, 668381, 668382" style="flex:1;" />
          <el-button @click="batchAdd" style="margin-top:2px;">批量解析</el-button>
        </div>
      </div>

      <!-- 提交 -->
      <div style="margin-top:28px;display:flex;justify-content:flex-end;gap:12px;padding-top:20px;border-top:1px solid var(--border);">
        <el-button @click="$router.push('/')">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="showPreview" :disabled="form.tickets.length===0" id="preview-btn">
          预览并提交 ({{ validCount }} 个工单)
        </el-button>
      </div>
    </div>

    <!-- 预览确认弹窗 -->
    <el-dialog v-model="previewDialog" title="任务预览确认" width="680px" id="preview-dialog">
      <div>
        <p style="margin-bottom:4px;"><strong>目标服务器：</strong>{{ selectedServer?.name }} ({{ selectedServer?.host }})</p>
        <p style="margin-bottom:12px;"><strong>SSH 账号：</strong>{{ selectedCred?.ssh_username }}</p>
        <el-table :data="validTickets" border size="small" style="width:100%;">
          <el-table-column type="index" label="#" width="50" />
          <el-table-column prop="ticket_id" label="工单号" width="140" />
          <el-table-column prop="code_directory" label="代码位置" />
          <el-table-column prop="note" label="补充说明" />
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
import api from '../api'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const servers = ref([])
const credentials = ref([])
const previewDialog = ref(false)
const submitting = ref(false)
const submitted = ref(false)
const batchInput = ref('')
const isExample = ref(true)

const form = reactive({
  server_id: null,
  credential_id: null,
  tickets: [
    { ticket_id: '668380', code_directory: '/home/user/aosp', note: '示例，点击即清除' }
  ]
})

const selectedServer = computed(() => servers.value.find(s => s.id === form.server_id))
const selectedCred = computed(() => credentials.value.find(c => c.id === form.credential_id))
const validTickets = computed(() => form.tickets.filter(t => t.ticket_id && t.code_directory))
const validCount = computed(() => validTickets.value.length)

onMounted(async () => {
  servers.value = (await api.getServers()).filter(s => s.has_my_credential)
  if (route.params.serverId) {
    form.server_id = parseInt(route.params.serverId)
    await loadCredentials()
  }
})

async function loadCredentials() {
  if (!form.server_id) return
  credentials.value = await api.getCredentials(form.server_id)
  if (credentials.value.length === 1) form.credential_id = credentials.value[0].id
}

function clearExample(idx) {
  if (isExample.value && idx === 0) {
    form.tickets[0].ticket_id = ''
    form.tickets[0].code_directory = ''
    form.tickets[0].note = ''
    isExample.value = false
  }
}

function addRow() {
  if (isExample.value) clearExample(0)
  form.tickets.push({ ticket_id: '', code_directory: '', note: '' })
}

function removeRow(idx) {
  if (form.tickets.length <= 1) return
  form.tickets.splice(idx, 1)
}

function normalizeId(id) {
  id = id.trim()
  return /^\d+$/.test(id) ? id : id
}

function batchAdd() {
  const raw = batchInput.value
  if (!raw.trim()) return
  if (isExample.value) clearExample(0)
  const ids = raw.split(/[,\s\n]+/).filter(Boolean).map(normalizeId)
  for (const id of ids) {
    if (!form.tickets.find(t => t.ticket_id === id)) {
      form.tickets.push({ ticket_id: id, code_directory: '', note: '' })
    }
  }
  batchInput.value = ''
  ElMessage.success(`已添加 ${ids.length} 个工单号，请补充代码位置`)
}

function showPreview() {
  submitted.value = true
  if (isExample.value) clearExample(0)
  if (!form.server_id || !form.credential_id) return ElMessage.warning('请选择服务器和账号')

  // 检查必填项
  const invalid = form.tickets.filter(t => t.ticket_id && !t.code_directory)
  if (invalid.length > 0) return ElMessage.warning(`${invalid.length} 个工单缺少代码位置`)
  if (validCount.value === 0) return ElMessage.warning('请至少填写一个完整的工单')

  previewDialog.value = true
}

async function submitTask() {
  submitting.value = true
  try {
    const payload = { ...form, tickets: validTickets.value }
    const task = await api.createTask(payload)
    ElMessage.success('任务已提交！')
    previewDialog.value = false
    router.push(`/tasks/${task.id}`)
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '提交失败')
  } finally { submitting.value = false }
}
</script>

<style scoped>
.field-label {
  display: block;
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin-bottom: 6px;
  font-weight: 500;
}
.required { color: var(--danger); font-weight: 600; }
.ticket-table-header {
  display: flex;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.ticket-table-row {
  display: flex;
  gap: 8px;
  padding: 6px 0;
  align-items: center;
  border-bottom: 1px solid rgba(255,255,255,0.03);
}
.ticket-table-row:hover { background: var(--accent-subtle); border-radius: var(--radius-sm); }
.row-example :deep(.el-input__inner) { color: var(--text-muted) !important; font-style: italic; }
.col-seq { width: 30px; text-align: center; color: var(--text-muted); font-size: 0.85rem; flex-shrink: 0; }
.col-ticket { width: 160px; flex-shrink: 0; }
.col-code { flex: 1; min-width: 200px; }
.col-note { flex: 1; min-width: 160px; }
.col-action { width: 36px; flex-shrink: 0; display: flex; justify-content: center; }
.input-error :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px var(--danger) inset !important; }
</style>
