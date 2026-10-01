// Client-reported metadata only. Never use this value for authentication or rate limits.
export const detectBrowserIp = async (): Promise<string | null> => {
  let timer: ReturnType<typeof setTimeout> | undefined
  let controller: AbortController | undefined
  try {
    controller = new AbortController()
    const lookup = fetch('https://api64.ipify.org?format=json', {
      signal: controller.signal,
      credentials: 'omit',
      referrerPolicy: 'no-referrer',
      cache: 'no-store',
    }).then(async response => {
      if (!response.ok) return null
      const data = await response.json()
      const ip = typeof data?.ip === 'string' ? data.ip.trim() : ''
      // The backend performs full IP validation before storing this reference value.
      return ip && ip.length <= 45 && /^[0-9a-fA-F:.]+$/.test(ip) ? ip : null
    }).catch(() => null)
    const timeout = new Promise<null>(resolve => {
      timer = setTimeout(() => resolve(null), 1500)
    })
    return await Promise.race([lookup, timeout])
  } catch {
    return null
  } finally {
    clearTimeout(timer)
    controller?.abort()
  }
}
