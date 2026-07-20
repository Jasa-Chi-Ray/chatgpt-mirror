<template>
  <div>
    <div v-if="!tableVisible" class="login-chatgpt-state">
      <t-loading :loading="tableLoading" size="medium">
        <div class="login-chatgpt-card">
          <div class="login-chatgpt-title">正在准备 ChatGPT 会话</div>
          <div class="login-chatgpt-desc">{{ statusText }}</div>
        </div>
      </t-loading>
    </div>
    <t-dialog
      :visible="tableVisible"
      header="请选择 ChatGPT 账号"
      :cancel-btn="null"
      :confirm-btn="null"
      :on-close="onClose"
      width="930px"
    >
      <t-loading :loading="tableLoading">
        <t-space direction="vertical" style="width: 100%; margin-bottom: 16px" :size="12">
          <div class="mode-switch">
            <span class="mode-switch__label">登录模式</span>
            <t-radio-group v-model="selectedMode" variant="default-filled">
              <t-radio-button value="api">API 模式</t-radio-button>
              <t-radio-button value="web">混合模式</t-radio-button>
            </t-radio-group>
          </div>
          <t-alert
            v-if="selectedMode === 'api'"
            theme="info"
            message="API 模式默认优先使用 AccessToken，可保证接口能力，但不承诺官方网页完整登录态。"
          />
          <t-alert
            v-else
            theme="warning"
            message="混合模式会同时传入 AccessToken 与 SessionToken，优先建立网页态，同时保留 AccessToken 供接口链路回退。"
          />
        </t-space>
        <t-space break-line>
          <div
            v-for="item in tableData"
            :key="item.id"
            style="width: 160px; cursor: pointer"
            :class="{ 'is-disabled': !item.auth_status || !supportsMode(item, selectedMode) }"
            @click="onSelect(item.id)"
          >
            <div style="background: #f2f4f7; padding: 8px; border-radius: 5px">
              <t-space direction="vertical" style="width: 100%" :size="8">
                <div>
                  <div style="display: flex; justify-content: space-between">
                    <t-tag
                      size="small"
                      theme="primary"
                      variant="outline"
                      style="width: 35px"
                      :class="{ 'shiny-blue': item.plan_type !== 'free' }"
                    >{{ item.plan_type }}</t-tag>
                    <span>{{ item.chatgpt_flag }}</span>
                  </div>
                </div>

                <div class="mode-tags">
                  <t-tag size="small" :theme="item.access_token_valid ? 'success' : 'default'">
                    API
                  </t-tag>
                  <t-tag size="small" :theme="item.session_token_valid ? 'success' : 'default'">
                    混合
                  </t-tag>
                </div>

                <div style="font-size: 12px; display: flex; justify-content: space-between">
                  <div>实时状态</div>
                  <div>
                    <span v-if="item.auth_status === false">已过期</span>
                    <span v-else-if="getGPTUsePercent(item) < 40">空闲</span>
                    <span v-else-if="getGPTUsePercent(item) < 80">忙碌</span>
                    <span v-else>繁忙 | 可用</span>
                  </div>
                </div>

                <div>
                  <t-progress
                    v-if="getGPTUsePercent(item) < 40"
                    :percentage="getGPTUsePercent(item)"
                    status="success"
                    :label="false"
                  />
                  <t-progress
                    v-else-if="getGPTUsePercent(item) < 80"
                    :percentage="getGPTUsePercent(item)"
                    status="warning"
                    :label="false"
                  />
                  <t-progress v-else :percentage="getGPTUsePercent(item)" status="error" :label="false" />
                </div>
              </t-space>
            </div>
          </div>
        </t-space>
      </t-loading>
    </t-dialog>
  </div>
</template>

<script setup lang="ts">
import { MessagePlugin } from 'tdesign-vue-next'
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import request from '@/api/request'
import { useUserStore } from '@/store/user'

const tableLoading = ref(false)
const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const tableVisible = ref(false)
const statusText = ref('正在加载可用账号...')

interface TableData {
  id: number
  chatgpt_flag: string
  plan_type: string
  auth_status: boolean
  use_count: number
  access_token_valid: boolean
  session_token_valid: boolean
  supported_login_modes: string[]
  default_login_mode: 'api' | 'web'
}
const tableData = ref<TableData[]>([])
const selectedMode = ref<'api' | 'web'>('api')
const preferredMode = ref<'api' | 'web'>('api')

onMounted(async () => {
  if (route.query.logout === '1') {
    userStore.logout()
  }
  preferredMode.value = route.query.mode === 'web' ? 'web' : 'api'
  selectedMode.value = preferredMode.value
  await getUserChatGPTAccountList()
})

const getGPTUsePercent = (item: TableData) => {
  const MaxLimitCount = item.plan_type === 'free' ? 20 : 80
  return Math.min((item.use_count / MaxLimitCount) * 100 + 1, 99)
}

const getUserChatGPTAccountList = async () => {
  tableLoading.value = true
  statusText.value = '正在加载可用账号...'
  const data = await request('/0x/user/chatgpt-list')
  tableLoading.value = false
  
  if (!data) {
    router.push({ name: 'Login' })
    return
  }
  
  const results = data.results || []
  tableData.value = results

  if (results.length > 0 && !results.some((item: TableData) => supportsMode(item, selectedMode.value))) {
    const fallbackMode = selectedMode.value === 'web' ? 'api' : 'web'
    if (results.some((item: TableData) => supportsMode(item, fallbackMode))) {
      selectedMode.value = fallbackMode
      MessagePlugin.info(
        fallbackMode === 'api'
          ? '当前没有支持混合模式的账号，已切换到 API 模式'
          : '当前没有支持 API 模式的账号，已切换到混合模式',
      )
    }
  }
  
  if (results.length === 0) {
    MessagePlugin.warning('暂无可用的 ChatGPT 账号，请联系管理员添加')
    statusText.value = '暂无可用的 ChatGPT 账号，请联系管理员添加'
  } else {
    if (results.length === 1 && results[0].auth_status && !supportsMode(results[0], selectedMode.value)) {
      if (supportsMode(results[0], 'api')) {
        selectedMode.value = 'api'
        statusText.value = '该账号当前不支持混合模式，已切回 API 模式，请确认登录'
      } else if (supportsMode(results[0], 'web')) {
        selectedMode.value = 'web'
        statusText.value = '该账号当前仅支持混合模式，请确认登录'
      }
    }
    tableVisible.value = true
  }
}

const onClose = () => {
  router.push({ name: 'Login' })
}

const supportsMode = (item: TableData, mode: 'api' | 'web') => {
  return Array.isArray(item.supported_login_modes) && item.supported_login_modes.includes(mode)
}

const onSelect = async (chatgptId: number) => {
  const current = tableData.value.find(item => item.id === chatgptId)
  if (current && !supportsMode(current, selectedMode.value)) {
    MessagePlugin.warning(
      selectedMode.value === 'api'
        ? '该账号当前不支持 API 模式，请切换到混合模式或联系管理员更新 AccessToken'
        : '该账号当前不支持混合模式，请切换到 API 模式或联系管理员补录 SessionToken',
    )
    return
  }

  tableLoading.value = true
  statusText.value =
    selectedMode.value === 'api'
      ? '正在以 API 模式登录 ChatGPT，请稍候...'
      : '正在以混合模式登录 ChatGPT，请稍候...'
  const data = await request('/0x/chatgpt/login', 'POST', {
    chatgpt_id: chatgptId,
    login_mode: selectedMode.value,
  })
  tableLoading.value = false
  
  if (data) {
    MessagePlugin.success('登录成功')
    if (data.login_url) {
      window.location.replace(data.login_url)
      return
    }
  }

  if (!tableVisible.value) {
    statusText.value = '登录失败，请返回重试'
  }
}
</script>

<style scoped>
.login-chatgpt-state {
  min-height: 70vh;
  display: flex;
  align-items: center;
  justify-content: center;
}

.login-chatgpt-card {
  min-width: 320px;
  padding: 24px 28px;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 12px 40px rgba(15, 23, 42, 0.08);
  text-align: center;
}

.login-chatgpt-title {
  font-size: 20px;
  font-weight: 600;
  color: #111827;
}

.login-chatgpt-desc {
  margin-top: 10px;
  color: #6b7280;
  font-size: 14px;
}

.mode-switch {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.mode-switch__label {
  color: #111827;
  font-size: 14px;
  font-weight: 600;
}

.mode-tags {
  display: flex;
  gap: 6px;
}

.is-disabled {
  opacity: 0.5;
  pointer-events: none;
}

.shiny-blue {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
}
</style>
