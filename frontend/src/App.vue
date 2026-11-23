<template>
  <t-config-provider :global-config="config">
    <router-view v-slot="{ Component }">
      <Transition :css="false" @leave="leaveOpeningSource">
        <component :is="Component" />
      </Transition>
    </router-view>
  </t-config-provider>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watchEffect } from 'vue'
import { useRoute } from 'vue-router'
import english from 'tdesign-vue-next/es/locale/en_US'
import chinese from 'tdesign-vue-next/es/locale/zh_CN'
import { useAppearanceStore } from '@/store/appearance'
import { leaveOpeningSource } from '@/layouts/window-opening'
import { replayPressFeedback } from '@/layouts/press-feedback'

const appearance = useAppearanceStore()
const route = useRoute()
const config = computed(() => ({
  ...(appearance.language === 'en' ? english : chinese),
  animation: { exclude: ['ripple'] },
}))

onMounted(() => document.addEventListener('click', replayPressFeedback, true))
onBeforeUnmount(() => document.removeEventListener('click', replayPressFeedback, true))

watchEffect(() => {
  document.documentElement.setAttribute('theme-mode', appearance.theme)
  document.documentElement.lang = appearance.language
  document.documentElement.toggleAttribute('data-admin-workspace', Boolean(route.meta.requiresAdmin))
  document.documentElement.toggleAttribute('data-profile-workspace', route.name === 'Profile')
})
</script>

<style>
main:is(.login-page, .session-page, .account-layout).opening-source-leaving {
  position: fixed;
  inset: 0;
  z-index: 15;
  padding: 0;
  background: transparent;
  overflow: clip;
  pointer-events: none;
}

main.opening-source-leaving :is(.login-panel, .session-frame, .account-frame) {
  position: absolute;
  margin: 0;
  max-width: none;
  min-height: 0;
  animation: none;
  transition: none;
}

.window-closing-outline {
  position: fixed;
  z-index: 14;
  border: 1px solid currentColor;
  box-shadow: inset 0 0 0 3px color-mix(in srgb, currentColor 13%, transparent);
  pointer-events: none;
}

.interaction-ripple {
  position: fixed;
  z-index: 8190;
  overflow: hidden;
  pointer-events: none;
}

.interaction-ripple > span {
  position: absolute;
  border-radius: 50%;
  background: #000;
}

@media (prefers-reduced-motion: no-preference) {
  :where(button, a[href], summary, [role='button'], [role='tab'], [role='switch'], .t-link, .t-switch, .t-checkbox, .t-radio, .t-radio-button):not(:disabled, [aria-disabled='true'], .t-is-disabled, .t-is-loading, [data-press-feedback='ripple']):not(:where(.t-input *, .t-textarea *, .t-input-number *, .t-select-input *, .t-select-option *, .t-dropdown__item *, .workspace-user, [role='combobox'], [aria-haspopup='listbox'], [aria-haspopup='menu'])):active {
    scale: 0.98;
  }

  .language-heading {
    display: inline-block;
    animation: language-heading-in 240ms cubic-bezier(.22,.67,.29,1) both;
  }

  @keyframes language-heading-in {
    from { opacity: .45; translate: 0 3px; }
    to { opacity: 1; translate: 0 0; }
  }
}

:root,
:root[theme-mode='light'] {
  color-scheme: light;
  --app-bg: #f1f3f1;
  --app-surface: #fff;
  --app-surface-muted: #edf3ee;
  --app-field: #f6f8f6;
  --app-text: #141714;
  --app-text-muted: #505951;
  --app-border: #d6dcd6;
  --app-border-strong: #abb9ad;
  --app-action: #115d30;
  --app-action-hover: #207b43;
  --app-action-pressed: #104827;
  --app-on-action: #fff;
  --app-hero: #10361f;
  --app-nav-text: #d4e6d6;
  --app-danger: #8d342c;
  --app-danger-border: #debeb9;
  --app-danger-field: #faeeeb;
  --app-warning: #705624;
  --app-warning-field: #f8f3e6;
  --app-success: #125a33;
  --app-shadow: rgb(11 20 13 / 10%);
}

:root[theme-mode='dark'] {
  color-scheme: dark;
  --app-bg: #0e100e;
  --app-surface: #171a17;
  --app-surface-muted: #28352a;
  --app-field: #202520;
  --app-text: #f4f7f4;
  --app-text-muted: #aeb9ae;
  --app-border: #343e34;
  --app-border-strong: #536355;
  --app-action: #89eaa1;
  --app-action-hover: #a7f5b8;
  --app-action-pressed: #6cc783;
  --app-on-action: #171a17;
  --app-hero: #102b1a;
  --app-nav-text: #c5ddc9;
  --app-danger: #ffaea4;
  --app-danger-border: #69433e;
  --app-danger-field: #362523;
  --app-warning: #f0cc8b;
  --app-warning-field: #373020;
  --app-success: #a2eeb3;
  --app-shadow: rgb(0 0 0 / 28%);
}

:root[theme-mode] {
  --td-brand-color: var(--app-action);
  --td-brand-color-hover: var(--app-action-hover);
  --td-brand-color-active: var(--app-action-pressed);
  --td-brand-color-disabled: var(--app-border-strong);
  --td-brand-color-light: var(--app-surface-muted);
  --td-brand-color-focus: var(--app-surface-muted);
  --td-text-color-primary: var(--app-text);
  --td-text-color-secondary: var(--app-text-muted);
  --td-bg-color-page: var(--app-bg);
  --td-bg-color-container: var(--app-surface);
  --td-bg-color-container-hover: var(--app-field);
  --td-bg-color-secondarycontainer: var(--app-field);
  --td-component-border: var(--app-border);
  --td-component-stroke: var(--app-border);
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html,
body,
#app {
  min-height: 100%;
}

body {
  color: var(--app-text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  background-color: var(--app-bg);
  -webkit-text-size-adjust: 100%;
  text-size-adjust: 100%;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}

button,
input,
textarea,
select {
  font: inherit;
  -webkit-user-select: text;
  user-select: text;
}

.t-card {
  overflow: hidden;
  background: var(--app-surface);
  border: 1px solid var(--app-border) !important;
  border-radius: 14px;
  box-shadow: none;
}

.t-card__header {
  flex-wrap: wrap;
  gap: 10px 16px;
  min-height: auto;
  padding: 22px 24px 18px;
  border-bottom: 1px solid var(--app-border);
}

.t-card__title {
  color: var(--app-text);
  font-size: 20px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.t-card__subtitle {
  margin-top: 6px;
  color: var(--app-text-muted);
  font-size: 13px;
  line-height: 1.6;
}

.t-card__body {
  padding: 22px 24px 24px;
}

.t-button {
  min-height: 36px;
  border-radius: 7px;
  box-shadow: none !important;
  transition: color 0.18s ease, background 0.18s ease, border-color 0.18s ease, transform 0.18s ease;
}

.t-button--theme-primary.t-button--variant-base {
  color: var(--app-on-action);
  background: var(--app-action);
  border-color: var(--app-action);
}

.t-button--theme-primary.t-button--variant-base:hover {
  background: var(--app-action-hover);
  border-color: var(--app-action-hover);
}

.t-button--theme-primary.t-button--variant-base:active {
  background: var(--app-action-pressed);
  border-color: var(--app-action-pressed);
  transform: translateY(1px);
}

.t-button--variant-outline {
  color: var(--app-text);
  background: var(--app-surface);
  border-color: var(--app-border-strong);
}

.t-button--variant-outline:hover {
  color: var(--app-text);
  background: var(--app-surface-muted);
  border-color: var(--app-border-strong);
}

.t-button--theme-danger.t-button--variant-outline {
  color: var(--app-danger);
  background: var(--app-surface);
  border-color: var(--app-danger-border);
}

.t-button--theme-danger.t-button--variant-outline:hover {
  color: var(--app-danger);
  background: var(--app-danger-field);
  border-color: var(--app-danger-border);
}

.t-link {
  font-weight: 500;
}

.t-link--theme-primary {
  color: var(--app-action);
}

.t-link--theme-primary:hover {
  color: var(--app-text);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.t-input,
.t-textarea,
.t-input-number,
.t-select-input {
  border-color: var(--app-border);
  border-radius: 7px;
  box-shadow: none;
}

.t-select-input:hover {
  border-color: var(--app-border-strong);
}

:root .t-input:focus-within,
:root .t-textarea__inner:focus {
  border-color: var(--app-action);
  box-shadow: inset 0 0 0 1px var(--app-action);
}

:root .t-input.t-is-error:focus-within,
:root .t-textarea__inner.t-is-error:focus {
  border-color: var(--td-error-color);
  box-shadow: inset 0 0 0 1px var(--td-error-color);
}

.t-input,
.t-textarea__inner {
  transition: none;
}

.t-table {
  color: var(--app-text);
  border-radius: 8px;
}

.t-table th {
  color: var(--app-text-muted);
  font-size: 13px;
  font-weight: 600;
  background: var(--app-field);
}

.t-table td,
.t-table th {
  border-color: var(--app-border);
}

.t-table tbody tr:hover > td {
  background: var(--app-surface-muted) !important;
}

.t-tag {
  border-radius: 5px;
}

.t-tag--default {
  color: var(--app-text-muted);
  background: var(--app-field);
}

.t-tag--primary {
  color: var(--app-text);
  background: var(--app-surface-muted);
}

.t-tag--success {
  color: var(--app-success);
  background: var(--app-surface-muted);
}

.t-tag--danger {
  color: var(--app-danger);
  background: var(--app-danger-field);
}

.t-tag--warning {
  color: var(--app-warning);
  background: var(--app-warning-field);
}

.t-pagination__number.t-is-current {
  color: var(--app-on-action);
  background: var(--app-action);
  border-color: var(--app-action);
}

.t-dialog {
  overflow: hidden;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 12px;
  max-width: calc(100vw - 30px);
  box-shadow: 0 18px 60px var(--app-shadow);
}

.t-dialog__ctx .t-dialog__mask {
  background: rgb(8 18 12 / 48%);
}

@media (prefers-reduced-motion: no-preference) {
  .t-dialog-zoom__vue-enter-active .t-dialog {
    animation-name: app-dialog-open;
    animation-timing-function: cubic-bezier(.22,.64,.29,1);
  }

  .t-dialog-zoom__vue-leave-active .t-dialog {
    animation-name: app-dialog-close;
    animation-duration: 185ms;
    animation-timing-function: cubic-bezier(.43,0,.66,.36);
  }

  @keyframes app-dialog-open {
    from { opacity: 0; transform: translateY(8px) scale(.966); }
    to { opacity: 1; transform: none; }
  }

  @keyframes app-dialog-close {
    from { opacity: 1; transform: none; }
    to { opacity: 0; transform: translateY(5px) scale(.98); }
  }
}

@media (prefers-reduced-motion: reduce) {
  :is(.t-dialog-zoom__vue-enter-active, .t-dialog-zoom__vue-leave-active) :is(.t-dialog, .t-dialog__mask) {
    animation: none;
  }
}

.t-dialog__header {
  padding: 22px 24px 18px;
  color: var(--app-text);
  font-size: 20px;
  font-weight: 600;
  border-bottom: 1px solid var(--app-border);
}

.t-dialog__body {
  padding: 24px;
  color: var(--app-text);
}

.t-dialog__footer {
  padding: 16px 24px 20px;
  border-top: 1px solid var(--app-border);
}

.t-dialog__close {
  color: var(--app-text-muted);
  border-radius: 6px;
}

.t-dialog__close:hover {
  color: var(--app-text);
  background: var(--app-surface-muted);
}

.t-message {
  min-height: 44px;
  padding: 10px 14px;
  color: var(--app-text);
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 8px;
  box-shadow: 0 10px 32px var(--app-shadow);
}

.t-message.t-is-success > .t-icon,
.t-message.t-is-success > [data-t-icon] > .t-icon {
  color: var(--app-success);
}

.t-message.t-is-warning > .t-icon,
.t-message.t-is-warning > [data-t-icon] > .t-icon {
  color: var(--app-warning);
}

.t-message.t-is-error > .t-icon,
.t-message.t-is-error > [data-t-icon] > .t-icon {
  color: var(--app-danger);
}

.t-popup__content {
  color: var(--app-text);
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 8px;
  box-shadow: 0 12px 36px var(--app-shadow);
}

@media (prefers-reduced-motion: no-preference) {
  .t-popup--animation-enter-active > .t-popup__content {
    animation: app-popup-open 220ms cubic-bezier(.22,.64,.29,1) both;
  }

  @keyframes app-popup-open {
    from { translate: 0 4px; scale: .974; }
    to { translate: 0 0; scale: 1; }
  }
}

@media (prefers-reduced-motion: reduce) {
  :is(.t-popup--animation-enter-active, .t-popup--animation-leave-active) {
    transition: none;
  }
}

.t-popconfirm .t-popup__content {
  padding: 16px;
}

.t-popconfirm__body {
  color: var(--app-text);
}

.t-popconfirm__buttons {
  margin-top: 16px;
}

.t-dropdown__menu {
  padding: 6px;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 8px;
  box-shadow: 0 12px 36px var(--app-shadow);
}

.t-dropdown__item {
  border-radius: 6px;
}

.t-alert {
  color: var(--app-text);
  background: var(--app-field);
  border-color: var(--app-border);
  border-radius: 8px;
}

@supports ((-webkit-backdrop-filter: blur(0)) or (backdrop-filter: blur(0))) {
  .t-popup,
  .t-dialog {
    -webkit-backdrop-filter: blur(0);
    backdrop-filter: blur(0);
  }
}

@media (max-width: 720px) {
  .t-card__header {
    padding: 20px 18px 16px;
  }

  .t-card__body {
    padding: 18px;
  }

  .t-dialog {
    width: calc(100vw - 32px) !important;
    max-width: calc(100vw - 32px);
  }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    scroll-behavior: auto !important;
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}

:root .t-card__actions .t-space,
:root .t-table__pagination,
:root .t-pagination {
  flex-wrap: wrap;
}
.t-input,
.t-input-number,
.t-textarea__inner,
.t-select-input,
.t-date-picker {
  --td-bg-color-specialcomponent: var(--app-field);
}
.t-table {
  --td-bg-color-container: var(--app-surface);
  --td-bg-color-secondarycontainer: var(--app-field);
}
.t-table .t-table__content {
  scrollbar-color: var(--app-border-strong) transparent;
}
.t-dialog__body { overflow-wrap: anywhere; }

:root .t-dialog__ctx .t-dialog__position {
  min-height: 100%;
  align-items: center;
  padding-block: 14px;
}

:root .t-dialog.t-dialog__modal-default {
  display: flex;
  flex-direction: column;
  max-height: calc(100dvh - 28px);
  padding: 0;
}

.t-dialog__header,
.t-dialog__footer { flex: 0 0 auto; }

.t-dialog__body {
  min-height: 0;
  overscroll-behavior: contain;
  overflow-y: auto;
}

@media (max-width: 600px) {
  .t-dialog__header,
  .t-dialog__footer { padding: 15px 16px; }
  .t-dialog__body { padding: 16px; }
  .t-dialog .t-space { flex-wrap: wrap; }
  .t-dialog .t-form__item {
    display: flex;
    flex-direction: column;
    align-items: stretch;
  }
  .t-dialog .t-form__label {
    width: auto !important;
    min-width: 0;
    line-height: 20px;
    text-align: left;
    padding: 0 0 5px;
  }
  .t-dialog .t-form__controls {
    min-width: 0;
    margin-left: 0 !important;
  }
}
</style>
