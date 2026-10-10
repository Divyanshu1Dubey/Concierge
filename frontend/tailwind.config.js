/** @type {import('tailwindcss').Config} */
import defaultTheme from 'tailwindcss/defaultTheme';

/*
 * HeyJarvis Concierge design tokens.
 * The app's existing utility classes use `teal`, `cyan`, `gray` and `slate`;
 * those names are re-pointed at the brand scales below so every screen picks up
 * the same identity without touching component logic:
 *   teal  -> forest  (primary actions, active states)
 *   cyan  -> sage    (secondary accents)
 *   gray  -> stone   (warm neutrals: cream surfaces, borders, body text)
 *   slate -> ink     (deep forest-ink for the app shell and headings)
 * Status hues (red / amber / emerald / blue) keep Tailwind defaults for clarity.
 */
const forest = {
  50: '#F1F5F1',
  100: '#E2EBE3',
  200: '#C5D6C8',
  300: '#9DB9A3',
  400: '#6E9578',
  500: '#477457',
  600: '#2E5C3F',
  700: '#234A33',
  800: '#1B3A29',
  900: '#142C20',
  950: '#0B1A13',
};

const sage = {
  50: '#F5F7F2',
  100: '#E8EDE1',
  200: '#D3DCC8',
  300: '#B5C3A6',
  400: '#96A785',
  500: '#7A8C68',
  600: '#617150',
  700: '#4C5940',
  800: '#3D4835',
  900: '#333C2D',
  950: '#1B2117',
};

const stone = {
  50: '#FAF8F3',
  100: '#F3F0E8',
  200: '#E7E2D7',
  300: '#D4CDBF',
  400: '#A9A193',
  500: '#7D776B',
  600: '#5F5A50',
  700: '#49453D',
  800: '#302D28',
  900: '#201E1A',
  950: '#12110E',
};

const ink = {
  50: '#F6F7F4',
  100: '#ECEFE9',
  200: '#D8DED4',
  300: '#B5BFB1',
  400: '#899685',
  500: '#626F5E',
  600: '#495546',
  700: '#364035',
  800: '#222B23',
  900: '#172019',
  950: '#0E1610',
};

// Muted companions so status/role hues sit comfortably beside the greens.
const dustyBlue = {
  50: '#F2F5F8', 100: '#E3E9F0', 200: '#C8D3E0', 300: '#A3B5C9', 400: '#7891AD',
  500: '#587493', 600: '#465D78', 700: '#3A4C62', 800: '#313F51', 900: '#2A3543', 950: '#1A212B',
};
const plum = {
  50: '#F7F3F6', 100: '#EEE5EC', 200: '#DDCBD9', 300: '#C4A8BF', 400: '#A47F9E',
  500: '#866281', 600: '#6E4F69', 700: '#5A4156', 800: '#4B3748', 900: '#3F303D', 950: '#261C25',
};

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        teal: forest,
        cyan: sage,
        gray: stone,
        slate: ink,
        forest,
        sage,
        stone,
        ink,
        blue: dustyBlue,
        indigo: dustyBlue,
        purple: plum,
        violet: plum,
        cream: '#FAF8F3',
        primary: forest,
      },
      fontFamily: {
        sans: ['Inter', ...defaultTheme.fontFamily.sans],
        display: ['Fraunces', 'Georgia', 'Cambria', '"Times New Roman"', 'serif'],
      },
      maxWidth: {
        prose: '68ch',
        content: '72rem',
      },
      borderRadius: {
        card: '1.125rem',
      },
      boxShadow: {
        card: '0 1px 2px rgba(20, 44, 32, 0.04), 0 1px 1px rgba(20, 44, 32, 0.03)',
        lift: '0 12px 32px -12px rgba(20, 44, 32, 0.18), 0 2px 6px rgba(20, 44, 32, 0.05)',
      },
      transitionTimingFunction: {
        brand: 'cubic-bezier(0.22, 1, 0.36, 1)',
      },
      keyframes: {
        rise: {
          from: { opacity: '0', transform: 'translateY(12px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        rise: 'rise 0.7s cubic-bezier(0.22, 1, 0.36, 1) both',
      },
    },
  },
  plugins: [],
};
