import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      typography: {
        DEFAULT: {
          css: {
            maxWidth: "none",
          },
        },
      },
      keyframes: {
        shimmer: {
          "0%":   { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(300%)" },
        },
        indeterminate: {
          "0%":   { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(400%)" },
        },
        ring: {
          "0%":   { transform: "rotate(0deg)" },
          "10%":  { transform: "rotate(14deg)" },
          "20%":  { transform: "rotate(-8deg)" },
          "30%":  { transform: "rotate(14deg)" },
          "40%":  { transform: "rotate(-4deg)" },
          "50%":  { transform: "rotate(10deg)" },
          "60%":  { transform: "rotate(0deg)" },
          "100%": { transform: "rotate(0deg)" },
        },
      },
      animation: {
        shimmer:       "shimmer 1.8s ease-in-out infinite",
        indeterminate: "indeterminate 1.6s ease-in-out infinite",
      },
      spacing: {
        sidebar: "272px",
      },
    },
  },
  plugins: [],
};

export default config;
