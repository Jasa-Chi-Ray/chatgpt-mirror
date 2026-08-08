<template>
  <div>
    <t-card title="日志" subtitle="查看登录与账号使用记录；管理员登录记录会被永久保留" :bordered="false">
      <template #actions>
        <t-popconfirm
          content="清除全部可删除日志？管理员登录记录不会被清除。"
          @confirm="clearLogs"
        >
          <t-button theme="danger" variant="outline" :loading="clearing">
            清除可删除日志
          </t-button>
        </t-popconfirm>
      </template>
      <div class="log-toolbar">
        <t-input v-model="query" clearable placeholder="搜索用户或上游账号" @enter="applyFilters" />
        <t-select v-model="logType" clearable placeholder="全部类型" @change="applyFilters">
          <t-option value="login" label="登录" />
          <t-option value="choose-gpt" label="选择账号" />
          <t-option value="proxy" label="代理请求" />
        </t-select>
        <t-button variant="outline" @click="applyFilters">查询</t-button>
      </div>
      <t-table
        :data="tableData"
        :columns="columns"
        :loading="loading"
        :pagination="pagination"
        @page-change="onPageChange"
        row-key="id"
      >
        <template #username="{ row }">
          <span>{{ row.username }}</span>
          <span v-if="isProtectedLog(row)" class="protected-label">保留</span>
        </template>
        <template #log_type="{ row }">
          <t-tag :theme="getLogTypeTheme(row.log_type)">
            {{ getLogTypeText(row.log_type) }}
          </t-tag>
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
  { colKey: 'ip', title: 'IP 地址', width: 150 },
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
      `已清除 ${data.deleted_count || 0} 条日志，保留 ${data.protected_count || 0} 条管理员登录记录`
    )
  }
}

const getLogTypeTheme = (type: string) => {
  const themes: Record<string, string> = {
    'login': 'success',
    'choose-gpt': 'primary',
    'logout': 'warning',
    'proxy': 'default'
  }
  return themes[type] || 'default'
}

const getLogTypeText = (type: string) => {
  const texts: Record<string, string> = {
    'login': '登录',
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
  color: #5f5f5a;
  font-size: 11px;
  line-height: 16px;
  background: #efefec;
  border-radius: 4px;
}
.log-toolbar {
  display: grid;
  grid-template-columns: minmax(240px, 1fr) 180px auto;
  gap: 10px;
  margin-bottom: 16px;
}
</style>
