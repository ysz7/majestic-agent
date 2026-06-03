import type { Config } from "tailwindcss";

// Design tokens extracted from web/template/majestic-agent.html
// Every color, radius and size here is taken verbatim from the template CSS.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // ── Colors ───────────────────────────────────────────────────────────
      colors: {
        bg: {
          DEFAULT:  "#050505",
          root:     "#000000",
          canvas:   "#060606",
          surface:  "#0a0a0a",
          elevated: "#0b0b0b",
          card:     "#121212",
          sidebar:  "#131313",
          toolbar:  "#161616",
          active:   "#1a1a1a",
          topbar:   "#0d0d0d",
          selected: "#242424",
          "selected-2": "#181818",
        },
        border: {
          DEFAULT: "rgba(255,255,255,0.08)",
          strong:  "rgba(255,255,255,0.16)",
          port:    "rgba(255,255,255,0.50)",
        },
        text: {
          DEFAULT:  "#f3f3f3",
          bright:   "#ffffff",
          sub:      "#e9e9e9",
          faint:    "#d8d8d8",
          dim:      "#cfcfcf",
          muted:    "#8c8c8c",
          "muted-2": "#6a6a6a",
          "muted-3": "#565656",
        },
        // White CTA button
        cta: {
          bg:   "#ffffff",
          text: "#000000",
        },
      },

      // ── Border radius (template values) ──────────────────────────────────
      borderRadius: {
        window:  "22px",
        sidebar: "16px",
        node:    "13px",
        card:    "13px",
        toolbar: "14px",
        control: "9px",
        avatar:  "7px",
        badge:   "7px",
        dot:     "50%",
        "tw-card": "11px",
      },

      // ── Font family (template) ────────────────────────────────────────────
      fontFamily: {
        sans: ['"Helvetica Neue"', "Helvetica", "Arial", "sans-serif"],
      },

      // ── Font sizes (template scale) ───────────────────────────────────────
      fontSize: {
        "2xs": ["7px",  { lineHeight: "1.2", letterSpacing: "1.4px" }],
        xs:    ["8.5px",{ lineHeight: "1.3" }],
        sm:    ["9px",  { lineHeight: "1.4" }],
        base:  ["10px", { lineHeight: "1.5" }],
        md:    ["11px", { lineHeight: "1.5" }],
        brand: ["13px", { lineHeight: "1.2", letterSpacing: "0.3px" }],
        stat:  ["16px", { lineHeight: "1.1", letterSpacing: "0.2px" }],
      },

      // ── Spacing extras ────────────────────────────────────────────────────
      spacing: {
        "sidebar-w": "130px",
        "rpanel-w":  "162px",
      },

      // ── Background gradients as utilities ────────────────────────────────
      backgroundImage: {
        "sidebar-gradient": "linear-gradient(180deg, #131313 0%, #0a0a0a 30%, #0a0a0a 100%)",
        "node-gradient":    "linear-gradient(180deg, #131313, #0b0b0b)",
        "card-gradient":    "linear-gradient(180deg, #121212, #0a0a0a)",
        "toolbar-gradient": "linear-gradient(180deg, #161616, #0c0c0c)",
        "zap-gradient":     "linear-gradient(180deg, #1a1a1a, #0e0e0e)",
        "active-gradient":  "linear-gradient(180deg, #1d1d1d, #141414)",
        "selected-gradient":"linear-gradient(180deg, #242424, #181818)",
      },
    },
  },
  plugins: [],
} satisfies Config;
