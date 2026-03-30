import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
        changeOrigin: true,
        timeout: 600000,  // 10 min — prevent proxy from killing long-running WS
      },
      '/fonts': 'http://127.0.0.1:8000',
    },
  },
})
