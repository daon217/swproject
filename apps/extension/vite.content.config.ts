import { resolve } from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// 쇼핑몰 페이지에 주입하는 인페이지 플로팅 패널(content script)을 단일 IIFE 파일로 빌드한다.
export default defineConfig({
  plugins: [react()],
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  build: {
    outDir: 'dist',
    emptyOutDir: false,
    lib: {
      entry: resolve(__dirname, 'src/content/index.tsx'),
      name: 'KkulpickContent',
      formats: ['iife'],
      fileName: () => 'content.js',
    },
  },
});
