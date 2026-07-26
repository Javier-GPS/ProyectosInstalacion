/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        brand: ['Exposure', 'Georgia', 'serif'],
        ui: ['Exposure UI', '"Helvetica Neue"', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['"SF Mono"', 'Consolas', 'monospace'],
      },
      colors: {
        salvi: {
          black:  '#1E1E1E',
          grey:   '#6A6A6A',
          cream:  '#FCF9F5',
          surface: '#F7F4EF',
          white:  '#FFFFFF',
          line:   '#E8E2D8',
          muted:  '#A09A91',
          gold:   '#1E1E1E',
          success: '#1F7A4D',
          warning: '#B7791F',
          danger:  '#B42318',
        },
        gis: {
          bg:      '#FCF9F5',
          surface: '#F7F4EF',
          card:    '#FFFFFF',
          bg4:     '#F0EDE8',
          line:    '#E8E2D8',
          border:  '#D4CEC6',
          border3: '#B8B0A6',
          text:    '#1E1E1E',
          text2:   '#6A6A6A',
          text3:   '#A09A91',
          gold:    '#1E1E1E',
          goldBg:  '#EDEAE4',
          green:   '#1F7A4D',
          greenBg: '#E8F4EE',
          red:     '#B42318',
          redBg:   '#FDECEA',
        },
      },
      borderRadius: {
        sm: '6px',
        md: '10px',
        lg: '12px',
        xl: '18px',
      },
    },
  },
  plugins: [],
};
