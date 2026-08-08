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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import request from '@/api/request'

const quota = ref<any>({ daily: { limit: 0, used: 0 }, monthly: { limit: 0, used: 0 } })
const loading = ref(false)
const saving = ref(false)
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

onMounted(loadQuota)
</script>

<style scoped>
.profile-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 20px; }
.quota-row + .quota-row { margin-top: 24px; }
.quota-head { display: flex; justify-content: space-between; margin-bottom: 10px; color: var(--app-text); font-size: 14px; }
@media (max-width: 900px) { .profile-grid { grid-template-columns: 1fr; } }
</style>
