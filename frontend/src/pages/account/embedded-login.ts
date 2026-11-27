export const embeddedLoginMessageType = 'mirror:web-login:complete'

export function isEmbeddedLoginCompletion(
  event: Pick<MessageEvent, 'origin' | 'source' | 'data'>,
  origin: string,
  frame: Window | null,
  flow: string,
): boolean {
  const data: unknown = event.data
  return Boolean(frame && /^[a-f0-9]{64}$/.test(flow)
    && event.origin === origin && event.source === frame
    && data !== null && typeof data === 'object' && !Array.isArray(data)
    && 'type' in data && data.type === embeddedLoginMessageType
    && 'flow' in data && data.flow === flow)
}
