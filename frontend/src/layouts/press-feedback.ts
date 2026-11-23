const textInputSelector = 'input:not([type="button"], [type="submit"], [type="reset"], [type="checkbox"], [type="radio"], [type="range"], [type="file"], [type="image"], [type="hidden"])'
const fieldSelector = '.t-input, .t-textarea, .t-input-number, textarea, [contenteditable="true"]'
const dropdownSelector = [
  'select', '[role="combobox"]', '[role="option"]', '[aria-haspopup="listbox"]', '[aria-haspopup="menu"]',
  '.t-select-input', '.t-select-option', '.t-dropdown__item', '.t-date-picker__cell', '.workspace-user',
].join(',')
const controlSelector = [
  'button', 'a[href]', 'summary', 'input:not([type="hidden"])',
  '[role="button"]', '[role="tab"]', '[role="switch"]', '[role="checkbox"]', '[role="radio"]',
  '[role^="menuitem"]', '[role="slider"]',
  '.t-link', '.t-switch', '.t-radio-button', '.t-radio', '.t-checkbox',
  '.t-pagination__number', '.t-collapse-panel__header.t-is-clickable', '.t-collapse-panel__icon',
  '.t-input__suffix .t-icon', '.t-table__sorter-icon', '.t-table__filter-icon',
  fieldSelector, dropdownSelector,
].join(',')
const disabledSelector = ':disabled, [aria-disabled="true"], .t-is-disabled, .t-is-loading, .t-date-picker__cell--disabled, [inert]'
const choiceSelector = '.t-radio-button, .t-radio, .t-checkbox'
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)')
const taps = new WeakMap<HTMLElement, Animation>()
const recentLabelClicks = new WeakMap<HTMLElement, number>()
const ripples = new WeakMap<HTMLElement, HTMLElement>()

const showRipple = (control: HTMLElement, event: MouseEvent, subtle: boolean) => {
  const bounds = control.getBoundingClientRect()
  if (bounds.width === 0 || bounds.height === 0) return

  const x = event.detail ? Math.min(bounds.width, Math.max(0, event.clientX - bounds.left)) : bounds.width / 2
  const y = event.detail ? Math.min(bounds.height, Math.max(0, event.clientY - bounds.top)) : bounds.height / 2
  const radius = Math.hypot(Math.max(x, bounds.width - x), Math.max(y, bounds.height - y))
  const clip = document.createElement('span')
  const ink = document.createElement('span')
  clip.className = 'interaction-ripple'
  clip.setAttribute('aria-hidden', 'true')
  Object.assign(clip.style, {
    left: `${bounds.left}px`,
    top: `${bounds.top}px`,
    width: `${bounds.width}px`,
    height: `${bounds.height}px`,
    borderRadius: getComputedStyle(control).borderRadius,
  })
  Object.assign(ink.style, {
    width: `${radius * 2}px`,
    height: `${radius * 2}px`,
    left: `${x - radius}px`,
    top: `${y - radius}px`,
  })
  clip.append(ink)
  ripples.get(control)?.remove()
  ripples.set(control, clip)
  document.body.append(clip)
  const wave = ink.animate([
    { scale: '0.03', opacity: subtle ? 0.15 : 0.26 },
    { scale: '0.78', opacity: subtle ? 0.11 : 0.21, offset: 0.45 },
    { scale: '1', opacity: 0, offset: 1 },
  ], { duration: subtle ? 270 : 440, easing: 'cubic-bezier(.18,.64,.34,1)' })
  const remove = () => {
    clip.remove()
    if (ripples.get(control) === clip) ripples.delete(control)
  }
  void wave.finished.then(remove, remove)
}

export const replayPressFeedback = (event: MouseEvent) => {
  if (!(event.target instanceof Element) || reducedMotion.matches) return
  const target = event.target
  const dropdown = target.closest(dropdownSelector)
  if (target.closest(`${textInputSelector}:not([readonly])`)) return
  if (!dropdown && target.closest(`${fieldSelector}, ${textInputSelector}`)) return

  let control = target.closest<HTMLElement>(controlSelector)
  if (control?.matches('input, textarea')) control = control.closest<HTMLElement>(`${choiceSelector}, ${fieldSelector}`) ?? control
  if (!control || target.closest(disabledSelector)) return

  // A label click can be followed by a second click on its associated input.
  if (control.matches(choiceSelector)) {
    const previous = recentLabelClicks.get(control)
    if (target.matches('input') && previous !== undefined && event.timeStamp - previous < 32) return
    if (!target.matches('input')) recentLabelClicks.set(control, event.timeStamp)
  }

  const rippleOnly = Boolean(dropdown) || control.dataset.pressFeedback === 'ripple'
  showRipple(control, event, rippleOnly)
  if (rippleOnly) return
  taps.get(control)?.cancel()
  taps.set(control, control.animate([
    { scale: '0.975' },
    { scale: '1.014', offset: 0.48 },
    { scale: '1' },
  ], { duration: 175, easing: 'cubic-bezier(.24,.67,.34,1)' }))
}
