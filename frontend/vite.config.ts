import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        // Overridable so several checkouts can run side by side.
        target: `http://127.0.0.1:${process.env.BACKEND_PORT ?? 8000}`,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
