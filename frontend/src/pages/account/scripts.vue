<template>
  <div>
    <t-card title="脚本" subtitle="管理注入到页面中的自定义代码" :bordered="false">
      <template #actions>
        <t-space>
          <t-button variant="outline" :loading="loading" @click="fetchConfig">
            刷新
          </t-button>
          <t-button theme="primary" @click="addScript">
            <template #icon><t-icon name="add" /></template>
            新增脚本
          </t-button>
        </t-space>
      </template>

      <t-form :data="formData" label-width="90px" class="script-form">
        <div class="script-list">
          <div v-for="script in formData.scripts" :key="script.localKey" class="script-row">
            <div class="script-title">
              <t-space>
                <t-input-number v-model="script.id" :min="1" theme="column" size="small" class="script-id" />
                <t-switch v-model="script.enabled" />
              </t-space>
              <t-button size="small" theme="danger" variant="outline" @click="removeScript(script.localKey)">
                删除
              </t-button>
            </div>

            <t-form-item label="名称">
              <t-input v-model="script.name" clearable placeholder="例如：隐藏顶部提示、注入统计脚本" />
            </t-form-item>

            <div class="script-meta">
              <t-form-item label="语言">
                <t-select v-model="script.language">
                  <t-option v-for="item in languageOptions" :key="item.value" :value="item.value" :label="item.label" />
                </t-select>
              </t-form-item>
              <t-form-item label="位置">
                <t-select v-model="script.position">
                  <t-option v-for="item in positionOptions" :key="item.value" :value="item.value" :label="item.label" />
                </t-select>
              </t-form-item>
            </div>

            <t-form-item label="内容">
              <t-textarea
                v-model="script.content"
                :autosize="{ minRows: 8, maxRows: 18 }"
                placeholder="CSS 会自动包裹 style；JavaScript 会自动包裹 script。"
              />
            </t-form-item>
          </div>
        </div>

        <div class="trusted-cdn-panel">
          <div class="trusted-cdn-title">可信 CDN 源</div>
          <div class="trusted-cdn-desc">
            每行一个来源。保存后会自动加入 Gateway 页面可信域名列表，仅接受以下格式：
            <code>https://example.com/*</code>
          </div>
          <t-textarea
            v-model="trustedCdnInput"
            :autosize="{ minRows: 4, maxRows: 10 }"
            placeholder="https://example.com/*"
          />
        </div>

        <t-form-item>
          <t-button theme="primary" :loading="saving" @click="handleSave">
            保存
          </t-button>
          <t-button variant="outline" @click="addScript">
            新增脚本
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

type ScriptForm = {
  localKey: number
  id: number
  enabled: boolean
  name: string
  language: string
  position: string
  content: string
}

const loading = ref(false)
const saving = ref(false)
const trustedCdnInput = ref('')
let nextLocalKey = 1

const formData = reactive<{ scripts: ScriptForm[] }>({
  scripts: []
})

const languageOptions = [
  { label: 'CSS', value: 'css' },
  { label: 'JavaScript', value: 'javascript' },
]

const positionOptions = [
  { label: 'head 开始', value: 'head_start' },
  { label: 'head 结束', value: 'head_end' },
  { label: 'body 开始', value: 'body_start' },
  { label: 'body 结束', value: 'body_end' }
]

onMounted(() => {
  fetchConfig()
})

const nextScriptId = () => {
  const ids = formData.scripts.map(script => Number(script.id) || 0)
  return Math.max(0, ...ids) + 1
}

const createScript = (data: any = {}): ScriptForm => ({
  localKey: nextLocalKey++,
  id: Number(data.id) || nextScriptId(),
  enabled: Boolean(data.enabled),
  name: data.name || '',
  language: data.language === 'javascript' ? 'javascript' : 'css',
  position: data.position || 'head_end',
  content: data.content || ''
})

const fetchConfig = async () => {
  loading.value = true
  const data = await request('/0x/user/custom-scripts')
  loading.value = false

  if (data) {
    formData.scripts.splice(0, formData.scripts.length, ...(data.scripts || []).map(createScript))
    trustedCdnInput.value = (data.trusted_cdn_sources || []).join('\n')
  }
}

const addScript = () => {
  formData.scripts.push(createScript({ enabled: true }))
}

const removeScript = (localKey: number) => {
  const index = formData.scripts.findIndex(script => script.localKey === localKey)
  if (index >= 0) {
    formData.scripts.splice(index, 1)
  }
}

const serializeScripts = () => formData.scripts.map(script => ({
  id: Number(script.id),
  enabled: script.enabled,
  name: script.name.trim(),
  language: script.language,
  position: script.position,
  content: script.content
})).filter(script => script.id > 0)

const serializeTrustedCdnSources = () => trustedCdnInput.value
  .split(/[\n,]/)
  .map(source => source.trim())
  .filter(Boolean)

const validateScripts = () => {
  const ids = new Set<number>()
  for (const script of serializeScripts()) {
    if (ids.has(script.id)) {
      MessagePlugin.warning(`脚本 ${script.id} 重复`)
      return false
    }
    ids.add(script.id)
    if (script.enabled && !script.content.trim()) {
      MessagePlugin.warning(`脚本 ${script.id} 已启用，请填写内容`)
      return false
    }
  }
  for (const source of serializeTrustedCdnSources()) {
    if (!/^https:\/\/[^/\s]+\/\*$/.test(source)) {
      MessagePlugin.warning(`可信 CDN 格式错误：${source}`)
      return false
    }
  }
  return true
}

const handleSave = async () => {
  if (!validateScripts()) {
    return
  }

  saving.value = true
  const data = await request('/0x/user/custom-scripts', 'POST', {
    scripts: serializeScripts(),
    trusted_cdn_sources: serializeTrustedCdnSources(),
  })
  saving.value = false

  if (data) {
    formData.scripts.splice(0, formData.scripts.length, ...(data.scripts || []).map(createScript))
    trustedCdnInput.value = (data.trusted_cdn_sources || []).join('\n')
    MessagePlugin.success('保存成功')
  }
}
</script>

<style scoped>
.script-form {
  max-width: 1080px;
}

.script-list {
  display: grid;
  gap: 16px;
  width: 100%;
}

.script-row {
  padding: 18px;
  border: 1px solid var(--app-border);
  border-radius: 10px;
  background: #fafaf8;
}

.script-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.script-id {
  width: 120px;
}

.script-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.trusted-cdn-panel {
  margin: 18px 0;
  padding: 18px;
  border: 1px solid var(--app-border);
  border-radius: 10px;
  background: var(--app-surface);
}

.trusted-cdn-title {
  color: var(--app-text);
  font-size: 14px;
  font-weight: 600;
}

.trusted-cdn-desc {
  margin: 6px 0 12px;
  color: var(--app-text-muted);
  font-size: 13px;
  line-height: 1.6;
}

.trusted-cdn-desc code {
  padding: 2px 5px;
  border-radius: 4px;
  background: var(--app-surface-muted);
  color: var(--app-text);
}

@media (max-width: 760px) {
  .script-meta {
    grid-template-columns: 1fr;
  }
}
</style>
