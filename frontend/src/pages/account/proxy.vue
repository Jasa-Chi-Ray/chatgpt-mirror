<template>
  <div class="workspace-page settings-page proxy-page">
    <t-card :title="t('代理')" :subtitle="t('为指定上游账号配置独立的网络出口')" :bordered="false">
      <t-form :data="formData" label-width="110px" class="proxy-form">
        <t-form-item :label="t('HTTP 传输')">
          <template #help>
            <div class="transport-help">
              <span><strong>reqwest：</strong>{{ t('已废弃，保留旧配置兼容；不模拟浏览器网络指纹。') }}</span>
              <span><strong>wreq：</strong>{{ t('不稳定模式，使用 Chrome 146 风格的 TLS/HTTP2 和持久连接池。') }}</span>
              <span><strong>curl-impersonate：</strong>{{ t('稳定模式，首次部署默认启用；使用 Chrome 146 风格的 TLS/HTTP2 和 libcurl Multi。') }}</span>
              <span>{{ t('切换后会立即重建直连、节点及账号连接池。') }}</span>
            </div>
          </template>
          <div class="transport-control">
            <t-radio-group
              v-model="formData.transport_mode"
              variant="outline"
              :disabled="saving"
              @change="handleTransportChange"
            >
              <t-radio-button value="reqwest">{{ t('reqwest（已废弃）') }}</t-radio-button>
              <t-radio-button value="wreq">{{ t('wreq（不稳定）') }}</t-radio-button>
              <t-radio-button value="curl-impersonate">{{ t('curl-impersonate（稳定 · 默认）') }}</t-radio-button>
            </t-radio-group>
            <t-tag theme="primary" variant="light">{{ t('当前：') }}{{ formData.transport_mode }}</t-tag>
          </div>
        </t-form-item>
        <t-form-item :label="t('节点')">
          <template #help>
            <span class="form-help">{{ t('账号不绑定节点时直连；绑定节点后，只有需要代理的上游域名走该节点。') }}</span>
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
                :placeholder="t('用户名')"
              />
              <t-input
                v-model="node.password"
                :disabled="!node.enabled"
                type="password"
                clearable
                :placeholder="node.has_password ? t('已保存（留空保持不变）') : t('密码')"
              />
              <div class="node-actions">
                <t-button size="small" variant="outline" :loading="testingNodeId === node.localKey" @click="handleTestNode(node)">
                  {{ t('测试') }}
                </t-button>
                <t-button size="small" theme="danger" variant="outline" @click="removeNode(node.localKey)">
                  {{ t('删除') }}
                </t-button>
              </div>
            </div>
          </div>
        </t-form-item>
        <t-form-item>
          <t-button theme="primary" :loading="saving" @click="handleSave()">
            {{ t('保存') }}
          </t-button>
          <t-button variant="outline" @click="addNode">
            {{ t('新增节点') }}
          </t-button>
          <t-button variant="outline" :loading="loading" @click="fetchConfig">
            {{ t('刷新') }}
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
import { useWorkspaceCopy } from '@/pages/account/workspace-copy'

const { t } = useWorkspaceCopy()

const loading = ref(false)
const saving = ref(false)
const testingNodeId = ref<number | null>(null)
const lastSavedTransportMode = ref<TransportMode>('curl-impersonate')

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

type TransportMode = 'reqwest' | 'wreq' | 'curl-impersonate'

const normalizeTransportMode = (value: unknown): TransportMode => {
  if (value === 'reqwest' || value === 'wreq' || value === 'curl-impersonate') {
    return value
  }
  return 'curl-impersonate'
}

const formData = reactive<{ transport_mode: TransportMode; nodes: ProxyNodeForm[] }>({
  transport_mode: 'curl-impersonate',
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
    formData.transport_mode = normalizeTransportMode(data.transport_mode)
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
      MessagePlugin.warning(t('节点 {0} 重复', [node.id]))
      return false
    }
    ids.add(node.id)
    if (node.enabled && !node.proxy_url) {
      MessagePlugin.warning(t('节点 {0} 已启用，请填写代理地址', [node.id]))
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
    formData.transport_mode = normalizeTransportMode(data.transport_mode)
    lastSavedTransportMode.value = formData.transport_mode
    applyNodes(data.nodes || [])
    MessagePlugin.success(transportChanged ? t('已切换为 {0}', [formData.transport_mode]) : t('保存成功'))
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
    MessagePlugin.warning(t('请先启用该节点'))
    return
  }
  if (!node.proxy_url.trim()) {
    MessagePlugin.warning(t('请输入节点代理地址'))
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
    MessagePlugin.success(data.message || t('节点 {0} 连接正常', [node.id]))
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

.transport-control :deep(.t-radio-group) {
  max-width: 100%;
  height: auto;
  flex-wrap: wrap;
  row-gap: 8px;
}

.transport-help {
  display: grid;
  gap: 4px;
  line-height: 1.6;
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
  background: var(--app-field);
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
