<template>
  <div class="code-path-select">
    <el-autocomplete
      v-model="inputValue"
      :fetch-suggestions="querySearch"
      placeholder="输入或选择代码路径"
      clearable
      :trigger-on-focus="true"
      highlight-first-item
      class="path-autocomplete"
      @select="handleSelect"
      @change="handleInput"
      @clear="handleClear"
    >
      <template #default="{ item }">
        <div class="path-option">
          <span class="path-text">{{ item.path }}</span>
          <span class="path-count">{{ item.use_count }}次</span>
          <el-icon class="path-delete" @click.stop="handleDelete(item.id)">
            <Close />
          </el-icon>
        </div>
      </template>
    </el-autocomplete>
  </div>
</template>

<script setup>
import { ref, watch, defineProps, defineEmits } from 'vue'
import { Close } from '@element-plus/icons-vue'
import api from '../api'

const props = defineProps({
  modelValue: { type: String, default: '' },
  serverId: { type: Number, default: 0 },
})

const emit = defineEmits(['update:modelValue'])

const inputValue = ref(props.modelValue)
const allPaths = ref([])

// 同步外部传入的 modelValue
watch(() => props.modelValue, (val) => { inputValue.value = val })

// serverId 变化时重新加载
watch(() => props.serverId, () => { loadPaths() }, { immediate: true })

// 内部输入变化时向外同步
function handleInput(val) {
  emit('update:modelValue', val || '')
}

function handleSelect(item) {
  inputValue.value = item.path
  emit('update:modelValue', item.path)
}

function handleClear() {
  emit('update:modelValue', '')
}

// autocomplete 搜索建议：聚焦时（queryString为空）显示全部，输入时过滤
function querySearch(queryString, cb) {
  const results = queryString
    ? allPaths.value.filter(p =>
        p.path.toLowerCase().includes(queryString.toLowerCase())
      ).map(p => ({ ...p, value: p.path }))
    : allPaths.value.map(p => ({ ...p, value: p.path }))
  cb(results)
}

async function loadPaths() {
  if (!props.serverId) { allPaths.value = []; return }
  try {
    const res = await api.getCodePaths(props.serverId)
    const list = Array.isArray(res) ? res : (res?.paths || [])
    allPaths.value = list.map(item => ({
      ...item,
      value: item.path,   // el-autocomplete 需要 value 字段
    }))
  } catch (e) {
    allPaths.value = []
  }
}

async function handleDelete(pathId) {
  try {
    await api.deleteCodePath(pathId)
    allPaths.value = allPaths.value.filter(p => p.id !== pathId)
  } catch (e) {
    console.error('删除路径失败', e)
  }
}
</script>

<style scoped>
.code-path-select {
  width: 100%;
}

.path-autocomplete {
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
