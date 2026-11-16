import { resolve } from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// 사이드 패널(HTML)과 백그라운드 서비스 워커(ES module)를 빌드한다.
// content script는 ES module로 로드할 수 없어서 vite.content.config.ts에서 IIFE로 따로 빌드한다.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        sidepanel: resolve(__dirname, 'sidepanel.html'),
        background: resolve(__dirname, 'src/background/index.ts'),
      },
      output: {
        entryFileNames: (chunk) => (chunk.name === 'background' ? 'background.js' : 'assets/[name]-[hash].js'),
      },
    },
  },
});
