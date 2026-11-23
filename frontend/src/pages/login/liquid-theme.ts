import type { ColorTheme } from '@/store/appearance'
import { createGlassRenderer, wavePointCount } from './liquid-glass'

type Transition = {
  ready: Promise<void>
  updateCallbackDone: Promise<void>
  skipTransition(): void
}

type TransitionDocument = Document & {
  startViewTransition?: (update: () => Promise<void>) => Transition
}

type Viewport = { width: number; height: number }

const point = (x: number, y: number) => `${x.toFixed(2)} ${y.toFixed(2)}`
const squared = (value: number) => value * value

const prepareWave = (viewport: Viewport, toLight: boolean, time: number, wave: Float32Array, quick: boolean) => {
  const { width, height } = viewport
  const amplitude = Math.max(48, Math.min(140, height * 0.16, width * 0.23))
  const motion = quick ? 1 - (1 - time) ** 1.65 : time * time * (3 - 2 * time)
  const margin = amplitude * (quick ? 1.15 : 2)
  const front = -margin + (height + 2 * margin) * motion
  const crest = 1.14 - time * 1.3
  const extent = 0.13 + time * 0.1
  for (let index = 0; index < wavePointCount; index += 1) {
    const t = index / (wavePointCount - 1)
    const x = toLight ? 1 - t : t
    const crestPosition = (x - crest) / extent
    const crestHeight = Math.exp(-squared(crestPosition)) - 0.35 * Math.exp(-squared(crestPosition + 1.35))
    const currents = Math.sin(x * 7.4 + time * 4.5) * 0.22 + Math.sin(x * 15.4 - time * 7.8) * 0.10
    wave[index * 2] = front + amplitude * (0.65 * crestHeight + currents + 0.37 * (x - 0.5))
    wave[index * 2 + 1] = Math.max(18, 46 + 41 * Math.abs(crestHeight) + currents * 23)
  }
}

const applyWave = (
  root: HTMLElement,
  viewport: Viewport,
  toLight: boolean,
  wave: Float32Array,
  useGlass: boolean
) => {
  const edge = []
  const litRim = []
  const darkRim = []
  const bound = toLight ? viewport.height + 2 : -2
  for (let index = 0; index < wavePointCount; index += 1) {
    const x = viewport.width * index / (wavePointCount - 1)
    const y = wave[index * 2]
    edge.push(`L ${point(x, y)}`)
    if (!useGlass) {
      litRim.push(point(x, y - 2))
      darkRim.push(point(x, y + 2.5))
    }
  }

  root.style.setProperty('--liquid-mask', `path("M 0 ${bound} ${edge.join(' ')} L ${viewport.width} ${bound} Z")`)
  if (!useGlass) {
    root.style.setProperty('--liquid-fallback-shape', `path("M ${litRim.join(' L ')} L ${darkRim.reverse().join(' L ')} Z")`)
  }
}

const captureScene = async (capture: typeof import('modern-screenshot').domToCanvas, page: HTMLElement, viewport: Viewport) => {
  const offset = page.getBoundingClientRect().top
  const scale = Math.min(1.15, Math.sqrt(1_800_000 / (viewport.width * viewport.height)))
  const transparentAsset = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'
  return capture(page, {
    width: viewport.width,
    height: viewport.height,
    scale,
    timeout: 720,
    font: false,
    backgroundColor: getComputedStyle(page).backgroundColor,
    style: {
      width: `${viewport.width}px`,
      height: `${page.offsetHeight}px`,
      transform: `translateY(${offset}px)`
    },
    filter: node => !(node instanceof Element && node.matches('iframe, canvas, script')),
    fetchFn: async url => url.startsWith('data:') ? url : transparentAsset,
    onCloneEachNode: cloned => {
      if (cloned instanceof HTMLInputElement && (cloned.id === 'login-password' || cloned.type === 'password')) {
        cloned.type = 'password'
        cloned.value = '•'.repeat(cloned.value.length)
        cloned.setAttribute('value', cloned.value)
      }
      if (cloned instanceof HTMLTextAreaElement && cloned.id === 'register-upstream-token') {
        cloned.value = ''
        cloned.textContent = ''
      }
    }
  })
}

const playFrames = (duration: number, draw: (progress: number) => void, signal: AbortSignal) =>
  new Promise<void>(resolve => {
    let frame = 0
    let start: number | undefined
    const stop = () => {
      cancelAnimationFrame(frame)
      signal.removeEventListener('abort', stop)
      document.removeEventListener('visibilitychange', stop)
      window.removeEventListener('resize', stop)
      resolve()
    }
    const tick = (now: number) => {
      start ??= now
      const progress = Math.min(1, (now - start) / duration)
      try {
        draw(progress)
      } catch {
        stop()
        return
      }
      if (progress === 1) stop()
      else frame = requestAnimationFrame(tick)
    }
    if (signal.aborted || document.hidden) return resolve()
    signal.addEventListener('abort', stop, { once: true })
    document.addEventListener('visibilitychange', stop, { once: true })
    window.addEventListener('resize', stop, { once: true })
    frame = requestAnimationFrame(tick)
  })

export const changeThemeWithLiquid = async (
  theme: ColorTheme,
  update: () => Promise<void>,
  signal: AbortSignal,
  canvas: HTMLCanvasElement | null,
  rendering: 'glass' | 'native' = 'glass'
) => {
  const page = canvas?.parentElement
  const transitionDocument = document as TransitionDocument
  const startTransition = transitionDocument.startViewTransition?.bind(transitionDocument)
  if (signal.aborted) return
  if (!canvas || !page || !startTransition || matchMedia('(prefers-reduced-motion: reduce)').matches) {
    await update()
    return
  }

  const root = document.documentElement
  const viewport = { width: root.clientWidth, height: window.innerHeight }
  const toLight = theme === 'light'
  const quick = rendering === 'native'
  const wave = new Float32Array(wavePointCount * 2)
  let gl: ReturnType<typeof createGlassRenderer> = null
  let before: HTMLCanvasElement | undefined
  let capture: typeof import('modern-screenshot').domToCanvas | undefined
  if (!quick) {
    try {
      gl = createGlassRenderer(canvas, viewport)
      if (gl) {
        capture = (await import('modern-screenshot')).domToCanvas
        before = await captureScene(capture, page, viewport)
      }
    } catch {
      gl?.dispose()
      gl = null
    }
  }

  if (signal.aborted) {
    gl?.dispose()
    return
  }
  if (document.hidden || viewport.width !== root.clientWidth || viewport.height !== window.innerHeight) {
    gl?.dispose()
    await update()
    return
  }

  let transition: Transition | undefined
  let glassReady = false
  const snapshotAfter = async () => {
    await update()
    if (!gl || !before || !capture || signal.aborted) return
    try {
      const after = await captureScene(capture, page, viewport)
      if (signal.aborted) return
      gl.setScenes(before, after)
      glassReady = true
      root.setAttribute('data-login-liquid-glass', '')
      gl.draw(wave, 0, toLight)
    } catch {
      glassReady = false
      root.removeAttribute('data-login-liquid-glass')
    }
  }

  root.dataset.loginLiquid = theme
  prepareWave(viewport, toLight, 0, wave, quick)
  applyWave(root, viewport, toLight, wave, false)
  const skip = () => transition?.skipTransition()
  signal.addEventListener('abort', skip, { once: true })
  try {
    try {
      transition = startTransition(snapshotAfter)
    } catch {
      await update()
      return
    }
    try {
      await transition.ready
    } catch {
      await transition.updateCallbackDone
      return
    }

    await playFrames(quick ? 590 : toLight ? 1130 : 1070, progress => {
      if (glassReady && gl?.lost()) {
        glassReady = false
        root.removeAttribute('data-login-liquid-glass')
      }
      prepareWave(viewport, toLight, progress, wave, quick)
      applyWave(root, viewport, toLight, wave, glassReady)
      if (glassReady) gl?.draw(wave, progress, toLight)
    }, signal)
  } finally {
    transition?.skipTransition()
    signal.removeEventListener('abort', skip)
    delete root.dataset.loginLiquid
    root.removeAttribute('data-login-liquid-glass')
    root.style.removeProperty('--liquid-mask')
    root.style.removeProperty('--liquid-fallback-shape')
    gl?.dispose()
  }
}
