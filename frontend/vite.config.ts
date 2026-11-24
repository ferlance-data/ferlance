/// <reference types="vitest/config" />
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';

const API_TARGET = process.env.FERLANCE_API ?? 'http://127.0.0.1:8000';

/**
 * In development, serve the workspace entry for client-side routes such as
 * /app/products, mirroring the backend's /app/{path} fallback in production.
 */
function workspaceFallback(): Plugin {
  return {
    name: 'ferlance-workspace-fallback',
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const path = req.url?.split('?')[0] ?? '';
        if (path === '/app' || (path.startsWith('/app/') && !path.slice(5).includes('.'))) {
          req.url = '/app/index.html';
        }
        if (path === '/admin' || (path.startsWith('/admin/') && !path.slice(7).includes('.'))) {
          req.url = '/admin/index.html';
        }
        next();
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), workspaceFallback()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rolldownOptions: {
      input: {
        landing: fileURLToPath(new URL('./index.html', import.meta.url)),
        app: fileURLToPath(new URL('./app/index.html', import.meta.url)),
        admin: fileURLToPath(new URL('./admin/index.html', import.meta.url)),
      },
      output: {
        // Third-party code changes far less often than ours. In its own chunk it keeps its
        // hash across app releases, so returning users re-download only the app code.
        codeSplitting: { groups: [{ name: 'vendor', test: /[\\/]node_modules[\\/]/ }] },
      },
    },
  },
  server: {
    // Same-origin proxy so the HttpOnly refresh cookie (path=/api/auth) keeps working in dev.
    proxy: { '/api': { target: API_TARGET, changeOrigin: false } },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    restoreMocks: true,
  },
});
