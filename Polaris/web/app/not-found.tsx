import Link from "next/link";

export default function NotFound() {
  return (
    <div style={{ padding: "48px 0", maxWidth: 560 }}>
      <div className="eyebrow">404 · Sheet not found</div>
      <h1 className="title">That sheet is not in this set.</h1>
      <p className="lede">Polaris has ten numbered sheets across Carbon, Earth, Plan and Evidence. The overview lists them all.</p>
      <p style={{ marginTop: 22 }}><Link className="btn primary" href="/">Back to the overview</Link></p>
    </div>
  );
}
