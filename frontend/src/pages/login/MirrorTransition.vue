<template>
  <Teleport to="body">
    <div class="mirror-transition" aria-hidden="true">
      <div ref="sheet" class="mirror-transition__sheet" :class="{ 'mirror-transition__sheet--opening': opening }">
        <div v-if="phase === 'word'" ref="word" class="mirror-transition__word" lang="en">
          <span v-for="(letter, index) in letters" :key="index" class="mirror-transition__lane" :style="{
            '--lane': `${letter.width}em`,
            '--tilt': `${letter.tilt}deg`,
            '--landing-delay': `${letter.delay}ms`,
            '--landing-duration': `${letter.duration}ms`,
          }">
            <span class="mirror-transition__letter" :class="{ 'mirror-transition__letter--erased': index >= visibleLetters }">{{ letter.glyph }}</span>
          </span>
        </div>
        <div v-else-if="phase === 'redirect'" class="mirror-transition__redirect" lang="zh-CN">{{ redirectCopy.slice(0, visibleLetters) }}</div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

const letters = [
  { glyph: 'C', width: 0.82, tilt: -13, delay: 60, duration: 950 },
  { glyph: 'h', width: 0.69, tilt: 10, delay: 178, duration: 1010 },
  { glyph: 'a', width: 0.68, tilt: -9, delay: 0, duration: 970 },
  { glyph: 't', width: 0.53, tilt: 13, delay: 230, duration: 1020 },
  { glyph: 'G', width: 0.86, tilt: -12, delay: 102, duration: 980 },
  { glyph: 'P', width: 0.73, tilt: 11, delay: 274, duration: 940 },
  { glyph: 'T', width: 0.72, tilt: -10, delay: 130, duration: 1000 },
]
const redirectCopy = '正在跳转'
const sheet = ref<HTMLElement | null>(null)
const word = ref<HTMLElement | null>(null)
const opening = ref(false)
const phase = ref<'waiting' | 'word' | 'redirect'>('waiting')
const visibleLetters = ref(letters.length)
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)')
const lifetime = new AbortController()
let sheetMotion: Animation | undefined

const pause = (ms: number) => new Promise<void>(resolve => {
  const finish = () => {
    window.clearTimeout(timer)
    lifetime.signal.removeEventListener('abort', finish)
    resolve()
  }
  const timer = window.setTimeout(finish, ms)
  lifetime.signal.addEventListener('abort', finish, { once: true })
})

onMounted(() => {
  if (reducedMotion.matches) return
  sheetMotion = sheet.value?.animate([
    { clipPath: 'inset(calc(50% - 1px) 47% calc(50% - 1px) 47%)' },
    { clipPath: 'inset(calc(50% - 1px) 6% calc(50% - 1px) 9%)' },
  ], { duration: 3900, fill: 'both', easing: 'cubic-bezier(.14,.55,.32,1)' })
})

const finish = async () => {
  const surface = sheet.value
  if (!surface) return
  const moving = !reducedMotion.matches
  const seam = getComputedStyle(surface).clipPath
  opening.value = true
  sheetMotion?.cancel()

  if (moving) {
    sheetMotion = surface.animate([
      { clipPath: seam },
      { clipPath: 'inset(3% 0% calc(50% - 1px) 6%)', offset: 0.51 },
      { clipPath: 'inset(0% 0% 0% 0%)' },
    ], { duration: 560, fill: 'both', easing: 'cubic-bezier(.33,.05,.24,1)' })
    await sheetMotion.finished.catch(() => undefined)
    sheetMotion.cancel()
  }
  if (lifetime.signal.aborted) return

  phase.value = 'word'
  await nextTick()
  if (moving) await Promise.allSettled(word.value?.getAnimations({ subtree: true }).map(animation => animation.finished) ?? [])
  if (lifetime.signal.aborted) return
  await pause(500)
  for (let remaining = letters.length - 1; remaining >= 0 && !lifetime.signal.aborted; remaining--) {
    visibleLetters.value = remaining
    await pause(remaining === 0 ? 75 : 55)
  }
  if (lifetime.signal.aborted) return

  phase.value = 'redirect'
  for (let count = 1; count <= redirectCopy.length && !lifetime.signal.aborted; count++) {
    visibleLetters.value = count
    await pause(count === redirectCopy.length ? 50 : 95)
  }
}

onBeforeUnmount(() => {
  lifetime.abort()
  sheetMotion?.cancel()
})

defineExpose({ finish })
</script>

<style scoped>
.mirror-transition {
  position: fixed;
  inset: 0;
  z-index: 10050;
  overflow: hidden;
  touch-action: none;
}

.mirror-transition__sheet {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  overflow: hidden;
  clip-path: inset(calc(50% - 1px) 34% calc(50% - 1px) 34%);
  background: #111113;
  color: #f5f4f2;
}

.mirror-transition__sheet::before {
  position: absolute;
  top: calc(50% - 1px);
  inset-inline: 0;
  height: 1px;
  background: #858589;
  content: '';
  transition: opacity 150ms linear;
}

.mirror-transition__sheet--opening { clip-path: inset(0); }
.mirror-transition__sheet--opening::before { opacity: 0; }

.mirror-transition__word {
  display: flex;
  justify-content: center;
  font: 650 clamp(38px, 11vw, 100px) / 1.23 system-ui, sans-serif;
  text-shadow: 0 0 .65px rgb(245 244 242 / 36%);
  -webkit-font-smoothing: antialiased;
}

.mirror-transition__lane {
  display: grid;
  width: var(--lane);
  overflow-x: clip;
  overflow-y: visible;
  justify-items: center;
}

.mirror-transition__letter {
  display: block;
  transform-origin: 50% 83%;
  animation: mirror-letter-landing var(--landing-duration) linear var(--landing-delay) both;
}

.mirror-transition__letter--erased { visibility: hidden; }

.mirror-transition__redirect {
  font: 520 clamp(24px, 5vw, 44px) / 1.35 system-ui, sans-serif;
  min-width: 4em;
  white-space: nowrap;
  -webkit-font-smoothing: antialiased;
}

@keyframes mirror-letter-landing {
  0% { transform: translateY(-64vh) rotate(var(--tilt)) scale(0.94); animation-timing-function: cubic-bezier(.58,.04,1,.61); }
  59% { transform: translateY(.035em) rotate(calc(var(--tilt) * -.42)) scale(1.04, .93); animation-timing-function: cubic-bezier(.14,.6,.36,1); }
  74% { transform: translateY(-.15em) rotate(calc(var(--tilt) * .26)) scale(.99, 1.02); animation-timing-function: ease-in; }
  87% { transform: translateY(.013em) rotate(calc(var(--tilt) * -.15)) scale(1.012, .985); animation-timing-function: ease-out; }
  100% { transform: none; }
}

@media (prefers-reduced-motion: reduce) {
  .mirror-transition__letter { animation: none; }
  .mirror-transition__sheet::before { transition: none; }
}
</style>
