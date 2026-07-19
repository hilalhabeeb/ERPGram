/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./apps/**/templates/**/*.html",
    // Class strings live in a few Python files (form widgets, components).
    "./apps/**/*.py",
  ],
  theme: {
    extend: {
      colors: {
        // Surfaces
        page: "#F3F3F1",
        card: "#FFFFFF",
        subtle: "#FAFAF9",
        // Text
        text: {
          primary: "#1C1917",
          secondary: "#57534E",
          muted: "#A8A29E",
        },
        // Border
        border: {
          DEFAULT: "#E7E5E4",
          strong: "#D6D3D1",
        },
        // Accent — the single blue
        accent: {
          primary: "#2563EB",
          primarySoft: "#EFF4FE",
        },
      },
      borderRadius: {
        card: "14px",
        control: "10px",
        pill: "999px",
      },
      boxShadow: {
        // The only shadow in the system.
        card: "0 1px 2px rgb(0 0 0 / 0.04)",
      },
      fontFamily: {
        sans: ['"Inter"', '"IBM Plex Sans Arabic"', "system-ui", "sans-serif"],
        arabic: ['"IBM Plex Sans Arabic"', '"Inter"', "system-ui", "sans-serif"],
      },
      fontSize: {
        // Base 14px; headings 15 / 18 / 22.
        base: ["14px", { lineHeight: "20px" }],
        "heading-sm": ["15px", { lineHeight: "22px" }],
        "heading-md": ["18px", { lineHeight: "26px" }],
        "heading-lg": ["22px", { lineHeight: "30px" }],
      },
    },
  },
  plugins: [],
};
