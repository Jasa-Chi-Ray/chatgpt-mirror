<template>
  <div class="language-switch" :data-language="language" role="group" :aria-label="label">
    <span class="language-switch__indicator" aria-hidden="true"></span>
    <button type="button" lang="zh-CN" :aria-pressed="language === 'zh-CN'" @click="appearance.setLanguage('zh-CN')">简中</button>
    <button type="button" lang="en" :aria-pressed="language === 'en'" @click="appearance.setLanguage('en')">EN</button>
  </div>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useAppearanceStore } from '@/store/appearance'

defineProps<{ label: string }>()

const appearance = useAppearanceStore()
const { language } = storeToRefs(appearance)
</script>

<style scoped>
.language-switch {
  --language-gap: 2px;
  position: relative;
  display: grid;
  grid-template-columns: repeat(2, minmax(var(--language-width, 34px), 1fr));
  flex: 0 0 auto;
  align-items: center;
  gap: var(--language-gap);
  padding: var(--language-inset, 2px);
  border: 1px solid var(--language-border, var(--app-border));
  border-radius: var(--language-radius, 8px);
  background-color: var(--language-surface, var(--app-field));
  isolation: isolate;
}

.language-switch__indicator {
  position: absolute;
  inset-block: var(--language-inset, 2px);
  inset-inline-start: var(--language-inset, 2px);
  width: calc((100% - 2 * var(--language-inset, 2px) - var(--language-gap)) / 2);
  border-radius: 5px;
  background: var(--language-selected, var(--app-text));
  pointer-events: none;
}

.language-switch[data-language="en"] .language-switch__indicator {
  transform: translateX(calc(100% + var(--language-gap)));
}

.language-switch button {
  position: relative;
  display: grid;
  place-items: center;
  min-height: 29px;
  padding: 0 4px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--language-text, var(--app-text));
  font-size: 12px;
  font-weight: 640;
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
}

.language-switch button[aria-pressed="true"] { color: var(--language-selected-text, var(--app-surface)); }
.language-switch button:hover:not([aria-pressed="true"]) { color: var(--language-hover, var(--app-action)); }

.language-switch button:focus-visible {
  outline: 2px solid var(--language-focus, var(--app-action));
  outline-offset: 2px;
}

@media (prefers-reduced-motion: no-preference) {
  .language-switch__indicator { transition: transform 250ms cubic-bezier(.22,.67,.29,1); }
  .language-switch button { transition: color 160ms ease; }
}
</style>
