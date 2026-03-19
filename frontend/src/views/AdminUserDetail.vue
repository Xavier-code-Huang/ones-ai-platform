<template>
  <div class="page-container" id="admin-user-detail">
    <el-button @click="$router.back()" text type="primary" style="margin-bottom:12px;">← 返回用户列表</el-button>
    <h1 class="fade-in-up" style="font-size:1.6rem;font-weight:700;">用户使用记录</h1>

    <!-- [FR-022] 使用频次趋势图表 -->
    <div class="glass-card fade-in-up" style="margin-top:16px;padding:20px 24px;">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:16px;">
        <h3 style="font-size:1rem;font-weight:600;margin:0;">📊 使用频次趋势</h3>
        <div style="display:flex;gap:10px;align-items:center;">
          <el-radio-group v-model="granularity" @change="loadTrends" size="small">
            <el-radio-button value="day">按日</el-radio-button>
            <el-radio-button value="week">按周</el-radio-button>
            <el-radio-button value="month">按月</el-radio-button>
          </el-radio-group>
          <el-radio-group v-model="trendDays" @change="loadTrends" size="small">
            <el-radio-button :value="30">30天</el-radio-button>
            <el-radio-button :value="90">90天</el-radio-button>
            <el-radio-button :value="180">180天</el-radio-button>
          </el-radio-group>
        </div>
      </div>
      <div ref="chartRef" style="height:350px;"></div>
      <div v-if="noTrendData" style="text-align:center;color:var(--text-muted);padding:60px 0;">
        暂无使用记录
      </div>
    </div>

    <!-- 任务历史列表 -->
    <h3 class="fade-in-up" style="font-size:1rem;font-weight:600;margin-top:24px;margin-bottom:12px;">📋 任务历史记录</h3>
    <div class="fade-in-up">
      <div v-for="t in tasks" :key="t.task_id" class="glass-card" style="margin-bottom:12px;padding:16px;">
        <div style="display:flex;justify-content:space-between;">
          <span><strong>#{{ t.task_id }}</strong> · {{ t.server_name }}</span>
          <span :class="'badge badge-' + (t.status==='completed'?'success':'danger')">{{ t.status }}</span>
        </div>
        <div style="color:var(--text-secondary);font-size:0.85rem;margin-top:4px;">
          {{ t.created_at?.substring(0,16) }} · {{ t.ticket_count }} 工单 · {{ t.total_duration?.toFixed(0) }}s
        </div>
        <div v-for="tt in t.tickets" :key="tt.ticket_id" style="margin-top:8px;padding:8px 12px;background:var(--bg-secondary);border-radius:6px;font-size:0.85rem;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span>
              <span style="color:var(--accent-blue);">{{ tt.ticket_id }}</span>
              <span v-if="tt.ticket_title" style="margin-left:8px;color:var(--text-primary);">{{ tt.ticket_title }}</span>
            </span>
            <span :class="tt.status==='completed'?'badge badge-success':'badge badge-danger'">{{ tt.status }}</span>
          </div>
          <div v-if="tt.result_summary" style="color:var(--text-secondary);margin-top:4px;white-space:pre-line;line-height:1.5;">{{ tt.result_summary }}</div>
          <div v-if="tt.note" style="color:var(--text-muted);margin-top:4px;font-size:0.8rem;">💬 {{ tt.note }}</div>
        </div>
      </div>
      <div v-if="tasks.length===0" style="text-align:center;color:var(--text-muted);padding:40px;">暂无记录</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import * as echarts from 'echarts'
import api from '../api'

const route = useRoute()
const tasks = ref([])
const granularity = ref('day')
const trendDays = ref(90)
const chartRef = ref(null)
const noTrendData = ref(false)
let chart = null

async function loadTrends() {
  try {
    const data = await api.getUserTrends(route.params.id, trendDays.value, granularity.value)
    if (!data || data.length === 0) {
      noTrendData.value = true
      if (chart) { chart.clear() }
      return
    }
    noTrendData.value = false
    const dates = data.map(d => d.date)
    const taskCounts = data.map(d => d.task_count)
    const ticketCounts = data.map(d => d.ticket_count)

    if (!chart && chartRef.value) chart = echarts.init(chartRef.value, 'dark')
    if (!chart) return

    chart.setOption({
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis' },
      legend: { data: ['任务数', '工单数'], textStyle: { color: '#94a3b8' } },
      grid: { left: 45, right: 20, top: 45, bottom: 30 },
      xAxis: {
        type: 'category', data: dates,
        axisLabel: { color: '#94a3b8', fontSize: 11 },
        axisLine: { lineStyle: { color: 'rgba(99,102,241,0.2)' } },
      },
      yAxis: {
        type: 'value', minInterval: 1,
        axisLabel: { color: '#94a3b8' },
        splitLine: { lineStyle: { color: 'rgba(99,102,241,0.1)' } },
      },
      series: [
        {
          name: '任务数', type: 'line', data: taskCounts, smooth: true,
          lineStyle: { color: '#6366f1', width: 2 },
          itemStyle: { color: '#6366f1' },
          areaStyle: {
            color: {
              type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(99,102,241,0.3)' },
                { offset: 1, color: 'rgba(99,102,241,0)' },
              ],
            },
          },
        },
        {
          name: '工单数', type: 'bar', data: ticketCounts,
          itemStyle: { color: 'rgba(139,92,246,0.6)', borderRadius: [4, 4, 0, 0] },
        },
      ],
    })
  } catch (err) {
    console.error('加载趋势失败', err)
    noTrendData.value = true
  }
}
const handleResize = () => { if (chart) chart.resize() }

onMounted(async () => {
  tasks.value = await api.getUserDetail(route.params.id, 90)
  await loadTrends()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (chart) { chart.dispose(); chart = null }
})
</script>
