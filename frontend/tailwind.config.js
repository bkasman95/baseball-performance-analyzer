/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Field-inspired palette
        diamond: {
          50:  "#f4f8f4",
          100: "#e1ece1",
          200: "#bdd6bd",
          400: "#5fa05f",
          600: "#2f6a2f",
          800: "#1c421c",
        },
      },
    },
  },
  plugins: [],
};
