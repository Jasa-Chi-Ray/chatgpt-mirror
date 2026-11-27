<template>
  <div ref="page" class="workspace-page connections-page" :class="{ 'profile-page': !admin }" tabindex="-1">
    <ExternalConnectionsCard v-if="!dialogOnly"
      :connections="connections"
      :loading="loading"
      :busy="busy"
      :open-label="admin ? '查看详情' : '进入'"
      :connect-label="admin ? '录入连接' : '发起连接'"
      :empty-description="admin ? '录入后可查看账号与工作区的连接状态。' : undefined"
      @connect="connect"
      @open="openConnection"
      @reconnect="reconnect"
      @disconnect="askToDisconnect"
    />

    <t-button v-if="!dialogOnly" variant="text" :disabled="busy" @click="cancelPending">取消未完成登录</t-button>

    <p class="connections-announcement" role="status" aria-atomic="true">{{ announcement }}</p>

    <dialog ref="loginDialog" class="connections-dialog connections-login-dialog"
      :aria-labelledby="loginTitleId" @cancel.prevent="closeEmbeddedLogin">
      <header class="connections-login-header">
        <div>
          <h2 :id="loginTitleId">自动化链接 ChatGPT</h2>
          <p>请在下方官网认证页面完成邮箱登录。</p>
        </div>
        <t-button variant="text" type="button" :disabled="loginCompleting" aria-label="关闭官网登录窗口" @click="closeEmbeddedLogin">
          <t-icon name="close" />
        </t-button>
      </header>
      <div class="connections-login-body" :aria-busy="loginCompleting || frameLoading">
        <p v-if="frameLoading" class="connections-login-loading" role="status">正在打开官网登录页…</p>
        <iframe v-if="loginUrl" ref="loginFrame" :src="loginUrl" title="ChatGPT 官网登录"
          sandbox="allow-forms allow-scripts allow-same-origin" referrerpolicy="no-referrer"
          @load="onEmbeddedFrameLoad" />
      </div>
      <footer class="connections-login-footer">
        <p role="status">{{ loginCompleting ? '登录已完成，正在更新连接…' : loginError || '完成登录后，此窗口会自动关闭并更新连接状态。' }}</p>
        <template v-if="overwriteEmail"><p>已存在 {{ overwriteEmail }}。是否覆盖上游账号的登录凭据？</p><t-button variant="outline" @click="closeEmbeddedLogin">保留原账号</t-button><t-button theme="primary" :loading="loginCompleting" @click="completeEmbeddedLogin(true)">确认覆盖</t-button></template>
        <t-button v-else-if="loginPageFailed" variant="outline" :loading="busy" @click="retryEmbeddedLogin">重新打开</t-button>
        <t-button v-else-if="loginError" variant="outline" :loading="loginCompleting" @click="completeEmbeddedLogin">重试确认</t-button>
        <t-button variant="outline" :disabled="loginCompleting" @click="closeEmbeddedLogin">取消登录</t-button>
      </footer>
    </dialog>

    <dialog
      ref="dialog"
      class="connections-dialog"
      :aria-labelledby="titleId"
      :aria-describedby="dialogMode === 'disconnect' ? descriptionId : undefined"
      @close="restoreFocus"
    >
      <h2 :id="titleId" class="connections-dialog-title">{{ dialogTitle }}</h2>

      <template v-if="dialogMode === 'disconnect' && selectedConnection">
        <p :id="descriptionId" class="connections-dialog-body">
          确定解除 <strong>{{ selectedConnection.label }}</strong> 在
          <strong>{{ selectedConnection.workspace }}</strong> 的连接吗？
        </p>
        <p class="connections-dialog-body"><t-checkbox v-model="deleteUpstream">是否一并删除上游账号</t-checkbox><br><small>解除后会清除该链接维护的 Token；未勾选时保留上游账号记录。</small></p>
        <div class="connections-dialog-actions">
          <t-button data-initial-focus type="button" variant="outline" @click="closeDialog">取消</t-button>
          <t-button theme="primary" type="button" :loading="busy" @click="disconnect">确认解除</t-button>
        </div>
      </template>

      <template v-else-if="dialogMode === 'details' && selectedConnection">
        <dl class="connections-dialog-body connections-summary">
          <div><dt>账号标识</dt><dd>{{ selectedConnection.label }}</dd></div>
          <div><dt>工作区</dt><dd>{{ selectedConnection.workspace }}</dd></div>
          <div><dt>状态</dt><dd>{{ connectionStatusLabels[selectedConnection.status] }}</dd></div>
          <div><dt>最近更新</dt><dd>{{ formatConnectionTime(selectedConnection.lastUpdated) }}</dd></div>
          <div><dt>访问凭据到期</dt><dd>{{ formatConnectionTime(selectedConnection.expiresAt) }}</dd></div>
        </dl>
        <div class="connections-dialog-actions">
          <t-button data-initial-focus type="button" variant="outline" @click="closeDialog">关闭</t-button>
        </div>
      </template>
    </dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { MessagePlugin } from 'tdesign-vue-next'
import request from '@/api/request'
import { useUserStore } from '@/store/user'
import ExternalConnectionsCard from './components/ExternalConnectionsCard.vue'
import { connectionStatusLabels, formatConnectionTime, type ExternalConnection } from './connection-details'
import { isEmbeddedLoginCompletion } from './embedded-login'

const props = defineProps<{ admin?: boolean; dialogOnly?: boolean }>()
const userStore = useUserStore()
const admin = computed(() => props.admin || userStore.isAdmin)
const activePool = ref(false)
const deleteUpstream = ref(false)
const overwriteToken = ref('')
const overwriteEmail = ref('')
const emit = defineEmits<{ changed: [] }>()
const route = useRoute()
const router = useRouter()
const connections = ref<ExternalConnection[]>([])
const loading = ref(false)
const busy = ref(false)
const page = ref<HTMLElement | null>(null)
const dialog = ref<HTMLDialogElement | null>(null)
const dialogMode = ref<'details' | 'disconnect' | null>(null)
const selectedId = ref<string | null>(null)
const titleId = useId()
const descriptionId = useId()
const announcement = ref('')
const loginDialog = ref<HTMLDialogElement | null>(null)
const loginFrame = ref<HTMLIFrameElement | null>(null)
const loginTitleId = useId()
const loginUrl = ref('')
const loginFlow = ref('')
const frameLoading = ref(false)
const loginCompleting = ref(false)
const loginError = ref('')
const loginPageFailed = ref(false)
let loginPageObserver: MutationObserver | null = null
let loginTarget: { id?: string; accountId?: number } | null = null
let loginReturnFocus: HTMLElement | null = null
let returnFocus: HTMLElement | null = null
const selectedConnection = computed(() => connections.value.find(item => item.id === selectedId.value))
const dialogTitle = computed(() => dialogMode.value === 'disconnect' ? '解除账号连接' : '连接详情')
const iso = (seconds: unknown) => {
  const value = Number(seconds)
  return Number.isFinite(value) && value > 0 ? new Date(value * 1000).toISOString() : undefined
}
async function loadConnections() {
  loading.value = true
  try {
    const result = await request(`/0x/chatgpt/web-login?pool=${Boolean(admin.value)}`)
    if (result) connections.value = (result.connections || []).map((item: any): ExternalConnection => ({
      id: item.id, label: item.label, workspace: item.workspace, pool: Boolean(item.pool),
      status: item.status === 'reauth_required' ? 'needs-reconnect' : item.status === 'temporary_error' ? 'unavailable' : 'connected',
      lastUpdated: iso(item.last_updated), expiresAt: iso(item.access_token_expires_at),
    }))
  } finally { loading.value = false }
}
async function startConnection(id?: string, accountId?: number) {
  activePool.value = id ? Boolean(connections.value.find(item => item.id === id)?.pool ?? admin.value) : Boolean(admin.value)
  if (busy.value || loginFlow.value) return
  busy.value = true
  try {
    const result = await request('/0x/chatgpt/web-login', 'POST', { action: 'start', pool: activePool.value, id: id || '', embedded: true,
      ...(accountId ? { account_id: accountId } : {}) })
    const match = typeof result?.authorize_url === 'string' && result.authorize_url.match(/^\/__upstream-login\/start\?ticket=([a-f0-9]{64})$/)
    if (match) {
      activePool.value = Boolean(result.pool)
      loginTarget = { id, accountId }
      loginPageFailed.value = false
      loginReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
      loginFlow.value = match[1]
      loginError.value = ''
      frameLoading.value = true
      loginUrl.value = result.authorize_url
      await nextTick()
      loginDialog.value?.showModal()
    }
  } finally { busy.value = false }
}

function clearEmbeddedLogin() {
  loginPageObserver?.disconnect()
  loginPageObserver = null
  loginTarget = null
  overwriteToken.value = ''
  overwriteEmail.value = ''
  loginPageFailed.value = false
  loginUrl.value = ''
  loginFlow.value = ''
  loginError.value = ''
  loginDialog.value?.close()
  const trigger = loginReturnFocus
  loginReturnFocus = null
  void nextTick(() => {
    if (trigger?.isConnected) trigger.focus({ preventScroll: true })
    else page.value?.focus({ preventScroll: true })
  })
}
function onEmbeddedFrameLoad() {
  frameLoading.value = false
  loginPageObserver?.disconnect()
  loginPageObserver = null
  try {
    const frameDocument = loginFrame.value?.contentDocument
    if (frameDocument?.contentType === 'application/json') {
      const payload = JSON.parse(frameDocument.body?.textContent || '{}')
      loginError.value = typeof payload.message === 'string'
        ? payload.message.slice(0, 300) : '认证页面未能打开，请重新打开。'
      loginPageFailed.value = true
    }
    if (frameDocument?.body && frameDocument.contentType !== 'application/json') {
      const inspectError = () => {
        const text = frameDocument.body.textContent || ''
        if (text.includes("Failed to construct 'URL': Invalid URL")) {
          loginError.value = '官网登录事务已失效，请重新打开后获取新的验证码。'
          loginPageFailed.value = true
        }
      }
      inspectError()
      loginPageObserver = new MutationObserver(inspectError)
      loginPageObserver.observe(frameDocument.body, { childList: true, subtree: true })
    }
  } catch { /* A nested provider frame may be inaccessible during navigation. */ }
}
async function retryEmbeddedLogin() {
  if (busy.value || loginCompleting.value || !loginTarget) return
  const target = loginTarget
  const flow = loginFlow.value
  busy.value = true
  clearEmbeddedLogin()
  try {
    if (flow) await request('/0x/chatgpt/web-login', 'POST', { action: 'cancel', pool: activePool.value, flow })
  } finally { busy.value = false }
  if (page.value?.isConnected) await startConnection(target.id, target.accountId)
}
function closeEmbeddedLogin() {
  if (loginCompleting.value) return
  const flow = loginFlow.value
  clearEmbeddedLogin()
  if (flow) void request('/0x/chatgpt/web-login', 'POST', { action: 'cancel', pool: activePool.value, flow })
}
async function completeEmbeddedLogin(confirmed: unknown = false) {
  if (overwriteEmail.value && confirmed !== true) return
  if (!loginFlow.value || loginCompleting.value) return
  loginCompleting.value = true
  loginError.value = ''
  try {
    const result = await request('/0x/chatgpt/web-login', 'POST', { action: 'complete', pool: activePool.value, flow: loginFlow.value, overwrite_token: overwriteToken.value })
    if (result?.status === 'overwrite_required') {
      overwriteToken.value = result.overwrite_token
      overwriteEmail.value = result.email
    } else if (result?.status === 'connected') {
      clearEmbeddedLogin()
      MessagePlugin.success(admin.value ? '自动化链接完成，已导入上游账号' : '自动化链接完成，已导入个人上游账号')
      await loadConnections()
      emit('changed')
    } else {
      loginError.value = result?.status === 'pending' ? '官网尚未完成登录，请继续在上方操作。' : '连接确认未完成，可以重试确认。'
    }
  } finally { loginCompleting.value = false }
}
function onEmbeddedLoginMessage(event: MessageEvent) {
  if (isEmbeddedLoginCompletion(event, window.location.origin, loginFrame.value?.contentWindow || null, loginFlow.value)) {
    void completeEmbeddedLogin()
  }
}
function connect(_event: MouseEvent, id?: string) { void startConnection(id) }
function reconnect(id: string) { void startConnection(id) }
async function cancelPending() {
  busy.value = true
  try {
    const result = await request('/0x/chatgpt/web-login', 'POST', { action: 'cancel', pool: Boolean(admin.value) })
    if (result) MessagePlugin.success(result.message)
  } finally { busy.value = false }
}
async function showDialog(mode: 'details' | 'disconnect', event: MouseEvent, id: string) {
  const modal = dialog.value
  if (!modal || dialogMode.value) return
  returnFocus = event.currentTarget instanceof HTMLElement ? event.currentTarget : null
  deleteUpstream.value = false
  selectedId.value = id
  dialogMode.value = mode
  await nextTick()
  if (modal.isConnected) {
    modal.showModal()
    modal.querySelector<HTMLElement>('[data-initial-focus]')?.focus({ preventScroll: true })
  }
}
function closeDialog() { dialog.value?.close() }
async function restoreFocus() {
  const trigger = returnFocus
  returnFocus = null
  selectedId.value = null
  dialogMode.value = null
  await nextTick()
  if (trigger?.isConnected && !trigger.matches(':disabled, [aria-disabled="true"]')) trigger.focus({ preventScroll: true })
  else page.value?.focus({ preventScroll: true })
}
async function openConnection(id: string, event: MouseEvent) {
  if (admin.value) { await showDialog('details', event, id); return }
  busy.value = true
  try {
    const result = await request('/0x/chatgpt/web-login', 'POST', { action: 'activate', id })
    if (result?.login_url && /^\/(?:[^?#]*\/)?api\/not-login\?user_gateway_token=mt-[a-f0-9]{64}$/.test(result.login_url)) {
      window.location.assign(result.login_url)
    }
  } finally { busy.value = false }
}
function askToDisconnect(id: string, event: MouseEvent) { void showDialog('disconnect', event, id) }
async function disconnect() {
  const connection = selectedConnection.value
  if (!connection || busy.value) return
  busy.value = true
  try {
    const result = await request('/0x/chatgpt/web-login', 'POST', { action: 'disconnect', id: connection.id, pool: Boolean(connection.pool), delete_upstream: deleteUpstream.value })
    if (result) {
      closeDialog()
      announcement.value = `已解除 ${connection.label} 的连接。`
      await loadConnections()
      emit('changed')
    }
  } finally { busy.value = false }
}
onMounted(async () => {
  window.addEventListener('message', onEmbeddedLoginMessage)
  if (route.query.web_login === 'complete') {
    busy.value = true
    try {
      const flow = typeof route.query.web_flow === 'string' ? route.query.web_flow : ''
      const result = await request('/0x/chatgpt/web-login', 'POST', { action: 'complete', pool: Boolean(admin.value), flow })
      if (result?.status === 'connected') {
        MessagePlugin.success(admin.value ? '自动化链接完成，已导入上游账号' : '自动化链接完成，已导入个人上游账号')
        emit('changed')
        const query = { ...route.query }; delete query.web_login; delete query.web_flow
        await router.replace({ path: route.path, query })
      }
    } finally { busy.value = false }
  }
  await loadConnections()
})
onBeforeUnmount(() => {
  loginPageObserver?.disconnect()
  window.removeEventListener('message', onEmbeddedLoginMessage)
  const flow = loginFlow.value
  if (flow && !loginCompleting.value) void request('/0x/chatgpt/web-login', 'POST', { action: 'cancel', pool: activePool.value, flow })
})
defineExpose({ startConnection })
</script>

<style scoped>
.connections-page:focus-visible,
.connections-dialog :deep(.t-button:focus-visible) {
  outline: 2px solid var(--app-action);
  outline-offset: 2px;
}

.connections-announcement {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.connections-dialog {
  box-sizing: border-box;
  width: min(calc(100% - 28px), 460px);
  max-height: calc(100dvh - 28px);
  margin: auto;
  padding: 0;
  overflow: auto;
  overscroll-behavior: contain;
  border: 1px solid var(--app-border);
  border-radius: 14px;
  background: var(--app-surface);
  color: var(--app-text);
  box-shadow: 0 18px 60px var(--app-shadow);
}

.connections-dialog::backdrop { background: rgb(0 0 0 / 34%); }

.connections-login-dialog { width: min(calc(100% - 24px), 820px); }
.connections-login-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 16px 20px; border-bottom: 1px solid var(--app-border); background: var(--app-field); }
.connections-login-header h2 { margin: 0; font-size: 17px; line-height: 1.5; }
.connections-login-header p, .connections-login-footer p { margin: 5px 0 0; color: var(--app-text-muted); font-size: 13px; line-height: 1.6; }
.connections-login-body { position: relative; min-height: 300px; background: var(--app-surface); }
.connections-login-body iframe { display: block; width: 100%; height: min(68dvh, 680px); min-height: 300px; border: 0; }
.connections-login-loading { position: absolute; top: 12px; inset-inline: 16px; margin: 0; z-index: 1; padding: 8px 12px; border: 1px solid var(--app-border); border-radius: 8px; background: var(--app-surface); color: var(--app-text-muted); font-size: 13px; }
.connections-login-footer { display: flex; align-items: center; flex-wrap: wrap; justify-content: flex-end; gap: 10px; padding: 12px 20px; border-top: 1px solid var(--app-border); background: var(--app-field); }
.connections-login-footer p { flex: 1 1 240px; margin: 0; }

.connections-dialog-title {
  margin: 0;
  padding: 18px 22px;
  border-bottom: 1px solid var(--app-border);
  background: var(--app-field);
  font-size: 17px;
  font-weight: 640;
  line-height: 1.5;
}

.connections-dialog-body {
  margin: 0;
  padding: 18px 22px;
  font-size: 14px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.connections-fields {
  display: grid;
  gap: 14px;
}

.connections-fields label {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.connections-form-error {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
}

.connections-summary > div {
  display: grid;
  grid-template-columns: minmax(88px, auto) minmax(0, 1fr);
  gap: 12px;
}

.connections-summary > div + div { margin-top: 8px; }
.connections-summary dt { color: var(--app-text-muted); }
.connections-summary dd { margin: 0; }

.connections-dialog-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 9px;
  padding: 14px 22px;
  border-top: 1px solid var(--app-border);
}

@media (max-width: 620px) {
  .connections-dialog-title,
  .connections-dialog-body,
  .connections-dialog-actions { padding-inline: 16px; }

  .connections-dialog :deep(.t-button) { min-height: 44px; }
}

@media (prefers-reduced-motion: no-preference) {
  .connections-dialog[open] { animation: connections-dialog-in 170ms ease-out; }

  @keyframes connections-dialog-in {
    from { opacity: 0; translate: 0 4px; }
    to { opacity: 1; translate: 0 0; }
  }
}
</style>
