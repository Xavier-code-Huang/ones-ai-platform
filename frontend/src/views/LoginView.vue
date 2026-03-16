<template>
  <div class="login-page" id="login-page">
    <div class="login-bg"></div>
    <div class="login-card glass-card fade-in-up" id="login-card">
      <div class="login-header">
        <div class="login-logo">🤖</div>
        <h1 class="login-title">ones-AI</h1>
        <p class="login-subtitle">智能工单处理平台</p>
      </div>

      <el-form @submit.prevent="handleLogin" :model="form" :rules="rules" ref="formRef">
        <el-form-item prop="email">
          <el-input v-model="form.email" placeholder="ONES 邮箱" size="large" prefix-icon="Message" id="login-email" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" size="large"
                    prefix-icon="Lock" show-password @keyup.enter="handleLogin" id="login-password" />
        </el-form-item>
        <el-button type="primary" size="large" :loading="loading" @click="handleLogin"
                   style="width:100%;height:48px;font-size:1rem;margin-top:8px;" id="login-submit">
          {{ loading ? '验证中...' : '登 录' }}
        </el-button>
      </el-form>

      <div style="text-align:center;margin-top:16px;color:var(--text-muted);font-size:0.8rem;">
        使用 ONES 系统账号（企业微信邮箱 + 密码）登录
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { ElMessage } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()
const formRef = ref(null)
const loading = ref(false)

const form = reactive({ email: '', password: '' })
const rules = {
  email: [{ required: true, message: '请输入邮箱', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  try {
    await formRef.value?.validate()
  } catch { return }

  loading.value = true
  try {
    await authStore.login(form.email, form.password)
    ElMessage.success('登录成功')
    router.push('/')
  } catch (err) {
    const msg = err.response?.data?.detail || '登录失败，请检查账号密码'
    ElMessage.error(msg)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page { min-height:100vh; display:flex; align-items:center; justify-content:center; position:relative; overflow:hidden; }
.login-bg { position:absolute; inset:0; background: radial-gradient(ellipse at 30% 20%, rgba(99,102,241,0.15) 0%, transparent 50%),
  radial-gradient(ellipse at 70% 80%, rgba(139,92,246,0.1) 0%, transparent 50%), var(--bg-primary); }
.login-card { position:relative; width:420px; padding:40px; z-index:1; }
.login-header { text-align:center; margin-bottom:32px; }
.login-logo { font-size:3rem; margin-bottom:8px; }
.login-title { font-size:2rem; font-weight:700; background:var(--accent-gradient); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.login-subtitle { color:var(--text-secondary); margin-top:4px; font-size:0.9rem; }
</style>
