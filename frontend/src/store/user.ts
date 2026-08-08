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

  const login = async (url: string, data: any) => {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(data)
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.message || '登录失败')
    }

    const result = await response.json()
    
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
    const activeCsrfToken =
      csrfToken.value || document.cookie.match(/(?:^|; )csrftoken=([^;]*)/)?.[1] || ''
    if (authenticated.value) {
      try {
        await fetch('/0x/user/logout', {
          method: 'POST',
          keepalive: true,
          headers: activeCsrfToken ? { 'X-CSRFToken': decodeURIComponent(activeCsrfToken) } : {}
        })
      } catch {
        // 本地状态仍需清理；服务端 Token 会按 TTL 自动过期。
      }
    }
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
