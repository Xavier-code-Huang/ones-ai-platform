<template>
  <div class="login-page" id="login-page">
    <div class="login-bg"></div>
    <!-- 装饰性网格 -->
    <div class="login-grid"></div>

    <div class="login-card scale-in" id="login-card">
      <div class="login-header">
        <div class="login-logo-wrap">
          <div class="login-logo">⚡</div>
        </div>
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
                   style="width:100%;height:48px;font-size:1rem;margin-top:8px;" id="login-submit"
                   class="login-btn click-feedback">
          {{ loading ? '验证中...' : '登 录' }}
        </el-button>
      </el-form>

      <div class="login-footer">
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
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  background: #f8fafc;
}

/* 背景装饰 — 柔和渐变光晕 */
.login-bg {
  position: absolute; inset: 0;
  background:
    radial-gradient(ellipse 60% 50% at 20% 30%, rgba(30, 64, 175, 0.06) 0%, transparent 60%),
    radial-gradient(ellipse 50% 40% at 80% 70%, rgba(13, 148, 136, 0.05) 0%, transparent 60%);
}

/* 装饰网格 — 精致感 */
.login-grid {
  position: absolute; inset: 0;
  background-image:
    linear-gradient(rgba(0, 0, 0, 0.02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 0, 0, 0.02) 1px, transparent 1px);
  background-size: 60px 60px;
  mask-image: radial-gradient(ellipse at center, black 30%, transparent 70%);
  -webkit-mask-image: radial-gradient(ellipse at center, black 30%, transparent 70%);
}

.login-card {
  position: relative;
  width: 420px;
  padding: 44px 40px;
  z-index: 1;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(20px);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.06), 0 4px 16px rgba(0, 0, 0, 0.03);
}

.login-header {
  text-align: center;
  margin-bottom: 36px;
}

.login-logo-wrap {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 56px; height: 56px;
  border-radius: 16px;
  background: var(--accent);
  color: white;
  margin-bottom: 16px;
  box-shadow: 0 4px 16px rgba(30, 64, 175, 0.2);
}
.login-logo {
  font-size: 1.8rem;
}

.login-title {
  font-size: 1.8rem;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: -0.5px;
}

.login-subtitle {
  color: var(--text-muted);
  margin-top: 6px;
  font-size: 0.9rem;
}

.login-btn {
  border-radius: 10px !important;
}

.login-footer {
  text-align: center;
  margin-top: 20px;
  color: var(--text-muted);
  font-size: 0.78rem;
}
</style>
