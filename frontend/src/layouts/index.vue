<template>
  <main class="account-layout" :class="{ 'account-layout--admin': workspaceAdmin, 'account-layout--profile': !workspaceAdmin, 'account-layout--collapsed': workspaceAdmin && sidebarCollapsed }" :data-theme="theme">
    <div ref="frame" class="account-frame" :class="{ 'account-frame--opening': entranceClip }" :style="{ clipPath: entranceClip || undefined }">
      <aside class="account-sidebar">
        <div class="sidebar-heading">
          <div class="sidebar-title">{{ t('管理') }}</div>
          <button
            v-if="workspaceAdmin"
            class="sidebar-toggle"
            type="button"
            :aria-label="t(sidebarCollapsed ? '展开侧边栏' : '收起侧边栏')"
            :title="t(sidebarCollapsed ? '展开侧边栏' : '收起侧边栏')"
            :aria-expanded="!sidebarCollapsed"
            aria-controls="workspace-navigation"
            @click="toggleSidebar"
          >
            <span class="sidebar-toggle-icon" aria-hidden="true"></span>
          </button>
        </div>
        <div class="sidebar-navigation">
          <nav id="workspace-navigation" class="account-nav" :aria-label="t('管理')">
            <router-link
              v-for="item in navigation"
              :key="item.to"
              :to="item.to"
              class="account-nav-link"
              active-class="is-active"
              :aria-label="t(item.label)"
              :title="workspaceAdmin && sidebarCollapsed ? t(item.label) : undefined"
            >
              <t-icon :name="item.icon" aria-hidden="true" />
              <span>{{ t(item.label) }}</span>
            </router-link>
          </nav>
        </div>
      </aside>
      <section class="account-workspace" aria-labelledby="workspace-title">
        <header class="workspace-header">
          <h1 id="workspace-title"><span :key="language" class="language-heading">{{ pageTitle }}</span></h1>
          <div class="workspace-controls">
            <LanguageSwitch class="workspace-language" :label="preferenceCopy.language" />
            <button type="button" class="workspace-icon" :aria-label="theme === 'light' ? preferenceCopy.switchToDark : preferenceCopy.switchToLight" :aria-disabled="themeBusy" @click="toggleTheme">
              <span class="workspace-theme-icon" aria-hidden="true"></span>
            </button>
            <t-dropdown :options="userOptions" @click="handleUserAction">
              <t-button class="workspace-user" variant="outline" :title="username" :disabled="Boolean(logoutIdentity)">
                <t-icon name="user-circle" />
                <span>{{ username }}</span>
                <t-icon name="chevron-down" />
              </t-button>
            </t-dropdown>
          </div>
        </header>
        <router-view v-slot="{ Component }">
          <Transition name="workspace-view" mode="out-in">
            <div :key="route.name" class="workspace-content" :data-page="route.name">
              <component :is="Component" />
            </div>
          </Transition>
        </router-view>
      </section>
    </div>
    <canvas ref="liquidSurface" class="login-liquid-surface" aria-hidden="true"></canvas>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useRoute, useRouter } from 'vue-router'
import { MessagePlugin } from 'tdesign-vue-next'
import { useAppearanceStore } from '@/store/appearance'
import { useUserStore } from '@/store/user'
import LanguageSwitch from '@/components/LanguageSwitch.vue'
import { useWorkspaceCopy } from '@/pages/account/workspace-copy'
import { loginCopy } from '@/pages/login/copy'
import { changeThemeWithLiquid } from '@/pages/login/liquid-theme'
import { animateWindowOpening, openingClip, queueWindowOpening, takeWindowOpening } from './window-opening'
import '@/pages/login/liquid-theme.css'
import '@/pages/account/workspace-pages.css'
import './admin-workspace.css'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const appearance = useAppearanceStore()
const { language, theme } = storeToRefs(appearance)
const { t } = useWorkspaceCopy()
const preferenceCopy = computed(() => loginCopy[language.value])
const themeBusy = ref(false)
const liquidSurface = ref<HTMLCanvasElement | null>(null)
const themeLifetime = new AbortController()
const frame = ref<HTMLElement | null>(null)
const logoutIdentity = ref<{ isAdmin: boolean; username: string }>()
let logoutError: ReturnType<typeof MessagePlugin.error> | undefined
const workspaceAdmin = computed(() => logoutIdentity.value?.isAdmin ?? userStore.isAdmin)
const opening = takeWindowOpening(userStore.isAdmin ? 'admin' : 'profile')
const entranceClip = ref(opening
  ? openingClip(opening, new DOMRect(0, 0, document.documentElement.clientWidth, window.innerHeight))
  : '')
let entrance: Animation | undefined

const readSidebarPreference = () => {
  try {
    return localStorage.getItem('admin-sidebar-collapsed') === 'true'
  } catch {
    return false
  }
}
const sidebarCollapsed = ref(readSidebarPreference())
const toggleSidebar = () => {
  sidebarCollapsed.value = !sidebarCollapsed.value
  try {
    localStorage.setItem('admin-sidebar-collapsed', String(sidebarCollapsed.value))
  } catch {
    // The current layout still works if storage is unavailable.
  }
}

const finishEntrance = () => {
  window.removeEventListener('resize', finishEntrance)
  const animation = entrance
  entrance = undefined
  entranceClip.value = ''
  animation?.cancel()
}

onMounted(() => {
  if (!opening || !frame.value) return
  window.scrollTo(0, 0)
  entrance = animateWindowOpening(opening, frame.value)
  window.addEventListener('resize', finishEntrance)
  void entrance.finished.then(finishEntrance, finishEntrance)
})

const adminNavigation = [
  { to: '/account/overview', icon: 'dashboard', label: '运维概览' },
  { to: '/account/user', icon: 'user', label: '用户' },
  { to: '/account/chatgpt', icon: 'root-list', label: '上游账号' },
  { to: '/account/gptcar', icon: 'server', label: '账号池' },
  { to: '/account/logs', icon: 'file', label: '日志' },
  { to: '/account/announcements', icon: 'notification', label: '公告' },
  { to: '/account/proxy', icon: 'internet', label: '代理' },
  { to: '/account/scripts', icon: 'code', label: '脚本' },
  { to: '/account/access', icon: 'secured', label: '访问与安全' },
  { to: '/account/political-moderation', icon: 'secured', label: '政治内容屏蔽' }
]
const navigation = computed(() => workspaceAdmin.value
  ? adminNavigation
  : [{ to: '/account/profile', icon: 'user-circle', label: '账户中心' }])

const username = computed(() => (logoutIdentity.value?.username ?? userStore.username) || t('管理员'))
const pageTitle = computed(() => t(String(route.meta.title || '管理')))
const userOptions = computed(() => {
  const options = [{ content: t('退出登录'), value: 'logout' }]
  options.unshift({ content: t('账户中心'), value: 'profile' })
  return options
})

const toggleTheme = async () => {
  if (themeBusy.value) return
  const next = theme.value === 'light' ? 'dark' : 'light'
  themeBusy.value = true
  try {
    await changeThemeWithLiquid(next, async () => {
      if (themeLifetime.signal.aborted) return
      appearance.setTheme(next)
      await nextTick()
    }, themeLifetime.signal, liquidSurface.value, userStore.isAdmin ? 'native' : 'glass')
  } finally {
    themeBusy.value = false
  }
}
onBeforeUnmount(() => {
  themeLifetime.abort()
  finishEntrance()
})

const handleUserAction = async (data: { value: string }) => {
  if (logoutIdentity.value) return
  if (data.value === 'profile') {
    router.push('/account/profile')
    return
  }
  if (data.value === 'logout') {
    logoutIdentity.value = { isAdmin: userStore.isAdmin, username: userStore.username }
    if (logoutError) {
      MessagePlugin.close(logoutError)
      logoutError = undefined
    }
    let clearOpening: (() => void) | undefined
    try {
      await userStore.logout()
      const panel = frame.value
      if (panel && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
        finishEntrance()
        clearOpening = queueWindowOpening(panel, 'login')
      }
      await router.replace('/login')
      await nextTick()
    } catch (error: any) {
      logoutError = MessagePlugin.error(error.message || t('退出未完成，请重试'))
    } finally {
      clearOpening?.()
      logoutIdentity.value = undefined
    }
  }
}
</script>

<style scoped>
.account-layout {
  min-height: 100vh;
  min-height: 100dvh;
  padding: clamp(12px, 2.7vw, 38px);
  background: var(--app-bg);
}
.account-frame {
  display: grid;
  grid-template-columns: 216px minmax(0, 1fr);
  max-width: 1560px;
  min-height: min(760px, calc(100dvh - 32px));
  margin-inline: auto;
  border: 1px solid var(--app-border);
  border-radius: 23px;
  background: var(--app-surface);
  box-shadow: 0 18px 50px var(--app-shadow);
}
.account-sidebar {
  position: sticky;
  top: clamp(12px, 2.7vw, 38px);
  align-self: start;
  max-height: calc(100dvh - 30px);
  padding: 24px 12px;
  overflow: auto;
  border-radius: 22px 0 0 0;
  color: var(--app-nav-text);
  background: var(--app-hero);
}
.account-frame { background: linear-gradient(to right, var(--app-hero) 216px, var(--app-surface) 216px); }
.sidebar-navigation { min-width: 0; }
.sidebar-heading { min-width: 0; }
.sidebar-title { padding: 3px 12px 21px; font-size: 19px; font-weight: 650; letter-spacing: -.025em; color: #fff; }
.account-nav { display: grid; gap: 3px; }
.account-nav-link {
  display: flex;
  min-height: 41px;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid transparent;
  border-radius: 8px;
  color: var(--app-nav-text);
  font-size: 14px;
  line-height: 1.35;
  text-decoration: none;
  transition: background-color 160ms, color 160ms, border-color 160ms;
}
.account-nav-link :deep(.t-icon) { flex: 0 0 auto; font-size: 18px; }
.account-nav-link:hover { color: #fff; background: rgb(255 255 255 / 8%); }
.account-nav-link.is-active { color: #f7fff7; background: rgb(255 255 255 / 13%); border-color: rgb(255 255 255 / 24%); font-weight: 630; }
.account-nav-link:focus-visible { outline: 2px solid #a6ecb2; outline-offset: -2px; }
.account-workspace { min-width: 0; background: var(--app-surface); border-radius: 0 22px 22px 0; }
.workspace-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px 18px;
  padding: 20px clamp(16px, 3vw, 34px);
  border-bottom: 1px solid var(--app-border);
}
.workspace-header h1 { font-size: clamp(21px, 2.45vw, 29px); font-weight: 660; letter-spacing: -.034em; line-height: 1.2; overflow-wrap: anywhere; }
.workspace-controls { display: flex; align-items: center; gap: 8px; min-width: 0; }
.workspace-icon { display: grid; place-items: center; background: transparent; color: var(--app-text); cursor: pointer; width: 36px; height: 36px; flex: 0 0 auto; border: 1px solid var(--app-border); border-radius: 8px; }
.workspace-icon:hover { color: var(--app-action); border-color: var(--app-action); }
.workspace-theme-icon { width: 14px; height: 14px; border-radius: 50%; box-shadow: inset 4px -3px 0 1px currentColor; }
[data-theme="dark"] .workspace-theme-icon {
  width: 17px;
  height: 17px;
  box-shadow: none;
  border-radius: 0;
  background:
    radial-gradient(circle, transparent 26%, currentColor 28% 36%, transparent 40%),
    linear-gradient(currentColor, currentColor) 50% 0 / 1px 3px no-repeat,
    linear-gradient(currentColor, currentColor) 50% 100% / 1px 3px no-repeat,
    linear-gradient(currentColor, currentColor) 0 50% / 3px 1px no-repeat,
    linear-gradient(currentColor, currentColor) 100% 50% / 3px 1px no-repeat;
}
.workspace-user { min-width: 0; max-width: min(23vw, 170px); }
.workspace-user :deep(.t-button__text) { display: flex; align-items: center; gap: 5px; min-width: 0; }
.workspace-user :deep(.t-button__text > span:not(.t-icon)) { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.workspace-user :deep(.t-icon) { flex: 0 0 auto; }
.workspace-content { min-width: 0; padding: clamp(14px, 2.6vw, 30px); }
.workspace-view-enter-active, .workspace-view-leave-active { transition: opacity 150ms, transform 150ms; }
.workspace-view-enter-from { opacity: 0; transform: translateY(4px); }
.workspace-view-leave-to { opacity: 0; transform: translateY(-2px); }

@media (max-width: 860px) {
  .account-frame { display: block; background: var(--app-surface); border-radius: 17px; }
  .account-sidebar { position: static; display: flex; align-items: center; gap: 10px; padding: 10px; border-radius: 16px 16px 0 0; }
  .sidebar-title { flex: 0 0 auto; padding: 0 3px; font-size: 15px; }
  .account-nav { display: flex; min-width: 0; overflow-x: auto; overscroll-behavior-x: contain; scrollbar-width: thin; }
  .account-nav-link { min-height: 37px; flex: 0 0 auto; gap: 6px; padding: 7px 9px; white-space: nowrap; font-size: 13px; }
  .account-nav-link :deep(.t-icon) { font-size: 15px; }
  .account-workspace { border-radius: 0 0 16px 16px; }
}
@media (max-width: 530px) {
  .account-layout { padding: 8px; }
  .workspace-header { flex-wrap: wrap; padding: 15px 13px; }
  .workspace-content { padding: 12px; }
  .workspace-user { max-width: 116px; }
}

.account-layout--admin { padding: 0; }
.account-layout--admin .account-frame {
  grid-template-columns: 216px minmax(0, 1fr);
  transition: grid-template-columns 260ms cubic-bezier(.22,.64,.29,1);
  max-width: none;
  min-height: 100vh;
  min-height: 100dvh;
  margin: 0;
  border: 0;
  border-radius: 0;
  box-shadow: none;
}
.account-layout--admin.account-layout--collapsed .account-frame { grid-template-columns: 66px minmax(0, 1fr); }
.account-layout--admin .account-sidebar,
.account-layout--admin .account-workspace { border-radius: 0; }
.account-layout--admin .account-sidebar { top: 0; max-height: 100dvh; }
.account-frame--opening .account-nav,
.account-frame--opening .sidebar-title,
.account-frame--opening .workspace-header,
.account-frame--opening .workspace-content {
  animation: admin-text-appear 280ms 135ms ease-out both;
}
@keyframes admin-text-appear {
  from { opacity: 0; }
  to { opacity: 1; }
}
@media (prefers-reduced-motion: reduce) {
  .workspace-view-enter-active, .workspace-view-leave-active { transition: none; }
  .account-frame--opening :is(.account-nav,.sidebar-title,.workspace-header,.workspace-content) { animation: none; }
  .account-layout--admin .account-frame { transition: none; }
}
</style>
