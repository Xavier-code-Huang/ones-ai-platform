<template>
  <div class="page-container" id="admin-users">
    <h1 class="fade-in-up" style="font-size:1.6rem;font-weight:700;margin-bottom:16px;">用户明细</h1>
    <el-table :data="users" border style="width:100%;" @row-click="r => $router.push('/admin/users/'+r.user_id)" class="fade-in-up">
      <el-table-column prop="display_name" label="姓名" width="120" />
      <el-table-column prop="email" label="邮箱" />
      <el-table-column prop="task_count" label="任务数" width="100" sortable />
      <el-table-column prop="ticket_count" label="工单数" width="100" sortable />
      <el-table-column prop="avg_duration" label="平均耗时" width="120">
        <template #default="{ row }">{{ row.avg_duration?.toFixed(0) }}s</template>
      </el-table-column>
    </el-table>
    <el-button style="margin-top:16px;" @click="exportData" type="primary" plain><el-icon><Download /></el-icon> 导出 Excel</el-button>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'

const users = ref([])
onMounted(async () => { users.value = await api.getUserRankings(30) })

function exportData() {
  window.open('/api/admin/export?days=30', '_blank')
}
</script>
