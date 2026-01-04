/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                'void-dark': '#050505',
                'glass-border': 'rgba(255, 255, 255, 0.1)',
                'glass-bg': 'rgba(10, 10, 10, 0.6)',
                'cyan-glow': '#00f3ff',
                'amber-alert': '#ffaa00',
            },
            fontFamily: {
                sans: ['Inter', 'sans-serif'],
                mono: ['JetBrains Mono', 'monospace'],
            },
        },
    },
    plugins: [],
}
