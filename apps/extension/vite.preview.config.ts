import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// 확장 설치 없이 브라우저 탭에서 화면을 확인하는 개발용 서버.
// chrome.* API가 없으면 src/shared/chromeShim.ts가 localStorage 기반 대체 구현을 쓴다.
export default defineConfig({
  plugins: [react()],
  build: { outDir: 'preview-dist', rollupOptions: { input: 'preview.html' } },
  server: { host: '127.0.0.1', port: 5174, strictPort: true }, // http://localhost:5174/preview.html
});
