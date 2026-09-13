import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// GitHub Pages URL：https://<owner>.github.io/<repo>/
// 因为 repo 名是 -ProofPath（含连字符），需要 base 指向 /-ProofPath/
// 本地 dev 仍用 '/'，不影响 npm run dev / pnpm dev
const REPO_NAME = "-ProofPath";
const GITHUB_PAGES_BASE = `/${REPO_NAME}/`;

export default defineConfig(({ command }) => ({
  plugins: [react()],
  // 生产构建用 GitHub Pages 路径；dev/build 命令 dev 时保持 '/'
  base: command === "build" ? GITHUB_PAGES_BASE : "/",
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
}));
