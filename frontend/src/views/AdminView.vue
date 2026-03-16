<template>
  <div class="page-container" id="admin-overview">
    <h1 class="fade-in-up" style="font-size:1.6rem;font-weight:700;margin-bottom:8px;">管理总览</h1>
    <div style="margin-bottom:24px;">
      <el-radio-group v-model="days" @change="load" size="small">
        <el-radio-button :value="7">近 7 天</el-radio-button>
        <el-radio-button :value="30">近 30 天</el-radio-button>
        <el-radio-button :value="90">近 90 天</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-grid fade-in-up">
      <div class="glass-card stat-card" v-for="(s, i) in stats" :key="i">
        <div class="stat-number">{{ animatedValues[i] }}</div>
        <div class="stat-label">{{ s.label }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, watch } from 'vue'
import api from '../api'

const days = ref(30)
const overview = ref({})
const stats = ref([])
const animatedValues = reactive([0,0,0,0,0,0])

async function load() {
  overview.value = await api.getOverview(days.value)
  const o = overview.value
  stats.value = [
    { label: '总使用次数', value: o.total_tasks },
    { label: '总工单数', value: o.total_tickets },
    { label: '独立用户数', value: o.unique_users },
    { label: '平均耗时(秒)', value: Math.round(o.avg_duration) },
    { label: '通过率', value: (o.success_rate * 100).toFixed(1) + '%' },
    { label: '预估节省(小时)', value: o.estimated_hours_saved?.toFixed(0) },
  ]
  stats.value.forEach((s, i) => {
    const target = typeof s.value === 'string' ? parseFloat(s.value) : s.value
    animateValue(i, 0, target, 1000, typeof s.value === 'string' && s.value.includes('%'))
  })
}

function animateValue(idx, start, end, duration, isPercent) {
  const startTime = performance.now()
  function update(now) {
    const elapsed = now - startTime
    const progress = Math.min(elapsed / duration, 1)
    const current = Math.round(start + (end - start) * easeOut(progress))
    animatedValues[idx] = isPercent ? current + '%' : current
    if (progress < 1) requestAnimationFrame(update)
  }
  requestAnimationFrame(update)
}

function easeOut(t) { return 1 - Math.pow(1 - t, 3) }

onMounted(load)
</script>

<style scoped>
.stats-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }
.stat-card { text-align:center; padding:28px; }
</style>
