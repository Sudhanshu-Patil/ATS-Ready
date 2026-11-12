import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxy target for /api and /outputs during development.
// Locally this is 127.0.0.1:8000; inside docker-compose it's set to
// http://api:8000 (the FastAPI service name on the compose network).
const apiTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // bind 0.0.0.0 so the Vite dev server is reachable from outside a container
    port: 5173,
    proxy: {
      // Proxy all /api/* requests to FastAPI during development
      // So you run: FastAPI on :8000, Vite on :5173
      // Browser hits :5173, API calls get forwarded to :8000
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/outputs': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
    historyApiFallback: true,
  },
  build: {
    // Output to FastAPI's static directory so it can serve the SPA
    outDir: '../app/static/dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // Stable vendor chunks cache across deploys and keep route chunks small.
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          motion: ['framer-motion'],
        },
      },
    },
  },
})
