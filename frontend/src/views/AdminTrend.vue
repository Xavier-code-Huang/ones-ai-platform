<template>
  <div class="page-container" id="admin-trends">
    <div class="page-header fade-in-up">
      <h1>趋势分析</h1>
      <p>平台使用量和工单处理量走势</p>
    </div>

    <div class="controls fade-in-up">
      <el-radio-group v-model="granularity" @change="load" size="small">
        <el-radio-button value="day">按日</el-radio-button>
        <el-radio-button value="week">按周</el-radio-button>
        <el-radio-button value="month">按月</el-radio-button>
      </el-radio-group>
    </div>

    <div class="glass-card fade-in-up chart-card">
      <div ref="chartRef" style="height:420px;"></div>
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

  if (!chart) chart = echarts.init(chartRef.value)
  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255,255,255,0.96)',
      borderColor: '#e2e8f0',
      textStyle: { color: '#0f172a', fontSize: 12 },
      axisPointer: { lineStyle: { color: '#cbd5e1' } },
    },
    legend: {
      data: ['使用次数', '工单处理量'],
      textStyle: { color: '#64748b' },
      itemGap: 24,
    },
    grid: { left: 48, right: 24, top: 48, bottom: 36 },
    xAxis: {
      type: 'category', data: dates,
      axisLabel: { color: '#94a3b8', fontSize: 11 },
      axisLine: { lineStyle: { color: '#e2e8f0' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#94a3b8', fontSize: 11 },
      splitLine: { lineStyle: { color: '#f1f5f9' } },
    },
    series: [
      {
        name: '使用次数', type: 'line', data: counts, smooth: true,
        lineStyle: { color: '#1e40af', width: 2.5 },
        areaStyle: {
          color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(30, 64, 175, 0.12)' },
              { offset: 1, color: 'rgba(30, 64, 175, 0)' }
            ]
          }
        },
        itemStyle: { color: '#1e40af' },
        symbol: 'circle', symbolSize: 4,
      },
      {
        name: '工单处理量', type: 'bar', data: tickets,
        itemStyle: { color: 'rgba(13, 148, 136, 0.6)', borderRadius: [4, 4, 0, 0] },
      },
    ],
  })
}

onMounted(load)
</script>

<style scoped>
.controls { margin-bottom: 20px; }
.chart-card { padding: 24px; }
</style>
