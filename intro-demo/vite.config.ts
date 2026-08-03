import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Corre solo en local: es la apertura de la demostración, no un servicio desplegado.
export default defineConfig({
  plugins: [react()],
  server: { port: 5174 },
});
