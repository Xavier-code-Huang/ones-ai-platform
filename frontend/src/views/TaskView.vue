<template>
  <div class="page-container" id="task-create-page">
    <h1 class="fade-in-up" style="font-size:1.6rem;font-weight:700;margin-bottom:24px;">创建工单任务</h1>

    <div class="glass-card fade-in-up" style="max-width:800px;">
      <!-- 服务器和凭证选择 -->
      <div style="display:flex;gap:16px;margin-bottom:24px;">
        <el-select v-model="form.server_id" placeholder="选择服务器" style="flex:1;" @change="loadCredentials" id="select-server">
          <el-option v-for="s in servers" :key="s.id" :label="s.name + ' (' + s.host + ')'" :value="s.id" :disabled="!s.has_my_credential" />
        </el-select>
        <el-select v-model="form.credential_id" placeholder="选择账号" style="flex:1;" id="select-credential">
          <el-option v-for="c in credentials" :key="c.id" :label="c.ssh_username + (c.alias ? ' - '+c.alias : '')" :value="c.id" />
        </el-select>
      </div>

      <!-- 工单输入 -->
      <h3 style="margin-bottom:12px;">工单号</h3>
      <el-input v-model="ticketInput" type="textarea" :rows="3" placeholder="输入工单号，多个用逗号、空格或换行分隔&#10;例如: 668380, 668381" id="ticket-input" />
      <el-button size="small" @click="addTickets" style="margin-top:8px;" id="add-tickets-btn">解析并添加</el-button>

      <!-- 工单列表 -->
      <div v-if="form.tickets.length > 0" style="margin-top:20px;">
        <h3 style="margin-bottom:12px;">工单详情 ({{ form.tickets.length }} 个)</h3>
        <div v-for="(t, i) in form.tickets" :key="i" class="ticket-item" style="padding:12px;border:1px solid var(--border-color);border-radius:var(--radius-sm);margin-bottom:8px;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="font-weight:600;color:var(--accent-blue);">{{ t.ticket_id }}</span>
            <el-button size="small" type="danger" text @click="form.tickets.splice(i,1)">删除</el-button>
          </div>
          <el-input v-model="t.note" placeholder="补充说明（可选）" size="small" style="margin-top:8px;" />
          <el-input v-model="t.code_directory" placeholder="代码目录（可选）" size="small" style="margin-top:4px;" />
          <div style="margin-top:4px;display:flex;gap:8px;">
            <el-input placeholder="编译命令" size="small" disabled style="flex:1;">
              <template #suffix><el-tag size="small" type="info">暂未开放</el-tag></template>
            </el-input>
            <el-switch disabled style="margin-top:4px;" />
          </div>
        </div>
      </div>

      <!-- 提交 -->
      <div style="margin-top:24px;display:flex;justify-content:flex-end;gap:12px;">
        <el-button @click="$router.push('/')">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="showPreview" :disabled="form.tickets.length===0" id="preview-btn">
          预览并提交
        </el-button>
      </div>
    </div>

    <!-- 预览确认弹窗 -->
    <el-dialog v-model="previewDialog" title="任务预览确认" width="600px" id="preview-dialog">
      <div>
        <p><strong>目标服务器:</strong> {{ selectedServer?.name }}</p>
        <p><strong>账号:</strong> {{ selectedCred?.ssh_username }}</p>
        <p><strong>工单数量:</strong> {{ form.tickets.length }}</p>
        <el-table :data="form.tickets" border size="small" style="margin-top:12px;">
          <el-table-column prop="ticket_id" label="工单号" width="140" />
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
const ticketInput = ref('')

const form = reactive({ server_id: null, credential_id: null, tickets: [] })

const selectedServer = computed(() => servers.value.find(s => s.id === form.server_id))
const selectedCred = computed(() => credentials.value.find(c => c.id === form.credential_id))

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

function addTickets() {
  const raw = ticketInput.value
  if (!raw.trim()) return
  const ids = raw.split(/[,\s\n]+/).filter(Boolean).map(id => {
    id = id.trim()
    return /^\d+$/.test(id) ? `ONES-${id}` : id
  })
  for (const id of ids) {
    if (!form.tickets.find(t => t.ticket_id === id)) {
      form.tickets.push({ ticket_id: id, note: '', code_directory: '' })
    }
  }
  ticketInput.value = ''
}

function showPreview() {
  if (!form.server_id || !form.credential_id) return ElMessage.warning('请选择服务器和账号')
  previewDialog.value = true
}

async function submitTask() {
  submitting.value = true
  try {
    const task = await api.createTask(form)
    ElMessage.success('任务已提交！')
    previewDialog.value = false
    router.push(`/tasks/${task.id}`)
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '提交失败')
  } finally { submitting.value = false }
}
</script>
