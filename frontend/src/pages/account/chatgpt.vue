<template>
  <div>
    <t-card title="ChatGPT 账号管理" :bordered="false">
      <template #actions>
        <t-space>
          <t-button :loading="checkingAll" @click="handleCheckTokenExpiry()">
            <template #icon><t-icon name="search" /></template>
            一键检测
          </t-button>
          <t-button theme="primary" @click="showAddDialog">
            <template #icon><t-icon name="add" /></template>
            添加账号
          </t-button>
        </t-space>
      </template>

      <t-table
        :data="tableData"
        :columns="columns"
        :loading="loading"
        :pagination="pagination"
        @page-change="onPageChange"
        row-key="id"
      >
        <template #auth_status="{ row }">
          <t-tag :theme="row.auth_status ? 'success' : 'danger'">
            {{ row.auth_status ? '有效' : '已过期' }}
          </t-tag>
        </template>
        <template #plan_type="{ row }">
          <t-tag :theme="getPlanTheme(row.plan_type)">
            {{ row.plan_type }}
          </t-tag>
        </template>
        <template #use_count="{ row }">
          <t-space size="small">
            <span>1h: {{ row.use_count?.last_1h || 0 }}</span>
            <span>2h: {{ row.use_count?.last_2h || 0 }}</span>
            <span>3h: {{ row.use_count?.last_3h || 0 }}</span>
          </t-space>
        </template>
        <template #access_token_valid="{ row }">
          <t-tag :theme="row.access_token_valid ? 'success' : 'danger'">
            {{ row.access_token_valid ? '可用' : '不可用' }}
          </t-tag>
        </template>
        <template #session_token_valid="{ row }">
          <t-tag :theme="row.session_token_valid ? 'success' : 'danger'">
            {{ row.session_token_valid ? '可用' : '不可用' }}
          </t-tag>
        </template>
        <template #supported_login_modes="{ row }">
          <t-space size="small">
            <t-tag
              v-for="mode in row.supported_login_modes || []"
              :key="mode"
              theme="primary"
              variant="light"
            >
              {{ mode.toUpperCase() }}
            </t-tag>
            <span v-if="!row.supported_login_modes?.length">无</span>
          </t-space>
        </template>
        <template #last_check_at="{ row }">
          <span>{{ formatCheckTime(row.last_check_at) }}</span>
        </template>
        <template #proxy_node_id="{ row }">
          <t-tag :theme="row.proxy_node_id ? 'primary' : 'default'" variant="light">
            {{ row.proxy_node_id ? `节点 ${row.proxy_node_id}` : '直连' }}
          </t-tag>
        </template>
        <template #token_remaining="{ row }">
          <t-tag :theme="getTokenRemainingTheme(row)" variant="light">
            {{ formatTokenRemaining(row) }}
          </t-tag>
        </template>
        <template #last_error="{ row }">
          <span>{{ row.last_error || '-' }}</span>
        </template>
        <template #op="{ row }">
          <t-space>
            <t-link theme="primary" :loading="checkingId === row.id" @click="handleCheckTokenExpiry(row)">
              检测
            </t-link>
            <t-link
              v-if="row.has_refresh_token || row.refresh_token"
              theme="primary"
              :loading="refreshingId === row.id"
              @click="handleRefreshToken(row)"
            >
              刷新Token
            </t-link>
            <t-link theme="primary" @click="showEditDialog(row)">编辑</t-link>
            <t-popconfirm content="确定删除该账号吗？" @confirm="handleDelete(row)">
              <t-link theme="danger">删除</t-link>
            </t-popconfirm>
          </t-space>
        </template>
      </t-table>
    </t-card>

    <!-- 添加对话框 -->
    <t-dialog
      :visible="addDialogVisible"
      header="添加 ChatGPT 账号"
      :confirm-btn="{ loading: submitLoading }"
      @confirm="handleAdd"
      @close="addDialogVisible = false"
      width="600px"
    >
      <t-form :data="addFormData" ref="addFormRef" label-width="120px">
        <t-form-item label="录入方式" name="auth_type">
          <t-radio-group v-model="authInputType">
            <t-radio-button value="cookie">Cookie 录入</t-radio-button>
            <t-radio-button value="refresh_token">RefreshToken 录入</t-radio-button>
          </t-radio-group>
        </t-form-item>

        <template v-if="authInputType === 'cookie'">
          <t-form-item label="Token 列表" name="chatgpt_token_list">
            <t-textarea
              v-model="tokenInput"
              placeholder="支持直接粘贴 AccessToken、SessionToken、完整 Cookie 文本或 Netscape HTTP Cookie File"
              :autosize="{ minRows: 5, maxRows: 10 }"
            />
          </t-form-item>
          <t-form-item>
            <t-alert theme="info" message="支持自动识别 AccessToken、SessionToken、浏览器 Cookie 文本与 Netscape HTTP Cookie File，并自动提取额外官网 Cookie。" />
          </t-form-item>
        </template>

        <template v-else>
          <t-form-item label="Client ID" name="client_id">
            <t-input
              v-model="refreshClientId"
              clearable
              placeholder="请输入 OpenAI 官方应用 Client ID"
            />
          </t-form-item>
          <t-form-item label="RefreshToken" name="refresh_token">
            <t-textarea
              v-model="refreshTokenInput"
              placeholder="请输入有效 refresh_token"
              :autosize="{ minRows: 4, maxRows: 8 }"
            />
          </t-form-item>
          <t-form-item>
            <t-alert theme="warning" message="RefreshToken 会滚动更新，系统会保存接口返回的新 refresh_token，请避免在多个服务中同时使用同一个旧 token。" />
          </t-form-item>
        </template>
      </t-form>
    </t-dialog>

    <!-- 编辑对话框 -->
    <t-dialog
      :visible="editDialogVisible"
      header="编辑账号备注"
      :confirm-btn="{ loading: submitLoading }"
      @confirm="handleEdit"
      @close="editDialogVisible = false"
    >
      <t-form :data="editFormData" ref="editFormRef" label-width="100px">
        <t-form-item label="账号">
          <t-input :value="editFormData.chatgpt_username" disabled />
        </t-form-item>
        <t-form-item label="备注" name="remark">
          <t-textarea v-model="editFormData.remark" placeholder="请输入备注" />
        </t-form-item>
        <t-form-item label="代理节点" name="proxy_node_id">
          <t-select v-model="editFormData.proxy_node_id" clearable placeholder="不绑定节点则直连">
            <t-option
              v-for="node in proxyNodeOptions"
              :key="node.id"
              :value="node.id"
              :label="`节点 ${node.id}`"
            />
          </t-select>
        </t-form-item>
      </t-form>
    </t-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import request from '@/api/request'

type AuthInputType = 'cookie' | 'refresh_token'

const DEFAULT_REFRESH_CLIENT_ID = 'app_EMoamEEZ73f0CkXaXp7hrann'

const loading = ref(false)
const submitLoading = ref(false)
const addDialogVisible = ref(false)
const editDialogVisible = ref(false)
const addFormRef = ref()
const editFormRef = ref()
const tableData = ref<any[]>([])
const authInputType = ref<AuthInputType>('cookie')
const tokenInput = ref('')
const refreshClientId = ref(DEFAULT_REFRESH_CLIENT_ID)
const refreshTokenInput = ref('')
const proxyNodeOptions = ref<Array<{ id: number }>>([])
const checkingAll = ref(false)
const checkingId = ref<number | null>(null)
const refreshingId = ref<number | null>(null)
const nowSeconds = ref(Math.floor(Date.now() / 1000))

const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0
})

const columns = [
  { colKey: 'id', title: 'ID', width: 80 },
  { colKey: 'chatgpt_username', title: '账号', ellipsis: true },
  { colKey: 'plan_type', title: '套餐', cell: 'plan_type', width: 100 },
  { colKey: 'auth_status', title: '状态', cell: 'auth_status', width: 100 },
  { colKey: 'access_token_valid', title: 'AccessToken', cell: 'access_token_valid', width: 110 },
  { colKey: 'session_token_valid', title: 'SessionToken', cell: 'session_token_valid', width: 120 },
  { colKey: 'supported_login_modes', title: '支持模式', cell: 'supported_login_modes', width: 160 },
  { colKey: 'use_count', title: '使用次数', cell: 'use_count', width: 200 },
  { colKey: 'proxy_node_id', title: '代理节点', cell: 'proxy_node_id', width: 110 },
  { colKey: 'token_remaining', title: 'Token剩余', cell: 'token_remaining', width: 130 },
  { colKey: 'last_check_at', title: '最近诊断', cell: 'last_check_at', width: 160 },
  { colKey: 'last_error', title: '诊断结果', cell: 'last_error', ellipsis: true },
  { colKey: 'remark', title: '备注', ellipsis: true },
  { colKey: 'op', title: '操作', cell: 'op', width: 260 }
]

const addFormData = reactive({
  auth_type: 'cookie' as AuthInputType,
  chatgpt_token_list: [] as string[]
})

const editFormData = reactive({
  chatgpt_username: '',
  remark: '',
  proxy_node_id: null as number | null
})

onMounted(() => {
  fetchData()
  fetchProxyNodes()
})

const formatCheckTime = (value?: number | null) => {
  if (!value) return '-'
  const date = new Date(value * 1000)
  const yyyy = date.getFullYear()
  const mm = String(date.getMonth() + 1).padStart(2, '0')
  const dd = String(date.getDate()).padStart(2, '0')
  const hh = String(date.getHours()).padStart(2, '0')
  const mi = String(date.getMinutes()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`
}

const getPlanTheme = (planType?: string) => {
  const normalized = (planType || '').toLowerCase()
  if (['team', 'business', 'enterprise', 'workspace'].includes(normalized)) {
    return 'warning'
  }
  if (['plus', 'pro'].includes(normalized)) {
    return 'primary'
  }
  return 'default'
}

const secondsUntilAccessTokenExpiry = (row: any) => {
  if (!row?.access_token_exp) return null
  return Number(row.access_token_exp) - nowSeconds.value
}

const formatSeconds = (seconds: number | null) => {
  if (seconds === null || Number.isNaN(seconds)) return '-'
  if (seconds <= 0) return '已过期'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days}天${hours}小时`
  if (hours > 0) return `${hours}小时${minutes}分钟`
  return `${Math.max(minutes, 1)}分钟`
}

const formatTokenRemaining = (row: any) => {
  return formatSeconds(secondsUntilAccessTokenExpiry(row))
}

const getTokenRemainingTheme = (row: any) => {
  const seconds = secondsUntilAccessTokenExpiry(row)
  if (seconds === null || seconds <= 0) return 'danger'
  if (seconds < 86400) return 'warning'
  return 'success'
}

const fetchData = async () => {
  loading.value = true
  const data = await request(`/0x/chatgpt?page=${pagination.current}&page_size=${pagination.pageSize}`)
  loading.value = false
  
  if (data) {
    nowSeconds.value = Math.floor(Date.now() / 1000)
    tableData.value = data.results || []
    pagination.total = data.count || 0
  }
}

const fetchProxyNodes = async () => {
  const data = await request('/0x/user/proxy-config')
  if (data) {
    proxyNodeOptions.value = (data.nodes || [])
      .filter((node: any) => node.enabled)
      .map((node: any) => ({ id: Number(node.id) }))
      .filter((node: any) => node.id > 0)
  }
}

const onPageChange = (pageInfo: any) => {
  pagination.current = pageInfo.current
  pagination.pageSize = pageInfo.pageSize
  fetchData()
}

const showAddDialog = () => {
  authInputType.value = 'cookie'
  addFormData.auth_type = 'cookie'
  tokenInput.value = ''
  refreshClientId.value = DEFAULT_REFRESH_CLIENT_ID
  refreshTokenInput.value = ''
  addDialogVisible.value = true
}

const showEditDialog = (row: any) => {
  editFormData.chatgpt_username = row.chatgpt_username
  editFormData.remark = row.remark || ''
  editFormData.proxy_node_id = row.proxy_node_id || null
  editDialogVisible.value = true
}

const looksLikeNetscapeCookieFile = (raw: string) => {
  if (raw.includes('# Netscape HTTP Cookie File')) {
    return true
  }
  return raw
    .split('\n')
    .map(line => line.trim())
    .filter(line => line && !line.startsWith('#'))
    .some(line => line.split('\t').length >= 7)
}

const splitTokenInputs = (raw: string) => {
  const trimmed = raw.trim()
  if (!trimmed) {
    return []
  }
  if (looksLikeNetscapeCookieFile(trimmed)) {
    return [trimmed]
  }
  return trimmed
    .split('\n')
    .map(item => item.trim())
    .filter(Boolean)
}

const handleAdd = async () => {
  if (authInputType.value === 'refresh_token') {
    const clientId = refreshClientId.value.trim()
    const refreshToken = refreshTokenInput.value.trim()
    if (!clientId) {
      MessagePlugin.warning('请输入 client_id')
      return
    }
    if (!refreshToken) {
      MessagePlugin.warning('请输入 refresh_token')
      return
    }

    submitLoading.value = true
    const data = await request('/0x/chatgpt', 'POST', {
      auth_type: 'refresh_token',
      client_id: clientId,
      refresh_token: refreshToken
    })
    submitLoading.value = false

    if (data) {
      MessagePlugin.success(data.message || '添加成功')
      addDialogVisible.value = false
      fetchData()
    }
    return
  }

  const tokens = splitTokenInputs(tokenInput.value)
  if (tokens.length === 0) {
    MessagePlugin.warning('请输入至少一个 Token')
    return
  }

  submitLoading.value = true
  const data = await request('/0x/chatgpt', 'POST', {
    chatgpt_token_list: tokens
  })
  submitLoading.value = false

  if (data) {
    if (data.errors?.length) {
      MessagePlugin.warning(data.message || `部分添加成功，失败 ${data.errors.length} 个`)
    } else {
      MessagePlugin.success(data.message || '添加成功')
    }
    addDialogVisible.value = false
    fetchData()
  }
}

const handleEdit = async () => {
  submitLoading.value = true
  const data = await request('/0x/chatgpt', 'PUT', {
    ...editFormData,
    proxy_node_id: editFormData.proxy_node_id || null
  })
  submitLoading.value = false

  if (data) {
    MessagePlugin.success('更新成功')
    editDialogVisible.value = false
    fetchData()
  }
}

const mergeTokenCheckResults = (results: any[]) => {
  nowSeconds.value = Math.floor(Date.now() / 1000)
  const resultMap = new Map(results.map(item => [item.id, item]))
  tableData.value = tableData.value.map(row => {
    const result = resultMap.get(row.id)
    return result ? { ...row, ...result } : row
  })
}

const summarizeTokenCheck = (results: any[]) => {
  if (results.length === 0) return '没有可检测的账号'
  if (results.length === 1) {
    return `Token剩余：${formatSeconds(results[0].remaining_seconds)}`
  }
  const expiredCount = results.filter(item => item.expired).length
  return `检测完成：${results.length}个账号，已过期${expiredCount}个`
}

const handleCheckTokenExpiry = async (row?: any) => {
  const ids = row ? [row.id] : tableData.value.map(item => item.id)
  if (ids.length === 0) {
    MessagePlugin.warning('当前页没有账号')
    return
  }

  if (row) {
    checkingId.value = row.id
  } else {
    checkingAll.value = true
  }

  const data = await request('/0x/chatgpt/token-expiry', 'POST', row ? { ids } : {})

  if (row) {
    checkingId.value = null
  } else {
    checkingAll.value = false
  }

  if (data?.results) {
    mergeTokenCheckResults(data.results)
    MessagePlugin.success(summarizeTokenCheck(data.results))
  }
}

const handleRefreshToken = async (row: any) => {
  refreshingId.value = row.id
  const data = await request('/0x/chatgpt/refresh-token', 'POST', {
    id: row.id
  })
  refreshingId.value = null

  if (data?.result) {
    mergeTokenCheckResults([data.result])
    MessagePlugin.success(`刷新成功，Token剩余：${formatSeconds(data.result.remaining_seconds)}`)
  }
}

const handleDelete = async (row: any) => {
  const data = await request('/0x/chatgpt', 'DELETE', {
    chatgpt_username: row.chatgpt_username
  })
  if (data) {
    MessagePlugin.success('删除成功')
    fetchData()
  }
}
</script>
