<template>
  <div>
    <t-card title="访问日志" :bordered="false">
      <t-table
        :data="tableData"
        :columns="columns"
        :loading="loading"
        :pagination="pagination"
        @page-change="onPageChange"
        row-key="id"
      >
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
import request from '@/api/request'

const loading = ref(false)
const tableData = ref<any[]>([])

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0
})

const columns = [
  { colKey: 'id', title: 'ID', width: 80 },
  { colKey: 'username', title: '用户名' },
  { colKey: 'chatgpt_username', title: 'ChatGPT 账号', ellipsis: true },
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
  const data = await request(`/0x/user/visit-log?page=${pagination.current}&page_size=${pagination.pageSize}`)
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

const getLogTypeTheme = (type: string) => {
  const themes: Record<string, string> = {
    'login': 'success',
    'choose-gpt': 'primary',
    'logout': 'warning'
  }
  return themes[type] || 'default'
}

const getLogTypeText = (type: string) => {
  const texts: Record<string, string> = {
    'login': '登录',
    'choose-gpt': '选择账号',
    'logout': '登出'
  }
  return texts[type] || type
}

const formatTime = (timestamp: number) => {
  return dayjs.unix(timestamp).format('YYYY-MM-DD HH:mm:ss')
}
</script>
