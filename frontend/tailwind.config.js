/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        /* ProofPath 品牌色 — 沉稳蓝绿系 */
        brand: {
          50: "#f0f9f6",
          100: "#d4efe6",
          200: "#a9dfcd",
          300: "#72c7ad",
          400: "#43a88a",
          500: "#2d8b70",
          600: "#236f5a",
          700: "#1e5949",
          800: "#1b483c",
          900: "#183b33",
          950: "#0b221d",
        },
        /* 状态色 — 用于条件判断 */
        status: {
          met: "#16a34a",
          unmet: "#dc2626",
          "needs-input": "#d97706",
          unknown: "#6b7280",
        },
        /* 引用核验色 */
        citation: {
          verified: "#16a34a",
          partial: "#2563eb",
          "not-found": "#dc2626",
          "too-short": "#d97706",
          "bad-page": "#9333ea",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Noto Sans SC",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "Fira Code", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
