<template>
  <div>
    <t-card title="用户" subtitle="管理可访问系统的用户、账号池和模型权限" :bordered="false">
      <template #actions>
        <t-button theme="primary" @click="showAddDialog">
          <template #icon><t-icon name="add" /></template>
          添加用户
        </t-button>
      </template>
      <div class="table-toolbar">
        <t-input v-model="query" clearable placeholder="搜索用户名或备注" @enter="applyFilters" />
        <t-select v-model="statusFilter" clearable placeholder="全部状态" @change="applyFilters">
          <t-option value="active" label="启用" />
          <t-option value="inactive" label="禁用" />
        </t-select>
        <t-button variant="outline" @click="applyFilters">查询</t-button>
        <t-button variant="outline" :disabled="!selectedRowKeys.length" @click="batchAction('activate')">批量启用</t-button>
        <t-button variant="outline" :disabled="!selectedRowKeys.length" @click="batchAction('deactivate')">批量禁用</t-button>
      </div>

      <t-table
        :data="tableData"
        :columns="columns"
        :loading="loading"
        :pagination="pagination"
        @page-change="onPageChange"
        row-key="id"
        v-model:selected-row-keys="selectedRowKeys"
      >
        <template #is_active="{ row }">
          <t-tag :theme="row.is_active ? 'success' : 'danger'">
            {{ row.is_active ? '启用' : '禁用' }}
          </t-tag>
        </template>
        <template #expired_date="{ row }">
          {{ row.expired_date || '永久' }}
        </template>
        <template #model_limit="{ row }">
          <t-space size="small" v-if="row.model_limit && row.model_limit.length > 0">
            <t-tag v-for="model in row.model_limit.slice(0, 2)" :key="model" size="small">
              {{ model }}
            </t-tag>
            <t-tag v-if="row.model_limit.length > 2" size="small">
              +{{ row.model_limit.length - 2 }}
            </t-tag>
          </t-space>
          <span v-else class="text-gray">全部模型</span>
        </template>
        <template #force_chat_mode="{ row }">
          <t-tag :theme="row.force_chat_mode !== false ? 'success' : 'default'">
            {{ row.force_chat_mode !== false ? '自动切回' : '允许 Work' }}
          </t-tag>
        </template>
        <template #model_message_counts="{ row }">
          <t-space v-if="Object.keys(row.model_message_counts || {}).length" size="small" break-line>
            <t-tag
              v-for="([model, count]) in Object.entries(row.model_message_counts || {}).slice(0, 2)"
              :key="model"
              size="small"
              variant="light"
            >
              {{ model }}: {{ count }}
            </t-tag>
          </t-space>
          <span v-else class="text-gray">暂无</span>
        </template>
        <template #op="{ row }">
          <t-space>
            <t-link theme="primary" @click="showStatisticsDialog(row)">对话统计</t-link>
            <t-link theme="primary" @click="showEditDialog(row)">编辑</t-link>
            <t-popconfirm content="确定删除该用户吗？" @confirm="handleDelete(row)">
              <t-link theme="danger">删除</t-link>
            </t-popconfirm>
          </t-space>
        </template>
      </t-table>
    </t-card>

    <!-- 添加/编辑对话框 -->
    <t-dialog
      :visible="dialogVisible"
      :header="isEdit ? '编辑用户' : '添加用户'"
      :confirm-btn="{ loading: submitLoading }"
      @confirm="handleSubmit"
      @close="dialogVisible = false"
      width="600px"
    >
      <t-form :data="formData" :rules="formRules" ref="formRef" label-width="100px">
        <t-form-item label="用户名" name="username">
          <t-input v-model="formData.username" :disabled="isEdit" placeholder="请输入用户名" />
        </t-form-item>
        <t-form-item label="密码" name="password">
          <t-input v-model="formData.password" type="password" :placeholder="isEdit ? '留空则不修改' : '请输入密码'" />
        </t-form-item>
        <t-form-item label="是否启用" name="is_active">
          <t-switch v-model="formData.is_active" />
        </t-form-item>
        <t-form-item label="独立会话" name="isolated_session">
          <t-switch v-model="formData.isolated_session" />
        </t-form-item>
        <t-form-item label="自动退出 Work" name="force_chat_mode">
          <t-switch v-model="formData.force_chat_mode" />
          <template #help>
            <span class="form-help">开启后检测到 Work 模式会自动点击“聊天 / Chat”切回聊天模式</span>
          </template>
        </t-form-item>
        <t-form-item label="过期日期" name="expired_date">
          <t-date-picker
            v-model="formData.expired_date"
            format="YYYY-MM-DD"
            value-type="YYYY-MM-DD"
            clearable
            placeholder="留空则永久有效"
          />
        </t-form-item>
        <t-form-item label="每日配额" name="daily_quota">
          <t-input-number v-model="formData.daily_quota" :min="0" />
        </t-form-item>
        <t-form-item label="每月配额" name="monthly_quota">
          <t-input-number v-model="formData.monthly_quota" :min="0" />
        </t-form-item>
        <t-form-item label="关联号池" name="gptcar_list">
          <t-select v-model="formData.gptcar_list" multiple placeholder="请选择号池">
            <t-option v-for="car in carOptions" :key="car.id" :value="car.id" :label="car.car_name" />
          </t-select>
        </t-form-item>
        <t-form-item label="模型限制" name="model_limit">
          <t-textarea
            v-model="modelLimitInput"
            placeholder="多个模型用逗号或换行分隔，留空表示可使用全部模型"
            :autosize="{ minRows: 3, maxRows: 6 }"
          />
          <template #help>
            <span class="form-help">按上游 Django 后台协议直接提交模型 ID 列表，不再依赖 /0x/models/* 接口</span>
          </template>
        </t-form-item>
        <t-form-item label="备注" name="remark">
          <t-textarea v-model="formData.remark" placeholder="请输入备注" />
        </t-form-item>
      </t-form>
    </t-dialog>

    <t-dialog
      :visible="statisticsDialogVisible"
      :header="`${statisticsUser.username || ''} 的对话统计`"
      :confirm-btn="null"
      width="860px"
      @close="statisticsDialogVisible = false"
    >
      <t-loading :loading="statisticsLoading">
        <div class="statistics-summary">
          <div class="statistics-card">
            <span>创建对话</span>
            <strong>{{ statisticsData.conversation_count }} 条</strong>
          </div>
          <div class="statistics-card">
            <span>发送消息</span>
            <strong>{{ statisticsData.message_count }} 条</strong>
          </div>
        </div>

        <div class="statistics-section">
          <div class="statistics-section__title">模型消息数</div>
          <t-space v-if="modelStatisticsRows.length" break-line>
            <t-tag v-for="item in modelStatisticsRows" :key="item.model" variant="light">
              {{ item.model }}：{{ item.count }} 条
            </t-tag>
          </t-space>
          <t-empty v-else description="暂无模型消息统计" />
        </div>

        <div class="statistics-section">
          <div class="statistics-section__head">
            <div class="statistics-section__title">对话列表</div>
            <t-popconfirm content="确定重置该用户的全部对话统计吗？不会删除实际对话。" @confirm="resetStatistics">
              <t-button size="small" theme="warning" variant="outline">重置统计</t-button>
            </t-popconfirm>
          </div>
          <t-alert
            v-if="!statisticsData.title_visible"
            theme="info"
            message="该用户未允许管理员查看对话标题，以下仅显示官网对话路径中的 UUID。"
          />
          <div v-if="statisticsData.conversations.length" class="conversation-stat-list">
            <div v-for="item in statisticsData.conversations" :key="item.conversation_id" class="conversation-stat-row">
              <div class="conversation-stat-title">{{ item.display_title }}</div>
              <div class="conversation-stat-meta">{{ item.message_count }} 条消息</div>
            </div>
          </div>
          <t-empty v-else description="暂无对话统计" />
        </div>
      </t-loading>
    </t-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, reactive, onMounted } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import request from '@/api/request'

const loading = ref(false)
const submitLoading = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const formRef = ref()
const tableData = ref<any[]>([])
const carOptions = ref<any[]>([])
const modelLimitInput = ref('')
const query = ref('')
const statusFilter = ref('')
const selectedRowKeys = ref<Array<number | string>>([])
const statisticsDialogVisible = ref(false)
const statisticsLoading = ref(false)
const statisticsUser = reactive({ id: 0, username: '' })
const statisticsData = reactive({
  conversation_count: 0,
  message_count: 0,
  model_message_counts: {} as Record<string, number>,
  conversations: [] as Array<{
    conversation_id: string
    display_title: string
    message_count: number
  }>,
  title_visible: false,
})
const modelStatisticsRows = computed(() =>
  Object.entries(statisticsData.model_message_counts)
    .map(([model, count]) => ({ model, count: Number(count) || 0 }))
    .sort((a, b) => b.count - a.count),
)

const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0
})

const columns = [
  { colKey: 'row-select', type: 'multiple', width: 46 },
  { colKey: 'id', title: 'ID', width: 80 },
  { colKey: 'username', title: '用户名' },
  { colKey: 'is_active', title: '状态', cell: 'is_active', width: 80 },
  { colKey: 'model_limit', title: '模型限制', cell: 'model_limit', width: 180 },
  { colKey: 'force_chat_mode', title: 'Work 模式', cell: 'force_chat_mode', width: 110 },
  { colKey: 'expired_date', title: '过期日期', cell: 'expired_date', width: 120 },
  { colKey: 'conversation_count', title: '对话数', width: 90 },
  { colKey: 'message_count', title: '消息数', width: 90 },
  { colKey: 'model_message_counts', title: '模型消息', cell: 'model_message_counts', width: 230 },
  { colKey: 'remark', title: '备注', ellipsis: true },
  { colKey: 'op', title: '操作', cell: 'op', width: 220 }
]

const formData = reactive({
  id: 0,
  username: '',
  password: '',
  is_active: true,
  isolated_session: true,
  force_chat_mode: true,
  expired_date: '',
  gptcar_list: [] as number[],
  model_limit: [] as string[],
  remark: '',
  daily_quota: 0,
  monthly_quota: 0
})

const formRules = {
  username: [{ required: true, message: '请输入用户名' }]
}

onMounted(() => {
  fetchData()
  fetchCarOptions()
})

const fetchData = async () => {
  loading.value = true
  const params = new URLSearchParams({
    page: String(pagination.current),
    page_size: String(pagination.pageSize)
  })
  if (query.value.trim()) params.set('q', query.value.trim())
  if (statusFilter.value) params.set('status', statusFilter.value)
  const data = await request(`/0x/user?${params.toString()}`)
  loading.value = false
  
  if (data) {
    tableData.value = data.results || []
    pagination.total = data.count || 0
  }
}

const fetchCarOptions = async () => {
  const data = await request('/0x/chatgpt/car-enum')
  if (data) {
    carOptions.value = data.data || []
  }
}

const onPageChange = (pageInfo: any) => {
  pagination.current = pageInfo.current
  pagination.pageSize = pageInfo.pageSize
  fetchData()
}

const showAddDialog = () => {
  isEdit.value = false
  Object.assign(formData, {
    id: 0,
    username: '',
    password: '',
    is_active: true,
    isolated_session: true,
    force_chat_mode: true,
    expired_date: '',
    gptcar_list: [],
    model_limit: [],
    remark: '',
    daily_quota: 0,
    monthly_quota: 0
  })
  modelLimitInput.value = ''
  dialogVisible.value = true
}

const showEditDialog = (row: any) => {
  isEdit.value = true
  Object.assign(formData, {
    id: row.id,
    username: row.username,
    password: '',
    is_active: row.is_active,
    isolated_session: row.isolated_session ?? true,
    force_chat_mode: row.force_chat_mode ?? true,
    expired_date: row.expired_date || '',
    gptcar_list: row.gptcar_list || [],
    model_limit: row.model_limit || [],
    remark: row.remark || '',
    daily_quota: Number(row.daily_quota || 0),
    monthly_quota: Number(row.monthly_quota || 0)
  })
  modelLimitInput.value = (row.model_limit || []).join(', ')
  dialogVisible.value = true
}

const handleSubmit = async () => {
  const valid = await formRef.value?.validate()
  if (valid !== true) return

  submitLoading.value = true
  const modelLimit = modelLimitInput.value
    .split(/[,\n]/)
    .map(item => item.trim())
    .filter(Boolean)
  
  const url = '/0x/user'
  const method = 'POST'
  const payload = {
    username: formData.username,
    is_active: formData.is_active,
    isolated_session: formData.isolated_session,
    force_chat_mode: formData.force_chat_mode,
    gptcar_list: formData.gptcar_list,
    model_limit: modelLimit,
    remark: formData.remark,
    expired_date: formData.expired_date || null,
    daily_quota: formData.daily_quota,
    monthly_quota: formData.monthly_quota
  }

  if (formData.password.trim()) {
    Object.assign(payload, { password: formData.password })
  }

  const data = await request(url, method, payload)
  submitLoading.value = false

  if (data) {
    MessagePlugin.success(isEdit.value ? '更新成功' : '添加成功')
    dialogVisible.value = false
    fetchData()
  }
}

const handleDelete = async (row: any) => {
  const data = await request('/0x/user', 'DELETE', { username: row.username })
  if (data) {
    MessagePlugin.success('删除成功')
    fetchData()
  }
}

const loadStatistics = async () => {
  statisticsLoading.value = true
  const data = await request(`/0x/user/conversation-statistics/${statisticsUser.id}`)
  statisticsLoading.value = false
  if (!data) return
  Object.assign(statisticsData, {
    conversation_count: Number(data.conversation_count || 0),
    message_count: Number(data.message_count || 0),
    model_message_counts: data.model_message_counts || {},
    conversations: data.conversations || [],
    title_visible: Boolean(data.title_visible),
  })
}

const showStatisticsDialog = async (row: any) => {
  statisticsUser.id = Number(row.id)
  statisticsUser.username = row.username
  statisticsDialogVisible.value = true
  await loadStatistics()
}

const resetStatistics = async () => {
  const data = await request(
    `/0x/user/conversation-statistics/${statisticsUser.id}`,
    'DELETE',
  )
  if (data) {
    MessagePlugin.success(data.message || '对话统计已重置')
    await loadStatistics()
    await fetchData()
  }
}

const applyFilters = () => {
  pagination.current = 1
  fetchData()
}

const batchAction = async (action: 'activate' | 'deactivate') => {
  const data = await request('/0x/user/batch', 'POST', {
    user_id_list: selectedRowKeys.value.map(Number),
    action
  })
  if (data) {
    selectedRowKeys.value = []
    MessagePlugin.success(data.message)
    fetchData()
  }
}
</script>

<style scoped>
.text-gray {
  color: var(--app-text-muted);
}
.form-help {
  color: var(--app-text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.statistics-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}

.statistics-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: var(--app-surface-muted);
}

.statistics-card span,
.conversation-stat-meta {
  color: var(--app-text-muted);
  font-size: 13px;
}

.statistics-card strong {
  color: var(--app-text);
  font-size: 18px;
}

.statistics-section + .statistics-section {
  margin-top: 22px;
}

.statistics-section__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.statistics-section__title {
  margin-bottom: 10px;
  color: var(--app-text);
  font-size: 14px;
  font-weight: 600;
}

.statistics-section__head .statistics-section__title {
  margin-bottom: 0;
}

.conversation-stat-list {
  max-height: 320px;
  margin-top: 12px;
  overflow-y: auto;
  border: 1px solid var(--app-border);
  border-radius: 8px;
}

.conversation-stat-row {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
}

.conversation-stat-row + .conversation-stat-row {
  border-top: 1px solid var(--app-border);
}

.conversation-stat-title {
  min-width: 0;
  overflow: hidden;
  color: var(--app-text);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 760px) {
  .statistics-summary {
    grid-template-columns: 1fr;
  }
}
.table-toolbar {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) 160px auto auto auto;
  gap: 10px;
  margin-bottom: 16px;
}
</style>
