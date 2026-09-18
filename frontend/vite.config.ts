import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
export default defineConfig({plugins:[react(),tailwindcss()],server:{proxy:{'/api':'http://127.0.0.1:8017','/admin':'http://127.0.0.1:8017','/static':'http://127.0.0.1:8017'}},test:{include:['src/**/*.test.{ts,tsx}'],environment:'jsdom',setupFiles:['./src/test-setup.ts']}})


