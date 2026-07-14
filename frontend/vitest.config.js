import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Separate from vite.config.js on purpose: keeps the dev/build config (proxy,
// outDir) untouched and free of any risk from test-only settings.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
    css: false,
    globals: true,
    // 'threads' (the default) segfaults during worker-pool teardown on
    // Windows after tests already pass, exiting non-zero and failing CI
    // for no real reason. 'forks' (child_process, not worker_threads) is
    // the stable alternative — same isolation, no native crash.
    pool: 'forks',
  },
})
