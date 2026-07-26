/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        salvi: {
          black: '#1E1E1E',
          grey: '#6A6A6A',
          cream: '#FCF9F5',
          surface: '#F7F4EF',
          white: '#FFFFFF',
          line: '#E8E2D8',
          muted: '#A09A91',
        },
        state: {
          success: '#1F7A4D',
          warning: '#B7791F',
          danger: '#B42318',
          info: '#4A5568',
        },
      },
      fontFamily: {
        brand: ['Exposure', 'Georgia', 'serif'],
        ui: ['Helvetica Neue', 'Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
