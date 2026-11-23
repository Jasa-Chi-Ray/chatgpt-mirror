import { storeToRefs } from 'pinia'
import { useAppearanceStore } from '@/store/appearance'
import { workspaceEnglish } from './workspace-english'

export const useWorkspaceCopy = () => {
  const appearance = useAppearanceStore()
  const { language } = storeToRefs(appearance)
  const t = (text: string, values: unknown[] = []) => {
    let result = text
    if (appearance.language === 'en' && Object.prototype.hasOwnProperty.call(workspaceEnglish, text)) {
      result = workspaceEnglish[text]
    }
    return values.length ? result.replace(/\{(\d+)\}/g, (placeholder, index) =>
      Number(index) < values.length ? String(values[Number(index)]) : placeholder,
    ) : result
  }

  const labels = <T extends object>(items: T[]) => items.map(item => {
    const translated = { ...item }
    for (const key of ['label', 'title', 'content'] as const) {
      const value = (item as Record<string, unknown>)[key]
      if (typeof value === 'string') Object.assign(translated, { [key]: t(value) })
    }
    return translated
  })

  return { t, labels, language }
}
