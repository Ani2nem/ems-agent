import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Vite proxies /api to the local FastAPI backend during dev.
// In prod the SPA and API share the CloudFront/API-Gateway origin, so /api is same-origin.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: false,
  },
});
