import { defineStore } from 'pinia'
import { ref } from 'vue'

const clearAccessibleCookies = () => {
  const cookies = document.cookie.split(';')
  for (const entry of cookies) {
    const [rawName] = entry.split('=', 1)
    const name = rawName?.trim()
    if (!name) continue
    document.cookie = `${name}=; Path=/; Max-Age=0`
  }
}

export const useUserStore = defineStore('user', () => {
  const authenticated = ref(false)
  const isAdmin = ref(false)
  const username = ref('')
  const csrfToken = ref('')
  let hydrated = false

  const setIsAdmin = (admin: boolean) => {
    isAdmin.value = admin
  }

  const setUsername = (name: string) => {
    username.value = name
  }

  const setCsrfToken = (token: string) => {
    csrfToken.value = token
  }

  const prepareCsrf = async () => {
    const response = await fetch('/0x/user/version-cfg', { cache: 'no-store' })
    if (!response.ok) throw new Error('无法准备登录验证，请重试')
    const config = await response.json()
    if (!config.csrf_token) throw new Error('无法准备登录验证，请重试')
    setCsrfToken(config.csrf_token)
  }

  const login = async (url: string, data: any, beforeConfirm: () => void = () => {}) => {
    await prepareCsrf()
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken.value
      },
      body: JSON.stringify(data)
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.message || '登录失败')
    }

    const prepared = await response.json()
    if (!prepared.login_ticket) throw new Error('登录确认无效，请重试')
    // No authenticated cookie exists before this callback accepts the current challenge.
    beforeConfirm()
    const confirmation = await fetch('/0x/user/login-confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken.value },
      body: JSON.stringify({ login_ticket: prepared.login_ticket })
    })
    if (!confirmation.ok) {
      const error = await confirmation.json()
      throw new Error(error.message || '登录确认失败，请重新验证')
    }
    const result = await confirmation.json()
    
    authenticated.value = Boolean(result.authenticated)
    setUsername(result.username || data.username || '')
    setIsAdmin(Boolean(result.is_admin))
    setCsrfToken(result.csrf_token || '')
    hydrated = true

    return result
  }

  const hydrate = async () => {
    if (hydrated) return authenticated.value
    hydrated = true
    try {
      const response = await fetch('/0x/user/me')
      if (!response.ok) return false
      const result = await response.json()
      authenticated.value = Boolean(result.authenticated)
      isAdmin.value = Boolean(result.is_admin)
      username.value = result.username || ''
      csrfToken.value = result.csrf_token || ''
      return authenticated.value
    } catch {
      return false
    }
  }

  const logout = async () => {
    await prepareCsrf()
    const activeCsrfToken =
      csrfToken.value || document.cookie.match(/(?:^|; )csrftoken=([^;]*)/)?.[1] || ''
    const response = await fetch('/0x/user/logout', {
      method: 'POST',
      keepalive: true,
      headers: activeCsrfToken ? { 'X-CSRFToken': decodeURIComponent(activeCsrfToken) } : {}
    })
    if (!response.ok) throw new Error('退出未完成，请重试')
    authenticated.value = false
    isAdmin.value = false
    username.value = ''
    csrfToken.value = ''
    clearAccessibleCookies()
  }

  return {
    authenticated,
    isAdmin,
    username,
    csrfToken,
    setIsAdmin,
    setUsername,
    setCsrfToken,
    login,
    hydrate,
    logout
  }
})
