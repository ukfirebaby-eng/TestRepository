import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/app-v2/",
  plugins: [react()],
  build: {
    outDir: "../static/app-v2",
    emptyOutDir: true,
    chunkSizeWarningLimit: 950,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("/react/") || id.includes("/react-dom/") || id.includes("@vitejs/plugin-react")) {
            return "react-vendor";
          }
          if (id.includes("/three/") || id.includes("@react-three")) {
            return "three-vendor";
          }
          if (id.includes("/sigma/") || id.includes("/graphology/")) {
            return "graph-vendor";
          }
          return undefined;
        },
      },
    },
  },
  server: {
    proxy: {
      "/api/v1": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    exclude: ["node_modules/**", "dist/**", "e2e/**"],
  },
});
