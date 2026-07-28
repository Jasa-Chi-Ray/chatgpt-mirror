<template>
  <div class="settings-stack">
    <t-card title="访问限制" subtitle="阻止用户进入指定的哈希路由路径" bordered>
      <template #subtitle>
        禁止用户访问指定的哈希路由路径，被拦截后会返回上一页并提示
      </template>
      <div class="section">
        <h4>当前拦截的哈希路径</h4>
        <t-tag
          v-for="(path, index) in hashPaths"
          :key="index"
          closable
          style="margin: 4px"
          theme="danger"
          @close="removePath(index)"
        >
          {{ path }}
        </t-tag>
        <div v-if="hashPaths.length === 0" class="empty-text">
          暂无拦截路径
        </div>
      </div>

      <t-divider />

      <div class="section">
        <h4>添加新的拦截路径</h4>
        <t-space style="margin-top: 12px">
          <t-input
            v-model="newPath"
            placeholder="例如 #settings/Billing"
            style="width: 300px"
            @keyup.enter="addPath"
          />
          <t-button theme="primary" @click="addPath">添加</t-button>
        </t-space>
        <div class="field-help">
          请输入以 # 开头的哈希路径
        </div>
      </div>

      <t-divider />

      <div class="section">
        <h4>预设拦截模板</h4>
        <t-space style="margin-top: 12px; flex-wrap: wrap">
          <t-button
            v-for="preset in presets"
            :key="preset"
            variant="outline"
            size="small"
            :disabled="hashPaths.includes(preset)"
            @click="addPreset(preset)"
          >
            {{ preset }}
          </t-button>
        </t-space>
      </div>

      <t-divider />

      <t-button theme="primary" :loading="saving" @click="save">
        保存配置
      </t-button>
      <span v-if="saved" class="saved-text">已保存</span>
    </t-card>

    <t-card title="登录人机验证" subtitle="此设置由运行环境控制，修改后需要重启服务" bordered>
      <div class="security-status">
        <div>
          <div class="status-title">Cloudflare Turnstile</div>
          <div class="status-description">
            开启后，每次登录、免费体验和注册都必须完成验证。
          </div>
        </div>
        <t-tag :theme="turnstileCfg.enabled ? 'success' : 'default'" variant="light">
          {{ turnstileCfg.enabled ? '已开启' : '未开启' }}
        </t-tag>
      </div>

      <div class="env-list">
        <div class="env-row">
          <code>CLOUDFLARE_TURNSTILE</code>
          <span>{{ turnstileCfg.enabled ? 'enable' : 'disable' }}</span>
        </div>
        <div class="env-row">
          <code>CLOUDFLARE_TURNSTILE_SITE_KEY</code>
          <span>{{ turnstileCfg.siteKeyConfigured ? '已配置' : '未生效' }}</span>
        </div>
        <div class="env-row">
          <code>CLOUDFLARE_TURNSTILE_SECRET_KEY</code>
          <span>{{ turnstileCfg.enabled ? '仅后端可见' : '未生效' }}</span>
        </div>
      </div>

      <t-alert
        class="security-note"
        message="disable 时，已填写的站点密钥和机密不会用于登录验证；enable 时缺少任一配置将阻止服务启动。"
      />
    </t-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import request from '@/api/request'

const hashPaths = ref<string[]>([])
const newPath = ref('')
const saving = ref(false)
const saved = ref(false)
const turnstileCfg = ref({
  enabled: false,
  siteKeyConfigured: false
})

const presets = [
  '#settings/Billing',
  '#settings/Notifications',
  '#settings/Connectors',
  '#settings/Security',
  '#settings/ParentalControls',
  '#settings/Account',
  '#pricing',
]

onMounted(async () => {
  const [data, versionResponse] = await Promise.all([
    request('/0x/user/access-control'),
    fetch('/0x/user/version-cfg').then(response => response.json()).catch(() => null)
  ])
  if (data) hashPaths.value = data.hash_paths || []
  if (versionResponse) {
    turnstileCfg.value.enabled = Boolean(versionResponse.turnstile_enabled)
    turnstileCfg.value.siteKeyConfigured = Boolean(versionResponse.turnstile_site_key)
  }
})

function addPath() {
  const p = newPath.value.trim()
  if (!p) return
  if (!p.startsWith('#')) {
    MessagePlugin.warning('路径必须以 # 开头')
    return
  }
  if (hashPaths.value.includes(p)) {
    MessagePlugin.warning('路径已存在')
    return
  }
  hashPaths.value.push(p)
  newPath.value = ''
  saved.value = false
}

function removePath(index: number) {
  hashPaths.value.splice(index, 1)
  saved.value = false
}

function addPreset(p: string) {
  if (!hashPaths.value.includes(p)) {
    hashPaths.value.push(p)
    saved.value = false
  }
}

async function save() {
  saving.value = true
  saved.value = false
  const data = await request('/0x/user/access-control', 'POST', { hash_paths: hashPaths.value })
  if (data) {
    saved.value = true
    MessagePlugin.success('配置已保存')
  } else {
    MessagePlugin.error('保存失败')
  }
  saving.value = false
}
</script>

<style scoped>
.settings-stack {
  display: grid;
  gap: 20px;
}

.section {
  padding: 8px 0;
}

.section h4 {
  margin: 0 0 8px 0;
  color: var(--app-text);
  font-size: 14px;
  font-weight: 600;
}

.empty-text,
.field-help {
  color: var(--app-text-muted);
  font-size: 13px;
}

.empty-text {
  padding: 12px 0;
}

.field-help {
  margin-top: 6px;
}

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
  border-bottom: 1px solid #e8e8e4;
}

.env-row:last-child {
  border-bottom: 0;
}

.env-row code {
  color: #3f3f3b;
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
