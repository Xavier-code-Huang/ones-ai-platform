<template>
  <div class="page-container" id="admin-eval">
    <div class="page-header fade-in-up">
      <h1>评价分析</h1>
      <p>追踪 AI 工单处理质量的用户满意度反馈</p>
    </div>
    <div style="margin-bottom:24px;">
      <el-radio-group v-model="days" @change="load" size="small">
        <el-radio-button :value="7">近 7 天</el-radio-button>
        <el-radio-button :value="30">近 30 天</el-radio-button>
        <el-radio-button :value="90">近 90 天</el-radio-button>
      </el-radio-group>
    </div>
    <div class="stats-row fade-in-up" style="display:flex;gap:16px;margin-bottom:24px;">
      <div class="glass-card" style="flex:1;text-align:center;padding:24px;">
        <div class="stat-number">{{ stats.total_evaluations }}</div><div class="stat-label">总评价数</div>
      </div>
      <div class="glass-card" style="flex:1;text-align:center;padding:24px;">
        <div class="stat-number" :style="{ color: satisfyColor }">{{ satisfyPct }}%</div>
        <div class="stat-label">用户满意率</div>
      </div>
      <div class="glass-card" style="flex:1;text-align:center;padding:24px;">
        <div class="stat-number" style="-webkit-text-fill-color:var(--success);">{{ stats.passed_count }}</div><div class="stat-label">满意</div>
      </div>
      <div class="glass-card" style="flex:1;text-align:center;padding:24px;">
        <div class="stat-number" style="-webkit-text-fill-color:var(--danger);">{{ stats.failed_count }}</div><div class="stat-label">不满意</div>
      </div>
    </div>
    <div class="glass-card fade-in-up" style="padding:24px;">
      <h3 style="margin-bottom:16px;">每日满意率趋势</h3>
      <div ref="chartRef" style="height:300px;"></div>
    </div>

    <!-- 评价覆盖率提示 -->
    <div class="glass-card fade-in-up" style="padding:16px;margin-top:16px;opacity:0.8;font-size:0.85rem;color:var(--text-muted);">
      💡 说明：「用户满意率」= 用户手动评价为"满意"的数量 / 总评价数。
      管理总览中的「执行成功率」= AI 执行完毕未报错的工单数 / 总工单数，两者衡量的维度不同。
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import * as echarts from 'echarts'
import api from '../api'

const chartRef = ref(null)
const days = ref(90)
const stats = ref({ total_evaluations: 0, passed_count: 0, failed_count: 0, pass_rate: 0, trend: [] })

const satisfyPct = computed(() => (stats.value.pass_rate * 100).toFixed(1))
const satisfyColor = computed(() => {
  const pct = stats.value.pass_rate * 100
  if (pct >= 60) return '#10b981'
  if (pct >= 30) return '#f59e0b'
  return '#ef4444'
})

let chart = null

async function load() {
  stats.value = await api.getEvalStats(days.value)
  renderChart()
}

function renderChart() {
  const trend = stats.value.trend || []
  if (!chart && chartRef.value) {
    chart = echarts.init(chartRef.value)
  }
  if (!chart) return

  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      formatter: params => {
        const p = params[0]
        const t = trend[p.dataIndex]
        return `${p.name}<br/>满意率: <b>${p.value}%</b><br/>满意: ${t?.passed || 0} / 总评: ${t?.total || 0}`
      }
    },
    grid: { left: 50, right: 20, top: 30, bottom: 30 },
    xAxis: { type: 'category', data: trend.map(t => t.date) },
    yAxis: {
      type: 'value', min: 0, max: 100,
      axisLabel: { formatter: '{value}%' },
      splitLine: { lineStyle: { color: 'rgba(30,64,175,0.08)' } }
    },
    series: [
      {
        name: '满意率',
        type: 'line', smooth: true,
        data: trend.map(t => t.total > 0 ? Math.round(t.passed / t.total * 100) : null),
        connectNulls: true,
        lineStyle: { color: '#10b981', width: 2 },
        itemStyle: { color: '#10b981' },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(16,185,129,0.3)' },
              { offset: 1, color: 'rgba(16,185,129,0)' }
            ]
          }
        },
      },
      {
        name: '评价数',
        type: 'bar',
        data: trend.map(t => t.total),
        barWidth: 16,
        itemStyle: { color: 'rgba(30,64,175,0.2)', borderRadius: [4, 4, 0, 0] },
        yAxisIndex: 0,
      }
    ],
  })
}

onMounted(load)
</script>
