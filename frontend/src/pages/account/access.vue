<template>
  <div class="settings-stack">
    <t-card title="访问限制" subtitle="阻止用户进入指定路径" bordered>
      <template #subtitle>
        支持普通路径和 # 哈希路径；命中路径及其子路径都会被拦截
      </template>
      <div class="section">
        <h4>当前拦截路径</h4>
        <t-tag
          v-for="(path, index) in blockedPaths"
          :key="index"
          closable
          style="margin: 4px"
          theme="danger"
          @close="removePath(index)"
        >
          {{ path }}
        </t-tag>
        <div v-if="blockedPaths.length === 0" class="empty-text">
          暂无拦截路径
        </div>
      </div>

      <t-divider />

      <div class="section">
        <h4>添加新的拦截路径</h4>
        <t-space style="margin-top: 12px">
          <t-input
            v-model="newPath"
            aria-label="拦截路径"
            placeholder="例如 #settings/Account 或 library"
            :maxlength="512"
            style="width: 300px"
            @keyup.enter="addPath"
          />
          <t-button theme="primary" @click="addPath">添加</t-button>
        </t-space>
        <div class="field-help">
          无需输入开头的 /；不能填写完整 URL 或查询参数；保存后已打开页面会自动同步
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
            :disabled="hasPath(preset)"
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

const blockedPaths = ref<string[]>([])
const newPath = ref('')
const saving = ref(false)
const saved = ref(false)
const turnstileCfg = ref({
  enabled: false,
  siteKeyConfigured: false
})

const presets = [
  '#settings/Personalization',
  '#settings/Security',
  '#settings/Billing',
  '#settings/Account',
  '#settings/Safety',
  '#pricing',
]

onMounted(async () => {
  const [data, versionResponse] = await Promise.all([
    request('/0x/user/access-control'),
    fetch('/0x/user/version-cfg').then(response => response.json()).catch(() => null)
  ])
  if (data) blockedPaths.value = (data.paths || data.hash_paths || []).map(toDisplayPath)
  if (versionResponse) {
    turnstileCfg.value.enabled = Boolean(versionResponse.turnstile_enabled)
    turnstileCfg.value.siteKeyConfigured = Boolean(versionResponse.turnstile_site_key)
  }
})

function addPath() {
  const rawPath = newPath.value.trim()
  const validationError = validatePath(rawPath)
  if (validationError) {
    MessagePlugin.warning(validationError)
    return
  }
  const p = toDisplayPath(rawPath)
  if (!p) return
  if (blockedPaths.value.length >= 200) {
    MessagePlugin.warning('拦截路径最多允许 200 条')
    return
  }
  if (hasPath(p)) {
    MessagePlugin.warning('路径已存在')
    return
  }
  blockedPaths.value.push(p)
  newPath.value = ''
  saved.value = false
}

function removePath(index: number) {
  blockedPaths.value.splice(index, 1)
  saved.value = false
}

function addPreset(p: string) {
  if (!hasPath(p)) {
    blockedPaths.value.push(p)
    saved.value = false
  }
}

function pathKey(path: string) {
  return toDisplayPath(path).replace(/\/+$/, '')
}

function toDisplayPath(path: string) {
  return path.trim().replace(/^\/+/, '')
}

function validatePath(path: string) {
  if (path.length > 512) return '单条拦截路径不能超过 512 个字符'
  if (!path || path === '/') return '不能拦截站点根路径'
  if (/[^\x21-\x7e]/.test(path)) return '拦截路径只能包含不带空白的 ASCII 字符'
  if (/^[a-z][a-z\d+.-]*:\/\//i.test(path) || path.startsWith('//')) {
    return '请填写站内路径，不能填写完整 URL'
  }
  const normalized = toDisplayPath(path)
  if (normalized.includes('\\') || normalized.split('/').some(segment => segment === '.' || segment === '..')) {
    return '拦截路径不能包含反斜杠或相对路径段'
  }
  if (normalized.includes('?')) return '拦截路径不能包含查询参数'
  if (normalized.includes('#') && !normalized.startsWith('#')) return '# 只能用于开头的哈希路径'
  if (normalized === '#') return '哈希路径不能只有 #'
  const lower = normalized.toLowerCase()
  if (lower === '#settings/plugins' || lower.startsWith('#settings/plugins/')) {
    return '#settings/Plugins 是系统保留路径，不能拦截'
  }
  return ''
}

function hasPath(path: string) {
  const key = pathKey(path)
  return blockedPaths.value.some(item => pathKey(item) === key)
}

async function save() {
  saving.value = true
  saved.value = false
  const data = await request('/0x/user/access-control', 'POST', { paths: blockedPaths.value })
  if (data) {
    blockedPaths.value = (data.paths || data.hash_paths || blockedPaths.value).map(toDisplayPath)
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
