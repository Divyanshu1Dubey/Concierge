import { defineConfig } from 'vite'

export default defineConfig({
  root: '.',
  build: {
    lib: {
      entry: './src/index.ts',
      name: 'HeyJarvisWidget',
      fileName: 'heyjarvis-widget',
    },
    rollupOptions: {
      output: {
        assetFileNames: 'heyjarvis-widget.[ext]',
      },
    },
  },
})
