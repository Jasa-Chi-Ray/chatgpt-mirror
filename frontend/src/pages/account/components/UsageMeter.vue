<template>
  <div class="usage-meter" :class="{ 'usage-meter--stale': usage?.stale }">
    <div class="usage-meter-heading"><span>{{ label }}</span><span>{{ measured ? `剩余 ${usage.remaining_percent}%` : '额度待同步' }}</span></div>
    <div v-if="measured" class="usage-meter-track" role="progressbar" :aria-label="`账号繁忙程度：${label}`" :aria-valuenow="usage.used_percent" aria-valuemin="0" aria-valuemax="100">
      <span :style="{ width: `${usage.used_percent}%`, backgroundSize: `${usage.used_percent > 0 ? 10000 / usage.used_percent : 100}% 100%` }"></span>
    </div>
    <div v-else class="usage-meter-track usage-meter-track--unknown"></div>
    <small>{{ checkedText }}<template v-if="usage?.stale && usage?.checked_at"> · 等待同步</template></small>
    <details v-if="detailed && (usage?.windows?.length || usage?.models?.length)" @click.stop>
      <summary>查看模型与额度窗口</summary>
      <div v-for="(window, index) in usage.windows" :key="`window-${index}`" class="usage-meter-detail">
        {{ window.name }} · 已用 {{ window.used_percent }}%<template v-if="window.reset_at"> · {{ new Date(window.reset_at * 1000).toLocaleString() }} 重置</template>
      </div>
      <div v-for="model in usage.models" :key="model.model" class="usage-meter-detail">
        {{ model.model }} · {{ model.available === true ? '可用' : model.available === false ? '额度已用完' : '待同步' }}
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
const props = defineProps<{ usage?: any; detailed?: boolean }>()
const now = ref(Math.floor(Date.now() / 1000))
const measured = computed(() => typeof props.usage?.used_percent === 'number')
const labels: Record<string, string> = { idle: '空闲', busy: '繁忙', full: '爆满', unknown: '待同步' }
const label = computed(() => labels[props.usage?.state] || '待同步')
const checkedText = computed(() => {
  if (!props.usage?.checked_at) return '尚未获取上游额度'
  const seconds = Math.max(0, now.value - props.usage.checked_at)
  return seconds < 60 ? `${seconds} 秒前更新` : seconds < 3600 ? `${Math.floor(seconds / 60)} 分钟前更新` : `${Math.floor(seconds / 3600)} 小时前更新`
})
let timer: ReturnType<typeof setInterval> | undefined
onMounted(() => { timer = setInterval(() => { now.value = Math.floor(Date.now() / 1000) }, 1000) })
onBeforeUnmount(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.usage-meter { display: grid; gap: 6px; width: 100%; min-width: 0; color: var(--app-text, #222); text-align: left; font-size: 12px; font-weight: 400; }
.usage-meter-heading { display: flex; justify-content: space-between; gap: 8px; }
.usage-meter-track { height: 7px; overflow: hidden; border-radius: 6px; background: var(--app-field, #e5e7eb); border: 1px solid var(--app-border, #d1d5db); }
.usage-meter-track > span { display: block; height: 100%; border-radius: inherit; background-image: linear-gradient(90deg, #16a34a 0%, #eab308 55%, #f97316 78%, #dc2626 100%); transition: width 300ms ease; }
.usage-meter-track--unknown { opacity: .5; }
.usage-meter small { font-size: 11px; color: var(--app-text-muted, #777); }
.usage-meter details { font-size: 11px; }
.usage-meter summary { cursor: pointer; }
.usage-meter-detail { padding-block: 4px; overflow-wrap: anywhere; }
@media (prefers-reduced-motion: reduce) { .usage-meter-track > span { transition: none; } }
</style>
