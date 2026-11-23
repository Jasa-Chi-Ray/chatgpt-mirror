type Destination = 'admin' | 'session' | 'profile' | 'login'
type Opening = { destination: Destination; rectangle: DOMRect; radius: string; source: HTMLElement }

let pending: Opening | undefined

export const queueWindowOpening = (card: HTMLElement, destination: Destination) => {
  const opening: Opening = {
    destination,
    rectangle: card.getBoundingClientRect(),
    radius: getComputedStyle(card).borderTopLeftRadius,
    source: card,
  }
  pending = opening
  return () => {
    if (pending === opening) pending = undefined
  }
}

export const takeWindowOpening = (destination: Destination) => {
  const opening = pending
  if (opening?.destination !== destination) return
  pending = undefined
  return opening
}

export const openingClip = (opening: Opening, target: DOMRect) => {
  const { rectangle, radius } = opening
  return `inset(${Math.max(0, rectangle.top - target.top)}px ${Math.max(0, target.right - rectangle.right)}px ${Math.max(0, target.bottom - rectangle.bottom)}px ${Math.max(0, rectangle.left - target.left)}px round ${radius})`
}

export const animateWindowOpening = (opening: Opening, frame: HTMLElement) => {
  const bounds = frame.getBoundingClientRect()
  const radius = getComputedStyle(frame).borderTopLeftRadius
  const belowViewport = Math.max(0, bounds.bottom - window.innerHeight)
  return frame.animate([
    { clipPath: openingClip(opening, bounds) },
    { clipPath: `inset(0px 0px ${belowViewport}px 0px round ${radius})` },
  ], { duration: 495, easing: 'cubic-bezier(.22,.64,.29,1)', fill: 'both' })
}

const frameBounds = (rectangle: DOMRect) => ({
  left: `${rectangle.left}px`,
  top: `${rectangle.top}px`,
  width: `${rectangle.width}px`,
  height: `${rectangle.height}px`,
})

export const animateWindowClosing = async (opening: Opening, panel: HTMLElement, signal: AbortSignal) => {
  if (signal.aborted) return
  const viewportWidth = document.documentElement.clientWidth
  const viewportHeight = window.innerHeight
  const left = Math.max(0, opening.rectangle.left)
  const top = Math.max(0, opening.rectangle.top)
  const width = Math.min(viewportWidth, opening.rectangle.right) - left
  const height = Math.min(viewportHeight, opening.rectangle.bottom) - top
  if (width <= 0 || height <= 0) return

  const outline = document.createElement('div')
  outline.className = 'window-closing-outline'
  outline.setAttribute('aria-hidden', 'true')
  const panelStyle = getComputedStyle(panel)
  outline.style.backgroundColor = panelStyle.backgroundColor
  outline.style.color = panelStyle.getPropertyValue('--login-ink').trim()
  document.body.append(outline)

  const duration = 450
  const start = { ...frameBounds(new DOMRect(left, top, width, height)), borderRadius: opening.radius }
  const closingBounds = () => [
    start,
    { ...frameBounds(panel.getBoundingClientRect()), borderRadius: panelStyle.borderRadius },
  ]
  const shrink = outline.animate(closingBounds(), { duration, easing: 'cubic-bezier(.27,.7,.3,1)', fill: 'both' })
  const fade = outline.animate([
    { opacity: 1 },
    { opacity: 1, offset: .58 },
    { opacity: 0 },
  ], { duration, fill: 'both' })
  const reveal = panel.animate([
    { opacity: 0 },
    { opacity: 1 },
  ], { delay: 230, duration: duration - 230, easing: 'ease-out', fill: 'both' })

  const effect = shrink.effect
  const observer = typeof ResizeObserver !== 'undefined' && effect instanceof KeyframeEffect
    ? new ResizeObserver(() => effect.setKeyframes(closingBounds()))
    : undefined
  observer?.observe(panel)
  const stop = () => {
    observer?.disconnect()
    shrink.cancel()
    fade.cancel()
    reveal.cancel()
    outline.remove()
  }
  window.addEventListener('resize', stop, { once: true })
  signal.addEventListener('abort', stop, { once: true })
  try {
    await shrink.finished.catch(() => undefined)
  } finally {
    window.removeEventListener('resize', stop)
    signal.removeEventListener('abort', stop)
    stop()
  }
}

export const leaveOpeningSource = (element: Element, done: () => void) => {
  const opening = pending
  if (!(element instanceof HTMLElement) || !opening || !element.contains(opening.source)) {
    done()
    return
  }

  // Keep the outgoing window at its measured position while the next view mounts.
  const closing = opening.destination === 'login'
  element.inert = true
  element.classList.add('opening-source-leaving')
  Object.assign(opening.source.style, frameBounds(opening.rectangle))
  const fade = element.animate([{ opacity: 1 }, { opacity: 0 }], {
    duration: closing ? 145 : 190,
    easing: 'cubic-bezier(.55,0,.72,.4)',
    fill: 'forwards',
  })
  void fade.finished.then(done, done)
}
