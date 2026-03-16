<template>
  <div class="page-container" id="admin-eval">
    <h1 class="fade-in-up" style="font-size:1.6rem;font-weight:700;margin-bottom:24px;">评价分析</h1>
    <div class="stats-row fade-in-up" style="display:flex;gap:16px;margin-bottom:24px;">
      <div class="glass-card" style="flex:1;text-align:center;padding:24px;">
        <div class="stat-number">{{ stats.total_evaluations }}</div><div class="stat-label">总评价数</div>
      </div>
      <div class="glass-card" style="flex:1;text-align:center;padding:24px;">
        <div class="stat-number" style="background:linear-gradient(135deg,#10b981,#34d399);-webkit-background-clip:text;">{{ (stats.pass_rate*100).toFixed(1) }}%</div>
        <div class="stat-label">通过率</div>
      </div>
      <div class="glass-card" style="flex:1;text-align:center;padding:24px;">
        <div class="stat-number" style="-webkit-text-fill-color:var(--success);">{{ stats.passed_count }}</div><div class="stat-label">通过</div>
      </div>
      <div class="glass-card" style="flex:1;text-align:center;padding:24px;">
        <div class="stat-number" style="-webkit-text-fill-color:var(--danger);">{{ stats.failed_count }}</div><div class="stat-label">未通过</div>
      </div>
    </div>
    <div class="glass-card fade-in-up" style="padding:24px;">
      <h3 style="margin-bottom:16px;">通过率趋势</h3>
      <div ref="chartRef" style="height:300px;"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import * as echarts from 'echarts'
import api from '../api'

const chartRef = ref(null)
const stats = ref({ total_evaluations: 0, passed_count: 0, failed_count: 0, pass_rate: 0, trend: [] })

onMounted(async () => {
  stats.value = await api.getEvalStats(90)
  const trend = stats.value.trend || []

  const chart = echarts.init(chartRef.value, 'dark')
  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'category', data: trend.map(t => t.date) },
    yAxis: { type: 'value', max: 100, axisLabel: { formatter: '{value}%' }, splitLine: { lineStyle: { color: 'rgba(99,102,241,0.1)' } } },
    series: [{
      type: 'line', smooth: true,
      data: trend.map(t => t.total > 0 ? Math.round(t.passed / t.total * 100) : 0),
      lineStyle: { color: '#10b981', width: 2 },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(16,185,129,0.3)' }, { offset: 1, color: 'rgba(16,185,129,0)' }] } },
    }],
  })
})
</script>
