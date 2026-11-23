<template>
  <span class="rocket-progress" :class="{ 'rocket-progress--complete': complete }" aria-hidden="true">
    <canvas ref="surface" class="rocket-progress__canvas"></canvas>
    <span v-if="unavailable" class="rocket-progress__fallback"></span>
  </span>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { drawFlight } from './rocket-scene'

const props = defineProps<{ complete: boolean }>()
const surface = ref<HTMLCanvasElement | null>(null)
const unavailable = ref(false)
let frame = 0
let observer: ResizeObserver | undefined

onMounted(() => {
  const canvas = surface.value
  const context = canvas?.getContext('2d')
  if (!canvas || !context) {
    unavailable.value = true
    return
  }

  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches
  const started = performance.now()
  let width = 0
  let height = 0
  let finishing: { time: number; progress: number } | undefined
  let lastPosition = 0

  const paint = (timestamp: number) => {
    if (width <= 0 || height <= 0) return

    const elapsed = (timestamp - started) / 1000
    const style = getComputedStyle(canvas)
    const palette = {
      ink: style.getPropertyValue('--login-button-ink').trim(),
      surface: style.getPropertyValue('--login-button-color').trim()
    }
    if (props.complete && !finishing) finishing = { time: timestamp, progress: lastPosition }
    if (reduced) {
      drawFlight(context, palette, width, height, 0, 0.52)
      return
    }
    if (finishing) {
      const advance = Math.min(1, (timestamp - finishing.time) / 138)
      lastPosition = finishing.progress + (1 - finishing.progress) * (1 - (1 - advance) ** 2)
    } else {
      const cycle = (elapsed % 1.78) / 1.78
      lastPosition = cycle * (0.78 + 0.22 * cycle)
    }
    drawFlight(context, palette, width, height, elapsed, lastPosition)
  }

  const resize = () => {
    const bounds = canvas.getBoundingClientRect()
    width = bounds.width
    height = bounds.height
    const ratio = Math.min(2, devicePixelRatio)
    canvas.width = Math.round(width * ratio)
    canvas.height = Math.round(height * ratio)
    context.setTransform(ratio, 0, 0, ratio, 0, 0)
    paint(performance.now())
  }

  const tick = (time: number) => {
    paint(time)
    if (finishing && lastPosition >= 1) return
    frame = requestAnimationFrame(tick)
  }

  resize()
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(resize)
    observer.observe(canvas)
  }
  if (!reduced) frame = requestAnimationFrame(tick)
})

onBeforeUnmount(() => {
  cancelAnimationFrame(frame)
  observer?.disconnect()
})
</script>

<style scoped>
.rocket-progress {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}

.rocket-progress__canvas {
  display: block;
  width: 100%;
  height: 100%;
}

.rocket-progress__fallback {
  position: absolute;
  inset: auto 14px 6px;
  height: 2px;
  border-radius: 5px;
  background: currentColor;
  animation: reveal-trail 1.1s ease-in-out infinite alternate;
}

@keyframes reveal-trail {
  from { opacity: 0.25; transform: scaleX(0.25); }
  to { opacity: 0.8; transform: scaleX(1); }
}

@media (prefers-reduced-motion: reduce) {
  .rocket-progress__fallback { animation: none; }
}
</style>
