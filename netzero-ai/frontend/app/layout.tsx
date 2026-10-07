import './globals.css';
export const metadata={title:'NetZeroAI · Microgrid control room',description:'Forecast-driven dispatch for a solar + wind + battery microgrid, with an AI analyst.'};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><head><link rel="preconnect" href="https://fonts.googleapis.com"/><link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet"/></head><body>{children}</body></html>}
