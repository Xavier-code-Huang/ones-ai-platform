<template>
  <div class="code-path-select">
    <el-select
      v-model="selectedPath"
      filterable
      allow-create
      default-first-option
      clearable
      placeholder="输入或选择代码路径"
      class="path-select"
      @change="handleChange"
    >
      <el-option
        v-for="item in paths"
        :key="item.id"
        :label="item.path"
        :value="item.path"
      >
        <div class="path-option">
          <span class="path-text">{{ item.path }}</span>
          <span class="path-count">{{ item.use_count }}次</span>
          <el-icon class="path-delete" @click.stop="handleDelete(item.id)">
            <Close />
          </el-icon>
        </div>
      </el-option>
    </el-select>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, defineProps, defineEmits } from 'vue'
import { Close } from '@element-plus/icons-vue'
import api from '../api'

const props = defineProps({
  modelValue: { type: String, default: '' },
  serverId: { type: Number, default: 0 },
})

const emit = defineEmits(['update:modelValue'])

const selectedPath = ref(props.modelValue)
const paths = ref([])

watch(() => props.modelValue, (val) => { selectedPath.value = val })
watch(() => props.serverId, () => { loadPaths() }, { immediate: true })

function handleChange(val) {
  emit('update:modelValue', val || '')
}

async function loadPaths() {
  if (!props.serverId) { paths.value = []; return }
  try {
    const res = await api.getCodePaths(props.serverId)
    paths.value = Array.isArray(res) ? res : (res?.paths || [])
  } catch (e) {
    paths.value = []
  }
}

async function handleDelete(pathId) {
  try {
    await api.deleteCodePath(pathId)
    paths.value = paths.value.filter(p => p.id !== pathId)
  } catch (e) {
    console.error('删除路径失败', e)
  }
}

// onMounted 不再需要，由 watch immediate 处理
</script>

<style scoped>
.code-path-select {
  width: 100%;
}

.path-select {
  width: 100%;
}

.path-option {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.path-text {
  flex: 1;
  font-family: var(--font-mono);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.path-count {
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
}

.path-delete {
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s;
}

.path-option:hover .path-delete { opacity: 1; }
.path-delete:hover { color: var(--danger); }
</style>
