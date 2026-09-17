/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: {
          primary: '#FFFFFF',
          secondary: '#F8F9FA',
          subtle: '#F9FAFB',
        },
        border: {
          subtle: '#E5E7EB',
          muted: '#E2E8F0',
        },
        brand: {
          50: '#EFF6FF',
          100: '#DBEAFE',
          500: '#3B82F6',
          600: '#2563EB',
          700: '#1D4ED8',
        },
        sync: {
          bg: '#FEF3C7',
          border: '#FDE68A',
          text: '#D97706',
        },
        clean: {
          bg: '#DEF7EC',
          border: '#BCF0DA',
          text: '#03543F',
        },
        guard: {
          bg: '#EEF2FF',
          border: '#E0E7FF',
          text: '#4338CA',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'PingFang SC', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Menlo', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}
