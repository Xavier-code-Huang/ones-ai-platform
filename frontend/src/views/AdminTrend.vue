<template>
  <div class="page-container" id="admin-trends">
    <h1 class="fade-in-up" style="font-size:1.6rem;font-weight:700;margin-bottom:16px;">趋势分析</h1>
    <el-radio-group v-model="granularity" @change="load" size="small" style="margin-bottom:16px;">
      <el-radio-button value="day">按日</el-radio-button>
      <el-radio-button value="week">按周</el-radio-button>
      <el-radio-button value="month">按月</el-radio-button>
    </el-radio-group>

    <div class="glass-card fade-in-up" style="padding:24px;">
      <div ref="chartRef" style="height:400px;"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import * as echarts from 'echarts'
import api from '../api'

const chartRef = ref(null)
const granularity = ref('day')
let chart = null

async function load() {
  const data = await api.getTrends(90, granularity.value)
  const dates = data.map(d => d.date)
  const counts = data.map(d => d.count)
  const tickets = data.map(d => d.tickets)

  if (!chart) chart = echarts.init(chartRef.value, 'dark')
  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { data: ['使用次数', '工单处理量'] },
    grid: { left: 40, right: 20, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: dates, axisLabel: { color: '#94a3b8' } },
    yAxis: { type: 'value', axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: 'rgba(99,102,241,0.1)' } } },
    series: [
      { name: '使用次数', type: 'line', data: counts, smooth: true, lineStyle: { color: '#6366f1' }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(99,102,241,0.3)' }, { offset: 1, color: 'rgba(99,102,241,0)' }] } } },
      { name: '工单处理量', type: 'bar', data: tickets, itemStyle: { color: 'rgba(139,92,246,0.6)', borderRadius: [4,4,0,0] } },
    ],
  })
}

onMounted(load)
</script>
