/** @type {import('tailwindcss').Config} */
// Palette from CarePortal's official brand guide (careportal.org):
//   orange #ff6129 · navy #172936 · gold #faca00 · light-blue #0773a7 · font Inter.
// `brand` = CarePortal light blue (links, selected states, charts, focus rings).
// `accent` = CarePortal orange (primary actions, active nav). `navy` = headings/
// strong text. Emerald/rose stay reserved for opportunity/risk semantics.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
      colors: {
        brand: {
          50: "#eef7fb",
          100: "#d3ebf4",
          200: "#aed9ec",
          500: "#0773a7",
          600: "#065f89",
          700: "#05496b",
        },
        accent: {
          50: "#fff2ec",
          100: "#ffe0d4",
          500: "#ff6129",
          600: "#ed4b13",
          700: "#c23c0f",
        },
        navy: {
          DEFAULT: "#172936",
          600: "#26414f",
          500: "#3a5566",
          400: "#5b7385",
        },
        gold: {
          100: "#fff5cc",
          400: "#faca00",
        },
        canvas: "#f8f6f3", // warm off-white background
      },
    },
  },
  plugins: [],
};
