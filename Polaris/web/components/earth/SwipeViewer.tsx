"use client";
/* Satellite frames are small pixelated data-URL rasters; next/image would blur or re-encode them. */
/* eslint-disable @next/next/no-img-element */
import { useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import type { Legend, Region } from "@/lib/sat";

type Props = {
  before: string; after: string; size: [number, number]; beforeLabel: string; afterLabel: string; afterAlt: string;
  mode: "swipe" | "side"; regions: Region[]; selected: number | null; onSelect: (id: number) => void; showRegions: boolean;
};

/** Before/after viewer. Swipe: one frame, a draggable divider (pointer or arrow keys). Side by side: two frames. */
export default function SwipeViewer({ before, after, size, beforeLabel, afterLabel, afterAlt, mode, regions, selected, onSelect, showRegions }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState(50);
  const [drag, setDrag] = useState(false);
  const ratio = `${size[0]} / ${size[1]}`;
  const move = (e: PointerEvent) => {
    const r = box.current!.getBoundingClientRect();
    setPos(Math.min(Math.max(((e.clientX - r.left) / r.width) * 100, 0), 100));
  };
  const key = (e: KeyboardEvent) => {
    const step = e.shiftKey ? 10 : 2;
    if (e.key === "ArrowLeft") setPos((p) => Math.max(p - step, 0));
    else if (e.key === "ArrowRight") setPos((p) => Math.min(p + step, 100));
    else if (e.key === "Home") setPos(0);
    else if (e.key === "End") setPos(100);
    else return;
    e.preventDefault();
  };
  const markers = showRegions ? regions.slice(0, 15) : [];
  const marks = (
    <>
      {markers.map((r) => (
        <button key={r.region} type="button" className={`mk ${selected === r.region ? "on" : ""} ${r.status !== "Needs review" ? "done" : ""}`}
          style={{ left: `${r.x * 100}%`, top: `${r.y * 100}%` }} aria-label={`Region ${r.region}, ${r.area_ha} hectares, ${r.status}`}
          onPointerDown={(e) => e.stopPropagation()} onClick={() => onSelect(r.region)}>{r.region}</button>
      ))}
    </>
  );
  if (mode === "side") {
    return (
      <div className="side2">
        <figure className="vfig"><div className="viewer" style={{ aspectRatio: ratio }}><img className="vimg" src={before} alt={`Baseline true-colour image, ${beforeLabel}`} /><span className="vlab l">{beforeLabel}</span></div></figure>
        <figure className="vfig"><div className="viewer" style={{ aspectRatio: ratio }}><img className="vimg" src={after} alt={afterAlt} /><span className="vlab l">{afterLabel}</span>{marks}</div></figure>
      </div>
    );
  }
  return (
    <div ref={box} className={`viewer swipe ${drag ? "drag" : ""}`} style={{ aspectRatio: ratio }}
      onPointerDown={(e) => { setDrag(true); (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); move(e); }}
      onPointerMove={(e) => drag && move(e)} onPointerUp={() => setDrag(false)} onPointerCancel={() => setDrag(false)}>
      
      <img className="vimg" src={before} alt={`Baseline true-colour image, ${beforeLabel}`} draggable={false} />
      
      <img className="vimg" src={after} alt={afterAlt} draggable={false} style={{ clipPath: `inset(0 0 0 ${pos}%)` }} />
      <span className="vlab l">{beforeLabel}</span><span className="vlab r">{afterLabel}</span>
      {marks}
      <div className="vhandle" style={{ left: `${pos}%` }} role="slider" tabIndex={0} aria-label="Comparison divider: left of it is the baseline, right of it the comparison"
        aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pos)} onKeyDown={key} onPointerDown={(e) => e.stopPropagation()}>
        <span className="grip" aria-hidden>⇆</span>
      </div>
    </div>
  );
}

export function LegendBar({ legend }: { legend: Legend }) {
  const grad = `linear-gradient(90deg, ${legend.stops.map(([c, p]) => `${c} ${p * 100}%`).join(", ")})`;
  return (
    <div className="legendbar" aria-label={`Colour scale from ${legend.min} to ${legend.max}`}>
      <span className="mono">{legend.min}</span><i style={{ background: grad }} /><span className="mono">{legend.max}</span>
      <span className="excl"><b /> excluded: cloud, shadow, snow, outside the mask</span>
    </div>
  );
}
