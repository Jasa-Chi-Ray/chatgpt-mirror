<template>
  <div class="workspace-page data-page logs-page">
    <t-card :title="t('日志')" :subtitle="t('查看登录与账号使用记录；管理员登录记录会被永久保留')" :bordered="false">
      <template #actions>
        <t-popconfirm
          :content="t('清除全部可删除日志？管理员登录记录不会被清除。')"
          @confirm="clearLogs"
        >
          <t-button theme="danger" variant="outline" :loading="clearing">
            {{ t('清除可删除日志') }}
          </t-button>
        </t-popconfirm>
      </template>
      <div class="log-toolbar">
        <t-input v-model="query" clearable :placeholder="t('搜索用户或上游账号')" @enter="applyFilters" />
        <t-select v-model="logType" clearable :placeholder="t('全部类型')" @change="applyFilters">
          <t-option value="login" :label="t('登录')" />
          <t-option value="login-failed" :label="t('密码连续错误')" />
          <t-option value="login-cooldown" :label="t('登录冷却')" />
          <t-option value="choose-gpt" :label="t('选择账号')" />
          <t-option value="proxy" :label="t('代理请求')" />
        </t-select>
        <t-button variant="outline" @click="applyFilters">{{ t('查询') }}</t-button>
      </div>
      <t-table
        :data="tableData"
        :columns="labels(columns)"
        :loading="loading"
        :pagination="pagination"
        @page-change="onPageChange"
        row-key="id"
      >
        <template #username="{ row }">
          <span>{{ row.username }}</span>
          <span v-if="isProtectedLog(row)" class="protected-label">{{ t('保留') }}</span>
        </template>
        <template #log_type="{ row }">
          <t-tag :theme="getLogTypeTheme(row.log_type)">
            {{ t(getLogTypeText(row.log_type)) }}
          </t-tag>
        </template>
        <template #browser_ip="{ row }">
          <span :title="row.browser_ip ? t('浏览器上报的公网出口 IP，仅供参考') : t('未获取、检测失败或历史记录')">
            {{ row.browser_ip || t('未获取') }}
          </span>
        </template>
        <template #created_at="{ row }">
          {{ formatTime(row.created_at) }}
        </template>
      </t-table>
    </t-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import dayjs from 'dayjs'
import { MessagePlugin } from 'tdesign-vue-next'
import request from '@/api/request'
import { useWorkspaceCopy } from '@/pages/account/workspace-copy'

const { t, labels } = useWorkspaceCopy()

const loading = ref(false)
const clearing = ref(false)
const tableData = ref<any[]>([])
const query = ref('')
const logType = ref('')

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

const columns = [
  { colKey: 'id', title: 'ID', width: 80 },
  { colKey: 'username', title: '用户名', cell: 'username' },
  { colKey: 'chatgpt_username', title: '上游账号', ellipsis: true },
  { colKey: 'log_type', title: '操作类型', cell: 'log_type', width: 120 },
  { colKey: 'ip', title: '服务端识别 IP', width: 180, ellipsis: true },
  { colKey: 'browser_ip', title: '浏览器检测 IP（参考）', cell: 'browser_ip', width: 220, ellipsis: true },
  { colKey: 'failure_count', title: '连续失败', width: 100 },
  { colKey: 'cooldown_seconds', title: '冷却秒数', width: 100 },
  { colKey: 'created_at', title: '时间', cell: 'created_at', width: 180 },
  { colKey: 'user_agent', title: 'User Agent', ellipsis: true }
]

onMounted(() => {
  fetchData()
})

const fetchData = async () => {
  loading.value = true
  const params = new URLSearchParams({
    page: String(pagination.current),
    page_size: String(pagination.pageSize)
  })
  if (query.value.trim()) params.set('q', query.value.trim())
  if (logType.value) params.set('log_type', logType.value)
  const data = await request(`/0x/user/visit-log?${params.toString()}`)
  loading.value = false
  
  if (data) {
    tableData.value = data.results || []
    pagination.total = data.count || 0
  }
}

const onPageChange = (pageInfo: any) => {
  pagination.current = pageInfo.current
  pagination.pageSize = pageInfo.pageSize
  fetchData()
}

const applyFilters = () => {
  pagination.current = 1
  fetchData()
}

const isProtectedLog = (row: any) => {
  return Boolean(row.is_protected)
}

const clearLogs = async () => {
  clearing.value = true
  const data = await request('/0x/user/visit-log', 'DELETE')
  clearing.value = false

  if (data) {
    pagination.current = 1
    await fetchData()
    MessagePlugin.success(
      t('已清除 {0} 条日志，保留 {1} 条管理员登录记录', [data.deleted_count || 0, data.protected_count || 0])
    )
  }
}

const getLogTypeTheme = (type: string) => {
  const themes: Record<string, string> = {
    'login': 'success',
    'login-failed': 'warning',
    'login-cooldown': 'danger',
    'choose-gpt': 'primary',
    'logout': 'warning',
    'proxy': 'default'
  }
  return themes[type] || 'default'
}

const getLogTypeText = (type: string) => {
  const texts: Record<string, string> = {
    'login': '登录',
    'login-failed': '密码连续错误',
    'login-cooldown': '登录冷却',
    'choose-gpt': '选择账号',
    'logout': '登出',
    'proxy': '代理请求'
  }
  return texts[type] || type
}

const formatTime = (timestamp: number) => {
  return dayjs.unix(timestamp).format('YYYY-MM-DD HH:mm:ss')
}
</script>

<style scoped>
.protected-label {
  display: inline-flex;
  margin-left: 8px;
  padding: 2px 6px;
  color: var(--app-text-muted);
  font-size: 11px;
  line-height: 16px;
  background: var(--app-field);
  border-radius: 4px;
}
.log-toolbar {
  display: grid;
  grid-template-columns: minmax(240px, 1fr) 180px auto;
  gap: 10px;
  margin-bottom: 16px;
}
</style>
