import { useUserStore } from '@/store/user'
import { MessagePlugin } from 'tdesign-vue-next'
import router from '@/router'

const normalizeUrl = (url: string) => {
  const [path, query] = url.split('?', 2)
  const normalizedPath = (() => {
    if (path === '/0x/user') return '/0x/user/'
    if (path === '/0x/chatgpt') return '/0x/chatgpt/'
    if (path === '/0x/chatgpt/car') return '/0x/chatgpt/car'
    return path
  })()

  return query ? `${normalizedPath}?${query}` : normalizedPath
}

const extractErrorMessage = (error: any): string => {
  if (!error) return '请求失败'
  if (typeof error.message === 'string' && error.message.trim()) return error.message
  if (typeof error.detail === 'string' && error.detail.trim()) return error.detail
  if (Array.isArray(error.non_field_errors) && error.non_field_errors.length > 0) {
    return String(error.non_field_errors[0])
  }

  for (const [key, value] of Object.entries(error)) {
    if (Array.isArray(value) && value.length > 0) {
      return `${key}: ${value[0]}`
    }
    if (typeof value === 'string' && value.trim()) {
      return `${key}: ${value}`
    }
  }

  return '请求失败'
}

const parseResponseBody = async (response: Response) => {
  if (response.status === 204) return null

  const contentType = response.headers.get('content-type') || ''
  const text = await response.text()

  if (!text) return null

  if (contentType.includes('application/json')) {
    try {
      return JSON.parse(text)
    } catch {
      return { message: '接口返回了无效 JSON' }
    }
  }

  const plainText = text.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
  return {
    message: plainText || `接口返回了非 JSON 响应 (${response.status})`
  }
}

const request = async (url: string, method = 'GET', body?: any) => {
  const userStore = useUserStore()
  const { token } = userStore

  const headers: Record<string, string> = {
    'Content-Type': 'application/json'
  }

  if (token) {
    headers['Authorization'] = `token ${token}`
  }

  try {
    const response = await fetch(normalizeUrl(url), {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined
    })

    if (response.status === 401) {
      userStore.logout()
      router.push('/login')
      return null
    }

    if (response.status === 403) {
      MessagePlugin.error('没有权限')
      return null
    }

    if (response.status === 500) {
      MessagePlugin.error('系统异常')
      return null
    }

    const data = await parseResponseBody(response)

    if (!response.ok) {
      const error = data || { message: `请求失败 (${response.status})` }
      MessagePlugin.error(extractErrorMessage(error))
      return null
    }

    return data
  } catch (error) {
    MessagePlugin.error('网络错误')
    return null
  }
}

export default request
