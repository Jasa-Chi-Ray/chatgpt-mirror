<template>
  <div>
    <t-card title="号池管理" :bordered="false">
      <template #actions>
        <t-button theme="primary" @click="showAddDialog">
          <template #icon><t-icon name="add" /></template>
          添加号池
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
        <template #gpt_account_list="{ row }">
          <t-tag v-for="id in row.gpt_account_list" :key="id" style="margin-right: 4px">
            {{ getAccountName(id) }}
          </t-tag>
          <span v-if="!row.gpt_account_list?.length">-</span>
        </template>
        <template #op="{ row }">
          <t-space>
            <t-link theme="primary" @click="showEditDialog(row)">编辑</t-link>
            <t-popconfirm content="确定删除该号池吗？" @confirm="handleDelete(row)">
              <t-link theme="danger">删除</t-link>
            </t-popconfirm>
          </t-space>
        </template>
      </t-table>
    </t-card>

    <!-- 添加/编辑对话框 -->
    <t-dialog
      :visible="dialogVisible"
      :header="isEdit ? '编辑号池' : '添加号池'"
      :confirm-btn="{ loading: submitLoading }"
      @confirm="handleSubmit"
      @close="dialogVisible = false"
    >
      <t-form :data="formData" :rules="formRules" ref="formRef" label-width="100px">
        <t-form-item label="号池名称" name="car_name">
          <t-input v-model="formData.car_name" placeholder="请输入号池名称" />
        </t-form-item>
        <t-form-item label="关联账号" name="gpt_account_list">
          <t-select v-model="formData.gpt_account_list" multiple placeholder="请选择 ChatGPT 账号">
            <t-option
              v-for="account in accountOptions"
              :key="account.id"
              :value="account.id"
              :label="`${account.chatgpt_username} (${account.plan_type})`"
            />
          </t-select>
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
const accountOptions = ref<any[]>([])
const accountMap = ref<Record<number, string>>({})

const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0
})

const columns = [
  { colKey: 'id', title: 'ID', width: 80 },
  { colKey: 'car_name', title: '号池名称' },
  { colKey: 'gpt_account_list', title: '关联账号', cell: 'gpt_account_list' },
  { colKey: 'remark', title: '备注', ellipsis: true },
  { colKey: 'op', title: '操作', cell: 'op', width: 150 }
]

const formData = reactive({
  id: 0,
  car_name: '',
  gpt_account_list: [] as number[],
  remark: ''
})

const formRules = {
  car_name: [{ required: true, message: '请输入号池名称' }]
}

onMounted(() => {
  fetchData()
  fetchAccountOptions()
})

const fetchData = async () => {
  loading.value = true
  const data = await request(`/0x/chatgpt/car?page=${pagination.current}&page_size=${pagination.pageSize}`)
  loading.value = false
  
  if (data) {
    tableData.value = data.results || []
    pagination.total = data.count || 0
  }
}

const fetchAccountOptions = async () => {
  const data = await request('/0x/chatgpt/enum')
  if (data) {
    accountOptions.value = data.data || []
    // 构建 ID 到名称的映射
    accountOptions.value.forEach((account: any) => {
      accountMap.value[account.id] = account.chatgpt_username
    })
  }
}

const getAccountName = (id: number) => {
  return accountMap.value[id] || `ID: ${id}`
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
    car_name: '',
    gpt_account_list: [],
    remark: ''
  })
  dialogVisible.value = true
}

const showEditDialog = (row: any) => {
  isEdit.value = true
  Object.assign(formData, {
    id: row.id,
    car_name: row.car_name,
    gpt_account_list: row.gpt_account_list || [],
    remark: row.remark || ''
  })
  dialogVisible.value = true
}

const handleSubmit = async () => {
  const valid = await formRef.value?.validate()
  if (valid !== true) return

  submitLoading.value = true
  
  const url = '/0x/chatgpt/car'
  const method = 'POST'
  const payload = isEdit.value ? {
    id: formData.id,
    car_name: formData.car_name,
    gpt_account_list: formData.gpt_account_list,
    remark: formData.remark
  } : {
    car_name: formData.car_name,
    gpt_account_list: formData.gpt_account_list,
    remark: formData.remark
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
  const data = await request('/0x/chatgpt/car', 'DELETE', { ids: [row.id] })
  if (data) {
    MessagePlugin.success('删除成功')
    fetchData()
  }
}
</script>
