import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.VITE_PORT) || 80,
    strictPort: true,
    // Bind all interfaces, not just localhost — required whenever traffic
    // reaches this process from outside the host itself (e.g. a load
    // balancer connecting over the VM's network interface rather than
    // loopback). Vite defaults to localhost-only, which works for plain
    // local dev but silently makes the server unreachable from an LB/proxy.
    host: process.env.VITE_HOST || "0.0.0.0",
    // Vite's DNS-rebinding guard rejects requests whose Host header isn't
    // in this list. Behind a load balancer, the forwarded Host header is
    // the public domain, not "localhost" — allow everything here since
    // actual access control (IAP, security groups, etc.) happens in front
    // of this process, not in Vite itself.
    allowedHosts: true,
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
