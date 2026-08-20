<template>
  <div>
    <div v-if="!tableVisible && !announcementVisible" class="login-chatgpt-state">
      <t-loading :loading="tableLoading" size="medium">
        <div class="login-chatgpt-card">
          <div class="login-chatgpt-title">正在准备 ChatGPT 会话</div>
          <div class="login-chatgpt-desc">{{ statusText }}</div>
        </div>
      </t-loading>
    </div>
    <t-dialog
      :visible="announcementVisible"
      header="登录公告"
      :cancel-btn="null"
      :close-btn="false"
      :close-on-overlay-click="false"
      :confirm-btn="{ content: '继续选择账号', loading: tableLoading }"
      width="760px"
      @confirm="continueToAccountSelection"
    >
      <div class="announcement-intro">请阅读管理员发布的公告，确认后继续选择 ChatGPT 账号。</div>
      <t-tabs v-model="activeAnnouncementTab" class="announcement-tabs">
        <t-tab-panel
          v-if="announcements.global.length"
          value="global"
          :label="`全局公告 (${announcements.global.length})`"
        >
          <div class="announcement-list">
            <article v-for="item in announcements.global" :key="item.id" class="announcement-item">
              <div class="announcement-heading">
                <h2>{{ item.title }}</h2>
                <time>{{ formatAnnouncementSchedule(item) }}</time>
              </div>
              <MarkdownContent class="announcement-content" :content="item.content" />
            </article>
          </div>
        </t-tab-panel>
        <t-tab-panel
          v-if="announcements.personal.length"
          value="personal"
          :label="`给你的公告 (${announcements.personal.length})`"
        >
          <div class="announcement-list">
            <article v-for="item in announcements.personal" :key="item.id" class="announcement-item">
              <div class="announcement-heading">
                <h2>{{ item.title }}</h2>
                <time>{{ formatAnnouncementSchedule(item) }}</time>
              </div>
              <MarkdownContent class="announcement-content" :content="item.content" />
            </article>
          </div>
        </t-tab-panel>
        <t-tab-panel
          v-if="announcements.history.length"
          value="history"
          :label="`历史公告 (${announcements.history.length})`"
        >
          <div class="announcement-list">
            <article v-for="item in announcements.history" :key="item.id" class="announcement-item announcement-item--history">
              <div class="announcement-heading">
                <h2>{{ item.title }}</h2>
                <time>{{ formatAnnouncementSchedule(item) }}</time>
              </div>
              <MarkdownContent class="announcement-content" :content="item.content" />
            </article>
          </div>
        </t-tab-panel>
      </t-tabs>
    </t-dialog>
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
          <t-alert
            theme="warning"
            message="管理员有权记录您的对话数量及模型消息统计，但不会记录对话正文。管理员查看不含正文的对话标题权限默认关闭，您可在账户中心主动授权。"
          />
          <div class="mode-switch">
            <span class="mode-switch__label">登录模式</span>
            <t-radio-group v-model="selectedMode" variant="default-filled">
              <t-radio-button value="api">API 模式</t-radio-button>
              <t-radio-button value="web">混合模式</t-radio-button>
            </t-radio-group>
          </div>
          <t-space>
            <t-button theme="primary" :disabled="tableLoading" @click="onSelect(null)">
              智能分配最空闲账号
            </t-button>
            <t-button variant="text" @click="router.push('/account/profile')">账户中心</t-button>
          </t-space>
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
                  <div>被登录次数</div>
                  <div>{{ item.login_count || 0 }} 次</div>
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
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import request from '@/api/request'
import MarkdownContent from '@/components/MarkdownContent.vue'
import { useUserStore } from '@/store/user'

const tableLoading = ref(false)
const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const tableVisible = ref(false)
const announcementVisible = ref(false)
const activeAnnouncementTab = ref<'global' | 'personal' | 'history'>('global')
const statusText = ref('正在加载可用账号...')

type Announcement = {
  id: number
  title: string
  content: string
  updated_at: string
  start_at: string
  end_at: string | null
  display_timezone: string
}

const announcements = reactive<{
  global: Announcement[]
  personal: Announcement[]
  history: Announcement[]
}>({
  global: [],
  personal: [],
  history: [],
})

interface TableData {
  id: number
  chatgpt_flag: string
  plan_type: string
  auth_status: boolean
  login_count: number
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
  await prepareAnnouncements()
})

const prepareAnnouncements = async () => {
  if (userStore.isAdmin) {
    await getUserChatGPTAccountList()
    return
  }
  statusText.value = '正在加载公告...'
  const data = await request('/0x/user/announcements/current')
  announcements.global = data?.global || []
  announcements.personal = data?.personal || []
  announcements.history = data?.history || []

  if (announcements.global.length || announcements.personal.length || announcements.history.length) {
    activeAnnouncementTab.value = announcements.global.length
      ? 'global'
      : announcements.personal.length ? 'personal' : 'history'
    announcementVisible.value = true
    statusText.value = '请先阅读登录公告'
    return
  }

  await getUserChatGPTAccountList()
}

const continueToAccountSelection = async () => {
  announcementVisible.value = false
  await getUserChatGPTAccountList()
}

const formatAnnouncementSchedule = (item: Announcement) => {
  const timeZone = item.display_timezone || 'Asia/Shanghai'
  const start = new Date(item.start_at).toLocaleString('zh-CN', { hour12: false, timeZone })
  const end = item.end_at
    ? new Date(item.end_at).toLocaleString('zh-CN', { hour12: false, timeZone })
    : '长期'
  return `${start} 至 ${end} · ${timeZone}`
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

const onSelect = async (chatgptId: number | null) => {
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

.announcement-intro {
  margin-bottom: 16px;
  color: #6b7280;
  font-size: 14px;
}

.announcement-tabs {
  min-height: 280px;
}

.announcement-list {
  display: grid;
  gap: 12px;
  max-height: 52vh;
  padding: 16px 2px 4px;
  overflow-y: auto;
}

.announcement-item {
  padding: 18px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #fafaf9;
}

.announcement-heading {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
}

.announcement-heading h2 {
  margin: 0;
  color: #111827;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.5;
}

.announcement-heading time {
  flex: 0 0 auto;
  color: #9ca3af;
  font-size: 12px;
}

.announcement-content {
  margin-top: 12px;
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
