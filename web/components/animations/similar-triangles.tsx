'use client';

/**
 * Concept animation — CBSE Class 10 Mathematics, Ch 6 "Triangles" (§6.3 Similarity of Triangles,
 * the Basic Proportionality Theorem).
 *
 * A is fixed, and t (state) is the fraction AD/AB. D and E are placed at that fraction along AB and
 * AC, so DE comes out parallel to BC — every length on screen is measured from the drawn points with
 * Math.hypot, and every ratio is a division of those measured lengths.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export type ConceptAnimationProps = { className?: string };

const W = 680;
const H = 380;

/* the triangle, in world coordinates */
const A = { x: 0, y: 3.4 };
const B = { x: -6, y: -2.6 };
const Cpt = { x: 5, y: -3.4 };

const C = {
  bg: '#0b1020',
  grid: '#17233d',
  outer: '#60a5fa',
  inner: '#fbbf24',
  parallel: '#34d399',
  ink: '#e5e7eb',
  dim: '#94a3b8',
};

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const apply = () => setReduced(mq.matches);
    apply();
    if (typeof mq.addEventListener === 'function') {
      mq.addEventListener('change', apply);
      return () => mq.removeEventListener('change', apply);
    }
    mq.addListener(apply);
    return () => mq.removeListener(apply);
  }, []);
  return reduced;
}

function prepare(canvas: HTMLCanvasElement): CanvasRenderingContext2D | null {
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  const dpr = typeof window === 'undefined' ? 1 : Math.min(window.devicePixelRatio || 1, 2);
  const w = Math.round(W * dpr);
  const h = Math.round(H * dpr);
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  return ctx;
}

const dist = (p: { x: number; y: number }, q: { x: number; y: number }) =>
  Math.hypot(q.x - p.x, q.y - p.y);

export default function SimilarTriangles({ className }: ConceptAnimationProps) {
  const [t, setT] = useState(0.5);
  const [showInner, setShowInner] = useState(true);
  const reduced = useReducedMotion();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  /* ---- the drawn points, and every length measured from them ---- */
  const D = { x: A.x + t * (B.x - A.x), y: A.y + t * (B.y - A.y) };
  const E = { x: A.x + t * (Cpt.x - A.x), y: A.y + t * (Cpt.y - A.y) };

  const ab = dist(A, B);
  const ac = dist(A, Cpt);
  const bc = dist(B, Cpt);
  const ad = dist(A, D);
  const db = dist(D, B);
  const ae = dist(A, E);
  const ec = dist(E, Cpt);
  const de = dist(D, E);

  const ratioAdDb = ad / db;
  const ratioAeEc = ae / ec;
  const ratioDeBc = de / bc;
  const scaleAbAd = ab / ad;

  /* parallel check by slope: DE and BC should have the same gradient */
  const slopeDe = (E.y - D.y) / (E.x - D.x);
  const slopeBc = (Cpt.y - B.y) / (Cpt.x - B.x);
  const slopeGap = Math.abs(slopeDe - slopeBc);
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = prepare(canvas);
    if (!ctx) return;

    ctx.fillStyle = C.bg;
    ctx.fillRect(0, 0, W, H);
    ctx.font = '12px ui-sans-serif, system-ui, sans-serif';
    ctx.textBaseline = 'middle';

    /* one uniform scale for both axes, so the shapes really are similar on screen */
    const xs = [A.x, B.x, Cpt.x, D.x, E.x];
    const ys = [A.y, B.y, Cpt.y, D.y, E.y];
    const xMin = Math.min(...xs);
    const xMax = Math.max(...xs);
    const yMin = Math.min(...ys);
    const yMax = Math.max(...ys);
    const padX = 56;
    const padTop = 34;
    const padBottom = 60;
    const availW = W - 2 * padX;
    const availH = H - padTop - padBottom;
    const scale = Math.min(availW / (xMax - xMin), availH / (yMax - yMin));
    const ox = padX + (availW - (xMax - xMin) * scale) / 2 - xMin * scale;
    const oy = padTop + (availH - (yMax - yMin) * scale) / 2 + yMax * scale;
    const X = (x: number) => ox + x * scale;
    const Y = (y: number) => oy - y * scale;

    /* the big triangle ABC */
    ctx.strokeStyle = C.outer;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.moveTo(X(A.x), Y(A.y));
    ctx.lineTo(X(B.x), Y(B.y));
    ctx.lineTo(X(Cpt.x), Y(Cpt.y));
    ctx.closePath();
    ctx.stroke();

    /* the inner triangle ADE */
    if (showInner) {
      ctx.fillStyle = 'rgba(251, 191, 36, 0.10)';
      ctx.beginPath();
      ctx.moveTo(X(A.x), Y(A.y));
      ctx.lineTo(X(D.x), Y(D.y));
      ctx.lineTo(X(E.x), Y(E.y));
      ctx.closePath();
      ctx.fill();
    }

    /* the parallel segment DE */
    ctx.strokeStyle = C.parallel;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.moveTo(X(D.x), Y(D.y));
    ctx.lineTo(X(E.x), Y(E.y));
    ctx.stroke();

    /* parallel tick marks: one on DE, two on BC */
    const tick = (p1: { x: number; y: number }, p2: { x: number; y: number }, count: number) => {
      const mx = (p1.x + p2.x) / 2;
      const my = (p1.y + p2.y) / 2;
      const dx = p2.x - p1.x;
      const dy = p2.y - p1.y;
      const len = Math.hypot(dx, dy) || 1;
      const nx = -dy / len;
      const ny = dx / len;
      ctx.strokeStyle = C.dim;
      ctx.lineWidth = 1.5;
      for (let i = 0; i < count; i++) {
        const off = (i - (count - 1) / 2) * 7;
        ctx.beginPath();
        ctx.moveTo(X(mx + nx * 0.22 + (dx / len) * (off / scale)), Y(my + ny * 0.22 + (dy / len) * (off / scale)));
        ctx.lineTo(X(mx - nx * 0.22 + (dx / len) * (off / scale)), Y(my - ny * 0.22 + (dy / len) * (off / scale)));
        ctx.stroke();
      }
    };
    tick(D, E, 1);
    tick(B, Cpt, 2);

    /* the vertices */
    const dot = (p: { x: number; y: number }, colour: string) => {
      ctx.fillStyle = colour;
      ctx.beginPath();
      ctx.arc(X(p.x), Y(p.y), 4.5, 0, Math.PI * 2);
      ctx.fill();
    };
    dot(A, C.ink);
    dot(B, C.ink);
    dot(Cpt, C.ink);
    dot(D, C.inner);
    dot(E, C.inner);

    ctx.fillStyle = C.ink;
    ctx.fillText('A', X(A.x) - 4, Y(A.y) - 14);
    ctx.fillText('B', X(B.x) - 16, Y(B.y) + 6);
    ctx.fillText('C', X(Cpt.x) + 8, Y(Cpt.y) + 6);
    ctx.fillStyle = C.inner;
    ctx.fillText('D', X(D.x) - 20, Y(D.y) + 2);
    ctx.fillText('E', X(E.x) + 8, Y(E.y) + 2);

    ctx.fillStyle = C.dim;
    ctx.fillText(`AD = ${ad.toFixed(3)}`, X((A.x + D.x) / 2) - 62, Y((A.y + D.y) / 2));
    ctx.fillText(`DB = ${db.toFixed(3)}`, X((D.x + B.x) / 2) - 62, Y((D.y + B.y) / 2));
    ctx.fillText(`AE = ${ae.toFixed(3)}`, X((A.x + E.x) / 2) + 10, Y((A.y + E.y) / 2));
    ctx.fillText(`EC = ${ec.toFixed(3)}`, X((E.x + Cpt.x) / 2) + 10, Y((E.y + Cpt.y) / 2));

    ctx.fillStyle = C.parallel;
    ctx.fillText(`DE = ${de.toFixed(3)}`, X((D.x + E.x) / 2) - 26, Y((D.y + E.y) / 2) - 16);
    ctx.fillStyle = C.outer;
    ctx.fillText(`BC = ${bc.toFixed(3)}`, X((B.x + Cpt.x) / 2) - 26, Y((B.y + Cpt.y) / 2) + 20);

    ctx.fillStyle = C.ink;
    ctx.fillText(
      `AD/DB = ${ratioAdDb.toFixed(4)}    AE/EC = ${ratioAeEc.toFixed(4)}    DE/BC = ${ratioDeBc.toFixed(4)}`,
      padX - 16,
      H - 22,
    );
    ctx.fillStyle = C.dim;
    ctx.fillText(
      `t = AD/AB = ${t.toFixed(2)}   AB/AD = ${scaleAbAd.toFixed(4)}   slope gap |m(DE) − m(BC)| = ${slopeGap.toExponential(1)}`,
      padX - 16,
      H - 6,
    );
  }, [t, D, E, ad, db, ae, ec, de, bc, ratioAdDb, ratioAeEc, ratioDeBc, scaleAbAd, slopeGap, showInner]);
  useEffect(() => {
    draw();
  }, [draw]);

  const fmt = (v: number, d = 3) => (Number.isFinite(v) ? v.toFixed(d) : '—');

  return (
    <section
      className={className}
      data-testid="similar-triangles"
      data-t={String(t)}
      data-ad={String(ad)}
      data-db={String(db)}
      data-ae={String(ae)}
      data-ec={String(ec)}
      data-ratio-ad-db={String(ratioAdDb)}
      data-ratio-ae-ec={String(ratioAeEc)}
      data-de={String(de)}
      data-bc={String(bc)}
      data-ratio-de-bc={String(ratioDeBc)}
      data-scale-ab-ad={String(scaleAbAd)}
      data-slope-gap={String(slopeGap)}
      data-reduced-motion={reduced ? 'true' : 'false'}
      style={{
        background: C.bg,
        color: C.ink,
        border: '1px solid #1f2a44',
        borderRadius: 12,
        padding: 16,
        fontFamily: 'ui-sans-serif, system-ui, sans-serif',
        maxWidth: W + 34,
      }}
    >
      <h3 style={{ margin: '0 0 4px', fontSize: 16 }}>
        Similar triangles and the Basic Proportionality Theorem
      </h3>
      <p style={{ margin: '0 0 12px', fontSize: 13, color: C.dim }}>
        CBSE Class 10 Mathematics · Ch 6 §6.3 — a line parallel to one side of a triangle divides the
        other two sides in the same ratio.
      </p>

      <canvas
        ref={canvasRef}
        data-testid="similar-canvas"
        width={W}
        height={H}
        role="img"
        aria-label={`Triangle ABC with DE parallel to BC; AD by DB is ${ratioAdDb.toFixed(4)}, AE by EC is ${ratioAeEc.toFixed(4)}`}
        style={{ width: '100%', maxWidth: W, height: 'auto', display: 'block', borderRadius: 8 }}
      />

      <label
        style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, marginTop: 14 }}
      >
        <span style={{ width: 230 }}>D slides along AB: AD/AB = {t.toFixed(2)}</span>
        <input
          type="range"
          min={0.1}
          max={0.9}
          step={0.01}
          value={t}
          data-testid="sim-t"
          aria-label="Position of D along AB as a fraction of AB"
          onChange={(e) => setT(Number(e.target.value))}
          style={{ flex: 1, maxWidth: 300 }}
        />
      </label>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'center', marginTop: 12 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
          <input
            type="checkbox"
            checked={showInner}
            data-testid="sim-inner-toggle"
            onChange={(e) => setShowInner(e.target.checked)}
          />
          <span>Shade triangle ADE</span>
        </label>
        <button
          type="button"
          data-testid="sim-reset"
          onClick={() => setT(0.5)}
          style={{
            fontSize: 13,
            padding: '6px 12px',
            borderRadius: 8,
            border: '1px solid #5b6f96',
            background: '#111a2e',
            color: C.ink,
            cursor: 'pointer',
          }}
        >
          Reset to the midpoint
        </button>
      </div>

      <dl
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
          gap: 8,
          margin: '14px 0 0',
          fontSize: 13,
        }}
      >
        <div>
          <dt style={{ color: C.dim }}>AD / DB</dt>
          <dd data-testid="sim-ratio-ad" style={{ margin: 0, color: C.inner }}>
            {fmt(ratioAdDb, 4)}
          </dd>
        </div>
        <div>
          <dt style={{ color: C.dim }}>AE / EC</dt>
          <dd data-testid="sim-ratio-ae" style={{ margin: 0, color: C.inner }}>
            {fmt(ratioAeEc, 4)}
          </dd>
        </div>
        <div>
          <dt style={{ color: C.dim }}>DE / BC</dt>
          <dd data-testid="sim-ratio-de" style={{ margin: 0, color: C.parallel }}>
            {fmt(ratioDeBc, 4)}
          </dd>
        </div>
        <div>
          <dt style={{ color: C.dim }}>AB / AD (similarity scale)</dt>
          <dd data-testid="sim-scale" style={{ margin: 0 }}>
            {fmt(scaleAbAd, 4)}
          </dd>
        </div>
        <div>
          <dt style={{ color: C.dim }}>|m(DE) − m(BC)| (parallel ⇒ 0)</dt>
          <dd data-testid="sim-slope-gap" style={{ margin: 0 }}>
            {slopeGap.toExponential(2)}
          </dd>
        </div>
        <div>
          <dt style={{ color: C.dim }}>AD, DB, AE, EC</dt>
          <dd data-testid="sim-lengths" style={{ margin: 0 }}>
            {fmt(ad)} , {fmt(db)} , {fmt(ae)} , {fmt(ec)}
          </dd>
        </div>
      </dl>

      <p data-testid="sim-what-to-notice" style={{ fontSize: 13, margin: '14px 0 0' }}>
        <strong>What to notice:</strong> slide D anywhere along AB and AD/DB keeps matching AE/EC — the
        Basic Proportionality Theorem. DE stays parallel to BC, and triangle ADE is just a scaled copy
        of triangle ABC by the factor AB/AD.
      </p>
      <p data-testid="sim-try-this" style={{ fontSize: 13, margin: '6px 0 0', color: C.dim }}>
        <strong>Try this:</strong> park D at the midpoint (t = 0.5) and check DE = BC/2. Then push t to
        0.9 — AD/DB becomes 9 and AE/EC must still agree to four decimal places.
      </p>
    </section>
  );
}
