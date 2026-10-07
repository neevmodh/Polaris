import type { Metadata, Viewport } from "next";
import { Archivo, JetBrains_Mono, Public_Sans } from "next/font/google";
import "./globals.css";
import { StoreProvider } from "@/lib/store";
import Shell from "@/components/Shell";

const display = Archivo({ subsets: ["latin"], variable: "--f-display", weight: ["600", "700", "800", "900"], display: "swap" });
const body = Public_Sans({ subsets: ["latin"], variable: "--f-body", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--f-mono", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Polaris · Measure it, see it, cut it", template: "%s · Polaris" },
  description: "Polaris: carbon accounting, satellite forest and lake screening, abatement planning and fuel runway for remote stations. Team CarbonIQ, Greenovators 2026.",
};
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable} ${mono.variable}`} suppressHydrationWarning>
      <body>
        <script dangerouslySetInnerHTML={{ __html: `try{var q=new URLSearchParams(location.search).get("theme");var t=(q==="light"||q==="dark")?q:localStorage.getItem("scope.theme");if(t)document.documentElement.dataset.theme=t}catch(e){}` }} />
        <StoreProvider><Shell>{children}</Shell></StoreProvider>
      </body>
    </html>
  );
}
