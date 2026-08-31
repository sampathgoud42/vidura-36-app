import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Nothing but the React plugin. The multi-world app this was carved out of
// carried ~1000 lines of dev middleware that shelled out to scripts in
// sibling folders; every one of those surfaces is now a real endpoint on the
// Tradier Bot API, so the dev server has no machine-specific work to do and
// `vite build` output is a plain static bundle.
//
// Port 5199 rather than Vite's 5173 so this can run alongside the original
// app on the same workstation without a collision.
export default defineConfig({
  plugins: [react()],
  server: { port: 5199, strictPort: false },
  preview: { port: 5199, strictPort: false },
  // dist-v2, not vite's default dist: api_v2 serves frontend/dist-v2, and
  // dist is the retired app's output directory. With the default, a plain
  // `npm run build` reported success while updating a folder nothing serves,
  // so the desk kept showing the previous bundle.
  build: { outDir: 'dist-v2', sourcemap: false },
});
