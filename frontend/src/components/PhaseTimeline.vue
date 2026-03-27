<template>
  <div class="phase-timeline">
    <div
      v-for="(phase, idx) in phases"
      :key="phase.phase_name"
      class="phase-node"
      :class="[`phase-${phase.status}`, { 'phase-last': idx === phases.length - 1 }]"
      :style="{ '--delay': `${idx * 60}ms` }"
    >
      <!-- 连接线 -->
      <div v-if="idx < phases.length - 1" class="phase-connector"
           :class="{ done: phase.status === 'completed' }" />

      <!-- 圆点 -->
      <div class="phase-dot">
        <span v-if="phase.status === 'completed'" class="dot-icon">✓</span>
        <span v-else-if="phase.status === 'failed'" class="dot-icon">✗</span>
        <span v-else-if="phase.status === 'skipped'" class="dot-icon">–</span>
        <span v-else-if="phase.status === 'active'" class="dot-icon pulse">●</span>
        <span v-else class="dot-icon">○</span>
      </div>

      <!-- 内容 -->
      <div class="phase-content">
        <div class="phase-header">
          <span class="phase-icon">{{ phase.icon || '⬜' }}</span>
          <span class="phase-label">{{ phase.phase_label }}</span>
          <span v-if="phase.duration_ms" class="phase-duration">
            {{ formatDuration(phase.duration_ms) }}
          </span>
          <span v-else-if="phase.status === 'active'" class="phase-running">
            运行中...
          </span>
        </div>
        <div v-if="phase.message" class="phase-message">
          {{ phase.message }}
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="!phases.length" class="phase-empty">
      <span>暂无阶段数据</span>
    </div>
  </div>
</template>

<script setup>
import { defineProps } from 'vue'

defineProps({
  phases: {
    type: Array,
    default: () => [],
  },
})

function formatDuration(ms) {
  if (!ms) return ''
  if (ms < 1000) return `${ms}ms`
  const sec = (ms / 1000).toFixed(1)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  const remainSec = (sec % 60).toFixed(0)
  return `${min}m ${remainSec}s`
}
</script>

<style scoped>
.phase-timeline {
  display: flex;
  flex-direction: column;
  padding: 8px 0;
}

.phase-node {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  position: relative;
  padding-bottom: 20px;
  animation: fadeInUp 0.3s var(--ease) forwards;
  animation-delay: var(--delay, 0ms);
  opacity: 0;
}

@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.phase-last { padding-bottom: 4px; }

/* 圆点 */
.phase-dot {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 600;
  border: 2px solid var(--phase-pending);
  background: var(--bg-card);
  transition: all var(--transition);
  z-index: 1;
}

.phase-completed .phase-dot {
  border-color: var(--phase-completed);
  background: var(--success-bg);
  color: var(--phase-completed);
}

.phase-active .phase-dot {
  border-color: var(--phase-active);
  background: rgba(59, 130, 246, 0.08);
  color: var(--phase-active);
  box-shadow: 0 0 0 4px var(--phase-glow);
}

.phase-failed .phase-dot {
  border-color: var(--phase-failed);
  background: var(--danger-bg);
  color: var(--phase-failed);
}

.phase-skipped .phase-dot {
  border-color: var(--phase-skipped);
  opacity: 0.5;
}

/* 圆点呼吸动画 */
.pulse {
  animation: breathe 2s ease-in-out infinite;
}

@keyframes breathe {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* 连接线 */
.phase-connector {
  position: absolute;
  left: 13px;
  top: 30px;
  width: 2px;
  bottom: 0;
  border-left: 2px dashed var(--phase-line);
  transition: all var(--transition);
}

.phase-connector.done {
  border-left: 2px solid var(--phase-line-done);
}

/* 内容 */
.phase-content {
  flex: 1;
  padding-top: 3px;
  min-width: 0;
}

.phase-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  line-height: 22px;
}

.phase-icon {
  font-size: 15px;
}

.phase-label {
  font-weight: 500;
  color: var(--text-primary);
}

.phase-pending .phase-label {
  color: var(--text-muted);
}

.phase-skipped .phase-label {
  color: var(--text-muted);
  text-decoration: line-through;
}

.phase-duration {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
  background: var(--bg-surface);
  padding: 1px 8px;
  border-radius: 10px;
}

.phase-running {
  margin-left: auto;
  font-size: 12px;
  color: var(--phase-active);
  animation: breathe 2s ease-in-out infinite;
}

.phase-message {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 2px;
  padding-left: 24px;
  word-break: break-word;
}

.phase-active .phase-message {
  color: var(--accent-light);
}

/* 空状态 */
.phase-empty {
  text-align: center;
  padding: 32px 16px;
  color: var(--text-muted);
  font-size: 13px;
}
</style>
