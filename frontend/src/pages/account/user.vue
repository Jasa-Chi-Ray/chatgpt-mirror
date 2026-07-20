<template>
  <div>
    <t-card title="用户管理" :bordered="false">
      <template #actions>
        <t-button theme="primary" @click="showAddDialog">
          <template #icon><t-icon name="add" /></template>
          添加用户
        </t-button>
      </template>

      <t-table
        :data="tableData"
        :columns="columns"
        :loading="loading"
        :pagination="pagination"
        @page-change="onPageChange"
        row-key="id"
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
        <template #op="{ row }">
          <t-space>
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
        <t-form-item label="过期日期" name="expired_date">
          <t-date-picker v-model="formData.expired_date" placeholder="留空则永久有效" />
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
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
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

const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0
})

const columns = [
  { colKey: 'id', title: 'ID', width: 80 },
  { colKey: 'username', title: '用户名' },
  { colKey: 'is_active', title: '状态', cell: 'is_active', width: 80 },
  { colKey: 'model_limit', title: '模型限制', cell: 'model_limit', width: 180 },
  { colKey: 'expired_date', title: '过期日期', cell: 'expired_date', width: 120 },
  { colKey: 'remark', title: '备注', ellipsis: true },
  { colKey: 'op', title: '操作', cell: 'op', width: 150 }
]

const formData = reactive({
  id: 0,
  username: '',
  password: '',
  is_active: true,
  isolated_session: true,
  expired_date: '',
  gptcar_list: [] as number[],
  model_limit: [] as string[],
  remark: ''
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
  const data = await request(`/0x/user?page=${pagination.current}&page_size=${pagination.pageSize}`)
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
    expired_date: '',
    gptcar_list: [],
    model_limit: [],
    remark: ''
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
    expired_date: row.expired_date || '',
    gptcar_list: row.gptcar_list || [],
    model_limit: row.model_limit || [],
    remark: row.remark || ''
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
    gptcar_list: formData.gptcar_list,
    model_limit: modelLimit,
    remark: formData.remark
  }

  if (formData.password.trim()) {
    Object.assign(payload, { password: formData.password })
  }

  if (formData.expired_date) {
    Object.assign(payload, { expired_date: formData.expired_date })
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
</script>

<style scoped>
.text-gray {
  color: #999;
}
.form-help {
  color: #999;
  font-size: 12px;
}
</style>
