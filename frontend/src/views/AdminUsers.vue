<template>
  <div class="page-container" id="admin-users">
    <div class="page-header fade-in-up">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div>
          <h1>用户明细</h1>
          <p>所有用户的使用分析</p>
        </div>
        <el-button @click="exportData" type="primary" plain round>
          <el-icon><Download /></el-icon> 导出 Excel
        </el-button>
      </div>
    </div>

    <!-- 搜索 -->
    <div class="fade-in-up" style="margin-bottom:16px;">
      <el-input v-model="searchQuery" placeholder="搜索姓名或邮箱..." prefix-icon="Search"
                clearable style="max-width:320px;" />
    </div>

    <div class="user-table-wrap glass-card fade-in-up">
      <el-table :data="filteredUsers" border style="width:100%;"
                @row-click="r => $router.push('/admin/users/'+r.user_id)"
                :row-class-name="'user-row'">
        <el-table-column prop="display_name" label="姓名" width="140">
          <template #default="{ row }">
            <div style="display:flex;align-items:center;gap:8px;">
              <div class="user-avatar">{{ (row.display_name || row.email)[0] }}</div>
              <span style="font-weight:600;">{{ row.display_name || '—' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="email" label="邮箱" />
        <el-table-column prop="task_count" label="任务数" width="100" sortable>
          <template #default="{ row }">
            <span class="num-highlight">{{ row.task_count }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="ticket_count" label="工单数" width="100" sortable>
          <template #default="{ row }">
            <span class="num-highlight">{{ row.ticket_count }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="avg_duration" label="平均耗时" width="120">
          <template #default="{ row }">{{ row.avg_duration?.toFixed(0) }}s</template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import api from '../api'

const users = ref([])
const searchQuery = ref('')

const filteredUsers = computed(() => {
  if (!searchQuery.value) return users.value
  const q = searchQuery.value.toLowerCase()
  return users.value.filter(u =>
    (u.display_name || '').toLowerCase().includes(q) ||
    (u.email || '').toLowerCase().includes(q)
  )
})

onMounted(async () => { users.value = await api.getUserRankings(30) })

function exportData() {
  window.open('/api/admin/export?days=30', '_blank')
}
</script>

<style scoped>
.user-table-wrap { padding: 0; overflow: hidden; }
.user-avatar {
  width: 28px; height: 28px;
  border-radius: 6px;
  background: var(--accent-bg);
  color: var(--accent);
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 0.78rem;
  flex-shrink: 0;
}
.num-highlight {
  font-weight: 700;
  color: var(--accent);
  font-family: var(--font-mono);
}
:deep(.user-row) {
  cursor: pointer;
  transition: background 0.15s ease;
}
:deep(.user-row:hover td) {
  background: var(--bg-card-hover) !important;
}
</style>
