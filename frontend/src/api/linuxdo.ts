import { getLoginCooldown, LoginCoolingError, LoginVerificationError } from './login-guard'

export const linuxdoRequest = async (action: string, csrf: string, body?: object, method = 'POST') => {
  const response = await fetch(`/0x/user/oauth/linuxdo/${action}`, {
    method, cache: 'no-store',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
    body: body ? JSON.stringify(body) : undefined
  })
  const data = await response.json()
  if (!response.ok) {
    if (typeof data?.remaining_seconds === 'number') throw new LoginCoolingError(data.remaining_seconds)
    if (data?.code === 'fingerprint_required') throw new LoginVerificationError(data.message)
    // The gateway deliberately returns an empty 401 for non-login routes during cooldown.
    if (response.status === 401) {
      const seconds = await getLoginCooldown()
      if (seconds) throw new LoginCoolingError(seconds)
    }
    throw new Error(data?.message || data?.detail || 'Linux DO 登录暂时不可用，请重试')
  }
  return data
}

const linuxdoErrors: Readonly<Record<string, string>> = {
  cancelled: 'Linux DO 授权已取消',
  expired: 'Linux DO 登录已过期，请重新授权',
  unavailable: '此 Linux DO 账号暂时无法登录本站',
  failed: 'Linux DO 登录暂时不可用，请重试'
}

export const linuxdoError = (code: unknown): string =>
  Object.prototype.hasOwnProperty.call(linuxdoErrors, String(code))
    ? linuxdoErrors[String(code)] : linuxdoErrors.failed
