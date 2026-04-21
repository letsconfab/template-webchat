import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3030,
    proxy: {
      '/api': {
        target: 'http://webchat-backend:8005',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://webchat-backend:8005',
        ws: true,
      },
    },
  },
})
