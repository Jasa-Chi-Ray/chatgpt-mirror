<template>
  <main class="session-page" :data-theme="theme" :lang="language" @keydown.esc="handleEscape">
    <section
      ref="frame"
      class="session-frame"
      :style="{ blockSize: frameSize, clipPath: entranceClip || undefined }"
      :inert="activeSelection !== null"
      aria-labelledby="session-title"
    >
      <div ref="frameContent" class="session-frame__inner">
        <header class="session-header">
          <h1 id="session-title" ref="heading" tabindex="-1">
            <span :key="language" class="language-heading">{{ announcementVisible ? copy.announcementTitle : tableVisible ? copy.accountTitle : copy.preparing }}</span>
          </h1>
          <div class="session-preferences">
            <LanguageSwitch class="session-language" :label="preferenceCopy.language" />
            <button
              class="session-icon"
              type="button"
              :aria-label="theme === 'light' ? preferenceCopy.switchToDark : preferenceCopy.switchToLight"
              :aria-disabled="themeBusy"
              @click="toggleTheme"
            >
              <span class="session-theme-icon" aria-hidden="true"></span>
            </button>
            <button v-if="tableVisible" type="button" class="session-icon" :aria-label="copy.close" :disabled="tableLoading" @click="onClose">
              <span class="session-close-icon" aria-hidden="true"></span>
            </button>
          </div>
        </header>

        <div v-if="announcementVisible" class="session-content session-enter">
          <p class="announcement-intro" :class="{ 'announcement-intro--paused': loginBlocked }">
            {{ loginBlocked ? copy.blockedIntro : copy.announcementIntro }}
          </p>

          <div class="announcement-tabs" role="tablist" :aria-label="copy.announcementTitle" @keydown="moveAnnouncementTab">
            <button
              v-for="group in announcementGroups"
              :id="`session-tab-${group}`"
              :key="group"
              type="button"
              role="tab"
              :aria-selected="activeAnnouncementTab === group"
              :aria-controls="`session-panel-${group}`"
              :tabindex="activeAnnouncementTab === group ? 0 : -1"
              @click="activeAnnouncementTab = group"
            >{{ copy[group] }} ({{ announcements[group].length }})</button>
          </div>
          <div
            v-for="group in announcementGroups"
            v-show="activeAnnouncementTab === group"
            :id="`session-panel-${group}`"
            :key="group"
            class="announcement-list"
            role="tabpanel"
            :aria-labelledby="`session-tab-${group}`"
          >
            <article v-for="item in announcements[group]" :key="item.id" class="announcement-item">
              <div class="announcement-heading">
                <h2>{{ item.title }}</h2>
                <time :datetime="item.start_at">{{ formatAnnouncementSchedule(item) }}</time>
              </div>
              <span v-if="group !== 'history' && item.block_chatgpt_login" class="announcement-pause">{{ copy.pause }}</span>
              <MarkdownContent class="announcement-content" :content="item.content" />
            </article>
          </div>

          <footer class="session-actions announcement-actions">
            <button type="button" class="session-button session-button--primary" :disabled="tableLoading" @click="continueToAccountSelection">
              {{ loginBlocked ? copy.returnToAccount : copy.continueToAccounts }}
            </button>
          </footer>
        </div>

        <div v-else-if="tableVisible" class="session-content session-enter">
          <div class="session-actions picker-actions">
            <button
              class="session-button session-button--primary"
              type="button"
              :aria-label="copy.autoAssign"
              :aria-busy="activeSelection === 'auto'"
              :disabled="tableLoading"
              @click="onSelect(null)"
            >
              <span>{{ copy.autoAssign }}</span>
            </button>
            <button v-if="!userStore.isAdmin" type="button" class="session-button" :disabled="tableLoading" @click="openAccountCenter">
              {{ copy.profile }}
            </button>
          </div>
          <div class="account-grid" :aria-busy="tableLoading">
            <button
              v-for="item in tableData"
              :key="item.id"
              type="button"
              class="account-card"
              :aria-busy="activeSelection === item.id"
              :disabled="tableLoading || !canSelect(item)"
              @click="onSelect(item.id)"
            >
              <span class="account-card__title">{{ item.chatgpt_flag }}</span>
              <span class="account-card__plan" :class="{ 'account-card__plan--paid': item.plan_type !== 'free' }">{{ item.plan_type }}</span>
              <UsageMeter :usage="item.usage" />
            </button>
          </div>
        </div>

        <div v-else class="session-content session-state">
          <span v-if="preparing" class="session-spinner" aria-hidden="true"></span>
          <p role="status">{{ translateStatus(statusText) }}</p>
        </div>
      </div>
    </section>
    <p v-if="tableVisible && tableLoading" class="visually-hidden" role="status">{{ translateStatus(statusText) }}</p>
    <canvas ref="liquidSurface" class="login-liquid-surface" aria-hidden="true"></canvas>
    <MirrorTransition v-if="activeSelection !== null" ref="mirrorTransition" />
  </main>
</template>

<script setup lang="ts">
import UsageMeter from '@/pages/account/components/UsageMeter.vue'
import { MessagePlugin } from 'tdesign-vue-next'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import request from '@/api/request'
import { detectBrowserIp } from '@/api/browser-ip'
import MarkdownContent from '@/components/MarkdownContent.vue'
import LanguageSwitch from '@/components/LanguageSwitch.vue'
import { useAppearanceStore } from '@/store/appearance'
import { useUserStore } from '@/store/user'
import { animateWindowOpening, openingClip, queueWindowOpening, takeWindowOpening } from '@/layouts/window-opening'
import { chatgptCopy, englishChatgptMessages } from './chatgpt-copy'
import { loginCopy } from './copy'
import { changeThemeWithLiquid } from './liquid-theme'
import MirrorTransition from './MirrorTransition.vue'
import './liquid-theme.css'

const tableLoading = ref(false)
const preparing = ref(true)
const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const appearance = useAppearanceStore()
const { theme, language } = storeToRefs(appearance)
const copy = computed(() => chatgptCopy[language.value])
const preferenceCopy = computed(() => loginCopy[language.value])
const translateStatus = (message: string) =>
  language.value === 'en' && Object.prototype.hasOwnProperty.call(englishChatgptMessages, message) ? englishChatgptMessages[message] : message
const tableVisible = ref(false)
const announcementVisible = ref(false)
const activeAnnouncementTab = ref<'global' | 'personal' | 'history'>('global')
const statusText = ref('正在加载可用账号...')
const activeSelection = ref<number | 'auto' | null>(null)
const mirrorTransition = ref<InstanceType<typeof MirrorTransition> | null>(null)
const heading = ref<HTMLElement | null>(null)
const frame = ref<HTMLElement | null>(null)
const frameContent = ref<HTMLElement | null>(null)
const frameSize = ref<string>()
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)')
const opening = takeWindowOpening('session')
const entranceClip = ref(opening ? openingClip(opening, new DOMRect(0, 0, document.documentElement.clientWidth, window.innerHeight)) : '')
let entrance: Animation | undefined
let observer: ResizeObserver | undefined
const liquidSurface = ref<HTMLCanvasElement | null>(null)
const themeBusy = ref(false)
const pageLifetime = new AbortController()

const toggleTheme = async () => {
  if (themeBusy.value) return
  themeBusy.value = true
  const next = theme.value === 'light' ? 'dark' : 'light'
  try {
    await changeThemeWithLiquid(next, async () => {
      if (pageLifetime.signal.aborted) return
      appearance.setTheme(next)
      await nextTick()
    }, pageLifetime.signal, liquidSurface.value)
  } finally {
    themeBusy.value = false
  }
}

watch([announcementVisible, tableVisible], async ([showAnnouncement, showAccounts]) => {
  if (!showAnnouncement && !showAccounts) return
  await nextTick()
  heading.value?.focus({ preventScroll: true })
})

const clearEntrance = () => {
  window.removeEventListener('resize', clearEntrance)
  entranceClip.value = ''
  entrance?.cancel()
  entrance = undefined
}

onBeforeUnmount(() => {
  if (usagePoll) clearInterval(usagePoll)
  pageLifetime.abort()
  observer?.disconnect()
  clearEntrance()
})

type Announcement = {
  id: number
  title: string
  content: string
  updated_at: string
  start_at: string
  end_at: string | null
  display_timezone: string
  block_chatgpt_login: boolean
}

const announcements = reactive<{
  global: Announcement[]
  personal: Announcement[]
  history: Announcement[]
}>({
  global: [],
  personal: [],
  history: [],
})
const loginBlocked = computed(() =>
  [...announcements.global, ...announcements.personal].some(item => item.block_chatgpt_login),
)
const announcementGroups = computed(() =>
  (['global', 'personal', 'history'] as const).filter(group => announcements[group].length > 0),
)

const moveAnnouncementTab = async (event: KeyboardEvent) => {
  const groups = announcementGroups.value
  const current = groups.indexOf(activeAnnouncementTab.value)
  let next: number
  switch (event.key) {
    case 'Home': next = 0; break
    case 'End': next = groups.length - 1; break
    case 'ArrowLeft': next = (current - 1 + groups.length) % groups.length; break
    case 'ArrowRight': next = (current + 1) % groups.length; break
    default: return
  }
  event.preventDefault()
  activeAnnouncementTab.value = groups[next]
  await nextTick()
  document.getElementById(`session-tab-${groups[next]}`)?.focus()
}

interface TableData {
  id: number
  chatgpt_flag: string
  plan_type: string
  auth_status: boolean
  usage: any
  access_token_valid: boolean
  session_token_valid: boolean
  supported_login_modes: string[]
  default_login_mode: 'api' | 'web'
}
const tableData = ref<TableData[]>([])

let usagePoll: ReturnType<typeof setInterval> | undefined
onMounted(async () => {
  usagePoll = setInterval(() => { if (!document.hidden) void getUserChatGPTAccountList(true) }, 60000)
  const panel = frame.value
  const content = frameContent.value
  if (panel && content) {
    const fitWindow = () => {
      const border = panel.offsetHeight - panel.clientHeight
      frameSize.value = reducedMotion.matches ? undefined : `${content.offsetHeight + border}px`
    }
    fitWindow()
    observer = new ResizeObserver(fitWindow)
    observer.observe(content)
    if (opening) {
      entrance = animateWindowOpening(opening, panel)
      window.addEventListener('resize', clearEntrance)
      void entrance.finished.then(clearEntrance, clearEntrance)
    }
  }
  if (route.query.logout === '1') {
    let clearOpening: (() => void) | undefined
    try {
      await userStore.logout()
      if (panel && !reducedMotion.matches) clearOpening = queueWindowOpening(panel, 'login')
      await router.replace('/login')
      await nextTick()
    } catch (error: any) {
      MessagePlugin.error(translateStatus(error.message || '退出未完成，请重试'))
    } finally {
      clearOpening?.()
      preparing.value = false
    }
    return
  }
  await prepareAnnouncements()
})

const prepareAnnouncements = async () => {
  statusText.value = '正在加载公告...'
  const data = await request('/0x/user/announcements/current')
  if (!data) {
    statusText.value = '公告暂时无法加载，请刷新页面重试'
    preparing.value = false
    return
  }
  announcements.global = data?.global || []
  announcements.personal = data?.personal || []
  announcements.history = data?.history || []

  if (announcementGroups.value.length) {
    activeAnnouncementTab.value = announcementGroups.value[0]
    announcementVisible.value = true
    preparing.value = false
    statusText.value = '请先阅读登录公告'
    return
  }

  await getUserChatGPTAccountList()
}

const openAccountCenter = async () => {
  const panel = frame.value
  const clearOpening = panel && !reducedMotion.matches ? queueWindowOpening(panel, 'profile') : undefined
  try {
    await router.push('/account/profile')
    await nextTick()
  } finally {
    clearOpening?.()
  }
}

const continueToAccountSelection = async () => {
  if (tableLoading.value) return
  if (loginBlocked.value) return openAccountCenter()
  await getUserChatGPTAccountList()
  announcementVisible.value = false
}

const formatAnnouncementSchedule = (item: Announcement) => {
  const timeZone = item.display_timezone || 'Asia/Shanghai'
  const start = new Date(item.start_at).toLocaleString(language.value, { hour12: false, timeZone })
  const end = item.end_at
    ? new Date(item.end_at).toLocaleString(language.value, { hour12: false, timeZone })
    : copy.value.ongoing
  return `${start} ${copy.value.through} ${end} · ${timeZone}`
}

const getUserChatGPTAccountList = async (background = false) => {
  if (!background) {
    preparing.value = true
    tableLoading.value = true
    statusText.value = '正在加载可用账号...'
  }
  const data = await request('/0x/user/chatgpt-list')
  tableLoading.value = false
  preparing.value = false
  
  if (!data) {
    router.push({ name: 'Login' })
    return
  }
  
  const results = data.results || []
  tableData.value = results

  if (results.length === 0) {
    MessagePlugin.warning(translateStatus('暂无可用的 ChatGPT 账号，请联系管理员添加'))
    statusText.value = '暂无可用的 ChatGPT 账号，请联系管理员添加'
  } else {
    tableVisible.value = true
  }
}

const onClose = () => {
  if (tableLoading.value) return
  router.push({ name: 'Login' })
}

const handleEscape = (event: KeyboardEvent) => {
  if (!tableVisible.value || tableLoading.value) return
  event.preventDefault()
  onClose()
}

const canSelect = (item: TableData) =>
  item.auth_status && Array.isArray(item.supported_login_modes) && item.supported_login_modes.length > 0

const supportsMode = (item: TableData, mode: 'api' | 'web') => {
  return Array.isArray(item.supported_login_modes) && item.supported_login_modes.includes(mode)
}

const resolveLoginMode = (item?: TableData) => {
  if (item) {
    if (supportsMode(item, item.default_login_mode)) return item.default_login_mode
    if (supportsMode(item, 'api')) return 'api'
    if (supportsMode(item, 'web')) return 'web'
    return null
  }

  if (tableData.value.some(account => supportsMode(account, 'api'))) return 'api'
  if (tableData.value.some(account => supportsMode(account, 'web'))) return 'web'
  return null
}

const redirectToMirror = async (url: string) => {
  let navigated = false
  const navigate = () => {
    if (navigated || pageLifetime.signal.aborted) return
    navigated = true
    window.location.replace(url)
  }

  // A stalled animation must not hold up an otherwise successful login.
  const deadline = window.setTimeout(navigate, 6200)
  try {
    await nextTick()
    await mirrorTransition.value?.finish()
  } finally {
    window.clearTimeout(deadline)
    navigate()
  }
}

const onSelect = async (chatgptId: number | null) => {
  if (tableLoading.value) return
  if (loginBlocked.value) {
    MessagePlugin.warning(translateStatus('公告生效期间，暂不能进入 ChatGPT'))
    return
  }
  const current = tableData.value.find(item => item.id === chatgptId)
  if (chatgptId !== null && (!current || !canSelect(current))) return
  const loginMode = resolveLoginMode(current)
  if (!loginMode) {
    MessagePlugin.warning(translateStatus('当前没有可登录的账号，请联系管理员更新账号凭据'))
    return
  }

  tableLoading.value = true
  activeSelection.value = chatgptId ?? 'auto'
  statusText.value = '正在登录 ChatGPT，请稍候...'
  const selection = document.activeElement
  let redirecting = false
  try {
    const data = await request('/0x/chatgpt/login', 'POST', {
      chatgpt_id: chatgptId,
      login_mode: loginMode,
      browser_ip: await detectBrowserIp(),
    })
    if (pageLifetime.signal.aborted) return
    if (data) MessagePlugin.success(translateStatus('登录成功'))
    if (data?.login_url) {
      await redirectToMirror(data.login_url)
      redirecting = true
      return
    }
    if (!tableVisible.value) statusText.value = '登录失败，请返回重试'
  } finally {
    if (!redirecting && !pageLifetime.signal.aborted) {
      activeSelection.value = null
      tableLoading.value = false
      await nextTick()
      if (selection instanceof HTMLElement) selection.focus({ preventScroll: true })
    }
  }
}
</script>

<style scoped>
.session-page {
  --surface: #fdfdfd;
  --field: #f6f6f6;
  --canvas: #efefef;
  --text: #202020;
  --muted: #555;
  --border: #cdcdcd;
  --accent: #353535;
  --hero: #252525;
  --ink-echo: rgb(32 32 32 / 18%);
  --ink-hatch: rgb(32 32 32 / 7%);
  --hero-line: rgb(255 255 255 / 26%);
  --hero-hatch: rgb(255 255 255 / 10%);
  --td-text-color-primary: var(--text);
  --td-text-color-secondary: var(--muted);
  --td-brand-color: var(--accent);
  --td-bg-color-container: var(--surface);
  --td-bg-color-container-hover: var(--field);
  --td-component-stroke: var(--border);

  display: grid;
  min-height: 100vh;
  min-height: 100dvh;
  padding: clamp(16px, 5vw, 64px) 24px;
  place-items: center;
  background: var(--canvas);
  color: var(--text);
  color-scheme: light;
}

.session-page[data-theme="dark"] {
  --surface: #191919;
  --field: #222;
  --canvas: #111;
  --text: #f1f1f1;
  --muted: #b6b6b6;
  --border: #454545;
  --accent: #dedede;
  --hero: #242424;
  --ink-echo: rgb(235 235 235 / 23%);
  --ink-hatch: rgb(235 235 235 / 9%);
  color-scheme: dark;
}

.session-frame {
  box-sizing: border-box;
  width: min(100%, 950px);
  border: 1px solid var(--border);
  border-radius: 24px;
  background: var(--surface);
  box-shadow: 0 18px 56px rgb(0 0 0 / 11%);
  overflow: hidden;
  transition: block-size 330ms cubic-bezier(.22,.64,.29,1);
}

.session-frame__inner { display: flow-root; }

.session-header {
  position: relative;
  isolation: isolate;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 26px clamp(18px, 4vw, 34px);
  overflow: hidden;
  color: #fff;
  background: var(--hero);
}

.session-header::before {
  position: absolute;
  z-index: -1;
  inset: 22% -44px -96px auto;
  width: min(53%, 450px);
  border: 1px solid var(--hero-line);
  border-radius: 140px 0 0;
  outline: 1px solid var(--hero-hatch);
  outline-offset: 7px;
  background: repeating-linear-gradient(29deg, transparent 0 9px, var(--hero-hatch) 9px 10px, transparent 10px 13px);
  transform: rotate(-10deg);
  pointer-events: none;
  content: "";
}

.session-header h1 {
  margin: 0;
  font-size: clamp(23px, 3.3vw, 33px);
  font-weight: 640;
  letter-spacing: -0.032em;
  line-height: 1.2;
  text-wrap: balance;
}

.session-header h1:focus { outline: none; }

.session-preferences,
.session-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.session-language {
  --language-width: 36px;
  --language-border: rgb(255 255 255 / 25%);
  --language-surface: transparent;
  --language-text: #f3f3f3;
  --language-selected: #eee;
  --language-selected-text: #282828;
  --language-hover: #fff;
  --language-focus: #eee;
}

.session-icon {
  display: grid;
  place-items: center;
  color: #f3f3f3;
  background: transparent;
  cursor: pointer;
  position: relative;
  width: 35px;
  height: 35px;
  border: 1px solid rgb(255 255 255 / 25%);
  border-radius: 8px;
  transition: background-color 160ms, border-color 160ms;
}

.session-icon:hover { background: rgb(255 255 255 / 9%); }
.session-icon:disabled { opacity: 0.45; cursor: not-allowed; }

.session-theme-icon {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  box-shadow: inset 4px -3px 0 1px currentColor;
}

[data-theme="dark"] .session-theme-icon {
  width: 17px;
  height: 17px;
  border-radius: 0;
  box-shadow: none;
  background:
    radial-gradient(circle, transparent 26%, currentColor 28% 36%, transparent 40%),
    linear-gradient(currentColor, currentColor) 50% 0 / 1px 3px no-repeat,
    linear-gradient(currentColor, currentColor) 50% 100% / 1px 3px no-repeat,
    linear-gradient(currentColor, currentColor) 0 50% / 3px 1px no-repeat,
    linear-gradient(currentColor, currentColor) 100% 50% / 3px 1px no-repeat;
}

.session-close-icon::before,
.session-close-icon::after {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 12px;
  height: 1px;
  background: currentColor;
  content: "";
  transform: translate(-50%, -50%) rotate(45deg);
}
.session-close-icon::after { transform: translate(-50%, -50%) rotate(-45deg); }

.session-content { padding: clamp(18px, 4vw, 34px); }
.session-enter { animation: session-enter 230ms cubic-bezier(.2,.66,.31,1) both; }

.session-state {
  display: grid;
  min-height: 168px;
  align-content: center;
  justify-items: center;
  gap: 14px;
  text-align: center;
  color: var(--muted);
}

.session-actions { flex-wrap: wrap; gap: 12px; }
.announcement-actions { justify-content: end; padding-top: 20px; }
.picker-actions { margin-bottom: 22px; }

.session-button {
  position: relative;
  display: inline-grid;
  place-items: center;
  overflow: hidden;
  min-height: 44px;
  padding: 9px 16px;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 9px;
  font-size: 14px;
  font-weight: 610;
  cursor: pointer;
  transition: border-color 160ms, background-color 160ms, transform 160ms;
}

.session-button:hover:not(:disabled) { border-color: var(--accent); background: var(--field); }
.session-button:active:not(:disabled) { transform: translateY(1px); }
.session-button:disabled:not([aria-busy="true"]) { opacity: .55; cursor: not-allowed; }

.session-button--primary {
  min-width: 182px;
  border-color: var(--accent);
  color: var(--text);
  background: var(--field);
}

.session-button--primary::before {
  position: absolute;
  inset: 2px 3px 3px 2px;
  border: 1px solid var(--ink-echo);
  border-radius: 6px;
  pointer-events: none;
  content: "";
}

.session-button--primary:hover:not(:disabled) {
  background-image: repeating-linear-gradient(-26deg, transparent 0 7px, var(--ink-hatch) 7px 8px);
}

.session-button[aria-busy="true"] { cursor: wait; }

.announcement-intro { margin: 0 0 16px; color: var(--muted); line-height: 1.65; }
.announcement-intro--paused {
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-inline-start: 3px solid var(--accent);
  border-radius: 9px;
  color: var(--text);
  background: var(--field);
}

.announcement-tabs { display: flex; gap: 6px; border-bottom: 1px solid var(--border); overflow-x: auto; }
.announcement-tabs button { white-space: nowrap; padding: 10px 11px 8px; border: 0; border-bottom: 2px solid transparent; background: transparent; color: var(--muted); cursor: pointer; transition: border-color 160ms, color 160ms; }
.announcement-tabs button[aria-selected="true"] { border-bottom-color: var(--accent); color: var(--accent); font-weight: 640; }
.announcement-tabs button:focus-visible { outline-offset: -3px; }

.announcement-list {
  display: grid;
  gap: 10px;
  max-height: min(48dvh, 470px);
  padding: 14px 2px 3px;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.announcement-item {
  min-width: 0;
  padding: clamp(13px, 3vw, 21px);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
}

.announcement-heading { display: grid; gap: 5px; }
.announcement-heading h2 { font-size: 17px; font-weight: 640; overflow-wrap: anywhere; }
.announcement-heading time { font-size: 12px; color: var(--muted); overflow-wrap: anywhere; }

.announcement-pause {
  display: inline-flex;
  margin-top: 10px;
  padding: 3px 8px;
  color: var(--accent);
  border: 1px solid currentColor;
  border-radius: 5px;
  font-size: 12px;
}

.announcement-content { margin-top: 11px; color: var(--text); }
.announcement-content :deep(:is(h1,h2,h3,h4)) { color: var(--text); }
.announcement-content :deep(a) { color: var(--accent); }
.announcement-content :deep(blockquote) { color: var(--muted); border-color: var(--border); }
.announcement-content :deep(:not(pre) > code) { background: var(--field); color: var(--text); }
.announcement-content :deep(pre) { background: var(--field); color: var(--text); border: 1px solid var(--border); }
.announcement-content :deep(:is(th, td)) { border-color: var(--border); }

.account-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 230px), 1fr));
  gap: 12px;
  max-height: 58dvh;
  overflow: auto;
  padding: 3px;
  overscroll-behavior: contain;
}

.account-card {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0,1fr) auto;
  align-items: start;
  gap: 18px 8px;
  min-height: 105px;
  min-width: 0;
  padding: 15px;
  border: 1px solid var(--border);
  border-radius: 11px;
  color: var(--text);
  background: var(--surface);
  text-align: start;
  cursor: pointer;
  transition: border-color 160ms, background-color 160ms, transform 160ms;
}

.account-card:hover:not(:disabled) { border-color: var(--accent); background: var(--field); }
.account-card :deep(.usage-meter) { grid-column: 1 / -1; }
.account-card:active:not(:disabled) { transform: translateY(1px); }
.account-card:disabled:not([aria-busy="true"]) { opacity: .54; cursor: not-allowed; }
.account-card :deep(.usage-meter) { grid-column: 1 / -1; }
.account-card__title { align-self: center; font-size: 16px; font-weight: 640; overflow-wrap: anywhere; }
.account-card__plan { border: 1px solid var(--border); border-radius: 5px; padding: 2px 7px; font-size: 12px; color: var(--muted); overflow-wrap: anywhere; max-width: 85px; }
.account-card__plan--paid {
  color: var(--accent);
  border-color: var(--ink-echo);
  background: repeating-linear-gradient(-26deg, transparent 0 5px, var(--ink-hatch) 5px 6px);
}
.account-card__footer { grid-column: 1 / -1; display: flex; align-items: baseline; justify-content: space-between; gap: 8px; color: var(--muted); font-size: 13px; }
.account-card__count { display: inline-flex; align-items: baseline; gap: 4px; color: var(--text); font-weight: 650; font-variant-numeric: tabular-nums; }
.account-card__count > span { color: var(--muted); font-size: 12px; font-weight: 400; }

.session-spinner { display: block; width: 19px; height: 19px; aspect-ratio: 1; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: session-spin 720ms linear infinite; }
.visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
.session-page button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.session-header button:focus-visible { outline-color: #eee; }

@keyframes session-enter {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes session-spin { to { transform: rotate(1turn); } }

@media (max-width: 560px) {
  .session-page { padding: 14px 10px; align-items: start; }
  .session-frame { border-radius: 17px; }
  .session-header { flex-wrap: wrap; align-items: center; gap: 12px; padding: 16px; }
  .session-content { padding: 16px; }
  .session-actions > button { flex: 1 1 auto; }
  .account-grid { max-height: none; }
}

@media (prefers-reduced-motion: reduce) {
  .session-enter, .session-spinner { animation: none; }
  .session-frame, .session-page button { transition: none; }
}
</style>
