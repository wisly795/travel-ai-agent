import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 建置結果放 dist/，由 FastAPI 提供：首頁 /，其他檔案在 /static/ 底下
export default defineConfig({
  plugins: [react()],
  base: "/static/",
  build: { outDir: "dist", emptyOutDir: true },
  server: { proxy: { "/api": "http://localhost:8100", "/partner": "http://localhost:8100" } },
  test: { environment: "jsdom" },
});
