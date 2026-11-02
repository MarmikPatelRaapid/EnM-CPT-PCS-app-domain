import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.VITE_PORT) || 80,
    strictPort: true,
    watch: {
      // Avoid EMFILE ("too many open files") in environments
      // with low fs watcher limits by using polling instead.
      usePolling: true,
      interval: 1000,
      // Don't watch large static assets / zips that trip the poller and
      // cause spurious full-page reloads even when nothing actually changed.
      // Source files under src/ are still watched, so real edits still reload.
      ignored: [
        "**/public/code_descriptions/**",
        "**/public.zip",
        "**/*.zip"
      ]
    }
  }
});
