<template>
  <div class="page-container" id="admin-user-detail">
    <el-button @click="$router.back()" text type="primary" style="margin-bottom:12px;">← 返回用户列表</el-button>
    <h1 class="fade-in-up" style="font-size:1.6rem;font-weight:700;">用户使用记录</h1>
    <div class="fade-in-up" style="margin-top:20px;">
      <div v-for="t in tasks" :key="t.task_id" class="glass-card" style="margin-bottom:12px;padding:16px;">
        <div style="display:flex;justify-content:space-between;">
          <span><strong>#{{ t.task_id }}</strong> · {{ t.server_name }}</span>
          <span :class="'badge badge-' + (t.status==='completed'?'success':'danger')">{{ t.status }}</span>
        </div>
        <div style="color:var(--text-secondary);font-size:0.85rem;margin-top:4px;">
          {{ t.created_at?.substring(0,16) }} · {{ t.ticket_count }} 工单 · {{ t.total_duration?.toFixed(0) }}s
        </div>
        <div v-for="tt in t.tickets" :key="tt.ticket_id" style="margin-top:8px;padding:8px;background:var(--bg-secondary);border-radius:6px;font-size:0.85rem;">
          <span style="color:var(--accent-blue);">{{ tt.ticket_id }}</span>
          <span v-if="tt.note" style="color:var(--text-muted);margin-left:8px;">{{ tt.note }}</span>
          <span style="float:right;" :class="tt.status==='completed'?'badge badge-success':'badge badge-danger'">{{ tt.status }}</span>
        </div>
      </div>
      <div v-if="tasks.length===0" style="text-align:center;color:var(--text-muted);padding:40px;">暂无记录</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'

const route = useRoute()
const tasks = ref([])

onMounted(async () => {
  tasks.value = await api.getUserDetail(route.params.id, 90)
})
</script>
