/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        base: "#0B0F0D",
        panel: "#121814",
        panel2: "#182019",
        line: "#24302A",
        ink: "#E8F0EA",
        muted: "#6F8079",
        safe: "#3ED598",
        alert: "#FF4757",
        scan: "#FFB020",
      },
      fontFamily: {
        display: ["'Space Grotesk'", "sans-serif"],
        body: ["'Inter'", "sans-serif"],
        mono: ["'JetBrains Mono'", "monospace"],
      },
      keyframes: {
        blink: { "0%, 100%": { opacity: 1 }, "50%": { opacity: 0.25 } },
        flash: {
          "0%": { boxShadow: "0 0 0 0 rgba(255,71,87,0.5)" },
          "70%": { boxShadow: "0 0 0 14px rgba(255,71,87,0)" },
          "100%": { boxShadow: "0 0 0 0 rgba(255,71,87,0)" },
        },
      },
      animation: {
        blink: "blink 1.8s ease-in-out infinite",
        flash: "flash 1.4s ease-out",
      },
    },
  },
  plugins: [],
};