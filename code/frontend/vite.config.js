import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 8471,
    strictPort: true, // a silently-incremented port breaks CORS (origin no longer matches) and cookies vanish with no error
  },
})
