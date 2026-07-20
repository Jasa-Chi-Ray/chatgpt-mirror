import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  base: '/admin/',
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  server: {
    port: 40003,
    proxy: {
      '/0x': {
        target: 'http://localhost:40002',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: '../gateway/static',
    emptyOutDir: true
  }
})
