/// <reference types="vitest/config" />
import { fileURLToPath } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig, searchForWorkspaceRoot } from 'vite';

const designDir = fileURLToPath(new URL('../../design', import.meta.url));
const apiUrl = process.env.MONA_API_URL ?? 'http://localhost:8765';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@design': designDir },
  },
  server: {
    fs: { allow: [searchForWorkspaceRoot(process.cwd()), designDir] },
    proxy: {
      '/api': apiUrl,
      '/mcp': apiUrl,
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
