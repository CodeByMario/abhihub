/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
        "./templates/**/*.html",
        "./static/**/*.js",
    ],
    theme: {
        extend: {
            colors: {
                primary: '#2563eb',
                secondary: '#1d4ed8',
            },
            fontFamily: {
                'kanit': ['Kanit', 'sans-serif'],
            },
        },
    },
    plugins: [],
}
