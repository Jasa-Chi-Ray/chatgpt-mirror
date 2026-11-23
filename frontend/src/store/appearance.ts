import { defineStore } from 'pinia'
import { ref } from 'vue'

export type ColorTheme = 'light' | 'dark'
export type InterfaceLanguage = 'zh-CN' | 'en'

const loadPreference = (key: string) => {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

const savePreference = (key: string, value: string) => {
  try {
    localStorage.setItem(key, value)
  } catch {
    // The preference still works for this visit when storage is unavailable.
  }
}

export const useAppearanceStore = defineStore('appearance', () => {
  const theme = ref<ColorTheme>(loadPreference('appearance-theme') === 'dark' ? 'dark' : 'light')
  const language = ref<InterfaceLanguage>(loadPreference('appearance-language') === 'en' ? 'en' : 'zh-CN')

  const setTheme = (value: ColorTheme) => {
    theme.value = value
    savePreference('appearance-theme', value)
  }

  const setLanguage = (value: InterfaceLanguage) => {
    language.value = value
    savePreference('appearance-language', value)
  }

  return { theme, language, setTheme, setLanguage }
})
