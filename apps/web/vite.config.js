import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  base: '/telegram/',
  plugins: [vue()],
  server: {
    proxy: {
      '/telegram/api': {
        target: 'http://127.0.0.1:9292',
        rewrite: (path) => path.replace(/^\/telegram/, '')
      }
    }
  }
});
