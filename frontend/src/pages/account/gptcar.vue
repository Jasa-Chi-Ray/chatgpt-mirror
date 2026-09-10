<template>
  <div>
    <t-card title="账号池" subtitle="将上游账号按使用场景组织为不同账号池" :bordered="false">
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
            <t-link theme="primary" @click="showDetailDialog(row)">详情</t-link>
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
          <t-select v-model="formData.gpt_account_list" multiple placeholder="请选择上游账号">
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

    <t-dialog
      :visible="detailVisible"
      :header="detailData ? `号池详情 · ${detailData.car_name}` : '号池详情'"
      :confirm-btn="null"
      cancel-btn="关闭"
      width="860px"
      @close="detailVisible = false"
    >
      <t-loading :loading="detailLoading">
        <template v-if="detailData">
          <t-table
            v-if="detailData.assigned_users.length"
            :data="detailData.assigned_users"
            :columns="detailColumns"
            row-key="id"
            :pagination="null"
          >
            <template #is_active="{ row }">
              <t-tag size="small" :theme="row.is_active ? 'success' : 'warning'">
                {{ row.is_active ? '正常' : '停用' }}
              </t-tag>
            </template>
            <template #expired_date="{ row }">
              <span>{{ row.expired_date || '未设置' }}</span>
            </template>
            <template #op="{ row }">
              <t-popconfirm
                content="确定将该用户移出当前号池吗？"
                @confirm="removeUserFromCar(row)"
              >
                <t-link theme="danger" :disabled="assignmentLoading">踢出</t-link>
              </t-popconfirm>
            </template>
          </t-table>
          <t-empty v-else description="该号池尚未分配给任何用户" />
          <div class="detail-actions">
            <t-button
              theme="primary"
              :disabled="!detailData.available_users.length"
              @click="showAddUserDialog"
            >
              <template #icon><t-icon name="user-add" /></template>
              加入用户
            </t-button>
          </div>
        </template>
      </t-loading>
    </t-dialog>

    <t-dialog
      :visible="addUserVisible"
      header="加入用户"
      :confirm-btn="{ content: '加入', loading: assignmentLoading, disabled: !selectedUserIds.length }"
      @confirm="addUsersToCar"
      @close="addUserVisible = false"
    >
      <t-form label-width="90px">
        <t-form-item label="选择用户">
          <t-select
            v-model="selectedUserIds"
            multiple
            filterable
            clearable
            placeholder="请选择要加入当前号池的用户"
          >
            <t-option
              v-for="user in detailData?.available_users || []"
              :key="user.id"
              :value="user.id"
              :label="`${user.username}${user.is_active ? '' : '（停用）'}`"
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

const loading = ref(false)
const submitLoading = ref(false)
const dialogVisible = ref(false)
const detailVisible = ref(false)
const detailLoading = ref(false)
const addUserVisible = ref(false)
const assignmentLoading = ref(false)
const selectedUserIds = ref<number[]>([])
const isEdit = ref(false)
const formRef = ref()
const tableData = ref<any[]>([])
const accountOptions = ref<any[]>([])
const accountMap = ref<Record<number, string>>({})

type AssignedUser = {
  id: number
  username: string
  is_active: boolean
  expired_date: string | null
}

type GptCarDetail = {
  id: number
  car_name: string
  remark: string
  assigned_users: AssignedUser[]
  available_users: AssignedUser[]
}

const detailData = ref<GptCarDetail | null>(null)

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
  { colKey: 'op', title: '操作', cell: 'op', width: 190 }
]

const detailColumns = [
  { colKey: 'username', title: '用户名' },
  { colKey: 'is_active', title: '状态', cell: 'is_active', width: 100 },
  { colKey: 'expired_date', title: '账号到期时间', cell: 'expired_date', width: 160 },
  { colKey: 'op', title: '操作', cell: 'op', width: 90 }
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

const showDetailDialog = async (row: any) => {
  detailVisible.value = true
  detailData.value = null
  await fetchCarDetail(row.id)
}

const fetchCarDetail = async (carId: number) => {
  detailLoading.value = true
  const data = await request(`/0x/chatgpt/car/${carId}/detail`)
  detailLoading.value = false
  if (data) detailData.value = data
}

const showAddUserDialog = () => {
  selectedUserIds.value = []
  addUserVisible.value = true
}

const addUsersToCar = async () => {
  if (!detailData.value || !selectedUserIds.value.length) return
  assignmentLoading.value = true
  const carId = detailData.value.id
  const data = await request(`/0x/chatgpt/car/${carId}/users`, 'POST', {
    user_ids: selectedUserIds.value,
  })
  assignmentLoading.value = false
  if (!data) return
  MessagePlugin.success('用户已加入号池')
  addUserVisible.value = false
  await fetchCarDetail(carId)
}

const removeUserFromCar = async (user: AssignedUser) => {
  if (!detailData.value) return
  assignmentLoading.value = true
  const carId = detailData.value.id
  const data = await request(`/0x/chatgpt/car/${carId}/users`, 'DELETE', {
    user_ids: [user.id],
  })
  assignmentLoading.value = false
  if (!data) return
  MessagePlugin.success('用户已移出号池')
  await fetchCarDetail(carId)
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

<style scoped>
.detail-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
