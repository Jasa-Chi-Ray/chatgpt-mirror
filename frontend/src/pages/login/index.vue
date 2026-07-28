<template>
  <main class="login-page">
    <section class="login-panel" aria-labelledby="login-title">
      <div v-if="cfg.notice" class="login-notice" role="status">
        {{ cfg.notice }}
      </div>

      <header class="login-header">
        <h1 id="login-title">{{ isRegister ? '创建账户' : '欢迎回来' }}</h1>
        <p>{{ isRegister ? '填写账号信息以完成注册' : '输入账号信息以继续' }}</p>
      </header>

      <t-loading :loading="loading" class="login-loading">
        <t-form
          ref="loginFormRef"
          :data="loginForm"
          :label-width="0"
          :rules="rules"
          class="login-form"
          @submit="onSubmit"
        >
          <div class="form-field">
            <label for="login-username">用户名</label>
            <t-form-item name="username">
              <t-input
                id="login-username"
                v-model="loginForm.username"
                autocomplete="username"
                placeholder="请输入用户名"
                size="large"
              ></t-input>
            </t-form-item>
          </div>

          <div class="form-field">
            <label for="login-password">密码</label>
            <t-form-item name="password">
              <t-input
                id="login-password"
                v-model="loginForm.password"
                type="password"
                :autocomplete="isRegister ? 'new-password' : 'current-password'"
                placeholder="请输入密码"
                size="large"
              ></t-input>
            </t-form-item>
          </div>

          <div v-if="isRegister" class="form-field">
            <label for="register-upstream-token">上游账号令牌</label>
            <t-form-item name="chatgpt_token">
              <t-textarea
                id="register-upstream-token"
                v-model="loginForm.chatgpt_token"
                placeholder="请粘贴用于绑定的账号令牌"
                :autosize="{ minRows: 3, maxRows: 5 }"
              ></t-textarea>
            </t-form-item>
          </div>

          <div v-if="turnstileEnabled" class="turnstile-field">
            <div ref="turnstileContainer" class="turnstile-widget"></div>
            <p v-if="turnstileError" class="turnstile-error" role="alert">
              {{ turnstileError }}
            </p>
          </div>

          <t-form-item class="submit-item">
            <t-button
              type="submit"
              size="large"
              class="login-button"
              :disabled="turnstileEnabled && !turnstileToken"
            >
              {{ isRegister ? '创建账户' : '登录' }}
            </t-button>
          </t-form-item>
        </t-form>
      </t-loading>

      <p class="account-switch">
        <template v-if="isRegister">
          已有账户？
          <router-link to="/login">登录</router-link>
        </template>
        <template v-else>
          还没有账户？
          <router-link to="/register">创建账户</router-link>
        </template>
      </p>

      <div class="login-divider" aria-hidden="true">
        <span>或</span>
      </div>

      <button
        class="free-button"
        type="button"
        :disabled="loading || (turnstileEnabled && !turnstileToken)"
        @click="goFree"
      >
        免费体验
      </button>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { MessagePlugin } from 'tdesign-vue-next'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
const loading = ref(false)
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

const loginForm = reactive({
  username: '',
  password: '',
  chatgpt_token: ''
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  chatgpt_token: [{ required: true, message: '请输入上游账号令牌', trigger: 'blur' }]
}

const isRegister = computed(() => {
  return route.path.endsWith('/register')
})
const turnstileEnabled = computed(() => {
  return cfg.value.turnstile_enabled && Boolean(cfg.value.turnstile_site_key)
})

let turnstileScriptPromise: Promise<void> | null = null

const loadTurnstileScript = () => {
  if (window.turnstile) return Promise.resolve()
  if (turnstileScriptPromise) return turnstileScriptPromise

  turnstileScriptPromise = new Promise((resolve, reject) => {
    const existingScript = document.querySelector<HTMLScriptElement>('script[data-turnstile-script]')
    if (existingScript) {
      existingScript.addEventListener('load', () => resolve(), { once: true })
      existingScript.addEventListener('error', () => reject(new Error('load failed')), { once: true })
      return
    }

    const script = document.createElement('script')
    script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
    script.async = true
    script.defer = true
    script.dataset.turnstileScript = 'true'
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('load failed'))
    document.head.appendChild(script)
  })

  return turnstileScriptPromise
}

const removeTurnstile = () => {
  if (turnstileWidgetId.value && window.turnstile) {
    window.turnstile.remove(turnstileWidgetId.value)
  }
  turnstileWidgetId.value = null
  turnstileToken.value = ''
}

const resetTurnstile = () => {
  turnstileToken.value = ''
  if (turnstileWidgetId.value && window.turnstile) {
    window.turnstile.reset(turnstileWidgetId.value)
  }
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
        turnstileToken.value = ''
        turnstileError.value = '验证已过期，请重新验证'
      },
      'error-callback': () => {
        turnstileToken.value = ''
        turnstileError.value = '人机验证加载失败，请刷新页面'
      }
    })
  } catch {
    turnstileError.value = '人机验证加载失败，请刷新页面'
  }
}

onMounted(async () => {
  if (route.query.logout === '1') {
    userStore.logout()
  }
  await getVersionCfg()
  await renderTurnstile()
})

watch(isRegister, async () => {
  if (turnstileEnabled.value) {
    removeTurnstile()
    await renderTurnstile()
  }
})

onBeforeUnmount(() => {
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

const onSubmit = async ({ validateResult }: any) => {
  if (validateResult === true) {
    if (turnstileEnabled.value && !turnstileToken.value) {
      MessagePlugin.warning('请完成人机验证')
      return
    }

    loading.value = true
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
        turnstile_token: turnstileToken.value
      })
      
      if (data.admin_token && data.is_admin) {
        router.push({ name: 'User' })
      } else if (data.admin_token) {
        router.push({ name: 'LoginChatgpt' })
      }
    } catch (error: any) {
      MessagePlugin.error(error.message || '操作失败')
      resetTurnstile()
    }
    loading.value = false
  }
}

const goFree = async () => {
  if (turnstileEnabled.value && !turnstileToken.value) {
    MessagePlugin.warning('请完成人机验证')
    return
  }

  loading.value = true
  try {
    const data = await userStore.login('/0x/user/login-free', {
      turnstile_token: turnstileToken.value
    })
    if (data.admin_token) {
      router.push({ name: 'LoginChatgpt' })
    }
  } catch (error: any) {
    MessagePlugin.error(error.message || '免费体验暂不可用')
    resetTurnstile()
  }
  loading.value = false
}
</script>

<style scoped>
.login-page {
  --login-bg: #f7f7f5;
  --login-surface: #ffffff;
  --login-text: #20201e;
  --login-muted: #6f6f6b;
  --login-border: #d9d9d5;
  --login-border-hover: #aaa9a3;
  --login-action: #252523;

  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  min-height: 100dvh;
  padding: 48px 24px;
  color: var(--login-text);
  background: var(--login-bg);
}

.login-panel {
  width: 100%;
  max-width: 380px;
}

.login-notice {
  margin-bottom: 24px;
  padding: 12px 14px;
  color: #4f4f4b;
  font-size: 14px;
  line-height: 1.5;
  background: #efefec;
  border: 1px solid #e2e2de;
  border-radius: 8px;
}

.login-header {
  margin-bottom: 32px;
  text-align: center;
}

.login-header h1 {
  margin: 0;
  font-size: 30px;
  font-weight: 600;
  line-height: 1.25;
  letter-spacing: -0.02em;
  text-wrap: balance;
}

.login-header p {
  margin: 10px 0 0;
  color: var(--login-muted);
  font-size: 15px;
  line-height: 1.6;
}

.login-loading {
  display: block;
  width: 100%;
}

.form-field {
  margin-bottom: 20px;
}

.form-field label {
  display: inline-block;
  margin-bottom: 8px;
  color: #373735;
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
}

.form-field :deep(.t-form__item) {
  margin-bottom: 0;
}

.form-field :deep(.t-input) {
  min-height: 50px;
  padding: 0 14px;
  color: var(--login-text);
  background: var(--login-surface);
  border-color: var(--login-border);
  border-radius: 8px;
  box-shadow: none;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}

.form-field :deep(.t-textarea) {
  padding: 12px 14px;
  background: var(--login-surface);
  border-color: var(--login-border);
  border-radius: 8px;
  box-shadow: none;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}

.form-field :deep(.t-textarea:hover) {
  border-color: var(--login-border-hover);
}

.form-field :deep(.t-textarea--focused) {
  border-color: var(--login-action);
  box-shadow: 0 0 0 1px var(--login-action);
}

.form-field :deep(.t-textarea__inner) {
  color: var(--login-text);
  font-size: 15px;
  line-height: 1.6;
}

.form-field :deep(.t-input:hover) {
  border-color: var(--login-border-hover);
}

.form-field :deep(.t-input--focused) {
  border-color: var(--login-action);
  box-shadow: 0 0 0 1px var(--login-action);
}

.form-field :deep(.t-input__inner) {
  color: var(--login-text);
  font-size: 16px;
}

.form-field :deep(.t-form__controls-content) {
  display: block;
}

.form-field :deep(.t-form__status) {
  margin-top: 7px;
  font-size: 13px;
}

.submit-item {
  margin: 28px 0 0;
}

.submit-item :deep(.t-form__controls-content) {
  display: block;
}

.turnstile-field {
  min-height: 65px;
  margin-top: 4px;
}

.turnstile-widget {
  width: 100%;
  min-height: 65px;
}

.turnstile-error {
  margin: 8px 0 0;
  color: #a3413a;
  font-size: 13px;
  line-height: 1.5;
}

.login-button {
  width: 100%;
  height: 50px;
  color: #f9f9f7;
  font-size: 15px;
  font-weight: 600;
  background: var(--login-action);
  border-color: var(--login-action);
  border-radius: 8px;
  box-shadow: none;
  transition: background 0.18s ease, border-color 0.18s ease, transform 0.18s ease;
}

.login-button:hover {
  background: #3a3a37;
  border-color: #3a3a37;
}

.login-button:active {
  background: #171715;
  border-color: #171715;
  transform: translateY(1px);
}

.login-button:focus-visible,
.free-button:focus-visible,
.account-switch a:focus-visible {
  outline: 2px solid var(--login-action);
  outline-offset: 3px;
}

.account-switch {
  margin: 22px 0 0;
  text-align: center;
  color: var(--login-muted);
  font-size: 14px;
  line-height: 22px;
}

.account-switch a {
  color: var(--login-text);
  font-weight: 600;
  text-decoration: underline;
  text-decoration-color: #b8b8b3;
  text-underline-offset: 3px;
}

.account-switch a:hover {
  text-decoration-color: var(--login-text);
}

.login-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 24px 0;
  color: #8a8a85;
  font-size: 13px;
}

.login-divider::before,
.login-divider::after {
  flex: 1;
  height: 1px;
  background: #dfdfdb;
  content: "";
}

.free-button {
  width: 100%;
  height: 50px;
  padding: 0 16px;
  color: var(--login-text);
  font: inherit;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  background: var(--login-surface);
  border: 1px solid var(--login-border);
  border-radius: 8px;
  transition: background 0.18s ease, border-color 0.18s ease, transform 0.18s ease;
}

.free-button:hover:not(:disabled) {
  background: #efefec;
  border-color: var(--login-border-hover);
}

.free-button:active:not(:disabled) {
  transform: translateY(1px);
}

.free-button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

@media (max-width: 520px) {
  .login-page {
    align-items: flex-start;
    padding: 72px 24px 40px;
  }

  .login-header {
    margin-bottom: 28px;
  }

  .login-header h1 {
    font-size: 28px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .login-page *,
  .login-page *::before,
  .login-page *::after {
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
  }
}
</style>
