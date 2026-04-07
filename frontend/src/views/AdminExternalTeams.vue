<template>
  <div class="page-container" id="admin-external-teams">
    <div class="page-header fade-in-up">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div>
          <h1>外部团队管理</h1>
          <p>管理接入的外部工单处理系统团队</p>
        </div>
        <el-button type="primary" @click="showCreateDialog = true" round>
          <el-icon><Plus /></el-icon> 注册新团队
        </el-button>
      </div>
    </div>

    <!-- 团队卡片列表 -->
    <div class="teams-grid">
      <div v-for="(t, idx) in teams" :key="t.id" class="team-card glass-card hover-lift fade-in-up"
           :style="{ animationDelay: (idx * 0.06) + 's' }"
           @click="viewTeamDetail(t)">
        <div class="team-card-header">
          <div class="team-avatar">{{ t.team_name[0] }}</div>
          <div class="team-info">
            <h3>{{ t.team_name }}</h3>
            <span class="team-desc">{{ t.description || '暂无描述' }}</span>
          </div>
          <span :class="['badge', t.is_active ? 'badge-success' : 'badge-danger']">
            {{ t.is_active ? '活跃' : '已禁用' }}
          </span>
        </div>
        <div class="team-stats-row">
          <div class="team-stat">
            <span class="team-stat-num">{{ t.total_logs }}</span>
            <span class="team-stat-label">上报次数</span>
          </div>
          <div class="team-stat">
            <span class="team-stat-num">{{ t.total_members }}</span>
            <span class="team-stat-label">成员数</span>
          </div>
          <div class="team-stat">
            <span class="team-stat-num">{{ t.contact_email ? '✓' : '—' }}</span>
            <span class="team-stat-label">联系人</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="teams.length === 0 && !loading" class="empty-state fade-in-up">
      <div class="empty-icon">🤝</div>
      <p>暂无外部团队</p>
      <span>点击右上角注册新的外部团队</span>
    </div>

    <!-- 注册新团队弹窗 -->
    <el-dialog v-model="showCreateDialog" title="注册新团队" width="480px" :close-on-click-modal="false">
      <el-form :model="createForm" label-width="80px">
        <el-form-item label="团队名称" required>
          <el-input v-model="createForm.team_name" placeholder="如: 视觉质量团队" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="2" placeholder="可选" />
        </el-form-item>
        <el-form-item label="联系邮箱">
          <el-input v-model="createForm.contact_email" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog=false" round>取消</el-button>
        <el-button type="primary" :loading="creating" @click="doCreate" round>注册</el-button>
      </template>
    </el-dialog>

    <!-- 团队详情弹窗 -->
    <el-dialog v-model="showDetailDialog" :title="detailTeam?.team_name + ' — 详情'" width="720px">
      <template v-if="detailData">
        <!-- API Key -->
        <div class="detail-section">
          <h4>API Key</h4>
          <div class="api-key-box">
            <code>{{ detailTeam.api_key }}</code>
            <el-button size="small" @click="copyKey" text type="primary">复制</el-button>
          </div>
        </div>

        <!-- 统计概览 -->
        <div class="detail-section">
          <h4>统计概览（近 {{ detailDays }} 天）</h4>
          <div class="detail-stats-grid">
            <div class="detail-stat">
              <span class="stat-number">{{ detailData.overview.total }}</span>
              <span class="stat-label">总上报</span>
            </div>
            <div class="detail-stat">
              <span class="stat-number" style="color:var(--success);">{{ detailData.overview.success }}</span>
              <span class="stat-label">成功</span>
            </div>
            <div class="detail-stat">
              <span class="stat-number" style="color:var(--danger);">{{ detailData.overview.failed }}</span>
              <span class="stat-label">失败</span>
            </div>
            <div class="detail-stat">
              <span class="stat-number">{{ detailData.overview.success_rate }}%</span>
              <span class="stat-label">成功率</span>
            </div>
            <div class="detail-stat">
              <span class="stat-number">{{ detailData.overview.avg_duration }}s</span>
              <span class="stat-label">平均耗时</span>
            </div>
          </div>
        </div>

        <!-- 趋势图 -->
        <div class="detail-section" v-if="detailData.trends.length > 0">
          <h4>使用趋势</h4>
          <div class="glass-card" style="padding:16px;">
            <div ref="trendChartRef" style="height:220px;"></div>
          </div>
        </div>
        <!-- 成员明细 -->
        <div class="detail-section">
          <h4>成员使用明细</h4>
          <el-table :data="detailData.members" border size="small" style="width:100%;"
                    @row-click="openMemberLogs" class="member-table">
            <el-table-column prop="member_name" label="成员" min-width="140">
              <template #default="{ row }">
                <span class="member-link">{{ row.member_name }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="log_count" label="上报次数" min-width="100" sortable />
            <el-table-column prop="success_count" label="成功" min-width="80" />
            <el-table-column label="平均耗时" min-width="100">
              <template #default="{ row }">{{ row.avg_duration }}s</template>
            </el-table-column>
          </el-table>
        </div>
      </template>
      <div v-else style="text-align:center;padding:40px;">
        <el-icon class="is-loading" :size="24"><Loading /></el-icon>
        <p style="margin-top:8px;color:var(--text-muted);">加载中...</p>
      </div>
      <template #footer>
        <el-popconfirm title="确定删除此团队？所有数据将被清除。" @confirm="doDelete">
          <template #reference>
            <el-button type="danger" plain round>删除团队</el-button>
          </template>
        </el-popconfirm>
        <el-button @click="showDetailDialog=false" round>关闭</el-button>
      </template>
    </el-dialog>

    <!-- 成员日志弹框 -->
    <el-dialog v-model="showMemberDialog" :title="memberDialogTitle" width="820px" append-to-body>
      <div v-if="memberLogsLoading" style="text-align:center;padding:40px;">
        <el-icon class="is-loading" :size="24"><Loading /></el-icon>
        <p style="margin-top:8px;color:var(--text-muted);">加载中...</p>
      </div>
      <template v-else-if="memberLogs.length">
        <!-- 成员统计概览 -->
        <div class="member-dialog-stats">
          <div class="member-mini-stat">
            <span class="stat-number">{{ memberLogs.length }}</span>
            <span class="stat-label">总记录</span>
          </div>
          <div class="member-mini-stat">
            <span class="stat-number" style="color:var(--success);">{{ memberLogs.filter(l => l.status === 'completed').length }}</span>
            <span class="stat-label">成功</span>
          </div>
          <div class="member-mini-stat">
            <span class="stat-number" style="color:var(--danger);">{{ memberLogs.filter(l => l.status === 'failed').length }}</span>
            <span class="stat-label">失败</span>
          </div>
          <div class="member-mini-stat">
            <span class="stat-number">{{ memberAvgDuration }}s</span>
            <span class="stat-label">平均耗时</span>
          </div>
        </div>
        <!-- 日志表格 -->
        <el-table :data="memberLogs" size="small" border style="width:100%;" max-height="420">
          <el-table-column prop="ticket_id" label="工单号" width="130">
            <template #default="{ row }">
              <span v-if="row.ticket_id" class="mono-text">{{ row.ticket_id }}</span>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="80" align="center">
            <template #default="{ row }">
              <span :class="['status-dot-inline', row.status === 'completed' ? 'dot-success' : 'dot-danger']"></span>
              {{ row.status === 'completed' ? '成功' : '失败' }}
            </template>
          </el-table-column>
          <el-table-column prop="duration" label="耗时" width="80" align="right">
            <template #default="{ row }">{{ row.duration }}s</template>
          </el-table-column>
          <el-table-column prop="summary" label="处理摘要" min-width="220">
            <template #default="{ row }">
              <span v-if="row.summary" style="font-size:0.82rem;line-height:1.5;">{{ row.summary }}</span>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="reported_at" label="上报时间" width="150">
            <template #default="{ row }">
              <span class="text-muted" style="font-size:0.78rem;">{{ row.reported_at?.substring(0,16) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </template>
      <div v-else style="text-align:center;padding:40px;color:var(--text-muted);">
        💭 该成员暂无上报记录
      </div>
      <template #footer>
        <el-button @click="showMemberDialog=false" round>关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import api from '../api'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { Loading } from '@element-plus/icons-vue'

const teams = ref([])
const loading = ref(false)
const showCreateDialog = ref(false)
const showDetailDialog = ref(false)
const creating = ref(false)
const createForm = reactive({ team_name: '', description: '', contact_email: '' })
const detailTeam = ref(null)
const detailData = ref(null)
const detailDays = ref(30)
const trendChartRef = ref(null)
let trendChart = null

async function loadTeams() {
  loading.value = true
  try { teams.value = await api.getExternalTeams() }
  catch (e) { ElMessage.error('加载失败') }
  finally { loading.value = false }
}

async function doCreate() {
  if (!createForm.team_name.trim()) return ElMessage.warning('请输入团队名称')
  creating.value = true
  try {
    const t = await api.createExternalTeam(createForm)
    ElMessage.success(`团队 "${t.team_name}" 注册成功`)
    showCreateDialog.value = false
    createForm.team_name = ''
    createForm.description = ''
    createForm.contact_email = ''
    await loadTeams()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '创建失败')
  } finally { creating.value = false }
}

async function viewTeamDetail(t) {
  detailTeam.value = t
  detailData.value = null
  showDetailDialog.value = true
  try {
    detailData.value = await api.getExternalTeamStats(t.id, detailDays.value)
    await nextTick()
    if (detailData.value.trends.length > 0 && trendChartRef.value) {
      renderChart()
    }
  } catch (e) {
    ElMessage.error('加载详情失败')
  }
}

function renderChart() {
  if (!trendChartRef.value) return
  if (trendChart) trendChart.dispose()
  trendChart = echarts.init(trendChartRef.value)
  const dates = detailData.value.trends.map(d => d.date)
  const counts = detailData.value.trends.map(d => d.count)
  trendChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 16, top: 16, bottom: 30 },
    xAxis: { type: 'category', data: dates, axisLabel: { color: '#94a3b8', fontSize: 11 }, axisLine: { lineStyle: { color: '#e2e8f0' } } },
    yAxis: { type: 'value', axisLabel: { color: '#94a3b8', fontSize: 11 }, splitLine: { lineStyle: { color: '#f1f5f9' } } },
    series: [{
      type: 'line', data: counts, smooth: true,
      lineStyle: { color: '#1e40af', width: 2 },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [{ offset: 0, color: 'rgba(30,64,175,0.15)' }, { offset: 1, color: 'rgba(30,64,175,0)' }] } },
      itemStyle: { color: '#1e40af' },
    }],
  })
}

async function doDelete() {
  try {
    await api.deleteExternalTeam(detailTeam.value.id)
    ElMessage.success('已删除')
    showDetailDialog.value = false
    await loadTeams()
  } catch (e) { ElMessage.error('删除失败') }
}

function copyKey() {
  navigator.clipboard.writeText(detailTeam.value.api_key)
  ElMessage.success('已复制 API Key')
}

// 成员日志弹框
const showMemberDialog = ref(false)
const memberLogs = ref([])
const memberLogsLoading = ref(false)
const currentMemberName = ref('')

const memberDialogTitle = computed(() => `📝 ${currentMemberName.value} — 详细记录`)
const memberAvgDuration = computed(() => {
  if (!memberLogs.value.length) return 0
  const total = memberLogs.value.reduce((s, l) => s + (l.duration || 0), 0)
  return (total / memberLogs.value.length).toFixed(1)
})

async function openMemberLogs(row) {
  currentMemberName.value = row.member_name
  memberLogs.value = []
  memberLogsLoading.value = true
  showMemberDialog.value = true
  try {
    const data = await api.getMemberLogs(detailTeam.value.id, row.member_name, detailDays.value)
    memberLogs.value = data.logs || []
  } catch (e) {
    ElMessage.error('加载成员日志失败')
  } finally {
    memberLogsLoading.value = false
  }
}

onMounted(loadTeams)
</script>

<style scoped>
.teams-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 16px;
}
.team-card { cursor: pointer; }
.team-card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.team-avatar {
  width: 40px; height: 40px;
  border-radius: 10px;
  background: var(--accent);
  color: white;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 1.1rem;
  flex-shrink: 0;
}
.team-info { flex: 1; min-width: 0; }
.team-info h3 { font-size: 1.05rem; font-weight: 700; }
.team-desc { font-size: 0.82rem; color: var(--text-muted); display: block; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.team-stats-row {
  display: flex; gap: 24px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}
.team-stat { text-align: center; flex: 1; }
.team-stat-num { display: block; font-size: 1.3rem; font-weight: 700; color: var(--accent); }
.team-stat-label { display: block; font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 2px; font-weight: 600; }

/* 详情弹窗 */
.detail-section { margin-bottom: 24px; }
.detail-section h4 {
  font-size: 0.88rem; font-weight: 700; color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px;
}
.api-key-box {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.api-key-box code {
  flex: 1; font-family: var(--font-mono); font-size: 0.82rem;
  color: var(--text-secondary); word-break: break-all;
}
.detail-stats-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
}
.detail-stat {
  text-align: center;
  padding: 16px 8px;
  background: var(--bg-surface);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
}

.member-table :deep(.el-table__row) {
  cursor: pointer;
}
.member-table :deep(.el-table__row:hover > td) {
  background: rgba(59,130,246,0.06) !important;
}
.member-table :deep(.current-row > td) {
  background: transparent !important;
}

.member-link {
  cursor: pointer;
  color: var(--accent);
  font-weight: 600;
  transition: color 0.2s;
}
.member-link:hover {
  color: var(--accent-dark, #1e40af);
  text-decoration: underline;
}

/* 成员弹框内 */
.member-dialog-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 16px;
}
.member-mini-stat {
  text-align: center;
  padding: 12px 8px;
  background: var(--bg-surface, #f8fafc);
  border-radius: var(--radius-sm, 6px);
  border: 1px solid var(--border, #e2e8f0);
}
.mono-text {
  font-family: var(--font-mono, monospace);
  font-size: 0.8rem;
}
.text-muted {
  color: var(--text-muted, #94a3b8);
  font-size: 0.82rem;
}
.status-dot-inline {
  display: inline-block;
  width: 6px; height: 6px;
  border-radius: 50%;
  margin-right: 4px;
  vertical-align: middle;
}
.dot-success { background: var(--success, #22c55e); }
.dot-danger { background: var(--danger, #ef4444); }
</style>
