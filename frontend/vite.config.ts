import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    watch: { usePolling: true },
  },
  preview: {
    host: true,
    // Allow the Render-deployed web service hostname (and any other onrender.com
    // subdomain). Vite's preview server blocks unknown hosts by default as a
    // dev-rebinding-attack mitigation.
    allowedHosts: [".onrender.com", "localhost"],
  },
});
