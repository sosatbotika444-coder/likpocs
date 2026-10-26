import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('/node_modules/')) return;
          if (/\/(react|react-dom|scheduler|react-router|@remix-run)\//.test(id)) return 'framework';
          if (id.includes('/recharts/')) return 'charts';
          if (id.includes('/dayjs/')) return 'dates';
        },
      },
    },
  },
});
