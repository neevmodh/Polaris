"use client";
/* Satellite frames are small pixelated data-URL rasters; next/image would blur or re-encode them. */
/* eslint-disable @next/next/no-img-element */
import { useEffect, useMemo, useState } from "react";
import { useGet, usePost } from "@/lib/hooks";
import { DEFAULT_CONTROLS, LAYERS, downloadB64, satPost, type CaseCard, type Controls, type FetchJob, type Kind, type SatAnalysis, type SatMeta, type SceneImages } from "@/lib/sat";
import { nf0, pct } from "@/lib/format";
import { CoordInput, ErrorNote, PageHead, Panel, Slider, Term } from "@/components/ui";
import { HBars, MetricBars } from "@/components/charts";
import SwipeViewer, { LegendBar } from "./SwipeViewer";

type Source = "case" | "custom" | "upload";
type Tab = "regions" | "evidence" | "sources";
const COPY: Record<Kind, { eyebrow: string; title: string; lede: React.ReactNode; basis: string }> = {
  forest: {
    eyebrow: "Forest loss", title: "Where has the forest changed?", basis: "Sentinel-2 · Hansen",
    lede: <>Two real Sentinel-2 scenes of the same place, cloud-masked and compared pixel by pixel. A trained random forest and a plain NDVI rule each propose <Term tip="A patch of pixels whose vegetation signal dropped sharply. It is a lead to check, not proof of deforestation.">candidate loss</Term> regions for a human to review.</>,
  },
  lake: {
    eyebrow: "Lake water", title: "What changed in the water?", basis: "Sentinel-2 · U-Net",
    lede: <>Open-water extent and optical algae and turbidity <Term tip="Unitless ratios of satellite bands. They move with chlorophyll and sediment but are not measured concentrations.">proxies</Term> compared on the same clear water pixels at two dates. These are screening signals, not a water-safety test.</>,
  },
};

const fmtDate = (s: string) => s || "—";
const fx = (v: number | null | undefined, d = 3) => (v == null ? "–" : v.toFixed(d));

export default function EarthWorkspace({ kind }: { kind: Kind }) {
  const { data: meta, error: metaErr } = useGet<SatMeta>("/api/sat/meta");
  const [source, setSource] = useState<Source>("case");
  const [caseId, setCaseId] = useState<string>(kind);
  const [cards, setCards] = useState<Record<string, CaseCard>>({});
  const [controls, setControls] = useState<Controls>(DEFAULT_CONTROLS);
  const [layer, setLayer] = useState(LAYERS[kind][0].id);
  const [mode, setMode] = useState<"swipe" | "side">("swipe");
  const [showRegions, setShowRegions] = useState(true);
  const [tab, setTab] = useState<Tab>("regions");
  const [selected, setSelected] = useState<number | null>(null);
  const [rev, setRev] = useState(0);
  const [cDensity, setCDensity] = useState(120), [released, setReleased] = useState(0.8);

  const activeCard: CaseCard | undefined = caseId === kind ? meta?.cases.find((c) => c.id === kind) : cards[caseId];
  const upd = <K extends keyof Controls>(k: K, v: Controls[K]) => setControls((c) => ({ ...c, [k]: v }));
  const useRf = controls.detector === "Trained random forest" && !!meta?.forest_model;

  const params = useMemo(() => ({ kind, case: caseId, ...controls, detector: useRf ? controls.detector : "NDVI screening baseline" }), [kind, caseId, controls, useRf]);
  const ready = !!meta && !!activeCard && !activeCard.error;
  const layerOk = LAYERS[kind].some((l) => l.id === layer && (!l.needs || (kind === "forest" && useRf)));
  const effLayer = layerOk ? layer : LAYERS[kind][0].id;
  const analysis = usePost<SatAnalysis>("/api/sat/analyze", { ...params, layer: effLayer, rev }, { debounce: 220, enabled: ready });
  const scene = usePost<SceneImages>("/api/sat/scene", { case: caseId }, { debounce: 0, enabled: ready });
  const crop = usePost<{ before: string; after: string }>("/api/sat/crop", { ...params, region: selected ?? 0 }, { debounce: 150, enabled: ready && selected != null && tab === "regions" });
  const a = analysis.data;
  const s = a?.summary;

  async function pickCase(id: string, k: Kind = kind) {
    try { const card = await satPost<CaseCard>("case", { case: id, kind: k }); setCards((c) => ({ ...c, [id]: card })); setCaseId(id); setSelected(null); }
    catch (e) { setNotice((e as Error).message); }
  }
  const [notice, setNotice] = useState<string | null>(null);

  // --- custom region fetch
  const preset = meta?.presets[kind];
  const [bbox, setBbox] = useState<number[] | null>(null);
  const [dates, setDates] = useState<string[] | null>(null);
  const [name, setName] = useState("My observation region");
  const [job, setJob] = useState<{ id: string; data: FetchJob } | null>(null);
  const box = bbox ?? preset?.bbox ?? [0, 0, 0.1, 0.1];
  const dts = dates ?? (preset ? [...preset.before, ...preset.after] : ["", "", "", ""]);
  const running = job?.data.state === "running";
  async function startFetch() {
    setNotice(null);
    try {
      const r = await satPost<{ job: string; case: string }>("fetch_start", { kind, name, bbox: box, before: dts.slice(0, 2), after: dts.slice(2, 4) });
      setJob({ id: r.job, data: { state: "running", log: ["Request accepted…"], case: r.case, error: null } });
    } catch (e) { setNotice((e as Error).message); }
  }
  useEffect(() => {
    if (!job || job.data.state !== "running") return;
    // A dropped connection must not leave the job "running" forever: retry with growing delays, then say what happened
    // and give the fetch button back so the reader can try again.
    let live = true, fails = 0, timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const d = await satPost<FetchJob>("fetch_status", { job: job.id });
        if (!live) return;
        fails = 0; setJob({ id: job.id, data: d });
        if (d.state === "done") { pickCase(d.case); return; }
        if (d.state === "error") return;
      } catch (e) {
        if (!live) return;
        if (++fails >= 5) {
          setJob({ id: job.id, data: { state: "error", log: [], case: job.data.case, error: `Lost contact with the server while fetching (${(e as Error).message || "no response"}). The fetch may still be running there; press Fetch again to resume, the cached result is reused.` } });
          return;
        }
      }
      timer = setTimeout(tick, Math.min(1500 * 2 ** fails, 12000));
    };
    timer = setTimeout(tick, 1500);
    return () => { live = false; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.id, job?.data.state]);

  // --- upload
  const [files, setFiles] = useState<{ before: File | null; after: File | null }>({ before: null, after: null });
  const [upDates, setUpDates] = useState(["2020-02-01", "2024-02-01"]);
  const [encoding, setEncoding] = useState("float");
  const [uploading, setUploading] = useState(false);
  async function doUpload() {
    setNotice(null); setUploading(true);
    try {
      const f = new FormData();
      f.set("before", files.before!); f.set("after", files.after!); f.set("before_date", upDates[0]); f.set("after_date", upDates[1]);
      f.set("encoding", encoding); f.set("name", name); f.set("kind", kind);
      const r = await fetch("/api/sat/upload", { method: "POST", body: f }); const j = await r.json();
      if (!r.ok) throw new Error(j.error ?? "Upload failed");
      setCards((c) => ({ ...c, [j.case]: j.card })); setCaseId(j.case); setSelected(null);
    } catch (e) { setNotice((e as Error).message); } finally { setUploading(false); }
  }

  // --- review + export
  const sel = a?.regions.find((r) => r.region === selected) ?? null;
  const [draft, setDraft] = useState<{ id: number | null; status: string; note: string }>({ id: null, status: "Needs review", note: "" });
  const [statusFilter, setStatusFilter] = useState("All");
  const [saving, setSaving] = useState(false);
  if (sel && draft.id !== sel.region) setDraft({ id: sel.region, status: sel.status, note: sel.note });
  async function saveReview() {
    if (!sel) return;
    setSaving(true);
    try { await satPost("review", { ...params, region: sel.region, status: draft.status, note: draft.note }); setRev((n) => n + 1); }
    catch (e) { setNotice((e as Error).message); } finally { setSaving(false); }
  }
  async function exportWhat(what: "package" | "summary" | "geojson" | "csv") {
    try {
      const r = await satPost<{ name: string; mime: string; text?: string; b64?: string }>("export", { ...params, what });
      if (r.b64) downloadB64(r.name, r.mime, r.b64);
      else { const url = URL.createObjectURL(new Blob([r.text ?? ""], { type: r.mime })); const l = Object.assign(document.createElement("a"), { href: url, download: r.name }); document.body.appendChild(l); l.click(); l.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
    } catch (e) { setNotice((e as Error).message); }
  }

  const tiles = !s ? null : kind === "forest"
    ? [["Candidate forest loss", `${nf0.format(s.candidate_loss_area_ha ?? 0)} ha`, `${s.candidate_loss_area_ha?.toFixed(2)} ha`], ["Regions to review", String(s.alert_regions), "connected patches"],
       ["Clear paired coverage", `${s.observed_pair_pct.toFixed(1)}%`, "pixels clear on both dates"], [a?.prior_used ? "Baseline forest support" : "Baseline vegetation", `${nf0.format(s.baseline_vegetation_area_ha ?? 0)} ha`, a?.prior_used ? "Hansen canopy ≥ 30%, no earlier loss" : "high baseline NDVI only"]]
    : [["Comparable open water", `${nf0.format(s.common_water_ha ?? 0)} ha`, "clear water on both dates"], ["Algae proxy increase", `${nf0.format(s.algae_proxy_increase_ha ?? 0)} ha`, "NDCI rise above threshold"],
       ["Clear paired coverage", `${s.observed_pair_pct.toFixed(1)}%`, "pixels clear on both dates"], ["Observed water area", `${nf0.format(s.after_open_water_ha ?? 0)} ha`, "comparison date, eroded mask"]];

  const regionsShown = (a?.regions ?? []).filter((r) => statusFilter === "All" || r.status === statusFilter);
  const m = meta?.metrics;

  return (
    <>
      <PageHead eyebrow={COPY[kind].eyebrow} title={COPY[kind].title}>{COPY[kind].lede}</PageHead>
      <ErrorNote message={metaErr} />
      {notice && <div className="alert err" role="alert" style={{ marginBottom: 16 }}>{notice} <button className="btn ghost" onClick={() => setNotice(null)}>Dismiss</button></div>}
      <div className="grid2 earth">
        <div className="stack rail fade">
          <Panel title="Observation" tick="var(--s1)">
            <div className="seg2" role="group" aria-label="Imagery source" style={{ alignSelf: "flex-start" }}>
              {([["case", "Case study"], ["custom", "Custom region"], ["upload", "Upload"]] as const).map(([id, label]) => (
                <button key={id} aria-pressed={source === id} onClick={() => { setSource(id); if (id === "case") { setCaseId(kind); setSelected(null); } }}>{label}</button>
              ))}
            </div>
            {source === "case" && activeCard && !activeCard.error && (
              <dl className="prov tight"><dt>Place</dt><dd><b>{activeCard.name}</b> · {activeCard.location}</dd><dt>Dates</dt><dd className="num nw">{fmtDate(activeCard.before.datetime)} → {fmtDate(activeCard.after.datetime)}</dd>
                <dt>Grid</dt><dd>{activeCard.size[0]} × {activeCard.size[1]} px at {activeCard.before.resolution_m} m · {activeCard.before.crs}</dd></dl>
            )}
            {source === "case" && <p className="note">Cached real Sentinel-2 pair. Works offline.</p>}
            {source === "custom" && (
              <>
                <p className="note">A box with each side under 0.3°. Imagery is fetched from the public Earth Search catalogue; this can take a minute or two.</p>
                <div className="fields">
                  <CoordInput id="bb-w" label="West" value={box[0]} onChange={(v) => setBbox([v, box[1], box[2], box[3]])} />
                  <CoordInput id="bb-e" label="East" value={box[2]} onChange={(v) => setBbox([box[0], box[1], v, box[3]])} />
                  <CoordInput id="bb-s" label="South" value={box[1]} onChange={(v) => setBbox([box[0], v, box[2], box[3]])} />
                  <CoordInput id="bb-n" label="North" value={box[3]} onChange={(v) => setBbox([box[0], box[1], box[2], v])} />
                </div>
                <div className="fields">
                  {["Baseline start", "Baseline end", "Comparison start", "Comparison end"].map((l, i) => (
                    <div className="field" key={l}><label htmlFor={`dt-${i}`}>{l}</label><div className="inp"><input id={`dt-${i}`} type="date" value={dts[i]} onChange={(e) => setDates(dts.map((d, j) => (j === i ? e.target.value : d)))} /></div></div>
                  ))}
                </div>
                <div className="field"><label htmlFor="rname">Region name</label><div className="inp"><input id="rname" value={name} maxLength={60} onChange={(e) => setName(e.target.value)} /></div></div>
                <div className="btns"><button className="btn primary" onClick={startFetch} disabled={running}>{running ? "Fetching…" : "Fetch satellite imagery"}</button>
                  <button className="btn ghost" onClick={() => { setBbox(null); setDates(null); }}>Reset to case study box</button></div>
                {job && <div className="log" aria-live="polite">{job.data.state === "error" ? <b style={{ color: "var(--bad)" }}>{job.data.error}</b> : job.data.log.map((l, i) => <div key={i}>{l}</div>)}</div>}
                {!!meta?.custom.filter((c) => c.kind === kind).length && (
                  <div className="field"><label htmlFor="prev">Earlier fetches</label><div className="inp"><select id="prev" value="" onChange={(e) => e.target.value && pickCase(e.target.value)}><option value="">Choose…</option>{meta.custom.filter((c) => c.kind === kind).map((c) => <option key={c.id} value={c.id}>{c.name} · {c.before}</option>)}</select></div></div>
                )}
              </>
            )}
            {source === "upload" && (
              <>
                <p className="note">Eight bands in this order: B02, B03, B04, B08, B11, B12, B05, SCL. Same projected grid in metres. The prepared pair in Task3/outputs/{kind}/ works as a test.</p>
                {(["before", "after"] as const).map((k, i) => (
                  <div className="field" key={k}><label htmlFor={`f-${k}`}>{k === "before" ? "Baseline" : "Comparison"} GeoTIFF</label>
                    <div className="inp"><input id={`f-${k}`} type="file" accept=".tif,.tiff" onChange={(e) => setFiles({ ...files, [k]: e.target.files?.[0] ?? null })} /></div>
                    <div className="inp"><input aria-label={`${k} acquisition date`} type="date" value={upDates[i]} onChange={(e) => setUpDates(upDates.map((d, j) => (j === i ? e.target.value : d)))} /></div></div>
                ))}
                <div className="field"><label htmlFor="enc">Reflectance encoding</label><div className="inp"><select id="enc" value={encoding} onChange={(e) => setEncoding(e.target.value)}><option value="float">Surface reflectance (float)</option><option value="dn">Harmonized reflectance × 10,000</option></select></div></div>
                <button className="btn primary" onClick={doUpload} disabled={!files.before || !files.after || uploading}>{uploading ? "Checking…" : "Use these rasters"}</button>
              </>
            )}
          </Panel>

          <Panel title="Detector" tick="var(--ml)">
            {kind === "forest" ? (
              <>
                <div className="field"><label htmlFor="det">Detection method</label><div className="inp"><select id="det" value={useRf ? controls.detector : "NDVI screening baseline"} onChange={(e) => upd("detector", e.target.value as Controls["detector"])}>
                  {meta?.forest_model && <option>Trained random forest</option>}<option>NDVI screening baseline</option></select></div></div>
                {useRf && <Slider label="Model score threshold" value={controls.threshold} min={0.1} max={0.9} step={0.05} onChange={(v) => upd("threshold", v)} format={(v) => v.toFixed(2)} />}
                <Slider label="NDVI decline threshold" value={controls.drop} min={0.05} max={0.6} step={0.05} onChange={(v) => upd("drop", v)} format={(v) => v.toFixed(2)} />
                <Slider label="Baseline vegetation (NDVI)" value={controls.vegetation} min={0.3} max={0.85} step={0.05} onChange={(v) => upd("vegetation", v)} format={(v) => v.toFixed(2)} />
                <Slider label="Minimum patch" value={controls.patches} min={1} max={30} step={1} onChange={(v) => upd("patches", v)} format={(v) => `${v} px`} />
                {caseId !== "forest" && useRf && <p className="note">The forest model was trained on the Rondônia pair only. Check its alerts before trusting them elsewhere.</p>}
              </>
            ) : (
              <>
                <div className="field"><label htmlFor="wm">Water segmentation</label><div className="inp"><select id="wm" value={controls.water} onChange={(e) => upd("water", e.target.value as Controls["water"])}>
                  <option>Spectral open-water mask</option>{meta?.unet && <option>Pretrained U-Net</option>}</select></div></div>
                <Slider label="Open-water MNDWI threshold" value={controls.mndwi} min={-0.2} max={0.4} step={0.05} onChange={(v) => upd("mndwi", v)} format={(v) => v.toFixed(2)} />
                <Slider label="Algae proxy increase threshold" value={controls.algae} min={0.02} max={0.4} step={0.02} onChange={(v) => upd("algae", v)} format={(v) => v.toFixed(2)} />
                {controls.water === "Pretrained U-Net" && <p className="note">The U-Net segments water; it is not a pollution classifier. The first run for a scene takes a few seconds, then it is cached.</p>}
              </>
            )}
          </Panel>
        </div>

        <div className="stack fade" style={{ animationDelay: ".08s" }}>
          <ErrorNote message={analysis.error ?? scene.error} />
          {!a && !analysis.error && <div className="skeleton" style={{ height: 120 }} />}
          {tiles && (
            <div className={`kpis ${analysis.loading ? "busy" : ""}`}>
              {tiles.map(([k, v, d]) => <div className="kpi" key={k}><div className="k">{k}</div><div className="v num">{v}</div><div className="d">{d}</div></div>)}
            </div>
          )}
          <Panel title="Observation workspace" tick="var(--ink)" right={<span>{activeCard ? `${activeCard.before.datetime} → ${activeCard.after.datetime}` : ""}</span>}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "10px 18px", alignItems: "center", justifyContent: "space-between" }}>
              <div className="chips" role="group" aria-label="Comparison layer">
                {LAYERS[kind].map((l) => { const off = !!l.needs && !(kind === "forest" && useRf); return <button key={l.id} className="chip-btn" aria-pressed={effLayer === l.id} disabled={off} title={off ? "Select the trained random forest" : undefined} onClick={() => setLayer(l.id)}>{l.label}</button>; })}
              </div>
              <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
                <div className="seg2" role="group" aria-label="Viewer">
                  <button aria-pressed={mode === "swipe"} onClick={() => setMode("swipe")}>Swipe</button><button aria-pressed={mode === "side"} onClick={() => setMode("side")}>Side by side</button>
                </div>
                <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13 }}><input type="checkbox" checked={showRegions} onChange={(e) => setShowRegions(e.target.checked)} />Region markers</label>
              </div>
            </div>
            <div className={analysis.loading ? "busy" : ""}>
              {scene.data && a ? (
                <SwipeViewer before={scene.data.before} after={a.image} size={a.size} beforeLabel={`Baseline ${scene.data.before_info.datetime}`} afterLabel={`Comparison ${scene.data.after_info.datetime}`}
                  afterAlt={`Comparison image, layer: ${LAYERS[kind].find((l) => l.id === effLayer)?.label}`} mode={mode} regions={a.regions} selected={selected} onSelect={(id) => { setSelected(id); setTab("regions"); }} showRegions={showRegions} />
              ) : <div className="skeleton" style={{ aspectRatio: activeCard ? `${activeCard.size[0]} / ${activeCard.size[1]}` : "1 / 1" }} />}
            </div>
            {a?.legend && <LegendBar legend={a.legend} />}
            <p className="note">{mode === "swipe" ? "Drag the divider, or focus it and use the arrow keys." : "Both panels use the same reflectance stretch."} Numbered markers are the largest regions; click one to review it. Areas count clear pixels only.</p>
            {s && <div className="alert" style={{ fontSize: 13 }}><span aria-hidden>ⓘ</span><span>{s.interpretation}</span></div>}
          </Panel>
        </div>
      </div>

      <div className="tabs" role="tablist" aria-label="Details" style={{ marginTop: 32 }}>
        {([["regions", kind === "forest" ? "Regions & review" : "Regions & indicators"], ["evidence", "Model & evidence"], ["sources", "Sources & export"]] as const).map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>

      {tab === "regions" && a && (
        <div className="stack fade" style={{ marginTop: 22 }}>
          {kind === "forest" && s?.candidate_loss_area_ha != null && (
            <Panel title="Carbon at stake in the candidate loss (indicative)" tick="var(--s1)" right={<span>not added to any footprint</span>}>
              <div className="grid2 even">
                <div className="stack">
                  <Slider label="Aboveground carbon density you assume" value={cDensity} min={40} max={250} step={5} onChange={setCDensity} format={(v) => `${v} tC / ha`} />
                  <Slider label="Share released to the atmosphere" value={released} min={0.3} max={1} step={0.05} onChange={setReleased} format={(v) => pct(v)} />
                  <p className="note">Placeholders, not data. Replace the density with a local biomass map (for example ESA CCI Biomass or GEDI) before quoting a number; the share depends on what happens to the wood.</p>
                </div>
                <div>
                  <div className="eyebrow">Indicative CO₂ if every candidate hectare were cleared forest</div>
                  <div className="big" style={{ fontSize: "clamp(40px,5vw,64px)", marginTop: 8 }}>{nf0.format(s.candidate_loss_area_ha * cDensity * released * (44 / 12))}<small>tCO₂</small></div>
                  <p className="sub" style={{ marginTop: 8 }}>Range {nf0.format(s.candidate_loss_area_ha * cDensity * 0.67 * released * (44 / 12))}–{nf0.format(s.candidate_loss_area_ha * cDensity * 1.33 * released * (44 / 12))} t for a ±33% carbon density. Formula: hectares × tC/ha × share × 44/12.</p>
                  <p className="note" style={{ marginTop: 8 }}>The {s.candidate_loss_area_ha.toFixed(1)} ha are <b>candidates for review</b>, not verified deforestation, and the result is kept out of the Scope 1/2/3 calculator on purpose.</p>
                </div>
              </div>
            </Panel>
          )}
          {kind === "lake" && s?.indicators && (
            <Panel title="Indicators on the same clear-water pixels" tick="var(--s2)">
              <div className="scroll"><table className="t"><thead><tr><th>Indicator</th><th>Meaning</th><th className="r">Before</th><th className="r">After</th><th className="r">Change</th></tr></thead>
                <tbody>{s.indicators.map((i) => <tr key={i.indicator}><td className="mono">{i.indicator}</td><td>{i.meaning}</td><td className="r">{fx(i.before_median, 4)}</td><td className="r">{fx(i.after_median, 4)}</td><td className="r"><b>{i.change == null ? "–" : (i.change > 0 ? "+" : "") + i.change.toFixed(4)}</b></td></tr>)}</tbody></table></div>
              <p className="note">Unitless spectral proxies (medians). NDCI uses Sentinel-2 B05 and B04. They are ratios, not calibrated concentrations.</p>
            </Panel>
          )}
          <div className="master">
            <Panel title={`Candidate regions · ${a.region_total} found, ${a.reviewed} reviewed`} tick="var(--s1)" right={
              <select aria-label="Filter by review status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ font: "inherit", background: "transparent", border: "1px solid var(--ink)", padding: "3px 6px" }}>
                <option>All</option>{meta?.review_states.map((x) => <option key={x}>{x}</option>)}</select>}>
              {a.region_total === 0 ? <p className="note">No regions meet the current thresholds. Try loosening a slider.</p> : (
                <div className="scroll" style={{ maxHeight: 420, overflowY: "auto" }}><table className="t">
                  <thead><tr><th>#</th><th className="r">Area ha</th><th className="r">Lat</th><th className="r">Lon</th><th className="r">Δ index</th>{a.scores_available && <th className="r">Score</th>}<th>Status</th></tr></thead>
                  <tbody>{regionsShown.map((r) => (
                    <tr key={r.region} className={`pick ${selected === r.region ? "on" : ""}`} tabIndex={0} onClick={() => setSelected(r.region)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), setSelected(r.region))}>
                      <td className="mono">{r.region}</td><td className="r">{r.area_ha.toFixed(2)}</td><td className="r">{r.latitude.toFixed(4)}</td><td className="r">{r.longitude.toFixed(4)}</td>
                      <td className="r">{fx(r.mean_index_change, 3)}</td>{a.scores_available && <td className="r">{fx(r.mean_model_score, 2)}</td>}<td>{r.status === "Needs review" ? <span className="pill">pending</span> : <span className={`pill ${r.status === "Likely change" ? "good" : r.status === "False positive" ? "warn" : ""}`}>{r.status}</span>}</td>
                    </tr>))}</tbody></table></div>
              )}
              {a.region_total > a.regions.length && <p className="note">Showing the {a.regions.length} largest of {a.region_total} regions. The export contains all of them.</p>}
            </Panel>
            <Panel title={sel ? `Region ${sel.region} · ${sel.area_ha.toFixed(2)} ha` : "Select a region"} tick="var(--s1)">
              {!sel ? <p className="note">Click a marker on the image or a row in the table to inspect the region and record a decision. Decisions are human screening notes, not verified findings.</p> : (
                <>
                  <p className="note">{sel.latitude.toFixed(5)}°, {sel.longitude.toFixed(5)}° · mean index change {fx(sel.mean_index_change, 3)}{sel.mean_model_score != null && ` · model score ${sel.mean_model_score.toFixed(2)} (uncalibrated)`}</p>
                  {crop.data ? (
                    <div className="crops"><figure><img src={crop.data.before} alt={`Region ${sel.region}, before`} /><figcaption>BEFORE</figcaption></figure>
                      <figure><img src={crop.data.after} alt={`Region ${sel.region}, after, region outlined`} /><figcaption>AFTER · selected region</figcaption></figure></div>
                  ) : <div className="skeleton" style={{ height: 150 }} />}
                  <div className="field"><span className="lab">Review decision</span>
                    <div className="seg2" role="group" aria-label="Review decision" style={{ flexWrap: "wrap" }}>{meta?.review_states.map((x) => <button key={x} aria-pressed={draft.status === x} onClick={() => setDraft({ ...draft, status: x })}>{x}</button>)}</div></div>
                  <div className="field"><label htmlFor="rnote">Notes</label><textarea id="rnote" className="note-in" maxLength={2000} value={draft.note} placeholder="What you see, possible confounders, evidence still needed." onChange={(e) => setDraft({ ...draft, note: e.target.value })} /></div>
                  <p className="note" style={{ margin: 0 }}>{a?.review_scope === "public demo" ? "Reviews on the demo cases are shared: every visitor sees them. Do not record anything private here." : "Reviews on your own uploads and fetched regions are private to this browser session."}</p>
                  <button className="btn primary" onClick={saveReview} disabled={saving} style={{ alignSelf: "flex-start" }}>{saving ? "Saving…" : "Save review"}</button>
                </>
              )}
            </Panel>
          </div>
        </div>
      )}

      {tab === "evidence" && (
        <div className="stack fade" style={{ marginTop: 22 }}>
          {kind === "forest" && m && useRf ? (
            <div className="grid2 even">
              <Panel title="A trained model with an explicit holdout" tick="var(--ml)">
                <MetricBars aName="Random forest" bName="NDVI baseline" groups={[
                  { label: "precision", a: m.rf.precision, b: m.ndvi_baseline.precision }, { label: "recall", a: m.rf.recall, b: m.ndvi_baseline.recall }, { label: "F1", a: m.rf.f1, b: m.ndvi_baseline.f1 },
                  { label: "IoU", a: m.rf.iou, b: m.ndvi_baseline.iou }, { label: "avg prec.", a: m.rf.average_precision, b: m.ndvi_baseline.average_precision }]} />
                <p className="note">{nf0.format(m.trained_samples)} training samples · {nf0.format(m.holdout_samples)} held-out pixels, {nf0.format(m.holdout_positive_samples)} with reference loss · label years {m.label_interval}. Split: {m.spatial_split}.</p>
              </Panel>
              <Panel title="What drives the forest model" tick="var(--ml)">
                <HBars rows={Object.entries(m.feature_importance).sort((x, y) => y[1] - x[1]).slice(0, 8).map(([name, value]) => ({ name, value }))} />
                <div className="alert" style={{ fontSize: 13 }}><span aria-hidden>⚠</span><span>This measures agreement with a satellite-derived reference (Hansen) in one region. It is not field accuracy and says nothing yet about other places or years. {m.probability_note}</span></div>
              </Panel>
            </div>
          ) : kind === "forest" ? (
            <Panel title="The NDVI screening baseline" tick="var(--ml)"><p className="note">It flags a vegetation-index decline in previously vegetated pixels. It is a transparent screening rule, not a trained model. Switch to the random forest to see held-out evidence.</p></Panel>
          ) : (
            <Panel title="What these observations can and cannot establish" tick="var(--s2)">
              <div className="two"><ul className="ledger yes"><li><span className="lk">✓</span><span>Open-water extent on clear pixels at two dates.</span></li><li><span className="lk">✓</span><span>Direction and size of optical algae and turbidity proxy change on the same pixels.</span></li>{meta?.unet && <li><span className="lk">✓</span><span>How sensitive the result is to the water mask, by switching spectral and U-Net.</span></li>}</ul>
                <ul className="ledger no"><li><span className="lk">✕</span><span>Chlorophyll, NTU, sewage, bacteria, heavy metals or drinking-water safety.</span></li><li><span className="lk">✕</span><span>Anything validated against field samples: none were available.</span></li><li><span className="lk">✕</span><span>Effects of sun glint, shallow bottoms and floating plants, which remain confounders.</span></li></ul></div>
              <p className="note">{meta?.unet
                ? "The U-Net segments water only. Its upstream project makes no water-safety claim and neither does Polaris."
                : "The pretrained U-Net is not installed here, so every figure on this sheet comes from the spectral open-water mask. The U-Net is an alternative segmenter, not a better one; where both are available they can be compared."}</p>
            </Panel>
          )}
        </div>
      )}

      {tab === "sources" && (
        <div className="stack fade" style={{ marginTop: 22 }}>
          <div className="grid2 even">
            {([scene.data?.before_info, scene.data?.after_info]).map((si, i) => si && (
              <Panel key={i} title={`${si.label} scene`} tick="var(--s1)">
                <dl className="prov"><dt>ID</dt><dd className="mono" style={{ fontSize: 12 }}>{si.id}</dd><dt>Acquired</dt><dd>{si.datetime}</dd><dt>Source</dt><dd>{si.source}</dd>
                  <dt>Scene cloud</dt><dd>{si.cloud_cover_scene_pct == null ? "–" : `${si.cloud_cover_scene_pct.toFixed(2)}%`}</dd><dt>Clear pixels</dt><dd>{si.clear_pct.toFixed(1)}% of the box</dd>
                  <dt>Baseline</dt><dd>processing {si.processing_baseline ?? "n/a"}</dd><dt>Grid</dt><dd>{si.shape[1]} × {si.shape[0]} px · {si.resolution_m} m · {si.crs}</dd><dt>Quality</dt><dd>{si.quality}</dd>
                  <dt>Bounds</dt><dd className="mono" style={{ fontSize: 12 }}>{si.bounds_wgs84.map((v) => v.toFixed(4)).join(", ")}</dd></dl>
              </Panel>
            ))}
          </div>
          <Panel title="Export" tick="var(--ink)">
            <div className="btns">
              <button className="btn primary" onClick={() => exportWhat("package")} disabled={!a}>Analysis package (ZIP)</button>
              <button className="btn" onClick={() => exportWhat("summary")} disabled={!a}>Summary JSON</button>
              <button className="btn" onClick={() => exportWhat("geojson")} disabled={!a}>Reviewed regions (GeoJSON)</button>
              <button className="btn" onClick={() => exportWhat("csv")} disabled={!a}>Review queue (CSV)</button>
            </div>
            <p className="note">The ZIP holds a Markdown report, JSON summary, before and after images, GeoTIFF layers, review regions in WGS84, the indicator table and the source scene metadata. Your review decisions are included.</p>
          </Panel>
          <Panel title="Data and references" tick="var(--ink)">
            <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6 }} className="note">
              <li>Copernicus Sentinel-2 Collection 1 Level 2A via Element 84 Earth Search. Free and open Sentinel terms.</li>
              {kind === "forest" ? <li>Hansen Global Forest Change 2024 v1.12 (CC BY 4.0) as a satellite-derived reference map, not field truth. Hansen et al., Science 342 (2013).</li> : <li>U-Net water segmentation from Iulia-plesu/lake-detection-water-quality (Apache-2.0); spectral ratios after the RAJohansen/waterquality R package (MIT).</li>}
              <li>SCL masking and NDVI-difference workflow adapted from TerraVision (MIT). Full revisions and licences: <span className="mono">Task3/THIRD_PARTY_NOTICES.md</span>.</li>
              {s && <li>Parameters used: <span className="mono">{JSON.stringify(s.parameters)}</span></li>}
            </ul>
          </Panel>
        </div>
      )}
      {a && <p className="note" style={{ marginTop: 18 }}>Analysis computed in {a.seconds}s · {pct(s?.observed_pair_pct ? s.observed_pair_pct / 100 : 0, 1)} of the box clear on both dates.</p>}
    </>
  );
}
