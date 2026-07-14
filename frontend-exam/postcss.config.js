// PostCSS pipeline for the candidate app (SEB 2.4.1 / Gecko 41 on Windows 7).
// postcss-preset-env reads the "browserslist" field in package.json (firefox 41)
// and down-levels modern CSS the old engine can't parse — most importantly it
// rewrites Tailwind's space-separated `rgb(R G B / A)` colours to `rgba(...)`
// (color-functional-notation) and runs autoprefixer for old flexbox syntax.
export default {
  plugins: {
    tailwindcss: {},
    "postcss-preset-env": {
      stage: 3,
      features: {
        "color-functional-notation": true,
      },
    },
  },
};
