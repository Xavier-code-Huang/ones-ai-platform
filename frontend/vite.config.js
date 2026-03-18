import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 9611,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://localhost:9610',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:9610',
        ws: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          // Element Plus 单独打包（最大的依赖）
          'element-plus': ['element-plus', '@element-plus/icons-vue'],
          // Vue 核心单独打包（浏览器缓存友好）
          'vue-vendor': ['vue', 'vue-router', 'pinia'],
        },
      },
    },
    // 启用 CSS 代码分割
    cssCodeSplit: true,
    // chunk 大小警告阈值
    chunkSizeWarningLimit: 800,
  },
})
