<template>
  <div>
    <t-card title="代理" subtitle="为指定上游账号配置独立的网络出口" :bordered="false">
      <t-form :data="formData" label-width="110px" class="proxy-form">
        <t-form-item label="HTTP 传输">
          <template #help>
            <span class="form-help">
              reqwest 为稳定模式；wreq 使用 Chrome 149 风格的 TLS/HTTP2。切换会立即重建直连及所有节点连接池，不保证阻止上游模型回退。
            </span>
          </template>
          <div class="transport-control">
            <t-radio-group
              v-model="formData.transport_mode"
              variant="default-filled"
              :disabled="saving"
              @change="handleTransportChange"
            >
              <t-radio-button value="reqwest">reqwest</t-radio-button>
              <t-radio-button value="wreq">wreq</t-radio-button>
            </t-radio-group>
            <t-tag theme="primary" variant="light">当前：{{ formData.transport_mode }}</t-tag>
          </div>
        </t-form-item>
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
                :placeholder="node.has_password ? '已保存（留空保持不变）' : '密码'"
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
          <t-button theme="primary" :loading="saving" @click="handleSave()">
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
const lastSavedTransportMode = ref<TransportMode>('reqwest')

type ProxyNodeForm = {
  localKey: number
  id: number
  enabled: boolean
  proxy_url: string
  username: string
  password: string
  has_password: boolean
}

let nextLocalKey = 1

type TransportMode = 'reqwest' | 'wreq'

const formData = reactive<{ transport_mode: TransportMode; nodes: ProxyNodeForm[] }>({
  transport_mode: 'reqwest',
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
  password: data.password || '',
  has_password: Boolean(data.has_password)
})

onMounted(() => {
  fetchConfig()
})

const fetchConfig = async () => {
  loading.value = true
  const data = await request('/0x/user/proxy-config')
  loading.value = false

  if (data) {
    formData.transport_mode = data.transport_mode === 'wreq' ? 'wreq' : 'reqwest'
    lastSavedTransportMode.value = formData.transport_mode
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

const handleSave = async (transportChanged = false) => {
  if (!validateNodes()) {
    if (transportChanged) {
      formData.transport_mode = lastSavedTransportMode.value
    }
    return
  }

  saving.value = true
  const data = await request('/0x/user/proxy-config', 'POST', {
    transport_mode: formData.transport_mode,
    nodes: serializeNodes()
  })
  saving.value = false

  if (data) {
    formData.transport_mode = data.transport_mode === 'wreq' ? 'wreq' : 'reqwest'
    lastSavedTransportMode.value = formData.transport_mode
    applyNodes(data.nodes || [])
    MessagePlugin.success(transportChanged ? `已切换为 ${formData.transport_mode}` : '保存成功')
  } else if (transportChanged) {
    formData.transport_mode = lastSavedTransportMode.value
  }
}

const handleTransportChange = (value: TransportMode) => {
  formData.transport_mode = value
  handleSave(true)
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
    transport_mode: formData.transport_mode,
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

.transport-control {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
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
  gap: 10px;
  padding: 18px;
  border: 1px solid var(--app-border);
  border-radius: 10px;
  background: #fafaf8;
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
