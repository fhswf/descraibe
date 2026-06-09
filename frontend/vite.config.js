import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import fs from 'fs'
import path from 'path'
import process from 'node:process'

const packageJson = JSON.parse(fs.readFileSync(path.resolve(import.meta.dirname, './package.json'), 'utf-8'));

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = {
    ...loadEnv(mode, import.meta.dirname, 'VITE_'),
    ...process.env
  }

  return {
    define: {
      'import.meta.env.VITE_APP_VERSION': JSON.stringify(packageJson.version),
      'import.meta.env.VITE_APP_BUILD_CHANNEL': JSON.stringify(env.VITE_APP_BUILD_CHANNEL || ''),
      'import.meta.env.VITE_APP_COMMIT_SHA': JSON.stringify(env.VITE_APP_COMMIT_SHA || ''),
      'import.meta.env.VITE_APP_REPOSITORY_URL': JSON.stringify(env.VITE_APP_REPOSITORY_URL || ''),
      'import.meta.env.VITE_APP_VERSION_LABEL': JSON.stringify(env.VITE_APP_VERSION_LABEL || '')
    },
    plugins: [
      react(),
      tailwindcss()
    ],
    server: {
      port: 5001,
      proxy: {
        '/api': {
          target: 'http://localhost:5000',
          changeOrigin: true,
        }
      }
    }
  }
})
