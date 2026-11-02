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
    // Proxy every backend call through this same origin/port, server-side.
    // The browser only ever talks to wherever the frontend itself is served
    // from (port 80 here); Vite forwards to each backend port on this same
    // machine. Without this, the browser would try to reach
    // "http://localhost:8087" etc. directly — which is just the browser's
    // own machine when accessed remotely (e.g. through a load balancer),
    // not the server, so those calls fail outright.
    proxy: {
      "/api/em-synth": {
        target: "http://localhost:8082",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/em-synth/, "")
      },
      "/api/cpt-synth": {
        target: "http://localhost:8086",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/cpt-synth/, "")
      },
      "/api/evidence": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/evidence/, "")
      },
      "/api/em": {
        target: "http://localhost:8081",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/em/, "")
      },
      "/api/cpt-retrieval": {
        target: "http://localhost:8083",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/cpt-retrieval/, "")
      },
      "/api/cpt": {
        target: "http://localhost:8084",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/cpt/, "")
      },
      "/api/pcs": {
        target: "http://localhost:8085",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/pcs/, "")
      },
      "/api/prompts-mgmt": {
        target: "http://localhost:8087",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/prompts-mgmt/, "")
      },
      "/api/batch": {
        target: "http://localhost:8088",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/batch/, "")
      }
    },
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
