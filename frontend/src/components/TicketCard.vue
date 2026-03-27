<template>
  <div
    class="ticket-card"
    :class="[`ticket-${status}`, { active: isActive }]"
    @click="$emit('select', ticketDbId)"
  >
    <div class="ticket-header">
      <div class="ticket-status-dot" />
      <span class="ticket-id">{{ ticketId }}</span>
      <span class="ticket-badge" :class="`badge-${status}`">
        {{ statusText }}
      </span>
    </div>

    <!-- 摘要/结论 -->
    <div v-if="conclusion" class="ticket-conclusion">{{ conclusion }}</div>
    <div v-else-if="status === 'running'" class="ticket-conclusion running">处理中...</div>
    <div v-else-if="status === 'pending'" class="ticket-conclusion pending">排队中</div>

    <!-- 编辑按钮 (仅 pending) -->
    <button
      v-if="status === 'pending'"
      class="ticket-edit-btn"
      @click.stop="$emit('edit', ticketDbId)"
    >
      ✏️ 编辑
    </button>

    <!-- 耗时 -->
    <div v-if="duration > 0" class="ticket-duration">
      耗时 {{ duration.toFixed(1) }}s
    </div>
  </div>
</template>

<script setup>
import { computed, defineProps, defineEmits } from 'vue'

const props = defineProps({
  ticketId: { type: String, required: true },
  ticketDbId: { type: Number, required: true },
  status: { type: String, default: 'pending' },
  conclusion: { type: String, default: '' },
  duration: { type: Number, default: 0 },
  isActive: { type: Boolean, default: false },
})

defineEmits(['select', 'edit'])

const statusText = computed(() => {
  const map = {
    pending: '排队',
    running: '执行中',
    completed: '完成 ✅',
    failed: '失败 ❌',
  }
  return map[props.status] || props.status
})
</script>

<style scoped>
.ticket-card {
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg-card);
  cursor: pointer;
  transition: all var(--transition);
  position: relative;
}

.ticket-card:hover {
  border-color: var(--border-hover);
  background: var(--bg-card-hover);
}

.ticket-card.active {
  border-color: var(--accent-light);
  background: var(--accent-bg);
  box-shadow: 0 0 0 2px var(--phase-glow);
}

.ticket-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ticket-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.ticket-pending .ticket-status-dot { background: var(--text-muted); }
.ticket-running .ticket-status-dot { background: var(--phase-active); animation: breathe 2s ease-in-out infinite; }
.ticket-completed .ticket-status-dot { background: var(--success); }
.ticket-failed .ticket-status-dot { background: var(--danger); }

@keyframes breathe {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.ticket-id {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
  font-family: var(--font-mono);
}

.ticket-badge {
  margin-left: auto;
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 10px;
  font-weight: 500;
}

.badge-pending { background: var(--bg-surface); color: var(--text-muted); }
.badge-running { background: rgba(59, 130, 246, 0.1); color: var(--accent-light); }
.badge-completed { background: var(--success-bg); color: var(--success); }
.badge-failed { background: var(--danger-bg); color: var(--danger); }

.ticket-conclusion {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 6px;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ticket-conclusion.running { color: var(--accent-light); }
.ticket-conclusion.pending { color: var(--text-muted); }

.ticket-edit-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition);
  opacity: 0;
}

.ticket-card:hover .ticket-edit-btn { opacity: 1; }
.ticket-edit-btn:hover {
  border-color: var(--accent-light);
  color: var(--accent-light);
}

.ticket-duration {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
  font-family: var(--font-mono);
}
</style>
