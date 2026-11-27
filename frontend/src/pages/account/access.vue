<template>
  <div class="workspace-page settings-page settings-stack">
    <t-card :title="t('上游访问控制')" bordered>
      <div class="security-status">
        <div>
          <div class="status-title">{{ t('保护上游账号设置') }}</div>
          <div class="status-description">
            {{ t('禁止修改共享账号设置。读取返回镜像站预设数据；弹窗与引导状态按用户独立保存，文件与回答所需状态保留真实结果。') }}
          </div>
        </div>
        <t-switch v-model="settingsLocked" :disabled="!loaded || saving" :aria-label="t('保护上游账号设置')" @change="saved = false" />
      </div>
      <div class="security-status dot-control">
        <div>
          <div class="status-title">{{ t('禁止访问 Dot') }}</div>
          <div class="status-description">
            {{ t('禁用 Dot 页面、消息、审批和管理接口，并隐藏相关入口。对所有账号立即生效。') }}
          </div>
        </div>
        <t-switch v-model="dotsLocked" :disabled="!loaded || saving" :aria-label="t('禁止访问 Dot')" @change="saved = false" />
      </div>
      <div class="save-row">
        <t-button theme="primary" :disabled="!loaded" :loading="saving" @click="save">{{ t('保存配置') }}</t-button>
        <span v-if="saved" class="saved-text">{{ t('已保存') }}</span>
      </div>
      <details class="rule-details">
        <summary data-press-feedback="ripple">{{ t('查看接口及用途（') }}{{ rules.length }} {{ t('项）') }}</summary>
        <div class="rule-scroll">
          <table class="rules-table">
            <thead><tr><th>{{ t('路径与备注') }}</th><th>{{ t('请求方法') }}</th><th>{{ t('所属开关') }}</th></tr></thead>
            <tbody>
              <tr v-for="rule in rules" :key="rule.path">
                <td><code>{{ rule.path }}</code> <span class="rule-label">[{{ t(rule.label) }}]</span></td>
                <td>{{ rule.methods.join(' / ') }}</td>
                <td>{{ rule.control === 'dots_locked' ? 'Dot' : t('上游设置') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
    </t-card>

    <t-card :title="t('登录人机验证')" :subtitle="t('此设置由运行环境控制，修改后需要重启服务')" bordered>
      <div class="security-status">
        <div>
          <div class="status-title">Cloudflare Turnstile</div>
          <div class="status-description">
            {{ t('开启后，每次登录、免费体验和注册都必须完成验证。') }}
          </div>
        </div>
        <t-tag :theme="turnstileCfg.enabled ? 'success' : 'default'" variant="light">
          {{ turnstileCfg.enabled ? t('已开启') : t('未开启') }}
        </t-tag>
      </div>

      <div class="env-list">
        <div class="env-row">
          <code>CLOUDFLARE_TURNSTILE</code>
          <span>{{ turnstileCfg.enabled ? 'enable' : 'disable' }}</span>
        </div>
        <div class="env-row">
          <code>CLOUDFLARE_TURNSTILE_SITE_KEY</code>
          <span>{{ turnstileCfg.siteKeyConfigured ? t('已配置') : t('未生效') }}</span>
        </div>
        <div class="env-row">
          <code>CLOUDFLARE_TURNSTILE_SECRET_KEY</code>
          <span>{{ turnstileCfg.enabled ? t('仅后端可见') : t('未生效') }}</span>
        </div>
      </div>

      <t-alert
        class="security-note"
        :message="t('disable 时，已填写的站点密钥和机密不会用于登录验证；enable 时缺少任一配置将阻止服务启动。')"
      />
    </t-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import request from '@/api/request'
import { useWorkspaceCopy } from '@/pages/account/workspace-copy'

const { t } = useWorkspaceCopy()

type SettingsRule = {
  path: string
  label: string
  methods: string[]
  control?: 'settings_locked' | 'dots_locked'
}

const settingsLocked = ref(false)
const dotsLocked = ref(true)
const rules = ref<SettingsRule[]>([])
const loaded = ref(false)
const saving = ref(false)
const saved = ref(false)
const turnstileCfg = ref({ enabled: false, siteKeyConfigured: false })

onMounted(async () => {
  const [data, versionResponse] = await Promise.all([
    request('/0x/user/access-control'),
    fetch('/0x/user/version-cfg').then(response => response.json()).catch(() => null)
  ])
  if (data) {
    settingsLocked.value = data.settings_locked ?? ((data.paths || data.hash_paths || []).length > 0)
    dotsLocked.value = data.dots_locked ?? true
    rules.value = data.rules || []
    loaded.value = true
  }
  if (versionResponse) {
    turnstileCfg.value.enabled = Boolean(versionResponse.turnstile_enabled)
    turnstileCfg.value.siteKeyConfigured = Boolean(versionResponse.turnstile_site_key)
  }
})

async function save() {
  saving.value = true
  saved.value = false
  try {
    const data = await request('/0x/user/access-control', 'POST', {
      settings_locked: settingsLocked.value,
      dots_locked: dotsLocked.value
    })
    if (data) {
      settingsLocked.value = data.settings_locked
      dotsLocked.value = data.dots_locked ?? true
      rules.value = data.rules || []
      saved.value = true
      MessagePlugin.success(t('设置访问策略已保存'))
    }
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.settings-stack {
  display: grid;
  gap: 20px;
}

.save-row { margin-top: 20px; }
.dot-control { margin-top: 22px; padding-top: 22px; border-top: 1px solid var(--app-border); }
.rule-details { margin-top: 24px; }
.rule-details summary { cursor: pointer; color: var(--app-text); font-weight: 500; }
.rule-scroll { margin-top: 12px; overflow-x: auto; }
.rules-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.rules-table th, .rules-table td { padding: 10px 8px; text-align: left; border-bottom: 1px solid var(--app-border); }
.rules-table th { color: var(--app-text-muted); }
.rules-table code { overflow-wrap: anywhere; }
.rule-label { color: var(--app-text-muted); white-space: nowrap; }

.saved-text {
  margin-left: 10px;
  color: var(--app-success);
  font-size: 13px;
}

.security-status {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.status-title {
  color: var(--app-text);
  font-size: 15px;
  font-weight: 600;
}

.status-description {
  margin-top: 6px;
  color: var(--app-text-muted);
  font-size: 13px;
  line-height: 1.6;
}

.env-list {
  margin-top: 22px;
  overflow: hidden;
  border: 1px solid var(--app-border);
  border-radius: 9px;
}

.env-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  min-height: 48px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--app-border);
}

.env-row:last-child {
  border-bottom: 0;
}

.env-row code {
  color: var(--app-text);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.env-row span {
  flex: none;
  color: var(--app-text-muted);
  font-size: 13px;
}

.security-note {
  margin-top: 18px;
}

@media (max-width: 640px) {
  .security-status,
  .env-row {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }
}
</style>
