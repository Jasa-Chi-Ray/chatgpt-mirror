<template>
  <div class="profile-grid">
    <t-card title="用量配额" subtitle="配额为 0 表示不限制" :bordered="false">
      <t-loading :loading="loading">
        <div v-for="item in quotaItems" :key="item.label" class="quota-row">
          <div class="quota-head">
            <span>{{ item.label }}</span>
            <span>{{ item.used }} / {{ item.limit || '不限' }}</span>
          </div>
          <t-progress :percentage="item.limit ? Math.min(100, item.used / item.limit * 100) : 0" :label="false" />
        </div>
      </t-loading>
    </t-card>
    <t-card title="修改密码" subtitle="修改后会撤销其他设备上的旧登录 Token" :bordered="false">
      <t-form :data="form" label-width="100px" @submit="changePassword">
        <t-form-item label="当前密码" name="current_password">
          <t-input v-model="form.current_password" type="password" autocomplete="current-password" />
        </t-form-item>
        <t-form-item label="新密码" name="new_password">
          <t-input v-model="form.new_password" type="password" autocomplete="new-password" />
        </t-form-item>
        <t-form-item>
          <t-button theme="primary" type="submit" :loading="saving">保存新密码</t-button>
        </t-form-item>
      </t-form>
    </t-card>
    <t-card title="对话标题隐私" subtitle="对话次数和模型消息统计始终可见，标题由你决定是否授权" :bordered="false">
      <t-loading :loading="privacyLoading">
        <div class="privacy-row">
          <div>
            <div class="privacy-title">允许管理员查看对话标题</div>
            <div class="privacy-desc">默认关闭。关闭时管理员只能看到官网对话路径中的 UUID，且不能点击。</div>
          </div>
          <t-switch
            v-model="allowAdminViewConversationTitles"
            :loading="privacySaving"
            @change="saveTitlePrivacy"
          />
        </div>
      </t-loading>
    </t-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import request from '@/api/request'

const quota = ref<any>({ daily: { limit: 0, used: 0 }, monthly: { limit: 0, used: 0 } })
const loading = ref(false)
const saving = ref(false)
const privacyLoading = ref(false)
const privacySaving = ref(false)
const allowAdminViewConversationTitles = ref(false)
const form = reactive({ current_password: '', new_password: '' })
const quotaItems = computed(() => [
  { label: '今日用量', ...quota.value.daily },
  { label: '本月用量', ...quota.value.monthly }
])

const loadQuota = async () => {
  loading.value = true
  quota.value = (await request('/0x/user/quota')) || quota.value
  loading.value = false
}

const changePassword = async () => {
  if (!form.current_password || !form.new_password) {
    MessagePlugin.warning('请完整填写当前密码和新密码')
    return
  }
  saving.value = true
  const data = await request('/0x/user/change-password', 'POST', form)
  saving.value = false
  if (data) {
    form.current_password = ''
    form.new_password = ''
    MessagePlugin.success(data.message)
  }
}

const loadTitlePrivacy = async () => {
  privacyLoading.value = true
  const data = await request('/0x/user/me')
  privacyLoading.value = false
  if (data) {
    allowAdminViewConversationTitles.value = Boolean(data.allow_admin_view_conversation_titles)
  }
}

const saveTitlePrivacy = async () => {
  privacySaving.value = true
  const data = await request('/0x/user/conversation-title-privacy', 'POST', {
    allow_admin_view_conversation_titles: allowAdminViewConversationTitles.value,
  })
  privacySaving.value = false
  if (data) {
    MessagePlugin.success(data.message)
  }
}

onMounted(() => {
  loadQuota()
  loadTitlePrivacy()
})
</script>

<style scoped>
.profile-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 20px; }
.quota-row + .quota-row { margin-top: 24px; }
.quota-head { display: flex; justify-content: space-between; margin-bottom: 10px; color: var(--app-text); font-size: 14px; }
.privacy-row { display: flex; gap: 20px; align-items: center; justify-content: space-between; }
.privacy-title { color: var(--app-text); font-size: 14px; font-weight: 600; }
.privacy-desc { margin-top: 6px; color: var(--app-text-muted); font-size: 13px; line-height: 1.6; }
@media (max-width: 900px) { .profile-grid { grid-template-columns: 1fr; } }
</style>
