import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The board calls the FastAPI backend directly at http://localhost:8000 (see src/api.ts).
// Port 5173 is pinned (strictPort) because the backend's CORS allow-list expects it.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1', // on macOS "localhost" can resolve to IPv6 only
    port: 5173,
    strictPort: true,
  },
})
