<template>
  <div class="moderation-page">
    <t-card
      title="政治敏感内容屏蔽"
      subtitle="在消息转发给 ChatGPT 上游前，通过独立后端模型进行判定"
      :bordered="false"
    >
      <div class="status-row">
        <div>
          <div class="status-title">启用内容审查</div>
          <div class="status-description">仅命中国家、政党、战争等候选词的用户消息会送审；审查服务故障时阻止发送。</div>
        </div>
        <t-switch v-model="form.enabled" />
      </div>

      <t-divider />

      <t-form :data="form" label-width="132px" class="moderation-form">
        <t-form-item label="审查强度" name="mode">
          <t-radio-group v-model="form.mode" variant="default-filled">
            <t-radio-button value="relaxed">宽松版</t-radio-button>
            <t-radio-button value="strict">严格版</t-radio-button>
          </t-radio-group>
          <template #help>
            <span class="field-help">
              {{ form.mode === 'relaxed'
                ? '允许普通地理、旅行和中立事实讨论，以及不站队的历史与趋势分析；拒绝政治站队、归责说服、煽动仇恨和现实争议定性。'
                : '国家名和地理位置可正常询问；仅当主要意图实质涉及现实政治、政府政党、战争军事、领土主权或外交制裁时拒绝。' }}
            </span>
          </template>
        </t-form-item>

        <t-form-item label="API 格式" name="protocol">
          <t-select v-model="form.protocol" @change="applyProtocolDefault">
            <t-option v-for="item in protocolOptions" :key="item.value" :value="item.value" :label="item.label" />
          </t-select>
        </t-form-item>

        <t-form-item label="Base URL" name="base_url">
          <t-input v-model="form.base_url" clearable :placeholder="activeProtocol.baseUrl" />
          <template #help>
            <span class="field-help"><strong>{{ activeProtocol.versionHint }}</strong> {{ activeProtocol.appendHint }}</span>
          </template>
        </t-form-item>

        <t-form-item label="模型" name="model">
          <t-input v-model="form.model" clearable :placeholder="activeProtocol.modelPlaceholder" />
        </t-form-item>

        <t-form-item label="API 密钥" name="api_key">
          <t-input v-model="form.api_key" type="password" clearable placeholder="留空表示继续使用已保存的密钥" />
          <template #help>
            <span class="field-help">
              密钥只提交给 Gateway 并加密保存；
              <t-tag size="small" :theme="apiKeyConfigured ? 'success' : 'default'" variant="light">
                {{ apiKeyConfigured ? '已配置' : '未配置' }}
              </t-tag>
            </span>
          </template>
        </t-form-item>

        <t-form-item label="自定义限制词" name="custom_terms">
          <t-textarea
            v-model="form.custom_terms"
            :autosize="{ minRows: 4, maxRows: 8 }"
            placeholder="每行或用逗号分隔一个词，最多 200 个"
          />
          <template #help>
            <span class="field-help">自定义词会追加到内置候选词；命中后才调用审查模型，不会直接判定违规。</span>
          </template>
        </t-form-item>

        <t-form-item label="单用户审查频率">
          <div class="rate-limit-grid">
            <label>
              <span>每分钟</span>
              <t-input-number v-model="form.limit_per_minute" :min="1" :max="10000" theme="normal" />
            </label>
            <label>
              <span>每五分钟</span>
              <t-input-number v-model="form.limit_per_five_minutes" :min="1" :max="10000" theme="normal" />
            </label>
            <label>
              <span>每小时</span>
              <t-input-number v-model="form.limit_per_hour" :min="1" :max="10000" theme="normal" />
            </label>
          </div>
          <template #help>
            <span class="field-help">只统计实际调用审查模型的消息；达到任一上限后，本次发送会被阻止。</span>
          </template>
        </t-form-item>

        <t-form-item>
          <t-space>
            <t-button variant="outline" :loading="testing" @click="testConnection">验证模型与规则</t-button>
            <t-button theme="primary" :loading="saving" @click="saveConfig">保存配置</t-button>
          </t-space>
        </t-form-item>
      </t-form>

      <t-alert
        theme="warning"
        message="审查模型只接收命中候选词的本次用户文本。请使用专门的低权限密钥；不要把 ChatGPT 账号 AccessToken 或 SessionToken 填到这里。"
      />
    </t-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import request from '@/api/request'

type Protocol = 'openai_chat' | 'anthropic_messages' | 'gemini_generate_content' | 'openai_responses'

const protocolOptions = [
  {
    value: 'openai_chat' as Protocol,
    label: 'OpenAI Chat Completions',
    baseUrl: 'https://api.openai.com/v1',
    versionHint: '需要包含 /v1。',
    appendHint: 'Gateway 会自动追加 /chat/completions。',
    modelPlaceholder: '例如 gpt-4.1-mini',
  },
  {
    value: 'anthropic_messages' as Protocol,
    label: 'Anthropic Messages',
    baseUrl: 'https://api.anthropic.com/v1',
    versionHint: '需要包含 /v1。',
    appendHint: 'Gateway 会自动追加 /messages。',
    modelPlaceholder: '例如 claude-3-5-haiku-latest',
  },
  {
    value: 'gemini_generate_content' as Protocol,
    label: 'Gemini GenerateContent',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta',
    versionHint: '需要包含 /v1beta。',
    appendHint: 'Gateway 会自动追加 /models/{模型}:generateContent。',
    modelPlaceholder: '例如 gemini-2.5-flash',
  },
  {
    value: 'openai_responses' as Protocol,
    label: 'OpenAI Responses API',
    baseUrl: 'https://api.openai.com/v1',
    versionHint: '需要包含 /v1。',
    appendHint: 'Gateway 会自动追加 /responses。',
    modelPlaceholder: '例如 gpt-4.1-mini',
  },
]

const form = reactive({
  enabled: false,
  protocol: 'openai_chat' as Protocol,
  mode: 'relaxed' as 'relaxed' | 'strict',
  base_url: 'https://api.openai.com/v1',
  model: '',
  api_key: '',
  custom_terms: '',
  limit_per_minute: 10,
  limit_per_five_minutes: 30,
  limit_per_hour: 120,
})
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const apiKeyConfigured = ref(false)
const activeProtocol = computed(() => protocolOptions.find(item => item.value === form.protocol) || protocolOptions[0])

const loadConfig = async () => {
  loading.value = true
  const data = await request('/0x/user/political-moderation')
  loading.value = false
  if (!data) return
  Object.assign(form, {
    enabled: Boolean(data.enabled),
    protocol: data.protocol || 'openai_chat',
    mode: data.mode || 'relaxed',
    base_url: data.base_url || 'https://api.openai.com/v1',
    model: data.model || '',
    api_key: '',
    custom_terms: Array.isArray(data.custom_terms) ? data.custom_terms.join('\n') : '',
    limit_per_minute: Number(data.limit_per_minute) || 10,
    limit_per_five_minutes: Number(data.limit_per_five_minutes) || 30,
    limit_per_hour: Number(data.limit_per_hour) || 120,
  })
  apiKeyConfigured.value = Boolean(data.api_key_configured)
}

const applyProtocolDefault = () => {
  form.base_url = activeProtocol.value.baseUrl
}

const validate = () => {
  if (!form.base_url.trim()) {
    MessagePlugin.warning('请输入 Base URL')
    return false
  }
  if (!form.model.trim()) {
    MessagePlugin.warning('请输入模型名称')
    return false
  }
  if (!form.api_key.trim() && !apiKeyConfigured.value) {
    MessagePlugin.warning('请输入 API 密钥')
    return false
  }
  if (form.limit_per_minute > form.limit_per_five_minutes || form.limit_per_five_minutes > form.limit_per_hour) {
    MessagePlugin.warning('频率限制必须满足：每分钟 ≤ 每五分钟 ≤ 每小时')
    return false
  }
  return true
}

const customTerms = () => Array.from(new Set(
  form.custom_terms
    .split(/[\n,，]/)
    .map(item => item.trim())
    .filter(Boolean),
))

const payload = () => ({
  enabled: form.enabled,
  protocol: form.protocol,
  mode: form.mode,
  base_url: form.base_url.trim(),
  model: form.model.trim(),
  api_key: form.api_key.trim(),
  custom_terms: customTerms(),
  limit_per_minute: form.limit_per_minute,
  limit_per_five_minutes: form.limit_per_five_minutes,
  limit_per_hour: form.limit_per_hour,
})

const testConnection = async () => {
  if (!validate()) return
  testing.value = true
  const data = await request('/0x/user/political-moderation/test', 'POST', payload())
  testing.value = false
  if (data) MessagePlugin.success(`${data.message}（${data.latency_ms} ms）`)
}

const saveConfig = async () => {
  if (form.enabled && !validate()) return
  saving.value = true
  const data = await request('/0x/user/political-moderation', 'POST', payload())
  saving.value = false
  if (!data) return
  apiKeyConfigured.value = Boolean(data.api_key_configured)
  form.api_key = ''
  MessagePlugin.success(form.enabled ? '配置已验证并启用' : '配置已保存，审查未启用')
}

onMounted(loadConfig)
</script>

<style scoped>
.moderation-page {
  max-width: 920px;
}

.status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}

.status-title {
  color: var(--app-text);
  font-size: 15px;
  font-weight: 600;
}

.status-description,
.field-help {
  color: var(--app-text-muted);
  font-size: 13px;
  line-height: 1.6;
}

.status-description {
  margin-top: 4px;
}

.moderation-form {
  max-width: 760px;
}

.rate-limit-grid {
  display: grid;
  width: 100%;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.rate-limit-grid label {
  display: grid;
  gap: 6px;
  color: var(--app-text-muted);
  font-size: 13px;
}

@media (max-width: 720px) {
  .status-row {
    align-items: flex-start;
  }

  .rate-limit-grid {
    grid-template-columns: 1fr;
  }
}
</style>
