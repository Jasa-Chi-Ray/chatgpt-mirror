<template>
  <div>
    <t-card title="模型管理" :bordered="false">
      <template #actions>
        <t-button theme="primary" @click="showAddDialog">
          <template #icon><t-icon name="add" /></template>
          添加模型
        </t-button>
      </template>

      <t-table
        :data="tableData"
        :columns="columns"
        :loading="loading"
        row-key="id"
      >
        <template #enabled="{ row }">
          <t-switch 
            :value="row.enabled" 
            @change="(val: boolean) => handleToggle(row, val)"
          />
        </template>
        <template #op="{ row }">
          <t-space>
            <t-link theme="primary" @click="showEditDialog(row)">编辑</t-link>
            <t-popconfirm content="确定删除该模型吗？" @confirm="handleDelete(row)">
              <t-link theme="danger">删除</t-link>
            </t-popconfirm>
          </t-space>
        </template>
      </t-table>
    </t-card>

    <!-- 添加/编辑对话框 -->
    <t-dialog
      :visible="dialogVisible"
      :header="isEdit ? '编辑模型' : '添加模型'"
      :confirm-btn="{ loading: submitLoading }"
      @confirm="handleSubmit"
      @close="dialogVisible = false"
    >
      <t-form :data="formData" :rules="formRules" ref="formRef" label-width="100px">
        <t-form-item label="模型ID" name="id">
          <t-input 
            v-model="formData.id" 
            :disabled="isEdit" 
            placeholder="请输入模型ID，如 gpt-4o" 
          />
        </t-form-item>
        <t-form-item label="显示名称" name="name">
          <t-input v-model="formData.name" placeholder="请输入显示名称" />
        </t-form-item>
        <t-form-item label="描述" name="description">
          <t-textarea v-model="formData.description" placeholder="请输入模型描述" />
        </t-form-item>
        <t-form-item label="启用" name="enabled">
          <t-switch v-model="formData.enabled" />
        </t-form-item>
      </t-form>
    </t-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import request from '@/api/request'

interface ModelInfo {
  id: string
  name: string
  description: string
  enabled: boolean
}

const loading = ref(false)
const submitLoading = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const formRef = ref()
const tableData = ref<ModelInfo[]>([])

const columns = [
  { colKey: 'id', title: '模型ID', width: 150 },
  { colKey: 'name', title: '显示名称', width: 150 },
  { colKey: 'description', title: '描述', ellipsis: true },
  { colKey: 'enabled', title: '启用', cell: 'enabled', width: 100 },
  { colKey: 'op', title: '操作', cell: 'op', width: 150 }
]

const formData = reactive<ModelInfo>({
  id: '',
  name: '',
  description: '',
  enabled: true
})

const formRules = {
  id: [{ required: true, message: '请输入模型ID' }],
  name: [{ required: true, message: '请输入显示名称' }]
}

onMounted(() => {
  fetchData()
})

const fetchData = async () => {
  loading.value = true
  const data = await request('/0x/models')
  loading.value = false
  
  if (data) {
    tableData.value = data.models || []
  }
}

const showAddDialog = () => {
  isEdit.value = false
  Object.assign(formData, {
    id: '',
    name: '',
    description: '',
    enabled: true
  })
  dialogVisible.value = true
}

const showEditDialog = (row: ModelInfo) => {
  isEdit.value = true
  Object.assign(formData, {
    id: row.id,
    name: row.name,
    description: row.description || '',
    enabled: row.enabled
  })
  dialogVisible.value = true
}

const handleSubmit = async () => {
  const valid = await formRef.value?.validate()
  if (valid !== true) return

  submitLoading.value = true
  
  let data
  if (isEdit.value) {
    // 编辑时更新整个列表
    const updatedModels = tableData.value.map(m => 
      m.id === formData.id ? { ...formData } : m
    )
    data = await request('/0x/models', 'PUT', { models: updatedModels })
  } else {
    // 添加新模型
    data = await request('/0x/models', 'POST', formData)
  }
  
  submitLoading.value = false

  if (data) {
    MessagePlugin.success(isEdit.value ? '更新成功' : '添加成功')
    dialogVisible.value = false
    fetchData()
  }
}

const handleToggle = async (row: ModelInfo, enabled: boolean) => {
  const data = await request('/0x/models/toggle', 'PUT', {
    id: row.id,
    enabled
  })
  
  if (data) {
    MessagePlugin.success('状态更新成功')
    fetchData()
  }
}

const handleDelete = async (row: ModelInfo) => {
  const data = await request('/0x/models', 'DELETE', { id: row.id })
  if (data) {
    MessagePlugin.success('删除成功')
    fetchData()
  }
}
</script>
