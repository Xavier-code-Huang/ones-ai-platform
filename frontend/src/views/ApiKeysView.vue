<template>
  <div class="page-container" id="api-keys-page">
    <div class="page-header fade-in-up">
      <h1>API 密钥管理</h1>
      <p>管理你的 AI 引擎 API Key</p>
    </div>

    <div style="margin-bottom: 24px;" class="fade-in-up">
      <el-button type="primary" round @click="openAddDialog">
        <el-icon><Plus /></el-icon> 添加密钥
      </el-button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="empty-state fade-in-up">
      <p>加载中...</p>
    </div>

    <!-- Key 列表按 Provider 分组 -->
    <template v-if="!loading">
      <div v-for="provider in providerOrder" :key="provider" class="fade-in-up" style="margin-bottom: 28px;">
        <template v-if="groupedKeys[provider] && groupedKeys[provider].length > 0">
          <div class="section-title">
            <span class="section-icon">{{ providerIcon(provider) }}</span>
            {{ providerLabel(provider) }}
          </div>
          <div class="key-list">
            <div v-for="k in groupedKeys[provider]" :key="k.id" class="key-item glass-card">
              <div class="key-info">
                <span v-if="k.is_default" class="key-default-star">★</span>
                <span class="key-label">{{ k.label || '未命名' }}</span>
                <span class="key-preview">{{ k.key_preview }}</span>
                <el-tag v-if="k.is_default" size="small" type="success" effect="plain">默认</el-tag>
              </div>
              <div class="key-actions">
                <el-button v-if="!k.is_default" size="small" plain round @click="setDefault(k)">
                  设为默认
                </el-button>
                <el-button size="small" type="danger" plain round @click="confirmDelete(k)">
                  删除
                </el-button>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- 无 Key 时的空状态 -->
      <div v-if="allKeys.length === 0" class="empty-state fade-in-up">
        <div class="empty-icon">🔑</div>
        <p>暂无 API 密钥</p>
        <span>点击上方按钮添加你的第一个 API Key</span>
      </div>

      <!-- GLM 提示 -->
      <div class="glm-notice glass-card fade-in-up">
        <el-icon style="color: var(--accent-light); font-size: 1.1rem;"><InfoFilled /></el-icon>
        <span>GLM 引擎使用系统网关自动分配的 Key，无需配置</span>
      </div>
    </template>

    <!-- 添加 Key 对话框 -->
    <el-dialog v-model="addDialogVisible" title="添加 API 密钥" width="500px" :close-on-click-modal="false">
      <el-form :model="addForm" label-width="90px" label-position="left">
        <el-form-item label="Provider">
          <el-select v-model="addForm.provider" placeholder="选择 Provider" style="width: 100%;">
            <el-option label="Anthropic" value="anthropic" />
            <el-option label="OpenAI" value="openai" />
          </el-select>
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="addForm.api_key" placeholder="输入 API Key" show-password />
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="addForm.label" placeholder="可选，如：个人 Key、团队共享" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialogVisible = false" round>取消</el-button>
        <el-button plain round :loading="validating" @click="doValidate" :disabled="!addForm.api_key || !addForm.provider">
          验证有效性
        </el-button>
        <el-button type="primary" round :loading="submitting" @click="doAdd" :disabled="!addForm.api_key || !addForm.provider">
          添加
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const loading = ref(false)
const allKeys = ref([])
const addDialogVisible = ref(false)
const submitting = ref(false)
const validating = ref(false)

const addForm = ref({
  provider: 'anthropic',
  api_key: '',
  label: ''
})

const providerOrder = ['anthropic', 'openai']

const groupedKeys = computed(() => {
  const groups = {}
  for (const p of providerOrder) {
    groups[p] = allKeys.value.filter(k => k.provider === p)
  }
  return groups
})

function providerLabel(p) {
  return { anthropic: 'Anthropic', openai: 'OpenAI' }[p] || p
}

function providerIcon(p) {
  return { anthropic: '🟠', openai: '🟢' }[p] || '🔑'
}

async function loadKeys() {
  loading.value = true
  try {
    allKeys.value = await api.listUserKeys()
  } catch (e) {
    ElMessage.error('加载密钥列表失败')
  } finally {
    loading.value = false
  }
}

function openAddDialog() {
  addForm.value = { provider: 'anthropic', api_key: '', label: '' }
  addDialogVisible.value = true
}

async function doAdd() {
  submitting.value = true
  try {
    await api.addUserKey({
      provider: addForm.value.provider,
      api_key: addForm.value.api_key,
      label: addForm.value.label
    })
    ElMessage.success('密钥添加成功')
    addDialogVisible.value = false
    await loadKeys()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '添加失败')
  } finally {
    submitting.value = false
  }
}

async function doValidate() {
  // 先验证 Key 有效性（不入库），通过后再添加
  validating.value = true
  try {
    const result = await api.validateUserKeyDirect({
      provider: addForm.value.provider,
      api_key: addForm.value.api_key,
    })
    if (result.valid) {
      // 验证通过，添加 Key
      await api.addUserKey({
        provider: addForm.value.provider,
        api_key: addForm.value.api_key,
        label: addForm.value.label,
      })
      ElMessage.success('✅ 密钥验证通过，已添加')
      addDialogVisible.value = false
      await loadKeys()
    } else {
      ElMessage.error(result.message || '密钥验证失败，请检查 Key 是否正确')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '验证请求失败')
  } finally {
    validating.value = false
  }
}

async function setDefault(key) {
  try {
    await api.updateUserKey(key.id, { is_default: true })
    ElMessage.success('已设为默认')
    await loadKeys()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

async function confirmDelete(key) {
  try {
    await ElMessageBox.confirm(
      `确定删除密钥「${key.label || key.key_preview}」？此操作不可撤销。`,
      '删除确认',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
    await api.deleteUserKey(key.id)
    ElMessage.success('密钥已删除')
    await loadKeys()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(e.response?.data?.detail || '删除失败')
    }
  }
}

onMounted(loadKeys)
</script>

<style scoped>
.page-header h1 {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
}
.page-header p {
  color: var(--text-secondary);
  margin-top: 6px;
  font-size: 0.9rem;
}
.page-header {
  margin-bottom: 24px;
}

.section-title {
  font-size: 1.1rem;
  font-weight: 700;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-primary);
}
.section-icon { font-size: 1rem; }

.key-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.key-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 20px !important;
}

.key-info {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.key-default-star {
  color: var(--warning);
  font-size: 1rem;
}

.key-label {
  font-weight: 600;
  font-size: 0.95rem;
  color: var(--text-primary);
}

.key-preview {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  color: var(--text-muted);
}

.key-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.glm-notice {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 20px !important;
  font-size: 0.88rem;
  color: var(--text-secondary);
  margin-top: 16px;
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-muted);
}
.empty-icon { font-size: 3rem; margin-bottom: 12px; opacity: 0.6; }
.empty-state p { font-size: 1rem; color: var(--text-secondary); margin-bottom: 4px; }
.empty-state span { font-size: 0.85rem; }
</style>
