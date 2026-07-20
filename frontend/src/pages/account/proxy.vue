<template>
  <div>
    <t-card title="代理" :bordered="false">
      <t-form :data="formData" label-width="110px" class="proxy-form">
        <t-form-item label="节点">
          <template #help>
            <span class="form-help">账号不绑定节点时直连；绑定节点后，只有需要代理的上游域名走该节点。</span>
          </template>
          <div class="node-list">
            <div v-for="node in formData.nodes" :key="node.localKey" class="node-row">
              <div class="node-title">
                <t-input-number
                  v-model="node.id"
                  :min="1"
                  theme="column"
                  size="small"
                  class="node-id"
                />
                <t-switch v-model="node.enabled" />
              </div>
              <t-input
                v-model="node.proxy_url"
                :disabled="!node.enabled"
                clearable
                placeholder="socks5://user:pass@127.0.0.1:1080"
              />
              <t-input
                v-model="node.username"
                :disabled="!node.enabled"
                clearable
                placeholder="用户名"
              />
              <t-input
                v-model="node.password"
                :disabled="!node.enabled"
                type="password"
                clearable
                placeholder="密码"
              />
              <div class="node-actions">
                <t-button size="small" variant="outline" :loading="testingNodeId === node.localKey" @click="handleTestNode(node)">
                  测试
                </t-button>
                <t-button size="small" theme="danger" variant="outline" @click="removeNode(node.localKey)">
                  删除
                </t-button>
              </div>
            </div>
          </div>
        </t-form-item>
        <t-form-item>
          <t-button theme="primary" :loading="saving" @click="handleSave">
            保存
          </t-button>
          <t-button variant="outline" @click="addNode">
            新增节点
          </t-button>
          <t-button variant="outline" :loading="loading" @click="fetchConfig">
            刷新
          </t-button>
        </t-form-item>
      </t-form>
    </t-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import request from '@/api/request'

const loading = ref(false)
const saving = ref(false)
const testingNodeId = ref<number | null>(null)

type ProxyNodeForm = {
  localKey: number
  id: number
  enabled: boolean
  proxy_url: string
  username: string
  password: string
}

let nextLocalKey = 1

const formData = reactive<{ nodes: ProxyNodeForm[] }>({
  nodes: []
})

const nextNodeId = (): number => {
  const ids = formData.nodes.map((node: ProxyNodeForm) => Number(node.id) || 0)
  return Math.max(0, ...ids) + 1
}

const createNode = (data: any = {}): ProxyNodeForm => ({
  localKey: nextLocalKey++,
  id: Number(data.id) || nextNodeId(),
  enabled: Boolean(data.enabled),
  proxy_url: data.proxy_url || '',
  username: data.username || '',
  password: data.password || ''
})

onMounted(() => {
  fetchConfig()
})

const fetchConfig = async () => {
  loading.value = true
  const data = await request('/0x/user/proxy-config')
  loading.value = false

  if (data) {
    applyNodes(data.nodes || [])
  }
}

const applyNodes = (nodes: any[]) => {
  formData.nodes.splice(0, formData.nodes.length, ...nodes.map(node => createNode(node)))
}

const serializeNodes = () => formData.nodes.map(node => ({
  id: Number(node.id),
  enabled: node.enabled,
  proxy_url: node.proxy_url.trim(),
  username: node.username.trim(),
  password: node.password.trim()
})).filter(node => node.id > 0)

const validateNodes = () => {
  const ids = new Set<number>()
  for (const node of serializeNodes()) {
    if (ids.has(node.id)) {
      MessagePlugin.warning(`节点 ${node.id} 重复`)
      return false
    }
    ids.add(node.id)
    if (node.enabled && !node.proxy_url) {
      MessagePlugin.warning(`节点 ${node.id} 已启用，请填写代理地址`)
      return false
    }
  }
  return true
}

const handleSave = async () => {
  if (!validateNodes()) {
    return
  }

  saving.value = true
  const data = await request('/0x/user/proxy-config', 'POST', {
    nodes: serializeNodes()
  })
  saving.value = false

  if (data) {
    applyNodes(data.nodes || [])
    MessagePlugin.success('保存成功')
  }
}

const addNode = () => {
  formData.nodes.push(createNode())
}

const removeNode = (localKey: number) => {
  const index = formData.nodes.findIndex(node => node.localKey === localKey)
  if (index >= 0) {
    formData.nodes.splice(index, 1)
  }
}

const handleTestNode = async (node: ProxyNodeForm) => {
  if (!node.enabled) {
    MessagePlugin.warning('请先启用该节点')
    return
  }
  if (!node.proxy_url.trim()) {
    MessagePlugin.warning('请输入节点代理地址')
    return
  }

  testingNodeId.value = node.localKey
  const data = await request('/0x/user/proxy-config/test', 'POST', {
    enabled: node.enabled,
    proxy_url: node.proxy_url.trim(),
    username: node.username.trim(),
    password: node.password.trim()
  })
  testingNodeId.value = null

  if (data) {
    MessagePlugin.success(data.message || `节点 ${node.id} 连接正常`)
  }
}
</script>

<style scoped>
.proxy-form {
  max-width: 960px;
}

.proxy-form :deep(.t-button + .t-button) {
  margin-left: 12px;
}

.node-list {
  width: 100%;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.node-row {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
  padding: 12px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  background: #fff;
}

.node-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.node-id {
  width: 120px;
}

.node-actions {
  display: flex;
  gap: 8px;
}

@media (max-width: 900px) {
  .node-list {
    grid-template-columns: 1fr;
  }
}
</style>
