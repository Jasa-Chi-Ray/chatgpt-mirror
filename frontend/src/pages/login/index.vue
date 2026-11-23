<template>
  <main class="login-page" :data-theme="theme" :lang="language">
    <section ref="loginPanel" class="login-panel" :class="{ 'login-panel--return': closing }" :inert="returning" aria-labelledby="login-title">
      <header class="login-header" @pointermove="moveWelcomeLight" @pointerleave="resetWelcomeLight">
        <div :key="route.path + language" class="welcome-copy">
          <h1 id="login-title">{{ isRegister ? copy.registerTitle : copy.loginTitle }}</h1>
          <p>{{ isRegister ? copy.registerDescription : copy.loginDescription }}</p>
        </div>
      </header>

      <div class="login-content" :style="{ '--login-content-height': measuredHeight ? measuredHeight + 'px' : undefined }">
        <div ref="loginContent" class="login-content__inner">
          <div class="login-preferences">
            <LanguageSwitch class="login-language" :label="copy.language" />
            <button
              class="login-theme"
              type="button"
              :aria-label="theme === 'light' ? copy.switchToDark : copy.switchToLight"
              :aria-disabled="themeBusy"
              @click="toggleTheme"
            >
              <span class="login-theme__icon" aria-hidden="true"></span>
            </button>
          </div>
          <div v-if="cfg.notice" class="login-notice" role="status">
            {{ cfg.notice }}
          </div>

          <p v-if="remainingSeconds > 0" class="login-cooldown" role="status" aria-live="polite">{{ copy.cooldown(remainingSeconds) }}</p>
          <div v-if="verificationError" class="login-cooldown" role="alert">
            {{ translatedMessage(verificationError) }}
            <button type="button" @click="refreshLoginState">{{ copy.retry }}</button>
          </div>
          <div class="login-loading" :aria-busy="loading">
            <t-form
              ref="loginFormRef"
              :data="loginForm"
              :label-width="0"
              :rules="rules"
              :readonly="loading"
              class="login-form"
              @submit="onSubmit"
            >
              <div class="form-field">
                <label for="login-username">{{ copy.username }}</label>
                <t-form-item name="username">
                  <t-input
                    v-field-id="'login-username'"
                    v-model="loginForm.username"
                    autocomplete="username"
                    :placeholder="copy.usernamePlaceholder"
                    size="large"
                  ></t-input>
                </t-form-item>
              </div>

              <div class="form-field">
                <label for="login-password">{{ copy.password }}</label>
                <t-form-item name="password">
                  <t-input
                    v-field-id="'login-password'"
                    v-model="loginForm.password"
                    type="password"
                    :autocomplete="isRegister ? 'new-password' : 'current-password'"
                    :placeholder="copy.passwordPlaceholder"
                    size="large"
                  ></t-input>
                </t-form-item>
              </div>

              <div v-if="isRegister" class="form-field">
                <label for="register-upstream-token">{{ copy.token }}</label>
                <t-form-item name="chatgpt_token">
                  <t-textarea
                    v-field-id="'register-upstream-token'"
                    v-model="loginForm.chatgpt_token"
                    :placeholder="copy.tokenPlaceholder"
                    :autosize="tokenRows"
                  ></t-textarea>
                </t-form-item>
              </div>

              <div v-if="turnstileEnabled" class="turnstile-field">
                <div ref="turnstileContainer" class="turnstile-widget"></div>
                <p v-if="turnstileError" class="turnstile-error" role="alert">
                  {{ translatedMessage(turnstileError) }}
                </p>
              </div>

              <t-form-item class="submit-item">
                <t-button
                  type="submit"
                  size="large"
                  class="login-button"
                  :aria-label="submitText"
                  :aria-busy="loading"
                  :data-flight="progressAction === 'login' ? '' : undefined"
                  :disabled="loading || Boolean(verificationError) || remainingSeconds > 0 || (turnstileEnabled && !turnstileToken)"
                >
                  <span v-if="!loading">{{ submitText }}</span>
                  <LoginRocket v-if="progressAction === 'login'" :complete="progressComplete" />
                  <span v-else-if="loading" class="login-action-wait" aria-hidden="true"></span>
                </t-button>
              </t-form-item>
            </t-form>
          </div>

          <p class="account-switch" :class="{ 'account-switch--busy': loading }" :inert="loading">
            <template v-if="isRegister">
              {{ copy.hasAccount }}
              <router-link to="/login">{{ copy.login }}</router-link>
            </template>
            <template v-else>
              {{ copy.noAccount }}
              <router-link to="/register">{{ copy.register }}</router-link>
            </template>
          </p>

          <div class="login-divider" aria-hidden="true">
            <span>{{ copy.or }}</span>
          </div>

          <button
            class="free-button"
            type="button"
            :aria-label="copy.free"
            :aria-busy="loading"
            :data-flight="progressAction === 'free' ? '' : undefined"
            :disabled="loading || Boolean(verificationError) || remainingSeconds > 0 || (turnstileEnabled && !turnstileToken)"
            @click="goFree"
          >
            <span v-if="!loading">{{ copy.free }}</span>
            <LoginRocket v-if="progressAction === 'free'" :complete="progressComplete" />
            <span v-else-if="loading" class="login-action-wait" aria-hidden="true"></span>
          </button>
        </div>
      </div>
    </section>
    <canvas ref="liquidSurface" class="login-liquid-surface" aria-hidden="true"></canvas>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch, type Directive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { MessagePlugin } from 'tdesign-vue-next'
import { useAppearanceStore } from '@/store/appearance'
import { useUserStore } from '@/store/user'
import { animateWindowClosing, queueWindowOpening, takeWindowOpening } from '@/layouts/window-opening'
import LanguageSwitch from '@/components/LanguageSwitch.vue'
import { getLoginCooldown, LoginCoolingError, LoginVerificationError } from '@/api/login-guard'
import LoginRocket from './LoginRocket.vue'
import { englishLoginMessages, loginCopy } from './copy'
import { changeThemeWithLiquid } from './liquid-theme'
import './liquid-theme.css'

const appearance = useAppearanceStore()
const { language, theme } = storeToRefs(appearance)
const copy = computed(() => loginCopy[language.value])
const translatedMessage = (message: string) =>
  language.value === 'en' && Object.prototype.hasOwnProperty.call(englishLoginMessages, message) ? englishLoginMessages[message] : message
const themeBusy = ref(false)
const themeLifetime = new AbortController()
const liquidSurface = ref<HTMLCanvasElement | null>(null)
const loginPanel = ref<HTMLElement | null>(null)
const closing = takeWindowOpening('login')
const returning = ref(Boolean(closing))
const loginContent = ref<HTMLElement | null>(null)
const measuredHeight = ref(0)
let contentObserver: ResizeObserver | undefined

// TDesign places fallthrough attributes on the wrapper around each native field.
const vFieldId: Directive<HTMLElement, string> = {
  mounted(wrapper, { value }) {
    const field = wrapper.querySelector('input, textarea')
    field?.setAttribute('id', value)
    field?.setAttribute('aria-required', 'true')
  }
}

const toggleTheme = async () => {
  if (themeBusy.value) return
  themeBusy.value = true
  const next = theme.value === 'light' ? 'dark' : 'light'
  try {
    await changeThemeWithLiquid(next, async () => {
      if (themeLifetime.signal.aborted) return
      appearance.setTheme(next)
      await nextTick()
    }, themeLifetime.signal, liquidSurface.value)
  } finally {
    themeBusy.value = false
  }
}

const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches
const moveWelcomeLight = (event: PointerEvent) => {
  if (event.pointerType === 'touch' || reducedMotion()) return
  const header = event.currentTarget as HTMLElement
  const bounds = header.getBoundingClientRect()
  const x = (event.clientX - bounds.left) / bounds.width
  const y = (event.clientY - bounds.top) / bounds.height
  header.style.setProperty('--welcome-x', `${x * 100}%`)
  header.style.setProperty('--welcome-y', `${y * 100}%`)
  header.style.setProperty('--welcome-shift-x', `${(x - 0.5) * 13}px`)
  header.style.setProperty('--welcome-shift-y', `${(y - 0.5) * 10}px`)
}
const resetWelcomeLight = (event: PointerEvent) => {
  const header = event.currentTarget as HTMLElement
  header.style.removeProperty('--welcome-shift-x')
  header.style.removeProperty('--welcome-shift-y')
}

const userStore = useUserStore()
const remainingSeconds = ref(0)
const verificationError = ref('')
let cooldownTimer: ReturnType<typeof setInterval> | undefined
const applyCooldown = (seconds: number) => {
  clearInterval(cooldownTimer)
  remainingSeconds.value = Math.max(0, seconds)
  if (!seconds) return
  const deadline = performance.now() + seconds * 1000
  cooldownTimer = setInterval(() => {
    remainingSeconds.value = Math.max(0, Math.ceil((deadline - performance.now()) / 1000))
    if (!remainingSeconds.value) {
      clearInterval(cooldownTimer)
      void refreshLoginState()
    }
  }, 250)
}
const refreshLoginState = async () => {
  try {
    const seconds = await getLoginCooldown()
    verificationError.value = ''
    applyCooldown(seconds)
    if (!seconds) { await getVersionCfg(); await renderTurnstile() }
  } catch (error: any) { verificationError.value = error.message || '登录状态暂时不可用，请重新检测。' }
}
const loading = ref(false)
const progressAction = ref<'login' | 'free' | null>(null)
const progressComplete = ref(false)
const route = useRoute()
const router = useRouter()
type TurnstileApi = {
  render: (container: HTMLElement, options: Record<string, unknown>) => string
  reset: (widgetId: string) => void
  remove: (widgetId: string) => void
}

declare global {
  interface Window {
    turnstile?: TurnstileApi
  }
}

const cfg = ref({
  show_github: true,
  notice: '',
  turnstile_enabled: false,
  turnstile_site_key: ''
})
const loginFormRef = ref()
const turnstileContainer = ref<HTMLElement | null>(null)
const turnstileToken = ref('')
const turnstileError = ref('')
const turnstileWidgetId = ref<string | null>(null)
let turnstileInvalidationRevision = 0

const loginForm = reactive({
  username: '',
  password: '',
  chatgpt_token: ''
})
const tokenRows = { minRows: 3, maxRows: 5 }

const rules = computed(() => ({
  username: [{ required: true, message: copy.value.usernamePlaceholder, trigger: 'blur' as const }],
  password: [{ required: true, message: copy.value.passwordPlaceholder, trigger: 'blur' as const }],
  chatgpt_token: [{ required: true, message: copy.value.tokenRequired, trigger: 'blur' as const }]
}))

watch(language, () => loginFormRef.value?.clearValidate())

const isRegister = computed(() => {
  return route.path.endsWith('/register')
})
const submitText = computed(() => remainingSeconds.value > 0
  ? copy.value.retryIn(remainingSeconds.value)
  : isRegister.value ? copy.value.register : copy.value.login)
const turnstileEnabled = computed(() => {
  return cfg.value.turnstile_enabled && Boolean(cfg.value.turnstile_site_key)
})

let turnstileScriptPromise: Promise<void> | null = null

const loadTurnstileScript = () => {
  if (window.turnstile) return Promise.resolve()
  if (turnstileScriptPromise) return turnstileScriptPromise

  turnstileScriptPromise = new Promise<void>((resolve, reject) => {
    const existingScript = document.querySelector<HTMLScriptElement>('script[data-turnstile-script]')
    if (existingScript) {
      existingScript.remove()
    }

    const script = document.createElement('script')
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
    script.async = true
    script.defer = true
    script.dataset.turnstileScript = 'true'
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('load failed'))
    document.head.appendChild(script)
  }).catch((error) => {
    turnstileScriptPromise = null
    throw error
  })

  return turnstileScriptPromise
}

const removeTurnstile = () => {
  turnstileInvalidationRevision += 1
  if (turnstileWidgetId.value && window.turnstile) {
    window.turnstile.remove(turnstileWidgetId.value)
  }
  turnstileWidgetId.value = null
  turnstileToken.value = ''
}

const renderTurnstile = async () => {
  if (!turnstileEnabled.value) return

  turnstileError.value = ''
  try {
    await loadTurnstileScript()
    await nextTick()
    if (!window.turnstile || !turnstileContainer.value) return

    removeTurnstile()
    turnstileWidgetId.value = window.turnstile.render(turnstileContainer.value, {
      sitekey: cfg.value.turnstile_site_key,
      action: isRegister.value ? 'register' : 'login',
      theme: 'light',
      size: 'flexible',
      appearance: 'always',
      callback: (token: string) => {
        turnstileToken.value = token
        turnstileError.value = ''
      },
      'expired-callback': () => {
        turnstileInvalidationRevision += 1
        turnstileToken.value = ''
        turnstileError.value = '验证已过期，请重新验证'
      },
      'error-callback': () => {
        turnstileInvalidationRevision += 1
        turnstileToken.value = ''
        turnstileError.value = '人机验证加载失败，请刷新页面'
      }
    })
  } catch {
    turnstileError.value = '人机验证加载失败，请刷新页面'
  }
}

onMounted(async () => {
  if (closing && loginPanel.value) {
    window.scrollTo(0, 0)
    void animateWindowClosing(closing, loginPanel.value, themeLifetime.signal).finally(() => {
      returning.value = false
    })
  }
  if (loginContent.value && typeof ResizeObserver !== 'undefined') {
    measuredHeight.value = loginContent.value.offsetHeight
    contentObserver = new ResizeObserver(([entry]) => {
      measuredHeight.value = entry.borderBoxSize?.[0]?.blockSize ?? loginContent.value?.offsetHeight ?? 0
    })
    contentObserver.observe(loginContent.value)
  }
  if (route.query.logout === '1') {
    try {
      await userStore.logout()
    } catch (error: any) {
      MessagePlugin.error(translatedMessage(error.message || '退出未完成，请重试'))
    }
  }
  await refreshLoginState()
})

watch(isRegister, async () => {
  if (turnstileEnabled.value) {
    removeTurnstile()
    await renderTurnstile()
  }
})

onBeforeUnmount(() => {
  themeLifetime.abort()
  contentObserver?.disconnect()
  clearInterval(cooldownTimer)
  removeTurnstile()
})

const getVersionCfg = async () => {
  try {
    const response = await fetch('/0x/user/version-cfg')
    const data = await response.json()
    Object.assign(cfg.value, data)
  } catch (e) {
    console.error('Failed to get version config')
  }
}

const openAfterLogin = async (isAdmin: boolean) => {
  progressComplete.value = true
  await nextTick()
  const panel = loginPanel.value
  const motion = !reducedMotion()
  const rocket = motion ? panel?.querySelector('[aria-busy="true"] .rocket-progress') : null
  const finish = rocket?.animate([{ opacity: 0.7 }, { opacity: 1 }], { duration: 150 })
  let clearOpening: (() => void) | undefined
  try {
    await finish?.finished.catch(() => undefined)
    if (themeLifetime.signal.aborted) return
    if (panel && motion) clearOpening = queueWindowOpening(panel, isAdmin ? 'admin' : 'session')
    await router.push({ name: isAdmin ? 'User' : 'LoginChatgpt' })
    await nextTick()
  } finally {
    clearOpening?.()
    finish?.cancel()
  }
}

const onSubmit = async ({ validateResult }: any) => {
  if (validateResult === true) {
    if (loading.value || verificationError.value || remainingSeconds.value > 0) return
    if (turnstileEnabled.value && !turnstileToken.value) {
      MessagePlugin.warning(translatedMessage('请完成人机验证'))
      return
    }

    loading.value = true
    progressAction.value = 'login'
    progressComplete.value = false
    const submittedTurnstileToken = turnstileToken.value
    const submittedInvalidationRevision = turnstileInvalidationRevision
    try {
      const url = isRegister.value ? '/0x/user/register' : '/0x/user/login'
      const credentials = isRegister.value
        ? {
            username: loginForm.username,
            password: loginForm.password,
            chatgpt_token: loginForm.chatgpt_token
          }
        : {
            username: loginForm.username,
            password: loginForm.password
          }
      const data = await userStore.login(url, {
        ...credentials,
        turnstile_token: submittedTurnstileToken
      }, () => {
        if (turnstileEnabled.value && turnstileInvalidationRevision !== submittedInvalidationRevision) {
          throw new Error('人机验证已失效，请重新验证')
        }
        // The verified challenge has been accepted; the server now checks the short-lived ticket.
        removeTurnstile()
      })

      if (data.authenticated) await openAfterLogin(Boolean(data.is_admin))
    } catch (error: any) {
      if (error instanceof LoginCoolingError) { applyCooldown(error.remainingSeconds); removeTurnstile() }
      else if (error instanceof LoginVerificationError) { verificationError.value = error.message; removeTurnstile() }
      else { MessagePlugin.error(translatedMessage(error.message || '操作失败')); await renderTurnstile() }
    } finally {
      progressAction.value = null
      progressComplete.value = false
      loading.value = false
    }
  }
}

const goFree = async () => {
  if (loading.value || verificationError.value || remainingSeconds.value > 0) return
  if (turnstileEnabled.value && !turnstileToken.value) {
    MessagePlugin.warning(translatedMessage('请完成人机验证'))
    return
  }

  loading.value = true
  progressAction.value = 'free'
  progressComplete.value = false
  const submittedTurnstileToken = turnstileToken.value
  const submittedInvalidationRevision = turnstileInvalidationRevision
  try {
    const data = await userStore.login('/0x/user/login-free', {
      turnstile_token: submittedTurnstileToken
    }, () => {
      if (turnstileEnabled.value && turnstileInvalidationRevision !== submittedInvalidationRevision) {
        throw new Error('人机验证已失效，请重新验证')
      }
      removeTurnstile()
    })
    if (data.authenticated) {
      await openAfterLogin(false)
    }
  } catch (error: any) {
    if (error instanceof LoginCoolingError) { applyCooldown(error.remainingSeconds); removeTurnstile() }
    else if (error instanceof LoginVerificationError) { verificationError.value = error.message; removeTurnstile() }
    else { MessagePlugin.error(translatedMessage(error.message || '免费体验暂不可用')); await renderTurnstile() }
  } finally {
    progressAction.value = null
    progressComplete.value = false
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  --login-canvas: #efefef;
  --login-panel: #fdfdfd;
  --login-field: #f6f6f6;
  --login-text: #202020;
  --login-muted: #555;
  --login-border: #cdcdcd;
  --login-hover-border: #828282;
  --login-ink: #353535;
  --login-paper-pressed: #e8e8e8;
  --login-ink-echo: rgb(32 32 32 / 18%);
  --login-hero: #252525;
  --login-hero-text: #f8f8f8;
  --login-hero-secondary: #d0d0d0;
  --login-sketch-stroke: rgb(255 255 255 / 29%);
  --login-sketch-echo: rgb(255 255 255 / 12%);
  --login-sketch-hatch: rgb(255 255 255 / 8%);
  --login-danger: #8d342c;
  --login-ease: cubic-bezier(0.22, 0.68, 0.25, 1);
  --app-action: var(--login-ink);
  --app-action-hover: var(--login-text);
  --app-action-pressed: var(--login-paper-pressed);
  --td-brand-color: var(--login-ink);
  --td-brand-color-hover: var(--login-text);
  --td-brand-color-active: var(--login-ink);
  --td-brand-color-focus: var(--login-border);
  --td-text-color-primary: var(--login-text);
  --td-text-color-secondary: var(--login-muted);
  --td-text-color-placeholder: var(--login-muted);
  --td-text-color-disabled: var(--login-muted);
  --td-bg-color-specialcomponent: var(--login-field);
  --td-bg-color-container: var(--login-panel);
  --td-component-border: var(--login-border);
  --td-component-stroke: var(--login-border);

  display: grid;
  place-items: center;
  min-height: 100vh;
  min-height: 100dvh;
  padding: 40px 24px;
  color: var(--login-text);
  background: var(--login-canvas);
  color-scheme: light;
}

.login-page[data-theme="dark"] {
  --login-canvas: #111;
  --login-panel: #191919;
  --login-field: #222;
  --login-text: #f1f1f1;
  --login-muted: #b6b6b6;
  --login-border: #454545;
  --login-hover-border: #909090;
  --login-ink: #dedede;
  --login-paper-pressed: #323232;
  --login-ink-echo: rgb(235 235 235 / 23%);
  --login-hero: #242424;
  --login-hero-secondary: #c9c9c9;
  --login-danger: #ffaea4;
  color-scheme: dark;
}

.login-panel {
  display: grid;
  grid-template-columns: minmax(0, 0.94fr) minmax(0, 1.06fr);
  width: min(100%, 880px);
  overflow: hidden;
  background: var(--login-panel);
  border: 1px solid var(--login-border);
  border-radius: 24px;
  box-shadow: 0 24px 70px rgb(0 0 0 / 12%), 0 3px 10px rgb(0 0 0 / 6%);
  animation: login-appear 350ms var(--login-ease) both;
}

.login-panel--return,
.login-panel--return .login-header :is(h1, p) {
  animation: none;
}

.login-header {
  position: relative;
  display: grid;
  align-content: center;
  isolation: isolate;
  overflow: hidden;
  padding: 56px clamp(34px, 4.8vw, 64px);
  background: var(--login-hero);
}

.login-header::before,
.login-header::after {
  position: absolute;
  z-index: -1;
  pointer-events: none;
  content: "";
}

.login-header::before {
  right: -120px;
  bottom: -217px;
  width: 345px;
  height: 465px;
  border: 1px solid var(--login-sketch-stroke);
  border-radius: 180px 180px 0 0;
  outline: 1px solid var(--login-sketch-echo);
  outline-offset: 9px;
  background: repeating-linear-gradient(29deg, transparent 0 10px, var(--login-sketch-hatch) 10px 11px, transparent 11px 14px);
  transform: translate(var(--welcome-shift-x, 0px), var(--welcome-shift-y, 0px)) rotate(32deg);
  transition: transform 350ms var(--login-ease);
}

.login-header::after {
  inset: 0;
  background: repeating-linear-gradient(-34deg, transparent 0 6px, var(--login-sketch-echo) 6px 7px, transparent 7px 10px);
  mask-image: radial-gradient(ellipse at var(--welcome-x, 50%) var(--welcome-y, 50%), #000, transparent 56%);
  opacity: 0;
  transition: opacity 280ms ease;
}

@media (hover: hover) and (pointer: fine) {
  .login-header:hover::after { opacity: 1; }
}

.welcome-copy {
  display: grid;
  gap: 14px;
  transform: translate(var(--welcome-shift-x, 0px), var(--welcome-shift-y, 0px));
  transition: transform 390ms var(--login-ease);
}

.login-header h1 {
  margin: 0;
  color: var(--login-hero-text);
  font-size: clamp(36px, 4.8vw, 54px);
  font-weight: 650;
  line-height: 1.14;
  letter-spacing: -0.045em;
  text-wrap: balance;
  animation: login-appear 300ms var(--login-ease) both;
}

.login-header p {
  margin: 0;
  color: var(--login-hero-secondary);
  font-size: 16px;
  line-height: 1.6;
  animation: login-appear 320ms 30ms var(--login-ease) both;
}

:lang(en) > .login-panel h1 {
  font-size: clamp(34px, 4.6vw, 49px);
  text-wrap: initial;
}

.login-content {
  min-width: 0;
  block-size: var(--login-content-height, auto);
  overflow: clip;
  transition: block-size 340ms var(--login-ease);
}

.login-content__inner {
  padding: 30px clamp(30px, 4.2vw, 54px) 48px;
}

.login-preferences {
  display: flex;
  min-height: 38px;
  align-items: center;
  justify-content: end;
  gap: 8px;
  margin-bottom: 24px;
}

.login-language {
  --language-width: 40px;
  --language-inset: 3px;
  --language-radius: 9px;
  --language-surface: var(--login-field);
  --language-border: var(--login-border);
  --language-text: var(--login-muted);
  --language-selected: var(--login-text);
  --language-selected-text: var(--login-panel);
  --language-hover: var(--login-ink);
  --language-focus: var(--login-ink);
}

.login-theme {
  display: grid;
  place-items: center;
  cursor: pointer;
  transition: background-color 160ms ease, color 160ms ease, transform 160ms var(--login-ease);
  width: 37px;
  height: 37px;
  color: var(--login-text);
  background: var(--login-field);
  border: 1px solid var(--login-border);
  border-radius: 9px;
}

.login-theme:hover {
  color: var(--login-ink);
  border-color: var(--login-hover-border);
}

.login-theme:active {
  transform: scale(0.93);
}

.login-theme__icon {
  display: block;
  width: 15px;
  height: 15px;
  border-radius: 50%;
  box-shadow: inset 4px -3px 0 1px currentColor;
}

[data-theme="dark"] .login-theme__icon {
  width: 18px;
  height: 18px;
  border-radius: 0;
  background:
    radial-gradient(circle, transparent 26%, currentColor 28% 36%, transparent 38%),
    linear-gradient(currentColor, currentColor) 50% 0 / 1px 3px no-repeat,
    linear-gradient(currentColor, currentColor) 50% 100% / 1px 3px no-repeat,
    linear-gradient(currentColor, currentColor) 0 50% / 3px 1px no-repeat,
    linear-gradient(currentColor, currentColor) 100% 50% / 3px 1px no-repeat;
  box-shadow: none;
}

.login-notice,
.login-cooldown {
  margin: 0 0 20px;
  padding: 12px 14px;
  border: 1px solid var(--login-border);
  border-radius: 9px;
  background: var(--login-field);
  color: var(--login-text);
  font-size: 14px;
  line-height: 1.55;
  overflow-wrap: anywhere;
  animation: login-appear 180ms var(--login-ease) both;
}

.login-cooldown {
  color: var(--login-danger);
  font-variant-numeric: tabular-nums;
}

.login-cooldown button {
  margin-inline-start: 6px;
  padding: 0;
  color: inherit;
  background: transparent;
  border: 0;
  border-radius: 2px;
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}

.login-loading {
  width: 100%;
}

.form-field + .form-field {
  margin-top: 18px;
}

.form-field:has(textarea) {
  animation: login-appear 220ms var(--login-ease) both;
}

.form-field label {
  display: inline-block;
  margin-bottom: 8px;
  color: var(--login-text);
  font-size: 14px;
  font-weight: 600;
  line-height: 20px;
}

.form-field :deep(.t-form__item) {
  margin: 0;
}

.form-field :deep(.t-form__controls-content),
.submit-item :deep(.t-form__controls-content) {
  display: block;
}

.form-field :deep(.t-input),
.form-field :deep(.t-textarea__inner) {
  color: var(--login-text);
  background: var(--login-field);
  border-color: var(--login-border);
  border-radius: 9px;
  box-shadow: none;
  transition: none;
}

.form-field :deep(.t-input) {
  min-height: 50px;
  padding: 0 14px;
}

.form-field :deep(.t-input__inner),
.form-field :deep(.t-textarea__inner) {
  color: var(--login-text);
  caret-color: var(--login-ink);
  font-size: 16px;
}

.form-field :deep(.t-textarea__inner) {
  min-height: 96px !important;
  padding: 10px 14px;
  line-height: 1.55;
}

.form-field :deep(.t-input__inner::placeholder),
.form-field :deep(.t-textarea__inner::placeholder) {
  color: var(--login-muted);
}

.form-field :deep(.t-input:focus-within),
.form-field :deep(.t-textarea__inner:focus) {
  border-color: var(--login-ink);
  box-shadow: inset 0 0 0 1px var(--login-ink);
}

.form-field :deep(.t-input.t-is-error),
.form-field :deep(.t-textarea__inner.t-is-error) {
  border-color: var(--login-danger);
}

.form-field :deep(.t-input.t-is-error:focus-within),
.form-field :deep(.t-textarea__inner.t-is-error:focus) {
  border-color: var(--login-danger);
  box-shadow: inset 0 0 0 1px var(--login-danger);
}

.form-field :deep(.t-input__extra) {
  color: var(--login-danger);
  font-size: 13px;
  animation: login-appear 160ms var(--login-ease) both;
}

.login-form :deep(.t-form__item.submit-item) {
  margin: 22px 0 0;
}

.turnstile-field {
  margin-top: 18px;
  animation: login-appear 200ms var(--login-ease) both;
}

.turnstile-widget {
  width: 100%;
  min-height: 65px;
}

.turnstile-error {
  margin-top: 8px;
  color: var(--login-danger);
  font-size: 13px;
  line-height: 1.55;
}

.login-button.t-button,
.free-button {
  position: relative;
  display: flex;
  width: 100%;
  min-height: 48px;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  padding-inline: 16px;
  border: 1px solid;
  border-radius: 9px;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.35;
  transition: background-color 160ms ease, border-color 160ms ease, color 160ms ease, transform 160ms var(--login-ease);
}

.login-button.t-button {
  --login-button-ink: var(--login-ink);
  --login-button-color: var(--login-field);

  min-height: 50px;
  color: var(--login-button-ink);
  background: var(--login-button-color);
  border-color: var(--login-ink);
  font-variant-numeric: tabular-nums;
}

.login-button.t-button::before {
  position: absolute;
  inset: 2px 3px 3px 2px;
  border: 1px solid var(--login-ink-echo);
  border-radius: 6px;
  pointer-events: none;
  content: "";
}

.login-button.t-button:disabled:not([data-flight])::before { opacity: .4; }

.login-button :deep(.t-button__text) {
  position: static;
}

.login-button.t-button:hover:not(:disabled) {
  --login-button-color: var(--login-paper-pressed);

  color: var(--login-button-ink);
  background: var(--login-button-color);
  border-color: var(--login-ink);
}

.login-button.t-button:disabled:not([data-flight]),
.free-button:disabled:not([data-flight]) {
  color: var(--login-muted);
  background: var(--login-field);
  border-color: var(--login-border);
  cursor: not-allowed;
}

.login-button[aria-busy="true"],
.free-button[aria-busy="true"] {
  cursor: wait;
}

.login-button.t-button:active:not(:disabled),
.free-button:active:not(:disabled) {
  transform: translateY(1px);
}

.login-action-wait {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  color: var(--login-muted);
  background: currentColor;
  box-shadow: -8px 0 currentColor, 8px 0 currentColor;
  animation: login-wait 700ms ease-in-out infinite alternate;
}

.account-switch {
  margin-top: 16px;
  color: var(--login-muted);
  text-align: center;
  font-size: 14px;
  line-height: 22px;
}

.account-switch--busy {
  visibility: hidden;
}

.account-switch a {
  color: var(--login-ink);
  border-radius: 2px;
  font-weight: 650;
  text-decoration: underline;
  text-decoration-color: var(--login-hover-border);
  text-underline-offset: 4px;
  transition: color 160ms ease, text-decoration-color 160ms ease;
}

.account-switch a:hover {
  text-decoration-color: currentColor;
}

.login-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 20px 0 16px;
  color: var(--login-muted);
  font-size: 13px;
}

.login-divider::before,
.login-divider::after {
  flex: 1;
  height: 1px;
  background: var(--login-border);
  content: "";
}

.free-button {
  --login-button-ink: var(--login-ink);
  --login-button-color: var(--login-panel);

  color: var(--login-button-ink);
  background: var(--login-button-color);
  border-color: var(--login-border);
  cursor: pointer;
}

.free-button:hover:not(:disabled) {
  background: var(--login-field);
  border-color: var(--login-hover-border);
}

.login-button:focus-visible,
.free-button:focus-visible,
.account-switch a:focus-visible,
.login-cooldown button:focus-visible,
.login-theme:focus-visible {
  outline: 2px solid var(--login-ink);
  outline-offset: 3px;
}

@keyframes login-appear {
  from { opacity: 0; transform: translateY(5px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes login-wait {
  from { opacity: 0.38; }
  to { opacity: 0.84; }
}

@media (max-width: 700px) {
  .login-page { padding: 24px 16px; }

  .login-panel {
    grid-template-columns: minmax(0, 1fr);
    max-width: 460px;
    border-radius: 21px;
  }

  .login-header {
    min-height: 152px;
    padding: 25px 26px;
  }

  .welcome-copy { gap: 8px; }

  .login-header::before {
    right: -86px;
    bottom: -273px;
    transform: rotate(39deg);
  }

  .login-header h1,
  :lang(en) > .login-panel h1 { font-size: 36px; }

  .login-header p { font-size: 15px; }

  .login-content__inner { padding: 21px 26px 27px; }
  .login-preferences { margin-bottom: 17px; }
}

@media (max-width: 399px) {
  .login-page { padding-inline: clamp(8px, (100vw - 304px) / 2, 16px); }
  .login-header { padding-inline-start: 20px; }
  .login-content__inner { padding-inline: 20px; }
  .turnstile-field { margin-inline: -19px; }
}

@media (prefers-reduced-motion: reduce) {
  .login-panel,
  .login-panel *,
  .login-panel *::before,
  .login-panel *::after {
    animation: none !important;
    transition: none !important;
  }
}
</style>
