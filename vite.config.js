import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'prompt',
      includeAssets: ['icon.svg'],
      manifest: {
        name: '墨记 · Markdown 编辑器',
        short_name: '墨记',
        description: '让思绪，自然成文',
        theme_color: '#58745e',
        background_color: '#fcfcfa',
        display: 'standalone',
        lang: 'zh-CN',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
        ],
      },
      workbox: { maximumFileSizeToCacheInBytes: 3 * 1024 * 1024 },
    }),
  ],
});
