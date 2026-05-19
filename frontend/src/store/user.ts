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
  const token = ref(localStorage.getItem('admin_token') || '')
  const isAdmin = ref(localStorage.getItem('is_admin') === 'true')
  const username = ref(localStorage.getItem('username') || '')

  const setToken = (newToken: string) => {
    token.value = newToken
    localStorage.setItem('admin_token', newToken)
  }

  const setIsAdmin = (admin: boolean) => {
    isAdmin.value = admin
    localStorage.setItem('is_admin', String(admin))
  }

  const setUsername = (name: string) => {
    username.value = name
    localStorage.setItem('username', name)
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
    
    if (result.admin_token) {
      setToken(result.admin_token)
      if (data.username) {
        setUsername(data.username)
      }
      if (result.is_admin) {
        setIsAdmin(true)
      }
    }

    return result
  }

  const logout = () => {
    token.value = ''
    isAdmin.value = false
    username.value = ''
    localStorage.removeItem('admin_token')
    localStorage.removeItem('is_admin')
    localStorage.removeItem('username')
    clearAccessibleCookies()
  }

  return {
    token,
    isAdmin,
    username,
    setToken,
    setIsAdmin,
    setUsername,
    login,
    logout
  }
})
