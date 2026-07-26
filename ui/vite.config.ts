import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// En desarrollo, /api se redirige al backend local para evitar problemas de CORS.
// En producción, la URL del backend llega por VITE_API_URL (ver .env.example).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
});
