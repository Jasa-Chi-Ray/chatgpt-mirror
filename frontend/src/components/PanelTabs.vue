<template>
  <div ref="bar" v-bind="$attrs" class="panel-tabs" role="tablist" :aria-label="label" @keydown="move">
    <button
      v-for="item in items"
      :key="item.value"
      :id="`${tabId}-${item.value}`"
      type="button"
      role="tab"
      :aria-selected="model === item.value"
      :aria-controls="$slots[item.value] ? `${tabId}-panel-${item.value}` : undefined"
      :tabindex="model === item.value ? 0 : -1"
      @click="model = item.value"
    >{{ item.label }}</button>
  </div>
  <template v-for="item in items" :key="item.value">
    <div
      v-if="$slots[item.value]"
      v-show="model === item.value"
      :id="`${tabId}-panel-${item.value}`"
      :aria-labelledby="`${tabId}-${item.value}`"
      role="tabpanel"
    >
      <slot :name="item.value" />
    </div>
  </template>
</template>

<script setup lang="ts" generic="Value extends string">
import { nextTick, ref, useId } from 'vue'

defineOptions({ inheritAttrs: false })
const model = defineModel<Value>({ required: true })
const props = defineProps<{ label: string; items: readonly { value: Value; label: string }[] }>()
const tabId = useId()
const bar = ref<HTMLElement | null>(null)

const move = async (event: KeyboardEvent) => {
  const items = props.items
  if (!items.length) return
  const selected = items.findIndex(item => item.value === model.value)
  let next: number
  switch (event.key) {
    case 'Home': next = 0; break
    case 'End': next = items.length - 1; break
    case 'ArrowLeft': next = (selected - 1 + items.length) % items.length; break
    case 'ArrowRight': next = (selected + 1) % items.length; break
    default: return
  }
  event.preventDefault()
  const value = items[next].value
  model.value = value
  await nextTick()
  bar.value?.querySelector<HTMLElement>('[aria-selected="true"]')?.focus()
}
</script>

<style scoped>
.panel-tabs { display: flex; gap: 6px; border-bottom: 1px solid var(--app-border); overflow-x: auto; }
.panel-tabs button { white-space: nowrap; padding: 10px 11px 8px; border: 0; border-bottom: 2px solid transparent; background: transparent; color: var(--app-text-muted); cursor: pointer; }
.panel-tabs button[aria-selected="true"] { border-bottom-color: var(--app-action); color: var(--app-action); font-weight: 640; }
.panel-tabs button:focus-visible { outline: 2px solid var(--app-action); outline-offset: -3px; }
@media (prefers-reduced-motion: no-preference) {
  .panel-tabs button { transition: border-color 160ms, color 160ms; }
}
</style>
