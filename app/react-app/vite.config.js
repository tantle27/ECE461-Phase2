import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Proxy API requests to Flask backend during development
      '/health': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
      '/authenticate': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
      '/reset': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
      '/tracks': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
      '/artifact': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
      '/artifacts': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
      '/upload': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
    }
  }
})
