<template>
  <div class="page-container" id="admin-configs">
    <h1 class="fade-in-up" style="font-size:1.6rem;font-weight:700;margin-bottom:8px;">外部服务配置</h1>
    <p style="color:var(--text-secondary);margin-bottom:24px;">配置 ONES、Gerrit、企业微信等外部服务的连接信息</p>

    <!-- ONES 配置 -->
    <div class="glass-card fade-in-up" style="margin-bottom:16px;">
      <h3 style="margin-bottom:16px;">📋 ONES 系统</h3>
      <el-form label-width="140px">
        <el-form-item label="API 网关地址"><el-input v-model="configs.ones_api_gateway" /></el-form-item>
        <el-form-item label="原生 API 地址"><el-input v-model="configs.ones_api_base_url" /></el-form-item>
      </el-form>
    </div>

    <!-- Gerrit 配置 -->
    <div class="glass-card fade-in-up" style="margin-bottom:16px;" v-for="i in [1,2,3]" :key="'gerrit-'+i">
      <h3 style="margin-bottom:16px;">🔧 Gerrit 实例 {{ i }}</h3>
      <el-form label-width="140px">
        <el-form-item label="地址"><el-input v-model="configs['gerrit_host_'+i]" :placeholder="'__GERRIT_HOST_'+i+'__'" /></el-form-item>
        <el-form-item label="HTTP Token"><el-input v-model="configs['gerrit_token_'+i]" type="password" show-password /></el-form-item>
        <el-form-item label="账号"><el-input v-model="configs['gerrit_user_'+i]" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="configs['gerrit_pass_'+i]" type="password" show-password /></el-form-item>
      </el-form>
    </div>

    <!-- 企微配置 -->
    <div class="glass-card fade-in-up" style="margin-bottom:16px;">
      <h3 style="margin-bottom:16px;">💬 企业微信</h3>
      <el-form label-width="140px">
        <el-form-item label="Corp ID"><el-input v-model="configs.wecom_corp_id" /></el-form-item>
        <el-form-item label="Agent ID"><el-input v-model="configs.wecom_agent_id" /></el-form-item>
        <el-form-item label="Secret"><el-input v-model="configs.wecom_secret" type="password" show-password /></el-form-item>
        <el-form-item label="Webhook URL"><el-input v-model="configs.wecom_webhook_url" /></el-form-item>
      </el-form>
    </div>

    <el-button type="primary" :loading="saving" @click="save" style="margin-top:8px;" id="save-configs">
      <el-icon><Check /></el-icon> 保存配置
    </el-button>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import api from '../api'
import { ElMessage } from 'element-plus'

const configs = reactive({})
const saving = ref(false)

onMounted(async () => {
  const list = await api.getConfigs()
  list.forEach(c => { configs[c.config_key] = c.config_value })
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
