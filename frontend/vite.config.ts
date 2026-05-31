import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/app-v2/",
  plugins: [react()],
  build: {
    outDir: "../static/app-v2",
    emptyOutDir: true,
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
