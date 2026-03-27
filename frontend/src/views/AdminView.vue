<template>
  <div class="page-container" id="admin-overview">
    <div class="page-header fade-in-up">
      <h1>数据总览</h1>
      <p>平台使用情况一览</p>
    </div>
    <div style="margin-bottom:24px;" class="fade-in-up">
      <el-radio-group v-model="days" @change="load" size="small">
        <el-radio-button :value="7">近 7 天</el-radio-button>
        <el-radio-button :value="30">近 30 天</el-radio-button>
        <el-radio-button :value="90">近 90 天</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 内部统计卡片 -->
    <div class="section-title fade-in-up">
      <span class="section-icon">📊</span> 内部使用
    </div>
    <div class="stats-grid fade-in-up">
      <div class="glass-card stat-card hover-lift" v-for="(s, i) in stats" :key="i"
           :style="{ animationDelay: (i * 0.06) + 's' }">
        <div class="stat-icon">{{ s.icon }}</div>
        <div class="stat-number count-up">{{ animatedValues[i] }}</div>
        <div class="stat-label">{{ s.label }}</div>
      </div>
    </div>

    <!-- 外部团队汇总 -->
    <div style="margin-top:36px;" v-if="externalTeams.length > 0">
      <div class="section-title fade-in-up">
        <span class="section-icon">🤝</span> 外部团队
      </div>
      <div class="external-grid fade-in-up">
        <div v-for="t in externalTeams" :key="t.team_id" class="glass-card hover-lift ext-card"
             @click="$router.push('/admin/external')">
          <div class="ext-card-header">
            <div class="ext-avatar">{{ t.team_name[0] }}</div>
            <div>
              <h4>{{ t.team_name }}</h4>
              <span class="ext-members">{{ t.member_count }} 成员</span>
            </div>
          </div>
          <div class="ext-stats">
            <span class="ext-stat-main">{{ t.total_logs }}</span>
            <span class="ext-stat-label">使用次数</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive } from 'vue'
import api from '../api'

const days = ref(30)
const overview = ref({})
const stats = ref([])
const externalTeams = ref([])
const animatedValues = reactive([0,0,0,0,0,0])

async function load() {
  overview.value = await api.getOverview(days.value)
  const o = overview.value
  stats.value = [
    { icon: '🚀', label: '总使用次数', value: o.total_tasks },
    { icon: '📋', label: '总工单数', value: o.total_tickets },
    { icon: '👥', label: '独立用户数', value: o.unique_users },
    { icon: '⏱️', label: '平均耗时(秒)', value: Math.round(o.avg_duration) },
    { icon: '✅', label: '执行成功率', value: (o.success_rate * 100).toFixed(1) + '%' },
    { icon: '💡', label: '预估节省(小时)', value: o.estimated_hours_saved?.toFixed(0) },
  ]
  stats.value.forEach((s, i) => {
    const target = typeof s.value === 'string' ? parseFloat(s.value) : s.value
    animateValue(i, 0, target, 1000, typeof s.value === 'string' && s.value.includes('%'))
  })

  // 加载外部团队汇总
  try {
    externalTeams.value = await api.getExternalOverview(days.value)
  } catch (e) {
    externalTeams.value = []
  }
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
.stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.stat-card {
  text-align: center; padding: 28px 20px;
  position: relative; overflow: hidden;
}
.stat-icon {
  font-size: 1.5rem;
  margin-bottom: 8px;
}
.stat-card .stat-number {
  font-size: 2.2rem;
}

/* 外部团队区域 */
.external-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; }
.ext-card {
  cursor: pointer; padding: 20px;
  display: flex; justify-content: space-between; align-items: center;
}
.ext-card-header { display: flex; align-items: center; gap: 10px; }
.ext-avatar {
  width: 36px; height: 36px; border-radius: 8px;
  background: var(--accent); color: white;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 1rem; flex-shrink: 0;
}
.ext-card-header h4 { font-size: 0.95rem; font-weight: 700; }
.ext-members { font-size: 0.75rem; color: var(--text-muted); }
.ext-stats { text-align: right; }
.ext-stat-main { display: block; font-size: 1.6rem; font-weight: 800; color: var(--accent); }
.ext-stat-label { display: block; font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; }

@media (max-width: 768px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
