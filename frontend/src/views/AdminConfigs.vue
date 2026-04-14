<template>
  <div class="page-container" id="admin-configs">
    <div class="page-header fade-in-up">
      <h1>外部服务配置</h1>
      <p>配置 ONES、Gerrit、企业微信等外部服务的连接信息</p>
    </div>

    <!-- ONES 配置 -->
    <div class="config-group glass-card fade-in-up">
      <div class="config-group-header">
        <span class="config-group-icon" style="background:var(--info-bg);color:var(--info);">📋</span>
        <div>
          <h3>ONES 系统</h3>
          <span class="config-group-desc">工单管理系统接口配置</span>
        </div>
      </div>
      <el-form label-width="140px">
        <el-form-item label="API 网关地址"><el-input v-model="configs.ones_api_gateway" /></el-form-item>
        <el-form-item label="原生 API 地址"><el-input v-model="configs.ones_api_base_url" /></el-form-item>
      </el-form>
    </div>

    <!-- Gerrit 配置 -->
    <div class="config-group glass-card fade-in-up" v-for="i in [1,2,3]" :key="'gerrit-'+i"
         :style="{ animationDelay: (i * 0.06) + 's' }">
      <div class="config-group-header">
        <span class="config-group-icon" style="background:var(--teal-bg);color:var(--teal);">🔧</span>
        <div>
          <h3>Gerrit 实例 {{ i }}</h3>
          <span class="config-group-desc">代码审查服务 #{{ i }} 连接信息</span>
        </div>
      </div>
      <el-form label-width="140px">
        <el-form-item label="地址"><el-input v-model="configs['gerrit_host_'+i]" :placeholder="'__GERRIT_HOST_'+i+'__'" /></el-form-item>
        <el-form-item label="HTTP Token"><el-input v-model="configs['gerrit_token_'+i]" type="password" show-password /></el-form-item>
        <el-form-item label="账号"><el-input v-model="configs['gerrit_user_'+i]" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="configs['gerrit_pass_'+i]" type="password" show-password /></el-form-item>
      </el-form>
    </div>

    <!-- 企微配置 -->
    <div class="config-group glass-card fade-in-up">
      <div class="config-group-header">
        <span class="config-group-icon" style="background:var(--success-bg);color:var(--success);">💬</span>
        <div>
          <h3>企业微信</h3>
          <span class="config-group-desc">企微应用和机器人通知配置</span>
        </div>
      </div>
      <el-form label-width="140px">
        <el-form-item label="Corp ID"><el-input v-model="configs.wecom_corp_id" /></el-form-item>
        <el-form-item label="Agent ID"><el-input v-model="configs.wecom_agent_id" /></el-form-item>
        <el-form-item label="Secret"><el-input v-model="configs.wecom_secret" type="password" show-password /></el-form-item>
        <el-form-item label="Webhook URL"><el-input v-model="configs.wecom_webhook_url" placeholder="群机器人 Webhook 地址" /></el-form-item>
      </el-form>
    </div>

    <!-- 通知开关 -->
    <div class="config-group glass-card fade-in-up">
      <div class="config-group-header">
        <span class="config-group-icon" style="background:var(--warning-bg);color:var(--warning);">🔔</span>
        <div>
          <h3>通知设置</h3>
          <span class="config-group-desc">任务完成后的通知方式控制</span>
        </div>
      </div>
      <el-form label-width="140px">
        <el-form-item label="Webhook 通知">
          <el-switch v-model="webhookEnabled" active-text="启用" inactive-text="关闭"
                     @change="v => configs.notify_webhook_enabled = v ? 'true' : 'false'" />
          <span class="switch-hint">任务完成后向企微群发送摘要通知</span>
        </el-form-item>
        <el-form-item label="邮件通知">
          <el-switch v-model="emailEnabled" active-text="启用" inactive-text="关闭"
                     @change="v => configs.notify_email_enabled = v ? 'true' : 'false'" />
          <span class="switch-hint">任务完成后向提交人邮箱发送完整报告</span>
        </el-form-item>
      </el-form>
    </div>

    <!-- 功能开关 -->
    <div class="config-group glass-card fade-in-up">
      <div class="config-group-header">
        <span class="config-group-icon" style="background:linear-gradient(135deg, rgba(99,102,241,0.15), rgba(168,85,247,0.15));color:#7c3aed;">🤖</span>
        <div>
          <h3>功能开关</h3>
          <span class="config-group-desc">平台功能模块的启用/禁用控制</span>
        </div>
      </div>
      <el-form label-width="140px">
        <el-form-item label="多引擎支持">
          <el-switch v-model="multiEngineEnabled" active-text="启用" inactive-text="关闭"
                     @change="v => configs.multi_engine_enabled = v ? 'true' : 'false'" />
          <span class="switch-hint">允许用户使用 Anthropic / OpenAI 引擎（需用户自行配置 API Key）</span>
        </el-form-item>
      </el-form>
    </div>

    <!-- SMTP 邮件服务器 -->
    <div class="config-group glass-card fade-in-up" v-if="emailEnabled">
      <div class="config-group-header">
        <span class="config-group-icon" style="background:var(--accent-bg);color:var(--accent);">📧</span>
        <div>
          <h3>SMTP 邮件服务器</h3>
          <span class="config-group-desc">邮件通知发送的 SMTP 服务配置</span>
        </div>
      </div>
      <el-form label-width="140px">
        <el-form-item label="SMTP 服务器"><el-input v-model="configs.smtp_host" placeholder="如 smtp.exmail.qq.com" /></el-form-item>
        <el-form-item label="端口"><el-input v-model="configs.smtp_port" placeholder="465 (SSL) 或 587 (TLS)" /></el-form-item>
        <el-form-item label="发件邮箱"><el-input v-model="configs.smtp_user" placeholder="xxx@lango-tech.cn" /></el-form-item>
        <el-form-item label="授权密码"><el-input v-model="configs.smtp_pass" type="password" show-password /></el-form-item>
        <el-form-item label="发件人显示名"><el-input v-model="configs.smtp_from_name" placeholder="ones-AI" /></el-form-item>
      </el-form>
    </div>

    <!-- 保存按钮 -->
    <div class="save-bar fade-in-up">
      <el-button type="primary" :loading="saving" @click="save" size="large" id="save-configs">
        <el-icon><Check /></el-icon> 保存配置
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import api from '../api'
import { ElMessage } from 'element-plus'

const configs = reactive({})
const saving = ref(false)
const webhookEnabled = ref(false)
const emailEnabled = ref(false)
const multiEngineEnabled = ref(false)

onMounted(async () => {
  const list = await api.getConfigs()
  list.forEach(c => { configs[c.config_key] = c.config_value })
  webhookEnabled.value = configs.notify_webhook_enabled === 'true'
  emailEnabled.value = configs.notify_email_enabled === 'true'
  multiEngineEnabled.value = configs.multi_engine_enabled === 'true'
})

async function save() {
  saving.value = true
  try {
    const entries = Object.entries(configs).map(([k, v]) => ({
      config_key: k,
      config_value: v,
      is_encrypted: k.includes('token') || k.includes('pass') || k.includes('secret'),
      description: '',
    }))
    await api.updateConfigs(entries)
    ElMessage.success('配置已保存')
  } catch (err) { ElMessage.error('保存失败') }
  finally { saving.value = false }
}
</script>

<style scoped>
.config-group {
  margin-bottom: 16px;
}
.config-group-header {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
}
.config-group-header h3 {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.config-group-icon {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.2rem;
  flex-shrink: 0;
}
.config-group-desc {
  font-size: 0.8rem;
  color: var(--text-muted);
  margin-top: 2px;
  display: block;
}
.switch-hint {
  color: var(--text-muted);
  font-size: 0.78rem;
  margin-left: 12px;
}
.save-bar {
  margin-top: 8px;
  padding-top: 20px;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: flex-end;
}
</style>
