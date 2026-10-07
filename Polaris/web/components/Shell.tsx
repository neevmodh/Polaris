"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { useGet, useIsDark } from "@/lib/hooks";
import { SECTIONS, SHEETS, sectionOf } from "@/lib/sheets";
import { decodeInputs, useStore } from "@/lib/store";
import type { Meta } from "@/lib/types";

/** Polaris north star: two crossed diamonds with a flare at the centre. */
export function StarMark({ size = 30 }: { size?: number }) {
  return (
    <svg className="star" width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <path d="M16 1 L18.8 13.2 L31 16 L18.8 18.8 L16 31 L13.2 18.8 L1 16 L13.2 13.2 Z" fill="currentColor" />
      <circle cx="16" cy="16" r="3.2" fill="var(--s1)" />
    </svg>
  );
}

/** Polar graticule: circles of latitude and meridians. Pure decoration, hidden from assistive tech. */
function Graticule() {
  const rings = [60, 120, 180, 240, 300], spokes = Array.from({ length: 24 }, (_, i) => i * 15);
  return (
    <svg className="mast-art" viewBox="-300 -300 600 600" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.2">
      {rings.map((r) => <circle key={r} r={r} />)}
      {spokes.map((a) => <line key={a} x1="0" y1="0" x2={300 * Math.cos((a * Math.PI) / 180)} y2={300 * Math.sin((a * Math.PI) / 180)} />)}
    </svg>
  );
}

export default function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const { error } = useGet<Meta>("/api/meta");
  const dark = useIsDark();
  const { setInputs } = useStore();
  const section = sectionOf(path);

  // a shared link (?s=…) loads its inputs once
  useEffect(() => {
    const s = new URLSearchParams(window.location.search).get("s");
    const decoded = s ? decodeInputs(s) : null;
    if (decoded) setInputs(decoded);
  }, [setInputs]);

  const toggle = () => {
    const next = dark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("scope.theme", next); } catch {}
  };
  const subs = SHEETS.filter((s) => s.section === section);
  return (
    <>
      <a className="skip" href="#content">Skip to content</a>
      {error && (
        <div className="banner" role="alert"><div>
          <b>The calculation engine is not responding.</b>
          <span>Start it with <span className="mono">make web</span> from the Polaris folder, then retry.</span>
          <button className="btn" onClick={() => window.location.reload()}>Retry</button>
        </div></div>
      )}
      <header className="mast">
        <Graticule />
        <div className="mast-in">
          <Link href="/" className="brand" aria-label="Polaris home">
            <StarMark />
            <span><span className="brand-name">POLARIS</span><span className="brand-sub" style={{ display: "block" }}>Net-zero field series</span></span>
          </Link>
          <nav className="nav" aria-label="Sections">
            {SECTIONS.map((s) => (
              <Link key={s.id} href={s.href} aria-current={section === s.id ? "page" : undefined}><span className="k">{s.verb}</span>{s.label}</Link>
            ))}
          </nav>
          <div className="tools">
            <button className="icon-btn" onClick={toggle} aria-label={`Switch to ${dark ? "light" : "dark"} theme`}>{dark ? "Light" : "Dark"}</button>
          </div>
        </div>
        {subs.length > 1 && (
          <div className="subnav"><nav className="subnav-in" aria-label="Sheets in this section">
            {subs.map((s) => <Link key={s.href} href={s.href} aria-current={path === s.href ? "page" : undefined}><span className="k">{s.num}</span>{s.label}</Link>)}
          </nav></div>
        )}
      </header>
      <main className="main" id="content">{children}</main>
      <footer className="foot">
        <span>POLARIS · Team CarbonIQ · Greenovators Hackathon 2026</span>
        <span>Carbon: CEA v22 · EPA · USEEIO 1.3</span>
        <span>Earth: Copernicus Sentinel-2 · Hansen GFC 2024</span>
      </footer>
    </>
  );
}
