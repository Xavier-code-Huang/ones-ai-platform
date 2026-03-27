<template>
  <div class="page-container" id="admin-servers">
    <div class="page-header fade-in-up">
      <h1>服务器管理</h1>
      <p>启用/禁用服务器对普通用户的可见性。禁用后用户无法看到和选择该服务器。</p>
    </div>

    <!-- 概览统计 -->
    <div class="server-stats fade-in-up">
      <div class="server-stat-card glass-card">
        <span class="server-stat-icon" style="background:var(--info-bg);color:var(--info);">🖥️</span>
        <div>
          <span class="server-stat-num">{{ servers.length }}</span>
          <span class="server-stat-label">服务器总数</span>
        </div>
      </div>
      <div class="server-stat-card glass-card">
        <span class="server-stat-icon" style="background:var(--success-bg);color:var(--success);">✅</span>
        <div>
          <span class="server-stat-num" style="color:var(--success);">{{ onlineCount }}</span>
          <span class="server-stat-label">在线</span>
        </div>
      </div>
      <div class="server-stat-card glass-card">
        <span class="server-stat-icon" style="background:var(--accent-bg);color:var(--accent);">👁️</span>
        <div>
          <span class="server-stat-num">{{ enabledCount }}</span>
          <span class="server-stat-label">已启用</span>
        </div>
      </div>
    </div>

    <div class="glass-card fade-in-up" style="margin-top:16px;">
      <el-table :data="servers" style="width:100%;" row-key="id">
        <el-table-column prop="name" label="服务器名称" min-width="180">
          <template #default="{ row }">
            <div class="server-name-cell">
              <span class="server-name">{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="host" label="IP 地址" width="160">
          <template #default="{ row }">
            <code class="server-host">{{ row.host }}</code>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100" align="center">
          <template #default="{ row }">
            <span :class="['status-indicator', row.status === 'online' ? 'status-online' : 'status-offline']">
              <span class="status-dot-sm"></span>
              {{ row.status === 'online' ? '在线' : '离线' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="凭证数" width="80" align="center">
          <template #default="{ row }">
            <span class="credential-count">{{ row.credential_count }}</span>
          </template>
        </el-table-column>
        <el-table-column label="可见性" width="120" align="center">
          <template #default="{ row }">
            <el-switch
              v-model="row.is_enabled"
              @change="toggle(row)"
              :loading="row._toggling"
              active-text="启用"
              inactive-text="禁用"
              inline-prompt
            />
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const servers = ref([])

const onlineCount = computed(() => servers.value.filter(s => s.status === 'online').length)
const enabledCount = computed(() => servers.value.filter(s => s.is_enabled).length)

async function load() {
  const list = await api.getServers()
  servers.value = list.map(s => ({ ...s, _toggling: false }))
}

async function toggle(row) {
  row._toggling = true
  try {
    const res = await api.toggleServer(row.id)
    row.is_enabled = res.is_enabled
    ElMessage.success(`${row.name} 已${res.is_enabled ? '启用' : '禁用'}`)
  } catch (e) {
    row.is_enabled = !row.is_enabled  // revert
    ElMessage.error(e.response?.data?.detail || '操作失败')
  } finally {
    row._toggling = false
  }
}

onMounted(load)
</script>

<style scoped>
.server-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}
.server-stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 20px;
}
.server-stat-icon {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.2rem;
  flex-shrink: 0;
}
.server-stat-num {
  display: block;
  font-size: 1.5rem;
  font-weight: 800;
  color: var(--text-primary);
  line-height: 1.1;
}
.server-stat-label {
  display: block;
  font-size: 0.72rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
  margin-top: 2px;
}
.server-name {
  font-weight: 600;
  color: var(--text-primary);
}
.server-host {
  font-family: var(--font-mono);
  font-size: 0.82rem;
  color: var(--text-secondary);
  background: var(--bg-surface);
  padding: 2px 8px;
  border-radius: 4px;
}
.status-indicator {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 0.82rem;
  font-weight: 600;
}
.status-dot-sm {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}
.status-online { color: var(--success); }
.status-offline { color: var(--text-muted); }
.credential-count {
  font-weight: 600;
  color: var(--text-secondary);
}

@media (max-width: 768px) {
  .server-stats { grid-template-columns: 1fr; }
}
</style>
