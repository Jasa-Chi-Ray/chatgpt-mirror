export type ConnectionStatus = 'connected' | 'disconnected' | 'connecting' | 'needs-reconnect' | 'unavailable'

export interface ExternalConnection {
  pool?: boolean
  id: string
  label: string
  workspace?: string
  status: ConnectionStatus
  lastUpdated?: string
  expiresAt?: string
}

export const connectionStatusLabels: Record<ConnectionStatus, string> = {
  connected: '已连接',
  disconnected: '未连接',
  connecting: '连接中',
  'needs-reconnect': '需要重新连接',
  unavailable: '暂时异常',
}

const dateFormat = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

export function formatConnectionTime(value?: string) {
  const timestamp = value ? Date.parse(value) : NaN
  return Number.isFinite(timestamp) ? dateFormat.format(timestamp) : '—'
}
