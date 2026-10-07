"use client";

export default function ErrorPage({ reset }: { error: Error; reset: () => void }) {
  return (
    <div style={{ padding: "48px 0", maxWidth: 560 }} role="alert">
      <div className="eyebrow">Something broke</div>
      <h1 className="title">This sheet could not be drawn.</h1>
      <p className="lede">Your inputs are saved in this browser, so nothing is lost. Try again, and if it keeps happening check that the engine is running with <span className="mono">make web</span>.</p>
      <p style={{ marginTop: 22 }}><button className="btn primary" onClick={reset}>Try again</button></p>
    </div>
  );
}
