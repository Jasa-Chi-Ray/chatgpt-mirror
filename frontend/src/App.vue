<template>
  <router-view />
</template>

<script setup lang="ts">
</script>

<style>
:root {
  --app-bg: #f7f7f5;
  --app-surface: #ffffff;
  --app-surface-muted: #efefec;
  --app-text: #20201e;
  --app-text-muted: #6f6f6b;
  --app-border: #dededa;
  --app-border-strong: #c9c9c4;
  --app-action: #252523;
  --app-action-hover: #3a3a37;
  --app-danger: #a3413a;
  --app-success: #3f6f54;
  --td-brand-color: var(--app-action);
  --td-brand-color-hover: var(--app-action-hover);
  --td-brand-color-active: #171715;
  --td-brand-color-disabled: #bcbcb7;
  --td-brand-color-light: var(--app-surface-muted);
  --td-brand-color-focus: #d8d8d3;
  --td-text-color-primary: var(--app-text);
  --td-text-color-secondary: var(--app-text-muted);
  --td-bg-color-page: var(--app-bg);
  --td-component-border: var(--app-border);
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
  border-radius: 12px;
  box-shadow: none;
}

.t-card__header {
  min-height: auto;
  padding: 22px 24px 18px;
  border-bottom: 1px solid #e8e8e4;
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
  color: #f9f9f7;
  background: var(--app-action);
  border-color: var(--app-action);
}

.t-button--theme-primary.t-button--variant-base:hover {
  background: var(--app-action-hover);
  border-color: var(--app-action-hover);
}

.t-button--theme-primary.t-button--variant-base:active {
  background: #171715;
  border-color: #171715;
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
  border-color: #aaa9a3;
}

.t-button--theme-danger.t-button--variant-outline {
  color: var(--app-danger);
  background: var(--app-surface);
  border-color: #dfc2bf;
}

.t-button--theme-danger.t-button--variant-outline:hover {
  color: #86332e;
  background: #f8eeee;
  border-color: #cfaaa6;
}

.t-link {
  font-weight: 500;
}

.t-link--theme-primary {
  color: #353532;
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

.t-input:hover,
.t-textarea:hover,
.t-input-number:hover,
.t-select-input:hover {
  border-color: #aaa9a3;
}

.t-input--focused,
.t-textarea--focused,
.t-input-number.t-is-focused,
.t-select-input.t-is-focused {
  border-color: var(--app-action);
  box-shadow: 0 0 0 1px var(--app-action);
}

.t-table {
  color: var(--app-text);
  border-radius: 8px;
}

.t-table th {
  color: #555550;
  font-size: 13px;
  font-weight: 600;
  background: #f4f4f1;
}

.t-table td,
.t-table th {
  border-color: #e7e7e3;
}

.t-table tbody tr:hover > td {
  background: #f8f8f6 !important;
}

.t-tag {
  border-radius: 5px;
}

.t-tag--default {
  color: #555550;
  background: #efefec;
}

.t-tag--primary {
  color: #3f3f3b;
  background: #e9e9e5;
}

.t-tag--success {
  color: var(--app-success);
  background: #edf3ef;
}

.t-tag--danger {
  color: var(--app-danger);
  background: #f8eeee;
}

.t-tag--warning {
  color: #775f33;
  background: #f6f1e6;
}

.t-pagination__number.t-is-current {
  color: #f9f9f7;
  background: var(--app-action);
  border-color: var(--app-action);
}

.t-dialog {
  overflow: hidden;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 12px;
  box-shadow: 0 18px 60px rgba(25, 25, 23, 0.16);
}

.t-dialog__ctx .t-dialog__mask {
  background: rgba(25, 25, 23, 0.36);
}

.t-dialog__header {
  padding: 22px 24px 18px;
  color: var(--app-text);
  font-size: 20px;
  font-weight: 600;
  border-bottom: 1px solid #e8e8e4;
}

.t-dialog__body {
  padding: 24px;
  color: var(--app-text);
}

.t-dialog__footer {
  padding: 16px 24px 20px;
  border-top: 1px solid #e8e8e4;
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
  box-shadow: 0 10px 32px rgba(25, 25, 23, 0.12);
}

.t-message.t-is-success > .t-icon,
.t-message.t-is-success > [data-t-icon] > .t-icon {
  color: var(--app-success);
}

.t-message.t-is-warning > .t-icon,
.t-message.t-is-warning > [data-t-icon] > .t-icon {
  color: #775f33;
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
  box-shadow: 0 12px 36px rgba(25, 25, 23, 0.13);
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
  box-shadow: 0 12px 36px rgba(25, 25, 23, 0.13);
}

.t-dropdown__item {
  border-radius: 6px;
}

.t-alert {
  color: #4f4f4b;
  background: #f1f1ee;
  border-color: #e2e2de;
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
</style>
