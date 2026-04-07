<template>
  <div class="page-container" id="accuracy-view">
    <div class="page-header fade-in-up">
      <h1>🎯 AI 代码审查准确度评测</h1>
      <p>AI 智能分析与开发实际修复的一致性验证（五维度量化评分体系）</p>
    </div>

    <!-- 顶部统计卡片 -->
    <div class="stats-row fade-in-up" style="display:flex;gap:16px;margin-bottom:24px;flex-wrap:wrap;">
      <div class="glass-card stat-card" :class="rateClass">
        <div class="stat-icon">🎯</div>
        <div class="stat-number" :style="{ '-webkit-text-fill-color': rateColor }">{{ summary.accuracy_rate }}</div>
        <div class="stat-label">分析准确率</div>
      </div>
      <div class="glass-card stat-card accent-purple">
        <div class="stat-icon">📈</div>
        <div class="stat-number">{{ summary.avg_score }}</div>
        <div class="stat-label">平均得分</div>
      </div>
      <div class="glass-card stat-card accent-blue">
        <div class="stat-icon">📋</div>
        <div class="stat-number">{{ summary.total_completed_tickets }}</div>
        <div class="stat-label">AI 处理总量</div>
      </div>
      <div class="glass-card stat-card accent-green">
        <div class="stat-icon">✅</div>
        <div class="stat-number" style="-webkit-text-fill-color:#10b981;">{{ summary.effective_count }}</div>
        <div class="stat-label">高质量分析</div>
      </div>
      <div class="glass-card stat-card accent-blue">
        <div class="stat-icon">🔍</div>
        <div class="stat-number">{{ summary.total_evaluated }}</div>
        <div class="stat-label">已验证</div>
      </div>
      <div class="glass-card stat-card accent-amber">
        <div class="stat-icon">⏳</div>
        <div class="stat-number" style="-webkit-text-fill-color:#f59e0b;">{{ summary.skipped_count }}</div>
        <div class="stat-label">待验证</div>
      </div>
    </div>

    <!-- 雷达图 + 等级分布 -->
    <div class="fade-in-up" style="display:flex;gap:16px;margin-bottom:24px;flex-wrap:wrap;">
      <div class="glass-card" style="flex:1;min-width:380px;padding:24px;">
        <h3 style="margin-bottom:16px;">五维度均分雷达图</h3>
        <div ref="radarRef" style="height:320px;"></div>
      </div>
      <div class="glass-card" style="flex:1;min-width:380px;padding:24px;">
        <h3 style="margin-bottom:16px;">评分等级分布</h3>
        <div ref="pieRef" style="height:260px;"></div>
        <div style="margin-top:12px;display:flex;justify-content:center;gap:24px;font-size:0.85rem;">
          <span>🏆 高度一致 (≥75): <b style="color:#10b981;">{{ levelCounts.full }}</b></span>
          <span>🔵 方向正确 (40-74): <b style="color:#3b82f6;">{{ levelCounts.partial }}</b></span>
          <span>⚪ 待优化 (<40): <b style="color:#94a3b8;">{{ levelCounts.none }}</b></span>
        </div>
      </div>
    </div>

    <!-- 操作栏 -->
    <div class="glass-card fade-in-up" style="padding:16px;margin-bottom:16px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
      <el-button type="primary" :loading="batchLoading" @click="doBatch" :icon="Refresh">
        执行评测 ({{ summary.pending_count }} 待评)
      </el-button>
      <el-switch v-model="effectiveOnly" active-text="仅看高质量" inactive-text="全部" @change="loadTickets" />
      <span style="flex:1;"></span>
      <span style="font-size:0.85rem;color:var(--text-muted);">
        已验证 {{ ticketTotal }} 条 · AI 累计处理 {{ summary.total_completed_tickets }} 工单
      </span>
    </div>

    <!-- 评测结果列表 -->
    <div class="glass-card fade-in-up" style="padding:0;overflow:hidden;">
      <el-table :data="tickets" style="width:100%;" stripe :header-cell-style="{ background: 'rgba(30,64,175,0.08)' }">
        <el-table-column label="工单号" width="140" fixed>
          <template #default="{ row }">
            <span style="font-family:monospace;font-weight:600;color:var(--primary);">{{ row.ticket_id }}</span>
          </template>
        </el-table-column>
        <el-table-column label="总分" width="80" align="center" sortable>
          <template #default="{ row }">
            <el-tag :type="scoreType(row.scores.total)" size="large" effect="dark" round>
              {{ row.scores.total }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="文件" width="65" align="center">
          <template #default="{ row }">
            <span :class="dimClass(row.scores.file_match, 20)">{{ row.scores.file_match }}</span>
          </template>
        </el-table-column>
        <el-table-column label="根因" width="65" align="center">
          <template #default="{ row }">
            <span :class="dimClass(row.scores.root_cause, 20)">{{ row.scores.root_cause }}</span>
          </template>
        </el-table-column>
        <el-table-column label="方案" width="65" align="center">
          <template #default="{ row }">
            <span :class="dimClass(row.scores.fix_similar, 25)">{{ row.scores.fix_similar }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作性" width="65" align="center">
          <template #default="{ row }">
            <span :class="dimClass(row.scores.actionable, 15)">{{ row.scores.actionable }}</span>
          </template>
        </el-table-column>
        <el-table-column label="一致" width="65" align="center">
          <template #default="{ row }">
            <span :class="dimClass(row.scores.consistency, 20)">{{ row.scores.consistency }}</span>
          </template>
        </el-table-column>
        <el-table-column label="等级" width="100" align="center">
          <template #default="{ row }">
            <span v-if="row.scores.total >= 75" class="level-badge level-full">🏆 高度一致</span>
            <span v-else-if="row.scores.total >= 40" class="level-badge level-partial">🔵 方向正确</span>
            <span v-else class="level-badge level-none">⚪ 待优化</span>
          </template>
        </el-table-column>
        <el-table-column label="Gerrit" min-width="120">
          <template #default="{ row }">
            <a v-if="row.gerrit_change_url" :href="row.gerrit_change_url" target="_blank" class="gerrit-link">
              {{ row.gerrit_diff_summary }} ↗
            </a>
          </template>
        </el-table-column>
        <el-table-column label="评测时间" width="140">
          <template #default="{ row }">
            <span style="font-size:0.8rem;color:var(--text-muted);">{{ formatDate(row.evaluated_at) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div style="padding:16px;display:flex;justify-content:center;">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="ticketTotal"
          layout="prev, pager, next"
          @current-change="loadTickets"
        />
      </div>
    </div>

    <!-- 说明 -->
    <div class="glass-card fade-in-up" style="padding:16px;margin-top:16px;opacity:0.8;font-size:0.85rem;color:var(--text-muted);">
      💡 <b>五维度量化评分体系</b>：文件定位(20) + 根因定位(20) + 方案相似度(25, AI语义对比) + 可操作性(15) + 整体一致性(20) = 总分100。
      对比基准为开发者实际 Gerrit 提交。≥75分「高度一致」，40-74分「方向正确」，「待验证」为尚未完成闭环验证的工单。
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, nextTick } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import api from '../api'

const radarRef = ref(null)
const pieRef = ref(null)
let radarChart = null
let pieChart = null

const summary = ref({
  accuracy_rate: 'N/A', total_evaluated: 0, effective_count: 0,
  ineffective_count: 0, skipped_count: 0, pending_count: 0,
  total_completed_tickets: 0, avg_score: 0,
  dimension_avg: { file_match: 0, root_cause: 0, fix_similar: 0, actionable: 0, consistency: 0 }
})

const tickets = ref([])
const ticketTotal = ref(0)
const page = ref(1)
const pageSize = 20
const effectiveOnly = ref(false)
const batchLoading = ref(false)

const rateColor = computed(() => {
  const r = parseFloat(summary.value.accuracy_rate)
  if (isNaN(r)) return '#94a3b8'
  if (r >= 30) return '#10b981'
  if (r >= 10) return '#f59e0b'
  return '#ef4444'
})
const rateClass = computed(() => {
  const r = parseFloat(summary.value.accuracy_rate)
  if (r >= 30) return 'accent-green'
  if (r >= 10) return 'accent-amber'
  return 'accent-red'
})

const levelCounts = computed(() => {
  // 从列表数据估算
  let full = 0, partial = 0, none = 0
  // 用 summary 数据
  full = summary.value._level_full || 0
  partial = summary.value._level_partial || 0
  none = summary.value._level_none || 0
  if (full === 0 && partial === 0 && none === 0) {
    // fallback: 用 effective/ineffective
    partial = summary.value.effective_count
    none = summary.value.ineffective_count
  }
  return { full, partial, none }
})

function scoreType(score) {
  if (score >= 75) return 'success'
  if (score >= 40) return 'primary'
  if (score >= 20) return 'warning'
  return 'danger'
}

function dimClass(val, max) {
  const pct = val / max
  if (pct >= 0.75) return 'dim-high'
  if (pct >= 0.5) return 'dim-mid'
  if (pct > 0) return 'dim-low'
  return 'dim-zero'
}

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) + ' ' +
         d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

async function loadSummary() {
  try {
    const data = await api.getAccuracySummary()
    // 计算等级分布（从 tickets 数据）
    summary.value = { ...data, _level_full: 0, _level_partial: 0, _level_none: 0 }
  } catch (e) {
    console.error('加载统计失败', e)
  }
}

async function loadTickets() {
  try {
    const data = await api.getAccuracyTickets(page.value, pageSize, effectiveOnly.value)
    tickets.value = data.items || []
    ticketTotal.value = data.total || 0

    // 计算等级分布
    let full = 0, partial = 0
    for (const t of tickets.value) {
      if (t.scores.total >= 75) full++
      else if (t.scores.total >= 40) partial++
    }
    summary.value._level_full = full
    summary.value._level_partial = summary.value.effective_count - full
    if (summary.value._level_partial < 0) summary.value._level_partial = partial
    summary.value._level_none = summary.value.ineffective_count
  } catch (e) {
    console.error('加载评测详情失败', e)
  }
}

async function doBatch() {
  batchLoading.value = true
  try {
    const result = await api.batchAccuracyEval(100)
    ElMessage.success(`评测完成: ${result.evaluated} 评 / ${result.effective} 有效 / ${result.skipped} 跳过`)
    await loadSummary()
    await loadTickets()
    renderCharts()
  } catch (e) {
    ElMessage.error('评测失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    batchLoading.value = false
  }
}

function renderCharts() {
  const dim = summary.value.dimension_avg || {}

  // 雷达图
  if (!radarChart && radarRef.value) radarChart = echarts.init(radarRef.value)
  if (radarChart) {
    radarChart.setOption({
      backgroundColor: 'transparent',
      tooltip: {},
      radar: {
        indicator: [
          { name: '文件定位', max: 20 },
          { name: '根因定位', max: 20 },
          { name: '方案相似', max: 25 },
          { name: '可操作性', max: 15 },
          { name: '整体一致', max: 20 },
        ],
        shape: 'polygon',
        splitArea: { areaStyle: { color: ['rgba(30,64,175,0.02)', 'rgba(30,64,175,0.05)'] } },
        axisLine: { lineStyle: { color: 'rgba(30,64,175,0.15)' } },
        splitLine: { lineStyle: { color: 'rgba(30,64,175,0.1)' } },
        axisName: { color: 'var(--text-primary)', fontSize: 13 },
      },
      series: [{
        type: 'radar',
        data: [{
          value: [dim.file_match || 0, dim.root_cause || 0, dim.fix_similar || 0, dim.actionable || 0, dim.consistency || 0],
          name: '维度均分',
          areaStyle: { color: 'rgba(59,130,246,0.25)' },
          lineStyle: { color: '#3b82f6', width: 2 },
          itemStyle: { color: '#3b82f6' },
        }]
      }]
    })
  }

  // 饼图
  if (!pieChart && pieRef.value) pieChart = echarts.init(pieRef.value)
  if (pieChart) {
    const effective = summary.value.effective_count || 0
    const ineffective = summary.value.ineffective_count || 0
    const skipped = summary.value.skipped_count || 0
    pieChart.setOption({
      backgroundColor: 'transparent',
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { bottom: 0, textStyle: { color: 'var(--text-secondary)' } },
      series: [{
        type: 'pie', radius: ['40%', '70%'],
        avoidLabelOverlap: false,
        label: { show: false },
        emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } },
        data: [
          { value: effective, name: '高质量分析', itemStyle: { color: '#10b981' } },
          { value: ineffective, name: '待优化', itemStyle: { color: '#f87171' } },
          { value: skipped, name: '待验证', itemStyle: { color: '#94a3b8' } },
        ].filter(d => d.value > 0)
      }]
    })
  }
}

onMounted(async () => {
  await loadSummary()
  await loadTickets()
  await nextTick()
  renderCharts()
})
</script>

<style scoped>
.stat-card {
  flex: 1;
  min-width: 140px;
  text-align: center;
  padding: 20px 16px;
  position: relative;
  overflow: hidden;
}
.stat-icon {
  font-size: 1.5rem;
  margin-bottom: 4px;
}
.accent-blue { border-left: 3px solid #3b82f6; }
.accent-green { border-left: 3px solid #10b981; }
.accent-red { border-left: 3px solid #ef4444; }
.accent-amber { border-left: 3px solid #f59e0b; }
.accent-purple { border-left: 3px solid #8b5cf6; }

.dim-high { color: #10b981; font-weight: 700; }
.dim-mid { color: #3b82f6; font-weight: 600; }
.dim-low { color: #f59e0b; font-weight: 500; }
.dim-zero { color: #cbd5e1; }

.level-badge {
  font-size: 0.75rem;
  padding: 2px 8px;
  border-radius: 12px;
  white-space: nowrap;
}
.level-full { background: rgba(16,185,129,0.15); color: #10b981; }
.level-partial { background: rgba(59,130,246,0.15); color: #3b82f6; }
.level-none { background: rgba(148,163,184,0.15); color: #94a3b8; }

.gerrit-link {
  color: #3b82f6;
  text-decoration: none;
  font-size: 0.85rem;
}
.gerrit-link:hover { text-decoration: underline; }

:deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-row-hover-bg-color: rgba(59,130,246,0.08);
  --el-table-header-bg-color: transparent;
  --el-table-border-color: rgba(255,255,255,0.06);
  --el-table-text-color: var(--text-primary);
  --el-table-header-text-color: var(--text-secondary);
}
:deep(.el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell) {
  background: rgba(255,255,255,0.025) !important;
}
:deep(.el-table__row) {
  transition: background 0.2s;
}
:deep(.el-table__row:hover > td) {
  background: rgba(59,130,246,0.08) !important;
}
</style>
