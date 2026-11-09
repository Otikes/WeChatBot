import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173 },
  build: {
    outDir: 'dist',
    rollupOptions: {
      output: {
        // 三方库单独分包：各 vendor chunk 可长期缓存，业务代码变更不失效
        manualChunks(id) {
          const norm = id.replace(/\\/g, '/')
          if (!norm.includes('node_modules')) return
          if (norm.includes('/node_modules/react/') || norm.includes('/node_modules/react-dom/') || norm.includes('/node_modules/scheduler/')) return 'react'
          if (norm.includes('/node_modules/framer-motion/') || norm.includes('/node_modules/motion-dom/') || norm.includes('/node_modules/motion-utils/')) return 'motion'
        },
      },
    },
  },
})
