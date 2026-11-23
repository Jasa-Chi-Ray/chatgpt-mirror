<template>
  <div class="workspace-page overview-page overview">
    <div class="overview-actions">
      <t-button variant="outline" :loading="backingUp" @click="downloadBackup">{{ t('下载加密备份') }}</t-button>
      <t-button variant="outline" :loading="restoring" @click="backupInput?.click()">{{ t('恢复备份') }}</t-button>
      <input ref="backupInput" type="file" accept="application/json" hidden @change="restoreBackup" />
    </div>
    <t-loading :loading="loading">
      <div class="metric-grid">
        <t-card v-for="metric in metrics" :key="metric.label" :bordered="false" class="metric-card">
          <div class="metric-label"><t-icon :name="metric.icon" aria-hidden="true" />{{ t(metric.label) }}</div>
          <div class="metric-value">{{ metric.value }}</div>
          <div class="metric-detail">{{ metric.detail }}</div>
        </t-card>
      </div>
      <t-card :title="t('运行状态')" :subtitle="t('用户、上游账号和今日活动的实时汇总')" :bordered="false">
        <t-descriptions v-if="overview" :column="2" bordered>
          <t-descriptions-item :label="t('启用用户')">{{ overview.users.active }}</t-descriptions-item>
          <t-descriptions-item :label="t('过期用户')">{{ overview.users.expired }}</t-descriptions-item>
          <t-descriptions-item :label="t('健康上游')">{{ overview.upstream.healthy }}</t-descriptions-item>
          <t-descriptions-item :label="t('异常上游')">{{ overview.upstream.unhealthy }}</t-descriptions-item>
          <t-descriptions-item :label="t('今日登录')">{{ overview.activity.today_logins }}</t-descriptions-item>
          <t-descriptions-item :label="t('今日代理请求')">{{ overview.activity.today_requests }}</t-descriptions-item>
          <t-descriptions-item :label="t('活跃镜像会话')">{{ overview.activity.active_sessions }}</t-descriptions-item>
        </t-descriptions>
      </t-card>
    </t-loading>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import request from '@/api/request'
import { useWorkspaceCopy } from '@/pages/account/workspace-copy'

const { t } = useWorkspaceCopy()

const loading = ref(false)
const overview = ref<any>(null)
const backingUp = ref(false)
const restoring = ref(false)
const backupInput = ref<HTMLInputElement | null>(null)
const metrics = computed(() => [
  { label: '用户总数', icon: 'user', value: overview.value?.users.total ?? '-', detail: t('{0} 个启用', [overview.value?.users.active ?? 0]) },
  { label: '上游账号', icon: 'server', value: overview.value?.upstream.total ?? '-', detail: t('{0} 个健康', [overview.value?.upstream.healthy ?? 0]) },
  { label: '今日登录', icon: 'dashboard', value: overview.value?.activity.today_logins ?? '-', detail: t('按自然日统计') },
  { label: '今日请求', icon: 'internet', value: overview.value?.activity.today_requests ?? '-', detail: t('计入配额的代理请求') }
])

onMounted(async () => {
  loading.value = true
  overview.value = await request('/0x/user/overview')
  loading.value = false
})

const downloadBackup = async () => {
  backingUp.value = true
  const data = await request('/0x/user/backup')
  backingUp.value = false
  if (!data?.archive) return
  const blob = new Blob([JSON.stringify(data)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `chatgpt-mirror-backup-${Date.now()}.json`
  anchor.click()
  URL.revokeObjectURL(url)
}

const restoreBackup = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  restoring.value = true
  try {
    const parsed = JSON.parse(await file.text())
    const data = await request('/0x/user/backup', 'POST', {
      archive: parsed.archive,
      confirm: 'RESTORE'
    })
    if (data) MessagePlugin.success(data.message)
  } catch {
    MessagePlugin.error(t('备份文件格式无效'))
  } finally {
    restoring.value = false
    input.value = ''
  }
}
</script>

<style scoped>
.overview { display: grid; gap: 20px; }
.overview-actions { display: flex; justify-content: flex-end; gap: 10px; }
.metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-bottom: 20px; }
.metric-card { min-height: 132px; }
.metric-label { display: flex; align-items: center; gap: 8px; color: var(--app-text-muted); font-size: 13px; }
.metric-label :deep(.t-icon) { color: var(--app-action); font-size: 16px; }
.metric-value { margin-top: 14px; color: var(--app-text); font-size: 30px; font-weight: 600; letter-spacing: -0.03em; }
.metric-detail { margin-top: 8px; color: var(--app-text-muted); font-size: 13px; }
@media (max-width: 900px) { .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
